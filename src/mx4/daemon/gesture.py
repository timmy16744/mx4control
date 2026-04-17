"""Gesture engine.

Detects the gesture-button press/release via HID++ button-diversion
notifications, tracks cursor movement via evdev, and drives the
Actions Ring overlay. Designed for sub-50 ms latency from press to
first paint.

Flow::

    press (HID++ notification, sw_id=0, feature_idx=REPROG)
      ├─ grab evdev device (cursor freezes)
      ├─ GLib.idle_add → overlay.show_at(cursor_x, cursor_y)
      │   ↓
      ├─ each REL_X/REL_Y accumulates (dx, dy)
      │   ├─ update segment selection
      │   └─ haptic tick on boundary crossing
      │
    release (HID++ notification)
      ├─ ungrab (cursor resumes)
      ├─ overlay.hide() → returns selected segment
      └─ executor.execute(segment.action)

The evdev device is always grabbed during a gesture — we pull movement
events out of the evdev fd ourselves so we know what happened, but the
compositor never sees them. That gives the Actions Ring its
"frame of reference" feel: physical mouse motion maps straight to ring
segments without the OS cursor drifting.
"""

from __future__ import annotations

import logging
import math
import struct
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

try:
    import evdev  # type: ignore[import-not-found]
    from evdev import ecodes
except ImportError:
    evdev = None  # type: ignore[assignment]
    ecodes = None  # type: ignore[assignment]

from ..hidpp import HIDPPDispatcher, MXMaster4, FeatureID, ControlID
from ..hidpp.dispatcher import Notification

logger = logging.getLogger(__name__)


# Trigger CIDs in priority order. GESTURE_BUTTON is preferred; BACK is
# only diverted when GESTURE_BUTTON refuses to divert (older firmware).
PRIMARY_TRIGGER = ControlID.GESTURE_BUTTON
FALLBACK_TRIGGER = ControlID.BACK


@dataclass
class GestureEvent:
    direction_index: Optional[int]  # 0..7 clockwise from top, or None for cancel
    dx: int
    dy: int
    distance: float
    duration_s: float


GestureStartHandler = Callable[[], None]
GestureMoveHandler = Callable[[int, int, Optional[int]], None]  # dx, dy, selected_segment
GestureEndHandler = Callable[[GestureEvent], None]


# Ring geometry (must match the overlay)
SEGMENT_COUNT = 8
CANCEL_RADIUS = 40  # pixels of movement before selecting a segment


class GestureEngine:
    """Subscribes to HID++ notifications + evdev movement."""

    def __init__(
        self,
        device: MXMaster4,
        *,
        on_start: GestureStartHandler,
        on_move: GestureMoveHandler,
        on_end: GestureEndHandler,
    ):
        self._device = device
        self._dispatcher: HIDPPDispatcher = device.dispatcher

        self._on_start = on_start
        self._on_move = on_move
        self._on_end = on_end

        self._evdev: Optional[object] = None  # evdev.InputDevice
        self._evdev_thread: Optional[threading.Thread] = None
        self._running = False
        self._evdev_grabbed = False

        # Gesture state
        self._lock = threading.Lock()
        self._active = False
        self._start_time = 0.0
        self._dx = 0
        self._dy = 0
        self._selected_segment: Optional[int] = None

        # Which CID triggered: gesture button, or back-fallback
        self._trigger_cid: Optional[int] = None
        self._diverted_cids: set[int] = set()

    # ─── lifecycle ──────────────────────────────────────────────────────

    def start(self) -> bool:
        if self._running:
            return True
        if evdev is None:
            logger.error("evdev not available — cannot detect cursor motion")
            return False

        self._evdev = self._find_mouse_evdev()
        if self._evdev is None:
            logger.error("no matching mouse evdev device found")
            return False

        if not self._setup_hidpp_diversion():
            logger.error("HID++ button diversion unavailable")
            return False

        self._dispatcher.subscribe(self._on_notification)

        self._running = True
        self._evdev_thread = threading.Thread(
            target=self._evdev_loop, name="MX4EvdevReader", daemon=True,
        )
        self._evdev_thread.start()
        logger.info(f"Gesture engine started (trigger CID 0x{self._trigger_cid:04X})")
        return True

    def stop(self) -> None:
        self._running = False
        self._dispatcher.unsubscribe(self._on_notification)

        for cid in list(self._diverted_cids):
            self._device.divert_button(cid, False)
        self._diverted_cids.clear()

        self._unfreeze()
        if self._evdev_thread:
            self._evdev_thread.join(timeout=1.0)
        self._evdev_thread = None
        self._evdev = None
        logger.info("Gesture engine stopped")

    # ─── HID++ diversion ────────────────────────────────────────────────

    def _setup_hidpp_diversion(self) -> bool:
        if not self._dispatcher.has_feature(FeatureID.REPROG_CONTROLS_V4):
            return False
        self._reprog_idx = self._dispatcher.feature_index(FeatureID.REPROG_CONTROLS_V4)

        if self._device.divert_button(PRIMARY_TRIGGER, True):
            self._trigger_cid = PRIMARY_TRIGGER
            self._diverted_cids.add(PRIMARY_TRIGGER)
            return True
        if self._device.divert_button(FALLBACK_TRIGGER, True):
            self._trigger_cid = FALLBACK_TRIGGER
            self._diverted_cids.add(FALLBACK_TRIGGER)
            logger.warning(
                "Falling back to BACK-button trigger — browser navigation "
                "may be affected while the daemon runs."
            )
            return True
        return False

    def _on_notification(self, note: Notification) -> None:
        if note.feature_index != self._reprog_idx:
            return
        if note.function_id != 0:  # divertedButtonsEvent only
            return
        # Payload is 4 big-endian CIDs, zero-padded
        if len(note.payload) < 8:
            return
        try:
            cids = struct.unpack(">HHHH", note.payload[:8])
        except struct.error:
            return
        pressed_now = {c for c in cids if c == self._trigger_cid}

        # Re-enter _lock only for state flip
        with self._lock:
            was_active = self._active
            now_active = bool(pressed_now)

        if now_active and not was_active:
            self._begin_gesture()
        elif was_active and not now_active:
            self._end_gesture()

    # ─── evdev loop (cursor movement) ───────────────────────────────────

    def _find_mouse_evdev(self):
        assert evdev is not None
        candidates = []
        for path in evdev.list_devices():
            try:
                d = evdev.InputDevice(path)
                name = d.name.lower()
                if "mx master 4" in name:
                    return d
                if ("logitech" in name or "usb receiver" in name) and "mouse" in name:
                    caps = d.capabilities()
                    rel = caps.get(ecodes.EV_REL, [])
                    if ecodes.REL_X in rel and ecodes.REL_Y in rel:
                        candidates.append((len(rel), d))
            except (PermissionError, OSError):
                continue
        if candidates:
            candidates.sort(reverse=True, key=lambda x: x[0])
            return candidates[0][1]
        return None

    def _evdev_loop(self) -> None:
        assert evdev is not None
        try:
            for event in self._evdev.read_loop():
                if not self._running:
                    break
                if event.type != ecodes.EV_REL:
                    continue
                with self._lock:
                    if not self._active:
                        continue
                    if event.code == ecodes.REL_X:
                        self._dx += event.value
                    elif event.code == ecodes.REL_Y:
                        self._dy += event.value
                    dx, dy = self._dx, self._dy

                # Compute current segment (outside lock so handler is free)
                new_seg = _segment_for(dx, dy)
                if new_seg != self._selected_segment:
                    self._selected_segment = new_seg
                try:
                    self._on_move(dx, dy, new_seg)
                except Exception as e:
                    logger.error(f"on_move handler raised: {e}")
        except OSError as e:
            if self._running:
                logger.error(f"evdev loop error: {e}")

    # ─── gesture state transitions ──────────────────────────────────────

    def _begin_gesture(self) -> None:
        with self._lock:
            if self._active:
                return
            self._active = True
            self._start_time = time.time()
            self._dx = 0
            self._dy = 0
            self._selected_segment = None

        self._freeze()
        try:
            self._on_start()
        except Exception as e:
            logger.error(f"on_start handler raised: {e}")

    def _end_gesture(self) -> None:
        # Ungrab first so the cursor always recovers
        self._unfreeze()

        with self._lock:
            if not self._active:
                return
            self._active = False
            dx, dy = self._dx, self._dy
            sel = self._selected_segment
            duration = time.time() - self._start_time

        evt = GestureEvent(
            direction_index=sel,
            dx=dx, dy=dy,
            distance=math.hypot(dx, dy),
            duration_s=duration,
        )
        try:
            self._on_end(evt)
        except Exception as e:
            logger.error(f"on_end handler raised: {e}")

    # ─── cursor freeze via evdev grab ───────────────────────────────────

    def _freeze(self) -> None:
        if self._evdev_grabbed or self._evdev is None:
            return
        try:
            self._evdev.grab()
            self._evdev_grabbed = True
        except OSError as e:
            logger.debug(f"grab failed: {e}")

    def _unfreeze(self) -> None:
        if not self._evdev_grabbed or self._evdev is None:
            return
        try:
            self._evdev.ungrab()
        except OSError:
            pass
        finally:
            self._evdev_grabbed = False


# ─────────────────────────── segment geometry ───────────────────────────

def _segment_for(dx: int, dy: int) -> Optional[int]:
    """Return 0..7 (clockwise from top) or None for cancel."""
    if dx * dx + dy * dy < CANCEL_RADIUS * CANCEL_RADIUS:
        return None
    angle = math.atan2(dy, dx) + math.pi / 2
    if angle < 0:
        angle += 2 * math.pi
    seg_angle = 2 * math.pi / SEGMENT_COUNT
    return int((angle + seg_angle / 2) / seg_angle) % SEGMENT_COUNT
