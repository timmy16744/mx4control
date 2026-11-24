"""Main settings window for MX4Control 1.0."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk

from ..common.dbus import DaemonUnavailable
from .pages.buttons import ButtonsPage
from .pages.diagnostics import DiagnosticsPage
from .pages.haptics import HapticsPage
from .pages.overview import OverviewPage
from .pages.ring import RingPage
from .pages.scroll import ScrollPage
from .widgets.nav import NavItem, SidebarNav

logger = logging.getLogger(__name__)


_CSS_LOCATIONS = [
    Path("/usr/share/mx4control/css/style.css"),
    Path(__file__).resolve().parents[3] / "data" / "css" / "style.css",
]


NAV_ITEMS = [
    NavItem("overview",    "input-mouse-symbolic",          "Device",       "Battery, DPI, hosts"),
    NavItem("scroll",      "view-continuous-symbolic",      "Scroll",       "MagSpeed & thumb wheel"),
    NavItem("haptics",     "audio-speakers-symbolic",       "Haptics",      "Motor, force & waves"),
    NavItem("ring",        "view-app-grid-symbolic",        "Actions Ring", "Profiles & slices"),
    NavItem("buttons",     "input-gaming-symbolic",         "Buttons",      "Global & per-app"),
    NavItem("diagnostics", "utilities-system-monitor-symbolic", "Diagnostics", "Health & HID++ probe"),
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
    display = Gdk.Display.get_default()
    if display is None:
        logger.warning("no default display; CSS not applied")
        return
    add = getattr(Gtk, "style_context_add_provider_for_display", None)
    if callable(add):
        add(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    else:
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )


class SettingsWindow(Adw.ApplicationWindow):
    def __init__(self, *, application, client, agent=None):
        super().__init__(application=application, title="MX4Control")
        self.client = client
        self.agent = agent

        _load_css()

        self.set_default_size(1040, 780)
        self.set_size_request(440, 560)
        self.add_css_class("mx4-window")

        toast = Adw.ToastOverlay()
        self.set_content(toast)
        self.toast_overlay = toast

        split = Adw.OverlaySplitView()
        split.set_sidebar_width_fraction(0.24)
        split.set_min_sidebar_width(235)
        split.set_max_sidebar_width(285)
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

        brand_sub = Gtk.Label(label="MX Master 4 · v1.0", xalign=0)
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

        status_text = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True,
        )
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
        refresh.set_tooltip_text("Reload hardware state")
        refresh.connect("clicked", lambda _b: self._refresh_all())
        header.pack_end(refresh)

        content.append(header)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(160)
        self.stack.add_css_class("mx4-content")
        content.append(self.stack)

        # ─── Pages ──────────────────────────────────────────────────
        self.pages = {
            "overview":    OverviewPage(client, window=self),
            "scroll":      ScrollPage(client, window=self),
            "haptics":     HapticsPage(client, window=self),
            "ring":        RingPage(client, window=self),
            "buttons":     ButtonsPage(client, window=self),
            "diagnostics": DiagnosticsPage(client, window=self),
        }
        for name, page in self.pages.items():
            scrolled = Gtk.ScrolledWindow()
            scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scrolled.set_propagate_natural_width(False)
            scrolled.set_propagate_natural_height(True)
            scrolled.set_hexpand(True)
            scrolled.set_vexpand(True)
            scrolled.set_child(page)
            self.stack.add_named(scrolled, name)

        self.stack.set_visible_child_name("overview")

        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 780sp"))
        bp.add_setter(split, "collapsed", True)
        bp.add_setter(self.sidebar_toggle, "visible", True)
        self.add_breakpoint(bp)

        # Subscribe to real-time D-Bus signals (button presses, state deltas, reconnects)
        try:
            self.client.subscribe_signals(
                on_diverted=self._on_live_buttons,
                on_state_changed=self._on_state_changed,
                on_connected=lambda _c, _i: self._refresh_all(),
                on_disconnected=self._refresh_all,
            )
        except Exception as e:
            logger.debug("D-Bus signal subscribe skipped: %s", e)

        self._refresh_status()
        GLib.timeout_add_seconds(10, self._refresh_status_tick)

    # ─── live D-Bus signal fan-out ──────────────────────────────────

    def _on_live_buttons(self, cids: set[int]) -> None:
        overview = self.pages.get("overview")
        if overview is not None and hasattr(overview, "set_pressed_cids"):
            overview.set_pressed_cids(cids)

    def _on_state_changed(self, delta: dict[str, Any]) -> None:
        for page in self.pages.values():
            if hasattr(page, "apply_state_delta"):
                try:
                    page.apply_state_delta(delta)
                except Exception:
                    pass
        if any(k in delta for k in ("battery", "charging", "connected", "friendly_name")):
            self._refresh_status()

    # ─── navigation ─────────────────────────────────────────────────

    def _select_page(self, page_id: str) -> None:
        if not hasattr(self, "stack"):
            return
        self.stack.set_visible_child_name(page_id)
        page = self.pages.get(page_id)
        if page is not None and hasattr(page, "refresh"):
            try:
                page.refresh()
            except Exception:
                pass
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
                state = self.client.get_state()
            except DaemonUnavailable:
                state = {"connected": False, "daemon": False}
            except Exception as e:
                state = {"connected": False, "error": str(e)}
            profile = ""
            if self.agent is not None:
                try:
                    prof = self.agent.get_active_profile()
                    profile = prof.get("app_name") or prof.get("app_id") or ""
                except Exception:
                    profile = ""
            GLib.idle_add(self._apply_status, state, profile)
        threading.Thread(target=fetch, daemon=True).start()

    def _apply_status(self, state: dict, profile: str = "") -> bool:
        dot = self.status_dot
        for cls in ("connected", "disconnected", "searching"):
            dot.remove_css_class(cls)

        if state.get("connected"):
            dot.add_css_class("connected")
            name = state.get("friendly_name") or state.get("name", "MX Master 4")
            self.status_title.set_text(str(name))
            bits = [f"{state.get('battery', 0)}%"]
            if state.get("charging"):
                bits.append("charging")
            bits.append(str(state.get("connection", "bolt")))
            if profile:
                bits.append(profile)
            self.status_sub.set_text(" · ".join(bits))
        else:
            dot.add_css_class("disconnected")
            if state.get("daemon") is False:
                self.status_title.set_text("Not connected")
                self.status_sub.set_text("mx4-sysd not running?")
            else:
                self.status_title.set_text("No device")
                self.status_sub.set_text("mouse not detected")
        return False

    def _refresh_all(self) -> None:
        for p in self.pages.values():
            if hasattr(p, "refresh"):
                try:
                    p.refresh()
                except Exception as e:
                    logger.debug("page refresh failed: %s", e)
        self._refresh_status()

    def toast(self, message: str, timeout: int = 3) -> None:
        t = Adw.Toast.new(message)
        t.set_timeout(timeout)
        self.toast_overlay.add_toast(t)
