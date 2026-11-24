"""Hardware-diverted Hi-Res Smooth Scroll & Speed Engine (``0x2121`` + uinput).

When vertical scroll tuning is active (``speed != 1.0``, ``smoothness > 0``,
or ``accel > 0``), ``mx4-sysd`` diverts ``HIRES_WHEEL (0x2121)`` so the mouse
streams raw sub-detent 16-bit wheel deltas over HID++ 2.0 instead of kernel
HID reports. This engine scales, accelerates, and (when ``smoothness > 0``)
smoothly interpolates those deltas at 144 Hz into virtual Linux input
``REL_WHEEL_HI_RES`` + properly accumulated ``REL_WHEEL`` events via
``/dev/uinput``.

When all tuning parameters are at neutral defaults (``speed == 1.0``,
``smoothness == 0``, ``accel == 0``), ``needs_diversion`` is ``False`` so the
mouse stays in native kernel HID mode with zero added latency.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

try:
    from evdev import UInput, ecodes  # type: ignore[import-not-found]
except ImportError:
    UInput = None  # type: ignore[assignment]
    ecodes = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Standard Linux REL_WHEEL_HI_RES units per traditional scroll detent
HIRES_UNITS_PER_NOTCH = 120.0
DEFAULT_HW_MULTIPLIER = 8  # Logitech MX Master 4 reports multiplier=8 (15 hi-res units/tick)
DEFAULT_TW_NATIVE_RES = 20     # MX Master 4 0x2150 native_res (20 ticks/rev)
DEFAULT_TW_DIVERTED_RES = 120  # MX Master 4 0x2150 diverted_res (120 ticks/rev = 6x detail!)
TICK_HZ = 144.0
TICK_DT = 1.0 / TICK_HZ
HAPTIC_DETENT_MIN_INTERVAL_S = 0.022  # up to ~45 Hz silky Digital-Crown micro-detents


@dataclass
class ScrollTuning:
    """User-adjustable vertical HD scroll physics parameters."""
    speed: float = 1.0       # 0.20 .. 4.00 (sensitivity / speed multiplier)
    smoothness: int = 0      # 0 .. 100 (% critically-damped interpolation)
    accel: int = 0           # 0 .. 100 (% dynamic flick velocity boost)
    invert: bool = False     # natural vertical scrolling
    hires: bool = True       # high-resolution sub-detent output

    def clamped(self) -> "ScrollTuning":
        return ScrollTuning(
            speed=round(max(0.20, min(4.00, float(self.speed))), 2),
            smoothness=max(0, min(100, int(self.smoothness))),
            accel=max(0, min(100, int(self.accel))),
            invert=bool(self.invert),
            hires=bool(self.hires),
        )

    @property
    def needs_diversion(self) -> bool:
        """True whenever software speed/smoothing/accel must intercept 0x2121."""
        return (
            abs(self.speed - 1.0) >= 0.01
            or self.smoothness > 0
            or self.accel > 0
        )


EmitCallback = Callable[[int, int], None]  # (hi_res_delta, legacy_notch_delta)


class _UInputScrollSink:
    """Minimal virtual uinput scroll device emitting vertical or horizontal hi-res scroll."""

    def __init__(self, axis: str = "vertical") -> None:
        self._axis = axis
        self._ui: Optional[object] = None

    @property
    def available(self) -> bool:
        return self._ui is not None

    def open(self) -> bool:
        if self._ui is not None:
            return True
        if UInput is None or ecodes is None:
            logger.warning("evdev.UInput unavailable — cannot start %s smooth scroll engine", self._axis)
            return False
        try:
            if self._axis == "horizontal":
                rel_codes = [ecodes.REL_HWHEEL, ecodes.REL_HWHEEL_HI_RES]
                dev_name = "MX4 Studio Hi-Res Thumb Wheel"
            else:
                rel_codes = [ecodes.REL_WHEEL, ecodes.REL_WHEEL_HI_RES]
                dev_name = "MX4 Studio Hi-Res Scroll"
            caps = {
                ecodes.EV_REL: rel_codes,
                ecodes.EV_KEY: [ecodes.BTN_LEFT],
            }
            self._ui = UInput(caps, name=dev_name)
            logger.info("opened virtual uinput device: %s", dev_name)
            return True
        except Exception as e:
            logger.warning("failed to open /dev/uinput for %s smooth scroll: %s", self._axis, e)
            self._ui = None
            return False

    def emit(self, hi_res: int, legacy_notches: int) -> None:
        if self._ui is None or ecodes is None:
            return
        if hi_res == 0 and legacy_notches == 0:
            return
        try:
            hi_code = ecodes.REL_HWHEEL_HI_RES if self._axis == "horizontal" else ecodes.REL_WHEEL_HI_RES
            lo_code = ecodes.REL_HWHEEL if self._axis == "horizontal" else ecodes.REL_WHEEL
            if hi_res != 0:
                self._ui.write(ecodes.EV_REL, hi_code, int(hi_res))
            if legacy_notches != 0:
                self._ui.write(ecodes.EV_REL, lo_code, int(legacy_notches))
            self._ui.syn()
        except Exception as e:
            logger.debug("uinput %s scroll emit failed: %s", self._axis, e)

    def close(self) -> None:
        if self._ui is not None:
            try:
                self._ui.close()
            except Exception:
                pass
            self._ui = None


class SmoothScrollEngine:
    """144 Hz critically-damped Hi-Res smooth scroll & sensitivity engine."""

    def __init__(
        self,
        *,
        hw_multiplier: int = DEFAULT_HW_MULTIPLIER,
        emit_fn: Optional[EmitCallback] = None,
    ) -> None:
        self._hw_mult = max(1, int(hw_multiplier))
        self._tuning = ScrollTuning()
        self._sink = _UInputScrollSink() if emit_fn is None else None
        self._emit_fn: EmitCallback = emit_fn if emit_fn is not None else self._sink.emit

        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Integrator state (all in REL_WHEEL_HI_RES units, 120 = 1 notch)
        self._pending_hires = 0.0
        self._frac_emit = 0.0
        self._notch_accum = 0.0
        self._last_feed_t = 0.0
        self._flick_rate = 0.0  # smoothed ticks/sec for dynamic acceleration

    @property
    def tuning(self) -> ScrollTuning:
        with self._lock:
            return self._tuning

    @property
    def active(self) -> bool:
        return self._running and (self._sink is None or self._sink.available)

    def set_hw_multiplier(self, multiplier: int) -> None:
        with self._lock:
            self._hw_mult = max(1, int(multiplier or DEFAULT_HW_MULTIPLIER))

    def configure(self, tuning: ScrollTuning) -> bool:
        """Update tuning live. Starts/stops uinput & worker automatically.

        Returns True if the requested mode is ready (including native bypass).
        """
        t = tuning.clamped()
        with self._lock:
            self._tuning = t

        if t.needs_diversion:
            return self.start()
        self.stop()
        return True

    def start(self) -> bool:
        if self._running:
            return True
        if self._sink is not None and not self._sink.open():
            return False
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, name="MX4SmoothScroll", daemon=True,
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        self._running = False
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        with self._lock:
            self._pending_hires = 0.0
            self._frac_emit = 0.0
            self._notch_accum = 0.0
            self._haptic_accum = 0.0
            self._flick_rate = 0.0
        if self._sink is not None:
            self._sink.close()

    def feed(self, raw_delta: int, hi_res: bool = True, now: Optional[float] = None) -> None:
        """Ingest one diverted ``0x2121`` wheel delta packet."""
        if raw_delta == 0:
            return
        ts = time.monotonic() if now is None else now

        with self._lock:
            t = self._tuning
            # Convert hardware delta into Linux REL_WHEEL_HI_RES units (120 per notch)
            unit_scale = (HIRES_UNITS_PER_NOTCH / self._hw_mult) if hi_res else HIRES_UNITS_PER_NOTCH
            signed_delta = -raw_delta if t.invert else raw_delta
            base_hires = signed_delta * unit_scale

            # Dynamic velocity acceleration on rapid flicks
            accel_gain = 1.0
            if t.accel > 0:
                dt = ts - self._last_feed_t if self._last_feed_t > 0 else 0.5
                dt = max(0.004, min(0.5, dt))
                inst_rate = abs(base_hires) / dt  # hi-res units / sec
                self._flick_rate = self._flick_rate * 0.65 + inst_rate * 0.35
                # Ramp smoothly above 240 hi-res/s (~2 notches/s) up to 2.6x at accel=100%
                excess = max(0.0, (self._flick_rate - 240.0) / 1400.0)
                accel_gain = 1.0 + (t.accel / 100.0) * min(1.8, excess * 1.45)
            self._last_feed_t = ts

            scaled = base_hires * t.speed * accel_gain

            # Instant crisp cancellation on scroll direction reversal (zero mushy overshoot!)
            if (self._pending_hires > 0 > scaled) or (self._pending_hires < 0 < scaled):
                self._pending_hires = 0.0
                self._frac_emit = 0.0

            if t.smoothness <= 0:
                # Direct scaled mode (0% smoothness) — emit immediately with zero lag!
                emit_hi, emit_notch = self._quantize_emit(scaled, t.hires)
            else:
                self._pending_hires += scaled
                # Cap runaway backlog on massive free-spin flicks
                self._pending_hires = max(-2400.0, min(2400.0, self._pending_hires))
                emit_hi, emit_notch = 0, 0

        if emit_hi != 0 or emit_notch != 0:
            self._emit_fn(emit_hi, emit_notch)
        elif t.smoothness > 0:
            self._wake.set()

    def step(self, dt: float) -> tuple[int, int]:
        """Advance the critically-damped smoother by ``dt`` seconds.

        Exposed for deterministic unit testing and called at 144 Hz by ``_run_loop``.
        """
        with self._lock:
            rem = self._pending_hires
            if rem == 0.0:
                return 0, 0

            # Exponential time constant tau: 16 ms (smooth=1%) .. 125 ms (smooth=100%)
            s_norm = self._tuning.smoothness / 100.0
            tau = 0.016 + (s_norm ** 1.25) * 0.109
            alpha = 1.0 - math.exp(-dt / tau)
            chunk = rem * alpha
            # Finish tiny tails cleanly without dropping sub-unit displacement
            if abs(rem) <= 0.8:
                chunk = rem
                self._pending_hires = 0.0
            else:
                if abs(chunk) < 0.8:
                    chunk = math.copysign(0.8, rem)
                self._pending_hires -= chunk

            hi_emit, notch_emit = self._quantize_emit(chunk, self._tuning.hires)
            return hi_emit, notch_emit

    def _quantize_emit(self, delta_hires: float, hires_enabled: bool) -> tuple[int, int]:
        """Accumulate sub-unit fractional hi-res & legacy 120-unit notches cleanly."""
        self._frac_emit += delta_hires
        # Guard IEEE-754 float drift (e.g. 0.99999999999998 -> 1)
        eps = math.copysign(1e-6, self._frac_emit) if self._frac_emit != 0.0 else 0.0
        hi_int = int(math.trunc(self._frac_emit + eps))
        self._frac_emit -= hi_int
        if abs(self._frac_emit) < 1e-6:
            self._frac_emit = 0.0

        self._notch_accum += hi_int
        notches = int(math.trunc(self._notch_accum / HIRES_UNITS_PER_NOTCH))
        self._notch_accum -= notches * HIRES_UNITS_PER_NOTCH

        if not hires_enabled:
            return 0, notches
        return hi_int, notches

    def _run_loop(self) -> None:
        while self._running:
            self._wake.wait(timeout=0.25)
            self._wake.clear()
            last = time.monotonic()
            while self._running:
                now = time.monotonic()
                dt = max(0.001, min(0.05, now - last))
                last = now
                hi_emit, notch_emit = self.step(dt)
                if hi_emit != 0 or notch_emit != 0:
                    self._emit_fn(hi_emit, notch_emit)
                with self._lock:
                    done = self._pending_hires == 0.0
                if done:
                    break
                time.sleep(TICK_DT)


@dataclass
class ThumbWheelTuning:
    """User-adjustable 6× Hi-Res horizontal thumb-wheel physics (``0x2150``)."""
    enabled: bool = False        # True when thumbwheel_mode == "hd_scroll"
    speed: float = 1.0           # 0.20 .. 4.00 horizontal speed multiplier
    smoothness: int = 35         # 0 .. 100 (% 144 Hz critically-damped glide)
    accel: int = 25              # 0 .. 100 (% dynamic thumb flick velocity boost)
    invert: bool = False         # natural horizontal scroll direction
    hires: bool = True           # emit REL_HWHEEL_HI_RES sub-detent units
    haptic_detent: bool = False  # virtual LRA micro-click on horizontal detents
    haptic_density: int = 6      # 1 (120u) | 2 (60u) | 3 (40u) | 6 (20u = every micro-tick!)
    haptic_pattern: int = 1      # LRA waveform id 0..14

    def clamped(self) -> "ThumbWheelTuning":
        dens = int(self.haptic_density)
        if dens not in (1, 2, 3, 6):
            dens = 6
        return ThumbWheelTuning(
            enabled=bool(self.enabled),
            speed=round(max(0.20, min(4.00, float(self.speed))), 2),
            smoothness=max(0, min(100, int(self.smoothness))),
            accel=max(0, min(100, int(self.accel))),
            invert=bool(self.invert),
            hires=bool(self.hires),
            haptic_detent=bool(self.haptic_detent),
            haptic_density=dens,
            haptic_pattern=max(0, min(14, int(self.haptic_pattern))),
        )


class HorizontalScrollEngine:
    """6× Hardware Hi-Res 144 Hz Horizontal Thumb Wheel Engine (``0x2150``).

    When ``THUMBWHEEL (0x2150)`` is diverted, the MX Master 4 switches from
    coarse ``20 ticks/rev`` native HID reporting to ``120 ticks/rev`` (6×
    finer detail) with 1 ms hardware timestamps. This engine converts each
    micro-tick into smooth 144 Hz ``REL_HWHEEL_HI_RES`` + accumulated
    ``REL_HWHEEL`` events via ``/dev/uinput`` and optionally fires crisp
    virtual LRA haptic detents on every virtual horizontal notch.
    """

    def __init__(
        self,
        *,
        native_res: int = DEFAULT_TW_NATIVE_RES,
        diverted_res: int = DEFAULT_TW_DIVERTED_RES,
        emit_fn: Optional[EmitCallback] = None,
        on_detent: Optional[Callable[[], None]] = None,
    ) -> None:
        self._native_res = max(1, int(native_res or DEFAULT_TW_NATIVE_RES))
        self._diverted_res = max(1, int(diverted_res or DEFAULT_TW_DIVERTED_RES))
        self._tuning = ThumbWheelTuning()
        self._sink = _UInputScrollSink(axis="horizontal") if emit_fn is None else None
        self._emit_fn: EmitCallback = emit_fn if emit_fn is not None else self._sink.emit
        self._on_detent = on_detent

        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._running = False
        self._thread: Optional[threading.Thread] = None

        self._pending_hires = 0.0
        self._frac_emit = 0.0
        self._notch_accum = 0.0
        self._haptic_accum = 0.0
        self._last_feed_t = 0.0
        self._flick_rate = 0.0
        self._last_detent_t = 0.0

    @property
    def tuning(self) -> ThumbWheelTuning:
        with self._lock:
            return self._tuning

    @property
    def active(self) -> bool:
        return self._running and (self._sink is None or self._sink.available)

    @property
    def resolution_ratio(self) -> float:
        with self._lock:
            return max(1.0, float(self._diverted_res) / float(self._native_res))

    def set_hardware_resolution(self, native_res: int, diverted_res: int) -> None:
        with self._lock:
            if native_res and native_res > 0:
                self._native_res = int(native_res)
            if diverted_res and diverted_res > 0:
                self._diverted_res = int(diverted_res)

    def configure(self, tuning: ThumbWheelTuning) -> bool:
        """Apply horizontal tuning live. Starts/stops uinput & 144 Hz loop."""
        t = tuning.clamped()
        with self._lock:
            self._tuning = t
        if t.enabled:
            return self.start()
        self.stop()
        return True

    def start(self) -> bool:
        if self._running:
            return True
        if self._sink is not None and not self._sink.open():
            return False
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, name="MX4ThumbWheelHD", daemon=True,
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        self._running = False
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        with self._lock:
            self._pending_hires = 0.0
            self._frac_emit = 0.0
            self._notch_accum = 0.0
            self._haptic_accum = 0.0
            self._flick_rate = 0.0
        if self._sink is not None:
            self._sink.close()

    def feed(
        self,
        raw_delta: int,
        *,
        elapsed_ms: int = 0,
        status: int = 2,
        now: Optional[float] = None,
    ) -> None:
        """Ingest one diverted ``0x2150`` thumb-wheel delta at 6× hardware resolution."""
        if raw_delta == 0:
            return
        ts = time.monotonic() if now is None else now
        fire_detent = False

        with self._lock:
            t = self._tuning
            # 1 full native detent == (diverted_res / native_res) ticks == 120 REL_HWHEEL_HI_RES units.
            # On MX Master 4 (120 / 20 = 6.0): 1 micro-tick == 20 REL_HWHEEL_HI_RES units!
            ratio = max(1.0, float(self._diverted_res) / float(self._native_res))
            unit_scale = HIRES_UNITS_PER_NOTCH / ratio
            signed_delta = -raw_delta if t.invert else raw_delta
            base_hires = signed_delta * unit_scale

            # Use 1 ms hardware timestamp when available (immune to USB/Bolt coalescing!)
            if elapsed_ms and elapsed_ms > 0:
                dt = max(0.004, min(0.5, elapsed_ms / 1000.0))
            elif self._last_feed_t > 0:
                dt = max(0.004, min(0.5, ts - self._last_feed_t))
            else:
                dt = 0.5
            self._last_feed_t = ts

            # Thumb-calibrated dynamic velocity acceleration:
            # Slow rolls stay pixel-precise; brisk thumb flicks accelerate up to 3.0×.
            accel_gain = 1.0
            if t.accel > 0:
                inst_rate = abs(base_hires) / dt
                self._flick_rate = self._flick_rate * 0.62 + inst_rate * 0.38
                excess = max(0.0, (self._flick_rate - 180.0) / 1100.0)
                accel_gain = 1.0 + (t.accel / 100.0) * min(2.0, excess * 1.55)

            scaled = base_hires * t.speed * accel_gain

            # Instant crisp cancellation on horizontal direction reversal
            if (self._pending_hires > 0 > scaled) or (self._pending_hires < 0 < scaled):
                self._pending_hires = 0.0
                self._frac_emit = 0.0
                self._haptic_accum = 0.0

            detent_pattern = t.haptic_pattern
            if t.smoothness <= 0:
                emit_hi, emit_notch = self._quantize_emit(scaled, t.hires)
                if t.haptic_detent and self._advance_haptic_detent(scaled, t.haptic_density, ts):
                    fire_detent = True
            else:
                self._pending_hires += scaled
                self._pending_hires = max(-2400.0, min(2400.0, self._pending_hires))
                emit_hi, emit_notch = 0, 0

        if emit_hi != 0 or emit_notch != 0:
            self._emit_fn(emit_hi, emit_notch)
        elif t.smoothness > 0:
            self._wake.set()
        if fire_detent and self._on_detent is not None:
            self._fire_detent(detent_pattern)

    def step(self, dt: float, now: Optional[float] = None) -> tuple[int, int]:
        """Advance the 144 Hz critically-damped horizontal smoother by ``dt`` seconds."""
        fire_detent = False
        detent_pattern = 1
        ts = time.monotonic() if now is None else now
        with self._lock:
            rem = self._pending_hires
            if rem == 0.0:
                return 0, 0
            s_norm = self._tuning.smoothness / 100.0
            tau = 0.014 + (s_norm ** 1.25) * 0.106
            alpha = 1.0 - math.exp(-dt / tau)
            chunk = rem * alpha
            if abs(rem) <= 0.8:
                chunk = rem
                self._pending_hires = 0.0
            else:
                if abs(chunk) < 0.8:
                    chunk = math.copysign(0.8, rem)
                self._pending_hires -= chunk

            hi_emit, notch_emit = self._quantize_emit(chunk, self._tuning.hires)
            if self._tuning.haptic_detent:
                detent_pattern = self._tuning.haptic_pattern
                if self._advance_haptic_detent(chunk, self._tuning.haptic_density, ts):
                    fire_detent = True

        if fire_detent and self._on_detent is not None:
            self._fire_detent(detent_pattern)
        return hi_emit, notch_emit

    def _fire_detent(self, pattern: int) -> None:
        if self._on_detent is None:
            return
        try:
            self._on_detent(pattern)  # type: ignore[call-arg]
        except TypeError:
            try:
                self._on_detent()  # type: ignore[call-arg]
            except Exception:
                pass
        except Exception:
            pass

    def _advance_haptic_detent(self, delta_hires: float, density: int, ts: float) -> bool:
        """Accumulate hi-res displacement against density (6x=20u, 3x=40u, 2x=60u, 1x=120u)."""
        step_u = HIRES_UNITS_PER_NOTCH / max(1, int(density))
        if (self._haptic_accum > 0 > delta_hires) or (self._haptic_accum < 0 < delta_hires):
            self._haptic_accum = 0.0
        self._haptic_accum += delta_hires
        crossed = int(math.trunc(self._haptic_accum / step_u))
        if crossed == 0:
            return False
        self._haptic_accum -= crossed * step_u
        return self._consume_detent_budget(ts)

    def _consume_detent_budget(self, ts: float) -> bool:
        if (ts - self._last_detent_t) >= HAPTIC_DETENT_MIN_INTERVAL_S:
            self._last_detent_t = ts
            return True
        return False

    def _quantize_emit(self, delta_hires: float, hires_enabled: bool) -> tuple[int, int]:
        self._frac_emit += delta_hires
        eps = math.copysign(1e-6, self._frac_emit) if self._frac_emit != 0.0 else 0.0
        hi_int = int(math.trunc(self._frac_emit + eps))
        self._frac_emit -= hi_int
        if abs(self._frac_emit) < 1e-6:
            self._frac_emit = 0.0

        self._notch_accum += hi_int
        notches = int(math.trunc(self._notch_accum / HIRES_UNITS_PER_NOTCH))
        self._notch_accum -= notches * HIRES_UNITS_PER_NOTCH

        if not hires_enabled:
            return 0, notches
        return hi_int, notches

    def _run_loop(self) -> None:
        while self._running:
            self._wake.wait(timeout=0.25)
            self._wake.clear()
            last = time.monotonic()
            while self._running:
                now = time.monotonic()
                dt = max(0.001, min(0.05, now - last))
                last = now
                hi_emit, notch_emit = self.step(dt, now=now)
                if hi_emit != 0 or notch_emit != 0:
                    self._emit_fn(hi_emit, notch_emit)
                with self._lock:
                    done = self._pending_hires == 0.0
                if done:
                    break
                time.sleep(TICK_DT)
