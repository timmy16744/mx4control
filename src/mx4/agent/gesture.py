"""Gesture engine (agent-local).

Same evdev-grab + cursor-freeze behaviour as the monolithic daemon, but
the press/release edges no longer come from a local HID++ dispatcher.
Instead the system daemon diverts the gesture-trigger CID and emits
``DivertedButtonEvent`` over D-Bus; the agent feeds that signal into
:meth:`GestureEngine.feed_diverted` (set of currently-held CIDs). A
press of the trigger CID begins a gesture, its release ends it.

Flow::

    DivertedButtonEvent {trigger}  (System D-Bus signal)
      ├─ grab evdev device (cursor freezes)
      ├─ on_start() → overlay.show_at_cursor()
      ├─ each REL_X/REL_Y accumulates (dx, dy)
      │   ├─ update segment selection
      │   └─ haptic tick on boundary crossing (sysclient.trigger_haptic)
      │
    DivertedButtonEvent {}  (trigger released)
      ├─ ungrab (cursor resumes)
      └─ on_end(GestureEvent) → overlay.hide_and_pick() + executor

The evdev device is grabbed for the gesture's duration so physical mouse
motion drives ring selection without the OS cursor drifting; we read the
REL events ourselves out of the evdev fd.
"""

from __future__ import annotations

import logging
import math
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

logger = logging.getLogger(__name__)


@dataclass
class GestureEvent:
    direction_index: Optional[int]  # 0..7 clockwise from top, or None for cancel
    dx: int
    dy: int
    distance: float
    duration_s: float


GestureStartHandler = Callable[[], None]
GestureMoveHandler = Callable[[int, int, Optional[int]], None]  # dx, dy, selected
GestureEndHandler = Callable[[GestureEvent], None]


# Ring geometry (must match the overlay)
SEGMENT_COUNT = 8
CANCEL_RADIUS = 40  # pixels of movement before selecting a segment


class GestureEngine:
    """Drives the Actions Ring from DivertedButtonEvent edges + evdev motion."""

    def __init__(
        self,
        *,
        trigger_cid: int,
        on_start: GestureStartHandler,
        on_move: GestureMoveHandler,
        on_end: GestureEndHandler,
        cancel_radius: int = CANCEL_RADIUS,
    ):
        self._trigger_cid = trigger_cid
        self._on_start = on_start
        self._on_move = on_move
        self._on_end = on_end
        self._cancel_radius = max(15, min(120, int(cancel_radius)))

        self._evdev: Optional[object] = None  # evdev.InputDevice
        self._evdev_thread: Optional[threading.Thread] = None
        self._running = False
        self._evdev_grabbed = False

        # Gesture state
        self._lock = threading.Lock()
        self._enabled = True
        self._active = False
        self._start_time = 0.0
        self._dx = 0
        self._dy = 0
        self._selected_segment: Optional[int] = None

    @property
    def trigger_cid(self) -> int:
        return self._trigger_cid

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        """Soft toggle — when disabled the trigger press is ignored.

        If a gesture is currently active it is ended (and the grab
        released) so the cursor never stays frozen.
        """
        self._enabled = bool(enabled)
        if not self._enabled and self.active:
            self._end_gesture()

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

        self._running = True
        self._evdev_thread = threading.Thread(
            target=self._evdev_loop, name="MX4EvdevReader", daemon=True,
        )
        self._evdev_thread.start()
        logger.info("Gesture engine started (trigger CID 0x%04X)", self._trigger_cid)
        return True

    def stop(self) -> None:
        self._running = False
        self._unfreeze()
        if self._evdev_thread:
            self._evdev_thread.join(timeout=1.0)
        self._evdev_thread = None
        self._evdev = None
        logger.info("Gesture engine stopped")

    # ─── DivertedButtonEvent edge handling ──────────────────────────────

    def feed_diverted(self, held_cids: set[int]) -> None:
        """Feed the latest set of held diverted CIDs from the System bus.

        Detects the press/release edge of the trigger CID and begins /
        ends a gesture accordingly. Called on the GLib main thread.
        """
        if not self._running:
            return
        trigger_held = self._trigger_cid in held_cids

        with self._lock:
            was_active = self._active

        if trigger_held and not was_active:
            if self._enabled:
                self._begin_gesture()
        elif was_active and not trigger_held:
            self._end_gesture()

    def rebind_device(self) -> None:
        """Re-acquire the MX Master 4 evdev node after sleep/hotplug."""
        if not self._running or evdev is None:
            return
        if self._evdev_thread is not None and self._evdev_thread.is_alive():
            return
        self._evdev = self._find_mouse_evdev()
        if self._evdev is not None:
            self._evdev_thread = threading.Thread(
                target=self._evdev_loop, name="MX4EvdevReader", daemon=True,
            )
            self._evdev_thread.start()
            logger.info("Gesture engine re-bound evdev device")

    # ─── evdev loop (cursor movement) ───────────────────────────────────

    def _find_mouse_evdev(self):
        assert evdev is not None
        candidates = []
        for path in evdev.list_devices():
            try:
                d = evdev.InputDevice(path)
                name = d.name.lower()
                # Never grab our own virtual uinput smooth-scroll device!
                if "mx4 studio" in name:
                    continue
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
        while self._running:
            if self._evdev is None:
                self._evdev = self._find_mouse_evdev()
                if self._evdev is None:
                    time.sleep(1.5)
                    continue
            try:
                for event in self._evdev.read_loop():
                    if not self._running:
                        break

                    if event.type == ecodes.EV_REL:
                        with self._lock:
                            if not self._active:
                                continue
                            if event.code == ecodes.REL_X:
                                self._dx += event.value
                            elif event.code == ecodes.REL_Y:
                                self._dy += event.value
                            dx, dy = self._dx, self._dy

                        new_seg = _segment_for(dx, dy, self._cancel_radius)
                        if new_seg != self._selected_segment:
                            self._selected_segment = new_seg
                        try:
                            self._on_move(dx, dy, new_seg)
                        except Exception as e:
                            logger.error(f"on_move handler raised: {e}")
            except OSError as e:
                if self._running:
                    logger.warning("evdev device lost (%s) — will auto-reconnect", e)
                self._unfreeze()
                try:
                    self._evdev.close()
                except Exception:
                    pass
                self._evdev = None
                if self._running:
                    time.sleep(1.5)

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
        # Safety watchdog: never leave cursor frozen if mouse sleeps mid-gesture
        self._watchdog = threading.Timer(12.0, self._safety_unfreeze)
        self._watchdog.daemon = True
        self._watchdog.start()
        try:
            self._on_start()
        except Exception as e:
            logger.error(f"on_start handler raised: {e}")

    def _safety_unfreeze(self) -> None:
        if self.active:
            logger.warning("gesture watchdog triggered — releasing evdev grab safely")
            self._end_gesture()

    def _end_gesture(self) -> None:
        # Cancel watchdog and ungrab first so the cursor always recovers
        wd = getattr(self, "_watchdog", None)
        if wd is not None:
            wd.cancel()
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

def _segment_for(dx: int, dy: int, cancel_radius: int = CANCEL_RADIUS) -> Optional[int]:
    """Return 0..7 (clockwise from top) or None for cancel."""
    if dx * dx + dy * dy < cancel_radius * cancel_radius:
        return None
    angle = math.atan2(dy, dx) + math.pi / 2
    if angle < 0:
        angle += 2 * math.pi
    seg_angle = 2 * math.pi / SEGMENT_COUNT
    return int((angle + seg_angle / 2) / seg_angle) % SEGMENT_COUNT
