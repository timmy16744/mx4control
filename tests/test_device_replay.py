"""Replay-based regression tests for the MXMaster4 parsers.

These pin the byte-level behaviour that the Phase-0 hardening fixed:
Easy-Switch host parsing (current-host no longer goes out of range) and
SmartShift 0x2111 enable semantics (disable = ratchet mode, auto-disengage
off — what actually stops the clutch "buzz").
"""

from __future__ import annotations

import pytest

from mx4.hidpp.device import MXMaster4
from mx4.hidpp.features import FeatureID, TaskID
from fakes import FakeDispatcher


@pytest.fixture
def device_from_fixture(live_fixture) -> MXMaster4:
    cache = {int(k, 16): v for k, v in live_fixture["device"]["feature_cache"].items()}
    return MXMaster4(FakeDispatcher(cache, live_fixture["responses"]))


# ─── Easy-Switch hosts ───

def test_get_hosts_count_and_current_in_range(device_from_fixture):
    hosts = device_from_fixture.get_hosts()
    assert hosts is not None
    # Live device: byte0=0x13 (low nibble 3), hosts 0/1/2 valid, host 3 errors.
    assert hosts.num_hosts == 3
    # Regression: the old parser fell back to byte1 (0x08) and returned 8.
    assert 0 <= hosts.current_host < hosts.num_hosts
    assert hosts.current_host != 8


def test_get_hosts_pairing_and_bus(device_from_fixture):
    hosts = device_from_fixture.get_hosts()
    by_index = {h.index: h for h in hosts.hosts}
    assert by_index[0].paired is True
    # Live capture 0x1815.01(00) = 00 01 05 01 08 18 -> bus_type=5 (Logi Bolt),
    # 0x1815.01(01) = 01 01 04 01 0a 18 -> bus_type=4 (Bluetooth LE).
    assert by_index[0].bus_type == 5
    assert by_index[0].bus_label == "Logi Bolt"
    assert by_index[1].paired is True
    assert by_index[1].bus_type == 4
    assert by_index[1].bus_label == "Bluetooth LE"
    assert by_index[2].paired is False   # 0x1815.01(02) = 02 00 00 ...
    # Live capture 0x1815.00() = 13 08 03 00 -> current_host is byte 3 = 0
    assert hosts.current_host == 0


def test_get_hosts_max_name_len_from_device(device_from_fixture):
    # Trailing byte of each host-info record is 0x18 = 24, read from device
    # rather than hardcoded.
    assert device_from_fixture.get_hosts().max_name_len == 0x18


# ─── SmartShift 0x2111 semantics ───

def _smartshift_device(responses=None):
    cache = {int(FeatureID.SMART_SHIFT_ENHANCED): 17}
    return MXMaster4(FakeDispatcher(cache, responses or {}))


def test_smartshift_read_uses_fn_index_1():
    # 0x2111 read is function INDEX 1 (HID++ byte 0x10); autoDisengage 1..254
    # means SmartShift on at that threshold. Live read = [mode, auto, ...].
    dev = _smartshift_device({"0x2111.01()": "02 0a 4b 00"})
    enabled, threshold = dev.get_smartshift()
    assert enabled is True
    assert threshold == 0x0a  # 10


def test_smartshift_read_255_is_off():
    # autoDisengage 255 = always ratchet = SmartShift off (the buzz-free state).
    dev = _smartshift_device({"0x2111.01()": "02 ff 4b 00"})
    assert dev.get_smartshift() == (False, 15)


def test_smartshift_disable_writes_255_via_fn_index_2():
    fake = FakeDispatcher({int(FeatureID.SMART_SHIFT_ENHANCED): 17},
                          {"0x2111.02(*)": "00"})
    dev = MXMaster4(fake)
    assert dev.set_smartshift(False, 15) is True
    feat, fn, args = fake.calls[-1]
    assert feat == int(FeatureID.SMART_SHIFT_ENHANCED)
    assert fn == 0x02                 # write = function INDEX 2 (byte 0x20)
    assert args == (0x00, 0xFF)       # mode=keep, autoDisengage=255 -> no buzz


def test_smartshift_enable_writes_threshold():
    fake = FakeDispatcher({int(FeatureID.SMART_SHIFT_ENHANCED): 17},
                          {"0x2111.02(*)": "00"})
    dev = MXMaster4(fake)
    assert dev.set_smartshift(True, 20) is True
    feat, fn, args = fake.calls[-1]
    assert fn == 0x02
    assert args == (0x00, 20)         # mode=keep, autoDisengage=threshold


def test_smartshift_absent_returns_safe_default():
    dev = MXMaster4(FakeDispatcher({}, {}))   # no 0x2111
    assert dev.get_smartshift() == (False, 15)
    assert dev.set_smartshift(False) is False


# ─── reverse-engineered task IDs ───

def test_taskids_include_probed_values():
    assert TaskID.THUMBWHEEL == 0x0109
    assert TaskID.VIRTUAL_GESTURE == 0x00B4
