"""Actions Ring configuration — radial preview + segment editor."""

from __future__ import annotations

import math
import threading
from typing import Optional

import cairo  # type: ignore[import-untyped]
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

from ..widgets.common import section_title, page_title
from ...config import ConfigStore, RingProfile, ActionSlice


QUICK_ACTIONS = [
    ("Copy",        "ctrl+c"),
    ("Paste",       "ctrl+v"),
    ("Cut",         "ctrl+x"),
    ("Undo",        "ctrl+z"),
    ("Redo",        "ctrl+shift+z"),
    ("Save",        "ctrl+s"),
    ("Find",        "ctrl+f"),
    ("Close",       "ctrl+w"),
    ("New Tab",     "ctrl+t"),
    ("Screenshot", "hyprshot -m region"),
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

    def set_profile(self, profile: RingProfile):
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

        # background shadow
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
                cr.select_font_face("Inter", cairo.FONT_SLANT_NORMAL,
                                     cairo.FONT_WEIGHT_BOLD)
                cr.set_font_size(11.5)
                ext = cr.text_extents(seg.label)
                cr.move_to(lx - ext.width / 2, ly + 4)
                cr.show_text(seg.label)

        # Center
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
    def __init__(self, client):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.client = client
        self.store = ConfigStore()
        self.profile = self.store.config.ring_profiles.get("default")
        self.current_segment: Optional[int] = None
        self._updating = False

        self.set_margin_top(4)
        self.set_margin_bottom(24)

        self.append(page_title(
            "Actions Ring",
            "Eight quick actions, one thumb flick away.",
        ))

        # ─── Preview + segment editor side-by-side ──────────────────
        columns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        self.append(columns)

        # Left: preview
        preview_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        preview_card.add_css_class("mx4-card")
        preview_card.set_valign(Gtk.Align.START)
        columns.append(preview_card)

        self.preview = RingPreview(on_pick=self._on_segment_picked)
        preview_card.append(self.preview)

        hint = Gtk.Label(label="Click a segment to edit")
        hint.add_css_class("mx4-card-sub")
        hint.set_halign(Gtk.Align.CENTER)
        preview_card.append(hint)

        # Right: editor
        edit_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                           hexpand=True)
        columns.append(edit_col)

        edit_col.append(section_title("Segment"))
        editor = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        editor.add_css_class("mx4-card")
        edit_col.append(editor)

        self.seg_title = Gtk.Label(label="— Select a segment —", xalign=0)
        self.seg_title.add_css_class("mx4-card-title")
        editor.append(self.seg_title)

        # Label entry
        lbl_head = Gtk.Label(label="LABEL", xalign=0)
        lbl_head.add_css_class("mx4-card-unit")
        editor.append(lbl_head)
        self.label_entry = Gtk.Entry()
        self.label_entry.set_placeholder_text("e.g. Copy")
        self.label_entry.add_css_class("mx4-entry")
        self.label_entry.connect("changed", self._on_edit_changed)
        editor.append(self.label_entry)

        # Action type
        act_head = Gtk.Label(label="ACTION TYPE", xalign=0)
        act_head.add_css_class("mx4-card-unit")
        editor.append(act_head)
        self.type_dropdown = Gtk.DropDown.new_from_strings(
            ["Keystroke", "Command", "Application", "Disabled"],
        )
        self.type_dropdown.connect("notify::selected", self._on_edit_changed)
        editor.append(self.type_dropdown)

        # Action data
        data_head = Gtk.Label(label="PAYLOAD", xalign=0)
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
        for label, data in QUICK_ACTIONS:
            btn = Gtk.Button(label=label)
            btn.add_css_class("mx4-chip")
            btn.connect("clicked", lambda _b, l=label, d=data: self._quick_set(l, d))
            chips_box.append(btn)

        self.preview.set_profile(self.profile)
        self._load_segment(0)

    # ─── editor logic ───────────────────────────────────────────────

    def refresh(self) -> None:
        self.store._config = None
        self.profile = self.store.config.ring_profiles.get("default")
        self.preview.set_profile(self.profile)
        self._load_segment(self.current_segment or 0)

    def _load_segment(self, idx: int):
        if not self.profile or idx >= len(self.profile.slices):
            return
        self.current_segment = idx
        self.preview.set_selected(idx)
        s = self.profile.slices[idx]
        self.seg_title.set_text(f"Segment {idx + 1}")
        self._updating = True
        try:
            self.label_entry.set_text(s.label)
            self.data_entry.set_text(s.action_data)
            idx_type = {"keystroke": 0, "command": 1, "application": 2, "disabled": 3}
            self.type_dropdown.set_selected(idx_type.get(s.action_type, 0))
        finally:
            self._updating = False

    def _on_segment_picked(self, idx: int):
        self._load_segment(idx)

    def _on_edit_changed(self, *_a):
        if self._updating or self.current_segment is None or not self.profile:
            return
        types = ["keystroke", "command", "application", "disabled"]
        s = self.profile.slices[self.current_segment]
        s.label = self.label_entry.get_text()
        s.action_data = self.data_entry.get_text()
        s.action_type = types[self.type_dropdown.get_selected()]
        self.preview.set_profile(self.profile)
        self.store.save()

    def _quick_set(self, label: str, data: str):
        self.label_entry.set_text(label)
        self.data_entry.set_text(data)
        self.type_dropdown.set_selected(0 if "+" in data or len(data) <= 3 else 1)
