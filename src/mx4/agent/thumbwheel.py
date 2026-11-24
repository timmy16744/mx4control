"""Thumb-wheel action engine (agent-local).

When the MX Master 4 thumb wheel is diverted (``THUMBWHEEL 0x2150``),
``mx4-sysd`` emits ``ThumbwheelEvent(delta, direction)`` over D-Bus.
This module accumulates raw ticks against ``ThumbWheelSettings.step``
and fires the configured positive/negative action plus an optional
haptic tick.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable, Optional

from ..config.schema import Config, ThumbWheelSettings

logger = logging.getLogger(__name__)

# Clear stale partial ticks after brief thumb pause so next intentional roll is crisp
IDLE_RESET_S = 0.48
# Guard burst action firing while still supporting fine 1-4 tick micro-steps
MAX_BURST_PER_FEED = 6
# Rate-limit high-frequency Digital-Crown micro-haptics (~45 Hz max)
MICRO_HAPTIC_MIN_INTERVAL_S = 0.022
MICRO_TICK_STEP = 3  # 120 / 3 = 40 silky micro-detents per wheel revolution
MICRO_HAPTIC_PATTERN = 4  # Subtle Impact (distinct softer tick between main action detents)


# Built-in quick presets for the thumb wheel when in Actions mode.
# (id, label, positive_type, positive_data, negative_type, negative_data)
THUMBWHEEL_PRESETS: dict[str, tuple[str, str, str, str, str]] = {
    "tabs":        ("Switch browser/editor tabs",   "keystroke", "ctrl+Tab",                                             "keystroke", "ctrl+shift+Tab"),
    "volume":      ("System volume 5% (PipeWire)",  "command",   "wpctl set-volume -l 1.5 @DEFAULT_AUDIO_SINK@ 5%+",     "command",   "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-"),
    "volume_fine": ("System volume 1% (Fine)",      "command",   "wpctl set-volume -l 1.5 @DEFAULT_AUDIO_SINK@ 1%+",     "command",   "wpctl set-volume @DEFAULT_AUDIO_SINK@ 1%-"),
    "zoom":        ("Zoom in / out",                "keystroke", "ctrl+plus",                                            "keystroke", "ctrl+minus"),
    "workspaces":  ("Hyprland workspaces",          "command",   "hyprctl dispatch workspace +1",                        "command",   "hyprctl dispatch workspace -1"),
    "timeline":    ("Timeline / frame scrub",       "keystroke", "Right",                                                "keystroke", "Left"),
    "brush":       ("Brush / font size ([ / ])",    "keystroke", "bracketright",                                         "keystroke", "bracketleft"),
    "brightness":  ("Display brightness",           "command",   "brightnessctl set +5%",                                "command",   "brightnessctl set 5%-"),
    "media":       ("Media next / previous",        "command",   "playerctl next",                                       "command",   "playerctl previous"),
    "history":     ("Navigate forward / back",      "keystroke", "alt+Right",                                            "keystroke", "alt+Left"),
    "scroll_v":    ("Fine vertical step (Up/Dn)",   "keystroke", "Up",                                                   "keystroke", "Down"),
    "custom":      ("Custom actions",               "keystroke", "ctrl+Tab",                                             "keystroke", "ctrl+shift+Tab"),
}


class ThumbWheelHandler:
    """Accumulates diverted 6× (120 ticks/rev) thumb-wheel deltas and dispatches actions."""

    def __init__(
        self,
        config_provider: Callable[[], Config],
        execute_fn: Callable[[str, str], bool],
        haptic_fn: Optional[Callable[[int], bool]] = None,
    ) -> None:
        self._config_provider = config_provider
        self._execute = execute_fn
        self._haptic = haptic_fn
        self._acc = 0
        self._micro_acc = 0
        self._last_t = 0.0
        self._last_haptic_t = 0.0
        # Ordered action queue prevents concurrent shell commands (e.g. 1% wpctl) from racing
        self._q: queue.Queue[tuple[str, str]] = queue.Queue(maxsize=16)
        self._worker = threading.Thread(
            target=self._run_queue, name="MX4ThumbActions", daemon=True,
        )
        self._worker.start()

    def _run_queue(self) -> None:
        while True:
            atype, adata = self._q.get()
            try:
                self._execute(atype, adata)
            except Exception:
                logger.exception("thumbwheel action %s:%s failed", atype, adata)
            finally:
                self._q.task_done()

    def reset(self) -> None:
        self._acc = 0
        self._micro_acc = 0
        self._last_t = 0.0

    def _pulse_haptic(self, pattern: int, ts: float, force: bool = False) -> None:
        if self._haptic is None:
            return
        if force or (ts - self._last_haptic_t) >= MICRO_HAPTIC_MIN_INTERVAL_S:
            self._last_haptic_t = ts
            self._haptic(max(0, min(14, int(pattern))))

    def feed(self, delta: int, direction: int = 0, now: Optional[float] = None) -> int:
        """Feed one raw signed thumb-wheel delta (120 ticks/rev). Returns actions fired."""
        if delta == 0:
            return 0
        cfg = self._config_provider()
        tw: ThumbWheelSettings = cfg.thumbwheel
        # Never fire custom actions if thumb wheel is configured for HD Scroll mode
        if tw.mode == "hd_scroll":
            return 0

        ts = time.monotonic() if now is None else now
        if self._last_t > 0 and (ts - self._last_t) > IDLE_RESET_S:
            self._acc = 0
            self._micro_acc = 0
        self._last_t = ts

        step = max(1, int(tw.step))
        # Reset accumulators on direction reversal for crisp feel
        if (self._acc > 0 > delta) or (self._acc < 0 < delta):
            self._acc = 0
            self._micro_acc = 0
        self._acc += delta
        self._micro_acc += delta

        fired = 0
        action_pattern = int(getattr(tw, "haptic_pattern", cfg.haptics.ring_boundary_pattern))
        while abs(self._acc) >= step and fired < MAX_BURST_PER_FEED:
            if self._acc > 0:
                atype, adata = tw.positive_type, tw.positive_data
                self._acc -= step
            else:
                atype, adata = tw.negative_type, tw.negative_data
                self._acc += step
            fired += 1
            if adata and atype != "disabled":
                logger.debug("thumbwheel → %s:%s", atype, adata)
                try:
                    self._q.put_nowait((atype, adata))
                except queue.Full:
                    pass
                if tw.haptic_tick and cfg.haptics.enabled:
                    self._pulse_haptic(action_pattern, ts, force=(fired == 1))

        # 6x Digital-Crown micro-detent texture between coarser action steps (step > 4)
        if (
            fired == 0
            and tw.haptic_tick
            and getattr(tw, "micro_haptics", True)
            and cfg.haptics.enabled
            and step > MICRO_TICK_STEP
            and abs(self._micro_acc) >= MICRO_TICK_STEP
        ):
            steps_crossed = int(self._micro_acc / MICRO_TICK_STEP)
            self._micro_acc -= steps_crossed * MICRO_TICK_STEP
            self._pulse_haptic(MICRO_HAPTIC_PATTERN, ts, force=False)
        elif fired > 0:
            self._micro_acc = 0

        # Clamp any leftover burst backlog so huge flicks don't queue stale actions
        if abs(self._acc) >= step * 2:
            self._acc = int(step - 1) if self._acc > 0 else -int(step - 1)
        return fired
