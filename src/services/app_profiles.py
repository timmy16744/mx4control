"""
Application Profiles System

Manages per-application action configurations for the Actions Ring.
Automatically detects the focused application and switches profiles.
"""

import os
import json
import subprocess
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List
from configparser import ConfigParser

logger = logging.getLogger(__name__)


@dataclass
class ActionSlice:
    """Configuration for a single action slice"""
    label: str
    icon: str
    action_type: str  # keystroke, command, application
    action_data: str

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'ActionSlice':
        return cls(**data)


@dataclass
class AppProfile:
    """Action profile for a specific application"""
    app_id: str  # e.g., "firefox", "code", "default"
    app_name: str  # Display name
    app_icon: str  # Icon name
    slices: List[ActionSlice] = field(default_factory=list)

    def to_dict(self):
        return {
            'app_id': self.app_id,
            'app_name': self.app_name,
            'app_icon': self.app_icon,
            'slices': [s.to_dict() for s in self.slices]
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'AppProfile':
        slices = [ActionSlice.from_dict(s) for s in data.get('slices', [])]
        return cls(
            app_id=data['app_id'],
            app_name=data['app_name'],
            app_icon=data.get('app_icon', 'application-x-executable'),
            slices=slices
        )


@dataclass
class InstalledApp:
    """Information about an installed application"""
    app_id: str
    name: str
    icon: str
    exec_cmd: str
    categories: List[str]
    desktop_file: str


# Common action templates by category
CATEGORY_TEMPLATES = {
    'browser': [
        ActionSlice("New Tab", "tab-new", "keystroke", "ctrl+t"),
        ActionSlice("Close Tab", "window-close", "keystroke", "ctrl+w"),
        ActionSlice("Reload", "view-refresh", "keystroke", "ctrl+r"),
        ActionSlice("Back", "go-previous", "keystroke", "alt+Left"),
        ActionSlice("Forward", "go-next", "keystroke", "alt+Right"),
        ActionSlice("Find", "edit-find", "keystroke", "ctrl+f"),
        ActionSlice("Bookmarks", "bookmark-new", "keystroke", "ctrl+d"),
        ActionSlice("History", "document-open-recent", "keystroke", "ctrl+h"),
    ],
    'editor': [
        ActionSlice("Save", "document-save", "keystroke", "ctrl+s"),
        ActionSlice("Undo", "edit-undo", "keystroke", "ctrl+z"),
        ActionSlice("Redo", "edit-redo", "keystroke", "ctrl+shift+z"),
        ActionSlice("Find", "edit-find", "keystroke", "ctrl+f"),
        ActionSlice("Replace", "edit-find-replace", "keystroke", "ctrl+h"),
        ActionSlice("Go to Line", "go-jump", "keystroke", "ctrl+g"),
        ActionSlice("Comment", "format-indent-more", "keystroke", "ctrl+/"),
        ActionSlice("Format", "format-justify-left", "keystroke", "ctrl+shift+i"),
    ],
    'terminal': [
        ActionSlice("New Tab", "tab-new", "keystroke", "ctrl+shift+t"),
        ActionSlice("Close Tab", "window-close", "keystroke", "ctrl+shift+w"),
        ActionSlice("Copy", "edit-copy", "keystroke", "ctrl+shift+c"),
        ActionSlice("Paste", "edit-paste", "keystroke", "ctrl+shift+v"),
        ActionSlice("Find", "edit-find", "keystroke", "ctrl+shift+f"),
        ActionSlice("Clear", "edit-clear", "keystroke", "ctrl+l"),
        ActionSlice("Zoom In", "zoom-in", "keystroke", "ctrl+plus"),
        ActionSlice("Zoom Out", "zoom-out", "keystroke", "ctrl+minus"),
    ],
    'media': [
        ActionSlice("Play/Pause", "media-playback-start", "keystroke", "space"),
        ActionSlice("Stop", "media-playback-stop", "keystroke", "s"),
        ActionSlice("Next", "media-skip-forward", "keystroke", "n"),
        ActionSlice("Previous", "media-skip-backward", "keystroke", "p"),
        ActionSlice("Vol Up", "audio-volume-high", "keystroke", "Up"),
        ActionSlice("Vol Down", "audio-volume-low", "keystroke", "Down"),
        ActionSlice("Mute", "audio-volume-muted", "keystroke", "m"),
        ActionSlice("Fullscreen", "view-fullscreen", "keystroke", "f"),
    ],
    'graphics': [
        ActionSlice("Undo", "edit-undo", "keystroke", "ctrl+z"),
        ActionSlice("Redo", "edit-redo", "keystroke", "ctrl+y"),
        ActionSlice("Brush", "draw-brush", "keystroke", "b"),
        ActionSlice("Eraser", "draw-eraser", "keystroke", "e"),
        ActionSlice("Zoom In", "zoom-in", "keystroke", "ctrl+plus"),
        ActionSlice("Zoom Out", "zoom-out", "keystroke", "ctrl+minus"),
        ActionSlice("Save", "document-save", "keystroke", "ctrl+s"),
        ActionSlice("Export", "document-export", "keystroke", "ctrl+shift+e"),
    ],
    'office': [
        ActionSlice("Save", "document-save", "keystroke", "ctrl+s"),
        ActionSlice("Undo", "edit-undo", "keystroke", "ctrl+z"),
        ActionSlice("Redo", "edit-redo", "keystroke", "ctrl+y"),
        ActionSlice("Copy", "edit-copy", "keystroke", "ctrl+c"),
        ActionSlice("Paste", "edit-paste", "keystroke", "ctrl+v"),
        ActionSlice("Find", "edit-find", "keystroke", "ctrl+f"),
        ActionSlice("Print", "document-print", "keystroke", "ctrl+p"),
        ActionSlice("Bold", "format-text-bold", "keystroke", "ctrl+b"),
    ],
    'default': [
        ActionSlice("Undo", "edit-undo", "keystroke", "ctrl+z"),
        ActionSlice("Paste", "edit-paste", "keystroke", "ctrl+v"),
        ActionSlice("Copy", "edit-copy", "keystroke", "ctrl+c"),
        ActionSlice("Cut", "edit-cut", "keystroke", "ctrl+x"),
        ActionSlice("Redo", "edit-redo", "keystroke", "ctrl+shift+z"),
        ActionSlice("Screenshot", "camera-photo", "command", "grimshot copy area"),
        ActionSlice("Terminal", "utilities-terminal", "application", "kitty"),
        ActionSlice("Files", "system-file-manager", "application", "nautilus"),
    ],
}

# App ID to category mapping
APP_CATEGORIES = {
    # Browsers
    'firefox': 'browser',
    'chromium': 'browser',
    'google-chrome': 'browser',
    'brave-browser': 'browser',
    'vivaldi': 'browser',
    'opera': 'browser',
    'epiphany': 'browser',
    'qutebrowser': 'browser',

    # Editors/IDEs
    'code': 'editor',
    'code-oss': 'editor',
    'vscodium': 'editor',
    'sublime_text': 'editor',
    'atom': 'editor',
    'gedit': 'editor',
    'kate': 'editor',
    'gnome-text-editor': 'editor',
    'neovim': 'editor',
    'vim': 'editor',
    'emacs': 'editor',
    'jetbrains-idea': 'editor',
    'jetbrains-pycharm': 'editor',
    'jetbrains-webstorm': 'editor',
    'jetbrains-clion': 'editor',

    # Terminals
    'kitty': 'terminal',
    'alacritty': 'terminal',
    'gnome-terminal': 'terminal',
    'konsole': 'terminal',
    'xfce4-terminal': 'terminal',
    'tilix': 'terminal',
    'terminator': 'terminal',
    'foot': 'terminal',
    'wezterm': 'terminal',

    # Media
    'vlc': 'media',
    'mpv': 'media',
    'totem': 'media',
    'celluloid': 'media',
    'spotify': 'media',
    'rhythmbox': 'media',
    'audacious': 'media',
    'elisa': 'media',

    # Graphics
    'gimp': 'graphics',
    'inkscape': 'graphics',
    'krita': 'graphics',
    'blender': 'graphics',
    'darktable': 'graphics',
    'rawtherapee': 'graphics',

    # Office
    'libreoffice-writer': 'office',
    'libreoffice-calc': 'office',
    'libreoffice-impress': 'office',
    'onlyoffice-desktopeditors': 'office',
    'thunderbird': 'office',
}


class AppProfileManager:
    """Manages application profiles and focused window detection"""

    # Cache focused-app lookups so rapid-fire gestures don't pay the
    # hyprctl subprocess cost every time. 500ms is short enough that
    # switching windows between gestures still picks up the new profile.
    _FOCUS_CACHE_TTL = 0.5

    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or Path.home() / '.config' / 'mx4control' / 'profiles'
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.profiles: Dict[str, AppProfile] = {}
        self.installed_apps: Dict[str, InstalledApp] = {}
        self.current_app_id: str = 'default'

        # TTL cache state for get_focused_app_id
        self._focus_cache_value: str = 'default'
        self._focus_cache_time: float = 0.0

        # Load existing profiles
        self._load_profiles()

        # Discover installed apps
        self._discover_apps()

        # Ensure default profile exists
        if 'default' not in self.profiles:
            self._create_default_profile()

    def _load_profiles(self):
        """Load saved profiles from disk"""
        profiles_file = self.config_dir / 'profiles.json'
        if profiles_file.exists():
            try:
                with open(profiles_file) as f:
                    data = json.load(f)
                for profile_data in data.get('profiles', []):
                    profile = AppProfile.from_dict(profile_data)
                    self.profiles[profile.app_id] = profile
                logger.info(f"Loaded {len(self.profiles)} profiles")
            except Exception as e:
                logger.error(f"Failed to load profiles: {e}")

    def save_profiles(self):
        """Save all profiles to disk"""
        profiles_file = self.config_dir / 'profiles.json'
        try:
            data = {
                'profiles': [p.to_dict() for p in self.profiles.values()]
            }
            with open(profiles_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved {len(self.profiles)} profiles")
        except Exception as e:
            logger.error(f"Failed to save profiles: {e}")

    def _create_default_profile(self):
        """Create the default profile"""
        self.profiles['default'] = AppProfile(
            app_id='default',
            app_name='Default',
            app_icon='application-x-executable',
            slices=CATEGORY_TEMPLATES['default'].copy()
        )

    def _discover_apps(self):
        """Discover installed applications from .desktop files"""
        desktop_dirs = [
            Path('/usr/share/applications'),
            Path.home() / '.local' / 'share' / 'applications',
            Path('/var/lib/flatpak/exports/share/applications'),
            Path.home() / '.local' / 'share' / 'flatpak' / 'exports' / 'share' / 'applications',
        ]

        for desktop_dir in desktop_dirs:
            if not desktop_dir.exists():
                continue

            for desktop_file in desktop_dir.glob('*.desktop'):
                try:
                    app = self._parse_desktop_file(desktop_file)
                    if app and app.app_id not in self.installed_apps:
                        self.installed_apps[app.app_id] = app
                except Exception as e:
                    logger.debug(f"Failed to parse {desktop_file}: {e}")

        logger.info(f"Discovered {len(self.installed_apps)} installed applications")

    def _parse_desktop_file(self, path: Path) -> Optional[InstalledApp]:
        """Parse a .desktop file and extract app info"""
        config = ConfigParser(interpolation=None)
        config.read(path, encoding='utf-8')

        if 'Desktop Entry' not in config:
            return None

        entry = config['Desktop Entry']

        # Skip hidden or NoDisplay apps
        if entry.get('Hidden', 'false').lower() == 'true':
            return None
        if entry.get('NoDisplay', 'false').lower() == 'true':
            return None

        # Get app ID from filename
        app_id = path.stem.lower().replace('.', '-')

        # Handle common ID patterns
        if app_id.startswith('org-'):
            parts = app_id.split('-')
            if len(parts) >= 3:
                app_id = parts[-1]

        name = entry.get('Name', app_id)
        icon = entry.get('Icon', 'application-x-executable')
        exec_cmd = entry.get('Exec', '')
        categories = entry.get('Categories', '').split(';')

        return InstalledApp(
            app_id=app_id,
            name=name,
            icon=icon,
            exec_cmd=exec_cmd,
            categories=[c.strip() for c in categories if c.strip()],
            desktop_file=str(path)
        )

    def get_focused_app_id(self) -> str:
        """Get the app ID of the currently focused window.

        Results are cached for :attr:`_FOCUS_CACHE_TTL` seconds so a burst
        of gestures within the same window skips the subprocess fork.
        """
        import time
        now = time.monotonic()
        if now - self._focus_cache_time < self._FOCUS_CACHE_TTL:
            return self._focus_cache_value

        try:
            # Try hyprctl for Hyprland
            result = subprocess.run(
                ['hyprctl', 'activewindow', '-j'],
                capture_output=True, text=True, timeout=1
            )
            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)
                app_class = data.get('class', '').lower()
                if app_class:
                    result_id = self._normalize_app_id(app_class)
                    self._focus_cache_value = result_id
                    self._focus_cache_time = now
                    return result_id
        except Exception:
            pass

        try:
            # Try swaymsg for Sway
            result = subprocess.run(
                ['swaymsg', '-t', 'get_tree'],
                capture_output=True, text=True, timeout=1
            )
            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)
                focused = self._find_focused_sway(data)
                if focused:
                    result_id = self._normalize_app_id(focused)
                    self._focus_cache_value = result_id
                    self._focus_cache_time = now
                    return result_id
        except Exception:
            pass

        try:
            # Fallback to xdotool for X11/XWayland
            result = subprocess.run(
                ['xdotool', 'getactivewindow', 'getwindowclassname'],
                capture_output=True, text=True, timeout=1
            )
            if result.returncode == 0:
                result_id = self._normalize_app_id(result.stdout.strip())
                self._focus_cache_value = result_id
                self._focus_cache_time = now
                return result_id
        except Exception:
            pass

        self._focus_cache_value = 'default'
        self._focus_cache_time = now
        return 'default'

    def _find_focused_sway(self, node: dict) -> Optional[str]:
        """Find focused window in sway tree"""
        if node.get('focused'):
            return node.get('app_id') or node.get('window_properties', {}).get('class')
        for child in node.get('nodes', []) + node.get('floating_nodes', []):
            result = self._find_focused_sway(child)
            if result:
                return result
        return None

    def _normalize_app_id(self, app_id: str) -> str:
        """Normalize app ID to match our profiles"""
        app_id = app_id.lower().strip()

        # Common normalizations
        normalizations = {
            'google-chrome-stable': 'google-chrome',
            'chromium-browser': 'chromium',
            'code - oss': 'code-oss',
            'visual studio code': 'code',
            'gnome-terminal-server': 'gnome-terminal',
        }

        return normalizations.get(app_id, app_id)

    def get_profile_for_app(self, app_id: str) -> AppProfile:
        """Get the profile for an app, creating from template if needed"""
        # Check for exact match
        if app_id in self.profiles:
            return self.profiles[app_id]

        # Check for category-based template
        category = APP_CATEGORIES.get(app_id, 'default')
        template = CATEGORY_TEMPLATES.get(category, CATEGORY_TEMPLATES['default'])

        # Get app info if available
        app_info = self.installed_apps.get(app_id)
        app_name = app_info.name if app_info else app_id.title()
        app_icon = app_info.icon if app_info else 'application-x-executable'

        # Create new profile from template
        profile = AppProfile(
            app_id=app_id,
            app_name=app_name,
            app_icon=app_icon,
            slices=template.copy()
        )

        # Save it for future use
        self.profiles[app_id] = profile
        self.save_profiles()

        return profile

    def get_current_profile(self) -> AppProfile:
        """Get the profile for the currently focused app"""
        self.current_app_id = self.get_focused_app_id()
        return self.get_profile_for_app(self.current_app_id)

    def update_profile(self, app_id: str, slices: List[ActionSlice]):
        """Update the slices for a profile"""
        if app_id in self.profiles:
            self.profiles[app_id].slices = slices
        else:
            app_info = self.installed_apps.get(app_id)
            self.profiles[app_id] = AppProfile(
                app_id=app_id,
                app_name=app_info.name if app_info else app_id.title(),
                app_icon=app_info.icon if app_info else 'application-x-executable',
                slices=slices
            )
        self.save_profiles()

    def delete_profile(self, app_id: str):
        """Delete a profile (except default)"""
        if app_id != 'default' and app_id in self.profiles:
            del self.profiles[app_id]
            self.save_profiles()

    def get_all_apps(self) -> List[InstalledApp]:
        """Get list of all discovered apps"""
        return sorted(self.installed_apps.values(), key=lambda a: a.name.lower())

    def get_all_profiles(self) -> List[AppProfile]:
        """Get list of all configured profiles"""
        return sorted(self.profiles.values(), key=lambda p: p.app_name.lower())

    def create_profile_for_app(self, app_id: str) -> AppProfile:
        """Create a new profile for an app from template"""
        return self.get_profile_for_app(app_id)


# Global instance
_profile_manager: Optional[AppProfileManager] = None


def get_profile_manager() -> AppProfileManager:
    """Get or create the global profile manager"""
    global _profile_manager
    if _profile_manager is None:
        _profile_manager = AppProfileManager()
    return _profile_manager
