"""
HID++ Protocol Implementation for Logitech MX Master 4

This module provides low-level communication with Logitech devices
using the HID++ 2.0 protocol over USB HID or Bluetooth.
"""

import struct
import logging
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional, Callable
import threading
import time

try:
    import hid
except ImportError:
    hid = None
    logging.warning("hidapi not installed. Install with: pip install hidapi")

logger = logging.getLogger(__name__)


# Logitech Vendor ID
LOGITECH_VID = 0x046D

# MX Master 4 Product IDs
MX_MASTER_4_PIDS = {
    0xB042: "MX Master 4 (Bolt)",
    0x4107: "MX Master 4 (Bluetooth)",
}

# Logitech Receiver Product IDs
RECEIVER_PIDS = {
    0xC548: "Bolt Receiver",
    0xC52B: "Unifying Receiver",
}

# HID++ Message Types
class MessageType(IntEnum):
    SHORT = 0x10  # 7 bytes
    LONG = 0x11   # 20 bytes


# HID++ Feature IDs
class FeatureID(IntEnum):
    ROOT = 0x0000
    FEATURE_SET = 0x0001
    FEATURE_INFO = 0x0002
    DEVICE_NAME = 0x0005
    DEVICE_FRIENDLY_NAME = 0x0007
    HOSTS_INFO = 0x1815
    CHANGE_HOST = 0x1814
    BATTERY_STATUS = 0x1000
    BATTERY_VOLTAGE = 0x1001
    UNIFIED_BATTERY = 0x1004
    REPROG_CONTROLS_V4 = 0x1B04
    ADJUSTABLE_DPI = 0x2201
    HIRES_WHEEL = 0x2121
    SMART_SHIFT = 0x2110
    SMART_SHIFT_ENHANCED = 0x2111  # Used by MX Master 4
    THUMBWHEEL = 0x2150
    GESTURE_2 = 0x19B0
    # MX Master 4 specific features
    MX_HAPTICS = 0x0B4E  # Logitech MX Master 4 haptic feedback (direct feature ID)
    MX_SMART_ACTIONS = 0x9401  # Actions Ring
    MX_PROFILES = 0x9402  # Mouse profiles


# Haptic Patterns for MX Master 4 (patterns 0-14)
class HapticPattern(IntEnum):
    PATTERN_0 = 0   # Subtle tick
    PATTERN_1 = 1   # Light click
    PATTERN_2 = 2   # Medium click
    PATTERN_3 = 3   # Strong click
    PATTERN_4 = 4   # Soft bump
    PATTERN_5 = 5   # Double tap
    PATTERN_6 = 6   # Triple tap
    PATTERN_7 = 7   # Ramp up
    PATTERN_8 = 8   # Ramp down
    PATTERN_9 = 9   # Pulse
    PATTERN_10 = 10  # Strong pulse
    PATTERN_11 = 11  # Alert
    PATTERN_12 = 12  # Success
    PATTERN_13 = 13  # Error
    PATTERN_14 = 14  # Notification

    # Aliases for common patterns
    SOFT_BUMP = 4
    LIGHT_CLICK = 1
    MEDIUM_CLICK = 2
    STRONG_CLICK = 3
    DOUBLE_TAP = 5
    ALERT = 11
    SUCCESS = 12
    ERROR = 13


# Control IDs (CIDs) for MX Master 4 buttons
class ControlID(IntEnum):
    """Button Control IDs - what physical button it is"""
    LEFT_CLICK = 0x0050
    RIGHT_CLICK = 0x0051
    MIDDLE_CLICK = 0x0052
    BACK = 0x0053
    FORWARD = 0x0056
    GESTURE_BUTTON = 0x00C3
    SMART_SHIFT = 0x00C4
    THUMB_WHEEL = 0x01A0
    VIRTUAL_GESTURE = 0x00D7


# Task IDs - what action a button can perform
class TaskID(IntEnum):
    """Actions that buttons can be remapped to"""
    # Mouse actions
    LEFT_CLICK = 0x0038
    RIGHT_CLICK = 0x0039
    MIDDLE_CLICK = 0x003A
    BACK = 0x003C
    FORWARD = 0x003E

    # Special actions
    GESTURE_BUTTON = 0x009C
    SMART_SHIFT = 0x009D

    # Keyboard keys
    KEY_PAGE_UP = 0x0057
    KEY_PAGE_DOWN = 0x0058
    KEY_HOME = 0x0059
    KEY_END = 0x005A
    KEY_ESCAPE = 0x0047
    KEY_ENTER = 0x0048
    KEY_SPACE = 0x0049
    KEY_TAB = 0x004A
    KEY_DELETE = 0x004B
    KEY_BACKSPACE = 0x004C

    # Media controls
    MEDIA_PLAY_PAUSE = 0x0069
    MEDIA_STOP = 0x006A
    MEDIA_NEXT = 0x006B
    MEDIA_PREVIOUS = 0x006C
    MEDIA_VOLUME_UP = 0x006D
    MEDIA_VOLUME_DOWN = 0x006E
    MEDIA_MUTE = 0x006F

    # System actions
    SHOW_DESKTOP = 0x0073
    LOCK_SCREEN = 0x0070
    SCREENSHOT = 0x0071

    # Application switching
    APP_SWITCH = 0x0065  # Alt+Tab equivalent
    APP_EXPOSE = 0x0066  # Mission Control / Overview

    # Disabled
    DISABLED = 0x0000


# Human-readable names for remappable actions
REMAP_ACTIONS = {
    "Default": None,  # Use default action
    "Left Click": TaskID.LEFT_CLICK,
    "Right Click": TaskID.RIGHT_CLICK,
    "Middle Click": TaskID.MIDDLE_CLICK,
    "Back": TaskID.BACK,
    "Forward": TaskID.FORWARD,
    "Gesture Button": TaskID.GESTURE_BUTTON,
    "Smart Shift": TaskID.SMART_SHIFT,
    "Page Up": TaskID.KEY_PAGE_UP,
    "Page Down": TaskID.KEY_PAGE_DOWN,
    "Home": TaskID.KEY_HOME,
    "End": TaskID.KEY_END,
    "Play/Pause": TaskID.MEDIA_PLAY_PAUSE,
    "Next Track": TaskID.MEDIA_NEXT,
    "Previous Track": TaskID.MEDIA_PREVIOUS,
    "Volume Up": TaskID.MEDIA_VOLUME_UP,
    "Volume Down": TaskID.MEDIA_VOLUME_DOWN,
    "Mute": TaskID.MEDIA_MUTE,
    "Show Desktop": TaskID.SHOW_DESKTOP,
    "App Switcher": TaskID.APP_SWITCH,
    "Disabled": TaskID.DISABLED,
}


@dataclass
class DeviceInfo:
    """Information about a connected device"""
    name: str
    product_id: int
    serial: str
    firmware_version: str
    protocol_version: str
    battery_level: int
    battery_charging: bool
    connection_type: str  # "bolt" or "bluetooth"


@dataclass
class Feature:
    """A HID++ feature supported by the device"""
    feature_id: int
    index: int
    feature_type: int
    name: str


class HIDPPError(Exception):
    """HID++ protocol error"""
    ERROR_CODES = {
        0x01: "Unknown",
        0x02: "Invalid argument",
        0x03: "Out of range",
        0x04: "Hardware error",
        0x05: "Logitech internal",
        0x06: "Invalid feature index",
        0x07: "Invalid function ID",
        0x08: "Busy",
        0x09: "Unsupported",
    }

    def __init__(self, code: int):
        self.code = code
        super().__init__(self.ERROR_CODES.get(code, f"Unknown error {code:#04x}"))


class HIDPPDevice:
    """
    Low-level HID++ device communication

    Handles raw HID++ message sending/receiving and feature discovery.
    Supports both direct connections and receiver-based connections.
    """

    REPORT_SHORT = 7
    REPORT_LONG = 20
    TIMEOUT_MS = 500  # 500ms for local HID responses

    def __init__(self, device_path: Optional[str] = None,
                 product_id: Optional[int] = None,
                 device_index: int = 0xFF,
                 use_raw: bool = False):
        self._device = None
        self._raw_fd = None  # File descriptor for raw hidraw access
        self._device_path = device_path
        self._product_id = product_id
        self._device_index = device_index  # 0xFF for direct, 1-6 for receiver
        self._use_raw = use_raw  # Use raw file I/O instead of hidapi
        self._feature_cache: dict[int, int] = {}  # feature_id -> index
        self._lock = threading.Lock()
        self._listeners: list[Callable] = []

    def open(self) -> bool:
        """Open connection to the device"""
        import os

        # If path starts with /dev/hidraw, use raw mode
        if self._device_path and self._device_path.startswith("/dev/hidraw"):
            self._use_raw = True

        if self._use_raw and self._device_path:
            try:
                self._raw_fd = os.open(self._device_path, os.O_RDWR)
                logger.info(f"Opened {self._device_path} in raw mode")
                try:
                    self._discover_features()
                except Exception as e:
                    # Clean up file descriptor if feature discovery fails
                    logger.warning(f"Feature discovery failed: {e}")
                    os.close(self._raw_fd)
                    self._raw_fd = None
                    return False
                return True
            except OSError as e:
                logger.error(f"Failed to open {self._device_path}: {e}")
                self._raw_fd = None
                return False

        # Fall back to hidapi
        if hid is None:
            logger.error("hidapi not installed")
            return False

        try:
            if self._device_path:
                self._device = hid.device()
                path = self._device_path
                if isinstance(path, str):
                    path = path.encode()
                self._device.open_path(path)
            elif self._product_id:
                self._device = hid.device()
                self._device.open(LOGITECH_VID, self._product_id)
            else:
                # Auto-detect MX Master 4
                for pid in MX_MASTER_4_PIDS:
                    try:
                        self._device = hid.device()
                        self._device.open(LOGITECH_VID, pid)
                        self._product_id = pid
                        logger.info(f"Opened {MX_MASTER_4_PIDS[pid]}")
                        break
                    except Exception:
                        continue

            if self._device:
                self._device.set_nonblocking(False)
                self._discover_features()
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to open device: {e}")
            return False

    def close(self):
        """Close device connection"""
        import os

        if self._raw_fd is not None:
            try:
                os.close(self._raw_fd)
            except Exception:
                pass
            self._raw_fd = None

        if self._device:
            self._device.close()
            self._device = None

    @property
    def is_open(self) -> bool:
        """Check if device is open"""
        return self._raw_fd is not None or self._device is not None

    def _discover_features(self):
        """Enumerate available HID++ features"""
        self._feature_cache.clear()

        # ROOT feature is always at index 0
        self._feature_cache[FeatureID.ROOT] = 0

        # Query FEATURE_SET index using ROOT.getFeatureIndex(0x0001)
        # ROOT function 0x00 = getFeatureIndex, takes 16-bit feature ID as args
        try:
            response = self._request(0x00, 0x00, 0x00, 0x01)  # Get index of feature 0x0001
            if response and len(response) >= 1 and response[0] != 0:
                feature_set_index = response[0]
                self._feature_cache[FeatureID.FEATURE_SET] = feature_set_index
                logger.debug(f"FEATURE_SET at index {feature_set_index}")

                # Query feature count using FEATURE_SET.getCount (function 0x00)
                response = self._request(feature_set_index, 0x00)
                if response and len(response) >= 1:
                    feature_count = response[0]
                    logger.info(f"Device has {feature_count} features")

                    # Enumerate all features using FEATURE_SET.getFeatureID (function 0x01)
                    # Index 0 = ROOT, index 1 = first feature, etc.
                    for i in range(feature_count):
                        response = self._request(feature_set_index, 0x01, i)
                        if response and len(response) >= 2:
                            feature_id = (response[0] << 8) | response[1]
                            self._feature_cache[feature_id] = i  # Index matches loop index
                            logger.debug(f"Feature {feature_id:#06x} at index {i}")
            else:
                logger.warning("FEATURE_SET not found, device may have limited HID++ support")

        except Exception as e:
            logger.warning(f"Feature discovery failed: {e}")

    def get_feature_index(self, feature_id: int) -> Optional[int]:
        """Get the index for a feature ID"""
        if feature_id in self._feature_cache:
            return self._feature_cache[feature_id]

        # Query device for feature index using ROOT.getFeatureIndex
        # Function 0x00, args are the 16-bit feature ID (high byte, low byte)
        response = self._request(0x00, 0x00, (feature_id >> 8) & 0xFF, feature_id & 0xFF)
        if response and len(response) >= 1 and response[0] != 0:
            self._feature_cache[feature_id] = response[0]
            return response[0]
        return None

    def has_feature(self, feature_id: int) -> bool:
        """Check if device supports a feature"""
        return self.get_feature_index(feature_id) is not None

    def _request(self, feature_index: int, function_id: int,
                 *args, long_message: bool = False) -> Optional[bytes]:
        """Send HID++ request and wait for response"""
        import os
        import select

        if not self.is_open:
            return None

        with self._lock:
            # Build message
            if long_message or len(args) > 3:
                msg = bytearray(self.REPORT_LONG)
                msg[0] = MessageType.LONG
            else:
                msg = bytearray(self.REPORT_SHORT)
                msg[0] = MessageType.SHORT

            msg[1] = self._device_index  # Device index (0xFF=direct, 1-6=via receiver)
            msg[2] = feature_index
            msg[3] = function_id << 4

            for i, arg in enumerate(args):
                if i + 4 < len(msg):
                    msg[i + 4] = arg if isinstance(arg, int) else arg

            try:
                if self._use_raw and self._raw_fd is not None:
                    # Raw file I/O for hidraw devices
                    os.write(self._raw_fd, bytes(msg))

                    # Wait for response with timeout, filtering by device index
                    # (receiver may send async notifications for other devices)
                    timeout_sec = self.TIMEOUT_MS / 1000.0
                    start_time = time.time()

                    while time.time() - start_time < timeout_sec:
                        remaining = timeout_sec - (time.time() - start_time)
                        if remaining <= 0:
                            break
                        r, _, _ = select.select([self._raw_fd], [], [], remaining)
                        if not r:
                            break

                        response = os.read(self._raw_fd, self.REPORT_LONG)
                        if not response:
                            continue

                        # Check if this response is for our device
                        resp_device = response[1]
                        resp_feature = response[2]

                        # Check for error response (feature index 0xFF)
                        if resp_device == self._device_index and resp_feature == 0xFF:
                            # Error response format:
                            # [report, device, 0xFF, feature, function, error_code, ...]
                            if len(response) >= 6:
                                error_feature = response[3]
                                if error_feature == feature_index:
                                    error_code = response[5]  # Error code is at byte 5
                                    raise HIDPPError(error_code)

                        # Check if response matches our request
                        if resp_device == self._device_index and resp_feature == feature_index:
                            # Return payload (skip 4-byte header)
                            return bytes(response[4:])

                        # Otherwise it's a notification or response for another request
                        logger.debug(f"Skipping message for device {resp_device}, feature {resp_feature}")

                    return None
                else:
                    # hidapi mode
                    self._device.write(bytes(msg))
                    response = self._device.read(self.REPORT_LONG, self.TIMEOUT_MS)

                    if response:
                        # Check for error
                        if response[2] == 0xFF:
                            error_code = response[4]
                            raise HIDPPError(error_code)
                        # Return payload (skip header)
                        return bytes(response[4:])
            except HIDPPError:
                raise
            except Exception as e:
                logger.error(f"Request failed: {e}")

        return None

    def request(self, feature_id: int, function_id: int,
                *args, **kwargs) -> Optional[bytes]:
        """Send request using feature ID (looks up index automatically)"""
        index = self.get_feature_index(feature_id)
        if index is None:
            logger.warning(f"Feature {feature_id:#06x} not supported")
            return None
        return self._request(index, function_id, *args, **kwargs)


class MXMaster4(HIDPPDevice):
    """
    High-level interface for MX Master 4 specific features

    Provides typed methods for all MX Master 4 capabilities including
    haptics, DPI, buttons, scroll, and more.
    """

    def __init__(self, device_path: Optional[str] = None, device_index: int = 0xFF):
        super().__init__(device_path, device_index=device_index)
        self._name = "MX Master 4"
        self._dpi = 1000
        self._haptic_intensity = 2  # 0=Subtle, 1=Low, 2=Medium, 3=High

    # ─────────────────────────────────────────────────────────────────
    # Device Information
    # ─────────────────────────────────────────────────────────────────

    def ping(self) -> bool:
        """Quick single-request liveness probe.

        Used by the window's health-check loop to detect a dropped Bolt
        link without the expense of the full ``get_device_info`` (which
        issues 4+ requests and is much more likely to timeout under
        light contention with the notification-listener thread).
        """
        if not self.is_open:
            return False
        try:
            # ROOT.getProtocolVersion — always present, always cheap.
            response = self._request(0x00, 0x01)
            return response is not None
        except Exception:
            return False

    def get_device_info(self) -> Optional[DeviceInfo]:
        """Get comprehensive device information"""
        if not self.is_open:
            return None

        try:
            # Get device name
            name = self._get_device_name()

            # Get battery status
            battery_level, charging = self._get_battery_status()

            # Get firmware version
            firmware = self._get_firmware_version()

            # Determine connection type based on device index
            # 0xFF = direct (Bluetooth), 1-6 = via receiver (Bolt)
            conn_type = "bolt" if self._device_index != 0xFF else "bluetooth"

            return DeviceInfo(
                name=name or self._name,
                product_id=self._product_id or 0,
                serial="",  # Would need to query
                firmware_version=firmware or "Unknown",
                protocol_version="HID++ 4.5",
                battery_level=battery_level,
                battery_charging=charging,
                connection_type=conn_type,
            )
        except Exception as e:
            logger.error(f"Failed to get device info: {e}")
            return None

    def _get_device_name(self) -> Optional[str]:
        """Query device name"""
        try:
            response = self.request(FeatureID.DEVICE_NAME, 0x00)
            if response:
                name_len = response[0]
                name = b""
                offset = 0
                while len(name) < name_len:
                    response = self.request(FeatureID.DEVICE_NAME, 0x01, offset)
                    if response:
                        name += response[:min(16, name_len - len(name))]
                        offset += 16
                    else:
                        break
                return name.decode("utf-8", errors="ignore").strip("\x00")
        except Exception:
            pass
        return None

    def _get_battery_status(self) -> tuple[int, bool]:
        """Query battery level and charging status"""
        try:
            # Try UNIFIED_BATTERY first (newer devices)
            response = self.request(FeatureID.UNIFIED_BATTERY, 0x00)
            if response and len(response) >= 3:
                level = response[0]
                status = response[2]
                charging = status in (1, 2, 3)  # Charging states
                return level, charging

            # Fallback to BATTERY_STATUS
            response = self.request(FeatureID.BATTERY_STATUS, 0x00)
            if response and len(response) >= 3:
                level = response[0]
                charging = response[2] != 0
                return level, charging
        except Exception:
            pass
        return 0, False

    def _get_firmware_version(self) -> Optional[str]:
        """Query firmware version"""
        try:
            response = self.request(FeatureID.ROOT, 0x01)
            if response and len(response) >= 3:
                return f"{response[0]}.{response[1]}.{response[2]:04x}"
        except Exception:
            pass
        return None

    # ─────────────────────────────────────────────────────────────────
    # Friendly name (user-settable) & Easy-Switch host management
    # ─────────────────────────────────────────────────────────────────

    def get_friendly_name(self) -> Optional[str]:
        """Return the user-settable friendly name (feature 0x0007).

        Falls back to the underlying device name if the feature isn't
        available on this firmware.
        """
        try:
            if not self.has_feature(FeatureID.DEVICE_FRIENDLY_NAME):
                return self._get_device_name()
            response = self.request(FeatureID.DEVICE_FRIENDLY_NAME, 0x00)
            if not response:
                return self._get_device_name()
            name_len = response[0]
            name = b""
            offset = 0
            while len(name) < name_len:
                chunk = self.request(FeatureID.DEVICE_FRIENDLY_NAME, 0x01, offset)
                if not chunk:
                    break
                # Each chunk is [offset_echo, ...14 bytes of name]
                data = chunk[1:]
                remaining = name_len - len(name)
                name += data[:min(len(data), remaining)]
                offset += 14
            return name.decode("utf-8", errors="ignore").strip("\x00") or None
        except Exception as e:
            logger.debug(f"get_friendly_name failed: {e}")
            return self._get_device_name()

    def get_hosts_info(self) -> Optional[dict]:
        """Query Easy-Switch host state (feature 0x1815).

        Returns a dict with total host count, currently-paired host index,
        and a per-host list of {paired, bus_type, name} entries, or None
        if the feature isn't supported.
        """
        try:
            if not self.has_feature(FeatureID.HOSTS_INFO):
                return None
            response = self.request(FeatureID.HOSTS_INFO, 0x00)
            if not response or len(response) < 3:
                return None
            # Layout per HID++ 2.0 feature 0x1815 v1+:
            # [flags, numHosts, currentHost, ...]
            num_hosts = response[1]
            current_host = response[2]
            hosts = []
            for idx in range(num_hosts):
                hr = self.request(FeatureID.HOSTS_INFO, 0x01, idx)
                if not hr or len(hr) < 5:
                    hosts.append(None)
                    continue
                # [hostIdx, paired, name_len, bus_type, page, ...]
                paired = bool(hr[1])
                name_len = hr[2]
                bus_type = hr[3]
                # Optional: query host name via function 0x02
                name = self._get_host_name(idx, name_len)
                hosts.append({
                    "index": idx,
                    "paired": paired,
                    "bus_type": bus_type,
                    "name": name,
                })
            return {
                "num_hosts": num_hosts,
                "current_host": current_host,
                "hosts": hosts,
            }
        except Exception as e:
            logger.debug(f"get_hosts_info failed: {e}")
            return None

    def _get_host_name(self, host_index: int, name_len: int) -> str:
        """Read a host's friendly name via HOSTS_INFO function 0x02."""
        if name_len <= 0:
            return ""
        try:
            name = b""
            offset = 0
            while len(name) < name_len:
                chunk = self.request(FeatureID.HOSTS_INFO, 0x02, host_index, offset)
                if not chunk:
                    break
                # [host_idx_echo, offset_echo, ...name bytes]
                data = chunk[2:]
                remaining = name_len - len(name)
                name += data[:min(len(data), remaining)]
                offset += 14
            return name.decode("utf-8", errors="ignore").strip("\x00")
        except Exception:
            return ""

    def switch_to_host(self, host_index: int) -> bool:
        """Switch the mouse to a different paired host (feature 0x1814)."""
        try:
            if not self.has_feature(FeatureID.CHANGE_HOST):
                return False
            # Function 0x01 = setHost(host_index)
            response = self.request(FeatureID.CHANGE_HOST, 0x01, host_index)
            if response is not None:
                logger.info(f"Switched to host {host_index}")
                return True
        except Exception as e:
            logger.error(f"switch_to_host failed: {e}")
        return False

    # ─────────────────────────────────────────────────────────────────
    # Haptic Feedback
    # ─────────────────────────────────────────────────────────────────

    def trigger_haptic(self, pattern: HapticPattern = HapticPattern.MEDIUM_CLICK,
                       intensity: Optional[int] = None) -> bool:
        """
        Trigger a haptic feedback pattern

        The MX Master 4 uses a direct feature ID protocol (0x0B4E) rather than
        the standard HID++ feature index lookup.

        Args:
            pattern: The haptic pattern to play (0-14, see HapticPattern enum)
            intensity: Not used on MX Master 4 (patterns have fixed intensity)

        Returns:
            True if successful
        """
        import os
        import struct
        import select

        if not self.is_open:
            return False

        try:
            # MX Master 4 uses direct feature ID protocol for haptics
            # Format: [report_id][device_index][feature_id (2 bytes)][pattern][0][0]
            HAPTIC_FEATURE_ID = 0x0B4E
            pattern_value = pattern.value if isinstance(pattern, HapticPattern) else int(pattern)

            data = struct.pack('>3s', bytes([pattern_value, 0, 0]))
            msg = struct.pack('>BBH', 0x10, self._device_index, HAPTIC_FEATURE_ID) + data

            # Serialize with _request so the notification listener and
            # other HID++ calls can't race on the hidraw fd.
            with self._lock:
                if self._use_raw and self._raw_fd is not None:
                    os.write(self._raw_fd, msg)
                    r, _, _ = select.select([self._raw_fd], [], [], 0.5)
                    if r:
                        response = os.read(self._raw_fd, 20)
                        if len(response) > 2 and response[2] == 0xFF:
                            logger.error(f"Haptic error: {response[4]:#04x}")
                            return False
                        return True
                    return False
                elif self._device:
                    self._device.write(bytes(msg))
                    response = self._device.read(20, 500)
                    if response and response[2] != 0xFF:
                        return True
                    return False

            return False
        except Exception as e:
            logger.error(f"Failed to trigger haptic: {e}")
            return False

    def set_haptic_intensity(self, intensity: int) -> bool:
        """
        Set default haptic intensity

        Args:
            intensity: 0=Subtle, 1=Low, 2=Medium, 3=High

        Returns:
            True if successful
        """
        if not 0 <= intensity <= 3:
            raise ValueError("Intensity must be 0-3")

        try:
            response = self.request(
                FeatureID.MX_HAPTICS,
                0x01,  # Function: Set intensity
                intensity,
            )
            if response is not None:
                self._haptic_intensity = intensity
                return True
        except Exception as e:
            logger.error(f"Failed to set intensity: {e}")
        return False

    def get_haptic_intensity(self) -> int:
        """Get current haptic intensity setting"""
        try:
            response = self.request(FeatureID.MX_HAPTICS, 0x02)  # Get intensity
            if response and len(response) >= 1:
                self._haptic_intensity = response[0]
        except Exception:
            pass
        return self._haptic_intensity

    # ─────────────────────────────────────────────────────────────────
    # DPI / Pointer Settings
    # ─────────────────────────────────────────────────────────────────

    def get_dpi(self) -> int:
        """Get current DPI setting"""
        # Note: Reading DPI from this device returns a fixed config value,
        # not the current active DPI. We return the cached value instead.
        if self._dpi == 1000:  # Default, try to read once
            try:
                # Try reading - response format varies by device
                response = self.request(FeatureID.ADJUSTABLE_DPI, 0x01, 0)
                if response and len(response) >= 3:
                    # Try parsing as big-endian DPI at bytes 1-2
                    dpi = (response[1] << 8) | response[2]
                    if 200 <= dpi <= 8000:
                        self._dpi = dpi
            except Exception:
                pass
        return self._dpi

    def set_dpi(self, dpi: int) -> bool:
        """
        Set pointer DPI

        Args:
            dpi: DPI value (200-8000)

        Returns:
            True if successful
        """
        dpi = max(200, min(8000, dpi))

        try:
            # Function 0x03 = setSensorDPI(sensor_index, dpi_msb, dpi_lsb)
            response = self.request(
                FeatureID.ADJUSTABLE_DPI,
                0x03,
                0,  # Sensor index
                (dpi >> 8) & 0xFF,
                dpi & 0xFF,
            )
            if response is not None:
                # Response echoes back: sensor, dpi_msb, dpi_lsb
                self._dpi = dpi
                logger.info(f"DPI set to {dpi}")
                return True
        except Exception as e:
            logger.error(f"Failed to set DPI: {e}")
        return False

    def get_dpi_list(self) -> list[int]:
        """Get list of available DPI presets"""
        try:
            response = self.request(FeatureID.ADJUSTABLE_DPI, 0x02)
            if response and len(response) >= 1:
                count = response[0]
                dpis = []
                for i in range(count):
                    # Each DPI entry is 2 bytes, starting at offset 1
                    offset = 1 + i * 2
                    if offset + 1 < len(response):
                        dpi = (response[offset] << 8) | response[offset + 1]
                        dpis.append(dpi)
                if dpis:
                    return dpis
        except Exception:
            pass
        # Default presets
        return [400, 800, 1000, 1600, 2000, 4000, 8000]

    # ─────────────────────────────────────────────────────────────────
    # Scroll Wheel
    # ─────────────────────────────────────────────────────────────────

    def _get_smartshift_feature(self) -> Optional[int]:
        """Get the SmartShift feature ID (enhanced or legacy)"""
        if self.has_feature(FeatureID.SMART_SHIFT_ENHANCED):
            return FeatureID.SMART_SHIFT_ENHANCED
        if self.has_feature(FeatureID.SMART_SHIFT):
            return FeatureID.SMART_SHIFT
        return None

    def get_smartshift_status(self) -> tuple[bool, int]:
        """
        Get SmartShift status

        Returns:
            Tuple of (enabled, threshold) where threshold is 1-255
        """
        feature = self._get_smartshift_feature()
        if not feature:
            return True, 25

        try:
            # Function 0x00 = getRatchetControlMode
            # Response for SMART_SHIFT_ENHANCED:
            #   byte 0: wheel_mode (1=ratchet, 2=freespin)
            #   byte 1: auto_disengage threshold (1-255, 0=disabled)
            #   byte 2: default_auto_disengage
            response = self.request(feature, 0x00)
            if response and len(response) >= 2:
                wheel_mode = response[0]
                auto_disengage = response[1]
                # SmartShift is "enabled" if auto_disengage > 0
                enabled = auto_disengage > 0
                threshold = auto_disengage if auto_disengage > 0 else 25
                return enabled, threshold
        except Exception:
            pass
        return True, 25

    def set_smartshift(self, enabled: bool, threshold: int = 25) -> bool:
        """
        Configure SmartShift (auto-switching between ratchet and freewheel)

        Args:
            enabled: Enable SmartShift auto-switching
            threshold: Sensitivity threshold (1-255, higher = easier to trigger)

        Returns:
            True if successful
        """
        feature = self._get_smartshift_feature()
        if not feature:
            logger.warning("Device does not support SmartShift")
            return False

        threshold = max(1, min(255, threshold))

        try:
            # Function 0x01 = setRatchetControlMode
            # Args: wheel_mode, auto_disengage
            # wheel_mode: 1=ratchet, 2=freespin
            # auto_disengage: 0=disabled, 1-255=threshold
            response = self.request(
                feature,
                0x01,
                1,  # wheel_mode = ratchet (let SmartShift control it)
                threshold if enabled else 0,  # 0 disables auto-switch
            )
            return response is not None
        except Exception as e:
            logger.error(f"Failed to set SmartShift: {e}")
        return False

    def set_hires_scroll(self, enabled: bool, invert: bool = False) -> bool:
        """
        Configure high-resolution scrolling

        Args:
            enabled: Enable hi-res scroll
            invert: Invert scroll direction

        Returns:
            True if successful
        """
        try:
            flags = 0
            if enabled:
                flags |= 0x01
            if invert:
                flags |= 0x02

            response = self.request(FeatureID.HIRES_WHEEL, 0x01, flags)
            return response is not None
        except Exception as e:
            logger.error(f"Failed to set hi-res scroll: {e}")
        return False

    # ─────────────────────────────────────────────────────────────────
    # Button Mapping
    # ─────────────────────────────────────────────────────────────────

    def get_button_count(self) -> int:
        """Get number of programmable buttons"""
        try:
            response = self.request(FeatureID.REPROG_CONTROLS_V4, 0x00)
            if response and len(response) >= 1:
                return response[0]
        except Exception:
            pass
        return 8  # MX Master 4 default

    def get_button_info(self, button_index: int) -> Optional[dict]:
        """
        Get information about a specific button

        Args:
            button_index: Button index (0-7)

        Returns:
            Dict with button info or None
        """
        try:
            response = self.request(
                FeatureID.REPROG_CONTROLS_V4,
                0x01,
                button_index,
            )
            if response and len(response) >= 5:
                cid = (response[0] << 8) | response[1]
                tid = (response[2] << 8) | response[3]
                flags = response[4]

                return {
                    "index": button_index,
                    "control_id": cid,
                    "task_id": tid,
                    "flags": flags,
                    "remappable": bool(flags & 0x10),
                    "divertable": bool(flags & 0x20),
                }
        except Exception:
            pass
        return None

    def remap_button(self, cid: int, remap_cid: int) -> bool:
        """
        Remap a button to a different action using Control IDs

        Args:
            cid: Control ID of the button to remap (e.g., ControlID.BACK)
            remap_cid: Control ID of the action to map to (e.g., ControlID.FORWARD)
                      Use the same CID as original to reset to default

        Returns:
            True if successful
        """
        import struct

        try:
            # Function 3: setControlReporting
            # Format: CID (2 bytes BE) + flags (1 byte) + remap_cid (2 bytes BE)
            # Flags: 0x01 = remap valid, 0x00 = reset to default
            flags = 0x01 if remap_cid != cid else 0x00

            packet = struct.pack('>HBH', cid, flags, remap_cid)

            response = self.request(
                FeatureID.REPROG_CONTROLS_V4,
                0x03,  # setControlReporting
                *packet,
            )
            if response:
                logger.info(f"Remapped CID 0x{cid:04X} to 0x{remap_cid:04X}")
                return True
        except Exception as e:
            logger.error(f"Failed to remap button: {e}")
        return False

    def get_button_remap(self, cid: int) -> Optional[int]:
        """
        Get the current remap target for a button

        Args:
            cid: Control ID of the button

        Returns:
            The remap target CID, or None if error
        """
        try:
            # Function 2: getControlReporting(cid)
            response = self.request(
                FeatureID.REPROG_CONTROLS_V4,
                0x02,  # getControlReporting
                (cid >> 8) & 0xFF,
                cid & 0xFF,
            )
            if response and len(response) >= 6:
                # Response: cid (2), flags (2), remap_cid (2)
                remap_cid = (response[4] << 8) | response[5]
                return remap_cid
        except Exception as e:
            logger.error(f"Failed to get button remap: {e}")
        return None

    def reset_button(self, cid: int) -> bool:
        """
        Reset a button to its default action

        Args:
            cid: Control ID of the button to reset

        Returns:
            True if successful
        """
        return self.remap_button(cid, cid)  # Remap to itself = reset

    # ─────────────────────────────────────────────────────────────────
    # Button Diversion (for gesture button)
    # ─────────────────────────────────────────────────────────────────

    def divert_button(self, cid: int, diverted: bool = True) -> bool:
        """
        Divert a button so its events come through HID++ instead of the OS.

        When diverted, button presses won't trigger any OS-level input events,
        they'll only be received through HID++ notifications. This is essential
        for the gesture button to work without affecting text selection, etc.

        Args:
            cid: Control ID of the button (e.g., ControlID.GESTURE_BUTTON)
            diverted: True to divert, False to restore normal behavior

        Returns:
            True if successful
        """
        try:
            # Function 0x03: setControlReporting
            # Format: CID (2 bytes BE) + flags (1 byte) + remap_cid (2 bytes BE)
            # Flags byte:
            #   bit 0: divert (send to host SW instead of HID)
            #   bit 1: dvalid (divert flag is valid)
            #   bit 2: persist
            #   bit 3: pvalid (persist flag is valid)
            #   bit 4: forceRawXY
            #   bit 5: rawXYValid

            # Set divert + dvalid flags (0x03 = enable divert, 0x02 = disable divert but flag valid)
            flags = 0x03 if diverted else 0x02

            # Send: CID_high, CID_low, flags, remap_high, remap_low
            cid_high = (cid >> 8) & 0xFF
            cid_low = cid & 0xFF

            response = self.request(
                FeatureID.REPROG_CONTROLS_V4,
                0x03,  # setControlReporting
                cid_high, cid_low, flags, cid_high, cid_low,  # remap to itself
            )
            if response is not None:
                logger.info(f"Button CID 0x{cid:04X} divert={'enabled' if diverted else 'disabled'}")
                return True
            else:
                logger.debug(f"Button divert failed: no response for CID 0x{cid:04X}")
        except Exception as e:
            logger.error(f"Failed to divert button CID 0x{cid:04X}: {e}")
        return False

    def start_notification_listener(self, callback: Callable[[int, int, bytes], None]) -> bool:
        """
        Start listening for HID++ notifications (for diverted buttons).

        Args:
            callback: Function called with (feature_index, function_id, payload)
                     for each notification received

        Returns:
            True if listener started
        """
        if hasattr(self, '_notification_thread') and self._notification_thread and self._notification_thread.is_alive():
            logger.debug("Notification listener already running")
            return True

        self._notification_callback = callback
        self._notification_running = True
        self._notification_thread = threading.Thread(
            target=self._notification_loop,
            daemon=True,
            name="HIDPPNotificationListener"
        )
        self._notification_thread.start()
        logger.info("HID++ notification listener started")
        return True

    def stop_notification_listener(self):
        """Stop the notification listener"""
        self._notification_running = False
        if hasattr(self, '_notification_thread') and self._notification_thread:
            self._notification_thread.join(timeout=1.0)
            self._notification_thread = None
        logger.info("HID++ notification listener stopped")

    def _notification_loop(self):
        """Background thread that listens for HID++ notifications.

        The hidraw fd is shared with :meth:`_request`, so reads must be
        serialized under ``self._lock`` — otherwise an in-flight request
        response can be stolen by this thread (or vice versa), causing
        spurious timeouts that falsely mark the device dead.
        """
        import os
        import select

        if not self.is_open:
            return

        logger.debug(f"Notification loop started, device_index={self._device_index}")

        while self._notification_running:
            try:
                if self._use_raw and self._raw_fd is not None:
                    # select without the lock — only acquire when there's data
                    r, _, _ = select.select([self._raw_fd], [], [], 0.1)
                    if not r:
                        continue

                    # Take the lock so a concurrent _request can't race us
                    # reading the same byte stream. Use a non-blocking
                    # acquire: if a request is in flight it'll consume the
                    # response itself, and we'll pick up genuine async
                    # notifications on a later iteration.
                    if not self._lock.acquire(blocking=False):
                        # Give up this tick; loop back and try again
                        time.sleep(0.005)
                        continue
                    try:
                        # Re-check there's still data after acquiring
                        r2, _, _ = select.select([self._raw_fd], [], [], 0)
                        if not r2:
                            continue
                        data = os.read(self._raw_fd, self.REPORT_LONG)
                    finally:
                        self._lock.release()
                    if not data:
                        continue

                    # Parse notification
                    # [report_type, device_index, feature_index, function_sw, ...]
                    if len(data) < 4:
                        continue

                    report_type = data[0]
                    device_idx = data[1]
                    feature_idx = data[2]
                    function_sw = data[3]

                    logger.debug(f"HID++ notification: dev={device_idx} feat={feature_idx} func_sw={function_sw:#04x}")

                    # Check if this is for our device
                    if device_idx != self._device_index:
                        continue

                    # Extract function ID (upper nibble) and SW ID (lower nibble)
                    function_id = (function_sw >> 4) & 0x0F
                    sw_id = function_sw & 0x0F

                    # Payload is the rest
                    payload = bytes(data[4:])

                    # Call the callback
                    if hasattr(self, '_notification_callback') and self._notification_callback:
                        try:
                            self._notification_callback(feature_idx, function_id, payload)
                        except Exception as e:
                            logger.error(f"Notification callback error: {e}")

                elif self._device:
                    # hidapi mode - blocking read with short timeout
                    data = self._device.read(self.REPORT_LONG, timeout_ms=100)
                    if data:
                        feature_idx = data[2]
                        function_sw = data[3]
                        function_id = (function_sw >> 4) & 0x0F
                        payload = bytes(data[4:])

                        if hasattr(self, '_notification_callback') and self._notification_callback:
                            try:
                                self._notification_callback(feature_idx, function_id, payload)
                            except Exception as e:
                                logger.error(f"Notification callback error: {e}")

            except Exception as e:
                if self._notification_running:
                    logger.debug(f"Notification loop error: {e}")
                time.sleep(0.1)

        logger.debug("Notification loop ended")


def _find_hidraw_for_receiver(product_id: int, interface: int = 2) -> Optional[str]:
    """
    Find the hidraw device path for a Logitech receiver.

    Args:
        product_id: The USB product ID (e.g., 0xC548 for Bolt)
        interface: The USB interface number (default 2 for HID++)

    Returns:
        Path like '/dev/hidraw3' or None if not found
    """
    import os
    import glob

    target_hid_id = f"0003:0000046D:{product_id:08X}".upper()

    for hidraw in glob.glob("/sys/class/hidraw/hidraw*"):
        try:
            uevent_path = os.path.join(hidraw, "device", "uevent")
            if not os.path.exists(uevent_path):
                continue

            with open(uevent_path) as f:
                uevent = f.read()

            # Check HID_ID matches
            if target_hid_id not in uevent.upper():
                continue

            # Check HID_PHYS for interface number (e.g., "input2" for interface 2)
            for line in uevent.split("\n"):
                if line.startswith("HID_PHYS="):
                    if f"input{interface}" in line:
                        hidraw_name = os.path.basename(hidraw)
                        return f"/dev/{hidraw_name}"
        except Exception:
            continue

    return None


def _query_bolt_receiver(hidraw_path: str) -> list[dict]:
    """
    Query a Bolt receiver for paired devices using HID++ 1.0 registers.

    Args:
        hidraw_path: Path to the hidraw device (e.g., '/dev/hidraw3')

    Returns:
        List of dicts with device info for each paired device
    """
    import os
    import select

    devices = []
    fd = None

    try:
        fd = os.open(hidraw_path, os.O_RDWR)
    except OSError as e:
        logger.debug(f"Cannot open {hidraw_path}: {e}")
        return []

    def send_recv(msg, timeout=0.5):
        try:
            os.write(fd, msg)
            r, _, _ = select.select([fd], [], [], timeout)
            if r:
                return os.read(fd, 64)
        except Exception:
            pass
        return None

    try:
        # Scan device slots 1-6 using BOLT_PAIRING_INFORMATION
        # Long register read (0x83) of register 0xB5 with param 0x5N
        for slot in range(1, 7):
            param = 0x50 + slot  # BOLT_PAIRING_INFORMATION + slot
            msg = bytes([0x10, 0xFF, 0x83, 0xB5, param, 0x00, 0x00])
            resp = send_recv(msg)

            if not resp or len(resp) < 12:
                continue

            # Check for error response
            if resp[2] == 0x8f:
                continue

            # Parse pairing info (data starts after 5-byte header)
            if len(resp) < 12:
                continue
            data = resp[5:]
            if len(data) < 7:
                continue

            device_kind = data[0] & 0x0F
            wpid = (data[2] << 8) | data[1]  # Little endian
            device_serial = data[3:7].hex().upper()

            # Check if this is an MX Master 4
            if wpid in MX_MASTER_4_PIDS:
                devices.append({
                    "slot": slot,
                    "wpid": wpid,
                    "kind": device_kind,
                    "serial": device_serial,
                    "name": MX_MASTER_4_PIDS[wpid],
                })
                logger.info(f"Found {MX_MASTER_4_PIDS[wpid]} at slot {slot}")

    except Exception as e:
        logger.debug(f"Error querying Bolt receiver: {e}")
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass

    return devices


def find_mx_master_4() -> Optional[dict]:
    """
    Find connected MX Master 4 devices

    Searches for:
    1. Direct Bluetooth connections
    2. Devices connected via Bolt receiver

    Returns:
        Dict with device info or None if not found
    """
    if hid is None:
        return None

    # First, check for direct connections (Bluetooth)
    for device in hid.enumerate(LOGITECH_VID):
        if device["product_id"] in MX_MASTER_4_PIDS:
            return {
                "path": device["path"],
                "product_id": device["product_id"],
                "product_string": device.get("product_string", MX_MASTER_4_PIDS[device["product_id"]]),
                "serial": device.get("serial_number", ""),
                "interface": device.get("interface_number", -1),
                "via_receiver": False,
                "device_index": 0xFF,  # Direct connection
            }

    # Check for Bolt receiver (interface 2 is HID++)
    bolt_hidraw = _find_hidraw_for_receiver(0xC548, interface=2)
    if bolt_hidraw:
        logger.info(f"Found Bolt receiver at {bolt_hidraw}")
        paired_devices = _query_bolt_receiver(bolt_hidraw)

        for dev in paired_devices:
            if dev["wpid"] in MX_MASTER_4_PIDS:
                return {
                    "path": bolt_hidraw,
                    "product_id": dev["wpid"],
                    "product_string": dev["name"],
                    "serial": dev["serial"],
                    "interface": 2,
                    "via_receiver": True,
                    "receiver_path": bolt_hidraw,
                    "device_index": dev["slot"],
                }

    # Check for Unifying receiver as fallback
    unifying_hidraw = _find_hidraw_for_receiver(0xC52B, interface=2)
    if unifying_hidraw:
        logger.info(f"Found Unifying receiver at {unifying_hidraw}")
        # Unifying uses different register format - would need separate handling

    return None


def list_logitech_devices() -> list[dict]:
    """List all connected Logitech HID devices"""
    if hid is None:
        return []

    devices = []
    for device in hid.enumerate(LOGITECH_VID):
        devices.append({
            "path": device["path"],
            "product_id": device["product_id"],
            "product_string": device.get("product_string", "Unknown"),
            "serial": device.get("serial_number", ""),
            "interface": device.get("interface_number", -1),
        })
    return devices
