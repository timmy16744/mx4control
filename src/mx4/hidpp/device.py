"""High-level MX Master 4 interface built on ``HIDPPDispatcher``.

Every method maps to a single HID++ 2.0 feature call. No threading or
locking here — the dispatcher owns all concurrency.

Byte layouts are live-verified against Logitech MX Master 4 firmware
39.0.0015 (Bolt) and cross-checked with Solaar's ``logitech_receiver``.
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from typing import Optional

from .dispatcher import HIDPPDispatcher
from .features import (
    BusType,
    FeatureID,
    HIDPPError,
    HiresFlag,
    KeyFlag,
    MappingFlag,
    WheelMode,
)

logger = logging.getLogger(__name__)


# ───────────────────────────── Data classes ──────────────────────────────

@dataclass(frozen=True)
class DeviceInfo:
    name: str
    friendly_name: Optional[str]
    firmware_version: str
    protocol_version: str
    battery_level: int
    battery_charging: bool
    battery_status: int
    connection_type: str  # "bolt" or "bluetooth"
    battery_bucket: int = 0

    @property
    def battery_level_name(self) -> str:
        return {8: "full", 4: "good", 2: "low", 1: "critical"}.get(
            self.battery_bucket, "unknown"
        )


@dataclass(frozen=True)
class ButtonInfo:
    """One REPROG_CONTROLS_V4 control."""
    index: int
    cid: int
    task_id: int
    flags: int
    remap_cid: int = 0
    diverted: bool = False
    persistently_diverted: bool = False
    raw_xy_diverted: bool = False

    @property
    def remappable(self) -> bool:
        return bool(self.flags & KeyFlag.REMAPPABLE)

    @property
    def divertable(self) -> bool:
        return bool(self.flags & KeyFlag.DIVERTABLE)


@dataclass(frozen=True)
class HostInfo:
    """One Easy-Switch paired-host slot."""
    index: int
    paired: bool
    bus_type: int  # BusType enum (4 = Bluetooth LE, 5 = Logi Bolt, ...)
    name: str
    max_name_len: int = 24

    @property
    def bus_label(self) -> str:
        return BusType.label(self.bus_type)


@dataclass(frozen=True)
class HostsSummary:
    num_hosts: int
    current_host: int
    capabilities: int
    max_name_len: int
    hosts: tuple[HostInfo, ...]

    @property
    def can_get_name(self) -> bool:
        return bool(self.capabilities & 0x01)

    @property
    def can_set_name(self) -> bool:
        return bool(self.capabilities & 0x02)


@dataclass(frozen=True)
class HapticCapabilities:
    """Capabilities of HAPTIC (0x19B0) from fn 0x00 + fn 0x01."""
    supported: bool
    discrete_levels: bool
    waveform_mask: int
    waveforms: tuple[int, ...]


@dataclass(frozen=True)
class ForceButtonInfo:
    """Force-sensing button parameters from FORCE_SENSING_BUTTON (0x19C0)."""
    index: int
    changeable: bool
    default_force: int
    min_force: int
    max_force: int
    current_force: int

    @property
    def percent(self) -> int:
        span = self.max_force - self.min_force
        if span <= 0:
            return 50
        return max(0, min(100, round((self.current_force - self.min_force) * 100 / span)))


@dataclass(frozen=True)
class SmartShiftState:
    """Full SMART_SHIFT_ENHANCED (0x2111) state & capabilities."""
    wheel_mode: int            # 1 = freespin, 2 = ratchet
    auto_disengage: int        # 1..50 = SmartShift threshold, 255 = off
    smartshift_enabled: bool
    threshold: int             # 1..50
    tuned_torque: int          # 1..100%
    tunable_torque: bool
    default_torque: int = 75
    default_auto_disengage: int = 10

    @property
    def mode_name(self) -> str:
        if self.wheel_mode == WheelMode.FREESPIN and not self.smartshift_enabled:
            return "free"
        if self.smartshift_enabled:
            return "smart"
        return "ratchet"


# ───────────────────────────── Device wrapper ────────────────────────────


class MXMaster4:
    """Typed wrapper over ``HIDPPDispatcher`` for MX Master 4 features."""

    def __init__(self, dispatcher: HIDPPDispatcher, connection_type: str = "bolt"):
        self._d = dispatcher
        self._connection_type = connection_type

    @property
    def dispatcher(self) -> HIDPPDispatcher:
        return self._d

    # ─── identification ─────────────────────────────────────────────────

    def get_device_name(self) -> Optional[str]:
        """Return the manufacturer-assigned name (e.g. 'MX Master 4')."""
        r = self._d.request(FeatureID.DEVICE_NAME, 0x00)
        if not r:
            return None
        name_len = r[0]
        name = bytearray()
        offset = 0
        while len(name) < name_len:
            chunk = self._d.request(FeatureID.DEVICE_NAME, 0x01, offset)
            if not chunk:
                break
            remaining = name_len - len(name)
            name.extend(chunk[:min(len(chunk), 16, remaining)])
            offset += 16
        return bytes(name).decode("utf-8", errors="ignore").strip("\x00") or None

    def get_friendly_name_limits(self) -> tuple[int, int]:
        """Return ``(current_len, max_len)`` for DEVICE_FRIENDLY_NAME (0x0007)."""
        if not self._d.has_feature(FeatureID.DEVICE_FRIENDLY_NAME):
            return 0, 0
        try:
            r = self._d.request(FeatureID.DEVICE_FRIENDLY_NAME, 0x00)
            if r and len(r) >= 2:
                return int(r[0]), int(r[1])
        except HIDPPError:
            pass
        return 0, 0

    def get_friendly_name(self) -> Optional[str]:
        """Return the user-settable friendly name if supported."""
        if not self._d.has_feature(FeatureID.DEVICE_FRIENDLY_NAME):
            return None
        try:
            r = self._d.request(FeatureID.DEVICE_FRIENDLY_NAME, 0x00)
        except HIDPPError:
            return None
        if not r:
            return None
        name_len = r[0]
        name = bytearray()
        offset = 0
        while len(name) < name_len:
            try:
                chunk = self._d.request(FeatureID.DEVICE_FRIENDLY_NAME, 0x01, offset)
            except HIDPPError:
                break
            if not chunk:
                break
            data = chunk[1:]  # skip offset echo
            remaining = name_len - len(name)
            name.extend(data[:min(len(data), 14, remaining)])
            offset += 14
        return bytes(name).decode("utf-8", errors="ignore").strip("\x00") or None

    def set_friendly_name(self, name: str) -> bool:
        """Write user-settable friendly name via DEVICE_FRIENDLY_NAME fn 0x03."""
        if not self._d.has_feature(FeatureID.DEVICE_FRIENDLY_NAME):
            return False
        _, max_len = self.get_friendly_name_limits()
        if max_len <= 0:
            max_len = 14
        encoded = name.strip().encode("utf-8")[:max_len]
        if not encoded:
            return self.reset_friendly_name()
        try:
            offset = 0
            while offset < len(encoded):
                chunk = encoded[offset:offset + 15]
                r = self._d.request(
                    FeatureID.DEVICE_FRIENDLY_NAME, 0x03,
                    offset, *chunk, use_long=True,
                )
                if r is None:
                    return False
                offset += len(chunk)
            return True
        except HIDPPError:
            return False

    def reset_friendly_name(self) -> bool:
        """Reset friendly name to factory default via DEVICE_FRIENDLY_NAME fn 0x04."""
        if not self._d.has_feature(FeatureID.DEVICE_FRIENDLY_NAME):
            return False
        try:
            r = self._d.request(FeatureID.DEVICE_FRIENDLY_NAME, 0x04)
            return r is not None
        except HIDPPError:
            return False

    def get_firmware_version(self) -> Optional[str]:
        """Return firmware version as 'major.minor.build'."""
        r = self._d.request(FeatureID.DEVICE_FW_VERSION, 0x00)
        if not r:
            r = self._d.request(FeatureID.ROOT, 0x01)
            if r and len(r) >= 3:
                return f"{r[0]}.{r[1]}.{r[2]:04x}"
            return None

        count = r[0]
        for i in range(count):
            r = self._d.request(FeatureID.DEVICE_FW_VERSION, 0x01, i)
            if r and len(r) >= 7:
                if r[0] == 0x00:
                    major = r[4]
                    minor = r[5]
                    build = (r[6] << 8) | r[7] if len(r) > 7 else 0
                    return f"{major}.{minor}.{build:04x}"
        return None

    def get_battery_detail(self) -> tuple[int, bool, int, int]:
        """Return ``(percent, charging, status_raw, level_bucket)``."""
        try:
            r = self._d.request(FeatureID.UNIFIED_BATTERY, 0x01)
            if r and len(r) >= 3:
                level = r[0]
                bucket = r[1]
                status = r[2]
                charging = status in (1, 2, 3)
                return level, charging, status, bucket
        except HIDPPError:
            pass
        return 0, False, 0, 0

    def get_battery(self) -> tuple[int, bool, int]:
        """Return ``(percent, charging, status_raw)``."""
        level, charging, status, _bucket = self.get_battery_detail()
        return level, charging, status

    def get_device_info(self) -> Optional[DeviceInfo]:
        """Bundle identification + power state into one struct."""
        name = self.get_device_name() or "MX Master 4"
        friendly = self.get_friendly_name()
        fw = self.get_firmware_version() or "unknown"
        level, charging, status, bucket = self.get_battery_detail()
        return DeviceInfo(
            name=name,
            friendly_name=friendly,
            firmware_version=fw,
            protocol_version="HID++ 2.0",
            battery_level=level,
            battery_charging=charging,
            battery_status=status,
            connection_type=self._connection_type,
            battery_bucket=bucket,
        )

    def ping(self) -> bool:
        """Cheap liveness check — one ROOT.getProtocolVersion call."""
        try:
            return self._d.request(FeatureID.ROOT, 0x01) is not None
        except HIDPPError:
            return False

    # ─── haptics (0x19B0) ───────────────────────────────────────────────

    def get_haptic_capabilities(self) -> HapticCapabilities:
        """Read HAPTIC (0x19B0) capabilities & supported waveform bitmask."""
        if not self._d.has_feature(FeatureID.HAPTIC):
            return HapticCapabilities(False, False, 0, ())
        try:
            r0 = self._d.request(FeatureID.HAPTIC, 0x00)
            r1 = self._d.request(FeatureID.HAPTIC, 0x01)
            mask = int.from_bytes(r0[4:8], "big") if r0 and len(r0) >= 8 else 0x7FFF
            discrete = bool(r1[2] & 0x01) if r1 and len(r1) >= 3 else False
            waves = tuple(i for i in range(32) if mask & (1 << i))
            return HapticCapabilities(True, discrete, mask, waves)
        except HIDPPError:
            return HapticCapabilities(True, False, 0x7FFF, tuple(range(15)))

    def trigger_haptic(self, pattern: int) -> bool:
        """Play a haptic waveform (0–14) via enumerated HAPTIC (0x19B0) fn 0x04.

        Falls back to raw direct address ``0x0B 0x4E`` only if HAPTIC wasn't
        enumerated (e.g. synthetic test fixture without 0x19B0).
        """
        pattern = max(0, min(27, int(pattern)))
        if self._d.has_feature(FeatureID.HAPTIC):
            try:
                r = self._d.request(FeatureID.HAPTIC, 0x04, pattern)
                if r is not None:
                    return True
            except HIDPPError:
                pass
        return self._d.raw_write_short(0x0B, 0x4E, pattern, 0, 0)

    def get_haptic(self) -> tuple[bool, int]:
        """Return ``(enabled, level 0..100)`` from HAPTIC 0x19B0 fn 0x01.

        Response = ``[statusByte, level, flags]``; bit 0 of statusByte = enabled.
        """
        if not self._d.has_feature(FeatureID.HAPTIC):
            return False, 0
        try:
            r = self._d.request(FeatureID.HAPTIC, 0x01)
            if r and len(r) >= 2:
                return bool(r[0] & 0x01), int(r[1])
        except HIDPPError:
            pass
        return False, 0

    def set_haptic(self, enabled: bool, level: int = 50) -> bool:
        """Enable/disable the haptic motor and set strength 1..100 (HAPTIC 0x19B0 fn 0x02)."""
        if not self._d.has_feature(FeatureID.HAPTIC):
            return False
        level = max(1, min(100, int(level))) if enabled else 0x32
        try:
            r = self._d.request(FeatureID.HAPTIC, 0x02, 0x01 if enabled else 0x00, level)
            return r is not None
        except HIDPPError:
            return False

    # ─── Force-Sensing Thumb Pad (0x19C0) ───────────────────────────────

    def get_force_button_count(self) -> int:
        if not self._d.has_feature(FeatureID.FORCE_SENSING_BUTTON):
            return 0
        try:
            r = self._d.request(FeatureID.FORCE_SENSING_BUTTON, 0x00)
            return int(r[0]) if r else 0
        except HIDPPError:
            return 0

    def get_force_button(self, index: int = 0) -> Optional[ForceButtonInfo]:
        """Read force-sensing thumb pad capabilities + current press threshold."""
        if not self._d.has_feature(FeatureID.FORCE_SENSING_BUTTON):
            return None
        try:
            cap = self._d.request(FeatureID.FORCE_SENSING_BUTTON, 0x01, index)
            cur = self._d.request(FeatureID.FORCE_SENSING_BUTTON, 0x02, index)
            if not cap or len(cap) < 8 or not cur or len(cur) < 2:
                return None
            changeable_raw, default_f, max_f, min_f = struct.unpack("!HHHH", cap[:8])
            current_f = struct.unpack("!H", cur[:2])[0]
            return ForceButtonInfo(
                index=index,
                changeable=bool(changeable_raw & 0x01),
                default_force=default_f,
                min_force=min_f,
                max_force=max_f,
                current_force=current_f,
            )
        except HIDPPError:
            return None

    def set_force_button(self, force: int, index: int = 0) -> bool:
        """Write thumb-pad actuation force threshold via 0x19C0 fn 0x03."""
        if not self._d.has_feature(FeatureID.FORCE_SENSING_BUTTON):
            return False
        info = self.get_force_button(index)
        if info is not None:
            if not info.changeable:
                return False
            force = max(info.min_force, min(info.max_force, int(force)))
        else:
            force = max(0, min(0xFFFF, int(force)))
        try:
            r = self._d.request(
                FeatureID.FORCE_SENSING_BUTTON, 0x03,
                index & 0xFF, (force >> 8) & 0xFF, force & 0xFF,
            )
            return r is not None
        except HIDPPError:
            return False

    # ─── DPI (0x2201) ───────────────────────────────────────────────────

    def get_dpi_range(self, sensor: int = 0) -> tuple[int, int, int]:
        """Return ``(min_dpi, max_dpi, step_dpi)`` decoded from 0x2201 fn 0x01."""
        try:
            r = self._d.request(FeatureID.ADJUSTABLE_DPI, 0x01, sensor, use_long=True)
            if r and len(r) >= 7:
                vals = []
                data = r[1:]
                i = 0
                while i + 1 < len(data):
                    v = (data[i] << 8) | data[i + 1]
                    if v == 0:
                        break
                    vals.append(v)
                    i += 2
                # Range format: [min, 0xE000 | step, max]
                if len(vals) >= 3 and (vals[1] & 0xE000) == 0xE000:
                    step = vals[1] & 0x1FFF
                    if step > 0 and vals[0] < vals[2]:
                        return vals[0], vals[2], step
                if vals:
                    return min(vals), max(vals), 50
        except HIDPPError:
            pass
        return 200, 8000, 50

    def get_dpi_list(self, sensor: int = 0) -> list[int]:
        """Return supported DPI values (flattening range-encoded lists)."""
        try:
            r = self._d.request(FeatureID.ADJUSTABLE_DPI, 0x01, sensor, use_long=True)
            if not r:
                return [400, 800, 1000, 1600, 2000, 4000, 8000]
            raw_vals = []
            data = r[1:]
            i = 0
            while i + 1 < len(data):
                v = (data[i] << 8) | data[i + 1]
                if v == 0:
                    break
                raw_vals.append(v)
                i += 2
            if len(raw_vals) >= 3 and (raw_vals[1] & 0xE000) == 0xE000:
                step = raw_vals[1] & 0x1FFF
                lo, hi = raw_vals[0], raw_vals[2]
                if step > 0 and lo < hi:
                    return list(range(lo, hi + 1, step))
            if raw_vals:
                return raw_vals
        except HIDPPError:
            pass
        return [400, 800, 1000, 1600, 2000, 4000, 8000]

    def get_dpi(self, sensor: int = 0) -> int:
        """Feature 0x2201 fn 0x02 = getSensorDpi(sensor_index)."""
        try:
            r = self._d.request(FeatureID.ADJUSTABLE_DPI, 0x02, sensor)
            if r and len(r) >= 3:
                dpi = (r[1] << 8) | r[2]
                if 50 <= dpi <= 32000:
                    return dpi
        except HIDPPError:
            pass
        return 1000

    def set_dpi(self, dpi: int) -> bool:
        dpi = max(200, min(8000, int(dpi)))
        try:
            r = self._d.request(
                FeatureID.ADJUSTABLE_DPI, 0x03,
                0, (dpi >> 8) & 0xFF, dpi & 0xFF,
            )
            return r is not None
        except HIDPPError:
            return False

    # ─── SmartShift Enhanced (0x2111) ───────────────────────────────────

    def _smartshift_feature(self) -> Optional[int]:
        if self._d.has_feature(FeatureID.SMART_SHIFT_ENHANCED):
            return FeatureID.SMART_SHIFT_ENHANCED
        return None

    _SS_CAPS = 0x00
    _SS_READ = 0x01
    _SS_WRITE = 0x02
    _SS_OFF = 0xFF

    def get_smartshift_capabilities(self) -> tuple[bool, int, int]:
        """Return ``(tunable_torque, default_auto_disengage, default_torque)``."""
        feat = self._smartshift_feature()
        if not feat:
            return False, 10, 75
        try:
            r = self._d.request(feat, self._SS_CAPS)
            if r and len(r) >= 3:
                return bool(r[0] & 0x01), int(r[1]) or 10, int(r[2]) or 75
        except HIDPPError:
            pass
        return False, 10, 75

    def get_smartshift_state(self) -> SmartShiftState:
        """Read full SMART_SHIFT_ENHANCED state: wheelMode, autoDisengage, torque."""
        tunable, def_auto, def_torque = self.get_smartshift_capabilities()
        feat = self._smartshift_feature()
        if not feat:
            return SmartShiftState(
                wheel_mode=WheelMode.RATCHET,
                auto_disengage=self._SS_OFF,
                smartshift_enabled=False,
                threshold=15,
                tuned_torque=def_torque,
                tunable_torque=tunable,
                default_torque=def_torque,
                default_auto_disengage=def_auto,
            )
        try:
            r = self._d.request(feat, self._SS_READ)
            if r and len(r) >= 2:
                wmode = int(r[0]) if r[0] in (1, 2) else WheelMode.RATCHET
                auto = int(r[1])
                torque = int(r[2]) if len(r) >= 3 and r[2] > 0 else def_torque
                enabled = 0 < auto < self._SS_OFF
                return SmartShiftState(
                    wheel_mode=wmode,
                    auto_disengage=auto,
                    smartshift_enabled=enabled,
                    threshold=auto if enabled else 15,
                    tuned_torque=torque,
                    tunable_torque=tunable,
                    default_torque=def_torque,
                    default_auto_disengage=def_auto,
                )
        except HIDPPError:
            pass
        return SmartShiftState(
            wheel_mode=WheelMode.RATCHET,
            auto_disengage=self._SS_OFF,
            smartshift_enabled=False,
            threshold=15,
            tuned_torque=def_torque,
            tunable_torque=tunable,
            default_torque=def_torque,
            default_auto_disengage=def_auto,
        )

    def get_smartshift(self) -> tuple[bool, int]:
        """Return ``(enabled, threshold)`` from 0x2111 fn 0x01."""
        feat = self._smartshift_feature()
        if not feat:
            return False, 15
        try:
            r = self._d.request(feat, self._SS_READ)
            if r and len(r) >= 2:
                auto = r[1]
                enabled = 0 < auto < self._SS_OFF
                return enabled, (auto if enabled else 15)
        except HIDPPError:
            pass
        return False, 15

    def set_smartshift(
        self,
        enabled: bool,
        threshold: int = 15,
        *,
        wheel_mode: Optional[int] = None,
        torque: Optional[int] = None,
    ) -> bool:
        """Write 0x2111 setRatchetControlMode (fn idx 2).

        Args layout: ``[wheelMode, autoDisengage, (optional) tunedTorque]``.
        ``wheel_mode``: 0=keep, 1=freespin, 2=ratchet.
        Note: On MX Master 4, changing ``torque`` requires passing a concrete
        ``wheelMode`` (1 or 2) in byte 0 so firmware applies the new torque
        immediately.
        """
        feat = self._smartshift_feature()
        if not feat:
            return False
        auto = max(1, min(50, int(threshold))) if enabled else self._SS_OFF
        wmode = WheelMode.KEEP if wheel_mode is None else int(wheel_mode)
        try:
            if torque is not None:
                t = max(1, min(100, int(torque)))
                if wmode == WheelMode.KEEP:
                    wmode = WheelMode.RATCHET
                r = self._d.request(feat, self._SS_WRITE, wmode, auto, t)
            else:
                r = self._d.request(feat, self._SS_WRITE, wmode, auto)
            return r is not None
        except HIDPPError:
            return False

    def set_scroll_mode(
        self,
        mode: str,
        threshold: int = 15,
        torque: Optional[int] = None,
    ) -> bool:
        """Set main scroll mode: ``'smart'``, ``'ratchet'``, or ``'free'``."""
        mode = mode.lower()
        if mode == "free":
            return self.set_smartshift(
                False, threshold, wheel_mode=WheelMode.FREESPIN, torque=torque,
            )
        if mode == "ratchet":
            return self.set_smartshift(
                False, threshold, wheel_mode=WheelMode.RATCHET, torque=torque,
            )
        # Default: "smart"
        return self.set_smartshift(
            True, threshold, wheel_mode=WheelMode.RATCHET, torque=torque,
        )

    # ─── Hi-Res Wheel (0x2121) ──────────────────────────────────────────

    def get_hires_capabilities(self) -> dict:
        """Return multiplier and capability flags from HIRES_WHEEL fn 0x00."""
        if not self._d.has_feature(FeatureID.HIRES_WHEEL):
            return {}
        try:
            r = self._d.request(FeatureID.HIRES_WHEEL, 0x00)
            if r and len(r) >= 2:
                return {
                    "multiplier": int(r[0]),
                    "has_invert": bool(r[1] & 0x08),
                    "has_ratchet": bool(r[1] & 0x04),
                    "flags": int(r[1]),
                }
        except HIDPPError:
            pass
        return {}

    def get_hires_scroll(self) -> tuple[bool, bool, bool]:
        """Return ``(hires_enabled, inverted, diverted)`` from HIRES_WHEEL fn 0x01."""
        if not self._d.has_feature(FeatureID.HIRES_WHEEL):
            return True, False, False
        try:
            r = self._d.request(FeatureID.HIRES_WHEEL, 0x01)
            if r:
                flags = r[0]
                return (
                    bool(flags & HiresFlag.HIRES),
                    bool(flags & HiresFlag.INVERT),
                    bool(flags & HiresFlag.DIVERT),
                )
        except HIDPPError:
            pass
        return True, False, False

    def set_hires_scroll(
        self, enabled: bool, invert: bool = False, diverted: bool = False
    ) -> bool:
        """Set HIRES_WHEEL mode via fn 0x02 (setWheelMode).

        Bits: ``0x01`` = divert to HID++, ``0x02`` = hi-res, ``0x04`` = invert.
        """
        if not self._d.has_feature(FeatureID.HIRES_WHEEL):
            return False
        flags = (
            (HiresFlag.DIVERT if diverted else 0)
            | (HiresFlag.HIRES if enabled else 0)
            | (HiresFlag.INVERT if invert else 0)
        )
        try:
            r = self._d.request(FeatureID.HIRES_WHEEL, 0x02, int(flags))
            return r is not None
        except HIDPPError:
            return False

    # ─── Thumb wheel (0x2150) ───────────────────────────────────────────

    def get_thumbwheel_info(self) -> dict:
        """Return native + diverted res, caps, time_unit, default direction."""
        if not self._d.has_feature(FeatureID.THUMBWHEEL):
            return {}
        try:
            r = self._d.request(FeatureID.THUMBWHEEL, 0x00)
        except HIDPPError:
            return {}
        if not r or len(r) < 6:
            return {}
        native_res = (r[0] << 8) | r[1]
        diverted_res = (r[2] << 8) | r[3]
        caps = r[5]
        time_unit = ((r[6] << 8) | r[7]) if len(r) >= 8 else 0
        ratio = round(diverted_res / native_res, 2) if native_res > 0 else 1.0
        return {
            "native_res": native_res,
            "diverted_res": diverted_res,
            "resolution_ratio": ratio,
            "default_direction": r[4],
            "capabilities": caps,
            "has_timestamp": bool(caps & 0x01),
            "has_touch": bool(caps & 0x02),
            "has_proxy": bool(caps & 0x04),
            "has_single_tap": bool(caps & 0x08),
            "time_unit_us": time_unit,
        }

    def get_thumbwheel_status(self) -> tuple[bool, bool]:
        """Return ``(diverted, inverted)`` from THUMBWHEEL fn 0x01."""
        if not self._d.has_feature(FeatureID.THUMBWHEEL):
            return False, False
        try:
            r = self._d.request(FeatureID.THUMBWHEEL, 0x01)
            if r and len(r) >= 2:
                return bool(r[0] & 0x01), bool(r[1] & 0x01)
        except HIDPPError:
            pass
        return False, False

    def set_thumbwheel_diverted(self, diverted: bool, invert: bool = False) -> bool:
        """Configure THUMBWHEEL reporting via fn 0x02: ``[divert_byte, invert_byte]``."""
        if not self._d.has_feature(FeatureID.THUMBWHEEL):
            return False
        try:
            r = self._d.request(
                FeatureID.THUMBWHEEL, 0x02,
                0x01 if diverted else 0x00,
                0x01 if invert else 0x00,
            )
            return r is not None
        except HIDPPError:
            return False

    # ─── Buttons (REPROG_CONTROLS_V4, 0x1B04) ───────────────────────────

    def get_button_count(self) -> int:
        try:
            r = self._d.request(FeatureID.REPROG_CONTROLS_V4, 0x00)
            if r:
                return r[0]
        except HIDPPError:
            pass
        return 0

    def get_button_info(self, index: int) -> Optional[ButtonInfo]:
        try:
            r = self._d.request(FeatureID.REPROG_CONTROLS_V4, 0x01, index)
            if not r or len(r) < 5:
                return None
            cid = (r[0] << 8) | r[1]
            tid = (r[2] << 8) | r[3]
            flags = r[4]
            rr = self._d.request(
                FeatureID.REPROG_CONTROLS_V4, 0x02,
                (cid >> 8) & 0xFF, cid & 0xFF,
            )
            remap = cid
            diverted = False
            pers_diverted = False
            raw_xy_diverted = False
            if rr and len(rr) >= 5:
                mflags = rr[2] | ((rr[5] if len(rr) > 5 else 0) << 8)
                remap = (rr[3] << 8) | rr[4]
                diverted = bool(mflags & MappingFlag.DIVERTED)
                pers_diverted = bool(mflags & MappingFlag.PERSISTENTLY_DIVERTED)
                raw_xy_diverted = bool(mflags & MappingFlag.RAW_XY_DIVERTED)
            return ButtonInfo(
                index=index, cid=cid, task_id=tid, flags=flags,
                remap_cid=remap, diverted=diverted,
                persistently_diverted=pers_diverted,
                raw_xy_diverted=raw_xy_diverted,
            )
        except HIDPPError:
            return None

    def divert_button(self, cid: int, diverted: bool) -> bool:
        """Divert or restore a button. Does NOT touch the remap target."""
        try:
            flags = MappingFlag.DIVERTED_VALID | (
                MappingFlag.DIVERTED if diverted else 0
            )
            r = self._d.request(
                FeatureID.REPROG_CONTROLS_V4, 0x03,
                (cid >> 8) & 0xFF, cid & 0xFF,
                flags,
                0x00, 0x00,  # 0x0000 = leave remap target unchanged
            )
            return r is not None
        except HIDPPError:
            return False

    def remap_button(self, cid: int, target_cid: int) -> bool:
        try:
            r = self._d.request(
                FeatureID.REPROG_CONTROLS_V4, 0x03,
                (cid >> 8) & 0xFF, cid & 0xFF,
                MappingFlag.DIVERTED_VALID,  # ensure un-diverted so firmware emits remap
                (target_cid >> 8) & 0xFF, target_cid & 0xFF,
            )
            return r is not None
        except HIDPPError:
            return False

    def reset_button(self, cid: int) -> bool:
        """Restore a control to factory default (un-diverted + remapped to itself)."""
        try:
            r = self._d.request(
                FeatureID.REPROG_CONTROLS_V4, 0x03,
                (cid >> 8) & 0xFF, cid & 0xFF,
                MappingFlag.DIVERTED_VALID | MappingFlag.PERSISTENTLY_DIVERTED_VALID,
                (cid >> 8) & 0xFF, cid & 0xFF,
            )
            return r is not None
        except HIDPPError:
            return False

    # ─── Easy-Switch hosts (0x1814 / 0x1815) ────────────────────────────

    def get_hosts(self) -> Optional[HostsSummary]:
        """Enumerate Easy-Switch hosts using HOSTS_INFO (0x1815) + CHANGE_HOST (0x1814).

        Live-verified layout on MX Master 4:
        - ``0x1815 fn 0x00`` -> ``[caps, reserved, numHosts, currentHost]``
        - ``0x1814 fn 0x00`` -> ``[numHosts, currentHost]``
        - ``0x1815 fn 0x01(h)`` -> ``[h, status, busType, numPages, nameLen, maxNameLen]``
        - ``0x1815 fn 0x03(h, offset)`` -> ``[h, offset, ...utf8 name bytes (up to 14)]``
        """
        if not self._d.has_feature(FeatureID.HOSTS_INFO):
            return None
        try:
            r = self._d.request(FeatureID.HOSTS_INFO, 0x00)
            if not r or len(r) < 4:
                return None
            caps = r[0]
            num = int(r[2]) if r[2] else (r[0] & 0x0F) or 1
            num = max(1, min(8, num))
            current = int(r[3])

            # Cross-check active host against CHANGE_HOST (0x1814) if available
            if self._d.has_feature(FeatureID.CHANGE_HOST):
                try:
                    ch = self._d.request(FeatureID.CHANGE_HOST, 0x00)
                    if ch and len(ch) >= 2 and ch[0] > 0:
                        num = max(1, min(8, int(ch[0])))
                        current = int(ch[1])
                except HIDPPError:
                    pass

            current = max(0, min(current, num - 1))
            max_name = 24
            can_read_names = bool(caps & 0x01)

            hosts = []
            for h in range(num):
                info = self._d.request(FeatureID.HOSTS_INFO, 0x01, h)
                if not info or len(info) < 6:
                    hosts.append(HostInfo(
                        index=h, paired=False, bus_type=0, name="",
                        max_name_len=max_name,
                    ))
                    continue
                paired = bool(info[1])
                bus_type = int(info[2])
                name_len = int(info[4])
                h_max_name = int(info[5]) or 24
                max_name = h_max_name
                name = (
                    self._read_host_name(h, name_len)
                    if paired and can_read_names and name_len > 0
                    else ""
                )
                hosts.append(HostInfo(
                    index=h, paired=paired, bus_type=bus_type, name=name,
                    max_name_len=h_max_name,
                ))
            return HostsSummary(
                num_hosts=num, current_host=current,
                capabilities=caps, max_name_len=max_name,
                hosts=tuple(hosts),
            )
        except HIDPPError:
            return None

    def _read_host_name(self, host_index: int, name_len: int) -> str:
        """Read a host's friendly name via HOSTS_INFO fn 0x03(host_idx, offset)."""
        if name_len <= 0:
            return ""
        name = bytearray()
        offset = 0
        while len(name) < name_len and offset < 64:
            try:
                chunk = self._d.request(FeatureID.HOSTS_INFO, 0x03, host_index, offset)
            except HIDPPError:
                break
            if not chunk or len(chunk) < 3:
                break
            data = chunk[2:]  # skip host_idx echo + offset echo
            if not data:
                break
            remaining = name_len - len(name)
            take = min(len(data), 14, remaining)
            name.extend(data[:take])
            offset += take
            if 0 in data[:take]:
                break
        raw = bytes(name)
        nul = raw.find(b"\x00")
        if nul >= 0:
            raw = raw[:nul]
        decoded = raw.decode("utf-8", errors="ignore").strip()
        return "".join(c for c in decoded if c.isprintable())

    def set_host_name(self, host_index: int, name: str) -> bool:
        """Set an Easy-Switch host's friendly name via HOSTS_INFO fn 0x04."""
        if not self._d.has_feature(FeatureID.HOSTS_INFO):
            return False
        summary = self.get_hosts()
        if not summary or not summary.can_set_name:
            return False
        if not (0 <= host_index < summary.num_hosts):
            return False
        max_len = summary.hosts[host_index].max_name_len or summary.max_name_len or 24
        encoded = name.strip().encode("utf-8")[:max_len]
        if not encoded:
            return False
        try:
            offset = 0
            while offset < len(encoded):
                chunk = encoded[offset:offset + 14]
                r = self._d.request(
                    FeatureID.HOSTS_INFO, 0x04,
                    host_index & 0xFF, offset & 0xFF, *chunk,
                    use_long=True,
                )
                if r is None:
                    return False
                offset += len(chunk)
            return True
        except HIDPPError:
            return False

    def switch_host(self, host_index: int) -> bool:
        try:
            r = self._d.request(FeatureID.CHANGE_HOST, 0x01, host_index)
            return r is not None
        except HIDPPError:
            return False
