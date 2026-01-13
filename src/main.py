#!/usr/bin/env python3
"""
MX4Control - Logitech MX Master 4 Configuration for Linux

A gorgeous GTK4/Libadwaita application for configuring the
MX Master 4 mouse with full feature support including haptic
feedback, Actions Ring, and per-application profiles.
"""

import sys
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gio

from application import MX4ControlApplication


def main():
    """Application entry point"""
    app = MX4ControlApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
