"""HID++ 2.0 feature/control/task identifiers.

Feature IDs come from the HID++ 2.0 specification and from the Solaar
project's reverse-engineering notes. Those prefixed with ``MX_`` are
MX-series-specific and only a subset are reachable from user space.

The MX Master 4 firmware (4.5.0000) exposes 45 features, enumerated live
at startup via FEATURE_SET. Live probing against the real device is
checked into ``tests/fixtures/mx4_master4_4.5.0000.json``.
"""

from enum import IntEnum


# ───────────────────────────── Vendor/Product ─────────────────────────────

LOGITECH_VID = 0x046D

# MX Master 4 product IDs (both cold-pair over Bolt and direct BT pairing)
MX_MASTER_4_PIDS = {
    0xB042: "MX Master 4 (Bolt)",
    0x4107: "MX Master 4 (Bluetooth)",
}

RECEIVER_PIDS = {
    0xC548: "Bolt Receiver",
    0xC52B: "Unifying Receiver",
}


# ───────────────────────────── Message types ─────────────────────────────

class MessageType(IntEnum):
    """HID++ message types selected by the first byte (report ID)."""
    SHORT = 0x10  # 7 bytes total
    LONG = 0x11   # 20 bytes total


# ───────────────────────────── Feature IDs ───────────────────────────────

class FeatureID(IntEnum):
    """HID++ 2.0 feature identifiers.

    Only features we *use* are listed here. The full enumeration lives
    in the test fixture; unknown features are kept as raw integers by
    the dispatcher so we don't need to version this enum on every
    firmware revision.
    """

    # Core / introspection
    ROOT = 0x0000
    FEATURE_SET = 0x0001
    DEVICE_FW_VERSION = 0x0003
    DEVICE_NAME = 0x0005
    DEVICE_FRIENDLY_NAME = 0x0007
    CONFIG_CHANGE = 0x0020

    # Power
    UNIFIED_BATTERY = 0x1004

    # Host management (Easy-Switch)
    CHANGE_HOST = 0x1814
    HOSTS_INFO = 0x1815

    # Hidden features unlock (kept for documentation — doesn't unlock
    # MX_SMART_ACTIONS as confirmed by the RE probe)
    ENABLE_HIDDEN_FEATURES = 0x1E00

    # Input
    REPROG_CONTROLS_V4 = 0x1B04
    GESTURE_2 = 0x19B0

    # Pointer & scroll
    SMART_SHIFT_ENHANCED = 0x2111
    SMART_SHIFT = 0x2110
    HIRES_WHEEL = 0x2121
    THUMBWHEEL = 0x2150
    ADJUSTABLE_DPI = 0x2201

    # Telemetry
    XY_STATS = 0x2250

    # MX Master 4 specific (firmware-locked — require Logi Options+ auth)
    MX_SMART_ACTIONS = 0x9401
    MX_PROFILES = 0x9402

    # Direct-address haptic (doesn't appear in the feature list but the
    # device responds to this "magic" feature ID for vibration triggers)
    MX_HAPTICS_DIRECT = 0x0B4E


# ───────────────────────────── Control IDs ───────────────────────────────

class ControlID(IntEnum):
    """Physical button identifiers."""
    LEFT_CLICK = 0x0050
    RIGHT_CLICK = 0x0051
    MIDDLE_CLICK = 0x0052
    BACK = 0x0053
    FORWARD = 0x0056
    GESTURE_BUTTON = 0x00C3
    SMART_SHIFT = 0x00C4
    THUMB_WHEEL = 0x01A0
    VIRTUAL_GESTURE = 0x00D7


# Divertable subset of ControlID (from the live probe's flags=0x0031)
DIVERTABLE_CONTROLS = frozenset({
    ControlID.MIDDLE_CLICK,
    ControlID.BACK,
    ControlID.FORWARD,
    ControlID.GESTURE_BUTTON,
    ControlID.SMART_SHIFT,
    ControlID.THUMB_WHEEL,
    ControlID.VIRTUAL_GESTURE,
})


# ───────────────────────────── Task IDs ──────────────────────────────────

class TaskID(IntEnum):
    """Logical actions that physical controls can be remapped to."""
    LEFT_CLICK = 0x0038
    RIGHT_CLICK = 0x0039
    MIDDLE_CLICK = 0x003A
    BACK = 0x003C
    FORWARD = 0x003E
    GESTURE_BUTTON = 0x009C
    SMART_SHIFT = 0x009D
    DISABLED = 0x0000


# ───────────────────────────── Haptic patterns ───────────────────────────

class HapticPattern(IntEnum):
    """Indices into the MX Master 4's built-in haptic waveform bank (0–14).

    Exposed via the ``MX_HAPTICS_DIRECT`` magic feature. Pattern 1 has the
    crispest feel for segment-crossing ticks on the Actions Ring; pattern
    2 is the default confirmation click; pattern 11 is an "alert".
    """
    SUBTLE_TICK = 0
    LIGHT_CLICK = 1
    MEDIUM_CLICK = 2
    STRONG_CLICK = 3
    SOFT_BUMP = 4
    DOUBLE_TAP = 5
    TRIPLE_TAP = 6
    RAMP_UP = 7
    RAMP_DOWN = 8
    PULSE = 9
    STRONG_PULSE = 10
    ALERT = 11
    SUCCESS = 12
    ERROR = 13
    NOTIFICATION = 14


# ───────────────────────────── Error type ────────────────────────────────

class HIDPPError(Exception):
    """Raised when the device returns an error response.

    Error codes per HID++ 2.0 spec.
    """

    CODES = {
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

    def __init__(self, code: int, feature: int = 0, function: int = 0):
        self.code = code
        self.feature = feature
        self.function = function
        super().__init__(
            f"{self.CODES.get(code, f'Unknown {code:#04x}')}"
            f" (feat=0x{feature:04X} fn={function:#04x})"
        )


# ───────────────────────────── Flag bitmasks ─────────────────────────────

# REPROG_CONTROLS_V4 key-info flags (byte 4 of getCidInfo response)
class KeyFlag(IntEnum):
    MSE = 0x01
    FKEY = 0x02
    HOTKEY = 0x04
    FN_SENSITIVE = 0x08
    REMAPPABLE = 0x10
    DIVERTABLE = 0x20
    PERSISTENTLY_DIVERTABLE = 0x40


# REPROG_CONTROLS_V4 mapping flags for setCidReporting
class MappingFlag(IntEnum):
    DIVERTED = 0x01
    DIVERTED_VALID = 0x02
    PERSISTENTLY_DIVERTED = 0x04
    PERSISTENTLY_DIVERTED_VALID = 0x08
    RAW_XY_DIVERTED = 0x10
    RAW_XY_DIVERTED_VALID = 0x20
