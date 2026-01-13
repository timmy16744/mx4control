"""
MX4Control Core Module

Low-level device communication and protocol handling.
"""

from .hidpp import (
    HIDPPDevice,
    MXMaster4,
    FeatureID,
    HapticPattern,
    DeviceInfo,
    HIDPPError,
    find_mx_master_4,
    list_logitech_devices,
    LOGITECH_VID,
    MX_MASTER_4_PIDS,
)

__all__ = [
    "HIDPPDevice",
    "MXMaster4",
    "FeatureID",
    "HapticPattern",
    "DeviceInfo",
    "HIDPPError",
    "find_mx_master_4",
    "list_logitech_devices",
    "LOGITECH_VID",
    "MX_MASTER_4_PIDS",
]
