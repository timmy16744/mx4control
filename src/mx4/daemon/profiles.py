"""Per-application ring profile resolution.

Uses :class:`HyprlandFocusWatcher` when available — zero-latency lookup
of the focused-window class. Falls back to a ``hyprctl activewindow``
subprocess or an ``xdotool`` call on X11, with a short TTL cache.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from typing import Optional

from ..config import Config, RingProfile, ActionSlice
from .hyprland import HyprlandFocusWatcher

logger = logging.getLogger(__name__)


# Category templates used as baseline when the user hasn't customised
# the profile for a specific app yet.
CATEGORY_TEMPLATES: dict[str, list[ActionSlice]] = {
    "browser": [
        ActionSlice("New Tab",   "tab-new",          "keystroke", "ctrl+t"),
        ActionSlice("Close Tab", "window-close",     "keystroke", "ctrl+w"),
        ActionSlice("Reload",    "view-refresh",     "keystroke", "ctrl+r"),
        ActionSlice("Back",      "go-previous",      "keystroke", "alt+Left"),
        ActionSlice("Forward",   "go-next",          "keystroke", "alt+Right"),
        ActionSlice("Find",      "edit-find",        "keystroke", "ctrl+f"),
        ActionSlice("Bookmark",  "bookmark-new",     "keystroke", "ctrl+d"),
        ActionSlice("History",   "document-open-recent", "keystroke", "ctrl+h"),
    ],
    "editor": [
        ActionSlice("Save",        "document-save",     "keystroke", "ctrl+s"),
        ActionSlice("Undo",        "edit-undo",         "keystroke", "ctrl+z"),
        ActionSlice("Redo",        "edit-redo",         "keystroke", "ctrl+shift+z"),
        ActionSlice("Find",        "edit-find",         "keystroke", "ctrl+f"),
        ActionSlice("Replace",     "edit-find-replace", "keystroke", "ctrl+h"),
        ActionSlice("Go to Line",  "go-jump",           "keystroke", "ctrl+g"),
        ActionSlice("Comment",     "format-indent-more","keystroke", "ctrl+/"),
        ActionSlice("Format",      "format-justify-left","keystroke", "ctrl+shift+i"),
    ],
    "terminal": [
        ActionSlice("New Tab",   "tab-new",       "keystroke", "ctrl+shift+t"),
        ActionSlice("Close Tab", "window-close",  "keystroke", "ctrl+shift+w"),
        ActionSlice("Copy",      "edit-copy",     "keystroke", "ctrl+shift+c"),
        ActionSlice("Paste",     "edit-paste",    "keystroke", "ctrl+shift+v"),
        ActionSlice("Find",      "edit-find",     "keystroke", "ctrl+shift+f"),
        ActionSlice("Clear",     "edit-clear",    "keystroke", "ctrl+l"),
        ActionSlice("Zoom In",   "zoom-in",       "keystroke", "ctrl+plus"),
        ActionSlice("Zoom Out",  "zoom-out",      "keystroke", "ctrl+minus"),
    ],
    "media": [
        ActionSlice("Play/Pause", "media-playback-start", "keystroke", "space"),
        ActionSlice("Next",       "media-skip-forward",   "keystroke", "n"),
        ActionSlice("Previous",   "media-skip-backward",  "keystroke", "p"),
        ActionSlice("Vol Up",     "audio-volume-high",    "keystroke", "Up"),
        ActionSlice("Vol Down",   "audio-volume-low",     "keystroke", "Down"),
        ActionSlice("Mute",       "audio-volume-muted",   "keystroke", "m"),
        ActionSlice("Fullscreen", "view-fullscreen",      "keystroke", "f"),
        ActionSlice("Quit",       "application-exit",     "keystroke", "q"),
    ],
}

APP_CATEGORIES: dict[str, str] = {
    # Browsers
    "firefox": "browser", "chromium": "browser", "google-chrome": "browser",
    "brave-browser": "browser", "vivaldi": "browser", "zen": "browser",
    # Editors
    "code": "editor", "code-oss": "editor", "vscodium": "editor",
    "jetbrains-pycharm": "editor", "jetbrains-idea": "editor",
    "gnome-text-editor": "editor", "kate": "editor",
    # Terminals
    "kitty": "terminal", "alacritty": "terminal", "wezterm": "terminal",
    "foot": "terminal", "gnome-terminal": "terminal", "ghostty": "terminal",
    # Media
    "vlc": "media", "mpv": "media", "spotify": "media", "celluloid": "media",
}


class ProfileManager:
    def __init__(self, config: Config):
        self.config = config
        self._watcher: Optional[HyprlandFocusWatcher] = None

        # Fallback subprocess-polling cache
        self._cache_value = "default"
        self._cache_time = 0.0
        self._CACHE_TTL = 0.4

    # ─── lifecycle ──────────────────────────────────────────────────────

    def start(self) -> None:
        if self._watcher is not None:
            return
        self._watcher = HyprlandFocusWatcher(lambda *_: None)
        self._watcher.start()

    def stop(self) -> None:
        if self._watcher:
            self._watcher.stop()
            self._watcher = None

    # ─── profile resolution ─────────────────────────────────────────────

    def current_app_id(self) -> str:
        """Return the focused application's normalized ID."""
        if self._watcher is not None:
            app_class, _ = self._watcher.current
            if app_class:
                return self._normalize(app_class)

        now = time.monotonic()
        if now - self._cache_time < self._CACHE_TTL:
            return self._cache_value

        app_id = self._probe_focus()
        self._cache_value = app_id
        self._cache_time = now
        return app_id

    def current_profile(self) -> RingProfile:
        app_id = self.current_app_id()
        if app_id in self.config.ring_profiles:
            return self.config.ring_profiles[app_id]

        # Build a new profile from the category template if known;
        # otherwise use the default profile.
        if category := APP_CATEGORIES.get(app_id):
            template = CATEGORY_TEMPLATES.get(category)
            if template:
                profile = RingProfile(
                    app_id=app_id, app_name=app_id.title(),
                    slices=[ActionSlice(**s.__dict__) for s in template],
                )
                return profile

        return self.config.ring_profiles.get("default") or RingProfile(app_id="default")

    # ─── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _normalize(app_class: str) -> str:
        app_class = app_class.lower().strip()
        aliases = {
            "google-chrome-stable": "google-chrome",
            "chromium-browser": "chromium",
            "code - oss": "code-oss",
            "visual studio code": "code",
            "gnome-terminal-server": "gnome-terminal",
        }
        return aliases.get(app_class, app_class)

    def _probe_focus(self) -> str:
        for cmd, parser in (
            (["hyprctl", "activewindow", "-j"], self._parse_hyprctl),
            (["xdotool", "getactivewindow", "getwindowclassname"], str.strip),
        ):
            try:
                r = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=0.5,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if r.returncode == 0 and r.stdout:
                try:
                    return self._normalize(parser(r.stdout))
                except Exception:
                    continue
        return "default"

    @staticmethod
    def _parse_hyprctl(out: str) -> str:
        data = json.loads(out)
        return data.get("class", "") or ""
