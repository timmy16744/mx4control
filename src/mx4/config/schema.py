"""Configuration schema.

Every field has a default so partial config files still load. The
dataclass hierarchy is the source of truth — TOML serialization is
derived from it, not hand-maintained.
"""

from __future__ import annotations

from dataclasses import dataclass, field


CONFIG_VERSION = 2


@dataclass
class HapticSettings:
    enabled: bool = True
    intensity: int = 2                 # Legacy 0..3 bucket; hardware level is 1..100 in device.toml
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
    dpi_presets: list[int] = field(default_factory=lambda: [800, 1200, 1600, 2400, 4000])


@dataclass
class ScrollSettings:
    smartshift_enabled: bool = True
    smartshift_threshold: int = 15
    wheel_mode: str = "smart"          # smart | ratchet | free
    ratchet_torque: int = 75           # 1..100%
    hires_enabled: bool = True
    invert_vertical: bool = False
    invert_horizontal: bool = False
    scroll_speed: float = 1.0          # 0.20..4.00 vertical HD sensitivity multiplier
    scroll_smoothness: int = 0         # 0..100% 144Hz critically-damped smoothing
    scroll_accel: int = 0              # 0..100% dynamic flick velocity boost


@dataclass
class ThumbWheelSettings:
    # Mode controls how the 0x2150 thumb wheel behaves:
    #   "hd_scroll" — diverts 0x2150 in mx4-sysd for 6× hardware resolution
    #                 (120 ticks/rev vs native 20) + 144 Hz smooth REL_HWHEEL_HI_RES.
    #   "native"    — firmware 20-tick/rev kernel HID passthrough.
    #   "actions"   — diverts 0x2150 to mx4-agent for tabs, volume, zoom, etc.
    mode: str = "native"               # native | hd_scroll | actions
    diverted: bool = False             # kept in sync with mode == "actions" for compat
    invert: bool = False
    speed: float = 1.0                 # 0.20..4.00 HD horizontal sensitivity multiplier
    smoothness: int = 35               # 0..100% 144 Hz critically-damped horizontal smoothing
    accel: int = 25                    # 0..100% dynamic thumb flick acceleration
    hires: bool = True                 # emit REL_HWHEEL_HI_RES sub-detent units
    haptic_detent: bool = False        # virtual LRA micro-detent tick in HD scroll
    haptic_density: int = 6            # 1 (20/rev) | 2 (40/rev) | 3 (60/rev) | 6 (120/rev micro)
    haptic_pattern: int = 1            # LRA waveform id (0..14) for thumb-wheel detents
    preset: str = "tabs"               # tabs | volume | volume_fine | zoom | workspaces | media | history | timeline | brightness | brush | scroll_v | custom
    step: int = 40                     # accumulated diverted ticks per fired action (1..120)
    haptic_tick: bool = False          # play LRA tick on every fired action step
    micro_haptics: bool = True         # 6x Digital Crown micro-ticks between action steps
    positive_type: str = "keystroke"
    positive_data: str = "ctrl+Tab"
    negative_type: str = "keystroke"
    negative_data: str = "ctrl+shift+Tab"


@dataclass
class ActionSlice:
    """One of eight segments on the Actions Ring."""
    label: str = ""
    icon: str = ""
    action_type: str = "keystroke"    # keystroke | command | application | dpi_cycle | smartshift_toggle | host_next | haptic | disabled
    action_data: str = ""


@dataclass
class RingProfile:
    """Actions Ring profile for a specific application (or 'default').

    ``button_overrides`` are per-app button bindings layered on top of the
    global ``Config.button_bindings`` when this app is focused (matched by
    CID).
    """
    app_id: str = "default"
    app_name: str = "Default"
    app_icon: str = "application-x-executable"
    slices: list[ActionSlice] = field(default_factory=list)
    button_overrides: list["ButtonBinding"] = field(default_factory=list)


@dataclass
class ButtonBinding:
    """One physical-button → action binding.

    ``action_type`` is one of:

    ``"default"``           Let the firmware do whatever it normally does.
    ``"disabled"``          Divert the button so it emits nothing.
    ``"remap"``             Firmware-level remap to another CID (``action_data`` is
                            the target CID as a decimal string).
    ``"keystroke"``         Divert the button and fire a keyboard shortcut.
    ``"command"``           Divert and launch a shell command.
    ``"application"``       Divert and launch a .desktop-style app name.
    ``"dpi_cycle"``         Cycle through ``pointer.dpi_presets``.
    ``"dpi_set"``           Jump directly to a specific DPI (``action_data``).
    ``"smartshift_toggle"`` Toggle between SmartShift/Ratchet and Free-spin.
    ``"host_next"``         Switch to the next paired Easy-Switch host.
    ``"haptic"``            Play a haptic waveform (``action_data`` = 0..14).
    """
    cid: int
    action_type: str = "default"
    action_data: str = ""


@dataclass
class DaemonSettings:
    reader_timeout: float = 0.2
    cursor_freeze_tail_ms: int = 30
    autostart_gesture: bool = True
    trigger_cid: int = 0x01A0
    cancel_radius: int = 40
    ring_theme: str = "studio"
    ring_size: str = "standard"
    ring_show_hints: bool = True
    ring_animate: bool = True


@dataclass
class Config:
    version: int = CONFIG_VERSION
    haptics: HapticSettings = field(default_factory=HapticSettings)
    pointer: PointerSettings = field(default_factory=PointerSettings)
    scroll: ScrollSettings = field(default_factory=ScrollSettings)
    thumbwheel: ThumbWheelSettings = field(default_factory=ThumbWheelSettings)
    daemon: DaemonSettings = field(default_factory=DaemonSettings)
    ring_profiles: dict[str, RingProfile] = field(default_factory=dict)
    button_bindings: list[ButtonBinding] = field(default_factory=list)

    def __post_init__(self):
        if "default" not in self.ring_profiles:
            self.ring_profiles["default"] = _default_ring()


@dataclass
class ButtonDefault:
    """A persistent (device-scope) button setting applied at connect."""
    cid: int
    mode: str = "default"
    target: int = 0


@dataclass
class DeviceConfig:
    """Device-scope settings owned by the system daemon (``device.toml``).

    Applied to the mouse the moment it connects — even at the login screen.
    ``smartshift_enabled`` defaults to False so a fresh install stops the
    SmartShift clutch "buzz" out of the box.
    """
    version: int = CONFIG_VERSION
    dpi: int = 1000
    smartshift_enabled: bool = False
    smartshift_threshold: int = 15
    wheel_mode: str = "ratchet"        # smart | ratchet | free
    ratchet_torque: int = 75           # 1..100% (0x2111 tunable torque)
    haptic_enabled: bool = False
    haptic_level: int = 50             # 1..100%
    force_threshold: int = 0           # 0 = leave device default; >0 = 0x19C0 raw threshold
    hires_enabled: bool = True
    hires_invert: bool = False
    scroll_speed: float = 1.0          # 0.20..4.00 HD vertical speed multiplier
    scroll_smoothness: int = 0         # 0..100% 144Hz smooth scroll inertia
    scroll_accel: int = 0              # 0..100% dynamic flick boost
    thumbwheel_mode: str = "native"    # native | hd_scroll | actions
    thumbwheel_diverted: bool = False
    thumbwheel_invert: bool = False
    thumbwheel_speed: float = 1.0      # 0.20..4.00 HD horizontal scroll multiplier
    thumbwheel_smoothness: int = 35    # 0..100% 144Hz smooth horizontal inertia
    thumbwheel_accel: int = 25         # 0..100% dynamic horizontal flick boost
    thumbwheel_hires: bool = True      # emit REL_HWHEEL_HI_RES sub-detent output
    thumbwheel_haptic_detent: bool = False  # virtual LRA haptic click on HD horizontal detents
    thumbwheel_haptic_density: int = 6      # 1 | 2 | 3 | 6 detents per native notch (6 = 120/rev)
    thumbwheel_haptic_pattern: int = 1      # LRA waveform id (0..14) for HD horizontal detents
    restore_host: bool = False
    preferred_host: int = 0
    buttons: list[ButtonDefault] = field(default_factory=list)


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
