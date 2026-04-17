"""
Configuration Management for MX4Control

Handles persistent storage of user preferences and device settings.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# XDG Base Directory paths
XDG_CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
XDG_DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))

CONFIG_DIR = XDG_CONFIG_HOME / "mx4control"
DATA_DIR = XDG_DATA_HOME / "mx4control"


@dataclass
class HapticSettings:
    """Haptic feedback configuration"""
    enabled: bool = True
    intensity: int = 2  # 0=Subtle, 1=Low, 2=Medium, 3=High
    selected_pattern: int = 2  # Currently selected pattern (0-14)
    notification_pattern: int = 0x0A  # Double tap
    scroll_end_pattern: int = 0x03  # Medium click
    notification_enabled: bool = True
    scroll_end_enabled: bool = False
    device_switch_enabled: bool = True


@dataclass
class PointerSettings:
    """Pointer/DPI configuration"""
    dpi: int = 1000
    angle_snapping: bool = False
    acceleration: float = 0.0


@dataclass
class ScrollSettings:
    """Scroll wheel configuration"""
    smartshift_enabled: bool = True
    smartshift_threshold: int = 25
    hires_enabled: bool = True
    invert_vertical: bool = False
    invert_horizontal: bool = False


@dataclass
class ButtonMapping:
    """Single button configuration"""
    button_id: int
    action_type: str = "default"  # default, keystroke, media, command
    action_data: str = ""
    gesture_up: str = ""
    gesture_down: str = ""
    gesture_left: str = ""
    gesture_right: str = ""


@dataclass
class ActionsRingSlice:
    """Single Actions Ring menu slice"""
    position: int  # 0-7, clockwise from top
    label: str = ""
    icon: str = ""
    action_type: str = "keystroke"
    action_data: str = ""


@dataclass
class ActionsRingProfile:
    """Actions Ring configuration for an application"""
    app_pattern: str = "*"  # Regex or wildcard for app matching
    enabled: bool = True
    slices: list[ActionsRingSlice] = field(default_factory=list)


@dataclass
class AppProfile:
    """Per-application profile"""
    name: str
    app_pattern: str  # WM_CLASS or executable pattern
    dpi: Optional[int] = None
    buttons: list[ButtonMapping] = field(default_factory=list)
    actions_ring: Optional[ActionsRingProfile] = None


@dataclass
class Config:
    """Main configuration container"""
    version: int = 1
    haptics: HapticSettings = field(default_factory=HapticSettings)
    pointer: PointerSettings = field(default_factory=PointerSettings)
    scroll: ScrollSettings = field(default_factory=ScrollSettings)
    buttons: list[ButtonMapping] = field(default_factory=list)
    actions_ring: ActionsRingProfile = field(default_factory=ActionsRingProfile)
    app_profiles: list[AppProfile] = field(default_factory=list)

    # UI preferences
    theme: str = "dark"  # dark, light, system
    show_tray_icon: bool = True
    start_minimized: bool = False
    autostart: bool = False


class ConfigManager:
    """
    Manages loading, saving, and updating configuration

    Configuration is stored as JSON in XDG_CONFIG_HOME/mx4control/config.json
    """

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or CONFIG_DIR / "config.json"
        self._config: Optional[Config] = None
        self._ensure_dirs()

    def _ensure_dirs(self):
        """Create config directories if they don't exist"""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def config(self) -> Config:
        """Get current configuration, loading if necessary"""
        if self._config is None:
            self.load()
        return self._config

    def load(self) -> Config:
        """Load configuration from disk"""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    data = json.load(f)
                self._config = self._from_dict(data)
                logger.info(f"Loaded config from {self.config_path}")
            except Exception as e:
                logger.warning(f"Failed to load config: {e}")
                self._config = self._default_config()
        else:
            self._config = self._default_config()
        return self._config

    def save(self) -> bool:
        """Save current configuration to disk"""
        if self._config is None:
            return False

        try:
            data = self._to_dict(self._config)
            with open(self.config_path, "w") as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved config to {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            return False

    def reset(self):
        """Reset configuration to defaults"""
        self._config = self._default_config()
        self.save()

    def _default_config(self) -> Config:
        """Create default configuration"""
        config = Config()

        # Default button mappings for MX Master 4
        config.buttons = [
            ButtonMapping(0, "default", "Left Click"),
            ButtonMapping(1, "default", "Right Click"),
            ButtonMapping(2, "default", "Middle Click"),
            ButtonMapping(3, "default", "Back"),
            ButtonMapping(4, "default", "Forward"),
            ButtonMapping(5, "default", "Gesture Button"),
            ButtonMapping(6, "default", "Mode Shift"),
            ButtonMapping(7, "default", "Thumb Wheel"),
        ]

        # Default Actions Ring
        config.actions_ring = ActionsRingProfile(
            app_pattern="*",
            enabled=True,
            slices=[
                ActionsRingSlice(0, "Copy", "edit-copy", "keystroke", "ctrl+c"),
                ActionsRingSlice(1, "Paste", "edit-paste", "keystroke", "ctrl+v"),
                ActionsRingSlice(2, "Cut", "edit-cut", "keystroke", "ctrl+x"),
                ActionsRingSlice(3, "Undo", "edit-undo", "keystroke", "ctrl+z"),
                ActionsRingSlice(4, "Screenshot", "camera-photo", "command", "gnome-screenshot -a"),
                ActionsRingSlice(5, "Files", "system-file-manager", "command", "nautilus"),
                ActionsRingSlice(6, "Terminal", "utilities-terminal", "command", "gnome-terminal"),
                ActionsRingSlice(7, "Settings", "preferences-system", "command", "gnome-control-center"),
            ],
        )

        return config

    def _to_dict(self, obj) -> dict:
        """Convert dataclass hierarchy to dict"""
        if hasattr(obj, "__dataclass_fields__"):
            return {k: self._to_dict(v) for k, v in asdict(obj).items()}
        elif isinstance(obj, list):
            return [self._to_dict(item) for item in obj]
        return obj

    def _from_dict(self, data: dict) -> Config:
        """Convert dict to Config dataclass"""
        config = Config(
            version=data.get("version", 1),
            theme=data.get("theme", "dark"),
            show_tray_icon=data.get("show_tray_icon", True),
            start_minimized=data.get("start_minimized", False),
            autostart=data.get("autostart", False),
        )

        if "haptics" in data:
            config.haptics = HapticSettings(**data["haptics"])

        if "pointer" in data:
            config.pointer = PointerSettings(**data["pointer"])

        if "scroll" in data:
            config.scroll = ScrollSettings(**data["scroll"])

        if "buttons" in data:
            config.buttons = [ButtonMapping(**b) for b in data["buttons"]]

        if "actions_ring" in data:
            ar_data = data["actions_ring"]
            slices = [ActionsRingSlice(**s) for s in ar_data.get("slices", [])]
            config.actions_ring = ActionsRingProfile(
                app_pattern=ar_data.get("app_pattern", "*"),
                enabled=ar_data.get("enabled", True),
                slices=slices,
            )

        if "app_profiles" in data:
            profiles = []
            for p in data["app_profiles"]:
                buttons = [ButtonMapping(**b) for b in p.get("buttons", [])]
                ar = None
                if "actions_ring" in p and p["actions_ring"]:
                    ar_data = p["actions_ring"]
                    ar = ActionsRingProfile(
                        app_pattern=ar_data.get("app_pattern", "*"),
                        enabled=ar_data.get("enabled", True),
                        slices=[ActionsRingSlice(**s) for s in ar_data.get("slices", [])],
                    )
                profiles.append(AppProfile(
                    name=p["name"],
                    app_pattern=p["app_pattern"],
                    dpi=p.get("dpi"),
                    buttons=buttons,
                    actions_ring=ar,
                ))
            config.app_profiles = profiles

        return config
