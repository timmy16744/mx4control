"""Tests for the system daemon's pure logic (no bus, no hardware, no root)."""

from __future__ import annotations

from mx4.config.schema import ButtonDefault, DeviceConfig
from mx4.hidpp.device import MXMaster4
from mx4.hidpp.dispatcher import Notification
from mx4.hidpp.features import FeatureID
from mx4.sysd.apply import apply_persistent_settings
from mx4.sysd.button_router import ButtonRouter
from mx4.sysd.deviceconfig import DeviceConfigStore
from mx4.sysd.state import build_state
from fakes import FakeDispatcher


# ─── device config store ───

def test_deviceconfig_roundtrip(tmp_path):
    store = DeviceConfigStore(tmp_path / "device.toml")
    store.config.dpi = 1600
    store.config.smartshift_enabled = False
    store.config.buttons = [ButtonDefault(cid=0x53, mode="remap", target=0x56)]
    assert store.save()

    fresh = DeviceConfigStore(tmp_path / "device.toml").load()
    assert fresh.dpi == 1600
    assert fresh.smartshift_enabled is False
    assert fresh.buttons == [ButtonDefault(cid=0x53, mode="remap", target=0x56)]


def test_deviceconfig_validates_and_clamps(tmp_path):
    p = tmp_path / "device.toml"
    p.write_text(
        "version = 2\ndpi = 99999\nsmartshift_threshold = 999\n"
        '[[buttons]]\ncid = 82\nmode = "bogus"\ntarget = 0\n'
    )
    cfg = DeviceConfigStore(p).load()
    assert cfg.dpi == 8000               # clamped
    assert cfg.smartshift_threshold == 255
    assert cfg.buttons == []             # invalid mode dropped


def test_deviceconfig_default_smartshift_off():
    # Fresh config (no file) must default SmartShift OFF — the buzz fix.
    assert DeviceConfig().smartshift_enabled is False


# ─── apply ───

def _apply_fake():
    cache = {int(FeatureID.SMART_SHIFT_ENHANCED): 17, int(FeatureID.ADJUSTABLE_DPI): 20,
             int(FeatureID.HIRES_WHEEL): 18, int(FeatureID.THUMBWHEEL): 19,
             int(FeatureID.REPROG_CONTROLS_V4): 13, int(FeatureID.HAPTIC): 11}
    resp = {f"0x{int(f):04x}.{fn:02x}(*)": "00" for f, fn in [
        (FeatureID.SMART_SHIFT_ENHANCED, 2), (FeatureID.ADJUSTABLE_DPI, 3),
        (FeatureID.HIRES_WHEEL, 2), (FeatureID.THUMBWHEEL, 2),
        (FeatureID.REPROG_CONTROLS_V4, 3), (FeatureID.HAPTIC, 2)]}
    return FakeDispatcher(cache, resp)


def test_apply_disables_smartshift_to_kill_buzz():
    fake = _apply_fake()
    cfg = DeviceConfig(smartshift_enabled=False, smartshift_threshold=15)
    res = apply_persistent_settings(MXMaster4(fake), cfg)
    assert res["smartshift"] is True
    ss = [c for c in fake.calls if c[0] == int(FeatureID.SMART_SHIFT_ENHANCED)]
    # WheelMode.RATCHET (0x02), auto_disengage=0xFF (SmartShift off), persisted torque (75%)
    assert ss == [(int(FeatureID.SMART_SHIFT_ENHANCED), 2, (0x02, 0xFF, 75))]


def test_apply_disables_haptic_to_kill_gesture_pad_buzz():
    fake = _apply_fake()
    cfg = DeviceConfig(haptic_enabled=False)
    res = apply_persistent_settings(MXMaster4(fake), cfg)
    assert res["haptic"] is True
    hap = [c for c in fake.calls if c[0] == int(FeatureID.HAPTIC)]
    assert hap[-1][1] == 0x02            # write = function INDEX 2 (byte 0x20)
    assert hap[-1][2][0] == 0x00         # enable byte 0 = haptic off


def test_apply_remaps_persistent_buttons():
    fake = _apply_fake()
    cfg = DeviceConfig(buttons=[ButtonDefault(cid=0x53, mode="remap", target=0x56)])
    apply_persistent_settings(MXMaster4(fake), cfg)
    remap = [c for c in fake.calls
             if c[0] == int(FeatureID.REPROG_CONTROLS_V4) and c[1] == 0x03]
    assert remap and remap[0][2][:2] == (0x00, 0x53)   # cid hi/lo


# ─── button router ───

def test_button_router_parses_diverted_cids():
    seen = []
    router = ButtonRouter(seen.append)
    router._reprog_index = 13
    note = Notification(device_index=2, feature_index=13, function_id=0x00,
                        payload=bytes([0x00, 0x52, 0x00, 0x53, 0, 0, 0, 0]))
    router._on_notification(note)
    assert seen == [[0x52, 0x53]]


def test_button_router_ignores_other_features():
    seen = []
    router = ButtonRouter(seen.append)
    router._reprog_index = 13
    router._on_notification(Notification(2, 99, 0x00, bytes([0x00, 0x52])))
    assert seen == []


# ─── state ───

def test_build_state_disconnected():
    assert build_state(None, None) == {"connected": False}
