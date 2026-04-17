"""
Preferences Dialog

Configure application-level settings.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PreferencesDialog(Adw.PreferencesWindow):
    """
    Application preferences dialog using Adwaita.

    Settings:
    - Theme (dark/light/system)
    - Autostart on login
    - Start minimized
    - System tray icon
    """

    def __init__(self, parent, config_manager):
        super().__init__()

        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_title("Preferences")
        self.set_default_size(500, 400)

        self.config_manager = config_manager
        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        """Build the preferences UI"""
        # General page
        general_page = Adw.PreferencesPage()
        general_page.set_title("General")
        general_page.set_icon_name("preferences-system-symbolic")
        self.add(general_page)

        # Appearance group
        appearance_group = Adw.PreferencesGroup()
        appearance_group.set_title("Appearance")
        appearance_group.set_description("Configure the application theme")
        general_page.add(appearance_group)

        # Theme selector
        self.theme_row = Adw.ComboRow()
        self.theme_row.set_title("Theme")
        self.theme_row.set_subtitle("Choose the application color scheme")

        theme_model = Gtk.StringList.new(["Dark", "Light", "System"])
        self.theme_row.set_model(theme_model)
        self.theme_row.connect("notify::selected", self._on_theme_changed)
        appearance_group.add(self.theme_row)

        # Startup group
        startup_group = Adw.PreferencesGroup()
        startup_group.set_title("Startup")
        startup_group.set_description("Configure startup behavior")
        general_page.add(startup_group)

        # Autostart
        self.autostart_row = Adw.SwitchRow()
        self.autostart_row.set_title("Start on Login")
        self.autostart_row.set_subtitle("Automatically launch MX4Control when you log in")
        self.autostart_row.connect("notify::active", self._on_autostart_changed)
        startup_group.add(self.autostart_row)

        # Start minimized
        self.minimized_row = Adw.SwitchRow()
        self.minimized_row.set_title("Start Minimized")
        self.minimized_row.set_subtitle("Start the application minimized to the system tray")
        self.minimized_row.connect("notify::active", self._on_minimized_changed)
        startup_group.add(self.minimized_row)

        # System tray group
        tray_group = Adw.PreferencesGroup()
        tray_group.set_title("System Tray")
        tray_group.set_description("Configure system tray integration")
        general_page.add(tray_group)

        # Show tray icon
        self.tray_row = Adw.SwitchRow()
        self.tray_row.set_title("Show Tray Icon")
        self.tray_row.set_subtitle("Display an icon in the system tray for quick access")
        self.tray_row.connect("notify::active", self._on_tray_changed)
        tray_group.add(self.tray_row)

    def _load_settings(self):
        """Load current settings from config"""
        try:
            config = self.config_manager.config

            # Theme
            theme_map = {"dark": 0, "light": 1, "system": 2}
            self.theme_row.set_selected(theme_map.get(config.theme, 0))

            # Startup
            self.autostart_row.set_active(config.autostart)
            self.minimized_row.set_active(config.start_minimized)

            # Tray
            self.tray_row.set_active(config.show_tray_icon)

        except Exception as e:
            logger.error(f"Failed to load preferences: {e}")

    def _on_theme_changed(self, row, pspec):
        """Handle theme change"""
        themes = ["dark", "light", "system"]
        theme = themes[row.get_selected()]

        try:
            self.config_manager.config.theme = theme
            self.config_manager.save()

            # Apply theme to application
            style_manager = Adw.StyleManager.get_default()
            if theme == "dark":
                style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
            elif theme == "light":
                style_manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
            else:
                style_manager.set_color_scheme(Adw.ColorScheme.PREFER_DARK)

            logger.info(f"Theme changed to: {theme}")

        except Exception as e:
            logger.error(f"Failed to save theme setting: {e}")

    def _on_autostart_changed(self, row, pspec):
        """Handle autostart change"""
        enabled = row.get_active()

        try:
            self.config_manager.config.autostart = enabled
            self.config_manager.save()

            # Create/remove autostart desktop entry
            self._set_autostart(enabled)

            logger.info(f"Autostart {'enabled' if enabled else 'disabled'}")

        except Exception as e:
            logger.error(f"Failed to save autostart setting: {e}")

    def _on_minimized_changed(self, row, pspec):
        """Handle start minimized change"""
        enabled = row.get_active()

        try:
            self.config_manager.config.start_minimized = enabled
            self.config_manager.save()
            logger.info(f"Start minimized: {enabled}")

        except Exception as e:
            logger.error(f"Failed to save minimized setting: {e}")

    def _on_tray_changed(self, row, pspec):
        """Handle tray icon change"""
        enabled = row.get_active()

        try:
            self.config_manager.config.show_tray_icon = enabled
            self.config_manager.save()
            logger.info(f"Tray icon: {enabled}")

        except Exception as e:
            logger.error(f"Failed to save tray setting: {e}")

    def _set_autostart(self, enabled: bool):
        """Create or remove autostart desktop entry"""
        import os

        autostart_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart"
        autostart_file = autostart_dir / "mx4control.desktop"

        if enabled:
            autostart_dir.mkdir(parents=True, exist_ok=True)

            desktop_entry = """[Desktop Entry]
Type=Application
Name=MX4Control
Comment=Logitech MX Master 4 Configuration
Exec=mx4control
Icon=input-mouse
Terminal=false
Categories=Settings;HardwareSettings;
X-GNOME-Autostart-enabled=true
"""
            try:
                autostart_file.write_text(desktop_entry)
                logger.info(f"Created autostart entry: {autostart_file}")
            except Exception as e:
                logger.error(f"Failed to create autostart entry: {e}")
        else:
            try:
                if autostart_file.exists():
                    autostart_file.unlink()
                    logger.info(f"Removed autostart entry: {autostart_file}")
            except Exception as e:
                logger.error(f"Failed to remove autostart entry: {e}")
