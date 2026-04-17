"""mx4-settings — Adw.Application wrapper."""

from __future__ import annotations

import logging
import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio

from ..common.logging import configure as configure_logging
from ..common.ipc import DaemonClient
from .window import SettingsWindow

logger = logging.getLogger("mx4.ui")

APP_ID = "io.github.mx4control.settings"


class SettingsApplication(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.client = DaemonClient()
        self.window: SettingsWindow | None = None

    def do_activate(self) -> None:
        Adw.Application.do_activate(self)
        # Force the dark, libadwaita-styled scheme consistent with the rest
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.PREFER_DARK)

        if self.window is None:
            self.window = SettingsWindow(application=self, client=self.client)
        self.window.present()


def main() -> int:
    configure_logging("INFO", component="mx4-settings")
    app = SettingsApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
