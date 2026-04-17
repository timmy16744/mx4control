"""HID++ 2.0 protocol layer for the MX Master 4."""

from .features import FeatureID, ControlID, HapticPattern, TaskID, HIDPPError
from .dispatcher import HIDPPDispatcher, MessageType
from .device import MXMaster4, DeviceInfo
from .discovery import find_mx_master_4, LOGITECH_VID, MX_MASTER_4_PIDS

__all__ = [
    "FeatureID",
    "ControlID",
    "HapticPattern",
    "TaskID",
    "HIDPPError",
    "HIDPPDispatcher",
    "MessageType",
    "MXMaster4",
    "DeviceInfo",
    "find_mx_master_4",
    "LOGITECH_VID",
    "MX_MASTER_4_PIDS",
]
