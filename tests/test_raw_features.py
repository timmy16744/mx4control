"""Tests for the Phase-5 raw / reverse-engineered feature accessors.

Driven by the captured live fixture
``tests/fixtures/mx4_master4_4.5.0000.json`` replayed through
``FakeDispatcher``. Decoders whose feature is auth-locked on the live
device (fn 0x00 → error 0x05) are exercised against synthetic payloads
that match the byte layout documented in ``raw.py``, so the parsing math
itself is still pinned.
"""

from __future__ import annotations

import pytest

from fakes import FakeDispatcher, hexbytes
from mx4.hidpp.features import HIDPPError
from mx4.hidpp import raw
from mx4.hidpp.raw import (
    FEATURE_NAMES,
    raw_call,
    feature_label,
    feature_description,
    decode_battery_voltage,
    estimate_voltage_percent,
    read_battery_voltage,
    decode_unified_battery,
    read_unified_battery,
    decode_wireless_status,
    read_unique_id,
    decode_device_properties,
    read_device_properties,
    decode_xy_stats,
    read_xy_stats,
    decode_wheel_stats,
    read_wheel_stats,
    decode_temperature_info,
    read_temperature_info,
    decode_force_sensing,
    read_force_sensing,
    probe_all,
)


# ─────────────────────────── fixtures ───────────────────────────


@pytest.fixture
def fake(live_fixture) -> FakeDispatcher:
    cache = {int(k, 16): v for k, v in live_fixture["device"]["feature_cache"].items()}
    return FakeDispatcher(cache, live_fixture["responses"])


@pytest.fixture
def fixture_cache(live_fixture) -> dict[int, int]:
    return {int(k, 16): v for k, v in live_fixture["device"]["feature_cache"].items()}


# ─────────────────────────── FEATURE_NAMES registry ───────────────────────


def test_feature_names_covers_every_enumerated_feature(fixture_cache):
    """The GUI explorer must be able to label every feature the device has."""
    missing = [f"0x{f:04x}" for f in fixture_cache if f not in FEATURE_NAMES]
    assert missing == [], f"unlabelled features: {missing}"


def test_feature_names_entries_are_name_and_description():
    for fid, entry in FEATURE_NAMES.items():
        assert isinstance(entry, tuple) and len(entry) == 2
        name, desc = entry
        assert name and name.isascii()
        assert desc and len(desc) > 5


def test_feature_label_known_and_unknown():
    assert feature_label(0x1861) == "BATTERY_VOLTAGE"
    assert feature_label(0x1004) == "UNIFIED_BATTERY"
    assert feature_label(0xABCD) == "UNKNOWN_0xabcd"
    assert "battery" in feature_description(0x1004).lower()
    assert feature_description(0xABCD) == "Unrecognised HID++ 2.0 feature"


# ─────────────────────────── raw_call ─────────────────────────────────────


def test_raw_call_returns_payload_for_present_feature(fake):
    # 0x1815 HOSTS_INFO fn 0x00 → "13 08 03 ..." in the fixture
    r = raw_call(fake, 0x1815, 0x00, [])
    assert r is not None
    assert r[0] == 0x13 and r[2] == 0x03


def test_raw_call_missing_feature_returns_none(fake):
    assert raw_call(fake, 0x9999, 0x00, []) is None


def test_raw_call_does_not_swallow_device_error(fake):
    # 0x9401.00 → ERR 0x05 in the fixture; raw_call must surface it
    with pytest.raises(HIDPPError):
        raw_call(fake, 0x9401, 0x00, [])


def test_raw_call_promotes_to_long_for_many_args(fake):
    raw_call(fake, 0x1815, 0x05, [1, 2, 3, 4, 5])
    feat, fn, args = fake.calls[-1]
    assert feat == 0x1815 and fn == 0x05
    assert args == (1, 2, 3, 4, 5)


# ─────────────────────────── battery voltage (0x1861) ─────────────────────


def test_battery_voltage_decode_discharging():
    # 4.05 V, no flags → discharging, ~89%
    bv = decode_battery_voltage(hexbytes("0f d2 00"))
    assert bv is not None
    assert bv.millivolts == 0x0FD2 == 4050
    assert bv.charging is False
    assert 3000 <= bv.millivolts <= 4300
    assert 0 <= bv.percent <= 100
    assert 80 <= bv.percent <= 95


def test_battery_voltage_decode_charging_flags():
    # 3.80 V, bit7 (charging) + bit3 (fast) set, status nibble = 1
    flags = (1 << 7) | (1 << 3) | 0x01
    bv = decode_battery_voltage(bytes([0x0E, 0xD8, flags]))
    assert bv.millivolts == 0x0ED8 == 3800
    assert bv.charging is True
    assert bv.fast_charge is True
    assert bv.slow_charge is False
    assert bv.charge_status == 1


def test_battery_voltage_decode_too_short():
    assert decode_battery_voltage(b"\x0f") is None
    assert decode_battery_voltage(b"") is None


def test_estimate_voltage_percent_monotonic_and_clamped():
    assert estimate_voltage_percent(4300) == 100   # above table top
    assert estimate_voltage_percent(3400) == 0      # below table bottom
    # midpoints interpolate within range
    p_hi = estimate_voltage_percent(4067)
    p_lo = estimate_voltage_percent(3671)
    assert p_hi == 90 and p_lo == 10
    # monotonic non-decreasing with voltage
    last = -1
    for mv in range(3400, 4300, 25):
        p = estimate_voltage_percent(mv)
        assert p >= last
        last = p


def test_read_battery_voltage_locked_on_live_device(fake):
    # Fixture: 0x1861.00 → ERR 0x05, decoder must swallow → None
    assert read_battery_voltage(fake) is None


def test_read_battery_voltage_with_synthetic_response(fixture_cache):
    fake = FakeDispatcher(fixture_cache, {"0x1861.00()": "0f d2 00"})
    bv = read_battery_voltage(fake)
    assert bv is not None and bv.millivolts == 4050


def test_read_battery_voltage_absent_feature():
    assert read_battery_voltage(FakeDispatcher({}, {})) is None


# ─────────────────────────── unified battery (0x1004) ─────────────────────


def test_unified_battery_decode():
    # 75%, level bucket "good" (4), status charging (1)
    ub = decode_unified_battery(bytes([75, 4, 1, 0]))
    assert ub.percent == 75
    assert ub.level_bucket == 4
    assert ub.level_name == "good"
    assert ub.status == 1 and ub.charging is True


def test_unified_battery_level_names():
    assert decode_unified_battery(bytes([0, 8, 0])).level_name == "full"
    assert decode_unified_battery(bytes([0, 2, 0])).level_name == "low"
    assert decode_unified_battery(bytes([0, 1, 0])).level_name == "critical"
    assert decode_unified_battery(bytes([0, 0, 0])).level_name == "empty"


def test_read_unified_battery_present(fixture_cache):
    fake = FakeDispatcher(fixture_cache, {"0x1004.01()": "5a 04 00 00"})
    ub = read_unified_battery(fake)
    assert ub is not None and ub.percent == 0x5A == 90


def test_read_unified_battery_absent():
    assert read_unified_battery(FakeDispatcher({}, {})) is None


# ─────────────────────────── wireless status (0x1D4B) ─────────────────────


def test_wireless_status_decode_reconnect():
    ws = decode_wireless_status(bytes([0x01, 0x01, 0x01]))
    assert ws.reconnection is True
    assert ws.reconf_needed is True
    assert ws.powered_on is True
    assert ws.raw == b"\x01\x01\x01"


def test_wireless_status_decode_idle():
    ws = decode_wireless_status(bytes([0x00, 0x00, 0x00]))
    assert ws.reconnection is False
    assert ws.reconf_needed is False
    assert ws.powered_on is False


def test_wireless_status_decode_empty():
    assert decode_wireless_status(b"") is None


def test_wireless_status_present_in_fixture(fixture_cache):
    # 0x1D4B is enumerated on the live device (index 4)
    assert 0x1D4B in fixture_cache


# ─────────────────────────── unique id (0x0021) ───────────────────────────


def test_read_unique_id_single_chunk(fixture_cache):
    fake = FakeDispatcher(
        fixture_cache,
        {"0x0021.00()": "de ad be ef 00 00 00 00 00 00 00 00 00 00 00 00"},
    )
    uid = read_unique_id(fake)
    assert uid is not None
    assert uid.raw == bytes.fromhex("deadbeef")
    assert uid.hex == "deadbeef"


def test_read_unique_id_two_chunks_assemble_32_bytes(fixture_cache):
    first = " ".join(["aa"] * 16)
    second = " ".join(["bb"] * 16)
    fake = FakeDispatcher(
        fixture_cache,
        {"0x0021.00()": first, "0x0021.01()": second},
    )
    uid = read_unique_id(fake)
    assert uid is not None
    assert len(uid.raw) == 32
    assert uid.raw[:16] == b"\xaa" * 16
    assert uid.raw[16:] == b"\xbb" * 16


def test_read_unique_id_absent():
    assert read_unique_id(FakeDispatcher({}, {})) is None


# ─────────────────────────── device properties (0x1807) ───────────────────


def test_device_properties_decode():
    dp = decode_device_properties(bytes([0x03, 0x01, 0x4D, 0x58, 0x00, 0x00]))
    assert dp.property_id == 0x03
    assert dp.flags == 0x01
    assert dp.data == b"MX"  # trailing NULs trimmed


def test_read_device_properties_locked_on_live_device(fake):
    # Fixture: 0x1807.00 → ERR 0x05 → None
    assert read_device_properties(fake) is None


def test_read_device_properties_with_synthetic(fixture_cache):
    fake = FakeDispatcher(fixture_cache, {"0x1807.00(00)": "00 00 53 4b 55 00"})
    dp = read_device_properties(fake)
    assert dp is not None and dp.data == b"SKU"


# ─────────────────────────── XY stats (0x2250) ────────────────────────────


def test_xy_stats_decode_from_fixture_bytes():
    # Live: 0x2250.00() = 00 01 00 00 ...
    xy = decode_xy_stats(hexbytes("00 01 00 00"))
    assert xy is not None
    assert xy.capabilities == 0x00
    assert xy.num_counters == 1


def test_read_xy_stats_from_fixture(fake):
    xy = read_xy_stats(fake)
    assert xy is not None
    assert xy.num_counters == 1
    assert xy.raw == b"\x00\x01\x00\x00"


# ─────────────────────────── wheel stats (0x2251) ─────────────────────────


def test_wheel_stats_decode_from_fixture_bytes():
    # Live: 0x2251.00() = 0f 01 68 00 78 00 ...
    ws = decode_wheel_stats(hexbytes("0f 01 68 00 78 00"))
    assert ws is not None
    assert ws.capabilities == 0x0F
    assert ws.num_counters == 1
    assert ws.field_a == 0x6800   # big-endian of bytes 2..3
    assert ws.field_b == 0x7800


def test_read_wheel_stats_from_fixture(fake):
    ws = read_wheel_stats(fake)
    assert ws is not None
    assert ws.capabilities == 0x0F
    assert ws.num_counters == 1


def test_wheel_stats_decode_too_short():
    assert decode_wheel_stats(b"\x0f\x01") is None


# ─────────────────────────── temperature (0x1701) ─────────────────────────


def test_temperature_decode_from_fixture_bytes():
    # Live: 0x1701.00() = 01 00 0a 00 ...
    t = decode_temperature_info(hexbytes("01 00 0a 00"))
    assert t is not None
    assert t.num_sensors == 1
    assert t.raw == b"\x01\x00\x0a\x00"


def test_read_temperature_from_fixture(fake):
    t = read_temperature_info(fake)
    assert t is not None and t.num_sensors == 1


# ─────────────────────────── force-sensing button (0x19C0) ────────────────


def test_force_sensing_decode_from_fixture_bytes():
    # Live: 0x19c0.00() = 01 00 ...
    fsb = decode_force_sensing(hexbytes("01 00"))
    assert fsb is not None
    assert fsb.num_buttons == 1
    assert fsb.capabilities == 0


def test_read_force_sensing_from_fixture(fake):
    fsb = read_force_sensing(fake)
    assert fsb is not None and fsb.num_buttons == 1


# ─────────────────────────── probe_all ────────────────────────────────────


def test_probe_all_one_entry_per_enumerated_feature(fake, fixture_cache):
    result = probe_all(fake)
    assert set(result.keys()) == set(fixture_cache.keys())
    assert len(result) == len(fixture_cache)


def test_probe_all_entries_have_name_index_and_outcome(fake):
    result = probe_all(fake)
    for fid, row in result.items():
        assert row["feature_id"] == fid
        assert row["name"] == feature_label(fid)
        assert row["description"]
        assert isinstance(row["index"], int)
        # exactly one of (response_hex, error) is populated, or neither
        # (when fn 0x00 timed out and the fake returns None)
        assert not (row["response_hex"] and row["error"])


def test_probe_all_flags_locked_features(fake):
    result = probe_all(fake)
    # 0x9401 MX_SMART_ACTIONS errors with 0x05 → locked
    assert result[0x9401]["locked"] is True
    assert result[0x9401]["error"] is not None
    assert result[0x9401]["response_hex"] is None
    # 0x1861 BATTERY_VOLTAGE is also 0x05-locked on this firmware
    assert result[0x1861]["locked"] is True


def test_probe_all_captures_successful_responses(fake):
    result = probe_all(fake)
    # 0x1815 HOSTS_INFO fn 0x00 returns real data
    assert result[0x1815]["response_hex"].startswith("130803")
    assert result[0x1815]["error"] is None
    assert result[0x1815]["locked"] is False
    # 0x2251 WHEEL_STATS returns real data
    assert result[0x2251]["response_hex"].startswith("0f0168007800")


def test_probe_all_result_dataclass_present(fake):
    result = probe_all(fake)
    row = result[0x1815]
    pr = row["result"]
    assert pr.feature_id == 0x1815
    assert pr.name == "HOSTS_INFO"
    assert pr.response_hex == row["response_hex"]


# ─────────────────────────── module sanity ────────────────────────────────


def test_module_exposes_expected_public_api():
    for sym in ("FEATURE_NAMES", "raw_call", "probe_all",
                "read_battery_voltage", "decode_wireless_status",
                "read_unique_id", "read_device_properties"):
        assert hasattr(raw, sym)
