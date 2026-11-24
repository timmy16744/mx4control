"""Actions Ring configuration — per-app profiles, radial designer, trigger & deadzone."""

from __future__ import annotations

import math
import threading
from typing import Optional

import cairo  # type: ignore[import-untyped]
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from ..widgets.common import page_title, section_title
from ...agent.profiles import CATEGORY_TEMPLATES
from ...config import ActionSlice, ConfigStore, RingProfile
from ...hidpp import ControlID


QUICK_ACTIONS = [
    ("Copy",         "keystroke",         "ctrl+c"),
    ("Paste",        "keystroke",         "ctrl+v"),
    ("Cut",          "keystroke",         "ctrl+x"),
    ("Undo",         "keystroke",         "ctrl+z"),
    ("Redo",         "keystroke",         "ctrl+shift+z"),
    ("Save",         "keystroke",         "ctrl+s"),
    ("Find",         "keystroke",         "ctrl+f"),
    ("Close Tab",    "keystroke",         "ctrl+w"),
    ("New Tab",      "keystroke",         "ctrl+t"),
    ("Screenshot",   "command",           "hyprshot -m region"),
    ("Cycle DPI",    "dpi_cycle",         ""),
    ("Scroll Mode",  "smartshift_toggle", ""),
    ("Next Host",    "host_next",         ""),
]

_ACTION_TYPES = [
    ("keystroke",         "Keystroke"),
    ("command",           "Command"),
    ("application",       "Application"),
    ("dpi_cycle",         "Cycle DPI"),
    ("smartshift_toggle", "Toggle Scroll Mode"),
    ("host_next",         "Next Easy-Switch Host"),
    ("haptic",            "Play Haptic"),
    ("disabled",          "Disabled"),
]

_TRIGGER_CHOICES: list[tuple[int, str]] = [
    (ControlID.VIRTUAL_GESTURE, "Thumb Pad (0x00D7)"),
    (ControlID.GESTURE_BUTTON,  "Gesture Button (0x00C3)"),
    (ControlID.SMART_SHIFT,     "Mode Shift (0x00C4)"),
    (ControlID.MIDDLE_CLICK,    "Wheel Click (0x0052)"),
    (ControlID.BACK,            "Back Button (0x0053)"),
]


class RingPreview(Gtk.DrawingArea):
    def __init__(self, on_pick):
        super().__init__()
        self._profile: Optional[RingProfile] = None
        self._selected: Optional[int] = None
        self._hover: Optional[int] = None
        self._on_pick = on_pick

        self.set_size_request(320, 320)
        self.set_draw_func(self._draw)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion)
        motion.connect("leave", self._on_leave)
        self.add_controller(motion)

        click = Gtk.GestureClick()
        click.connect("pressed", self._on_click)
        self.add_controller(click)

    def set_profile(self, profile: Optional[RingProfile]):
        self._profile = profile
        self.queue_draw()

    def set_selected(self, idx: Optional[int]):
        self._selected = idx
        self.queue_draw()

    def _draw(self, _area, cr, w, h):
        cx, cy = w / 2, h / 2
        outer = min(w, h) / 2 - 16
        inner = outer * 0.36
        segs = self._profile.slices if self._profile else []

        cr.set_source_rgba(0, 0, 0, 0.35)
        cr.arc(cx, cy, outer + 10, 0, 2 * math.pi)
        cr.fill()

        for i in range(8):
            start = -math.pi / 2 + (i - 0.5) * math.pi / 4
            end = start + math.pi / 4
            seg = segs[i] if i < len(segs) else None
            disabled = not seg or not seg.label or seg.action_type == "disabled"

            if i == self._selected:
                cr.set_source_rgba(0.83, 0.65, 0.46, 0.28)
            elif i == self._hover:
                cr.set_source_rgba(0.22, 0.22, 0.26, 0.95)
            else:
                cr.set_source_rgba(0.15, 0.15, 0.18, 0.92)
            cr.new_path()
            cr.arc(cx, cy, outer, start, end)
            cr.arc_negative(cx, cy, inner, end, start)
            cr.close_path()
            cr.fill()

            if i == self._selected:
                cr.set_source_rgba(0.83, 0.65, 0.46, 1.0)
                cr.set_line_width(2.2)
            else:
                cr.set_source_rgba(1, 1, 1, 0.06)
                cr.set_line_width(1)
            cr.new_path()
            cr.arc(cx, cy, outer, start, end)
            cr.arc_negative(cx, cy, inner, end, start)
            cr.close_path()
            cr.stroke()

            if seg and seg.label:
                mid = (start + end) / 2
                rad = (inner + outer) / 2
                lx = cx + math.cos(mid) * rad
                ly = cy + math.sin(mid) * rad
                if i == self._selected:
                    cr.set_source_rgb(0.92, 0.78, 0.60)
                elif disabled:
                    cr.set_source_rgb(0.42, 0.45, 0.50)
                else:
                    cr.set_source_rgb(0.92, 0.92, 0.92)
                cr.select_font_face("Inter", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
                cr.set_font_size(11.0)
                text = seg.label[:12]
                ext = cr.text_extents(text)
                cr.move_to(lx - ext.width / 2, ly + 4)
                cr.show_text(text)

        cr.set_source_rgba(0.08, 0.08, 0.10, 1)
        cr.arc(cx, cy, inner - 6, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgba(0.83, 0.65, 0.46, 0.85)
        cr.arc(cx, cy, 7, 0, 2 * math.pi)
        cr.fill()

    def _segment_at(self, x, y):
        w, h = self.get_width(), self.get_height()
        cx, cy = w / 2, h / 2
        outer = min(w, h) / 2 - 16
        inner = outer * 0.36
        dx, dy = x - cx, y - cy
        d = math.hypot(dx, dy)
        if d < inner or d > outer:
            return None
        a = math.atan2(dy, dx) + math.pi / 2
        if a < 0:
            a += 2 * math.pi
        return int((a + math.pi / 8) / (math.pi / 4)) % 8

    def _on_motion(self, _ctrl, x, y):
        s = self._segment_at(x, y)
        if s != self._hover:
            self._hover = s
            self.queue_draw()

    def _on_leave(self, _ctrl):
        self._hover = None
        self.queue_draw()

    def _on_click(self, _g, _n, x, y):
        s = self._segment_at(x, y)
        if s is not None and self._on_pick:
            self._on_pick(s)


class RingPage(Gtk.Box):
    def __init__(self, client, *, window=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.client = client
        self.window = window
        self.store = ConfigStore()
        self._profile_ids: list[str] = []
        self._current_profile_id: str = "default"
        self.current_segment: Optional[int] = None
        self._updating = False
        self._reload_src: Optional[int] = None

        self.set_margin_top(4)
        self.set_margin_bottom(24)

        self.append(page_title(
            "Actions Ring",
            "Per-application 8-slice radial menus triggered by holding the thumb pad and flicking.",
        ))

        # ─── Ring engine settings ───────────────────────────────────
        cfg_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        cfg_card.add_css_class("mx4-card")
        self.append(cfg_card)

        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        cfg_card.append(top_row)

        en_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        top_row.append(en_col)
        en_t = Gtk.Label(label="Enable Actions Ring", xalign=0)
        en_t.add_css_class("mx4-card-title")
        en_col.append(en_t)
        en_s = Gtk.Label(label="Freeze cursor & show radial overlay when trigger is held", xalign=0)
        en_s.add_css_class("mx4-card-sub")
        en_col.append(en_s)

        self.ring_enable_switch = Gtk.Switch()
        self.ring_enable_switch.set_valign(Gtk.Align.CENTER)
        self.ring_enable_switch.connect("notify::active", self._on_ring_enable_toggle)
        top_row.append(self.ring_enable_switch)

        trig_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        cfg_card.append(trig_row)
        trig_lbl = Gtk.Label(label="Trigger button", xalign=0, hexpand=True)
        trig_lbl.add_css_class("mx4-row-title")
        trig_row.append(trig_lbl)
        self.trigger_dd = Gtk.DropDown.new_from_strings([lbl for _cid, lbl in _TRIGGER_CHOICES])
        self.trigger_dd.connect("notify::selected", self._on_trigger_changed)
        trig_row.append(self.trigger_dd)

        dz_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        cfg_card.append(dz_row)
        dz_lbl = Gtk.Label(label="Cancel deadzone radius", xalign=0, hexpand=True)
        dz_lbl.add_css_class("mx4-row-title")
        dz_row.append(dz_lbl)
        self.dz_val = Gtk.Label(label="40 px", xalign=1)
        self.dz_val.add_css_class("mx4-card-value-small")
        dz_row.append(self.dz_val)

        self.dz_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 20, 80, 5)
        self.dz_scale.add_css_class("mx4-slider")
        self.dz_scale.set_draw_value(False)
        self.dz_scale.connect("value-changed", self._on_deadzone_changed)
        cfg_card.append(self.dz_scale)

        # ─── Per-app profile bar ────────────────────────────────────
        self.append(section_title("Application profile"))
        prof_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        prof_bar.add_css_class("mx4-card")
        prof_bar.add_css_class("compact")
        self.append(prof_bar)

        self.profile_dd = Gtk.DropDown()
        self.profile_dd.set_hexpand(True)
        self.profile_dd.connect("notify::selected", self._on_profile_selected)
        prof_bar.append(self.profile_dd)

        add_btn = Gtk.Button(label="+ Add app")
        add_btn.add_css_class("mx4-btn-primary")
        add_btn.connect("clicked", self._on_add_profile)
        prof_bar.append(add_btn)

        self.del_prof_btn = Gtk.Button(label="Delete")
        self.del_prof_btn.add_css_class("mx4-btn-ghost")
        self.del_prof_btn.connect("clicked", self._on_delete_profile)
        prof_bar.append(self.del_prof_btn)

        # ─── Preview + segment editor side-by-side ──────────────────
        columns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        self.append(columns)

        preview_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        preview_card.add_css_class("mx4-card")
        preview_card.set_valign(Gtk.Align.START)
        columns.append(preview_card)

        self.preview = RingPreview(on_pick=self._on_segment_picked)
        preview_card.append(self.preview)

        hint = Gtk.Label(label="Click any slice to edit")
        hint.add_css_class("mx4-card-sub")
        hint.set_halign(Gtk.Align.CENTER)
        preview_card.append(hint)

        edit_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, hexpand=True)
        columns.append(edit_col)

        edit_col.append(section_title("Selected slice"))
        editor = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        editor.add_css_class("mx4-card")
        edit_col.append(editor)

        seg_head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        editor.append(seg_head)
        self.seg_title = Gtk.Label(label="Slice 1", xalign=0, hexpand=True)
        self.seg_title.add_css_class("mx4-card-title")
        seg_head.append(self.seg_title)

        test_btn = Gtk.Button(label="Test action")
        test_btn.add_css_class("mx4-btn-ghost")
        test_btn.connect("clicked", self._on_test_slice)
        seg_head.append(test_btn)

        lbl_head = Gtk.Label(label="LABEL", xalign=0)
        lbl_head.add_css_class("mx4-card-unit")
        editor.append(lbl_head)
        self.label_entry = Gtk.Entry()
        self.label_entry.set_placeholder_text("e.g. Copy")
        self.label_entry.add_css_class("mx4-entry")
        self.label_entry.connect("changed", self._on_edit_changed)
        editor.append(self.label_entry)

        act_head = Gtk.Label(label="ACTION TYPE", xalign=0)
        act_head.add_css_class("mx4-card-unit")
        editor.append(act_head)
        self.type_dropdown = Gtk.DropDown.new_from_strings([lbl for _k, lbl in _ACTION_TYPES])
        self.type_dropdown.connect("notify::selected", self._on_edit_changed)
        editor.append(self.type_dropdown)

        data_head = Gtk.Label(label="PAYLOAD (shortcut, command, app, or waveform ID)", xalign=0)
        data_head.add_css_class("mx4-card-unit")
        editor.append(data_head)
        self.data_entry = Gtk.Entry()
        self.data_entry.set_placeholder_text("e.g. ctrl+c")
        self.data_entry.add_css_class("mx4-entry")
        self.data_entry.connect("changed", self._on_edit_changed)
        editor.append(self.data_entry)

        # ─── Quick-action chips ─────────────────────────────────────
        self.append(section_title("Quick presets"))
        chips_box = Gtk.FlowBox()
        chips_box.set_selection_mode(Gtk.SelectionMode.NONE)
        chips_box.set_column_spacing(6)
        chips_box.set_row_spacing(6)
        self.append(chips_box)
        for label, atype, data in QUICK_ACTIONS:
            btn = Gtk.Button(label=label)
            btn.add_css_class("mx4-chip")
            btn.connect(
                "clicked",
                lambda _b, lab=label, t=atype, d=data: self._quick_set(lab, t, d),
            )
            chips_box.append(btn)

        self.refresh()

    # ─── profile & segment logic ────────────────────────────────────

    @property
    def profile(self) -> RingProfile:
        profs = self.store.config.ring_profiles
        if self._current_profile_id not in profs:
            self._current_profile_id = "default"
        p = profs[self._current_profile_id]
        while len(p.slices) < 8:
            p.slices.append(ActionSlice("", "", "disabled", ""))
        return p

    def refresh(self) -> None:
        self.store.invalidate()
        cfg = self.store.config
        self._updating = True
        try:
            self.ring_enable_switch.set_active(cfg.daemon.autostart_gesture)
            trig_cids = [int(c) for c, _ in _TRIGGER_CHOICES]
            t_idx = trig_cids.index(cfg.daemon.trigger_cid) if cfg.daemon.trigger_cid in trig_cids else 0
            self.trigger_dd.set_selected(t_idx)
            self.dz_scale.set_value(cfg.daemon.cancel_radius)
            self.dz_val.set_text(f"{cfg.daemon.cancel_radius} px")

            self._rebuild_profile_dropdown()
        finally:
            self._updating = False
        self.preview.set_profile(self.profile)
        self._load_segment(self.current_segment or 0)

    def _rebuild_profile_dropdown(self) -> None:
        profs = self.store.config.ring_profiles
        ids = ["default"] + sorted(k for k in profs if k != "default")
        self._profile_ids = ids
        labels = [
            f"{profs[k].app_name} ({k})" if k != "default" else "Default (All Applications)"
            for k in ids
        ]
        self.profile_dd.set_model(Gtk.StringList.new(labels))
        idx = ids.index(self._current_profile_id) if self._current_profile_id in ids else 0
        self.profile_dd.set_selected(idx)
        self.del_prof_btn.set_sensitive(self._current_profile_id != "default")

    def _on_profile_selected(self, dd, _):
        if self._updating:
            return
        idx = dd.get_selected()
        if 0 <= idx < len(self._profile_ids):
            self._current_profile_id = self._profile_ids[idx]
            self.del_prof_btn.set_sensitive(self._current_profile_id != "default")
            self.preview.set_profile(self.profile)
            self._load_segment(0)

    def _on_add_profile(self, _btn):
        dlg = Adw.AlertDialog(
            heading="Add application profile",
            body="Enter the window class (e.g. zen, code, kitty, blender) and choose a starting template.",
        )
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        entry = Gtk.Entry(placeholder_text="Window class (e.g. zen, code, kitty)")
        box.append(entry)
        tpl_keys = ["default", "browser", "editor", "terminal", "media"]
        tpl_dd = Gtk.DropDown.new_from_strings(
            ["Copy Default Ring", "Browser Template", "Code Editor Template", "Terminal Template", "Media Template"]
        )
        box.append(tpl_dd)
        dlg.set_extra_child(box)
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("add", "Create")
        dlg.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)

        def on_resp(_d, resp):
            if resp != "add":
                return
            app_id = entry.get_text().strip().lower()
            if not app_id or app_id == "default":
                return
            tpl = tpl_keys[tpl_dd.get_selected()]
            if tpl in CATEGORY_TEMPLATES:
                slices = [ActionSlice(**s.__dict__) for s in CATEGORY_TEMPLATES[tpl]]
            else:
                slices = [ActionSlice(**s.__dict__) for s in self.store.config.ring_profiles["default"].slices]
            self.store.config.ring_profiles[app_id] = RingProfile(
                app_id=app_id, app_name=app_id.title(), slices=slices,
            )
            self._current_profile_id = app_id
            self._save_and_reload()
            self._updating = True
            try:
                self._rebuild_profile_dropdown()
            finally:
                self._updating = False
            self.preview.set_profile(self.profile)
            self._load_segment(0)
            self._toast(f"Created profile for '{app_id}'")

        dlg.connect("response", on_resp)
        dlg.present(self.get_root())

    def _on_delete_profile(self, _btn):
        if self._current_profile_id == "default":
            return
        removed = self._current_profile_id
        self.store.config.ring_profiles.pop(removed, None)
        self._current_profile_id = "default"
        self._save_and_reload()
        self._updating = True
        try:
            self._rebuild_profile_dropdown()
        finally:
            self._updating = False
        self.preview.set_profile(self.profile)
        self._load_segment(0)
        self._toast(f"Deleted profile '{removed}'")

    def _load_segment(self, idx: int):
        prof = self.profile
        if idx >= len(prof.slices):
            return
        self.current_segment = idx
        self.preview.set_selected(idx)
        s = prof.slices[idx]
        self.seg_title.set_text(f"Slice {idx + 1}")
        self._updating = True
        try:
            self.label_entry.set_text(s.label)
            self.data_entry.set_text(s.action_data)
            keys = [k for k, _ in _ACTION_TYPES]
            self.type_dropdown.set_selected(keys.index(s.action_type) if s.action_type in keys else 0)
            self._sync_payload_sensitivity(s.action_type)
        finally:
            self._updating = False

    def _sync_payload_sensitivity(self, atype: str) -> None:
        needs_payload = atype in ("keystroke", "command", "application", "haptic")
        self.data_entry.set_sensitive(needs_payload)

    def _on_segment_picked(self, idx: int):
        self._load_segment(idx)

    def _on_edit_changed(self, *_a):
        if self._updating or self.current_segment is None:
            return
        keys = [k for k, _ in _ACTION_TYPES]
        s = self.profile.slices[self.current_segment]
        s.label = self.label_entry.get_text()
        s.action_type = keys[self.type_dropdown.get_selected()]
        s.action_data = self.data_entry.get_text()
        self._sync_payload_sensitivity(s.action_type)
        self.preview.set_profile(self.profile)
        self._save_and_reload()

    def _on_ring_enable_toggle(self, sw, _):
        if self._updating:
            return
        on = sw.get_active()
        self.store.config.daemon.autostart_gesture = on
        self.store.save()
        if self.window is not None and self.window.agent is not None:
            threading.Thread(
                target=self.window.agent.set_gesture_enabled, args=(on,), daemon=True
            ).start()
        self._toast("Actions Ring enabled" if on else "Actions Ring disabled")

    def _on_trigger_changed(self, dd, _):
        if self._updating:
            return
        cid, lbl = _TRIGGER_CHOICES[dd.get_selected()]
        self.store.config.daemon.trigger_cid = int(cid)
        self._save_and_reload()
        self._toast(f"Ring trigger → {lbl}")

    def _on_deadzone_changed(self, scale):
        if self._updating:
            return
        val = int(scale.get_value())
        self.dz_val.set_text(f"{val} px")
        self.store.config.daemon.cancel_radius = val
        self._save_and_reload()

    def _on_test_slice(self, _btn):
        if self.current_segment is None:
            return
        s = self.profile.slices[self.current_segment]
        if self.window is not None and self.window.agent is not None:
            threading.Thread(
                target=self.window.agent.test_action,
                args=(s.action_type, s.action_data),
                daemon=True,
            ).start()
            self._toast(f"Triggered '{s.label or s.action_type}'")

    # ─── persistence + reload mx4-agent ─────────────────────────────

    def _save_and_reload(self) -> None:
        self.store.save()
        if self._reload_src is not None:
            GLib.source_remove(self._reload_src)
        self._reload_src = GLib.timeout_add(350, self._do_reload)

    def _do_reload(self) -> bool:
        self._reload_src = None

        def worker():
            if self.window is not None and self.window.agent is not None:
                try:
                    self.window.agent.reload_profiles()
                except Exception:
                    pass
        threading.Thread(target=worker, daemon=True).start()
        return False

    def _toast(self, message: str) -> None:
        if self.window is not None:
            self.window.toast(message)

    def _quick_set(self, label: str, atype: str, data: str):
        keys = [k for k, _ in _ACTION_TYPES]
        self._updating = True
        try:
            self.label_entry.set_text(label)
            self.type_dropdown.set_selected(keys.index(atype) if atype in keys else 0)
            self.data_entry.set_text(data)
        finally:
            self._updating = False
        self._on_edit_changed()
        if self.current_segment is not None:
            self._toast(f"Slice {self.current_segment + 1} → {label}")
