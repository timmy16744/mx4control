"""TOML-backed configuration with schema and migrations."""

from .schema import (
    Config, HapticSettings, PointerSettings, ScrollSettings,
    ActionSlice, RingProfile, ThumbWheelSettings, DaemonSettings,
)
from .store import ConfigStore

__all__ = [
    "Config", "HapticSettings", "PointerSettings", "ScrollSettings",
    "ActionSlice", "RingProfile", "ThumbWheelSettings", "DaemonSettings",
    "ConfigStore",
]
