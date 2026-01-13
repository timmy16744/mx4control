"""
Pointer Page

Configure DPI, sensitivity, and pointer behavior.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, GLib
import math
import cairo


class DPISliderWidget(Gtk.Box):
    """
    Custom DPI slider with visual feedback and preset buttons
    """

    def __init__(self, on_change=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)

        self.on_change = on_change
        self._updating = False

        # DPI display
        display_box = Gtk.Box(spacing=8)
        display_box.set_halign(Gtk.Align.CENTER)
        self.append(display_box)

        self.dpi_label = Gtk.Label(label="1000")
        self.dpi_label.add_css_class("value-label")
        display_box.append(self.dpi_label)

        unit_label = Gtk.Label(label="DPI")
        unit_label.add_css_class("unit-label")
        unit_label.set_valign(Gtk.Align.END)
        unit_label.set_margin_bottom(4)
        display_box.append(unit_label)

        # Main slider
        self.scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 100, 8000, 50
        )
        self.scale.set_value(1000)
        self.scale.set_draw_value(False)
        self.scale.add_css_class("dpi-slider")
        self.scale.set_hexpand(True)
        self.scale.connect("value-changed", self._on_value_changed)
        self.append(self.scale)

        # Preset buttons
        presets_box = Gtk.Box(spacing=8)
        presets_box.set_halign(Gtk.Align.CENTER)
        self.append(presets_box)

        presets = [400, 800, 1000, 1600, 2000, 4000, 8000]
        self.preset_buttons = []

        for dpi in presets:
            btn = Gtk.Button(label=str(dpi))
            btn.add_css_class("ghost-button")
            btn.connect("clicked", self._on_preset_clicked, dpi)
            self.preset_buttons.append((dpi, btn))
            presets_box.append(btn)

        self._update_preset_highlight()

    def _on_value_changed(self, scale):
        """Handle slider value change"""
        if self._updating:
            return

        dpi = int(scale.get_value())
        self.dpi_label.set_label(str(dpi))
        self._update_preset_highlight()

        if self.on_change:
            self.on_change(dpi)

    def _on_preset_clicked(self, button, dpi):
        """Handle preset button click"""
        self.set_value(dpi)

    def _update_preset_highlight(self):
        """Highlight the active preset button"""
        current = int(self.scale.get_value())

        for dpi, btn in self.preset_buttons:
            if dpi == current:
                btn.remove_css_class("ghost-button")
                btn.add_css_class("copper-button")
            else:
                btn.remove_css_class("copper-button")
                btn.add_css_class("ghost-button")

    def set_value(self, dpi):
        """Set the DPI value"""
        self._updating = True
        self.scale.set_value(dpi)
        self.dpi_label.set_label(str(dpi))
        self._update_preset_highlight()
        self._updating = False

        if self.on_change:
            self.on_change(dpi)

    def get_value(self):
        """Get current DPI value"""
        return int(self.scale.get_value())


class SensitivityPreview(Gtk.DrawingArea):
    """
    Visual preview of pointer sensitivity

    Shows a representation of how far the pointer moves
    for a given physical mouse movement.
    """

    def __init__(self):
        super().__init__()

        self.set_size_request(200, 100)
        self.set_draw_func(self._draw)
        self.dpi = 1000
        self.cursor_x = 0

        # Animation
        self._animation_id = None

    def _draw(self, area, cr, width, height):
        """Draw the sensitivity preview"""
        cx = width / 2
        cy = height / 2

        # Background grid
        cr.set_source_rgba(1, 1, 1, 0.05)
        for x in range(0, int(width), 20):
            cr.move_to(x, 0)
            cr.line_to(x, height)
            cr.stroke()
        for y in range(0, int(height), 20):
            cr.move_to(0, y)
            cr.line_to(width, y)
            cr.stroke()

        # Physical movement indicator (bottom)
        cr.set_source_rgba(1, 1, 1, 0.3)
        cr.set_line_width(2)
        cr.move_to(cx - 40, height - 15)
        cr.line_to(cx + 40, height - 15)
        cr.stroke()

        # Arrows
        cr.move_to(cx - 40, height - 15)
        cr.line_to(cx - 35, height - 20)
        cr.move_to(cx - 40, height - 15)
        cr.line_to(cx - 35, height - 10)
        cr.stroke()

        cr.move_to(cx + 40, height - 15)
        cr.line_to(cx + 35, height - 20)
        cr.move_to(cx + 40, height - 15)
        cr.line_to(cx + 35, height - 10)
        cr.stroke()

        # Cursor trail based on DPI
        sensitivity = self.dpi / 1000.0
        trail_length = 40 * sensitivity

        # Trail
        gradient = cairo.LinearGradient(
            cx + self.cursor_x - trail_length, cy,
            cx + self.cursor_x, cy
        )
        gradient.add_color_stop_rgba(0, 0.83, 0.65, 0.46, 0)
        gradient.add_color_stop_rgba(1, 0.83, 0.65, 0.46, 0.8)

        cr.set_source(gradient)
        cr.set_line_width(4)
        cr.move_to(cx + self.cursor_x - trail_length, cy)
        cr.line_to(cx + self.cursor_x, cy)
        cr.stroke()

        # Cursor
        cr.set_source_rgb(0.83, 0.65, 0.46)
        cr.arc(cx + self.cursor_x, cy, 8, 0, 2 * math.pi)
        cr.fill()

        # Inner dot
        cr.set_source_rgb(0.15, 0.15, 0.17)
        cr.arc(cx + self.cursor_x, cy, 3, 0, 2 * math.pi)
        cr.fill()

    def set_dpi(self, dpi):
        """Update DPI for visualization"""
        self.dpi = dpi
        self._animate()

    def _animate(self):
        """Animate cursor movement preview"""
        if self._animation_id:
            GLib.source_remove(self._animation_id)

        sensitivity = self.dpi / 1000.0
        target_x = 40 * (sensitivity - 1)

        def step():
            diff = target_x - self.cursor_x
            if abs(diff) < 1:
                self.cursor_x = target_x
                self.queue_draw()
                self._animation_id = None
                return False

            self.cursor_x += diff * 0.2
            self.queue_draw()
            return True

        self._animation_id = GLib.timeout_add(16, step)


class PointerPage(Gtk.Box):
    """
    Pointer settings page

    Features:
    - DPI slider with presets
    - Sensitivity preview
    - Acceleration curve
    - Angle snapping toggle
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

        # DPI Section
        dpi_section = Gtk.Label(label="Pointer Speed (DPI)")
        dpi_section.add_css_class("section-title")
        dpi_section.set_halign(Gtk.Align.START)
        content.append(dpi_section)

        dpi_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        dpi_card.add_css_class("settings-card")
        content.append(dpi_card)

        # DPI description
        dpi_desc = Gtk.Label(
            label="Higher DPI means the cursor moves faster across the screen "
                  "for the same physical mouse movement."
        )
        dpi_desc.add_css_class("card-description")
        dpi_desc.set_wrap(True)
        dpi_desc.set_halign(Gtk.Align.START)
        dpi_card.append(dpi_desc)

        # DPI Slider
        self.dpi_slider = DPISliderWidget(on_change=self._on_dpi_changed)
        dpi_card.append(self.dpi_slider)

        # Sensitivity preview
        preview_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        preview_box.set_margin_top(16)
        dpi_card.append(preview_box)

        preview_label = Gtk.Label(label="Movement Preview")
        preview_label.add_css_class("card-description")
        preview_label.set_halign(Gtk.Align.START)
        preview_box.append(preview_label)

        self.sensitivity_preview = SensitivityPreview()
        self.sensitivity_preview.add_css_class("settings-card")
        preview_box.append(self.sensitivity_preview)

        # Sensor settings section
        sensor_section = Gtk.Label(label="Sensor Settings")
        sensor_section.add_css_class("section-title")
        sensor_section.set_halign(Gtk.Align.START)
        content.append(sensor_section)

        sensor_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        sensor_card.add_css_class("settings-card")
        content.append(sensor_card)

        # Angle snapping
        self._add_toggle_row(
            sensor_card,
            "Angle Snapping",
            "Smooth out diagonal movements to straight lines. "
            "Useful for design work, not recommended for gaming.",
            "angle_snapping",
            False
        )

        # Lift-off distance (if supported)
        self._add_toggle_row(
            sensor_card,
            "Low Lift-Off Distance",
            "Reduce the height at which the sensor stops tracking. "
            "Better for fast movements but may cause unwanted tracking.",
            "low_lod",
            True
        )

        # System integration section
        system_section = Gtk.Label(label="System Integration")
        system_section.add_css_class("section-title")
        system_section.set_halign(Gtk.Align.START)
        content.append(system_section)

        system_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        system_card.add_css_class("settings-card")
        content.append(system_card)

        system_desc = Gtk.Label(
            label="These settings override system-level pointer configuration. "
                  "Changes are applied directly to the mouse firmware."
        )
        system_desc.add_css_class("card-description")
        system_desc.set_wrap(True)
        system_desc.set_halign(Gtk.Align.START)
        system_card.append(system_desc)

        # Pointer acceleration (system level info)
        info_row = Gtk.Box(spacing=12)
        info_row.set_margin_top(8)
        system_card.append(info_row)

        info_icon = Gtk.Image.new_from_icon_name("dialog-information-symbolic")
        info_icon.set_opacity(0.6)
        info_row.append(info_icon)

        info_label = Gtk.Label(
            label="Pointer acceleration is controlled by your desktop environment. "
                  "This app sets raw DPI which is then modified by system acceleration settings."
        )
        info_label.add_css_class("card-description")
        info_label.set_wrap(True)
        info_label.set_hexpand(True)
        info_label.set_halign(Gtk.Align.START)
        info_row.append(info_label)

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
        row.append(switch)

    def _on_dpi_changed(self, dpi):
        """Handle DPI change"""
        self.sensitivity_preview.set_dpi(dpi)

        if self.device:
            import threading

            def apply():
                self.device.set_dpi(dpi)

            threading.Thread(target=apply, daemon=True).start()

        # Save to config
        self._save_to_config(dpi=dpi)

    def _save_to_config(self, dpi=None):
        """Save pointer settings to config"""
        try:
            config_manager = self.window.config_manager
            if dpi is not None:
                config_manager.config.pointer.dpi = dpi
            config_manager.save()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to save config: {e}")

    def update_device(self, device):
        """Update page with new device connection"""
        self.device = device

        if device:
            # Load DPI from saved config (not from device, which is unreliable)
            try:
                config = self.window.config_manager.config
                saved_dpi = config.pointer.dpi
                self.dpi_slider.set_value(saved_dpi)
                self.sensitivity_preview.set_dpi(saved_dpi)
            except Exception:
                # Fallback to default
                self.dpi_slider.set_value(1000)
                self.sensitivity_preview.set_dpi(1000)
