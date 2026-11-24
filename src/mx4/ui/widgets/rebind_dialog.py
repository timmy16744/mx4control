"""Full button-rebind dialog with interactive shortcut recording.

Supports:
* Default (restores original firmware behaviour via ResetButton)
* Keystroke (manual entry, quick chips, OR live Record Shortcut capture)
* Command (shlex-parsed shell command)
* Application (direct exec / gtk-launch)
* DPI Cycle (step through configured DPI presets)
* SmartShift Toggle (toggle between Free-Spin & SmartShift/Ratchet)
* Switch Host (cycle to next paired Easy-Switch host)
* Remap to button (zero-latency firmware CID remap)
* Disabled (divert & swallow press)
"""

from __future__ import annotations

from typing import Callable, Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk

from ...hidpp import ControlID


_REMAP_TARGETS: list[tuple[str, int]] = [
    ("Left click",        ControlID.LEFT_CLICK),
    ("Right click",       ControlID.RIGHT_CLICK),
    ("Middle click",      ControlID.MIDDLE_CLICK),
    ("Back",              ControlID.BACK),
    ("Forward",           ControlID.FORWARD),
    ("SmartShift toggle", ControlID.SMART_SHIFT),
    ("Gesture button",    ControlID.GESTURE_BUTTON),
]

_QUICK_KEYSTROKES: list[tuple[str, str]] = [
    ("Copy",       "ctrl+c"),
    ("Paste",      "ctrl+v"),
    ("Cut",        "ctrl+x"),
    ("Undo",       "ctrl+z"),
    ("Redo",       "ctrl+shift+z"),
    ("Save",       "ctrl+s"),
    ("Find",       "ctrl+f"),
    ("New tab",    "ctrl+t"),
    ("Close tab",  "ctrl+w"),
    ("Alt-Tab",    "alt+Tab"),
    ("Play/Pause", "XF86AudioPlay"),
    ("Vol +",      "XF86AudioRaiseVolume"),
    ("Vol -",      "XF86AudioLowerVolume"),
    ("Overview",   "super"),
]

_MODIFIER_KEYVALS = {
    Gdk.KEY_Control_L, Gdk.KEY_Control_R,
    Gdk.KEY_Shift_L, Gdk.KEY_Shift_R,
    Gdk.KEY_Alt_L, Gdk.KEY_Alt_R,
    Gdk.KEY_Super_L, Gdk.KEY_Super_R,
    Gdk.KEY_Meta_L, Gdk.KEY_Meta_R,
    Gdk.KEY_ISO_Level3_Shift,
}


def format_gdk_shortcut(keyval: int, state: Gdk.ModifierType) -> Optional[str]:
    """Convert a GDK key press into a wtype-compatible shortcut string."""
    if keyval in _MODIFIER_KEYVALS:
        return None
    name = Gdk.keyval_name(keyval)
    if not name:
        return None
    parts: list[str] = []
    if state & Gdk.ModifierType.CONTROL_MASK:
        parts.append("ctrl")
    if state & Gdk.ModifierType.ALT_MASK:
        parts.append("alt")
    if state & Gdk.ModifierType.SHIFT_MASK:
        parts.append("shift")
    if state & Gdk.ModifierType.SUPER_MASK:
        parts.append("super")
    # Single ASCII letters: lowercase when combined with modifiers unless plain
    if len(name) == 1 and name.isalpha():
        name = name.lower()
    parts.append(name)
    return "+".join(parts)


class RebindDialog(Adw.AlertDialog):
    """Modal dialog that calls ``on_apply(action_type, action_data)``."""

    def __init__(
        self,
        *,
        button_label: str,
        cid: int,
        current_action_type: str,
        current_action_data: str,
        remappable: bool,
        divertable: bool,
        on_apply: Callable[[str, str], None],
        scope_label: str = "Global",
    ):
        super().__init__()
        self.set_heading(f"Configure {button_label}")
        if remappable or divertable:
            self.set_body(
                f"Scope: {scope_label} · CID 0x{cid:04X}. "
                "Changes apply immediately and persist across restarts."
            )
        else:
            self.set_body(
                f"CID 0x{cid:04X} is firmware-locked (primary click) and cannot be rebound."
            )

        self._on_apply = on_apply
        self._cid = cid
        self._recording = False

        self.add_response("cancel", "Cancel")
        if remappable or divertable:
            self.add_response("apply", "Apply")
            self.set_response_appearance("apply", Adw.ResponseAppearance.SUGGESTED)

        if not (remappable or divertable):
            self.connect("response", lambda *_: None)
            return

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        body.set_size_request(440, -1)
        self.set_extra_child(body)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_max_content_height(280)
        scroll.set_propagate_natural_height(True)
        body.append(scroll)

        self._type_group = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self._type_group.add_css_class("boxed-list")
        scroll.set_child(self._type_group)

        self._radios: dict[str, Gtk.CheckButton] = {}
        self._add_type_row("default", "Default", "Restore original firmware behaviour")
        if divertable:
            self._add_type_row("keystroke", "Keystroke", "Synthesise a keyboard shortcut")
            self._add_type_row("command", "Command", "Run a shell command")
            self._add_type_row("application", "Application", "Launch an application")
            self._add_type_row("dpi_cycle", "Cycle DPI", "Step through your DPI presets")
            self._add_type_row(
                "smartshift_toggle", "Toggle Scroll Mode",
                "Switch between Free-Spin and SmartShift",
            )
            self._add_type_row(
                "host_next", "Next Easy-Switch Host",
                "Switch to the next paired computer",
            )
        if remappable:
            self._add_type_row(
                "remap", "Hardware Remap",
                "Zero-latency firmware remap to another button",
            )
        if divertable:
            self._add_type_row("disabled", "Disabled", "Swallow press — emit nothing")

        # Contextual fields
        fields = Gtk.Stack()
        fields.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        fields.set_transition_duration(120)
        body.append(fields)
        self._fields_stack = fields

        fields.add_named(Gtk.Box(), "empty")

        # Keystroke + live recorder
        ks_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        ks_hint = Gtk.Label(
            label="Type a shortcut or click Record and press your keys",
            xalign=0,
        )
        ks_hint.add_css_class("dim-label")
        ks_box.append(ks_hint)

        ks_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        ks_box.append(ks_row)

        self._keystroke_entry = Gtk.Entry(hexpand=True)
        self._keystroke_entry.set_placeholder_text("ctrl+shift+t")
        ks_row.append(self._keystroke_entry)

        self._record_btn = Gtk.ToggleButton(label="Record")
        self._record_btn.add_css_class("pill")
        self._record_btn.connect("toggled", self._on_record_toggled)
        ks_row.append(self._record_btn)

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_recorded)
        self._record_btn.add_controller(key_ctrl)

        chips = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            column_spacing=4, row_spacing=4,
            max_children_per_line=5,
        )
        for label, data in _QUICK_KEYSTROKES:
            b = Gtk.Button(label=label)
            b.add_css_class("pill")
            b.connect("clicked", lambda _b, d=data: self._keystroke_entry.set_text(d))
            chips.append(b)
        ks_box.append(chips)
        fields.add_named(ks_box, "keystroke")

        # Command
        cmd_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        cmd_hint = Gtk.Label(label="Command (parsed with shlex)", xalign=0)
        cmd_hint.add_css_class("dim-label")
        cmd_box.append(cmd_hint)
        self._command_entry = Gtk.Entry()
        self._command_entry.set_placeholder_text("hyprshot -m region")
        cmd_box.append(self._command_entry)
        fields.add_named(cmd_box, "command")

        # Application
        app_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        app_hint = Gtk.Label(label="Executable or .desktop basename", xalign=0)
        app_hint.add_css_class("dim-label")
        app_box.append(app_hint)
        self._app_entry = Gtk.Entry()
        self._app_entry.set_placeholder_text("kitty")
        app_box.append(self._app_entry)
        fields.add_named(app_box, "application")

        # Remap
        remap_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        remap_hint = Gtk.Label(
            label="Target physical button (applied directly in mouse firmware)",
            xalign=0,
        )
        remap_hint.add_css_class("dim-label")
        remap_box.append(remap_hint)
        labels = [name for name, t_cid in _REMAP_TARGETS if t_cid != cid]
        self._remap_targets = [t_cid for _n, t_cid in _REMAP_TARGETS if t_cid != cid]
        self._remap_dropdown = Gtk.DropDown.new_from_strings(labels)
        remap_box.append(self._remap_dropdown)
        fields.add_named(remap_box, "remap")

        self._seed_current(current_action_type, current_action_data)
        self.connect("response", self._on_response)

    def _on_record_toggled(self, btn: Gtk.ToggleButton) -> None:
        self._recording = btn.get_active()
        btn.set_label("Press keys…" if self._recording else "Record")
        if self._recording:
            btn.grab_focus()

    def _on_key_recorded(self, _ctrl, keyval: int, _keycode: int, state: Gdk.ModifierType) -> bool:
        if not self._recording:
            return False
        if keyval == Gdk.KEY_Escape:
            self._record_btn.set_active(False)
            return True
        spec = format_gdk_shortcut(keyval, state)
        if spec:
            self._keystroke_entry.set_text(spec)
            self._record_btn.set_active(False)
            return True
        return False

    def _add_type_row(self, kind: str, name: str, sub: str) -> None:
        row = Adw.ActionRow(title=name, subtitle=sub)
        check = Gtk.CheckButton()
        if self._radios:
            check.set_group(next(iter(self._radios.values())))
        check.connect("toggled", self._on_type_toggled, kind)
        self._radios[kind] = check
        row.add_prefix(check)
        row.set_activatable_widget(check)
        self._type_group.append(row)

    def _on_type_toggled(self, btn, kind: str):
        if not btn.get_active():
            return
        stack_name = {
            "keystroke": "keystroke",
            "command": "command",
            "application": "application",
            "remap": "remap",
        }.get(kind, "empty")
        self._fields_stack.set_visible_child_name(stack_name)

    def _seed_current(self, at: str, data: str) -> None:
        if at in self._radios:
            self._radios[at].set_active(True)
        else:
            self._radios["default"].set_active(True)

        if at == "keystroke":
            self._keystroke_entry.set_text(data)
        elif at == "command":
            self._command_entry.set_text(data)
        elif at == "application":
            self._app_entry.set_text(data)
        elif at == "remap":
            try:
                target = int(data)
            except ValueError:
                target = 0
            for i, tid in enumerate(self._remap_targets):
                if tid == target:
                    self._remap_dropdown.set_selected(i)
                    break

    def _on_response(self, _d, response: str):
        if response != "apply":
            return
        kind: Optional[str] = next((k for k, r in self._radios.items() if r.get_active()), None)
        if kind is None:
            return

        if kind == "keystroke":
            data = self._keystroke_entry.get_text().strip()
            if data:
                self._on_apply("keystroke", data)
        elif kind == "command":
            data = self._command_entry.get_text().strip()
            if data:
                self._on_apply("command", data)
        elif kind == "application":
            data = self._app_entry.get_text().strip()
            if data:
                self._on_apply("application", data)
        elif kind == "remap":
            idx = self._remap_dropdown.get_selected()
            if 0 <= idx < len(self._remap_targets):
                self._on_apply("remap", str(self._remap_targets[idx]))
        elif kind in ("dpi_cycle", "smartshift_toggle", "host_next", "disabled", "default"):
            self._on_apply(kind, "")
