"""
Scroll Page

Configure scroll wheel behavior, SmartShift, and horizontal scrolling.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, GLib
import math
import cairo


class ScrollWheelPreview(Gtk.DrawingArea):
    """
    Visual representation of the MagSpeed scroll wheel

    Shows the current mode (ratchet/free) and SmartShift behavior.
    """

    def __init__(self):
        super().__init__()

        self.set_size_request(120, 120)
        self.set_draw_func(self._draw)

        self.mode = "smart"  # "ratchet", "free", "smart"
        self.rotation = 0
        self._animation_id = None

    def _draw(self, area, cr, width, height):
        """Draw the scroll wheel visualization"""
        cx = width / 2
        cy = height / 2

        # Outer ring (housing)
        cr.set_source_rgb(0.15, 0.15, 0.17)
        cr.arc(cx, cy, 50, 0, 2 * math.pi)
        cr.fill()

        # Inner wheel with grooves
        if self.mode == "free":
            # Smooth gradient for free-spin
            cr.set_source_rgb(0.35, 0.35, 0.38)
        else:
            cr.set_source_rgb(0.28, 0.28, 0.30)

        cr.arc(cx, cy, 40, 0, 2 * math.pi)
        cr.fill()

        # Wheel ridges
        num_ridges = 24
        for i in range(num_ridges):
            angle = (i * 2 * math.pi / num_ridges) + self.rotation

            if self.mode == "ratchet":
                # Defined notches
                cr.set_source_rgba(0, 0, 0, 0.4)
            else:
                # Subtle lines
                cr.set_source_rgba(0, 0, 0, 0.2)

            x1 = cx + math.cos(angle) * 25
            y1 = cy + math.sin(angle) * 25
            x2 = cx + math.cos(angle) * 38
            y2 = cy + math.sin(angle) * 38

            cr.set_line_width(2)
            cr.move_to(x1, y1)
            cr.line_to(x2, y2)
            cr.stroke()

        # Center cap
        cr.set_source_rgb(0.2, 0.2, 0.22)
        cr.arc(cx, cy, 15, 0, 2 * math.pi)
        cr.fill()

        # Mode indicator
        if self.mode == "smart":
            # SmartShift icon
            cr.set_source_rgb(0.83, 0.65, 0.46)
            cr.arc(cx, cy, 8, 0, 2 * math.pi)
            cr.stroke()
            cr.move_to(cx, cy - 4)
            cr.line_to(cx, cy + 4)
            cr.move_to(cx - 4, cy)
            cr.line_to(cx + 4, cy)
            cr.stroke()
        elif self.mode == "free":
            # Free-spin (smooth circle)
            cr.set_source_rgb(0.31, 0.80, 0.77)  # Teal
            cr.arc(cx, cy, 8, 0, 2 * math.pi)
            cr.fill()
        else:
            # Ratchet (notched)
            cr.set_source_rgb(0.83, 0.65, 0.46)
            for i in range(6):
                angle = i * math.pi / 3
                x = cx + math.cos(angle) * 6
                y = cy + math.sin(angle) * 6
                cr.arc(x, y, 2, 0, 2 * math.pi)
                cr.fill()

    def set_mode(self, mode):
        """Set scroll mode"""
        self.mode = mode
        self.queue_draw()

    def animate_scroll(self):
        """Animate the wheel rotation"""
        if self._animation_id:
            return

        def step():
            self.rotation += 0.1
            self.queue_draw()
            return True

        self._animation_id = GLib.timeout_add(32, step)

    def stop_animation(self):
        """Stop wheel animation"""
        if self._animation_id:
            GLib.source_remove(self._animation_id)
            self._animation_id = None


class ScrollPage(Gtk.Box):
    """
    Scroll settings page

    Features:
    - SmartShift configuration
    - Scroll mode toggle
    - Sensitivity adjustment
    - Direction inversion
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
        self.set_spacing(24)

        # Scrolled content
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        self.append(scroll)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        scroll.set_child(content)

        # Main layout with preview
        main_box = Gtk.Box(spacing=32)
        content.append(main_box)

        # Left side - Preview
        preview_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        preview_box.set_halign(Gtk.Align.CENTER)
        preview_box.set_valign(Gtk.Align.START)
        main_box.append(preview_box)

        preview_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        preview_card.add_css_class("settings-card")
        preview_card.set_halign(Gtk.Align.CENTER)
        preview_box.append(preview_card)

        self.wheel_preview = ScrollWheelPreview()
        self.wheel_preview.set_halign(Gtk.Align.CENTER)
        preview_card.append(self.wheel_preview)

        self.mode_label = Gtk.Label(label="SmartShift")
        self.mode_label.add_css_class("card-title")
        preview_card.append(self.mode_label)

        self.mode_desc = Gtk.Label(label="Automatically switches modes")
        self.mode_desc.add_css_class("card-description")
        preview_card.append(self.mode_desc)

        # Right side - Settings
        settings_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        settings_box.set_hexpand(True)
        main_box.append(settings_box)

        # Scroll Mode Section
        mode_section = Gtk.Label(label="Scroll Mode")
        mode_section.add_css_class("section-title")
        mode_section.set_halign(Gtk.Align.START)
        settings_box.append(mode_section)

        mode_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        mode_card.add_css_class("settings-card")
        settings_box.append(mode_card)

        # Mode selection buttons
        mode_buttons = Gtk.Box(spacing=8)
        mode_card.append(mode_buttons)

        self.mode_group = None
        modes = [
            ("smart", "SmartShift", "Auto-switch based on speed"),
            ("ratchet", "Ratchet", "Notched, precise scrolling"),
            ("free", "Free Spin", "Smooth, momentum scrolling"),
        ]

        for mode_id, name, desc in modes:
            btn = Gtk.ToggleButton()
            btn.mode_id = mode_id

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            box.set_margin_start(16)
            box.set_margin_end(16)
            box.set_margin_top(12)
            box.set_margin_bottom(12)
            btn.set_child(box)

            name_label = Gtk.Label(label=name)
            name_label.add_css_class("card-title")
            box.append(name_label)

            desc_label = Gtk.Label(label=desc)
            desc_label.add_css_class("card-description")
            box.append(desc_label)

            if self.mode_group is None:
                self.mode_group = btn
                btn.set_active(True)
            else:
                btn.set_group(self.mode_group)

            btn.connect("toggled", self._on_mode_toggled)
            mode_buttons.append(btn)

        # SmartShift sensitivity
        smartshift_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        smartshift_box.set_margin_top(16)
        mode_card.append(smartshift_box)

        ss_header = Gtk.Box(spacing=12)
        smartshift_box.append(ss_header)

        ss_label = Gtk.Label(label="SmartShift Sensitivity")
        ss_label.add_css_class("card-title")
        ss_label.set_halign(Gtk.Align.START)
        ss_header.append(ss_label)

        self.ss_value = Gtk.Label(label="25")
        self.ss_value.add_css_class("value-label")
        self.ss_value.set_halign(Gtk.Align.END)
        self.ss_value.set_hexpand(True)
        ss_header.append(self.ss_value)

        ss_desc = Gtk.Label(
            label="Lower values switch to free-spin at slower scroll speeds"
        )
        ss_desc.add_css_class("card-description")
        ss_desc.set_halign(Gtk.Align.START)
        smartshift_box.append(ss_desc)

        self.ss_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 1, 50, 1
        )
        self.ss_scale.set_value(25)
        self.ss_scale.set_draw_value(False)
        self.ss_scale.add_css_class("dpi-slider")
        self.ss_scale.connect("value-changed", self._on_ss_changed)
        smartshift_box.append(self.ss_scale)

        # Horizontal scroll section
        h_section = Gtk.Label(label="Horizontal Scroll")
        h_section.add_css_class("section-title")
        h_section.set_halign(Gtk.Align.START)
        settings_box.append(h_section)

        h_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        h_card.add_css_class("settings-card")
        settings_box.append(h_card)

        # Horizontal speed
        h_speed_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        h_card.append(h_speed_box)

        h_header = Gtk.Box(spacing=12)
        h_speed_box.append(h_header)

        h_label = Gtk.Label(label="Thumb Wheel Speed")
        h_label.add_css_class("card-title")
        h_label.set_halign(Gtk.Align.START)
        h_header.append(h_label)

        self.h_value = Gtk.Label(label="100%")
        self.h_value.add_css_class("value-label")
        self.h_value.set_halign(Gtk.Align.END)
        self.h_value.set_hexpand(True)
        h_header.append(self.h_value)

        self.h_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 25, 200, 5
        )
        self.h_scale.set_value(100)
        self.h_scale.set_draw_value(False)
        self.h_scale.connect("value-changed", self._on_h_speed_changed)
        h_speed_box.append(self.h_scale)

        # Direction settings
        direction_section = Gtk.Label(label="Scroll Direction")
        direction_section.add_css_class("section-title")
        direction_section.set_halign(Gtk.Align.START)
        content.append(direction_section)

        direction_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        direction_card.add_css_class("settings-card")
        content.append(direction_card)

        # Invert vertical
        self._add_toggle_row(
            direction_card,
            "Invert Vertical Scroll",
            "Reverse the vertical scroll direction (natural scrolling)",
            "invert_v",
            False
        )

        # Invert horizontal
        self._add_toggle_row(
            direction_card,
            "Invert Horizontal Scroll",
            "Reverse the horizontal scroll direction",
            "invert_h",
            False
        )

        # Hi-res scrolling
        self._add_toggle_row(
            direction_card,
            "High-Resolution Scrolling",
            "Enable smooth pixel-level scrolling (may not work in all apps)",
            "hires",
            True
        )

    def _add_toggle_row(self, container, title, description, setting_key, default_value):
        """Add a toggle setting row"""
        row = Gtk.Box(spacing=12)
        row.add_css_class("settings-row")
        container.append(row)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        text_box.set_hexpand(True)
        row.append(text_box)

        title_label = Gtk.Label(label=title)
        title_label.add_css_class("card-title")
        title_label.set_halign(Gtk.Align.START)
        text_box.append(title_label)

        desc_label = Gtk.Label(label=description)
        desc_label.add_css_class("card-description")
        desc_label.set_wrap(True)
        desc_label.set_halign(Gtk.Align.START)
        text_box.append(desc_label)

        switch = Gtk.Switch()
        switch.set_active(default_value)
        switch.set_valign(Gtk.Align.CENTER)
        switch.connect("notify::active", self._on_toggle_changed, setting_key)
        row.append(switch)

    def _on_mode_toggled(self, button):
        """Handle scroll mode change"""
        if button.get_active():
            mode = button.mode_id
            self.wheel_preview.set_mode(mode)

            # Update labels
            mode_info = {
                "smart": ("SmartShift", "Automatically switches modes"),
                "ratchet": ("Ratchet Mode", "Notched, precise scrolling"),
                "free": ("Free Spin", "Smooth, momentum scrolling"),
            }

            self.mode_label.set_label(mode_info[mode][0])
            self.mode_desc.set_label(mode_info[mode][1])

            # Enable/disable SmartShift sensitivity
            self.ss_scale.set_sensitive(mode == "smart")

            if self.device:
                import threading
                threshold = int(self.ss_scale.get_value())
                enabled = mode == "smart"

                def apply():
                    self.device.set_smartshift(enabled, threshold)

                threading.Thread(target=apply, daemon=True).start()

            # Save to config
            self._save_to_config(smartshift_enabled=(mode == "smart"))

    def _on_ss_changed(self, scale):
        """Handle SmartShift sensitivity change"""
        value = int(scale.get_value())
        self.ss_value.set_label(str(value))

        if self.device:
            import threading

            def apply():
                self.device.set_smartshift(True, value)

            threading.Thread(target=apply, daemon=True).start()

        # Save to config
        self._save_to_config(smartshift_threshold=value)

    def _on_h_speed_changed(self, scale):
        """Handle horizontal speed change"""
        value = int(scale.get_value())
        self.h_value.set_label(f"{value}%")

    def _on_toggle_changed(self, switch, pspec, setting_key):
        """Handle toggle switch change"""
        value = switch.get_active()

        if self.device and setting_key == "hires":
            import threading

            def apply():
                self.device.set_hires_scroll(value, False)

            threading.Thread(target=apply, daemon=True).start()

        # Save to config
        if setting_key == "hires":
            self._save_to_config(hires_enabled=value)
        elif setting_key == "invert_v":
            self._save_to_config(invert_vertical=value)
        elif setting_key == "invert_h":
            self._save_to_config(invert_horizontal=value)

    def _save_to_config(self, **kwargs):
        """Save scroll settings to config"""
        try:
            config_manager = self.window.config_manager
            for key, value in kwargs.items():
                if hasattr(config_manager.config.scroll, key):
                    setattr(config_manager.config.scroll, key, value)
            config_manager.save()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to save config: {e}")

    def update_device(self, device):
        """Update page with new device connection"""
        self.device = device

        if device:
            # Load settings from saved config
            try:
                config = self.window.config_manager.config
                self.ss_scale.set_value(config.scroll.smartshift_threshold)

                # Set mode based on config
                # Find and activate the appropriate mode button
                for child in self.mode_group.get_parent().observe_children():
                    if hasattr(child, 'mode_id'):
                        if config.scroll.smartshift_enabled and child.mode_id == "smart":
                            child.set_active(True)
                            break
            except Exception:
                # Fallback to defaults
                self.ss_scale.set_value(25)
