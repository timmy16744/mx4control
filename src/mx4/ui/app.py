"""mx4-settings entrypoint — launches MX4 Studio 3D (with ``--gtk`` fallback)."""

from __future__ import annotations

import logging
import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio

from ..common.dbus import AgentClient, SystemClient
from ..common.logging import configure as configure_logging
from .window import SettingsWindow

logger = logging.getLogger("mx4.ui")

APP_ID = "io.github.mx4control.settings"


class SettingsApplication(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.client = SystemClient()
        self.agent = AgentClient()
        self.window: SettingsWindow | None = None

    def do_activate(self) -> None:
        Adw.Application.do_activate(self)
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.PREFER_DARK)
        if self.window is None:
            self.window = SettingsWindow(
                application=self, client=self.client, agent=self.agent,
            )
        self.window.present()


def main() -> int:
    # Default to the 2027 3D WebGL Studio when PySide6 QtWebEngine is available;
    # pass ``--gtk`` to open the classic Libadwaita window instead.
    if "--gtk" not in sys.argv:
        try:
            from .studio_app import main as studio_main
            return studio_main(sys.argv)
        except Exception as e:
            logger.warning("3D Studio unavailable (%s); falling back to GTK4", e)

    configure_logging("INFO", component="mx4-settings")
    app = SettingsApplication()
    return app.run([a for a in sys.argv if a != "--gtk"])


if __name__ == "__main__":
    sys.exit(main())
