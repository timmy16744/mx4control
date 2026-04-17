"""Configuration schema.

Every field has a default so partial config files still load. The
dataclass hierarchy is the source of truth — TOML serialization is
derived from it, not hand-maintained.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


CONFIG_VERSION = 2


@dataclass
class HapticSettings:
    enabled: bool = True
    intensity: int = 2                 # 0=Subtle .. 3=High (device-level)
    ring_boundary_pattern: int = 1     # played when gesture crosses a segment
    ring_confirm_pattern: int = 2      # played on release-in-segment
    ring_cancel_pattern: int = 0       # played on release-in-center
    notification_enabled: bool = False
    notification_pattern: int = 5
    scroll_end_enabled: bool = False
    scroll_end_pattern: int = 3


@dataclass
class PointerSettings:
    dpi: int = 1000


@dataclass
class ScrollSettings:
    smartshift_enabled: bool = True
    smartshift_threshold: int = 15
    hires_enabled: bool = True
    invert_vertical: bool = False
    invert_horizontal: bool = False


@dataclass
class ThumbWheelSettings:
    # When True the daemon diverts the thumb wheel and handles events in
    # software — lets us fire custom actions on tilt-scroll (e.g. tab
    # cycling) instead of firmware-default horizontal scroll.
    diverted: bool = False
    invert: bool = False


@dataclass
class ActionSlice:
    """One of eight segments on the Actions Ring."""
    label: str = ""
    icon: str = ""
    action_type: str = "keystroke"    # keystroke | command | application | disabled
    action_data: str = ""


@dataclass
class RingProfile:
    """Actions Ring profile for a specific application (or 'default')."""
    app_id: str = "default"
    app_name: str = "Default"
    app_icon: str = "application-x-executable"
    slices: list[ActionSlice] = field(default_factory=list)


@dataclass
class DaemonSettings:
    # Low-latency poll interval for the HID++ reader (seconds).
    reader_timeout: float = 0.2
    # How long we hold the evdev grab after release before restoring
    # movement to the compositor — keeps late movement events from
    # pulling the cursor after a gesture.
    cursor_freeze_tail_ms: int = 30
    # Whether to automatically open the gesture button on startup.
    autostart_gesture: bool = True


@dataclass
class Config:
    version: int = CONFIG_VERSION
    haptics: HapticSettings = field(default_factory=HapticSettings)
    pointer: PointerSettings = field(default_factory=PointerSettings)
    scroll: ScrollSettings = field(default_factory=ScrollSettings)
    thumbwheel: ThumbWheelSettings = field(default_factory=ThumbWheelSettings)
    daemon: DaemonSettings = field(default_factory=DaemonSettings)
    # Global / default ring + per-app overrides keyed by app_id
    ring_profiles: dict[str, RingProfile] = field(default_factory=dict)

    def __post_init__(self):
        if "default" not in self.ring_profiles:
            self.ring_profiles["default"] = _default_ring()


def _default_ring() -> RingProfile:
    return RingProfile(
        app_id="default",
        app_name="Default",
        app_icon="application-x-executable",
        slices=[
            ActionSlice("Undo",       "edit-undo",      "keystroke", "ctrl+z"),
            ActionSlice("Redo",       "edit-redo",      "keystroke", "ctrl+shift+z"),
            ActionSlice("Copy",       "edit-copy",      "keystroke", "ctrl+c"),
            ActionSlice("Paste",      "edit-paste",     "keystroke", "ctrl+v"),
            ActionSlice("Cut",        "edit-cut",       "keystroke", "ctrl+x"),
            ActionSlice("Save",       "document-save",  "keystroke", "ctrl+s"),
            ActionSlice("Find",       "edit-find",      "keystroke", "ctrl+f"),
            ActionSlice("Screenshot", "camera-photo",   "command",   "hyprshot -m region"),
        ],
    )
