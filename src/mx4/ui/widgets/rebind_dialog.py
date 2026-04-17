"""Full button-rebind dialog.

Offered when the user clicks a button on the mouse preview. Supports:

* Default (firmware's original behaviour)
* Remap → another physical button (CID-level)
* Keystroke → synthesised via wtype/xdotool on press
* Command → ``subprocess.Popen`` of an arbitrary shell command
* Application → launch via ``gtk-launch``
* Disabled → swallow the press entirely

Picks the correct action_type + action_data on apply and returns them
to the caller's handler.
"""

from __future__ import annotations

from typing import Callable, Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

from ...hidpp import ControlID


# (label, CID) — targets offered for the "Remap to button" path
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
    ("Copy",      "ctrl+c"),
    ("Paste",     "ctrl+v"),
    ("Cut",       "ctrl+x"),
    ("Undo",      "ctrl+z"),
    ("Redo",      "ctrl+shift+z"),
    ("Save",      "ctrl+s"),
    ("Find",      "ctrl+f"),
    ("New tab",   "ctrl+t"),
    ("Close tab", "ctrl+w"),
    ("Alt-Tab",   "alt+Tab"),
    ("Play/Pause","XF86AudioPlay"),
    ("Vol +",     "XF86AudioRaiseVolume"),
    ("Vol -",     "XF86AudioLowerVolume"),
    ("Overview",  "super"),
]


class RebindDialog(Adw.AlertDialog):
    """Open-and-forget dialog. Calls ``on_apply(action_type, action_data)``
    when the user clicks Apply with a valid selection.
    """

    def __init__(self, *, button_label: str, cid: int,
                 current_action_type: str, current_action_data: str,
                 remappable: bool, divertable: bool,
                 on_apply: Callable[[str, str], None]):
        super().__init__()
        self.set_heading(f"Rebind {button_label.lower()} button")
        self.set_body(
            "Choose a new behaviour. Changes persist to config and "
            "are reapplied on daemon restart."
            if remappable or divertable
            else "This button is firmware-locked and can't be rebound."
        )

        self._on_apply = on_apply
        self._cid = cid

        self.add_response("cancel", "Cancel")
        if remappable or divertable:
            self.add_response("apply", "Apply")
            self.set_response_appearance("apply", Adw.ResponseAppearance.SUGGESTED)

        if not (remappable or divertable):
            self.connect("response", lambda *_: None)
            return

        # ─── Body: action-type picker + contextual fields ───────────
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        body.set_size_request(420, -1)
        self.set_extra_child(body)

        # Action-type radio list
        self._type_group = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self._type_group.add_css_class("boxed-list")
        body.append(self._type_group)

        self._radios: dict[str, Gtk.CheckButton] = {}
        self._add_type_row("default",     "Default",
                            "Original firmware behaviour")
        if divertable:
            self._add_type_row("keystroke",   "Keystroke",
                                "Synthesise a keyboard shortcut on press")
            self._add_type_row("command",     "Command",
                                "Run a shell command on press")
            self._add_type_row("application", "Application",
                                "Launch an app on press")
        if remappable:
            self._add_type_row("remap",       "Remap to button",
                                "Make this button act as another physical button")
        if divertable:
            self._add_type_row("disabled",    "Disabled",
                                "Swallow the press — button emits nothing")

        # Contextual fields
        fields = Gtk.Stack()
        fields.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        fields.set_transition_duration(140)
        body.append(fields)
        self._fields_stack = fields

        # empty — for "default" / "disabled"
        fields.add_named(Gtk.Box(), "empty")

        # keystroke
        ks_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        ks_hint = Gtk.Label(
            label="Shortcut (e.g. ctrl+shift+n, alt+Tab, XF86AudioPlay)",
            xalign=0,
        )
        ks_hint.add_css_class("dim-label")
        ks_box.append(ks_hint)
        self._keystroke_entry = Gtk.Entry()
        self._keystroke_entry.set_placeholder_text("ctrl+c")
        ks_box.append(self._keystroke_entry)

        chips = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            column_spacing=4, row_spacing=4,
            max_children_per_line=4,
        )
        for label, data in _QUICK_KEYSTROKES:
            b = Gtk.Button(label=label)
            b.add_css_class("pill")
            b.connect("clicked",
                       lambda _b, d=data: self._keystroke_entry.set_text(d))
            chips.append(b)
        ks_box.append(chips)
        fields.add_named(ks_box, "keystroke")

        # command
        cmd_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        cmd_hint = Gtk.Label(
            label="Shell command (parsed with shlex, not a full shell)", xalign=0,
        )
        cmd_hint.add_css_class("dim-label")
        cmd_box.append(cmd_hint)
        self._command_entry = Gtk.Entry()
        self._command_entry.set_placeholder_text("hyprshot -m region")
        cmd_box.append(self._command_entry)
        fields.add_named(cmd_box, "command")

        # application
        app_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        app_hint = Gtk.Label(
            label="Launch by executable name or .desktop-file basename", xalign=0,
        )
        app_hint.add_css_class("dim-label")
        app_box.append(app_hint)
        self._app_entry = Gtk.Entry()
        self._app_entry.set_placeholder_text("kitty")
        app_box.append(self._app_entry)
        fields.add_named(app_box, "application")

        # remap-to-button
        remap_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        remap_hint = Gtk.Label(
            label="Target button (firmware-level remap — zero latency)",
            xalign=0,
        )
        remap_hint.add_css_class("dim-label")
        remap_box.append(remap_hint)

        labels = [name for name, t_cid in _REMAP_TARGETS if t_cid != cid]
        self._remap_targets = [t_cid for _n, t_cid in _REMAP_TARGETS if t_cid != cid]
        self._remap_dropdown = Gtk.DropDown.new_from_strings(labels)
        remap_box.append(self._remap_dropdown)
        fields.add_named(remap_box, "remap")

        # Seed from current state
        self._seed_current(current_action_type, current_action_data)
        self.connect("response", self._on_response)

    # ─── helpers ────────────────────────────────────────────────────

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
            "default": "empty",
            "disabled": "empty",
            "remap": "remap",
            "keystroke": "keystroke",
            "command": "command",
            "application": "application",
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

        # Find the active radio
        kind: Optional[str] = None
        for k, r in self._radios.items():
            if r.get_active():
                kind = k
                break
        if kind is None:
            return

        if kind == "keystroke":
            data = self._keystroke_entry.get_text().strip()
            if not data:
                return
            self._on_apply("keystroke", data)
        elif kind == "command":
            data = self._command_entry.get_text().strip()
            if not data:
                return
            self._on_apply("command", data)
        elif kind == "application":
            data = self._app_entry.get_text().strip()
            if not data:
                return
            self._on_apply("application", data)
        elif kind == "remap":
            idx = self._remap_dropdown.get_selected()
            if 0 <= idx < len(self._remap_targets):
                self._on_apply("remap", str(self._remap_targets[idx]))
        elif kind == "disabled":
            self._on_apply("disabled", "")
        elif kind == "default":
            self._on_apply("default", "")
