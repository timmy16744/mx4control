"""
MX4Control Main Window

The primary application window with navigation sidebar and content area.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, GLib, Gio
import logging

from ui.pages.overview import OverviewPage
from ui.pages.buttons import ButtonsPage
from ui.pages.haptics import HapticsPage
from ui.pages.pointer import PointerPage
from ui.pages.scroll import ScrollPage
from ui.pages.actions_ring import ActionsRingPage
from core import MXMaster4, find_mx_master_4
from services import get_gesture_service

logger = logging.getLogger(__name__)


class MX4ControlWindow(Adw.ApplicationWindow):
    """
    Main application window

    Layout:
    ┌────────────┬──────────────────────────────────┐
    │            │                                  │
    │  Sidebar   │         Content Area             │
    │            │                                  │
    │  - Device  │   (Selected page content)        │
    │  - Buttons │                                  │
    │  - Haptics │                                  │
    │  - Pointer │                                  │
    │  - Scroll  │                                  │
    │  - Actions │                                  │
    │            │                                  │
    └────────────┴──────────────────────────────────┘
    """

    # How often to retry the device connection while disconnected.
    _RECONNECT_INTERVAL_MS = 3000
    # How often to poll the device for basic info to detect a dropped link.
    _HEALTH_CHECK_INTERVAL_MS = 10000
    # Declare the device dead only after this many consecutive health
    # probe failures. One transient HID++ timeout shouldn't disconnect.
    _HEALTH_CHECK_FAILURE_THRESHOLD = 3

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.device = None
        self._pages = {}
        self._gesture_service = None
        self._connecting = False
        self._reconnect_source_id = None
        self._health_source_id = None
        self._health_failures = 0  # consecutive failed probes
        self._last_connection_type = None
        self._last_charging_state = None

        # Get config manager from application
        self.config_manager = self.get_application().config_manager

        # Window setup — start wide but let Adw.Breakpoint collapse us below
        # 700px and stack panes vertically on the overview below 1050px.
        self.set_title("MX4Control")
        self.set_default_size(1200, 800)
        self.set_size_request(380, 520)
        self.add_css_class("main-window")

        # Build UI
        self._build_ui()

        # Responsive layout via Adw breakpoints
        self._setup_breakpoints()

        # Initialize gesture service
        self._init_gesture_service()

        # Try to connect to device
        GLib.idle_add(self._connect_device)

        # Handle window close
        self.connect("close-request", self._on_close_request)

    def _init_gesture_service(self):
        """Initialize the gesture service for Actions Ring"""
        try:
            self._gesture_service = get_gesture_service()
            result = self._gesture_service.initialize(self.config_manager.config)

            # Connect haptic callback to device
            self._gesture_service.on_haptic_trigger = self._trigger_haptic_from_gesture

            logger.info(f"Gesture service initialized: {result}")
        except Exception as e:
            logger.error(f"Failed to initialize gesture service: {e}")
            self._gesture_service = None

    def _trigger_haptic_from_gesture(self, pattern: int):
        """Trigger haptic feedback from gesture service"""
        if self.device:
            try:
                self.device.trigger_haptic(pattern)
            except Exception as e:
                logger.debug(f"Haptic trigger failed: {e}")

    def _on_close_request(self, window):
        """Handle window close"""
        self._cancel_reconnect()
        self._cancel_health_check()

        if self._gesture_service:
            self._gesture_service.stop()

        if self.device:
            try:
                self.device.close()
            except Exception:
                pass

        return False  # Allow close to proceed

    def _build_ui(self):
        """Construct the window UI using Adw.OverlaySplitView for a
        collapsible sidebar that switches to an overlay drawer on narrow
        widths (Adw.Breakpoint drives the ``collapsed`` property).
        """
        # Toast overlay wraps everything for notifications
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        # Responsive split: sidebar on wide, overlay drawer on narrow
        self.split_view = Adw.OverlaySplitView()
        self.split_view.set_sidebar_width_fraction(0.22)
        self.split_view.set_min_sidebar_width(240)
        self.split_view.set_max_sidebar_width(320)
        self.split_view.set_show_sidebar(True)
        self.toast_overlay.set_child(self.split_view)

        # Navigation sidebar (populates self.nav_list, self.status_dot, …)
        sidebar_widget = self._build_sidebar()
        self.split_view.set_sidebar(sidebar_widget)

        # Content area with header and page stack
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        content_box.add_css_class("main-content")
        self.split_view.set_content(content_box)

        # Header bar — gains a sidebar-toggle button when collapsed
        self.header_bar = self._build_header()
        content_box.append(self.header_bar)

        # Page stack
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(200)
        self.stack.set_vexpand(True)
        content_box.append(self.stack)

        # Create pages
        self._create_pages()

    def _setup_breakpoints(self):
        """Install Adw.Breakpoint instances so the layout adapts on resize.

        - Below 720px wide: sidebar collapses into an overlay drawer and
          the toggle button in the header becomes visible.
        - Below 1050px wide: the overview page stacks its preview and
          stats vertically (handled in OverviewPage._on_breakpoint).
        """
        # Narrow breakpoint — collapse sidebar into an overlay drawer
        narrow = Adw.Breakpoint.new(
            Adw.BreakpointCondition.parse("max-width: 820sp")
        )
        narrow.add_setter(self.split_view, "collapsed", True)
        narrow.add_setter(self.sidebar_toggle, "visible", True)
        narrow.connect("apply", lambda _b: self._on_narrow(True))
        narrow.connect("unapply", lambda _b: self._on_narrow(False))
        self.add_breakpoint(narrow)

        # Medium breakpoint — stack overview panes vertically. Set high
        # enough that the overview's horizontal layout never fights the
        # window size; anything below ~1300px wide goes to stacked.
        medium = Adw.Breakpoint.new(
            Adw.BreakpointCondition.parse("max-width: 1300sp")
        )
        medium.connect("apply", lambda _b: self._notify_pages_compact(True))
        medium.connect("unapply", lambda _b: self._notify_pages_compact(False))
        self.add_breakpoint(medium)

    def _on_narrow(self, narrow: bool):
        """Sidebar is now collapsed (narrow=True) or docked (narrow=False)."""
        if not narrow:
            # Leaving narrow mode: make sure sidebar is shown
            self.split_view.set_show_sidebar(True)

    def _notify_pages_compact(self, compact: bool):
        """Inform pages that we've crossed the 'compact' breakpoint."""
        for page in self._pages.values():
            if hasattr(page, "set_compact_layout"):
                try:
                    page.set_compact_layout(compact)
                except Exception as e:
                    logger.debug(f"page compact-layout switch failed: {e}")

    def show_toast(self, message: str, timeout: int = 3):
        """
        Show a toast notification to the user.

        Args:
            message: The message to display
            timeout: Duration in seconds (default 3)
        """
        toast = Adw.Toast.new(message)
        toast.set_timeout(timeout)
        self.toast_overlay.add_toast(toast)

    def show_error(self, message: str, timeout: int = 5):
        """
        Show an error toast notification.

        Args:
            message: The error message to display
            timeout: Duration in seconds (default 5)
        """
        toast = Adw.Toast.new(f"Error: {message}")
        toast.set_timeout(timeout)
        # Add a button to dismiss
        toast.set_button_label("Dismiss")
        self.toast_overlay.add_toast(toast)

    def _build_sidebar(self):
        """Build the navigation sidebar. Returns the sidebar widget so the
        caller can embed it in an Adw.OverlaySplitView.
        """
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar.add_css_class("navigation-sidebar")

        # Logo/Title area
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        title_box.set_margin_top(24)
        title_box.set_margin_bottom(24)
        title_box.set_margin_start(16)
        title_box.set_margin_end(16)
        sidebar.append(title_box)

        logo_label = Gtk.Label(label="MX4Control")
        logo_label.add_css_class("page-title")
        logo_label.set_halign(Gtk.Align.START)
        title_box.append(logo_label)

        version_label = Gtk.Label(label="MX Master 4 Configuration")
        version_label.add_css_class("card-description")
        version_label.set_halign(Gtk.Align.START)
        title_box.append(version_label)

        # Separator
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_start(16)
        separator.set_margin_end(16)
        sidebar.append(separator)

        # Navigation list
        self.nav_list = Gtk.ListBox()
        self.nav_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.nav_list.add_css_class("navigation-sidebar")
        self.nav_list.set_margin_top(12)
        self.nav_list.connect("row-selected", self._on_nav_selected)
        sidebar.append(self.nav_list)

        # Navigation items
        nav_items = [
            ("overview", "computer-symbolic", "Device", "Battery, connection, info"),
            ("buttons", "input-mouse-symbolic", "Buttons", "Configure 8 buttons"),
            ("haptics", "audio-speakers-symbolic", "Haptics", "Feedback patterns"),
            ("pointer", "input-tablet-symbolic", "Pointer", "DPI & sensitivity"),
            ("scroll", "view-continuous-symbolic", "Scroll", "SmartShift & wheel"),
            ("actions_ring", "view-app-grid-symbolic", "Actions Ring", "Radial menu"),
        ]

        for page_id, icon_name, title, subtitle in nav_items:
            row = self._create_nav_row(page_id, icon_name, title, subtitle)
            self.nav_list.append(row)

        # Select first row
        first_row = self.nav_list.get_row_at_index(0)
        if first_row:
            self.nav_list.select_row(first_row)

        # Spacer
        spacer = Gtk.Box(vexpand=True)
        sidebar.append(spacer)

        # Device status at bottom
        self.device_status = self._create_device_status()
        sidebar.append(self.device_status)

        return sidebar

    def _create_nav_row(self, page_id: str, icon_name: str,
                        title: str, subtitle: str) -> Gtk.ListBoxRow:
        """Create a navigation list row"""
        row = Gtk.ListBoxRow()
        row.page_id = page_id

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(12)
        box.set_margin_end(12)
        row.set_child(box)

        # Icon
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(24)
        icon.add_css_class("text_secondary")
        box.append(icon)

        # Text
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.append(text_box)

        title_label = Gtk.Label(label=title)
        title_label.set_halign(Gtk.Align.START)
        title_label.add_css_class("card-title")
        text_box.append(title_label)

        subtitle_label = Gtk.Label(label=subtitle)
        subtitle_label.set_halign(Gtk.Align.START)
        subtitle_label.add_css_class("card-description")
        text_box.append(subtitle_label)

        return row

    def _create_device_status(self) -> Gtk.Box:
        """Create the device status widget for the sidebar bottom"""
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        status_box.set_margin_start(16)
        status_box.set_margin_end(16)
        status_box.set_margin_bottom(16)
        status_box.set_margin_top(8)
        status_box.add_css_class("battery-indicator")

        # Status dot
        self.status_dot = Gtk.Box()
        self.status_dot.set_size_request(10, 10)
        self.status_dot.add_css_class("status-dot")
        self.status_dot.add_css_class("disconnected")
        self.status_dot.set_valign(Gtk.Align.CENTER)
        status_box.append(self.status_dot)

        # Status text
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        status_box.append(text_box)

        self.status_label = Gtk.Label(label="Searching...")
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.add_css_class("card-title")
        text_box.append(self.status_label)

        self.battery_label = Gtk.Label(label="--")
        self.battery_label.set_halign(Gtk.Align.START)
        self.battery_label.add_css_class("card-description")
        text_box.append(self.battery_label)

        return status_box

    def _build_header(self) -> Adw.HeaderBar:
        """Build the header bar"""
        header = Adw.HeaderBar()
        header.set_show_start_title_buttons(True)
        header.set_show_end_title_buttons(True)

        # Sidebar toggle — hidden by default, shown when the breakpoint
        # collapses the split view at narrow widths.
        self.sidebar_toggle = Gtk.ToggleButton()
        self.sidebar_toggle.set_icon_name("sidebar-show-symbolic")
        self.sidebar_toggle.add_css_class("flat")
        self.sidebar_toggle.set_tooltip_text("Toggle sidebar")
        self.sidebar_toggle.set_visible(False)
        self.sidebar_toggle.connect("toggled", self._on_sidebar_toggle)
        header.pack_start(self.sidebar_toggle)

        # Window title
        self.page_title = Gtk.Label(label="Device")
        self.page_title.add_css_class("page-title")
        header.set_title_widget(self.page_title)

        # Menu button
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        menu_button.add_css_class("flat")

        # Create menu
        menu = Gio.Menu()
        menu.append("Preferences", "app.preferences")
        menu.append("About MX4Control", "app.about")
        menu.append("Quit", "app.quit")
        menu_button.set_menu_model(menu)

        header.pack_end(menu_button)

        # Refresh button
        refresh_button = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh_button.add_css_class("flat")
        refresh_button.set_tooltip_text("Reconnect to device")
        refresh_button.connect("clicked", self._on_refresh_clicked)
        header.pack_end(refresh_button)

        return header

    def _create_pages(self):
        """Create all content pages"""
        # Overview page
        self._pages["overview"] = OverviewPage(self)
        self.stack.add_named(self._pages["overview"], "overview")

        # Buttons page
        self._pages["buttons"] = ButtonsPage(self)
        self.stack.add_named(self._pages["buttons"], "buttons")

        # Haptics page
        self._pages["haptics"] = HapticsPage(self)
        self.stack.add_named(self._pages["haptics"], "haptics")

        # Pointer page
        self._pages["pointer"] = PointerPage(self)
        self.stack.add_named(self._pages["pointer"], "pointer")

        # Scroll page
        self._pages["scroll"] = ScrollPage(self)
        self.stack.add_named(self._pages["scroll"], "scroll")

        # Actions Ring page
        self._pages["actions_ring"] = ActionsRingPage(self)
        self.stack.add_named(self._pages["actions_ring"], "actions_ring")

    def _on_nav_selected(self, listbox, row):
        """Handle navigation selection"""
        if row and hasattr(self, 'stack'):
            page_id = row.page_id
            self.stack.set_visible_child_name(page_id)

            # Update header title
            if hasattr(self, 'page_title'):
                titles = {
                    "overview": "Device",
                    "buttons": "Buttons",
                    "haptics": "Haptics",
                    "pointer": "Pointer",
                    "scroll": "Scroll",
                    "actions_ring": "Actions Ring",
                }
                self.page_title.set_label(titles.get(page_id, ""))

    def _on_sidebar_toggle(self, button):
        """Sync the overlay sidebar to the toggle state."""
        self.split_view.set_show_sidebar(button.get_active())

    def _on_refresh_clicked(self, button):
        """Handle refresh button click"""
        self._connect_device(force=True)

    def _connect_device(self, force: bool = False):
        """Attempt to connect to MX Master 4 (async).

        Safe to call repeatedly — guarded by ``self._connecting`` so the
        reconnect loop can fire without stacking up threads. Set
        ``force=True`` when the user explicitly requests a reconnect
        (refresh button), to tear down any existing device handle first.
        """
        import threading

        if self._connecting:
            return
        self._connecting = True

        # Tear down the previous handle if the caller asked us to or if
        # the link was lost (health check detected a dead fd).
        if force and self.device is not None:
            try:
                if self._gesture_service and self._gesture_service.is_running:
                    self._gesture_service.stop()
                self.device.close()
            except Exception:
                pass
            self.device = None

        # Update status to "searching"
        self.status_dot.remove_css_class("connected")
        self.status_dot.remove_css_class("disconnected")
        self.status_dot.add_css_class("searching")
        self.status_label.set_label("Searching...")

        def connect_thread():
            device_info = find_mx_master_4()
            device = None
            info = None

            if device_info:
                try:
                    device_index = device_info.get("device_index", 0xFF)
                    device = MXMaster4(device_info.get("path"), device_index=device_index)
                    if device.open():
                        info = device.get_device_info()
                    else:
                        device = None
                except Exception as e:
                    logger.error(f"Failed to open device: {e}")
                    device = None

            GLib.idle_add(self._on_device_connected, device, info)

        threading.Thread(target=connect_thread, daemon=True).start()

    def _schedule_reconnect(self):
        """Start the periodic reconnect loop (idempotent)."""
        if self._reconnect_source_id is not None:
            return
        self._reconnect_source_id = GLib.timeout_add(
            self._RECONNECT_INTERVAL_MS, self._reconnect_tick
        )

    def _cancel_reconnect(self):
        if self._reconnect_source_id is not None:
            GLib.source_remove(self._reconnect_source_id)
            self._reconnect_source_id = None

    def _reconnect_tick(self) -> bool:
        """GLib timeout callback: retry connection while disconnected."""
        if self.device is not None:
            self._reconnect_source_id = None
            return False
        if not self._connecting:
            self._connect_device()
        return True  # keep firing until we succeed

    def _schedule_health_check(self):
        """Start the periodic health check that detects a dropped link."""
        if self._health_source_id is not None:
            return
        self._health_source_id = GLib.timeout_add(
            self._HEALTH_CHECK_INTERVAL_MS, self._health_tick
        )

    def _cancel_health_check(self):
        if self._health_source_id is not None:
            GLib.source_remove(self._health_source_id)
            self._health_source_id = None

    def _health_tick(self) -> bool:
        """Ping the device; declare dead only after N consecutive failures.

        A single failure is likely a transient HID++ timeout from the
        notification-listener thread racing with the probe. Only flip
        the UI to disconnected after the device has clearly gone away.
        """
        if self.device is None:
            self._health_source_id = None
            return False

        import threading

        def probe():
            alive = False
            try:
                alive = bool(self.device and self.device.ping())
            except Exception:
                alive = False

            # If the quick ping succeeded, refresh live info for the UI
            # (battery level, charging state). This is the "maybe the
            # user just plugged in USB-C" path.
            fresh_info = None
            if alive:
                try:
                    fresh_info = self.device.get_device_info()
                except Exception:
                    fresh_info = None

            def apply():
                if alive:
                    self._health_failures = 0
                    if fresh_info:
                        self._refresh_connection_display(fresh_info)
                    return False

                self._health_failures += 1
                logger.debug(
                    f"Health probe failed ({self._health_failures}/"
                    f"{self._HEALTH_CHECK_FAILURE_THRESHOLD})"
                )

                if self._health_failures < self._HEALTH_CHECK_FAILURE_THRESHOLD:
                    return False  # keep probing; don't disrupt UI yet

                logger.info("Device unresponsive after 3 probes — reconnecting")
                try:
                    if self._gesture_service and self._gesture_service.is_running:
                        self._gesture_service.stop()
                    if self.device:
                        self.device.close()
                except Exception:
                    pass
                self.device = None
                self._health_failures = 0
                self._cancel_health_check()
                self._apply_disconnected_state("Link lost — retrying…")
                self._schedule_reconnect()
                return False

            GLib.idle_add(apply)

        threading.Thread(target=probe, daemon=True).start()
        return True

    def _on_device_connected(self, device, info):
        """Called on main thread when the connect-thread finishes."""
        self._connecting = False
        self.device = device

        if device and info:
            self._cancel_reconnect()

            # Refresh UI + pages + gesture service (all live in one place)
            self._refresh_connection_display(info)

            # Low-battery toast only when not already charging
            if not info.battery_charging and info.battery_level <= 20:
                self.show_toast(
                    f"Battery low ({info.battery_level}%) — connect USB-C to charge",
                    timeout=6,
                )

            logger.info(f"Connected to {info.name} via {info.connection_type}")
            self._schedule_health_check()
        else:
            self.device = None
            self._apply_disconnected_state("Searching for MX Master 4…")

            if self._gesture_service and self._gesture_service.is_running:
                self._gesture_service.stop()

            for page in self._pages.values():
                try:
                    page.update_device(None)
                except Exception:
                    pass

            # Only surface a toast the first time we notice it's gone, to
            # avoid spamming while the reconnect loop retries.
            if self._last_connection_type is not None:
                self.show_toast("Mouse disconnected — retrying", timeout=3)
            self._last_connection_type = None
            self._last_charging_state = None

            self._schedule_reconnect()

        return False  # Don't repeat

    def _apply_disconnected_state(self, label: str):
        """Put the sidebar status widget into the 'not-connected' visual state."""
        self.status_dot.remove_css_class("connected")
        self.status_dot.remove_css_class("searching")
        self.status_dot.add_css_class("disconnected")
        self.status_label.set_label("Not connected")
        self.battery_label.set_label(label)

    def _refresh_connection_display(self, info):
        """Update sidebar + pages to match live device info.

        Called on first connect and on every health-check tick. When the
        charging state flips ('Bolt' ↔ 'Bolt — charging') or the
        transport changes (Bolt ↔ Bluetooth), we update the badges so
        the user always sees the live state without having to refresh.
        """
        # Sidebar status
        self.status_dot.remove_css_class("disconnected")
        self.status_dot.remove_css_class("searching")
        self.status_dot.add_css_class("connected")
        self.status_label.set_label(info.name or "MX Master 4")

        battery_text = f"{info.battery_level}%"
        if info.battery_charging:
            battery_text += " ⚡ charging"
        elif info.battery_level <= 20:
            battery_text += " ⚠ low"
        self.battery_label.set_label(battery_text)

        # Detect transport / charging changes for toasts + page refresh
        first_connect = self._last_connection_type is None
        conn_changed = info.connection_type != self._last_connection_type
        charging_changed = info.battery_charging != self._last_charging_state

        if first_connect or conn_changed or charging_changed:
            # Push the new device handle into every page (and into the
            # gesture service if this is a fresh connect).
            for page in self._pages.values():
                try:
                    page.update_device(self.device)
                except Exception as e:
                    logger.debug(f"page.update_device failed: {e}")

            if first_connect and self._gesture_service:
                try:
                    self._gesture_service.set_hidpp_device(self.device)
                    if not self._gesture_service.is_running:
                        self._gesture_service.start()
                        logger.info("Gesture service started")
                except Exception as e:
                    logger.error(f"Error starting gesture service: {e}")

            if first_connect:
                self.show_toast(
                    f"Connected to {info.name} via {info.connection_type.title()}",
                    timeout=2,
                )
            elif conn_changed:
                self.show_toast(
                    f"Now connected via {info.connection_type.title()}",
                    timeout=2,
                )
            elif charging_changed and info.battery_charging:
                self.show_toast("USB-C charging", timeout=2)
            elif charging_changed:
                self.show_toast("Charging cable removed", timeout=2)

        self._last_connection_type = info.connection_type
        self._last_charging_state = info.battery_charging

    def trigger_haptic(self, pattern):
        """Trigger a haptic pattern on the connected device"""
        if self.device:
            self.device.trigger_haptic(pattern)
