"""Phase 5 — reverse-engineered access to the MX Master 4's *unexplored*
HID++ 2.0 features.

The MX Master 4 (firmware 4.5.0000) enumerates 45 HID++ features. The
``device.py`` wrapper covers the dozen we actively *control* (battery,
hosts, buttons, DPI, SmartShift, thumb-wheel, gestures, haptics). The
remaining ~25 were probed during the live RE pass but never decoded into
typed accessors.

This module fills that gap. It provides:

1. ``FEATURE_NAMES`` — a human-readable label + one-line description for
   every feature ID the device exposes (named *and* unexplored), so the
   GUI/CLI "device explorer" can show something meaningful for each row.
2. ``raw_call`` — a thin generic wrapper over ``dispatcher.request`` that
   backs the planned ``mx4ctl raw`` command and the D-Bus
   ``RawFeatureCall`` method.
3. Typed decoder dataclasses + functions for the features we can decode
   with confidence from the captured fixture / HID++ 2.0 spec.
4. ``probe_all`` — walks every enumerated feature and records its fn-0x00
   response (hex or error), for the GUI device explorer / bug reports.

Everything here is *read-only* and side-effect-free except ``raw_call``
(which can write whatever the caller asks). Where a layout was inferred
rather than spec-confirmed, the docstring says so and cites the fixture
bytes that justify it.

Byte layouts are cross-checked against Solaar's ``logitech_receiver``
(the canonical Linux RE of these features) and the captured live
responses in ``tests/fixtures/mx4_master4_4.5.0000.json``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Protocol

from .features import HIDPPError

logger = logging.getLogger(__name__)


# ─────────────────────────── Dispatcher protocol ──────────────────────────
#
# We only need the read surface of HIDPPDispatcher. Typing against a
# Protocol lets the FakeDispatcher in the tests satisfy it without an
# import cycle or an isinstance check.


class _Dispatcher(Protocol):
    def request(self, feature_id: int, function_id: int, *args: int,
                use_long: bool = ..., timeout_ms: Optional[int] = ...) -> Optional[bytes]: ...

    def has_feature(self, feature_id: int) -> bool: ...

    def feature_index(self, feature_id: int) -> Optional[int]: ...

    @property
    def feature_cache(self) -> dict[int, int]: ...


# ───────────────────────────── Feature registry ───────────────────────────
#
# Label + short description for every feature ID the MX Master 4 exposes,
# plus the common ones it doesn't, so the registry stays useful across
# firmware revisions and sibling devices.
#
# Names follow Logitech's HID++ 2.0 feature catalogue and Solaar's
# `logitech_receiver.hidpp20_constants.SupportedFeature`. Features marked
# "(locked)" return error 0x05 (Logitech-internal) to unauthenticated
# callers on this firmware — Logi Options+ unlocks them via 0x1602/0x1E00.

FEATURE_NAMES: dict[int, tuple[str, str]] = {
    # ─── Core / introspection ───
    0x0000: ("ROOT", "Feature discovery root (getFeature/getProtocolVersion)"),
    0x0001: ("FEATURE_SET", "Enumerates every supported feature index/ID"),
    0x0002: ("FEATURE_INFO", "Per-feature version & flag metadata"),
    0x0003: ("DEVICE_FW_VERSION", "Firmware/bootloader/hardware version entities"),
    0x0004: ("DEVICE_UNIT_ID", "Per-unit serial / unit identifier"),
    0x0005: ("DEVICE_NAME", "Manufacturer device name + device type"),
    0x0006: ("DEVICE_GROUPS", "Device-group / friendly-grouping info"),
    0x0007: ("DEVICE_FRIENDLY_NAME", "User-settable friendly name"),
    0x0008: ("KEEP_ALIVE", "Link keep-alive timing"),
    0x0011: ("CONFIG_DEVICE_INFO", "Configurable device-info blob (locked)"),
    0x0020: ("CONFIG_CHANGE", "Configuration-cookie / change notification"),
    0x0021: ("UNIQUE_IDENTIFIER", "32-byte unique device identifier (CRYPTO_ID)"),
    # ─── Power ───
    0x1000: ("BATTERY_STATUS", "Legacy battery status (percent + charging)"),
    0x1001: ("BATTERY_VOLTAGE_LEGACY", "Legacy battery-voltage feature ID"),
    0x1004: ("UNIFIED_BATTERY", "Unified battery: percent + discrete level + state"),
    0x1010: ("CHARGING_CONTROL", "Charging-control parameters"),
    # ─── Generic test / device management ───
    0x1801: ("MANUFACTURING_MODE", "Manufacturing/test mode (locked)"),
    0x1802: ("DEVICE_RESET", "Force device reset / reboot (locked)"),
    0x1803: ("GPIO_ACCESS", "Raw GPIO access (locked)"),
    0x1805: ("OOB_STATE", "Out-of-box-state reset to factory (locked)"),
    0x1806: ("CONFIG_DEVICE_PROPS", "Configurable device properties (legacy)"),
    0x1807: ("CONFIG_DEVICE_PROPERTIES", "Configurable device properties / SKU blob (locked)"),
    0x1814: ("CHANGE_HOST", "Easy-Switch: read/set the active host"),
    0x1815: ("HOSTS_INFO", "Easy-Switch: paired-host slots, names, bus type"),
    0x1816: ("BLE_PRO_DEVICE_INFO", "Bolt/BLE-Pro pairing & device info (locked)"),
    0x1830: ("POWER_MODES", "Power-mode / deep-sleep management (locked)"),
    0x1861: ("BATTERY_VOLTAGE", "Battery voltage in mV + charge flags"),
    0x1890: ("RF_TEST", "RF test harness (locked)"),
    0x1891: ("RF_TEST_EXTENDED", "Extended RF test harness (locked)"),
    0x18A1: ("LED_TEST", "LED test harness (locked)"),
    0x18B1: ("ANALYTICS_EVENTS", "Usage-analytics event reporting (locked)"),
    0x1D4B: ("WIRELESS_DEVICE_STATUS", "Wireless link status / reconnection notify"),
    0x1DF3: ("EQUAD_DJ_DEVICE_NAME", "eQuad/DJ device name"),
    0x1E00: ("ENABLE_HIDDEN_FEATURES", "Toggle Logitech-internal hidden features"),
    0x1E02: ("MANAGE_DEACTIVATABLE_FEATURES", "Enable/disable lockable features (locked)"),
    0x1E22: ("SPI_DIRECT_ACCESS", "Raw SPI flash access (locked)"),
    0x1E30: ("I2C_DIRECT_ACCESS", "Raw I2C bus access (locked)"),
    0x1EB0: ("TDE_ACCESS", "Test/debug/engineering register access (locked)"),
    0x1602: ("PASSWORD", "Challenge/response auth gate for locked features"),
    0x1F1F: ("FIRMWARE_PROPERTIES", "Firmware property blob"),
    0x1F20: ("ADC_MEASUREMENT", "Raw ADC voltage measurement"),
    # ─── Input / controls ───
    0x1701: ("TEMPERATURE_MEASUREMENT", "On-die temperature sensor readout"),
    0x1B04: ("REPROG_CONTROLS_V4", "Remappable controls: cid/task info + diversion"),
    0x19B0: ("HAPTIC", "Haptic motor power / gesture-pad vibration (0 = off)"),
    0x19C0: ("FORCE_SENSING_BUTTON", "Force-sensing button capabilities + thresholds"),
    0x00D1: ("HOST_SWITCH_CHANNEL", "Host-switch channel / control descriptor"),
    # ─── Pointer & scroll ───
    0x2110: ("SMART_SHIFT", "SmartShift ratchet threshold (base)"),
    0x2111: ("SMART_SHIFT_ENHANCED", "SmartShift enhanced: wheel mode + auto-disengage"),
    0x2121: ("HIRES_WHEEL", "Hi-res main wheel: ratchet/freespin, divert, invert"),
    0x2150: ("THUMB_WHEEL", "Thumb wheel: resolution, divert, default direction"),
    0x2201: ("ADJUSTABLE_DPI", "Per-sensor DPI list / get / set"),
    # ─── Telemetry ───
    0x2250: ("XY_STATS", "Cumulative X/Y movement statistics"),
    0x2251: ("WHEEL_STATS", "Cumulative wheel / scroll statistics"),
    # ─── Sensor / MX-specific (firmware-locked) ───
    0x9001: ("SENSOR_PARAMS", "Optical-sensor parameter access (locked)"),
    0x9201: ("MOUSE_SENSOR", "Mouse-sensor register access (locked)"),
    0x9205: ("MOTION_SENSOR", "Motion-sensor calibration access (locked)"),
    0x9300: ("SENSOR_CALIBRATION", "Sensor calibration data (locked)"),
    0x9401: ("MX_SMART_ACTIONS", "MX Smart Actions engine (Options+ only, locked)"),
    0x9402: ("MX_PROFILES", "MX onboard profiles (Options+ only, locked)"),
    0x0B4E: ("MX_HAPTICS_DIRECT", "Direct-address haptic waveform trigger (hidden)"),
}


def feature_label(feature_id: int) -> str:
    """Return ``"NAME"`` for a known feature, else ``"UNKNOWN_0xXXXX"``."""
    entry = FEATURE_NAMES.get(feature_id)
    return entry[0] if entry else f"UNKNOWN_{feature_id:#06x}"


def feature_description(feature_id: int) -> str:
    """Return the one-line description, or a generic fallback."""
    entry = FEATURE_NAMES.get(feature_id)
    return entry[1] if entry else "Unrecognised HID++ 2.0 feature"


# ─────────────────────────── Generic raw call ─────────────────────────────


def raw_call(dispatcher: _Dispatcher, feature_id: int, function_id: int,
             args: list[int], use_long: bool = False) -> Optional[bytes]:
    """Invoke an arbitrary feature function and return the raw payload.

    This is the un-typed escape hatch behind ``mx4ctl raw`` and the D-Bus
    ``RawFeatureCall``. It does *not* swallow ``HIDPPError`` — the caller
    decides whether a device error is interesting (the explorer wants to
    show it; a control path wants to react to it).

    Returns ``None`` if the feature isn't present or the request times
    out. ``args`` longer than 3 bytes (or ``use_long=True``) forces a
    20-byte LONG report.
    """
    if not dispatcher.has_feature(feature_id):
        return None
    return dispatcher.request(
        feature_id, function_id, *args,
        use_long=use_long or len(args) > 3,
    )


# ─────────────────────────── Typed decoders ───────────────────────────────


@dataclass(frozen=True)
class BatteryVoltage:
    """Decoded ``BATTERY_VOLTAGE`` (0x1861) reading.

    Layout (Solaar ``decipher_battery_voltage``, fn 0x00 getBatteryVoltage)::

        byte0..1  voltage   big-endian uint16, millivolts
        byte2     flags
                    bit7  charging (recharging)
                    bit4  slow/trickle charge
                    bit3  fast charge
                    bit5  critical level
                    bit1..0  charge status when charging (0..3)

    A single Li-ion cell reads ~3.5 V (empty) to ~4.2 V (full), so a sane
    decode lands in roughly the 3000-4300 mV window. ``percent`` is a
    piece-wise-linear estimate from the same voltage table Solaar uses.
    """
    millivolts: int
    charging: bool
    fast_charge: bool
    slow_charge: bool
    critical: bool
    charge_status: int
    percent: int
    flags: int


# Voltage→percent breakpoints (mV, %) for a single Li-ion cell, from
# Solaar's estimate_battery_level_percentage. Monotonic descending.
_VOLTAGE_TO_PERCENT: tuple[tuple[int, int], ...] = (
    (4186, 100), (4067, 90), (3989, 80), (3922, 70), (3859, 60),
    (3811, 50), (3778, 40), (3751, 30), (3717, 20), (3671, 10),
    (3646, 5), (3579, 2), (3500, 0),
)


def estimate_voltage_percent(millivolts: int) -> int:
    """Piece-wise-linear battery percent for a Li-ion cell voltage (mV)."""
    table = _VOLTAGE_TO_PERCENT
    if millivolts >= table[0][0]:
        return table[0][1]
    if millivolts <= table[-1][0]:
        return table[-1][1]
    for i in range(len(table) - 1):
        v_hi, p_hi = table[i]
        v_lo, p_lo = table[i + 1]
        if v_lo <= millivolts <= v_hi:
            return round(p_lo + (p_hi - p_lo) * (millivolts - v_lo) / (v_hi - v_lo))
    return 0


def decode_battery_voltage(payload: bytes) -> Optional[BatteryVoltage]:
    """Decode a raw 0x1861 getBatteryVoltage payload. ``None`` if too short."""
    if not payload or len(payload) < 3:
        return None
    millivolts = (payload[0] << 8) | payload[1]
    flags = payload[2]
    charging = bool(flags & (1 << 7))
    return BatteryVoltage(
        millivolts=millivolts,
        charging=charging,
        fast_charge=bool(flags & (1 << 3)),
        slow_charge=bool(flags & (1 << 4)),
        critical=bool(flags & (1 << 5)),
        charge_status=(flags & 0x03) if charging else 0,
        percent=estimate_voltage_percent(millivolts),
        flags=flags,
    )


def read_battery_voltage(dispatcher: _Dispatcher) -> Optional[BatteryVoltage]:
    """Read 0x1861 BATTERY_VOLTAGE → ``BatteryVoltage`` or ``None``.

    Tries fn 0x00 (getBatteryVoltage). On this firmware the call is gated
    behind Logi-Options+ auth and returns error 0x05; we treat that as
    "unavailable" and return ``None`` rather than raising.
    """
    if not dispatcher.has_feature(0x1861):
        return None
    try:
        r = dispatcher.request(0x1861, 0x00)
    except HIDPPError as e:
        logger.debug("BATTERY_VOLTAGE locked/error: %s", e)
        return None
    return decode_battery_voltage(r) if r else None


@dataclass(frozen=True)
class UnifiedBattery:
    """Decoded ``UNIFIED_BATTERY`` (0x1004) status (fn 0x01 getStatus).

    Layout (Solaar ``decipher_battery_unified``)::

        byte0  stateOfCharge   percent (0..100), 0 if device reports level only
        byte1  level           discrete bucket bitfield: 8=full 4=good 2=low 1=critical
        byte2  status          0 discharging, 1 charging, 2 charging-near-full,
                               3 charge-complete, 4 charge-fault, ...
        byte3  reserved

    ``capabilities`` byte (from fn 0x00 getCapabilities, if read) is left
    to the caller; this decodes the *status* report.
    """
    percent: int
    level_bucket: int
    status: int
    charging: bool

    @property
    def level_name(self) -> str:
        return {8: "full", 4: "good", 2: "low", 1: "critical"}.get(
            self.level_bucket, "empty")


def decode_unified_battery(payload: bytes) -> Optional[UnifiedBattery]:
    """Decode a raw 0x1004 getStatus payload. ``None`` if too short."""
    if not payload or len(payload) < 3:
        return None
    percent = payload[0]
    level = payload[1]
    status = payload[2]
    return UnifiedBattery(
        percent=percent,
        level_bucket=level,
        status=status,
        charging=status in (1, 2, 3),
    )


def read_unified_battery(dispatcher: _Dispatcher) -> Optional[UnifiedBattery]:
    """Read 0x1004 UNIFIED_BATTERY status (fn 0x01). ``None`` if unavailable.

    A richer companion to ``device.MXMaster4.get_battery`` that surfaces
    the discrete level bucket alongside the percentage.
    """
    if not dispatcher.has_feature(0x1004):
        return None
    try:
        r = dispatcher.request(0x1004, 0x01)
    except HIDPPError as e:
        logger.debug("UNIFIED_BATTERY error: %s", e)
        return None
    return decode_unified_battery(r) if r else None


@dataclass(frozen=True)
class WirelessStatus:
    """Decoded ``WIRELESS_DEVICE_STATUS`` (0x1D4B) reconnection report.

    0x1D4B has no readable getter — the device *pushes* a notification on
    (re)connection. Layout of that event payload::

        byte0  reconnection   1 = device reconnected and needs (re)config
        byte1  reconfNeeded   nonzero if the host must re-apply settings
        byte2  powerSwitch    1 = powered on via the on/off switch

    ``read_wireless_status`` therefore decodes a *captured* notification
    payload rather than issuing a request. Provided so the daemon's
    notification handler can turn the raw bytes into a typed event.
    """
    reconnection: bool
    reconf_needed: bool
    powered_on: bool
    raw: bytes


def decode_wireless_status(payload: bytes) -> Optional[WirelessStatus]:
    """Decode a 0x1D4B reconnection-notification payload."""
    if not payload:
        return None
    b0 = payload[0]
    b1 = payload[1] if len(payload) > 1 else 0
    b2 = payload[2] if len(payload) > 2 else 0
    return WirelessStatus(
        reconnection=bool(b0 & 0x01),
        reconf_needed=bool(b1),
        powered_on=bool(b2 & 0x01),
        raw=bytes(payload[:3]),
    )


@dataclass(frozen=True)
class UniqueId:
    """Decoded ``UNIQUE_IDENTIFIER`` (0x0021 / CRYPTO_ID).

    fn 0x00 getUniqueId returns up to a 16-byte chunk of an opaque
    identifier; a 32-byte id is read in two LONG calls. We surface the
    raw bytes plus a lowercase-hex string for display/keying. The id is
    not interpreted further (it's an opaque per-unit value).
    """
    raw: bytes

    @property
    def hex(self) -> str:
        return self.raw.hex()


def read_unique_id(dispatcher: _Dispatcher) -> Optional[UniqueId]:
    """Read 0x0021 UNIQUE_IDENTIFIER. Returns up to 32 bytes, or ``None``.

    fn 0x00 yields the first chunk; if it comes back full (>=16 payload
    bytes) we read fn 0x01 for the rest to assemble the documented 32-byte
    id. Trailing NULs are trimmed.
    """
    if not dispatcher.has_feature(0x0021):
        return None
    try:
        first = dispatcher.request(0x0021, 0x00, use_long=True)
    except HIDPPError as e:
        logger.debug("UNIQUE_IDENTIFIER error: %s", e)
        return None
    if not first:
        return None
    raw = bytearray(first)
    if len(first) >= 16:
        try:
            second = dispatcher.request(0x0021, 0x01, use_long=True)
        except HIDPPError:
            second = None
        if second:
            raw.extend(second)
    trimmed = bytes(raw).rstrip(b"\x00")
    return UniqueId(raw=trimmed or bytes(raw[:1]))


@dataclass(frozen=True)
class DeviceProperties:
    """Decoded ``CONFIG_DEVICE_PROPERTIES`` (0x1807) property record.

    fn 0x00 getDeviceProperties echoes ``[propertyId, flags, ...data]``.
    The property catalogue (SKU string, extended model id, serial, etc.)
    is firmware-private; on this device the call is auth-gated and returns
    error 0x05. We decode whatever the device returns into id/flags/data
    so an authenticated caller can iterate the catalogue.
    """
    property_id: int
    flags: int
    data: bytes


def decode_device_properties(payload: bytes) -> Optional[DeviceProperties]:
    """Decode a raw 0x1807 getDeviceProperties payload."""
    if not payload or len(payload) < 2:
        return None
    return DeviceProperties(
        property_id=payload[0],
        flags=payload[1],
        data=bytes(payload[2:]).rstrip(b"\x00"),
    )


def read_device_properties(dispatcher: _Dispatcher,
                           property_id: int = 0) -> Optional[DeviceProperties]:
    """Read 0x1807 CONFIG_DEVICE_PROPERTIES. ``None`` if locked/unavailable."""
    if not dispatcher.has_feature(0x1807):
        return None
    try:
        r = dispatcher.request(0x1807, 0x00, property_id)
    except HIDPPError as e:
        logger.debug("CONFIG_DEVICE_PROPERTIES locked/error: %s", e)
        return None
    return decode_device_properties(r) if r else None


@dataclass(frozen=True)
class XYStats:
    """Decoded ``XY_STATS`` (0x2250) getInfo (fn 0x00).

    Inferred from the live capture ``0x2250.00() = 00 01 00 00 ...``:

        byte0  capabilities / version flags
        byte1  number of available statistics counters (here 1)

    The actual cumulative X/Y counts are read per-counter via fn 0x01/0x02
    (both return all-zeroes on a freshly-probed unit in the fixture). This
    is a best-effort layout — Solaar does not decode XY_STATS — so we keep
    the raw getInfo bytes too.
    """
    capabilities: int
    num_counters: int
    raw: bytes


def decode_xy_stats(payload: bytes) -> Optional[XYStats]:
    if not payload or len(payload) < 2:
        return None
    return XYStats(capabilities=payload[0], num_counters=payload[1],
                   raw=bytes(payload[:4]))


def read_xy_stats(dispatcher: _Dispatcher) -> Optional[XYStats]:
    """Read 0x2250 XY_STATS getInfo. ``None`` if unavailable."""
    if not dispatcher.has_feature(0x2250):
        return None
    try:
        r = dispatcher.request(0x2250, 0x00)
    except HIDPPError as e:
        logger.debug("XY_STATS error: %s", e)
        return None
    return decode_xy_stats(r) if r else None


@dataclass(frozen=True)
class WheelStats:
    """Decoded ``WHEEL_STATS`` (0x2251) getInfo (fn 0x00).

    Inferred from the live capture ``0x2251.00() = 0f 01 68 00 78 00 ...``:

        byte0     capabilities bitfield (0x0f = 4 capability bits set)
        byte1     number of statistics counters (1)
        byte2..3  big-endian field — 0x0068 = 104
        byte4..5  big-endian field — 0x0078 = 120

    The two 16-bit fields look like per-detent resolution / range values
    rather than live counts (the cumulative counters via fn 0x01/0x02 are
    zero in the fixture). Best-effort — Solaar does not decode WHEEL_STATS
    — so the raw getInfo bytes are preserved for the explorer.
    """
    capabilities: int
    num_counters: int
    field_a: int
    field_b: int
    raw: bytes


def decode_wheel_stats(payload: bytes) -> Optional[WheelStats]:
    if not payload or len(payload) < 6:
        return None
    return WheelStats(
        capabilities=payload[0],
        num_counters=payload[1],
        field_a=(payload[2] << 8) | payload[3],
        field_b=(payload[4] << 8) | payload[5],
        raw=bytes(payload[:6]),
    )


def read_wheel_stats(dispatcher: _Dispatcher) -> Optional[WheelStats]:
    """Read 0x2251 WHEEL_STATS getInfo. ``None`` if unavailable."""
    if not dispatcher.has_feature(0x2251):
        return None
    try:
        r = dispatcher.request(0x2251, 0x00)
    except HIDPPError as e:
        logger.debug("WHEEL_STATS error: %s", e)
        return None
    return decode_wheel_stats(r) if r else None


@dataclass(frozen=True)
class Temperature:
    """Decoded ``TEMPERATURE_MEASUREMENT`` (0x1701) getInfo (fn 0x00).

    Inferred from the live capture ``0x1701.00() = 01 00 0a 00 ...``:

        byte0     number of temperature sensors (1)
        byte1     reserved / flags
        byte2..3  big-endian capability/range word — 0x000a = 10

    Best-effort identification. The per-sensor reading is obtained via a
    higher function id; we expose the sensor count + raw bytes so the
    explorer can label the feature and a future control path can iterate.
    """
    num_sensors: int
    raw: bytes


def decode_temperature_info(payload: bytes) -> Optional[Temperature]:
    if not payload:
        return None
    return Temperature(num_sensors=payload[0], raw=bytes(payload[:4]))


def read_temperature_info(dispatcher: _Dispatcher) -> Optional[Temperature]:
    """Read 0x1701 TEMPERATURE_MEASUREMENT getInfo. ``None`` if unavailable."""
    if not dispatcher.has_feature(0x1701):
        return None
    try:
        r = dispatcher.request(0x1701, 0x00)
    except HIDPPError as e:
        logger.debug("TEMPERATURE_MEASUREMENT error: %s", e)
        return None
    return decode_temperature_info(r) if r else None


@dataclass(frozen=True)
class ForceSensingButton:
    """Decoded ``FORCE_SENSING_BUTTON`` (0x19C0) getCapabilities (fn 0x00).

    Inferred from the live capture ``0x19c0.00() = 01 00 ...``:

        byte0  number of force-sensing buttons (1 — the gesture button)
        byte1  capability flags

    Per-button force thresholds are read via fn 0x10/0x20 (see Solaar's
    ForceSensingButton). The MX Master 4's gesture button is force-aware,
    which makes this a promising *control* target: an authenticated path
    could tune the press-force threshold.
    """
    num_buttons: int
    capabilities: int
    raw: bytes


def decode_force_sensing(payload: bytes) -> Optional[ForceSensingButton]:
    if not payload:
        return None
    return ForceSensingButton(
        num_buttons=payload[0],
        capabilities=payload[1] if len(payload) > 1 else 0,
        raw=bytes(payload[:2]),
    )


def read_force_sensing(dispatcher: _Dispatcher) -> Optional[ForceSensingButton]:
    """Read 0x19C0 FORCE_SENSING_BUTTON capabilities. ``None`` if unavailable."""
    if not dispatcher.has_feature(0x19C0):
        return None
    try:
        r = dispatcher.request(0x19C0, 0x00)
    except HIDPPError as e:
        logger.debug("FORCE_SENSING_BUTTON error: %s", e)
        return None
    return decode_force_sensing(r) if r else None


# ─────────────────────────── Device explorer ──────────────────────────────


@dataclass(frozen=True)
class ProbeResult:
    """One row in the device-explorer probe."""
    feature_id: int
    index: int
    name: str
    description: str
    response_hex: Optional[str]   # fn-0x00 payload hex, if it returned data
    error: Optional[str]          # error string, if fn-0x00 errored
    locked: bool                  # True if the error was 0x05 (Logitech-internal)


def probe_all(dispatcher: _Dispatcher) -> dict[int, dict]:
    """Walk every enumerated feature and capture its fn-0x00 response.

    Returns ``{feature_id: {...}}`` with one entry per feature in the
    dispatcher's ``feature_cache``. Each value carries the human label,
    description, feature index, and the result of calling fn 0x00:
    either ``response_hex`` (success) or ``error`` (device error string,
    with ``locked`` set when the error is the Logitech-internal 0x05 used
    to gate Options+-only features). Powers the GUI "device explorer".

    fn 0x00 is the universal "getInfo/getCapabilities/getCount" entry
    point, so probing it is safe and side-effect-free across features.
    """
    out: dict[int, dict] = {}
    for fid, index in sorted(dispatcher.feature_cache.items()):
        name = feature_label(fid)
        desc = feature_description(fid)
        response_hex: Optional[str] = None
        error: Optional[str] = None
        locked = False
        try:
            r = dispatcher.request(fid, 0x00)
            if r is not None:
                response_hex = bytes(r).hex()
        except HIDPPError as e:
            error = str(e)
            locked = e.code == 0x05
        result = ProbeResult(
            feature_id=fid, index=index, name=name, description=desc,
            response_hex=response_hex, error=error, locked=locked,
        )
        out[fid] = {
            "feature_id": fid,
            "index": index,
            "name": name,
            "description": desc,
            "response_hex": response_hex,
            "error": error,
            "locked": locked,
            "result": result,
        }
    return out
