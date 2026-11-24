"""Per-application ring profile + button-override resolution.

Uses :class:`HyprlandFocusWatcher` for zero-latency lookup of the
focused-window class, falling back to a ``hyprctl activewindow``
subprocess or an ``xdotool`` call on X11 with a short TTL cache.

Stale-config fix
----------------
The monolithic ``ProfileManager`` captured a ``Config`` object at
construction, so ``mx4ctl reload`` (which swaps in a *new* Config) left
the manager pointing at the old one. Here we hold the :class:`ConfigStore`
and read ``store.config`` afresh on every lookup, so a reload is picked
up immediately with no re-wiring.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from typing import Optional

from ..config import ActionSlice, ButtonBinding, Config, ConfigStore, RingProfile
from .hyprland import HyprlandFocusWatcher

logger = logging.getLogger(__name__)


# Curated 8-slice Actions Ring presets available both as 1-click profile presets
# in MX4 Studio and as automatic category templates for newly focused apps.
RING_PRESETS: dict[str, dict] = {
    "default": {
        "id": "default",
        "name": "Productivity",
        "tagline": "Universal daily workflow · edit, clipboard, capture & tabs",
        "badge": "CORE",
        "slices": [
            ActionSlice("Undo",       "edit-undo",      "keystroke", "ctrl+z"),
            ActionSlice("Redo",       "edit-redo",      "keystroke", "ctrl+shift+z"),
            ActionSlice("Copy",       "edit-copy",      "keystroke", "ctrl+c"),
            ActionSlice("Paste",      "edit-paste",     "keystroke", "ctrl+v"),
            ActionSlice("Screenshot", "camera-photo",   "command",   'grim -g "$(slurp)" - | wl-copy'),
            ActionSlice("Save",       "document-save",  "keystroke", "ctrl+s"),
            ActionSlice("Find",       "edit-find",      "keystroke", "ctrl+f"),
            ActionSlice("Close Tab",  "window-close",   "keystroke", "ctrl+w"),
        ],
    },
    "hyprland": {
        "id": "hyprland",
        "name": "Hyprland WM",
        "tagline": "Workspaces, tiling float, fullscreen & Wayland capture",
        "badge": "WAYLAND",
        "slices": [
            ActionSlice("Fullscreen", "view-fullscreen", "command", "hyprctl dispatch fullscreen 0"),
            ActionSlice("Next WS",    "go-next",         "command", "hyprctl dispatch workspace +1"),
            ActionSlice("Move Next",  "go-jump",         "command", "hyprctl dispatch movetoworkspace +1"),
            ActionSlice("Float",      "window-new",      "command", "hyprctl dispatch togglefloating"),
            ActionSlice("Close Win",  "window-close",    "command", "hyprctl dispatch killactive"),
            ActionSlice("Screenshot", "camera-photo",    "command", 'grim -g "$(slurp)" - | wl-copy'),
            ActionSlice("Move Prev",  "go-jump",         "command", "hyprctl dispatch movetoworkspace -1"),
            ActionSlice("Prev WS",    "go-previous",     "command", "hyprctl dispatch workspace -1"),
        ],
    },
    "browser": {
        "id": "browser",
        "name": "Web Browser",
        "tagline": "Fast tab surfing, reopen closed, history & page search",
        "badge": "WEB",
        "slices": [
            ActionSlice("New Tab",   "tab-new",              "keystroke", "ctrl+t"),
            ActionSlice("Close Tab", "window-close",         "keystroke", "ctrl+w"),
            ActionSlice("Reload",    "view-refresh",         "keystroke", "ctrl+r"),
            ActionSlice("Forward",   "go-next",              "keystroke", "alt+Right"),
            ActionSlice("Reopen",    "edit-undo",            "keystroke", "ctrl+shift+t"),
            ActionSlice("Find",      "edit-find",            "keystroke", "ctrl+f"),
            ActionSlice("Back",      "go-previous",          "keystroke", "alt+Left"),
            ActionSlice("Bookmark",  "bookmark-new",         "keystroke", "ctrl+d"),
        ],
    },
    "editor": {
        "id": "editor",
        "name": "Code / IDE",
        "tagline": "Command palette, quick open, format, terminal & refactor",
        "badge": "DEV",
        "slices": [
            ActionSlice("Palette",   "system-search",       "keystroke", "ctrl+shift+p"),
            ActionSlice("Quick Open","document-open",       "keystroke", "ctrl+p"),
            ActionSlice("Find All",  "edit-find",           "keystroke", "ctrl+shift+f"),
            ActionSlice("Format",    "format-justify-left", "keystroke", "ctrl+shift+i"),
            ActionSlice("Terminal",  "utilities-terminal",  "keystroke", "ctrl+grave"),
            ActionSlice("Comment",   "format-indent-more",  "keystroke", "ctrl+/"),
            ActionSlice("Undo",      "edit-undo",           "keystroke", "ctrl+z"),
            ActionSlice("Save",      "document-save",       "keystroke", "ctrl+s"),
        ],
    },
    "terminal": {
        "id": "terminal",
        "name": "Terminal / Shell",
        "tagline": "Split panes, clipboard, history search & screen clear",
        "badge": "CLI",
        "slices": [
            ActionSlice("New Tab",   "tab-new",            "keystroke", "ctrl+shift+t"),
            ActionSlice("Copy",      "edit-copy",          "keystroke", "ctrl+shift+c"),
            ActionSlice("Paste",     "edit-paste",         "keystroke", "ctrl+shift+v"),
            ActionSlice("Find",      "edit-find",          "keystroke", "ctrl+shift+f"),
            ActionSlice("Close Tab", "window-close",       "keystroke", "ctrl+shift+w"),
            ActionSlice("Clear",     "edit-clear",         "keystroke", "ctrl+l"),
            ActionSlice("Zoom In",   "zoom-in",            "keystroke", "ctrl+plus"),
            ActionSlice("Zoom Out",  "zoom-out",           "keystroke", "ctrl+minus"),
        ],
    },
    "media": {
        "id": "media",
        "name": "Media & Audio",
        "tagline": "Native PipeWire volume, MPRIS playback & mic mute",
        "badge": "AUDIO",
        "slices": [
            ActionSlice("Play/Pause", "media-playback-start", "command", "playerctl play-pause"),
            ActionSlice("Vol +5%",    "audio-volume-high",    "command", "wpctl set-volume -l 1.5 @DEFAULT_AUDIO_SINK@ 5%+"),
            ActionSlice("Next",       "media-skip-forward",   "command", "playerctl next"),
            ActionSlice("Vol -5%",    "audio-volume-low",     "command", "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-"),
            ActionSlice("Mute Audio", "audio-volume-muted",   "command", "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"),
            ActionSlice("Mute Mic",   "microphone-muted",     "command", "wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle"),
            ActionSlice("Previous",   "media-skip-backward",  "command", "playerctl previous"),
            ActionSlice("Fullscreen", "view-fullscreen",      "keystroke", "f"),
        ],
    },
    "creative": {
        "id": "creative",
        "name": "Creative & 3D",
        "tagline": "Blender, Figma, GIMP & Krita precision studio tools",
        "badge": "3D / ART",
        "slices": [
            ActionSlice("Save",       "document-save",  "keystroke", "ctrl+s"),
            ActionSlice("Redo",       "edit-redo",      "keystroke", "ctrl+shift+z"),
            ActionSlice("Duplicate",  "edit-copy",      "keystroke", "shift+d"),
            ActionSlice("Export",     "document-export","keystroke", "ctrl+shift+e"),
            ActionSlice("Screenshot", "camera-photo",   "command",   'grim -g "$(slurp)" - | wl-copy'),
            ActionSlice("Zoom Fit",   "zoom-in",        "keystroke", "Home"),
            ActionSlice("Hide/Show",  "view-refresh",   "keystroke", "h"),
            ActionSlice("Undo",       "edit-undo",      "keystroke", "ctrl+z"),
        ],
    },
    "hardware": {
        "id": "hardware",
        "name": "MX4 Hardware Deck",
        "tagline": "Cycle DPI, SmartShift toggle, Easy-Switch & audio",
        "badge": "MX4",
        "slices": [
            ActionSlice("Cycle DPI",  "input-mouse",        "dpi_cycle",         ""),
            ActionSlice("SmartShift", "view-refresh",       "smartshift_toggle", ""),
            ActionSlice("Next Host",  "network-wireless",   "host_next",         ""),
            ActionSlice("Vol +5%",    "audio-volume-high",  "command",           "wpctl set-volume -l 1.5 @DEFAULT_AUDIO_SINK@ 5%+"),
            ActionSlice("Mute Audio", "audio-volume-muted", "command",           "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"),
            ActionSlice("Vol -5%",    "audio-volume-low",   "command",           "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-"),
            ActionSlice("Screenshot", "camera-photo",       "command",           'grim -g "$(slurp)" - | wl-copy'),
            ActionSlice("Haptic Ping","emblem-favorite",    "haptic",            "2"),
        ],
    },
}

# Category templates used as baseline when the user hasn't customised
# the profile for a specific app yet.
CATEGORY_TEMPLATES: dict[str, list[ActionSlice]] = {
    k: v["slices"] for k, v in RING_PRESETS.items()
}


def clone_preset_slices(preset_id: str) -> list[ActionSlice]:
    """Return a fresh copy of the 8 ActionSlices for ``preset_id``."""
    preset = RING_PRESETS.get(str(preset_id).strip().lower()) or RING_PRESETS["default"]
    return [
        ActionSlice(s.label, s.icon, s.action_type, s.action_data)
        for s in preset["slices"]
    ]


def list_ring_presets() -> list[dict]:
    """Serialize all curated Actions Ring presets for MX4 Studio."""
    out: list[dict] = []
    for preset in RING_PRESETS.values():
        out.append({
            "id": preset["id"],
            "name": preset["name"],
            "tagline": preset["tagline"],
            "badge": preset["badge"],
            "slices": [
                {
                    "label": s.label,
                    "icon": s.icon,
                    "action_type": s.action_type,
                    "action_data": s.action_data,
                }
                for s in preset["slices"]
            ],
        })
    return out


APP_CATEGORIES: dict[str, str] = {
    # Browsers
    "firefox": "browser", "chromium": "browser", "google-chrome": "browser",
    "brave-browser": "browser", "vivaldi": "browser", "zen": "browser",
    # Editors
    "code": "editor", "code-oss": "editor", "vscodium": "editor",
    "jetbrains-pycharm": "editor", "jetbrains-idea": "editor",
    "gnome-text-editor": "editor", "kate": "editor", "zed": "editor",
    # Terminals
    "kitty": "terminal", "alacritty": "terminal", "wezterm": "terminal",
    "foot": "terminal", "gnome-terminal": "terminal", "ghostty": "terminal",
    # Media
    "vlc": "media", "mpv": "media", "spotify": "media", "celluloid": "media",
    # Creative
    "blender": "creative", "gimp": "creative", "krita": "creative",
    "inkscape": "creative", "figma": "creative", "obs": "creative",
}

_ALIASES = {
    "google-chrome-stable": "google-chrome",
    "chromium-browser": "chromium",
    "code - oss": "code-oss",
    "visual studio code": "code",
    "gnome-terminal-server": "gnome-terminal",
}


def normalize_app_id(app_class: str) -> str:
    """Normalise a raw window class into a stable profile key.

    Pure helper — no Wayland / GTK dependency, so it's unit-testable.
    """
    app_class = app_class.lower().strip()
    return _ALIASES.get(app_class, app_class)


def resolve_profile(config: Config, app_id: str) -> RingProfile:
    """Resolve the active :class:`RingProfile` for ``app_id`` against
    ``config``. Pure helper — no I/O, so it's unit-testable.

    Resolution order: explicit per-app profile → category template →
    the ``default`` profile.
    """
    if app_id in config.ring_profiles:
        return config.ring_profiles[app_id]

    if category := APP_CATEGORIES.get(app_id):
        template = CATEGORY_TEMPLATES.get(category)
        if template:
            return RingProfile(
                app_id=app_id, app_name=app_id.title(),
                slices=[ActionSlice(**s.__dict__) for s in template],
            )

    return config.ring_profiles.get("default") or RingProfile(app_id="default")


def merge_button_bindings(global_bindings: list[ButtonBinding],
                          profile: RingProfile) -> list[ButtonBinding]:
    """Overlay a profile's per-app button overrides on the global bindings.

    Pure helper — per-CID, the per-app override wins. Unit-testable.
    """
    by_cid = {b.cid: b for b in global_bindings}
    for ov in getattr(profile, "button_overrides", None) or []:
        by_cid[ov.cid] = ov
    return list(by_cid.values())


class ProfileManager:
    """Resolves the active ring profile + button overrides for the
    focused window. Re-reads the live config on every lookup so reloads
    are picked up without re-wiring."""

    def __init__(self, store: ConfigStore):
        # Hold the STORE, not a captured Config — fixes the stale-config
        # bug where a reload swapped in a fresh Config the manager never
        # saw.
        self._store = store
        self._watcher: Optional[HyprlandFocusWatcher] = None

        # Fallback subprocess-polling cache
        self._cache_value = "default"
        self._cache_time = 0.0
        self._CACHE_TTL = 0.4

    @property
    def config(self) -> Config:
        return self._store.config

    # ─── lifecycle ──────────────────────────────────────────────────────

    def start(self, on_change=None) -> None:
        if self._watcher is not None:
            return
        self._watcher = HyprlandFocusWatcher(on_change or (lambda *_: None))
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
                return normalize_app_id(app_class)

        now = time.monotonic()
        if now - self._cache_time < self._CACHE_TTL:
            return self._cache_value

        app_id = self._probe_focus()
        self._cache_value = app_id
        self._cache_time = now
        return app_id

    def current_profile(self) -> RingProfile:
        return resolve_profile(self.config, self.current_app_id())

    def current_button_bindings(self) -> list[ButtonBinding]:
        """Button bindings active for the focused window.

        Global ``config.button_bindings`` overlaid with the focused app's
        ``RingProfile.button_overrides`` (per-CID; the per-app binding wins).
        So the same physical button can do different things per application.
        """
        return merge_button_bindings(
            self.config.button_bindings, self.current_profile())

    def current_app_button_bindings(self, app_id: str) -> list[ButtonBinding]:
        """Pure variant for tests: resolve bindings for an explicit app_id."""
        return merge_button_bindings(
            self.config.button_bindings, resolve_profile(self.config, app_id))

    # ─── helpers ────────────────────────────────────────────────────────

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
                    return normalize_app_id(parser(r.stdout))
                except Exception:
                    continue
        return "default"

    @staticmethod
    def _parse_hyprctl(out: str) -> str:
        data = json.loads(out)
        return data.get("class", "") or ""
