"""HID++ 2.0 protocol layer for the MX Master 4."""

from .features import (
    BusType,
    ControlID,
    FeatureID,
    HIDPPError,
    HapticPattern,
    HiresFlag,
    TaskID,
    WheelMode,
)
from .dispatcher import HIDPPDispatcher, MessageType
from .device import (
    ButtonInfo,
    DeviceInfo,
    ForceButtonInfo,
    HapticCapabilities,
    HostInfo,
    HostsSummary,
    MXMaster4,
    SmartShiftState,
)
from .discovery import find_mx_master_4, LOGITECH_VID, MX_MASTER_4_PIDS

__all__ = [
    "BusType",
    "ButtonInfo",
    "ControlID",
    "DeviceInfo",
    "FeatureID",
    "ForceButtonInfo",
    "HIDPPDispatcher",
    "HIDPPError",
    "HapticCapabilities",
    "HapticPattern",
    "HiresFlag",
    "HostInfo",
    "HostsSummary",
    "LOGITECH_VID",
    "MXMaster4",
    "MX_MASTER_4_PIDS",
    "MessageType",
    "SmartShiftState",
    "TaskID",
    "WheelMode",
    "find_mx_master_4",
]
