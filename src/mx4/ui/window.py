"""Main settings window — thin Adw.ApplicationWindow with two pages."""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

from .pages.overview import OverviewPage
from .pages.ring import RingPage


class SettingsWindow(Adw.ApplicationWindow):
    def __init__(self, *, application, client):
        super().__init__(application=application, title="MX4 Control")
        self.client = client

        self.set_default_size(720, 720)
        self.set_size_request(360, 520)

        # Simple ViewStack-based navigation — no custom sidebar. The
        # inherent libadwaita responsiveness handles narrow/wide.
        toast_overlay = Adw.ToastOverlay()
        self.set_content(toast_overlay)

        toolbar = Adw.ToolbarView()
        toast_overlay.set_child(toolbar)

        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        view_stack = Adw.ViewStack()
        toolbar.set_content(view_stack)

        switcher = Adw.ViewSwitcher()
        switcher.set_stack(view_stack)
        switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)

        # Pages
        overview = OverviewPage(client)
        ring = RingPage(client)
        view_stack.add_titled_with_icon(overview, "overview", "Device", "input-mouse-symbolic")
        view_stack.add_titled_with_icon(ring, "ring", "Actions Ring", "view-app-grid-symbolic")

        # A bottom view-switcher for narrow widths
        bottom_switcher = Adw.ViewSwitcherBar()
        bottom_switcher.set_stack(view_stack)
        toolbar.add_bottom_bar(bottom_switcher)

        # Breakpoint: hide the top switcher and show the bottom one when narrow
        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 520sp"))
        bp.add_setter(switcher, "visible", False)
        bp.add_setter(bottom_switcher, "reveal", True)
        self.add_breakpoint(bp)
