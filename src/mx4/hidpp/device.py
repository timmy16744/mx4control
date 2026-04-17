"""High-level MX Master 4 interface built on ``HIDPPDispatcher``.

Every method maps to a single HID++ 2.0 feature call. No threading or
locking here — the dispatcher owns all concurrency.
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from typing import Optional

from .dispatcher import HIDPPDispatcher
from .features import (
    FeatureID, ControlID, HapticPattern,
    HIDPPError, MappingFlag, KeyFlag,
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


@dataclass(frozen=True)
class ButtonInfo:
    """One REPROG_CONTROLS_V4 control."""
    index: int
    cid: int
    task_id: int
    flags: int
    # Reporting state (from getCidReporting — fn 0x02). The buggy old
    # implementation read this from the wrong byte offset; now correct.
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
    bus_type: int  # 1 = Bluetooth, 2 = eQuad/Bolt
    name: str


@dataclass(frozen=True)
class HostsSummary:
    num_hosts: int
    current_host: int
    capabilities: int
    max_name_len: int
    hosts: tuple[HostInfo, ...]


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

    def get_friendly_name(self) -> Optional[str]:
        """Return the user-settable friendly name if supported."""
        if not self._d.has_feature(FeatureID.DEVICE_FRIENDLY_NAME):
            return None
        r = self._d.request(FeatureID.DEVICE_FRIENDLY_NAME, 0x00)
        if not r:
            return None
        name_len = r[0]
        name = bytearray()
        offset = 0
        while len(name) < name_len:
            chunk = self._d.request(FeatureID.DEVICE_FRIENDLY_NAME, 0x01, offset)
            if not chunk:
                break
            data = chunk[1:]  # skip offset echo
            remaining = name_len - len(name)
            name.extend(data[:min(len(data), 14, remaining)])
            offset += 14
        return bytes(name).decode("utf-8", errors="ignore").strip("\x00") or None

    def get_firmware_version(self) -> Optional[str]:
        """Return firmware version as 'major.minor.build'."""
        # DEVICE_FW_VERSION (0x0003) has structure:
        # fn 0x00 getInfo -> [entities_count, ...]
        # fn 0x01 getFwInfo(entity_idx) -> [fw_type, prefix(3), version(2), build(2), trPid(2)]
        r = self._d.request(FeatureID.DEVICE_FW_VERSION, 0x00)
        if not r:
            # Fall back to ROOT.getProtocolVersion for a version-shaped string
            r = self._d.request(FeatureID.ROOT, 0x01)
            if r and len(r) >= 3:
                return f"{r[0]}.{r[1]}.{r[2]:04x}"
            return None

        count = r[0]
        for i in range(count):
            r = self._d.request(FeatureID.DEVICE_FW_VERSION, 0x01, i)
            if r and len(r) >= 7:
                # fw_type 0x00 = main firmware, 0x01 = bootloader, 0x02 = hardware
                if r[0] == 0x00:
                    major = r[4]
                    minor = r[5]
                    build = (r[6] << 8) | r[7] if len(r) > 7 else 0
                    return f"{major}.{minor}.{build:04x}"
        return None

    def get_battery(self) -> tuple[int, bool, int]:
        """Return (percent, charging, status_raw).

        status_raw meanings (per UNIFIED_BATTERY spec):
            0 = discharging, 1 = charging, 2 = charging-nearly-full,
            3 = charging-complete, 4 = error
        """
        try:
            r = self._d.request(FeatureID.UNIFIED_BATTERY, 0x01)
            if r and len(r) >= 3:
                level = r[0]
                status = r[2]
                charging = status in (1, 2, 3)
                return level, charging, status
        except HIDPPError:
            pass
        return 0, False, 0

    def get_device_info(self) -> Optional[DeviceInfo]:
        """Bundle identification + power state into one struct."""
        name = self.get_device_name() or "MX Master 4"
        friendly = self.get_friendly_name()
        fw = self.get_firmware_version() or "unknown"
        level, charging, status = self.get_battery()
        return DeviceInfo(
            name=name,
            friendly_name=friendly,
            firmware_version=fw,
            protocol_version="HID++ 2.0",
            battery_level=level,
            battery_charging=charging,
            battery_status=status,
            connection_type=self._connection_type,
        )

    def ping(self) -> bool:
        """Cheap liveness check — one ROOT.getProtocolVersion call."""
        try:
            return self._d.request(FeatureID.ROOT, 0x01) is not None
        except HIDPPError:
            return False

    # ─── haptics ────────────────────────────────────────────────────────

    def trigger_haptic(self, pattern: int) -> bool:
        """Play a haptic pattern (0–14) via the direct-address feature.

        The MX Master 4 responds to feature 0x0B4E even though it isn't
        in the enumerated feature set. Confirmed working against
        firmware 4.5.0000 via the reverse-engineering probe.
        """
        pattern = max(0, min(14, int(pattern)))
        return self._d.raw_write_short(0x0B, 0x4E, pattern, 0, 0)

    # ─── DPI ────────────────────────────────────────────────────────────

    def get_dpi_list(self, sensor: int = 0) -> list[int]:
        """Feature 0x2201 fn 0x01 = getSensorDpiList(sensor_index).

        Response is a stream of 16-bit DPI values terminated by 0x0000
        (or by the LONG-message length). Some firmware uses a range
        encoding (start, step-marker, end) which we flatten on the fly.
        """
        try:
            r = self._d.request(FeatureID.ADJUSTABLE_DPI, 0x01, sensor, use_long=True)
            if not r:
                return [400, 800, 1000, 1600, 2000, 4000, 8000]
            out = []
            # Response is [sensor_echo, dpi_1, dpi_2, ...]
            data = r[1:]
            i = 0
            while i + 1 < len(data):
                v = (data[i] << 8) | data[i + 1]
                if v == 0:
                    break
                out.append(v)
                i += 2
            if out:
                return out
        except HIDPPError:
            pass
        return [400, 800, 1000, 1600, 2000, 4000, 8000]

    def get_dpi(self, sensor: int = 0) -> int:
        """Feature 0x2201 fn 0x02 = getSensorDpi(sensor_index).

        Response layout: [sensor_echo, dpi_hi, dpi_lo, default_hi, default_lo].
        """
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
        dpi = max(200, min(8000, dpi))
        try:
            r = self._d.request(
                FeatureID.ADJUSTABLE_DPI, 0x03,
                0, (dpi >> 8) & 0xFF, dpi & 0xFF,
            )
            return r is not None
        except HIDPPError:
            return False

    # ─── SmartShift ─────────────────────────────────────────────────────

    def _smartshift_feature(self) -> Optional[int]:
        if self._d.has_feature(FeatureID.SMART_SHIFT_ENHANCED):
            return FeatureID.SMART_SHIFT_ENHANCED
        if self._d.has_feature(FeatureID.SMART_SHIFT):
            return FeatureID.SMART_SHIFT
        return None

    def get_smartshift(self) -> tuple[bool, int]:
        feat = self._smartshift_feature()
        if not feat:
            return True, 25
        try:
            r = self._d.request(feat, 0x00)
            if r and len(r) >= 2:
                threshold = r[1]
                return threshold > 0, threshold or 25
        except HIDPPError:
            pass
        return True, 25

    def set_smartshift(self, enabled: bool, threshold: int = 25) -> bool:
        feat = self._smartshift_feature()
        if not feat:
            return False
        threshold = max(1, min(255, threshold))
        try:
            r = self._d.request(feat, 0x01, 1, threshold if enabled else 0)
            return r is not None
        except HIDPPError:
            return False

    def set_hires_scroll(self, enabled: bool, invert: bool = False) -> bool:
        flags = (0x01 if enabled else 0) | (0x02 if invert else 0)
        try:
            r = self._d.request(FeatureID.HIRES_WHEEL, 0x01, flags)
            return r is not None
        except HIDPPError:
            return False

    # ─── Thumb wheel (new in v2) ────────────────────────────────────────

    def get_thumbwheel_info(self) -> dict:
        """Return native + diverted res, caps, default direction."""
        r = self._d.request(FeatureID.THUMBWHEEL, 0x00)
        if not r or len(r) < 6:
            return {}
        return {
            "native_res": (r[0] << 8) | r[1],
            "diverted_res": (r[2] << 8) | r[3],
            "default_direction": r[4],
            "capabilities": r[5],
        }

    def set_thumbwheel_diverted(self, diverted: bool, invert: bool = False) -> bool:
        """Divert the thumb wheel so we can handle scroll events in software."""
        try:
            flags = (0x01 if diverted else 0) | (0x02 if invert else 0)
            r = self._d.request(FeatureID.THUMBWHEEL, 0x02, flags, 0)
            return r is not None
        except HIDPPError:
            return False

    # ─── Buttons (REPROG_CONTROLS_V4) ───────────────────────────────────

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
            # Fetch current reporting state (corrected byte offsets)
            rr = self._d.request(
                FeatureID.REPROG_CONTROLS_V4, 0x02,
                (cid >> 8) & 0xFF, cid & 0xFF,
            )
            remap = cid
            diverted = False
            pers_diverted = False
            raw_xy_diverted = False
            if rr and len(rr) >= 5:
                # Layout per HID++ 2.0: [cid(2), flags1, remap(2), flags2]
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
            # DIVERTED_VALID | (DIVERTED if diverted else 0)
            flags = MappingFlag.DIVERTED_VALID | (
                MappingFlag.DIVERTED if diverted else 0
            )
            r = self._d.request(
                FeatureID.REPROG_CONTROLS_V4, 0x03,
                (cid >> 8) & 0xFF, cid & 0xFF,
                flags,
                (cid >> 8) & 0xFF, cid & 0xFF,  # remap to self = no change
            )
            return r is not None
        except HIDPPError:
            return False

    def remap_button(self, cid: int, target_cid: int) -> bool:
        try:
            r = self._d.request(
                FeatureID.REPROG_CONTROLS_V4, 0x03,
                (cid >> 8) & 0xFF, cid & 0xFF,
                0x00,  # no flag change
                (target_cid >> 8) & 0xFF, target_cid & 0xFF,
            )
            return r is not None
        except HIDPPError:
            return False

    # ─── Easy-Switch hosts ──────────────────────────────────────────────

    def get_hosts(self) -> Optional[HostsSummary]:
        """Enumerate Easy-Switch hosts.

        HOSTS_INFO fn 0 response layout varies slightly by firmware
        revision but the low nibble of byte 0 consistently encodes
        the host count, and byte 2 is the currently-active host.
        Instead of trusting the spec layout for every vendor, we
        iterate slot indices defensively and keep the ones that
        respond with structured data.
        """
        if not self._d.has_feature(FeatureID.HOSTS_INFO):
            return None
        try:
            r = self._d.request(FeatureID.HOSTS_INFO, 0x00)
            if not r or len(r) < 3:
                return None
            caps = r[0]
            # Low nibble = count (max 15 realistically ≤ 3 on MX series)
            num = min(6, r[0] & 0x0F) if (r[0] & 0x0F) else min(6, r[1])
            # Current host is typically byte 1 on older FW, byte 2 on newer
            current = r[2] if r[2] < num else r[1]
            max_name = 24

            hosts = []
            for h in range(num):
                info = self._d.request(FeatureID.HOSTS_INFO, 0x01, h)
                if not info or len(info) < 4:
                    hosts.append(HostInfo(
                        index=h, paired=False, bus_type=0, name="",
                    ))
                    continue
                paired = bool(info[1])
                name_len = info[2]
                bus_type = info[3]
                name = self._read_host_name(h, name_len) if paired else ""
                hosts.append(HostInfo(
                    index=h, paired=paired, bus_type=bus_type, name=name,
                ))
            return HostsSummary(
                num_hosts=num, current_host=current,
                capabilities=caps, max_name_len=max_name,
                hosts=tuple(hosts),
            )
        except HIDPPError:
            return None

    def _read_host_name(self, host_index: int, name_len: int) -> str:
        if name_len <= 0:
            return ""
        name = bytearray()
        offset = 0
        # Chunk size depends on device: HOSTS_INFO v1 returns 15 bytes
        # of name per chunk (after 1 byte offset echo in some revs).
        # We pull up to ``max_name_len`` bytes total, stopping at the
        # first NUL.
        while len(name) < name_len and offset < 64:
            chunk = self._d.request(FeatureID.HOSTS_INFO, 0x02, host_index, offset)
            if not chunk:
                break
            # The probe showed the first byte of the chunk echoes the
            # offset; the rest is name bytes.
            data = chunk[1:]
            remaining = name_len - len(name)
            name.extend(data[:min(len(data), remaining)])
            offset += len(data)
            if 0 in data:
                break
        # Strip at first NUL and decode
        raw = bytes(name)
        nul = raw.find(b"\x00")
        if nul >= 0:
            raw = raw[:nul]
        return raw.decode("utf-8", errors="ignore").strip()

    def switch_host(self, host_index: int) -> bool:
        try:
            r = self._d.request(FeatureID.CHANGE_HOST, 0x01, host_index)
            return r is not None
        except HIDPPError:
            return False
