"""Main settings window.

Two-column layout modelled on v1:

    ┌─────────────┬──────────────────────────────────────┐
    │ MX4Control  │                                      │
    │ ─────────── │        Page content                  │
    │ 󰇘 Device    │                                      │
    │ 󰇘 Scroll    │                                      │
    │ 󰇘 Haptics   │                                      │
    │ 󰇘 Ring      │                                      │
    │             │                                      │
    │ [status]    │                                      │
    └─────────────┴──────────────────────────────────────┘

Below ~780 px the sidebar collapses into an overlay drawer (Adw handles
the transition via OverlaySplitView + Breakpoint). All CSS lives in
``data/css/style.css``; we prefer that over inline strings so it's
editable without a rebuild.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gio, Gtk, Adw, Gdk, GLib

from .pages.overview import OverviewPage
from .pages.ring import RingPage
from .pages.haptics import HapticsPage
from .pages.scroll import ScrollPage
from .widgets.nav import NavItem, SidebarNav

logger = logging.getLogger(__name__)


_CSS_LOCATIONS = [
    Path("/usr/share/mx4control/css/style.css"),
    Path(__file__).resolve().parents[3] / "data" / "css" / "style.css",
]


NAV_ITEMS = [
    NavItem("overview", "input-mouse-symbolic",        "Device",
            "Battery, DPI, hosts"),
    NavItem("scroll",   "view-continuous-symbolic",    "Scroll",
            "SmartShift & wheel"),
    NavItem("haptics",  "audio-speakers-symbolic",     "Haptics",
            "Feedback patterns"),
    NavItem("ring",     "view-app-grid-symbolic",      "Actions Ring",
            "Radial menu"),
]


def _load_css() -> None:
    provider = Gtk.CssProvider()
    for path in _CSS_LOCATIONS:
        if path.exists():
            provider.load_from_path(str(path))
            break
    else:
        logger.warning("no mx4 stylesheet found in %s", _CSS_LOCATIONS)
        return
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


class SettingsWindow(Adw.ApplicationWindow):
    def __init__(self, *, application, client):
        super().__init__(application=application, title="MX4Control")
        self.client = client

        _load_css()

        self.set_default_size(980, 740)
        self.set_size_request(420, 540)
        self.add_css_class("mx4-window")

        # Toast overlay wraps everything
        toast = Adw.ToastOverlay()
        self.set_content(toast)
        self.toast_overlay = toast

        # Adw.OverlaySplitView auto-collapses on narrow widths
        split = Adw.OverlaySplitView()
        split.set_sidebar_width_fraction(0.24)
        split.set_min_sidebar_width(230)
        split.set_max_sidebar_width(280)
        split.set_show_sidebar(True)
        toast.set_child(split)
        self.split_view = split

        # ─── Sidebar ────────────────────────────────────────────────
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sidebar.add_css_class("mx4-sidebar")
        split.set_sidebar(sidebar)

        brand = Gtk.Label(label="MX4Control", xalign=0)
        brand.add_css_class("mx4-brand")
        sidebar.append(brand)

        brand_sub = Gtk.Label(label="MX Master 4 Configuration", xalign=0)
        brand_sub.add_css_class("mx4-brand-subtitle")
        sidebar.append(brand_sub)

        sep = Gtk.Box()
        sep.add_css_class("mx4-sidebar-sep")
        sidebar.append(sep)

        self.nav = SidebarNav(NAV_ITEMS, on_selected=self._select_page)
        sidebar.append(self.nav)

        spacer = Gtk.Box(vexpand=True)
        sidebar.append(spacer)

        # Status footer
        status = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        status.add_css_class("mx4-status-footer")
        sidebar.append(status)

        self.status_dot = Gtk.Box()
        self.status_dot.set_size_request(10, 10)
        self.status_dot.add_css_class("mx4-status-dot")
        self.status_dot.add_css_class("searching")
        self.status_dot.set_valign(Gtk.Align.CENTER)
        status.append(self.status_dot)

        status_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                              hexpand=True)
        status.append(status_text)
        self.status_title = Gtk.Label(label="Searching…", xalign=0)
        self.status_title.add_css_class("mx4-status-title")
        status_text.append(self.status_title)
        self.status_sub = Gtk.Label(label="—", xalign=0)
        self.status_sub.add_css_class("mx4-status-sub")
        status_text.append(self.status_sub)

        # ─── Content area: header + stack ───────────────────────────
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.add_css_class("mx4-content-root")
        split.set_content(content)

        header = Adw.HeaderBar()
        header.set_show_title(False)

        self.sidebar_toggle = Gtk.ToggleButton()
        self.sidebar_toggle.set_icon_name("sidebar-show-symbolic")
        self.sidebar_toggle.add_css_class("flat")
        self.sidebar_toggle.set_visible(False)
        self.sidebar_toggle.set_tooltip_text("Toggle sidebar")
        self.sidebar_toggle.connect("toggled", self._on_sidebar_toggle)
        header.pack_start(self.sidebar_toggle)

        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh.add_css_class("flat")
        refresh.set_tooltip_text("Reload state")
        refresh.connect("clicked", lambda _b: self._refresh_all())
        header.pack_end(refresh)

        content.append(header)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(180)
        self.stack.add_css_class("mx4-content")
        content.append(self.stack)

        # ─── Pages ──────────────────────────────────────────────────
        self.pages = {
            "overview": OverviewPage(client),
            "scroll":   ScrollPage(client),
            "haptics":  HapticsPage(client),
            "ring":     RingPage(client),
        }
        for name, page in self.pages.items():
            scrolled = Gtk.ScrolledWindow()
            # Allow horizontal scroll too — pages with wide rows (pattern
            # flowbox etc.) should scroll rather than clip, and we'll
            # still favour vertical stacking whenever possible.
            scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scrolled.set_propagate_natural_width(False)
            scrolled.set_propagate_natural_height(True)
            scrolled.set_hexpand(True)
            scrolled.set_vexpand(True)
            scrolled.set_child(page)
            self.stack.add_named(scrolled, name)

        # Default page
        self.stack.set_visible_child_name("overview")

        # ─── Breakpoint: collapse sidebar < 780sp ───────────────────
        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 780sp"))
        bp.add_setter(split, "collapsed", True)
        bp.add_setter(self.sidebar_toggle, "visible", True)
        self.add_breakpoint(bp)

        # ─── Status footer refresh loop ─────────────────────────────
        self._refresh_status()
        GLib.timeout_add_seconds(5, self._refresh_status_tick)

    # ─── navigation ─────────────────────────────────────────────────

    def _select_page(self, page_id: str) -> None:
        # SidebarNav emits row-selected during its own __init__ (before
        # the window has finished building the stack) — ignore that.
        if not hasattr(self, "stack"):
            return
        self.stack.set_visible_child_name(page_id)
        # Auto-close the drawer when a page is picked on narrow widths
        if self.split_view.get_collapsed():
            self.split_view.set_show_sidebar(False)
            self.sidebar_toggle.set_active(False)

    def _on_sidebar_toggle(self, btn):
        self.split_view.set_show_sidebar(btn.get_active())

    # ─── status footer polling ──────────────────────────────────────

    def _refresh_status_tick(self) -> bool:
        self._refresh_status()
        return True

    def _refresh_status(self) -> None:
        def fetch():
            try:
                state = self.client.state()
            except Exception as e:
                state = {"connected": False, "error": str(e)}
            GLib.idle_add(self._apply_status, state)
        threading.Thread(target=fetch, daemon=True).start()

    def _apply_status(self, state: dict) -> bool:
        dot = self.status_dot
        for cls in ("connected", "disconnected", "searching"):
            dot.remove_css_class(cls)

        if state.get("connected"):
            dot.add_css_class("connected")
            name = state.get("friendly_name") or state.get("name", "MX Master 4")
            self.status_title.set_text(name)
            bits = [f"{state.get('battery', 0)}%"]
            if state.get("charging"):
                bits.append("charging")
            bits.append(state.get("connection", "bolt"))
            self.status_sub.set_text(" · ".join(bits))
        else:
            dot.add_css_class("disconnected")
            self.status_title.set_text("Not connected")
            self.status_sub.set_text("mx4d not running?")
        return False

    def _refresh_all(self) -> None:
        """Manually re-query state on every page that supports it."""
        for p in self.pages.values():
            if hasattr(p, "refresh"):
                try:
                    p.refresh()
                except Exception as e:
                    logger.debug(f"page refresh failed: {e}")
        self._refresh_status()

    # Shown via Adw.Toast for anything the pages want to surface
    def toast(self, message: str, timeout: int = 3) -> None:
        t = Adw.Toast.new(message)
        t.set_timeout(timeout)
        self.toast_overlay.add_toast(t)
