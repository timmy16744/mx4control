"""
Actions Ring Page

Configure the radial menu system with per-application profiles.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, GLib, Gdk
import math
import cairo

from services.app_profiles import (
    get_profile_manager,
    AppProfile,
    ActionSlice,
    InstalledApp,
    CATEGORY_TEMPLATES,
)


class RadialMenuWidget(Gtk.DrawingArea):
    """Interactive radial menu preview widget"""

    def __init__(self, on_segment_click=None):
        super().__init__()

        self.set_size_request(350, 350)
        self.set_draw_func(self._draw)
        self.set_can_focus(True)

        self.on_segment_click = on_segment_click
        self.selected_segment = None
        self.hover_segment = None

        # Segments from profile
        self.segments = []

        # Mouse tracking
        motion_controller = Gtk.EventControllerMotion()
        motion_controller.connect("motion", self._on_motion)
        motion_controller.connect("leave", self._on_leave)
        self.add_controller(motion_controller)

        click_controller = Gtk.GestureClick()
        click_controller.connect("pressed", self._on_click)
        self.add_controller(click_controller)

    def set_profile(self, profile: AppProfile):
        """Load segments from a profile"""
        self.segments = []
        for slice in profile.slices:
            self.segments.append({
                "label": slice.label,
                "icon": slice.icon,
                "action_type": slice.action_type,
                "action_data": slice.action_data,
            })
        # Pad to 8
        while len(self.segments) < 8:
            self.segments.append({"label": "", "icon": "", "action_type": "disabled", "action_data": ""})
        self.queue_draw()

    def _draw(self, area, cr, width, height):
        """Draw the radial menu"""
        cx = width / 2
        cy = height / 2
        outer_radius = min(width, height) / 2 - 20
        inner_radius = outer_radius * 0.35
        segment_count = 8

        # Colors
        bg_color = (0.14, 0.14, 0.16)
        segment_color = (0.18, 0.18, 0.20)
        hover_color = (0.22, 0.22, 0.25)
        selected_color = (0.83, 0.65, 0.46, 0.2)
        border_color = (1, 1, 1, 0.08)
        accent_color = (0.83, 0.65, 0.46)
        text_color = (0.94, 0.93, 0.91)
        disabled_color = (0.4, 0.4, 0.42)

        # Draw segments
        for i in range(segment_count):
            start_angle = (i * 2 * math.pi / segment_count) - math.pi / 2 - math.pi / segment_count
            end_angle = ((i + 1) * 2 * math.pi / segment_count) - math.pi / 2 - math.pi / segment_count

            segment = self.segments[i] if i < len(self.segments) else {}
            is_disabled = not segment.get("label") or segment.get("action_type") == "disabled"

            # Segment background
            if i == self.selected_segment:
                cr.set_source_rgba(*selected_color)
            elif i == self.hover_segment:
                cr.set_source_rgb(*hover_color)
            else:
                cr.set_source_rgb(*segment_color)

            cr.new_path()
            cr.arc(cx, cy, outer_radius, start_angle, end_angle)
            cr.arc_negative(cx, cy, inner_radius, end_angle, start_angle)
            cr.close_path()
            cr.fill()

            # Border
            if i == self.selected_segment:
                cr.set_source_rgba(*accent_color, 1)
                cr.set_line_width(2)
            else:
                cr.set_source_rgba(*border_color)
                cr.set_line_width(1)

            cr.new_path()
            cr.arc(cx, cy, outer_radius, start_angle, end_angle)
            cr.arc_negative(cx, cy, inner_radius, end_angle, start_angle)
            cr.close_path()
            cr.stroke()

            # Content
            mid_angle = (start_angle + end_angle) / 2
            mid_radius = (inner_radius + outer_radius) / 2
            label_x = cx + math.cos(mid_angle) * mid_radius
            label_y = cy + math.sin(mid_angle) * mid_radius

            # Icon circle
            icon_y = label_y - 10
            if is_disabled:
                cr.set_source_rgb(*disabled_color)
            elif i == self.selected_segment:
                cr.set_source_rgb(*accent_color)
            else:
                cr.set_source_rgb(*text_color)

            cr.arc(label_x, icon_y, 12, 0, 2 * math.pi)
            cr.set_line_width(1.5)
            cr.stroke()

            if not is_disabled:
                cr.arc(label_x, icon_y, 3, 0, 2 * math.pi)
                cr.fill()

            # Label
            cr.select_font_face("sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(10)

            label = segment.get("label", "")
            if label:
                extents = cr.text_extents(label)
                cr.move_to(label_x - extents.width / 2, label_y + 18)
                cr.show_text(label)

        # Center circle
        cr.set_source_rgb(*bg_color)
        cr.arc(cx, cy, inner_radius - 5, 0, 2 * math.pi)
        cr.fill()

        cr.set_source_rgba(*accent_color, 0.5)
        cr.set_line_width(2)
        cr.arc(cx, cy, inner_radius - 5, 0, 2 * math.pi)
        cr.stroke()

        cr.set_source_rgb(*accent_color)
        cr.arc(cx, cy, 15, 0, 2 * math.pi)
        cr.fill()

    def _get_segment_at(self, x, y):
        width = self.get_width()
        height = self.get_height()
        cx = width / 2
        cy = height / 2

        dx = x - cx
        dy = y - cy
        distance = math.sqrt(dx * dx + dy * dy)

        outer_radius = min(width, height) / 2 - 20
        inner_radius = outer_radius * 0.35

        if distance < inner_radius or distance > outer_radius:
            return None

        angle = math.atan2(dy, dx) + math.pi / 2 + math.pi / 8
        if angle < 0:
            angle += 2 * math.pi

        return int(angle / (2 * math.pi) * 8) % 8

    def _on_motion(self, controller, x, y):
        segment = self._get_segment_at(x, y)
        if segment != self.hover_segment:
            self.hover_segment = segment
            self.queue_draw()

    def _on_leave(self, controller):
        self.hover_segment = None
        self.queue_draw()

    def _on_click(self, gesture, n_press, x, y):
        segment = self._get_segment_at(x, y)
        if segment is not None:
            self.selected_segment = segment
            self.queue_draw()
            if self.on_segment_click:
                seg_data = self.segments[segment] if segment < len(self.segments) else {}
                self.on_segment_click(segment, seg_data)


class ActionsRingPage(Gtk.Box):
    """Actions Ring configuration page with per-app profiles"""

    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.device = None
        self.current_segment = None
        self.current_profile = None
        self.profile_manager = get_profile_manager()

        self.add_css_class("page-content")
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(16)
        self.set_margin_bottom(24)
        self.set_spacing(16)

        # Initialize profile list before building UI
        self._profile_list = []

        self._build_ui()
        self._load_profiles()

    def _build_ui(self):
        """Build the page UI"""
        # Header with app selector
        header_box = Gtk.Box(spacing=16)
        self.append(header_box)

        # App profile selector
        profile_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        header_box.append(profile_box)

        profile_label = Gtk.Label(label="Application Profile")
        profile_label.add_css_class("card-description")
        profile_label.set_halign(Gtk.Align.START)
        profile_box.append(profile_label)

        profile_selector_box = Gtk.Box(spacing=8)
        profile_box.append(profile_selector_box)

        self.profile_dropdown = Gtk.DropDown()
        self.profile_dropdown.set_size_request(250, -1)
        self.profile_dropdown.connect("notify::selected", self._on_profile_changed)
        profile_selector_box.append(self.profile_dropdown)

        add_profile_btn = Gtk.Button.new_from_icon_name("list-add-symbolic")
        add_profile_btn.add_css_class("flat")
        add_profile_btn.set_tooltip_text("Add profile for application")
        add_profile_btn.connect("clicked", self._on_add_profile)
        profile_selector_box.append(add_profile_btn)

        delete_profile_btn = Gtk.Button.new_from_icon_name("user-trash-symbolic")
        delete_profile_btn.add_css_class("flat")
        delete_profile_btn.set_tooltip_text("Delete current profile")
        delete_profile_btn.connect("clicked", self._on_delete_profile)
        profile_selector_box.append(delete_profile_btn)

        # Spacer
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        header_box.append(spacer)

        # Current app indicator
        self.current_app_label = Gtk.Label(label="Active: Default")
        self.current_app_label.add_css_class("card-description")
        self.current_app_label.set_halign(Gtk.Align.END)
        header_box.append(self.current_app_label)

        # Main content
        main_box = Gtk.Box(spacing=24)
        main_box.set_vexpand(True)
        self.append(main_box)

        # Left: Radial menu preview
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        main_box.append(left_box)

        preview_label = Gtk.Label(label="Menu Preview")
        preview_label.add_css_class("section-title")
        preview_label.set_halign(Gtk.Align.START)
        left_box.append(preview_label)

        preview_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        preview_card.add_css_class("settings-card")
        left_box.append(preview_card)

        self.radial_menu = RadialMenuWidget(on_segment_click=self._on_segment_selected)
        preview_card.append(self.radial_menu)

        preview_hint = Gtk.Label(label="Click a segment to edit")
        preview_hint.add_css_class("card-description")
        preview_hint.set_margin_top(8)
        preview_card.append(preview_hint)

        # Right: Segment editor
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        right_box.set_hexpand(True)
        main_box.append(right_box)

        # Segment config
        config_label = Gtk.Label(label="Segment Configuration")
        config_label.add_css_class("section-title")
        config_label.set_halign(Gtk.Align.START)
        right_box.append(config_label)

        self.config_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.config_card.add_css_class("settings-card")
        right_box.append(self.config_card)

        # No selection placeholder
        self.no_selection_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.no_selection_box.set_halign(Gtk.Align.CENTER)
        self.no_selection_box.set_valign(Gtk.Align.CENTER)
        self.no_selection_box.set_vexpand(True)
        self.config_card.append(self.no_selection_box)

        no_sel_icon = Gtk.Image.new_from_icon_name("edit-select-all-symbolic")
        no_sel_icon.set_pixel_size(48)
        no_sel_icon.set_opacity(0.3)
        self.no_selection_box.append(no_sel_icon)

        no_sel_label = Gtk.Label(label="Select a segment to configure")
        no_sel_label.add_css_class("card-description")
        self.no_selection_box.append(no_sel_label)

        # Segment editor
        self.editor_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.editor_box.set_visible(False)
        self.config_card.append(self.editor_box)

        self.segment_title = Gtk.Label(label="Segment 1")
        self.segment_title.add_css_class("card-title")
        self.segment_title.set_halign(Gtk.Align.START)
        self.editor_box.append(self.segment_title)

        # Label
        label_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.editor_box.append(label_box)

        Gtk.Label(label="Label").set_halign(Gtk.Align.START)
        label_lbl = Gtk.Label(label="Label")
        label_lbl.add_css_class("card-description")
        label_lbl.set_halign(Gtk.Align.START)
        label_box.append(label_lbl)

        self.label_entry = Gtk.Entry()
        self.label_entry.set_placeholder_text("e.g., Copy")
        self.label_entry.connect("changed", self._on_entry_changed)
        label_box.append(self.label_entry)

        # Action type
        type_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.editor_box.append(type_box)

        type_lbl = Gtk.Label(label="Action Type")
        type_lbl.add_css_class("card-description")
        type_lbl.set_halign(Gtk.Align.START)
        type_box.append(type_lbl)

        self.type_dropdown = Gtk.DropDown.new_from_strings([
            "Keystroke",
            "Command",
            "Application",
            "Disabled"
        ])
        self.type_dropdown.connect("notify::selected", self._on_type_changed)
        type_box.append(self.type_dropdown)

        # Action data
        data_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.editor_box.append(data_box)

        self.data_label = Gtk.Label(label="Keystroke")
        self.data_label.add_css_class("card-description")
        self.data_label.set_halign(Gtk.Align.START)
        data_box.append(self.data_label)

        self.data_entry = Gtk.Entry()
        self.data_entry.set_placeholder_text("e.g., ctrl+c")
        self.data_entry.connect("changed", self._on_entry_changed)
        data_box.append(self.data_entry)

        # Common shortcuts
        shortcuts_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        shortcuts_box.set_margin_top(8)
        self.editor_box.append(shortcuts_box)

        shortcuts_lbl = Gtk.Label(label="Quick Actions")
        shortcuts_lbl.add_css_class("card-description")
        shortcuts_lbl.set_halign(Gtk.Align.START)
        shortcuts_box.append(shortcuts_lbl)

        quick_grid = Gtk.FlowBox()
        quick_grid.set_selection_mode(Gtk.SelectionMode.NONE)
        quick_grid.set_max_children_per_line(4)
        quick_grid.set_column_spacing(4)
        quick_grid.set_row_spacing(4)
        shortcuts_box.append(quick_grid)

        quick_actions = [
            ("Copy", "ctrl+c"),
            ("Paste", "ctrl+v"),
            ("Cut", "ctrl+x"),
            ("Undo", "ctrl+z"),
            ("Redo", "ctrl+shift+z"),
            ("Save", "ctrl+s"),
            ("Find", "ctrl+f"),
            ("Close", "ctrl+w"),
        ]

        for label, shortcut in quick_actions:
            btn = Gtk.Button(label=label)
            btn.add_css_class("flat")
            btn.add_css_class("pill")
            btn.connect("clicked", lambda b, l=label, s=shortcut: self._quick_set(l, s))
            quick_grid.append(btn)

        # Template section
        template_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        template_box.set_margin_top(16)
        right_box.append(template_box)

        template_label = Gtk.Label(label="Apply Template")
        template_label.add_css_class("section-title")
        template_label.set_halign(Gtk.Align.START)
        template_box.append(template_label)

        template_card = Gtk.Box(spacing=8)
        template_card.add_css_class("settings-card")
        template_box.append(template_card)

        templates = ["Default", "Browser", "Editor", "Terminal", "Media", "Graphics", "Office"]
        for tmpl in templates:
            btn = Gtk.Button(label=tmpl)
            btn.add_css_class("flat")
            btn.connect("clicked", lambda b, t=tmpl.lower(): self._apply_template(t))
            template_card.append(btn)

    def _load_profiles(self):
        """Load profiles into dropdown"""
        profiles = self.profile_manager.get_all_profiles()

        # Create string list for dropdown
        profile_names = [f"{p.app_name}" for p in profiles]
        if not profile_names:
            profile_names = ["Default"]

        model = Gtk.StringList.new(profile_names)
        self.profile_dropdown.set_model(model)

        # Store profile mapping
        self._profile_list = profiles if profiles else [self.profile_manager.get_profile_for_app('default')]

        # Select first profile
        if self._profile_list:
            self._load_profile(self._profile_list[0])

    def _load_profile(self, profile: AppProfile):
        """Load a profile into the editor"""
        self.current_profile = profile
        self.radial_menu.set_profile(profile)
        self.current_app_label.set_label(f"Editing: {profile.app_name}")

        # Deselect segment
        self.current_segment = None
        self.radial_menu.selected_segment = None
        self.radial_menu.queue_draw()
        self.no_selection_box.set_visible(True)
        self.editor_box.set_visible(False)

    def _on_profile_changed(self, dropdown, pspec):
        """Handle profile selection change"""
        if not self._profile_list:
            return
        idx = dropdown.get_selected()
        if idx < len(self._profile_list):
            self._load_profile(self._profile_list[idx])

    def _on_add_profile(self, button):
        """Show dialog to add new profile"""
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            heading="Add Application Profile",
            body="Select an application to create a custom profile for:",
        )

        # Add app list
        apps = self.profile_manager.get_all_apps()

        # Create scrolled list
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(300)
        scroll.set_min_content_width(400)

        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        listbox.add_css_class("boxed-list")
        scroll.set_child(listbox)

        for app in apps[:50]:  # Limit to 50 apps for performance
            row = Adw.ActionRow(title=app.name, subtitle=app.app_id)
            row.set_activatable(True)
            row.app_id = app.app_id
            listbox.append(row)

        dialog.set_extra_child(scroll)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("create", "Create Profile")
        dialog.set_response_appearance("create", Adw.ResponseAppearance.SUGGESTED)

        def on_response(dialog, response):
            if response == "create":
                row = listbox.get_selected_row()
                if row:
                    app_id = row.app_id
                    profile = self.profile_manager.create_profile_for_app(app_id)
                    self._load_profiles()
                    # Select the new profile
                    for i, p in enumerate(self._profile_list):
                        if p.app_id == app_id:
                            self.profile_dropdown.set_selected(i)
                            break

        dialog.connect("response", on_response)
        dialog.present()

    def _on_delete_profile(self, button):
        """Delete current profile"""
        if not self.current_profile or self.current_profile.app_id == 'default':
            return

        dialog = Adw.MessageDialog(
            transient_for=self.window,
            heading="Delete Profile?",
            body=f"Delete the profile for {self.current_profile.app_name}? This cannot be undone.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_response(dialog, response):
            if response == "delete":
                self.profile_manager.delete_profile(self.current_profile.app_id)
                self._load_profiles()

        dialog.connect("response", on_response)
        dialog.present()

    def _on_segment_selected(self, index, segment):
        """Handle segment click"""
        self.current_segment = index

        self.no_selection_box.set_visible(False)
        self.editor_box.set_visible(True)

        self.segment_title.set_label(f"Segment {index + 1}")
        self.label_entry.set_text(segment.get("label", ""))
        self.data_entry.set_text(segment.get("action_data", ""))

        # Set type dropdown
        action_type = segment.get("action_type", "keystroke")
        type_map = {"keystroke": 0, "command": 1, "application": 2, "disabled": 3}
        self.type_dropdown.set_selected(type_map.get(action_type, 0))

    def _on_type_changed(self, dropdown, pspec):
        """Handle action type change"""
        idx = dropdown.get_selected()
        labels = ["Keystroke", "Command", "Application", ""]
        placeholders = ["e.g., ctrl+c", "e.g., grimshot copy area", "e.g., firefox", ""]

        self.data_label.set_label(labels[idx])
        self.data_entry.set_placeholder_text(placeholders[idx])
        self._save_current_segment()

    def _on_entry_changed(self, entry):
        """Handle entry changes"""
        self._save_current_segment()

    def _save_current_segment(self):
        """Save current segment to profile"""
        if self.current_segment is None or not self.current_profile:
            return

        type_map = {0: "keystroke", 1: "command", 2: "application", 3: "disabled"}
        action_type = type_map.get(self.type_dropdown.get_selected(), "keystroke")

        # Update profile
        while len(self.current_profile.slices) <= self.current_segment:
            self.current_profile.slices.append(ActionSlice("", "", "disabled", ""))

        self.current_profile.slices[self.current_segment] = ActionSlice(
            label=self.label_entry.get_text(),
            icon="",  # TODO: icon selector
            action_type=action_type,
            action_data=self.data_entry.get_text(),
        )

        # Update preview
        self.radial_menu.set_profile(self.current_profile)
        self.radial_menu.selected_segment = self.current_segment

        # Save to disk
        self.profile_manager.save_profiles()

    def _quick_set(self, label, shortcut):
        """Quick-set a segment with common action"""
        self.label_entry.set_text(label)
        self.data_entry.set_text(shortcut)
        self.type_dropdown.set_selected(0)  # Keystroke

    def _apply_template(self, template_name):
        """Apply a template to current profile"""
        if not self.current_profile:
            return

        template = CATEGORY_TEMPLATES.get(template_name, CATEGORY_TEMPLATES['default'])
        self.current_profile.slices = [
            ActionSlice(s.label, s.icon, s.action_type, s.action_data)
            for s in template
        ]

        self.profile_manager.save_profiles()
        self.radial_menu.set_profile(self.current_profile)

        # Deselect
        self.current_segment = None
        self.radial_menu.selected_segment = None
        self.no_selection_box.set_visible(True)
        self.editor_box.set_visible(False)

    def update_device(self, device):
        """Update page with device"""
        self.device = device
