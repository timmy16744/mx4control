"""Comprehensive tests for MX4Control 1.0 hardware protocol & agent features."""

from __future__ import annotations

from mx4.agent.executor import execute
from mx4.agent.thumbwheel import ThumbWheelHandler
from mx4.config.schema import Config, DeviceConfig
from mx4.hidpp.device import MXMaster4
from mx4.hidpp.dispatcher import Notification
from mx4.hidpp.features import FeatureID, HiresFlag, WheelMode
from mx4.sysd.apply import apply_persistent_settings
from mx4.sysd.button_router import ButtonRouter
from mx4.sysd.deviceconfig import DeviceConfigStore
from fakes import FakeDispatcher


# ─── HAPTIC (0x19B0) ───

def test_trigger_haptic_uses_enumerated_feature_0x19b0():
    fake = FakeDispatcher({int(FeatureID.HAPTIC): 11}, {"0x19b0.04(*)": "00"})
    dev = MXMaster4(fake)
    assert dev.trigger_haptic(2) is True
    assert fake.calls[-1] == (int(FeatureID.HAPTIC), 0x04, (2,))
    assert fake.writes == []  # did NOT use legacy hardcoded 0x0B 0x4E


def test_haptic_capabilities_and_level_roundtrip():
    fake = FakeDispatcher(
        {int(FeatureID.HAPTIC): 11},
        {
            "0x19b0.00()": "00 01 00 3c 00 00 7f ff",
            "0x19b0.01()": "01 4b 00",
            "0x19b0.02(*)": "00",
        },
    )
    dev = MXMaster4(fake)
    caps = dev.get_haptic_capabilities()
    assert caps.supported is True
    assert caps.discrete_levels is False
    assert caps.waveforms == tuple(range(15))

    enabled, level = dev.get_haptic()
    assert enabled is True
    assert level == 75

    assert dev.set_haptic(True, 80) is True
    assert fake.calls[-1] == (int(FeatureID.HAPTIC), 0x02, (0x01, 80))


# ─── FORCE_SENSING_BUTTON (0x19C0) ───

def test_force_sensing_button_decode_and_set():
    # Live capture from MX Master 4 FW 39.0.0015
    fake = FakeDispatcher(
        {int(FeatureID.FORCE_SENSING_BUTTON): 12},
        {
            "0x19c0.00()": "01 00",
            "0x19c0.01(00)": "00 01 14 4b 1a fd 10 3c",
            "0x19c0.02(00)": "14 4b",
            "0x19c0.03(*)": "00",
        },
    )
    dev = MXMaster4(fake)
    fb = dev.get_force_button(0)
    assert fb is not None
    assert fb.changeable is True
    assert fb.default_force == 5195
    assert fb.min_force == 4156
    assert fb.max_force == 6909
    assert fb.current_force == 5195
    assert 35 <= fb.percent <= 40

    # Clamping + big-endian encoding
    assert dev.set_force_button(99999, 0) is True
    assert fake.calls[-1] == (
        int(FeatureID.FORCE_SENSING_BUTTON), 0x03, (0, 0x1A, 0xFD),
    )


# ─── SMART_SHIFT_ENHANCED (0x2111) — modes + tunable torque ───

def test_smartshift_free_spin_and_torque():
    fake = FakeDispatcher(
        {int(FeatureID.SMART_SHIFT_ENHANCED): 17},
        {
            "0x2111.00()": "01 0a 4b 0e",
            "0x2111.01()": "01 ff 32",
            "0x2111.02(*)": "00",
        },
    )
    dev = MXMaster4(fake)
    st = dev.get_smartshift_state()
    assert st.tunable_torque is True
    assert st.mode_name == "free"
    assert st.tuned_torque == 50

    assert dev.set_scroll_mode("free", 15, torque=60) is True
    assert fake.calls[-1] == (
        int(FeatureID.SMART_SHIFT_ENHANCED), 0x02, (WheelMode.FREESPIN, 0xFF, 60),
    )

    assert dev.set_scroll_mode("smart", 22, torque=85) is True
    assert fake.calls[-1] == (
        int(FeatureID.SMART_SHIFT_ENHANCED), 0x02, (WheelMode.RATCHET, 22, 85),
    )


# ─── HIRES_WHEEL (0x2121) — fn 0x02 + bitmask ───

def test_hires_wheel_reads_fn1_writes_fn2_with_spec_bits():
    fake = FakeDispatcher(
        {int(FeatureID.HIRES_WHEEL): 18},
        {
            "0x2121.01()": "06",  # HIRES (0x02) | INVERT (0x04)
            "0x2121.02(*)": "00",
        },
    )
    dev = MXMaster4(fake)
    assert dev.get_hires_scroll() == (True, True, False)

    assert dev.set_hires_scroll(True, invert=False) is True
    assert fake.calls[-1] == (int(FeatureID.HIRES_WHEEL), 0x02, (int(HiresFlag.HIRES),))

    assert dev.set_hires_scroll(True, invert=True) is True
    assert fake.calls[-1] == (
        int(FeatureID.HIRES_WHEEL), 0x02, (int(HiresFlag.HIRES | HiresFlag.INVERT),),
    )


# ─── THUMBWHEEL (0x2150) — two separate bytes ───

def test_thumbwheel_uses_two_separate_bytes():
    fake = FakeDispatcher(
        {int(FeatureID.THUMBWHEEL): 19},
        {
            "0x2150.01()": "01 01",
            "0x2150.02(*)": "00",
        },
    )
    dev = MXMaster4(fake)
    assert dev.get_thumbwheel_status() == (True, True)

    assert dev.set_thumbwheel_diverted(False, invert=True) is True
    assert fake.calls[-1] == (int(FeatureID.THUMBWHEEL), 0x02, (0x00, 0x01))

    assert dev.set_thumbwheel_diverted(True, invert=True) is True
    assert fake.calls[-1] == (int(FeatureID.THUMBWHEEL), 0x02, (0x01, 0x01))


# ─── ADJUSTABLE_DPI (0x2201) — range decoding ───

def test_dpi_range_and_list_decode():
    # Live capture: 00 00 c8 e0 32 1f 40 00 -> min=200, step=50, max=8000
    fake = FakeDispatcher(
        {int(FeatureID.ADJUSTABLE_DPI): 20},
        {"0x2201.01(00)": "00 00 c8 e0 32 1f 40 00 00"},
    )
    dev = MXMaster4(fake)
    assert dev.get_dpi_range() == (200, 8000, 50)
    vals = dev.get_dpi_list()
    assert vals[0] == 200 and vals[-1] == 8000 and vals[1] == 250


# ─── HOSTS_INFO (0x1815) — fn 0x03 host names & fn 0x04 rename ───

def test_hosts_friendly_names_via_fn3_and_rename_via_fn4():
    fake = FakeDispatcher(
        {int(FeatureID.HOSTS_INFO): 15, int(FeatureID.CHANGE_HOST): 14},
        {
            "0x1815.00()": "13 08 03 00",
            "0x1814.00()": "03 00",
            "0x1815.01(00)": "00 01 05 01 08 18",
            "0x1815.01(01)": "01 01 04 01 0a 18",
            "0x1815.01(02)": "02 00 00 00 00 18",
            "0x1815.03(00, 00)": "00 00 44 75 63 6b 73 74 6f 70 00",
            "0x1815.03(01, 00)": "01 00 54 49 4d 5f 4c 41 50 54 4f 50 00",
            "0x1815.04(*)": "00",
        },
    )
    dev = MXMaster4(fake)
    hosts = dev.get_hosts()
    assert hosts is not None
    assert hosts.current_host == 0
    assert hosts.can_set_name is True
    assert hosts.hosts[0].name == "Duckstop"
    assert hosts.hosts[0].bus_label == "Logi Bolt"
    assert hosts.hosts[1].name == "TIM_LAPTOP"
    assert hosts.hosts[1].bus_label == "Bluetooth LE"
    assert hosts.hosts[2].paired is False

    assert dev.set_host_name(0, "Workstation") is True
    assert any(c[0] == int(FeatureID.HOSTS_INFO) and c[1] == 0x04 for c in fake.calls)


# ─── Button reset ───

def test_reset_button_undiverts_and_remaps_to_self():
    fake = FakeDispatcher({int(FeatureID.REPROG_CONTROLS_V4): 13}, {"0x1b04.03(*)": "00"})
    dev = MXMaster4(fake)
    assert dev.reset_button(0x0053) is True
    feat, fn, args = fake.calls[-1]
    assert feat == int(FeatureID.REPROG_CONTROLS_V4)
    assert fn == 0x03
    assert args[0:2] == (0x00, 0x53)
    assert args[3:5] == (0x00, 0x53)


# ─── ButtonRouter (thumbwheel + wireless reconnect + battery) ───

def test_router_handles_thumbwheel_reconnect_and_battery():
    tw_events = []
    reconnects = []
    batteries = []
    router = ButtonRouter(
        on_diverted=lambda _c: None,
        on_thumbwheel=lambda d, dir_: tw_events.append((d, dir_)),
        on_reconnect=lambda: reconnects.append(True),
        on_battery=lambda p, c, s, b: batteries.append((p, c, s, b)),
    )
    router._thumb_index = 19
    router._wireless_index = 4
    router._battery_index = 9

    # Signed negative thumbwheel delta (-10 = 0xFFF6)
    router._on_notification(Notification(2, 19, 0x00, bytes([0xFF, 0xF6, 0, 0, 0])))
    assert tw_events == [(-10, -1)]

    # Wireless reconnect (0x1D4B)
    router._on_notification(Notification(2, 4, 0x00, bytes([0x01, 0x01, 0x00])))
    assert reconnects == [True]

    # Battery update (0x1004): 80%, good (4), charging (1)
    router._on_notification(Notification(2, 9, 0x00, bytes([80, 4, 1, 0])))
    assert batteries == [(80, True, 1, 4)]


# ─── ThumbWheelHandler & Hardware Actions ───

def test_thumbwheel_handler_accumulates_and_fires():
    cfg = Config()
    cfg.thumbwheel.step = 30
    cfg.thumbwheel.positive_type = "keystroke"
    cfg.thumbwheel.positive_data = "ctrl+Tab"
    cfg.thumbwheel.negative_type = "keystroke"
    cfg.thumbwheel.negative_data = "ctrl+shift+Tab"

    fired = []
    handler = ThumbWheelHandler(
        config_provider=lambda: cfg,
        execute_fn=lambda at, ad: (fired.append((at, ad)) or True),
    )
    assert handler.feed(15) == 0
    assert handler.feed(20) == 1  # 35 >= 30
    # Reversing resets remainder
    assert handler.feed(-30) == 1


def test_executor_routes_hardware_actions():
    seen = []
    ok = execute("dpi_cycle", "", hardware_handler=lambda at, ad: (seen.append((at, ad)) or True))
    assert ok is True
    assert seen == [("dpi_cycle", "")]


# ─── DeviceConfig v1.0 fields roundtrip ───

def test_deviceconfig_v1_fields_roundtrip(tmp_path):
    store = DeviceConfigStore(tmp_path / "device.toml")
    store.config.wheel_mode = "free"
    store.config.ratchet_torque = 60
    store.config.haptic_enabled = True
    store.config.haptic_level = 85
    store.config.force_threshold = 4800
    assert store.save()

    loaded = DeviceConfigStore(tmp_path / "device.toml").load()
    assert loaded.wheel_mode == "free"
    assert loaded.ratchet_torque == 60
    assert loaded.haptic_enabled is True
    assert loaded.haptic_level == 85
    assert loaded.force_threshold == 4800


def test_apply_writes_force_and_free_spin():
    cache = {
        int(FeatureID.SMART_SHIFT_ENHANCED): 17,
        int(FeatureID.ADJUSTABLE_DPI): 20,
        int(FeatureID.HIRES_WHEEL): 18,
        int(FeatureID.THUMBWHEEL): 19,
        int(FeatureID.HAPTIC): 11,
        int(FeatureID.FORCE_SENSING_BUTTON): 12,
    }
    resp = {
        "0x2111.02(*)": "00",
        "0x2201.03(*)": "00",
        "0x2121.02(*)": "00",
        "0x2150.02(*)": "00",
        "0x19b0.02(*)": "00",
        "0x19c0.01(00)": "00 01 14 4b 1a fd 10 3c",
        "0x19c0.02(00)": "14 4b",
        "0x19c0.03(*)": "00",
    }
    fake = FakeDispatcher(cache, resp)
    cfg = DeviceConfig(
        wheel_mode="free", ratchet_torque=65,
        haptic_enabled=True, haptic_level=80, force_threshold=4900,
    )
    res = apply_persistent_settings(MXMaster4(fake), cfg)
    assert res["smartshift"] is True
    assert res["hires"] is True
    assert res["haptic"] is True
    assert res["force"] is True
