"""Unit tests for the 144 Hz HD Smooth Scroll Engine, 0x2121 diversion decoding,
device.toml scroll tuning persistence, and executor shortcut fixes.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from mx4.agent.actions import ActionDispatcher
from mx4.agent.executor import parse_keyspec, resolve_evdev_keycode, wtype_argv
from mx4.agent.thumbwheel import THUMBWHEEL_PRESETS, ThumbWheelHandler
from mx4.config.schema import ButtonBinding, Config, DeviceConfig
from mx4.hidpp.device import MXMaster4
from mx4.hidpp.dispatcher import Notification
from mx4.hidpp.features import FeatureID
from mx4.sysd.apply import apply_persistent_settings
from mx4.sysd.button_router import ButtonRouter
from mx4.sysd.deviceconfig import DeviceConfigStore
from mx4.sysd.smooth_scroll import (
    HorizontalScrollEngine,
    ScrollTuning,
    SmoothScrollEngine,
    ThumbWheelTuning,
)
from fakes import FakeDispatcher


# ─── ScrollTuning ───

def test_scroll_tuning_bypass_detection():
    assert ScrollTuning(speed=1.0, smoothness=0, accel=0).needs_diversion is False
    assert ScrollTuning(speed=1.004, smoothness=0, accel=0).needs_diversion is False
    assert ScrollTuning(speed=1.25, smoothness=0, accel=0).needs_diversion is True
    assert ScrollTuning(speed=1.0, smoothness=25, accel=0).needs_diversion is True
    assert ScrollTuning(speed=1.0, smoothness=0, accel=15).needs_diversion is True


def test_scroll_tuning_clamping():
    t = ScrollTuning(speed=9.9, smoothness=180, accel=-20).clamped()
    assert t.speed == 4.0
    assert t.smoothness == 100
    assert t.accel == 0

    t2 = ScrollTuning(speed=0.05, smoothness=-5, accel=250).clamped()
    assert t2.speed == 0.20
    assert t2.smoothness == 0
    assert t2.accel == 100


# ─── SmoothScrollEngine ───

def test_smooth_scroll_instant_speed_scaling_and_invert():
    emitted: list[tuple[int, int]] = []
    eng = SmoothScrollEngine(hw_multiplier=8, emit_fn=lambda hi, lo: emitted.append((hi, lo)))
    try:
        # multiplier=8 -> 1 hardware hi-res unit == 15 REL_WHEEL_HI_RES units
        eng.configure(ScrollTuning(speed=2.0, smoothness=0, accel=0, invert=False))
        eng.feed(2, hi_res=True, now=1.0)  # 2 * 15 * 2.0 = +60 hi-res
        assert emitted == [(60, 0)]

        # Another +2 ticks reaches +120 hi-res -> emits 1 legacy REL_WHEEL notch too
        emitted.clear()
        eng.feed(2, hi_res=True, now=2.0)
        assert emitted == [(60, 1)]

        # Invert flips sign cleanly
        emitted.clear()
        eng.configure(ScrollTuning(speed=1.0, smoothness=0, accel=0, invert=True))
        eng.feed(1, hi_res=True, now=3.0)  # -15 hi-res
        assert emitted == [(-15, 0)]
    finally:
        eng.stop()


def test_smooth_scroll_144hz_interpolation_conserves_displacement():
    emitted: list[tuple[int, int]] = []
    eng = SmoothScrollEngine(hw_multiplier=8, emit_fn=lambda hi, lo: emitted.append((hi, lo)))
    try:
        eng.configure(ScrollTuning(speed=1.0, smoothness=60, accel=0, invert=False))
        # Inject 8 hardware hi-res ticks (= 120 Linux REL_WHEEL_HI_RES units = 1 full detent)
        eng.feed(8, hi_res=True)
        deadline = time.monotonic() + 0.75
        while time.monotonic() < deadline and sum(h for h, _ in emitted) < 120:
            time.sleep(0.01)
    finally:
        eng.stop()

    total_hi = sum(h for h, _ in emitted)
    total_lo = sum(lo for _, lo in emitted)
    # Must break the single impulse into multiple smooth sub-frames and conserve displacement
    assert len(emitted) >= 3
    assert total_hi == 120
    assert total_lo == 1


def test_smooth_scroll_direction_reversal_cancels_momentum():
    emitted: list[tuple[int, int]] = []
    eng = SmoothScrollEngine(hw_multiplier=8, emit_fn=lambda hi, lo: emitted.append((hi, lo)))
    # Set tuning directly without starting thread so we can inspect _pending_hires deterministically
    eng._tuning = ScrollTuning(speed=1.0, smoothness=85, accel=0, invert=False)
    eng.feed(10, hi_res=True, now=1.0)
    assert eng._pending_hires > 0
    eng.feed(-2, hi_res=True, now=1.01)
    # Pending tail must immediately be negative (zero overshoot from old direction)
    assert eng._pending_hires < 0
    assert eng._pending_hires == pytest.approx(-30.0)


def test_smooth_scroll_flick_acceleration_boosts_rapid_ticks():
    emitted_linear: list[tuple[int, int]] = []
    eng_lin = SmoothScrollEngine(hw_multiplier=8, emit_fn=lambda hi, lo: emitted_linear.append((hi, lo)))
    eng_lin._tuning = ScrollTuning(speed=1.0, smoothness=0, accel=0)

    emitted_accel: list[tuple[int, int]] = []
    eng_acc = SmoothScrollEngine(hw_multiplier=8, emit_fn=lambda hi, lo: emitted_accel.append((hi, lo)))
    eng_acc._tuning = ScrollTuning(speed=1.0, smoothness=0, accel=100)

    t = 10.0
    for _ in range(10):
        t += 0.008  # rapid 125 Hz flick!
        eng_lin.feed(4, hi_res=True, now=t)
        eng_acc.feed(4, hi_res=True, now=t)

    sum_lin = sum(h for h, _ in emitted_linear)
    sum_acc = sum(h for h, _ in emitted_accel)
    assert sum_lin == 10 * 4 * 15
    assert sum_acc > sum_lin * 1.35


# ─── ButtonRouter 0x2121 Hi-Res Wheel Notification Decoding ───

def test_button_router_decodes_0x2121_hires_wheel():
    wheels: list[tuple[int, bool]] = []
    router = ButtonRouter(lambda _cids: None, on_wheel=lambda d, h: wheels.append((d, h)))
    router._hires_index = 18

    # Hi-res flag set (bit 4 = 0x10), signed int16 +5 -> 0x00 0x05
    router._on_notification(Notification(
        device_index=2, feature_index=18, function_id=0x00,
        payload=bytes([0x10, 0x00, 0x05, 0x00]),
    ))
    # Hi-res flag clear (0x00), signed int16 -3 -> 0xFF 0xFD
    router._on_notification(Notification(
        device_index=2, feature_index=18, function_id=0x00,
        payload=bytes([0x00, 0xFF, 0xFD, 0x00]),
    ))
    assert wheels == [(5, True), (-3, False)]


# ─── device.toml Persistence for Scroll Tuning ───

def test_deviceconfig_roundtrips_scroll_tuning(tmp_path: Path):
    p = tmp_path / "device.toml"
    store = DeviceConfigStore(p)
    store.config.scroll_speed = 1.65
    store.config.scroll_smoothness = 70
    store.config.scroll_accel = 35
    store.save()

    loaded = DeviceConfigStore(p).load()
    assert loaded.scroll_speed == pytest.approx(1.65)
    assert loaded.scroll_smoothness == 70
    assert loaded.scroll_accel == 35


# ─── Executor Keyspec Fixes ───

def test_executor_standalone_super_and_lowercase_aliases():
    assert parse_keyspec("super") == ([], "Super_L")
    assert wtype_argv("super") == ["wtype", "-k", "Super_L"]
    assert parse_keyspec("ctrl+tab") == (["ctrl"], "Tab")
    assert parse_keyspec("alt+left") == (["alt"], "Left")
    assert parse_keyspec("esc") == ([], "Escape")
    assert parse_keyspec("enter") == ([], "Return")


# ─── 6x Hi-Res Horizontal Thumb Wheel Engine (0x2150) ───

def test_horizontal_engine_6x_resolution_scaling_and_invert():
    emitted: list[tuple[int, int]] = []
    eng = HorizontalScrollEngine(
        native_res=20,
        diverted_res=120,  # 6x hardware resolution -> 20 hi-res units per diverted tick
        emit_fn=lambda hi, lo: emitted.append((hi, lo)),
    )
    try:
        eng._tuning = ThumbWheelTuning(enabled=True, speed=1.0, smoothness=0, accel=0, invert=False)
        eng.feed(1, elapsed_ms=20, now=1.0)
        assert emitted == [(20, 0)]  # sub-detent 1/6th notch!

        emitted.clear()
        eng.feed(5, elapsed_ms=20, now=1.1)  # total 6 ticks = 120 hi-res = 1 legacy notch
        assert emitted == [(100, 1)]

        emitted.clear()
        eng._tuning = ThumbWheelTuning(enabled=True, speed=1.0, smoothness=0, accel=0, invert=True)
        eng.feed(2, elapsed_ms=20, now=1.2)
        assert emitted == [(-40, 0)]
    finally:
        eng.stop()


def test_horizontal_engine_144hz_smoothing_and_haptic_detents():
    emitted: list[tuple[int, int]] = []
    detents: list[int] = []
    eng = HorizontalScrollEngine(
        native_res=20,
        diverted_res=120,
        emit_fn=lambda hi, lo: emitted.append((hi, lo)),
        on_detent=lambda pat: detents.append(pat),
    )
    try:
        eng.configure(ThumbWheelTuning(
            enabled=True, speed=1.0, smoothness=55, accel=0, invert=False,
            haptic_detent=True, haptic_density=6, haptic_pattern=2,
        ))
        eng.feed(6, elapsed_ms=16)  # 1 full detent = 120 REL_HWHEEL_HI_RES units (6 micro-ticks)
        deadline = time.monotonic() + 0.75
        while time.monotonic() < deadline and sum(h for h, _ in emitted) < 120:
            time.sleep(0.01)
    finally:
        eng.stop()

    assert len(emitted) >= 3
    assert sum(h for h, _ in emitted) == 120
    assert sum(lo for _, lo in emitted) == 1
    # 6x micro density fires multiple tactile micro-ticks across a 120u glide with chosen pattern
    assert len(detents) >= 2
    assert all(p == 2 for p in detents)


def test_horizontal_engine_hardware_timestamp_flick_acceleration():
    emitted_lin: list[tuple[int, int]] = []
    eng_lin = HorizontalScrollEngine(emit_fn=lambda hi, lo: emitted_lin.append((hi, lo)))
    eng_lin._tuning = ThumbWheelTuning(enabled=True, speed=1.0, smoothness=0, accel=0)

    emitted_acc: list[tuple[int, int]] = []
    eng_acc = HorizontalScrollEngine(emit_fn=lambda hi, lo: emitted_acc.append((hi, lo)))
    eng_acc._tuning = ThumbWheelTuning(enabled=True, speed=1.0, smoothness=0, accel=100)

    for _ in range(8):
        eng_lin.feed(3, elapsed_ms=10)
        eng_acc.feed(3, elapsed_ms=10)

    sum_lin = sum(h for h, _ in emitted_lin)
    sum_acc = sum(h for h, _ in emitted_acc)
    assert sum_lin == 8 * 3 * 20
    assert sum_acc > sum_lin * 1.4


def test_button_router_decodes_0x2150_full_packet():
    packets: list[tuple[int, int, int, int]] = []
    router = ButtonRouter(
        lambda _c: None,
        on_thumbwheel_packet=lambda d, ms, st, fl: packets.append((d, ms, st, fl)),
    )
    router._thumb_index = 19
    # delta = +4 (0x0004), elapsed = 12 ms (0x000C), status = 2 (active), flags = 0x04 (touch)
    router._on_notification(Notification(2, 19, 0x00, bytes([0x00, 0x04, 0x00, 0x0C, 0x02, 0x04])))
    assert packets == [(4, 12, 2, 4)]


def test_deviceconfig_roundtrips_thumbwheel_hd_and_migrates_legacy(tmp_path: Path):
    p = tmp_path / "device.toml"
    store = DeviceConfigStore(p)
    store.config.thumbwheel_mode = "hd_scroll"
    store.config.thumbwheel_invert = True
    store.config.thumbwheel_speed = 1.45
    store.config.thumbwheel_smoothness = 60
    store.config.thumbwheel_accel = 40
    store.config.thumbwheel_hires = True
    store.config.thumbwheel_haptic_detent = True
    store.config.thumbwheel_haptic_density = 6
    store.config.thumbwheel_haptic_pattern = 4
    store.save()

    loaded = DeviceConfigStore(p).load()
    assert loaded.thumbwheel_mode == "hd_scroll"
    assert loaded.thumbwheel_diverted is False
    assert loaded.thumbwheel_invert is True
    assert loaded.thumbwheel_speed == pytest.approx(1.45)
    assert loaded.thumbwheel_smoothness == 60
    assert loaded.thumbwheel_accel == 40
    assert loaded.thumbwheel_haptic_detent is True
    assert loaded.thumbwheel_haptic_density == 6
    assert loaded.thumbwheel_haptic_pattern == 4

    # Legacy config with only thumbwheel_diverted = true migrates to actions mode
    legacy_path = tmp_path / "legacy.toml"
    legacy_path.write_text("version = 2\nthumbwheel_diverted = true\nthumbwheel_invert = true\n")
    legacy = DeviceConfigStore(legacy_path).load()
    assert legacy.thumbwheel_mode == "actions"
    assert legacy.thumbwheel_diverted is True


def test_apply_hd_scroll_diverts_thumbwheel_without_double_invert():
    cache = {
        int(FeatureID.SMART_SHIFT_ENHANCED): 17,
        int(FeatureID.ADJUSTABLE_DPI): 20,
        int(FeatureID.HIRES_WHEEL): 18,
        int(FeatureID.THUMBWHEEL): 19,
        int(FeatureID.REPROG_CONTROLS_V4): 13,
        int(FeatureID.HAPTIC): 11,
    }
    resp = {f"0x{int(f):04x}.{fn:02x}(*)": "00" for f, fn in [
        (FeatureID.SMART_SHIFT_ENHANCED, 2), (FeatureID.ADJUSTABLE_DPI, 3),
        (FeatureID.HIRES_WHEEL, 2), (FeatureID.THUMBWHEEL, 2),
        (FeatureID.REPROG_CONTROLS_V4, 3), (FeatureID.HAPTIC, 2),
    ]}
    fake = FakeDispatcher(cache, resp)
    cfg = DeviceConfig(thumbwheel_mode="hd_scroll", thumbwheel_invert=True)
    apply_persistent_settings(MXMaster4(fake), cfg, divert_thumbwheel_hd=True)
    tw_calls = [c for c in fake.calls if c[0] == int(FeatureID.THUMBWHEEL)]
    # Hardware diverted=1, hw_invert=0 so HorizontalScrollEngine applies invert once
    assert tw_calls == [(int(FeatureID.THUMBWHEEL), 0x02, (0x01, 0x00))]


def test_thumbwheel_handler_skips_hd_scroll_and_resets_after_idle():
    cfg = Config()
    cfg.thumbwheel.mode = "hd_scroll"
    cfg.thumbwheel.step = 20
    fired = []
    handler = ThumbWheelHandler(lambda: cfg, lambda at, ad: (fired.append((at, ad)) or True))
    assert handler.feed(50, now=1.0) == 0

    cfg.thumbwheel.mode = "actions"
    assert handler.feed(15, now=2.0) == 0
    # After >0.48s idle, stale 15 ticks clear so +10 does not fire unexpectedly
    assert handler.feed(10, now=3.0) == 0
    assert handler.feed(10, now=3.05) == 1
    assert {"timeline", "brush", "brightness", "scroll_v", "volume_fine"}.issubset(THUMBWHEEL_PRESETS.keys())


def test_thumbwheel_handler_micro_crown_haptics_between_action_steps():
    cfg = Config()
    cfg.haptics.enabled = True
    cfg.thumbwheel.mode = "actions"
    cfg.thumbwheel.step = 16
    cfg.thumbwheel.haptic_tick = True
    cfg.thumbwheel.micro_haptics = True
    cfg.thumbwheel.haptic_pattern = 2

    haptics: list[int] = []
    handler = ThumbWheelHandler(
        lambda: cfg,
        lambda _at, _ad: True,
        haptic_fn=lambda pat: (haptics.append(pat) or True),
    )
    # Slow roll: 3 ticks -> subtle micro-tick (pattern 4); 3 more -> micro-tick (4); +10 -> fires action (pattern 2)
    assert handler.feed(3, now=1.00) == 0
    assert handler.feed(3, now=1.05) == 0
    assert handler.feed(10, now=1.10) == 1
    assert haptics == [4, 4, 2]


def test_key_hold_ptt_press_release_and_disconnect_safety():
    assert resolve_evdev_keycode("PageDown") == 109
    assert resolve_evdev_keycode("Page_Down") == 109
    assert resolve_evdev_keycode("PageUp") == 104
    assert resolve_evdev_keycode("KEY_PAGEUP") == 104
    assert resolve_evdev_keycode("109") == 109

    events: list[tuple[int, bool]] = []
    bindings = [
        ButtonBinding(cid=0x0056, action_type="key_hold", action_data="PageDown"),
        ButtonBinding(cid=0x0053, action_type="key_hold", action_data="PageUp"),
    ]
    disp = ActionDispatcher(
        bindings_provider=lambda: bindings,
        hold_key_fn=lambda code, down: (events.append((code, down)) or True),
    )
    assert disp.action_bound_cids() == {0x0056, 0x0053}

    disp.feed_diverted({0x0056})
    time.sleep(0.03)
    disp.feed_diverted(set())
    time.sleep(0.03)
    disp.feed_diverted({0x0053})
    time.sleep(0.03)
    # Disconnect while Back button is held must release PageUp (104) cleanly
    disp.release_all()

    assert events == [(109, True), (109, False), (104, True), (104, False)]
