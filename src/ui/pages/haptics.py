"""
Haptics Page

Configure haptic feedback patterns, intensity, and triggers.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, GLib
import math
import cairo


class HapticPatternCard(Gtk.Button):
    """
    A card representing a haptic pattern with visual preview
    """

    def __init__(self, pattern_id, name, description, icon_pattern):
        super().__init__()

        self.pattern_id = pattern_id
        self.selected = False

        self.add_css_class("haptic-pattern-card")
        self.set_size_request(140, 120)

        # Content
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        self.set_child(box)

        # Pattern visualization
        self.pattern_vis = Gtk.DrawingArea()
        self.pattern_vis.set_size_request(60, 40)
        self.pattern_vis.set_draw_func(self._draw_pattern)
        self.pattern_vis.icon_pattern = icon_pattern
        box.append(self.pattern_vis)

        # Name
        name_label = Gtk.Label(label=name)
        name_label.add_css_class("card-title")
        box.append(name_label)

        # Description
        desc_label = Gtk.Label(label=description)
        desc_label.add_css_class("card-description")
        desc_label.set_wrap(True)
        desc_label.set_max_width_chars(15)
        box.append(desc_label)

    def _draw_pattern(self, area, cr, width, height):
        """Draw the pattern visualization"""
        pattern = area.icon_pattern
        cx = width / 2
        cy = height / 2

        # Color based on selection
        if self.selected:
            cr.set_source_rgb(0.83, 0.65, 0.46)
        else:
            cr.set_source_rgb(0.5, 0.5, 0.52)

        # Draw pattern-specific visualization
        if pattern == "pulse":
            # Concentric circles
            for i in range(3):
                radius = 8 + i * 8
                cr.set_line_width(2)
                cr.arc(cx, cy, radius, 0, 2 * math.pi)
                cr.stroke()
        elif pattern == "click":
            # Single sharp peak
            cr.set_line_width(2)
            cr.move_to(cx - 20, cy)
            cr.line_to(cx - 5, cy)
            cr.line_to(cx, cy - 15)
            cr.line_to(cx + 5, cy)
            cr.line_to(cx + 20, cy)
            cr.stroke()
        elif pattern == "double":
            # Two peaks
            cr.set_line_width(2)
            cr.move_to(cx - 25, cy)
            cr.line_to(cx - 15, cy)
            cr.line_to(cx - 10, cy - 12)
            cr.line_to(cx - 5, cy)
            cr.line_to(cx + 5, cy)
            cr.line_to(cx + 10, cy - 12)
            cr.line_to(cx + 15, cy)
            cr.line_to(cx + 25, cy)
            cr.stroke()
        elif pattern == "ramp":
            # Rising line
            cr.set_line_width(2)
            cr.move_to(cx - 25, cy + 10)
            cr.line_to(cx, cy - 10)
            cr.line_to(cx + 5, cy - 10)
            cr.line_to(cx + 25, cy + 10)
            cr.stroke()
        elif pattern == "wave":
            # Sine wave
            cr.set_line_width(2)
            cr.move_to(cx - 25, cy)
            for x in range(-25, 26):
                y = math.sin(x * 0.3) * 10
                cr.line_to(cx + x, cy + y)
            cr.stroke()
        else:
            # Default dot
            cr.arc(cx, cy, 10, 0, 2 * math.pi)
            cr.fill()

    def set_selected(self, selected):
        """Update selection state"""
        self.selected = selected
        if selected:
            self.add_css_class("selected")
        else:
            self.remove_css_class("selected")
        self.pattern_vis.queue_draw()


class HapticsPage(Gtk.Box):
    """
    Haptic feedback configuration page

    Features:
    - Pattern selection with visual preview
    - Intensity control
    - Event trigger configuration
    - Test buttons
    """

    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.device = None
        self.pattern_cards = []
        self.current_pattern = 2  # Default to medium click (pattern index 2)

        self.add_css_class("page-content")
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(16)
        self.set_margin_bottom(24)
        self.set_spacing(24)

        # Scrolled window for content
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        self.append(scroll)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        scroll.set_child(content)

        # Intensity section
        intensity_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        intensity_card.add_css_class("settings-card")
        content.append(intensity_card)

        intensity_header = Gtk.Box(spacing=12)
        intensity_card.append(intensity_header)

        intensity_title = Gtk.Label(label="Haptic Intensity")
        intensity_title.add_css_class("section-title")
        intensity_title.set_halign(Gtk.Align.START)
        intensity_header.append(intensity_title)

        # Intensity value display
        self.intensity_label = Gtk.Label(label="Medium")
        self.intensity_label.add_css_class("value-label")
        self.intensity_label.set_halign(Gtk.Align.END)
        self.intensity_label.set_hexpand(True)
        intensity_header.append(self.intensity_label)

        # Intensity slider
        self.intensity_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 3, 1
        )
        self.intensity_scale.set_value(2)  # Medium
        self.intensity_scale.set_draw_value(False)
        self.intensity_scale.set_hexpand(True)
        self.intensity_scale.add_css_class("dpi-slider")

        # Custom marks
        self.intensity_scale.add_mark(0, Gtk.PositionType.BOTTOM, "Subtle")
        self.intensity_scale.add_mark(1, Gtk.PositionType.BOTTOM, "Low")
        self.intensity_scale.add_mark(2, Gtk.PositionType.BOTTOM, "Medium")
        self.intensity_scale.add_mark(3, Gtk.PositionType.BOTTOM, "High")

        self.intensity_scale.connect("value-changed", self._on_intensity_changed)
        intensity_card.append(self.intensity_scale)

        # Patterns section
        patterns_section = Gtk.Label(label="Feedback Patterns")
        patterns_section.add_css_class("section-title")
        patterns_section.set_halign(Gtk.Align.START)
        content.append(patterns_section)

        # Pattern grid
        patterns_flow = Gtk.FlowBox()
        patterns_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        patterns_flow.set_max_children_per_line(6)
        patterns_flow.set_min_children_per_line(3)
        patterns_flow.set_row_spacing(12)
        patterns_flow.set_column_spacing(12)
        content.append(patterns_flow)

        # Define patterns (MX Master 4 supports patterns 0-14)
        patterns = [
            (0, "Subtle Tick", "Light feedback", "pulse"),
            (1, "Light Click", "Subtle tap", "click"),
            (2, "Medium Click", "Standard feel", "click"),
            (3, "Strong Click", "Firm response", "click"),
            (4, "Soft Bump", "Gentle nudge", "pulse"),
            (5, "Double Tap", "Two quick taps", "double"),
            (6, "Triple Tap", "Three quick taps", "double"),
            (7, "Ramp Up", "Building intensity", "ramp"),
            (8, "Ramp Down", "Fading intensity", "ramp"),
            (9, "Pulse", "Light vibration", "wave"),
            (10, "Strong Pulse", "Strong vibration", "wave"),
            (11, "Alert", "Attention grab", "pulse"),
            (12, "Success", "Confirmation", "click"),
            (13, "Error", "Warning signal", "pulse"),
            (14, "Notification", "System alert", "pulse"),
        ]

        for pattern_id, name, desc, icon in patterns:
            card = HapticPatternCard(pattern_id, name, desc, icon)
            card.connect("clicked", self._on_pattern_clicked, pattern_id)
            self.pattern_cards.append(card)
            patterns_flow.append(card)

        # Select default
        if self.pattern_cards:
            self.pattern_cards[2].set_selected(True)

        # Event triggers section
        triggers_section = Gtk.Label(label="Event Triggers")
        triggers_section.add_css_class("section-title")
        triggers_section.set_halign(Gtk.Align.START)
        triggers_section.set_margin_top(8)
        content.append(triggers_section)

        triggers_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        triggers_card.add_css_class("settings-card")
        content.append(triggers_card)

        # Notification trigger
        self._add_trigger_row(
            triggers_card,
            "Notifications",
            "Haptic feedback when notifications arrive",
            "notification_enabled",
            True
        )

        # Scroll end trigger
        self._add_trigger_row(
            triggers_card,
            "Scroll Endpoints",
            "Feel when reaching document top/bottom",
            "scroll_end_enabled",
            False
        )

        # Device switch trigger
        self._add_trigger_row(
            triggers_card,
            "Device Switch",
            "Confirm when switching paired devices",
            "device_switch_enabled",
            True
        )

        # App-specific section
        app_section = Gtk.Label(label="Application-Specific Haptics")
        app_section.add_css_class("section-title")
        app_section.set_halign(Gtk.Align.START)
        app_section.set_margin_top(8)
        content.append(app_section)

        app_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        app_card.add_css_class("settings-card")
        content.append(app_card)

        app_desc = Gtk.Label(
            label="Configure different haptic patterns for specific applications. "
                  "These override the global settings when the application is focused."
        )
        app_desc.add_css_class("card-description")
        app_desc.set_wrap(True)
        app_desc.set_halign(Gtk.Align.START)
        app_card.append(app_desc)

        add_app_btn = Gtk.Button(label="Add Application Rule")
        add_app_btn.add_css_class("ghost-button")
        add_app_btn.set_halign(Gtk.Align.START)
        add_app_btn.set_margin_top(8)
        app_card.append(add_app_btn)

        # Test section at bottom
        test_box = Gtk.Box(spacing=12)
        test_box.set_margin_top(16)
        content.append(test_box)

        test_btn = Gtk.Button(label="Test Selected Pattern")
        test_btn.add_css_class("copper-button")
        test_btn.connect("clicked", self._on_test_pattern)
        test_box.append(test_btn)

        test_all_btn = Gtk.Button(label="Preview All Patterns")
        test_all_btn.add_css_class("ghost-button")
        test_all_btn.connect("clicked", self._on_test_all)
        test_box.append(test_all_btn)

    def _add_trigger_row(self, container, title, description, setting_key, default_value):
        """Add a trigger configuration row"""
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
        desc_label.set_halign(Gtk.Align.START)
        text_box.append(desc_label)

        switch = Gtk.Switch()
        switch.set_active(default_value)
        switch.set_valign(Gtk.Align.CENTER)
        switch.connect("notify::active", self._on_trigger_changed, setting_key)
        row.append(switch)

    def _on_intensity_changed(self, scale):
        """Handle intensity change"""
        value = int(scale.get_value())
        labels = ["Subtle", "Low", "Medium", "High"]
        self.intensity_label.set_label(labels[value])

        # Save to config
        self._save_to_config(intensity=value)

    def _on_pattern_clicked(self, button, pattern_id):
        """Handle pattern selection"""
        self.current_pattern = pattern_id

        # Update selection state
        for card in self.pattern_cards:
            card.set_selected(card.pattern_id == pattern_id)

        # Save to config
        self._save_to_config(selected_pattern=pattern_id)

        # Test the pattern
        self._trigger_pattern(pattern_id)

    def _on_trigger_changed(self, switch, pspec, setting_key):
        """Handle trigger setting change"""
        # Save to config
        self._save_to_config(**{setting_key: switch.get_active()})

    def _on_test_pattern(self, button):
        """Test the currently selected pattern"""
        self._trigger_pattern(self.current_pattern)

    def _on_test_all(self, button):
        """Preview all patterns in sequence"""
        patterns = [card.pattern_id for card in self.pattern_cards]

        def play_next(index):
            if index < len(patterns):
                self._trigger_pattern(patterns[index])
                # Highlight the card
                for card in self.pattern_cards:
                    card.set_selected(card.pattern_id == patterns[index])
                GLib.timeout_add(500, play_next, index + 1)
            else:
                # Restore original selection
                for card in self.pattern_cards:
                    card.set_selected(card.pattern_id == self.current_pattern)

        play_next(0)

    def _trigger_pattern(self, pattern_id):
        """Trigger a haptic pattern"""
        import threading

        if self.device:
            # Trigger haptic in background thread to avoid blocking UI
            def trigger():
                self.device.trigger_haptic(pattern_id)
            threading.Thread(target=trigger, daemon=True).start()

        # Trigger visual feedback on overview page
        if hasattr(self.window, '_pages') and 'overview' in self.window._pages:
            self.window._pages['overview'].mouse_preview.trigger_haptic_animation()

    def _save_to_config(self, **kwargs):
        """Save haptic settings to config"""
        try:
            config_manager = self.window.config_manager
            for key, value in kwargs.items():
                if hasattr(config_manager.config.haptics, key):
                    setattr(config_manager.config.haptics, key, value)
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

                # Load intensity
                self.intensity_scale.set_value(config.haptics.intensity)

                # Load selected pattern
                pattern_id = config.haptics.selected_pattern
                self.current_pattern = pattern_id
                for card in self.pattern_cards:
                    card.set_selected(card.pattern_id == pattern_id)

            except Exception:
                # Fallback to defaults
                self.intensity_scale.set_value(2)
                self.current_pattern = 2
                if self.pattern_cards:
                    self.pattern_cards[2].set_selected(True)
