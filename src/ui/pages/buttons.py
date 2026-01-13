"""
Buttons Page

Configure the 8 programmable buttons and gesture actions.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, GLib

# Control IDs for MX Master 4 buttons
# Format: (CID, Name, Remappable)
# Note: Gesture button is firmware-locked for Actions Ring
BUTTON_CIDS = {
    0: (0x0050, "Left Click", False),
    1: (0x0051, "Right Click", False),
    2: (0x0052, "Middle Click", True),
    3: (0x0053, "Back", True),
    4: (0x0056, "Forward", True),
    5: (0x00C3, "Gesture Button", False),  # Firmware-locked for Actions Ring
    6: (0x00C4, "Smart Shift", True),
    7: (0x01A0, "Thumb Wheel", False),  # Scroll wheel, not a button
}

# Available remap targets (CID -> name)
REMAP_TARGETS = {
    "Default": None,
    "Left Click": 0x0050,
    "Right Click": 0x0051,
    "Middle Click": 0x0052,
    "Back": 0x0053,
    "Forward": 0x0056,
    "Gesture Button": 0x00C3,
    "Smart Shift": 0x00C4,
}


class ButtonConfigRow(Gtk.Box):
    """A row for configuring a single button with inline remap dropdown"""

    def __init__(self, button_id, name, default_action, remappable, on_remap):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)

        self.button_id = button_id
        self.on_remap = on_remap
        self.remappable = remappable
        self.cid = BUTTON_CIDS.get(button_id, (0, name, False))[0]

        self.add_css_class("settings-row")
        self.set_margin_start(8)
        self.set_margin_end(8)

        # Button indicator
        indicator = Gtk.Box()
        indicator.set_size_request(8, 40)
        if remappable:
            indicator.add_css_class("copper-button")
        else:
            indicator.set_opacity(0.3)
        indicator.set_valign(Gtk.Align.CENTER)
        self.append(indicator)

        # Button number
        num_label = Gtk.Label(label=f"{button_id + 1}")
        num_label.add_css_class("value-label")
        num_label.set_size_request(30, -1)
        self.append(num_label)

        # Button info
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        info_box.set_hexpand(True)
        self.append(info_box)

        self.name_label = Gtk.Label(label=name)
        self.name_label.add_css_class("card-title")
        self.name_label.set_halign(Gtk.Align.START)
        info_box.append(self.name_label)

        self.action_label = Gtk.Label(label=default_action if not remappable else "")
        self.action_label.add_css_class("card-description")
        self.action_label.set_halign(Gtk.Align.START)
        info_box.append(self.action_label)

        # Remap dropdown (only for remappable buttons)
        if remappable:
            self.remap_combo = Gtk.ComboBoxText()
            for action_name in REMAP_TARGETS.keys():
                self.remap_combo.append_text(action_name)
            self.remap_combo.set_active(0)  # Default
            self.remap_combo.set_valign(Gtk.Align.CENTER)
            self.remap_combo.connect("changed", self._on_remap_changed)
            self.append(self.remap_combo)
        else:
            # Show "Not remappable" label
            fixed_label = Gtk.Label(label="Fixed")
            fixed_label.add_css_class("card-description")
            fixed_label.set_opacity(0.5)
            fixed_label.set_valign(Gtk.Align.CENTER)
            self.append(fixed_label)
            self.remap_combo = None

    def _on_remap_changed(self, combo):
        """Handle remap selection change"""
        action_name = combo.get_active_text()
        if action_name and self.on_remap:
            target_cid = REMAP_TARGETS.get(action_name)
            self.on_remap(self.button_id, self.cid, target_cid, action_name)

    def set_remap(self, action_name):
        """Set the current remap selection"""
        if self.remap_combo:
            model = self.remap_combo.get_model()
            for i, row in enumerate(model):
                if row[0] == action_name:
                    self.remap_combo.set_active(i)
                    break

    def set_action(self, action_text):
        """Update the displayed action"""
        self.action_label.set_label(action_text)


class ButtonsPage(Gtk.Box):
    """
    Button configuration page

    Features:
    - Interactive button list with quick configure
    - Action picker dialog
    - Gesture configuration
    - Per-application button profiles
    """

    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.device = None
        self.button_rows = []

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

        # Main buttons section
        main_section = Gtk.Label(label="Mouse Buttons")
        main_section.add_css_class("section-title")
        main_section.set_halign(Gtk.Align.START)
        content.append(main_section)

        buttons_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        buttons_card.add_css_class("settings-card")
        content.append(buttons_card)

        # Create button rows from BUTTON_CIDS
        for btn_id in range(8):
            cid, name, remappable = BUTTON_CIDS.get(btn_id, (0, f"Button {btn_id}", False))
            default_action = "Primary Click" if btn_id == 0 else "Secondary Click" if btn_id == 1 else ""
            row = ButtonConfigRow(btn_id, name, default_action, remappable, self._on_button_remap)
            self.button_rows.append(row)
            buttons_card.append(row)

        # Gestures section
        gestures_section = Gtk.Label(label="Gesture Actions")
        gestures_section.add_css_class("section-title")
        gestures_section.set_halign(Gtk.Align.START)
        content.append(gestures_section)

        gestures_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        gestures_card.add_css_class("settings-card")
        content.append(gestures_card)

        gestures_desc = Gtk.Label(
            label="Hold the Gesture Button and move the mouse in a direction to trigger these actions."
        )
        gestures_desc.add_css_class("card-description")
        gestures_desc.set_wrap(True)
        gestures_desc.set_halign(Gtk.Align.START)
        gestures_card.append(gestures_desc)

        # Gesture directions grid
        gesture_grid = Gtk.Grid()
        gesture_grid.set_row_spacing(8)
        gesture_grid.set_column_spacing(16)
        gesture_grid.set_margin_top(16)
        gesture_grid.set_halign(Gtk.Align.CENTER)
        gestures_card.append(gesture_grid)

        # Gesture direction buttons
        gestures = [
            ("↑", "Gesture Up", "Desktop Overview", 1, 0),
            ("←", "Gesture Left", "Previous Desktop", 0, 1),
            ("●", "Center", "Actions Ring", 1, 1),
            ("→", "Gesture Right", "Next Desktop", 2, 1),
            ("↓", "Gesture Down", "Show Windows", 1, 2),
        ]

        for symbol, name, action, col, row in gestures:
            btn = Gtk.Button()
            btn.set_size_request(100, 60)

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            box.set_halign(Gtk.Align.CENTER)
            box.set_valign(Gtk.Align.CENTER)
            btn.set_child(box)

            symbol_label = Gtk.Label(label=symbol)
            symbol_label.add_css_class("value-label")
            box.append(symbol_label)

            action_label = Gtk.Label(label=action)
            action_label.add_css_class("card-description")
            box.append(action_label)

            if col == 1 and row == 1:
                btn.add_css_class("copper-button")
            else:
                btn.add_css_class("ghost-button")

            btn.set_tooltip_text(name)
            gesture_grid.attach(btn, col, row, 1, 1)

        # Application profiles section
        profiles_section = Gtk.Label(label="Application Profiles")
        profiles_section.add_css_class("section-title")
        profiles_section.set_halign(Gtk.Align.START)
        content.append(profiles_section)

        profiles_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        profiles_card.add_css_class("settings-card")
        content.append(profiles_card)

        profiles_desc = Gtk.Label(
            label="Create custom button mappings that activate automatically when specific applications are focused."
        )
        profiles_desc.add_css_class("card-description")
        profiles_desc.set_wrap(True)
        profiles_desc.set_halign(Gtk.Align.START)
        profiles_card.append(profiles_desc)

        # Profile list (placeholder)
        self.profile_list = Gtk.ListBox()
        self.profile_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.profile_list.add_css_class("boxed-list")
        profiles_card.append(self.profile_list)

        # Add placeholder profiles
        self._add_profile_row("Firefox", "firefox", "Custom navigation shortcuts")
        self._add_profile_row("VS Code", "code", "IDE-specific bindings")

        # Add profile button
        add_profile_btn = Gtk.Button(label="Add Application Profile")
        add_profile_btn.add_css_class("ghost-button")
        add_profile_btn.set_halign(Gtk.Align.START)
        add_profile_btn.set_margin_top(8)
        profiles_card.append(add_profile_btn)

    def _add_profile_row(self, name, app_id, description):
        """Add a profile row to the list"""
        row = Gtk.ListBoxRow()

        box = Gtk.Box(spacing=12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        row.set_child(box)

        # App icon (placeholder)
        icon = Gtk.Image.new_from_icon_name("application-x-executable-symbolic")
        icon.set_pixel_size(32)
        box.append(icon)

        # Info
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        info_box.set_hexpand(True)
        box.append(info_box)

        name_label = Gtk.Label(label=name)
        name_label.add_css_class("card-title")
        name_label.set_halign(Gtk.Align.START)
        info_box.append(name_label)

        desc_label = Gtk.Label(label=description)
        desc_label.add_css_class("card-description")
        desc_label.set_halign(Gtk.Align.START)
        info_box.append(desc_label)

        # Edit button
        edit_btn = Gtk.Button.new_from_icon_name("document-edit-symbolic")
        edit_btn.add_css_class("flat")
        edit_btn.set_valign(Gtk.Align.CENTER)
        box.append(edit_btn)

        # Delete button
        del_btn = Gtk.Button.new_from_icon_name("user-trash-symbolic")
        del_btn.add_css_class("flat")
        del_btn.set_valign(Gtk.Align.CENTER)
        box.append(del_btn)

        self.profile_list.append(row)

    def _on_button_remap(self, button_id, cid, target_cid, action_name):
        """Handle button remap from UI"""
        import threading

        if not self.device:
            return

        def apply_remap():
            if target_cid is None:
                # Reset to default (remap to itself)
                self.device.remap_button(cid, cid)
            else:
                # Remap to target
                self.device.remap_button(cid, target_cid)

        threading.Thread(target=apply_remap, daemon=True).start()

        # Save to config
        self._save_button_config(button_id, action_name)

    def _save_button_config(self, button_id, action_name):
        """Save button mapping to config"""
        try:
            config = self.window.config_manager.config
            if button_id < len(config.buttons):
                config.buttons[button_id].action_type = "remap"
                config.buttons[button_id].action_data = action_name
            self.window.config_manager.save()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to save button config: {e}")

    def update_device(self, device):
        """Update page with new device connection"""
        self.device = device

        if device:
            # Load saved button config and apply
            try:
                config = self.window.config_manager.config
                for i, row in enumerate(self.button_rows):
                    if i < len(config.buttons):
                        btn_config = config.buttons[i]
                        if btn_config.action_type == "remap" and btn_config.action_data:
                            row.set_remap(btn_config.action_data)
                            # Apply the remap to device
                            cid = BUTTON_CIDS.get(i, (0, "", False))[0]
                            target_cid = REMAP_TARGETS.get(btn_config.action_data)
                            if target_cid is not None:
                                import threading
                                threading.Thread(
                                    target=lambda c=cid, t=target_cid: device.remap_button(c, t),
                                    daemon=True
                                ).start()
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to load button config: {e}")


class ButtonConfigDialog(Adw.Window):
    """Dialog for configuring a button action"""

    def __init__(self, parent, button_id):
        super().__init__()

        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(400, 500)
        self.set_title(f"Configure Button {button_id + 1}")

        # Header bar
        header = Adw.HeaderBar()

        # Cancel button
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda b: self.close())
        header.pack_start(cancel_btn)

        # Apply button
        apply_btn = Gtk.Button(label="Apply")
        apply_btn.add_css_class("suggested-action")
        apply_btn.connect("clicked", self._on_apply)
        header.pack_end(apply_btn)

        # Main content
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.append(header)
        self.set_content(main_box)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_margin_start(24)
        content.set_margin_end(24)
        content.set_margin_top(16)
        content.set_margin_bottom(24)
        main_box.append(content)

        # Action type selection
        type_label = Gtk.Label(label="Action Type")
        type_label.add_css_class("section-title")
        type_label.set_halign(Gtk.Align.START)
        content.append(type_label)

        action_types = [
            ("default", "Default Action", "Use the button's default behavior"),
            ("keystroke", "Keystroke", "Send keyboard shortcut"),
            ("media", "Media Control", "Play/pause, volume, etc."),
            ("navigation", "Navigation", "Back, forward, scroll"),
            ("command", "Run Command", "Execute a shell command"),
            ("disabled", "Disabled", "Button does nothing"),
        ]

        self.action_group = None
        for action_id, name, desc in action_types:
            row = self._create_action_type_row(action_id, name, desc)
            content.append(row)

        # Keystroke entry (shown when keystroke is selected)
        self.keystroke_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.keystroke_box.set_margin_top(16)
        self.keystroke_box.set_visible(False)
        content.append(self.keystroke_box)

        keystroke_label = Gtk.Label(label="Keystroke")
        keystroke_label.add_css_class("section-title")
        keystroke_label.set_halign(Gtk.Align.START)
        self.keystroke_box.append(keystroke_label)

        self.keystroke_entry = Gtk.Entry()
        self.keystroke_entry.set_placeholder_text("e.g., Ctrl+C or Super+Tab")
        self.keystroke_box.append(self.keystroke_entry)

    def _create_action_type_row(self, action_id, name, description):
        """Create an action type selection row"""
        row = Gtk.Box(spacing=12)
        row.add_css_class("settings-row")

        radio = Gtk.CheckButton()
        if self.action_group is None:
            self.action_group = radio
        else:
            radio.set_group(self.action_group)
        radio.action_id = action_id
        radio.connect("toggled", self._on_action_type_changed)
        row.append(radio)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        text_box.set_hexpand(True)
        row.append(text_box)

        name_label = Gtk.Label(label=name)
        name_label.add_css_class("card-title")
        name_label.set_halign(Gtk.Align.START)
        text_box.append(name_label)

        desc_label = Gtk.Label(label=description)
        desc_label.add_css_class("card-description")
        desc_label.set_halign(Gtk.Align.START)
        text_box.append(desc_label)

        # Make the whole row clickable
        row_gesture = Gtk.GestureClick()
        row_gesture.connect("pressed", lambda g, n, x, y: radio.set_active(True))
        row.add_controller(row_gesture)

        return row

    def _on_action_type_changed(self, radio):
        """Handle action type selection"""
        if radio.get_active():
            action_id = radio.action_id
            self.keystroke_box.set_visible(action_id == "keystroke")

    def _on_apply(self, button):
        """Apply the configuration"""
        # TODO: Save configuration
        self.close()
