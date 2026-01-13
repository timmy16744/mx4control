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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.device = None
        self._pages = {}
        self._gesture_service = None

        # Get config manager from application
        self.config_manager = self.get_application().config_manager

        # Window setup
        self.set_title("MX4Control")
        self.set_default_size(1200, 800)
        self.set_size_request(900, 600)
        self.add_css_class("main-window")

        # Build UI
        self._build_ui()

        # Initialize gesture service
        self._init_gesture_service()

        # Try to connect to device
        GLib.idle_add(self._connect_device)

        # Handle window close
        self.connect("close-request", self._on_close_request)

    def _init_gesture_service(self):
        """Initialize the gesture service for Actions Ring"""
        try:
            print(">>> Initializing gesture service...")
            self._gesture_service = get_gesture_service()
            result = self._gesture_service.initialize(self.config_manager.config)
            print(f">>> Gesture service initialized: {result}")

            # Connect haptic callback to device
            self._gesture_service.on_haptic_trigger = self._trigger_haptic_from_gesture

            logger.info("Gesture service initialized")
        except Exception as e:
            print(f">>> ERROR initializing gesture service: {e}")
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
        # Stop gesture service
        if self._gesture_service:
            self._gesture_service.stop()

        # Close device connection
        if self.device:
            try:
                self.device.close()
            except Exception:
                pass

        return False  # Allow close to proceed

    def _build_ui(self):
        """Construct the window UI"""
        # Main layout container
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_content(self.main_box)

        # Navigation sidebar
        self._build_sidebar()

        # Content area with header and stack
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        content_box.add_css_class("main-content")
        self.main_box.append(content_box)

        # Header bar
        self.header_bar = self._build_header()
        content_box.append(self.header_bar)

        # Page stack
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(200)
        content_box.append(self.stack)

        # Create pages
        self._create_pages()

    def _build_sidebar(self):
        """Build the navigation sidebar"""
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar.set_size_request(240, -1)
        sidebar.add_css_class("navigation-sidebar")
        self.main_box.append(sidebar)

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

    def _on_refresh_clicked(self, button):
        """Handle refresh button click"""
        self._connect_device()

    def _connect_device(self):
        """Attempt to connect to MX Master 4 (async)"""
        import threading

        # Update status
        self.status_dot.remove_css_class("connected")
        self.status_dot.remove_css_class("disconnected")
        self.status_dot.add_css_class("searching")
        self.status_label.set_label("Searching...")

        def connect_thread():
            """Run device connection in background thread"""
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

            # Update UI on main thread
            GLib.idle_add(self._on_device_connected, device, info)

        # Start connection in background
        thread = threading.Thread(target=connect_thread, daemon=True)
        thread.start()

    def _on_device_connected(self, device, info):
        """Called on main thread when device connection completes"""
        self.device = device

        if device and info:
            self.status_dot.remove_css_class("searching")
            self.status_dot.add_css_class("connected")
            self.status_label.set_label(info.name if info else "MX Master 4")

            battery_text = f"{info.battery_level}%"
            if info.battery_charging:
                battery_text += " ⚡"
            self.battery_label.set_label(battery_text)

            # Apply saved settings from config
            self._apply_saved_settings()

            # Update all pages with device and config
            for page in self._pages.values():
                page.update_device(self.device)

            # Start gesture service for Actions Ring
            if self._gesture_service:
                try:
                    # Pass HID++ device for proper button diversion
                    # This ensures the gesture button doesn't trigger OS events
                    print(">>> Setting HID++ device for gesture service...")
                    self._gesture_service.set_hidpp_device(self.device)

                    if not self._gesture_service.is_running:
                        print(">>> Starting gesture service...")
                        if self._gesture_service.start():
                            print(f">>> Gesture service STARTED, device: {self._gesture_service.device_name}")
                            logger.info("Gesture service started for Actions Ring")
                        else:
                            print(">>> FAILED to start gesture service")
                            logger.warning("Failed to start gesture service")
                except Exception as e:
                    print(f">>> ERROR starting gesture service: {e}")
                    import traceback
                    traceback.print_exc()
                    logger.error(f"Error starting gesture service: {e}")

            logger.info("Connected to MX Master 4")
        else:
            # Not found or failed
            self.device = None
            self.status_dot.remove_css_class("searching")
            self.status_dot.add_css_class("disconnected")
            self.status_label.set_label("Not connected")
            self.battery_label.set_label("Connect your MX Master 4")

            # Stop gesture service
            if self._gesture_service and self._gesture_service.is_running:
                self._gesture_service.stop()

            # Update pages with None device
            for page in self._pages.values():
                page.update_device(None)

        return False  # Don't repeat

    def _apply_saved_settings(self):
        """Apply saved settings to the connected device"""
        if not self.device:
            return

        import threading

        config = self.config_manager.config

        def apply_settings():
            try:
                # Apply DPI
                if config.pointer.dpi:
                    self.device.set_dpi(config.pointer.dpi)
                    logger.info(f"Applied saved DPI: {config.pointer.dpi}")

                # Apply SmartShift settings
                self.device.set_smartshift(
                    config.scroll.smartshift_enabled,
                    config.scroll.smartshift_threshold
                )
                logger.info(f"Applied SmartShift: enabled={config.scroll.smartshift_enabled}, threshold={config.scroll.smartshift_threshold}")

                # Apply hi-res scroll
                self.device.set_hires_scroll(
                    config.scroll.hires_enabled,
                    config.scroll.invert_vertical
                )

            except Exception as e:
                logger.error(f"Failed to apply saved settings: {e}")

        # Apply in background to not block UI
        threading.Thread(target=apply_settings, daemon=True).start()

    def trigger_haptic(self, pattern):
        """Trigger a haptic pattern on the connected device"""
        if self.device:
            self.device.trigger_haptic(pattern)
