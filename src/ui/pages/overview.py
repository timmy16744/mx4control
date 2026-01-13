"""
Overview Page

Displays device status, battery, connection info, and quick settings.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, GLib
import math
import cairo


class MousePreviewWidget(Gtk.DrawingArea):
    """
    Custom widget that renders an MX Master 4 mouse illustration

    Features highlighted buttons, battery indicator, and haptic feedback
    visualization with ripple animations.
    """

    def __init__(self):
        super().__init__()

        self.set_size_request(220, 320)
        self.set_draw_func(self._draw)
        self.active_button = None
        self.haptic_rings = []

        # Animation timer for haptic effects
        self._animation_id = None

    def _draw(self, area, cr, width, height):
        """Draw the mouse illustration"""
        # Center the drawing
        cx = width / 2
        cy = height / 2

        # Colors
        body_color = (0.18, 0.18, 0.20)
        body_highlight = (0.25, 0.25, 0.28)
        button_color = (0.22, 0.22, 0.25)
        accent = (0.83, 0.65, 0.46)  # Copper
        wheel_color = (0.35, 0.35, 0.38)

        # Draw haptic rings first (behind mouse)
        for ring in self.haptic_rings:
            self._draw_haptic_ring(cr, cx, cy - 40, ring)

        # Mouse body shadow
        cr.set_source_rgba(0, 0, 0, 0.3)
        self._draw_mouse_shape(cr, cx + 4, cy + 6, 0.95)
        cr.fill()

        # Mouse body gradient
        pattern = cairo.LinearGradient(cx - 60, cy - 100, cx + 60, cy + 100)
        pattern.add_color_stop_rgb(0, *body_highlight)
        pattern.add_color_stop_rgb(0.5, *body_color)
        pattern.add_color_stop_rgb(1, 0.12, 0.12, 0.14)
        cr.set_source(pattern)
        self._draw_mouse_shape(cr, cx, cy, 1.0)
        cr.fill()

        # Body outline
        cr.set_source_rgba(1, 1, 1, 0.05)
        cr.set_line_width(1)
        self._draw_mouse_shape(cr, cx, cy, 1.0)
        cr.stroke()

        # Left button
        self._draw_button(cr, cx - 28, cy - 85, 45, 70, button_color,
                         self.active_button == 0)

        # Right button
        self._draw_button(cr, cx + 28, cy - 85, 45, 70, button_color,
                         self.active_button == 1)

        # Scroll wheel housing
        cr.set_source_rgb(0.12, 0.12, 0.14)
        self._rounded_rect(cr, cx - 12, cy - 75, 24, 45, 6)
        cr.fill()

        # Scroll wheel
        wheel_gradient = cairo.LinearGradient(cx - 8, cy - 70, cx + 8, cy - 40)
        wheel_gradient.add_color_stop_rgb(0, 0.4, 0.4, 0.42)
        wheel_gradient.add_color_stop_rgb(0.5, *wheel_color)
        wheel_gradient.add_color_stop_rgb(1, 0.25, 0.25, 0.28)
        cr.set_source(wheel_gradient)
        self._rounded_rect(cr, cx - 8, cy - 68, 16, 38, 4)
        cr.fill()

        # Wheel ridges
        cr.set_source_rgba(0, 0, 0, 0.3)
        for i in range(6):
            y = cy - 62 + i * 6
            cr.rectangle(cx - 6, y, 12, 2)
            cr.fill()

        # Mode switch button (below wheel)
        self._draw_small_button(cr, cx, cy - 20, 16, 10,
                               self.active_button == 6)

        # Thumb buttons area
        self._draw_thumb_area(cr, cx - 55, cy + 10)

        # Side buttons
        self._draw_side_button(cr, cx - 48, cy - 20, 20, 25,
                              self.active_button == 3, "◄")
        self._draw_side_button(cr, cx - 48, cy + 10, 20, 25,
                              self.active_button == 4, "►")

        # Gesture button (large thumb area)
        self._draw_gesture_button(cr, cx - 55, cy + 45, 40, 50,
                                 self.active_button == 5)

        # Thumb scroll wheel
        self._draw_thumb_wheel(cr, cx - 75, cy - 5, 10, 50,
                              self.active_button == 7)

    def _draw_mouse_shape(self, cr, cx, cy, scale):
        """Draw the ergonomic mouse body shape"""
        # Ergonomic curved shape
        cr.new_path()

        # Top curve (buttons area)
        cr.move_to(cx - 50 * scale, cy - 60 * scale)
        cr.curve_to(
            cx - 60 * scale, cy - 100 * scale,
            cx + 60 * scale, cy - 100 * scale,
            cx + 50 * scale, cy - 60 * scale
        )

        # Right side curve
        cr.curve_to(
            cx + 70 * scale, cy + 20 * scale,
            cx + 60 * scale, cy + 80 * scale,
            cx + 30 * scale, cy + 100 * scale
        )

        # Bottom curve
        cr.curve_to(
            cx, cy + 110 * scale,
            cx - 30 * scale, cy + 100 * scale,
            cx - 45 * scale, cy + 70 * scale
        )

        # Left side (thumb rest) - more curved
        cr.curve_to(
            cx - 75 * scale, cy + 40 * scale,
            cx - 80 * scale, cy - 20 * scale,
            cx - 50 * scale, cy - 60 * scale
        )

        cr.close_path()

    def _draw_button(self, cr, x, y, w, h, color, active):
        """Draw a main mouse button"""
        if active:
            # Glowing effect
            cr.set_source_rgba(0.83, 0.65, 0.46, 0.3)
            self._rounded_rect(cr, x - w/2 - 4, y - 4, w + 8, h + 8, 10)
            cr.fill()

            cr.set_source_rgb(0.83, 0.65, 0.46)
        else:
            cr.set_source_rgb(*color)

        self._rounded_rect(cr, x - w/2, y, w, h, 8)
        cr.fill()

        # Highlight edge
        cr.set_source_rgba(1, 1, 1, 0.08)
        cr.set_line_width(1)
        self._rounded_rect(cr, x - w/2, y, w, h, 8)
        cr.stroke()

    def _draw_small_button(self, cr, x, y, w, h, active):
        """Draw a small button (mode switch)"""
        if active:
            cr.set_source_rgb(0.83, 0.65, 0.46)
        else:
            cr.set_source_rgb(0.3, 0.3, 0.32)

        self._rounded_rect(cr, x - w/2, y - h/2, w, h, 3)
        cr.fill()

    def _draw_side_button(self, cr, x, y, w, h, active, label):
        """Draw a side button with label"""
        if active:
            cr.set_source_rgba(0.83, 0.65, 0.46, 0.5)
            self._rounded_rect(cr, x - 2, y - 2, w + 4, h + 4, 5)
            cr.fill()
            cr.set_source_rgb(0.83, 0.65, 0.46)
        else:
            cr.set_source_rgb(0.25, 0.25, 0.28)

        self._rounded_rect(cr, x, y, w, h, 4)
        cr.fill()

        # Button label
        cr.set_source_rgba(1, 1, 1, 0.5 if not active else 0.9)
        cr.select_font_face("sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(10)
        extents = cr.text_extents(label)
        cr.move_to(x + w/2 - extents.width/2, y + h/2 + extents.height/2)
        cr.show_text(label)

    def _draw_gesture_button(self, cr, x, y, w, h, active):
        """Draw the large gesture button"""
        if active:
            cr.set_source_rgba(0.83, 0.65, 0.46, 0.4)
            self._rounded_rect(cr, x - 4, y - 4, w + 8, h + 8, 12)
            cr.fill()
            cr.set_source_rgb(0.28, 0.28, 0.32)
        else:
            cr.set_source_rgb(0.2, 0.2, 0.23)

        self._rounded_rect(cr, x, y, w, h, 10)
        cr.fill()

        # Texture dots
        cr.set_source_rgba(0, 0, 0, 0.2)
        for row in range(4):
            for col in range(3):
                dot_x = x + 10 + col * 10
                dot_y = y + 12 + row * 10
                cr.arc(dot_x, dot_y, 2, 0, 2 * math.pi)
                cr.fill()

    def _draw_thumb_wheel(self, cr, x, y, w, h, active):
        """Draw the horizontal thumb scroll wheel"""
        # Housing
        cr.set_source_rgb(0.15, 0.15, 0.17)
        self._rounded_rect(cr, x - w/2, y, w, h, 5)
        cr.fill()

        # Wheel
        if active:
            cr.set_source_rgb(0.83, 0.65, 0.46)
        else:
            cr.set_source_rgb(0.35, 0.35, 0.38)

        self._rounded_rect(cr, x - w/2 + 2, y + 2, w - 4, h - 4, 3)
        cr.fill()

        # Ridges
        cr.set_source_rgba(0, 0, 0, 0.2)
        for i in range(6):
            ridge_y = y + 6 + i * 7
            cr.rectangle(x - w/2 + 3, ridge_y, w - 6, 2)
            cr.fill()

    def _draw_thumb_area(self, cr, x, y):
        """Draw the textured thumb rest area"""
        # Subtle texture
        cr.set_source_rgba(0, 0, 0, 0.1)
        for row in range(6):
            for col in range(3):
                dot_x = x + col * 8
                dot_y = y + row * 8
                cr.arc(dot_x, dot_y, 1.5, 0, 2 * math.pi)
                cr.fill()

    def _draw_haptic_ring(self, cr, x, y, ring):
        """Draw an animated haptic feedback ring"""
        progress, opacity = ring
        radius = 30 + progress * 80

        cr.set_source_rgba(0.83, 0.65, 0.46, opacity * (1 - progress))
        cr.set_line_width(3 * (1 - progress * 0.5))
        cr.arc(x, y, radius, 0, 2 * math.pi)
        cr.stroke()

    def _rounded_rect(self, cr, x, y, w, h, r):
        """Draw a rounded rectangle path"""
        cr.new_path()
        cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
        cr.arc(x + w - r, y + r, r, 1.5 * math.pi, 2 * math.pi)
        cr.arc(x + w - r, y + h - r, r, 0, 0.5 * math.pi)
        cr.arc(x + r, y + h - r, r, 0.5 * math.pi, math.pi)
        cr.close_path()

    def set_active_button(self, button_index):
        """Highlight a specific button"""
        self.active_button = button_index
        self.queue_draw()

    def trigger_haptic_animation(self):
        """Start haptic feedback visualization"""
        self.haptic_rings = []

        # Add 3 rings with staggered timing
        for i in range(3):
            GLib.timeout_add(i * 100, lambda: self._add_ring())

        # Start animation
        if self._animation_id is None:
            self._animation_id = GLib.timeout_add(16, self._animate_rings)

    def _add_ring(self):
        """Add a new haptic ring"""
        self.haptic_rings.append([0.0, 1.0])  # [progress, opacity]
        return False

    def _animate_rings(self):
        """Animate haptic rings"""
        if not self.haptic_rings:
            self._animation_id = None
            return False

        # Update ring animations
        new_rings = []
        for ring in self.haptic_rings:
            ring[0] += 0.03  # Progress
            ring[1] = max(0, 1 - ring[0])  # Fade out

            if ring[0] < 1.0:
                new_rings.append(ring)

        self.haptic_rings = new_rings
        self.queue_draw()

        if not self.haptic_rings:
            self._animation_id = None
            return False
        return True


class OverviewPage(Gtk.Box):
    """
    Device overview page

    Shows:
    - Mouse preview with interactive button highlighting
    - Battery status
    - Connection info
    - Quick DPI display
    - Firmware info
    """

    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.device = None

        self.add_css_class("page-content")
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(16)
        self.set_margin_bottom(24)

        # Content layout
        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        content.set_vexpand(True)
        self.append(content)

        # Left side - Device preview
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        left_box.set_hexpand(True)
        content.append(left_box)

        # Device card
        device_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        device_card.add_css_class("device-card")
        device_card.set_halign(Gtk.Align.CENTER)
        device_card.set_valign(Gtk.Align.CENTER)
        device_card.set_vexpand(True)
        left_box.append(device_card)

        # Mouse preview
        self.mouse_preview = MousePreviewWidget()
        self.mouse_preview.set_halign(Gtk.Align.CENTER)
        device_card.append(self.mouse_preview)

        # Device name
        self.device_name = Gtk.Label(label="MX Master 4")
        self.device_name.add_css_class("card-title")
        self.device_name.set_margin_top(16)
        device_card.append(self.device_name)

        # Connection badge
        conn_box = Gtk.Box(spacing=8)
        conn_box.set_halign(Gtk.Align.CENTER)
        conn_box.set_margin_top(8)
        device_card.append(conn_box)

        self.conn_dot = Gtk.Box()
        self.conn_dot.set_size_request(8, 8)
        self.conn_dot.add_css_class("status-dot")
        self.conn_dot.add_css_class("disconnected")
        self.conn_dot.set_valign(Gtk.Align.CENTER)
        conn_box.append(self.conn_dot)

        self.conn_label = Gtk.Label(label="Disconnected")
        self.conn_label.add_css_class("card-description")
        conn_box.append(self.conn_label)

        # Right side - Stats cards
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        right_box.set_hexpand(True)
        content.append(right_box)

        # Section title
        section_title = Gtk.Label(label="Device Status")
        section_title.add_css_class("section-title")
        section_title.set_halign(Gtk.Align.START)
        right_box.append(section_title)

        # Stats grid
        stats_grid = Gtk.Grid()
        stats_grid.set_row_spacing(16)
        stats_grid.set_column_spacing(16)
        stats_grid.set_row_homogeneous(True)
        stats_grid.set_column_homogeneous(True)
        right_box.append(stats_grid)

        # Battery card
        self.battery_card = self._create_stat_card(
            "Battery", "100", "%", "battery-full-symbolic"
        )
        stats_grid.attach(self.battery_card, 0, 0, 1, 1)

        # DPI card
        self.dpi_card = self._create_stat_card(
            "DPI", "1000", "dpi", "input-tablet-symbolic"
        )
        stats_grid.attach(self.dpi_card, 1, 0, 1, 1)

        # Connection card
        self.conn_card = self._create_stat_card(
            "Connection", "Bolt", "receiver", "network-wireless-symbolic"
        )
        stats_grid.attach(self.conn_card, 0, 1, 1, 1)

        # Firmware card
        self.firmware_card = self._create_stat_card(
            "Firmware", "--", "version", "emblem-system-symbolic"
        )
        stats_grid.attach(self.firmware_card, 1, 1, 1, 1)

        # Haptic test section
        haptic_section = Gtk.Label(label="Quick Actions")
        haptic_section.add_css_class("section-title")
        haptic_section.set_halign(Gtk.Align.START)
        haptic_section.set_margin_top(16)
        right_box.append(haptic_section)

        # Action buttons
        action_box = Gtk.Box(spacing=12)
        right_box.append(action_box)

        test_haptic_btn = Gtk.Button(label="Test Haptic")
        test_haptic_btn.add_css_class("copper-button")
        test_haptic_btn.connect("clicked", self._on_test_haptic)
        action_box.append(test_haptic_btn)

        identify_btn = Gtk.Button(label="Identify Device")
        identify_btn.add_css_class("ghost-button")
        identify_btn.connect("clicked", self._on_identify)
        action_box.append(identify_btn)

        # Spacer
        spacer = Gtk.Box(vexpand=True)
        right_box.append(spacer)

        # Device info row at bottom
        info_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        info_box.add_css_class("settings-card")
        right_box.append(info_box)

        # Serial
        self._add_info_item(info_box, "Serial", "Fetching...")
        self._add_info_item(info_box, "Protocol", "HID++ 4.5")
        self._add_info_item(info_box, "Buttons", "8")
        self._add_info_item(info_box, "Max DPI", "8000")

    def _create_stat_card(self, title, value, unit, icon_name):
        """Create a statistics card widget"""
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.add_css_class("settings-card")

        # Header with icon
        header = Gtk.Box(spacing=8)
        card.append(header)

        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(20)
        icon.set_opacity(0.6)
        header.append(icon)

        title_label = Gtk.Label(label=title)
        title_label.add_css_class("card-description")
        header.append(title_label)

        # Value
        value_box = Gtk.Box(spacing=4, halign=Gtk.Align.START)
        card.append(value_box)

        value_label = Gtk.Label(label=value)
        value_label.add_css_class("value-label")
        value_box.append(value_label)

        unit_label = Gtk.Label(label=unit)
        unit_label.add_css_class("unit-label")
        unit_label.set_valign(Gtk.Align.END)
        unit_label.set_margin_bottom(4)
        value_box.append(unit_label)

        # Store references
        card.value_label = value_label
        card.unit_label = unit_label

        return card

    def _add_info_item(self, container, label, value):
        """Add an info item to a container"""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_hexpand(True)
        container.append(box)

        label_widget = Gtk.Label(label=label)
        label_widget.add_css_class("card-description")
        label_widget.set_halign(Gtk.Align.START)
        box.append(label_widget)

        value_widget = Gtk.Label(label=value)
        value_widget.add_css_class("card-title")
        value_widget.set_halign(Gtk.Align.START)
        box.append(value_widget)

        # Store reference for updates
        setattr(self, f"info_{label.lower().replace(' ', '_')}", value_widget)

    def _on_test_haptic(self, button):
        """Test haptic feedback"""
        import threading
        self.mouse_preview.trigger_haptic_animation()

        if self.device:
            def trigger():
                # Pattern 2 = Medium Click
                self.device.trigger_haptic(2)
            threading.Thread(target=trigger, daemon=True).start()

    def _on_identify(self, button):
        """Identify device with haptic sequence"""
        import threading
        import time
        self.mouse_preview.trigger_haptic_animation()

        if self.device:
            def trigger_sequence():
                # Pattern 1 = Light Click
                for i in range(3):
                    self.device.trigger_haptic(1)
                    time.sleep(0.15)
            threading.Thread(target=trigger_sequence, daemon=True).start()

    def update_device(self, device):
        """Update page with new device connection"""
        import threading
        self.device = device

        if device:
            # Fetch data in background to avoid blocking UI
            def fetch_data():
                info = device.get_device_info()
                dpi = device.get_dpi()
                GLib.idle_add(self._update_ui, info, dpi)

            threading.Thread(target=fetch_data, daemon=True).start()
        else:
            self._update_ui(None, 0)

    def _update_ui(self, info, dpi):
        """Update UI elements (called on main thread)"""
        if info:
            # Update device name
            self.device_name.set_label(info.name)

            # Update connection status
            self.conn_dot.remove_css_class("disconnected")
            self.conn_dot.add_css_class("connected")
            self.conn_label.set_label(f"Connected via {info.connection_type.title()}")

            # Update stats
            self.battery_card.value_label.set_label(str(info.battery_level))
            self.dpi_card.value_label.set_label(str(dpi) if dpi else "--")
            self.conn_card.value_label.set_label(info.connection_type.title())
            self.firmware_card.value_label.set_label(info.firmware_version)

            # Update info bar
            if hasattr(self, 'info_serial'):
                self.info_serial.set_label(info.serial or "N/A")
        else:
            # Disconnected state
            self.conn_dot.remove_css_class("connected")
            self.conn_dot.add_css_class("disconnected")
            self.conn_label.set_label("Disconnected")

            self.battery_card.value_label.set_label("--")
            self.dpi_card.value_label.set_label("--")
            self.conn_card.value_label.set_label("--")
            self.firmware_card.value_label.set_label("--")

        return False  # Don't repeat GLib.idle_add
