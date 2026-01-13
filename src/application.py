"""
MX4Control Application

Main Adw.Application subclass that manages the application lifecycle,
theming, and global services.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, Gio, GLib
from pathlib import Path
import logging

from window import MX4ControlWindow
from core.config import ConfigManager

logger = logging.getLogger(__name__)

APP_ID = "io.github.mx4control"
APP_NAME = "MX4Control"
APP_VERSION = "1.0.0"


class MX4ControlApplication(Adw.Application):
    """
    Main application class

    Handles:
    - Application lifecycle
    - Theme management
    - Global keyboard shortcuts
    - D-Bus activation
    """

    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

        self.config_manager = ConfigManager()
        self.window = None

        # Set up application actions
        self._setup_actions()

    def _setup_actions(self):
        """Configure application actions"""
        # Quit action
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", self._on_quit)
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Ctrl>q"])

        # About action
        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self._on_about)
        self.add_action(about_action)

        # Preferences action
        prefs_action = Gio.SimpleAction.new("preferences", None)
        prefs_action.connect("activate", self._on_preferences)
        self.add_action(prefs_action)
        self.set_accels_for_action("app.preferences", ["<Ctrl>comma"])

    def do_startup(self):
        """Called when the application starts"""
        Adw.Application.do_startup(self)

        # Load custom CSS
        self._load_css()

        # Configure color scheme based on settings
        style_manager = Adw.StyleManager.get_default()
        theme = self.config_manager.config.theme

        if theme == "dark":
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        elif theme == "light":
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        else:
            style_manager.set_color_scheme(Adw.ColorScheme.PREFER_DARK)

    def _load_css(self):
        """Load custom application CSS"""
        css_provider = Gtk.CssProvider()

        # Try to load from installed location first, then development
        css_paths = [
            Path("/usr/share/mx4control/css/style.css"),
            Path(__file__).parent.parent / "data" / "css" / "style.css",
        ]

        css_loaded = False
        for css_path in css_paths:
            if css_path.exists():
                css_provider.load_from_path(str(css_path))
                logger.info(f"Loaded CSS from {css_path}")
                css_loaded = True
                break

        if not css_loaded:
            # Use inline CSS if no file found
            css_provider.load_from_string(self._get_inline_css())

        # Apply CSS to default display
        from gi.repository import Gdk
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _get_inline_css(self) -> str:
        """Return inline CSS for the application"""
        return '''
/* ═══════════════════════════════════════════════════════════════════
   MX4Control - Industrial Precision meets Haptic Warmth
   A GTK4/Libadwaita theme for premium hardware control
   ═══════════════════════════════════════════════════════════════════ */

/* ─────────────────────────────────────────────────────────────────────
   Color Variables
   ───────────────────────────────────────────────────────────────────── */

@define-color bg_primary #1a1a1d;
@define-color bg_secondary #232326;
@define-color bg_elevated #2d2d32;
@define-color bg_card #28282d;

@define-color accent_primary #d4a574;
@define-color accent_secondary #4ecdc4;
@define-color accent_glow rgba(212, 165, 116, 0.3);
@define-color accent_glow_strong rgba(212, 165, 116, 0.5);

@define-color text_primary #f0ece8;
@define-color text_secondary #8a8a8f;
@define-color text_muted #5a5a5f;

@define-color success #4ade80;
@define-color warning #fbbf24;
@define-color error #f87171;

@define-color border_subtle rgba(255, 255, 255, 0.06);
@define-color border_hover rgba(212, 165, 116, 0.4);

/* ─────────────────────────────────────────────────────────────────────
   Window & Layout
   ───────────────────────────────────────────────────────────────────── */

window.main-window {
    background-color: @bg_primary;
}

.main-content {
    background-color: @bg_primary;
}

/* Navigation sidebar */
.navigation-sidebar {
    background-color: @bg_secondary;
    border-right: 1px solid @border_subtle;
    padding: 12px;
}

.navigation-sidebar row {
    border-radius: 8px;
    margin: 2px 0;
    padding: 12px 16px;
    transition: all 200ms ease;
}

.navigation-sidebar row:hover {
    background-color: @bg_elevated;
}

.navigation-sidebar row:selected {
    background: linear-gradient(135deg, rgba(212, 165, 116, 0.15) 0%, rgba(212, 165, 116, 0.08) 100%);
    border: 1px solid @border_hover;
}

.navigation-sidebar row:selected label {
    color: @accent_primary;
}

/* ─────────────────────────────────────────────────────────────────────
   Cards & Containers
   ───────────────────────────────────────────────────────────────────── */

.settings-card {
    background-color: @bg_card;
    border-radius: 16px;
    border: 1px solid @border_subtle;
    padding: 24px;
    margin: 8px;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3),
                inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

.settings-card:hover {
    border-color: @border_hover;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4),
                0 0 0 1px @accent_glow,
                inset 0 1px 0 rgba(255, 255, 255, 0.05);
}

/* Device preview card - larger, prominent */
.device-card {
    background: linear-gradient(180deg, @bg_elevated 0%, @bg_card 100%);
    border-radius: 20px;
    border: 1px solid @border_subtle;
    padding: 32px;
    min-height: 300px;
}

/* ─────────────────────────────────────────────────────────────────────
   Typography
   ───────────────────────────────────────────────────────────────────── */

.page-title {
    font-family: "JetBrains Mono", "IBM Plex Mono", monospace;
    font-size: 28px;
    font-weight: 700;
    color: @text_primary;
    letter-spacing: -0.5px;
}

.section-title {
    font-family: "Overpass", "Outfit", sans-serif;
    font-size: 13px;
    font-weight: 600;
    color: @accent_primary;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    margin-bottom: 16px;
}

.card-title {
    font-family: "Overpass", "Outfit", sans-serif;
    font-size: 16px;
    font-weight: 600;
    color: @text_primary;
}

.card-description {
    font-size: 13px;
    color: @text_secondary;
}

.value-label {
    font-family: "JetBrains Mono", "IBM Plex Mono", monospace;
    font-size: 24px;
    font-weight: 700;
    color: @accent_primary;
}

.unit-label {
    font-family: "JetBrains Mono", monospace;
    font-size: 12px;
    color: @text_muted;
    text-transform: uppercase;
}

/* ─────────────────────────────────────────────────────────────────────
   Buttons
   ───────────────────────────────────────────────────────────────────── */

.copper-button {
    background: linear-gradient(180deg, @accent_primary 0%, #c49a6c 100%);
    color: @bg_primary;
    border: none;
    border-radius: 8px;
    padding: 12px 24px;
    font-weight: 600;
    box-shadow: 0 4px 12px rgba(212, 165, 116, 0.3),
                inset 0 1px 0 rgba(255, 255, 255, 0.2);
    transition: all 150ms ease;
}

.copper-button:hover {
    background: linear-gradient(180deg, #e0b584 0%, #d4a574 100%);
    box-shadow: 0 6px 20px rgba(212, 165, 116, 0.4),
                inset 0 1px 0 rgba(255, 255, 255, 0.3);
    transform: translateY(-1px);
}

.copper-button:active {
    transform: translateY(1px);
    box-shadow: 0 2px 8px rgba(212, 165, 116, 0.3);
}

.ghost-button {
    background: transparent;
    color: @text_secondary;
    border: 1px solid @border_subtle;
    border-radius: 8px;
    padding: 10px 20px;
    transition: all 150ms ease;
}

.ghost-button:hover {
    color: @accent_primary;
    border-color: @accent_primary;
    background: @accent_glow;
}

.icon-button {
    background: @bg_elevated;
    border: 1px solid @border_subtle;
    border-radius: 12px;
    min-width: 48px;
    min-height: 48px;
    transition: all 150ms ease;
}

.icon-button:hover {
    background: @accent_glow;
    border-color: @accent_primary;
}

/* ─────────────────────────────────────────────────────────────────────
   Sliders & Controls
   ───────────────────────────────────────────────────────────────────── */

scale {
    padding: 8px 0;
}

scale trough {
    background: @bg_secondary;
    border-radius: 4px;
    min-height: 8px;
}

scale highlight {
    background: linear-gradient(90deg, @accent_primary 0%, @accent_secondary 100%);
    border-radius: 4px;
}

scale slider {
    background: @accent_primary;
    border: 2px solid @bg_primary;
    border-radius: 50%;
    min-width: 24px;
    min-height: 24px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3),
                0 0 0 4px @accent_glow;
    transition: all 150ms ease;
}

scale slider:hover {
    background: #e0b584;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.4),
                0 0 0 6px @accent_glow_strong;
}

/* DPI Slider - larger, more prominent */
.dpi-slider trough {
    min-height: 12px;
    border-radius: 6px;
}

.dpi-slider slider {
    min-width: 32px;
    min-height: 32px;
}

/* ─────────────────────────────────────────────────────────────────────
   Switches & Toggles
   ───────────────────────────────────────────────────────────────────── */

switch {
    background: @bg_secondary;
    border: 1px solid @border_subtle;
    border-radius: 16px;
    min-width: 56px;
    min-height: 32px;
    transition: all 200ms ease;
}

switch:checked {
    background: linear-gradient(135deg, @accent_primary 0%, #c49a6c 100%);
    border-color: @accent_primary;
}

switch slider {
    background: @text_primary;
    border-radius: 50%;
    min-width: 26px;
    min-height: 26px;
    margin: 2px;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

/* ─────────────────────────────────────────────────────────────────────
   Mouse Preview Widget
   ───────────────────────────────────────────────────────────────────── */

.mouse-preview {
    background: radial-gradient(ellipse at 50% 30%, @bg_elevated 0%, @bg_card 100%);
    border-radius: 24px;
    min-width: 200px;
    min-height: 300px;
}

.mouse-button {
    transition: all 150ms ease;
}

.mouse-button:hover {
    filter: brightness(1.2);
}

.mouse-button.active {
    box-shadow: 0 0 20px @accent_primary;
}

/* ─────────────────────────────────────────────────────────────────────
   Haptic Visualization
   ───────────────────────────────────────────────────────────────────── */

.haptic-ring {
    border: 2px solid @accent_primary;
    border-radius: 50%;
    opacity: 0;
}

.haptic-ring.pulse {
    animation: haptic-pulse 600ms ease-out;
}

@keyframes haptic-pulse {
    0% {
        opacity: 1;
        transform: scale(1);
    }
    100% {
        opacity: 0;
        transform: scale(2);
    }
}

.haptic-pattern-card {
    background: @bg_secondary;
    border-radius: 12px;
    padding: 16px;
    border: 1px solid @border_subtle;
    transition: all 150ms ease;
}

.haptic-pattern-card:hover {
    background: @bg_elevated;
    border-color: @accent_primary;
}

.haptic-pattern-card.selected {
    background: @accent_glow;
    border-color: @accent_primary;
    box-shadow: 0 0 20px @accent_glow;
}

/* ─────────────────────────────────────────────────────────────────────
   Actions Ring Preview
   ───────────────────────────────────────────────────────────────────── */

.actions-ring {
    background: radial-gradient(circle, @bg_elevated 0%, transparent 70%);
}

.ring-segment {
    fill: @bg_card;
    stroke: @border_subtle;
    stroke-width: 1px;
    transition: all 150ms ease;
}

.ring-segment:hover {
    fill: @accent_glow;
    stroke: @accent_primary;
}

.ring-segment.selected {
    fill: @accent_glow_strong;
    stroke: @accent_primary;
    stroke-width: 2px;
}

/* ─────────────────────────────────────────────────────────────────────
   Battery Indicator
   ───────────────────────────────────────────────────────────────────── */

.battery-indicator {
    background: @bg_secondary;
    border-radius: 8px;
    padding: 8px 16px;
    border: 1px solid @border_subtle;
}

.battery-level {
    background: linear-gradient(90deg, @success 0%, @success 100%);
    border-radius: 4px;
    min-height: 8px;
    transition: all 300ms ease;
}

.battery-level.charging {
    background: linear-gradient(90deg, @success 0%, @accent_primary 100%);
    animation: charging-pulse 2s ease-in-out infinite;
}

.battery-level.low {
    background: @warning;
}

.battery-level.critical {
    background: @error;
}

@keyframes charging-pulse {
    0%, 100% { opacity: 0.8; }
    50% { opacity: 1; }
}

/* ─────────────────────────────────────────────────────────────────────
   Scrollbars
   ───────────────────────────────────────────────────────────────────── */

scrollbar {
    background: transparent;
}

scrollbar slider {
    background: @text_muted;
    border-radius: 4px;
    min-width: 6px;
    transition: all 150ms ease;
}

scrollbar slider:hover {
    background: @accent_primary;
    min-width: 8px;
}

/* ─────────────────────────────────────────────────────────────────────
   Lists & Rows
   ───────────────────────────────────────────────────────────────────── */

.settings-row {
    padding: 16px;
    border-radius: 12px;
    margin: 4px 0;
    background: transparent;
    transition: all 150ms ease;
}

.settings-row:hover {
    background: @bg_secondary;
}

/* ─────────────────────────────────────────────────────────────────────
   Entry & Inputs
   ───────────────────────────────────────────────────────────────────── */

entry {
    background: @bg_secondary;
    border: 1px solid @border_subtle;
    border-radius: 8px;
    padding: 12px 16px;
    color: @text_primary;
    caret-color: @accent_primary;
    box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.1);
    transition: all 150ms ease;
}

entry:focus {
    border-color: @accent_primary;
    box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.1),
                0 0 0 3px @accent_glow;
}

/* ─────────────────────────────────────────────────────────────────────
   Noise Texture Overlay (applied to main window)
   ───────────────────────────────────────────────────────────────────── */

.noise-overlay {
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%' height='100%' filter='url(%23noise)'/%3E%3C/svg%3E");
    opacity: 0.02;
    pointer-events: none;
}

/* ─────────────────────────────────────────────────────────────────────
   Page Transitions
   ───────────────────────────────────────────────────────────────────── */

.page-content {
    animation: page-enter 300ms ease-out;
}

@keyframes page-enter {
    from {
        opacity: 0;
        transform: translateY(20px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

/* Staggered reveal for cards */
.settings-card:nth-child(1) { animation-delay: 0ms; }
.settings-card:nth-child(2) { animation-delay: 50ms; }
.settings-card:nth-child(3) { animation-delay: 100ms; }
.settings-card:nth-child(4) { animation-delay: 150ms; }

/* ─────────────────────────────────────────────────────────────────────
   Status Indicators
   ───────────────────────────────────────────────────────────────────── */

.status-dot {
    min-width: 10px;
    min-height: 10px;
    border-radius: 50%;
    background: @text_muted;
}

.status-dot.connected {
    background: @success;
    box-shadow: 0 0 8px @success;
}

.status-dot.disconnected {
    background: @error;
}

.status-dot.searching {
    background: @warning;
    animation: status-pulse 1s ease-in-out infinite;
}

@keyframes status-pulse {
    0%, 100% { opacity: 0.5; }
    50% { opacity: 1; }
}

/* ─────────────────────────────────────────────────────────────────────
   Toast Notifications
   ───────────────────────────────────────────────────────────────────── */

.toast {
    background: @bg_elevated;
    border: 1px solid @border_subtle;
    border-radius: 12px;
    padding: 16px 24px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
}

.toast.success {
    border-color: @success;
}

.toast.error {
    border-color: @error;
}
'''

    def do_activate(self):
        """Called when the application is activated"""
        # Create window if it doesn't exist
        if not self.window:
            self.window = MX4ControlWindow(application=self)

        # Present window
        self.window.present()

    def _on_quit(self, action, param):
        """Handle quit action"""
        self.quit()

    def _on_about(self, action, param):
        """Show about dialog"""
        about = Adw.AboutWindow(
            transient_for=self.window,
            application_name=APP_NAME,
            application_icon=APP_ID,
            developer_name="MX4Control Contributors",
            version=APP_VERSION,
            developers=["MX4Control Team"],
            copyright="© 2025 MX4Control Contributors",
            license_type=Gtk.License.MIT_X11,
            website="https://github.com/mx4control/mx4control",
            issue_url="https://github.com/mx4control/mx4control/issues",
            comments="Configure your Logitech MX Master 4 with style.\n\n"
                    "Features:\n"
                    "• Haptic feedback patterns\n"
                    "• Actions Ring radial menu\n"
                    "• 8 programmable buttons\n"
                    "• DPI and scroll settings\n"
                    "• Per-application profiles",
        )
        about.present()

    def _on_preferences(self, action, param):
        """Show preferences dialog"""
        # TODO: Implement preferences dialog
        pass
