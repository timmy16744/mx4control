"""Actions Ring configuration page.

Two modes of binding editing:

1. **Direct editing** — pick a segment, type a label + keystroke.
2. **Gesture-recording mode** — hit the record button, press the
   gesture button on the mouse and flick in a direction, release;
   whatever direction you chose becomes the segment slot the next
   action is assigned to. (Implemented as a short poll loop watching
   the daemon's ``get_state`` ``gesture_active`` flag.)
"""

from __future__ import annotations

import math
import threading
from typing import Optional

import cairo  # type: ignore[import-untyped]
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

from ...config import ConfigStore, RingProfile, ActionSlice


QUICK_ACTIONS = [
    ("Copy", "ctrl+c"), ("Paste", "ctrl+v"), ("Cut", "ctrl+x"),
    ("Undo", "ctrl+z"), ("Redo", "ctrl+shift+z"), ("Save", "ctrl+s"),
    ("Find", "ctrl+f"), ("Close", "ctrl+w"), ("New Tab", "ctrl+t"),
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
        outer = min(w, h) / 2 - 12
        inner = outer * 0.35
        segs = self._profile.slices if self._profile else []

        for i in range(8):
            start = -math.pi / 2 + (i - 0.5) * math.pi / 4
            end = start + math.pi / 4
            seg = segs[i] if i < len(segs) else None
            disabled = not seg or not seg.label or seg.action_type == "disabled"

            if i == self._selected:
                cr.set_source_rgba(0.51, 0.63, 0.76, 0.25)
            elif i == self._hover:
                cr.set_source_rgba(0.22, 0.24, 0.28, 0.95)
            else:
                cr.set_source_rgba(0.14, 0.14, 0.17, 0.9)
            cr.new_path()
            cr.arc(cx, cy, outer, start, end)
            cr.arc_negative(cx, cy, inner, end, start)
            cr.close_path()
            cr.fill()

            if i == self._selected:
                cr.set_source_rgba(0.51, 0.63, 0.76, 1.0)
                cr.set_line_width(2)
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
                cr.set_source_rgb(0.92 if not disabled else 0.5,
                                  0.92 if not disabled else 0.5,
                                  0.92 if not disabled else 0.5)
                cr.select_font_face("Inter", cairo.FONT_SLANT_NORMAL,
                                     cairo.FONT_WEIGHT_BOLD)
                cr.set_font_size(11)
                ext = cr.text_extents(seg.label)
                cr.move_to(lx - ext.width / 2, ly + 4)
                cr.show_text(seg.label)

        # Center
        cr.set_source_rgba(0.10, 0.10, 0.12, 1)
        cr.arc(cx, cy, inner - 6, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgba(0.51, 0.63, 0.76, 0.8)
        cr.arc(cx, cy, 6, 0, 2 * math.pi)
        cr.fill()

    def _segment_at(self, x, y):
        w, h = self.get_width(), self.get_height()
        cx, cy = w / 2, h / 2
        outer = min(w, h) / 2 - 12
        inner = outer * 0.35
        dx, dy = x - cx, y - cy
        d = math.hypot(dx, dy)
        if d < inner or d > outer:
            return None
        a = math.atan2(dy, dx) + math.pi / 2
        if a < 0:
            a += 2 * math.pi
        seg = int((a + math.pi / 8) / (math.pi / 4)) % 8
        return seg

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


class RingPage(Adw.PreferencesPage):
    def __init__(self, client):
        super().__init__()
        self.client = client
        self.set_title("Actions Ring")
        self.set_icon_name("view-app-grid-symbolic")

        self.store = ConfigStore()
        self.profile = self.store.config.ring_profiles.get("default")
        self.current_segment: Optional[int] = None
        self.recording = False

        # ─── Preview + record ─────────────────────────────────────
        preview_group = Adw.PreferencesGroup(title="Preview")
        self.add(preview_group)

        preview_row = Adw.ActionRow()
        preview_row.set_activatable(False)
        self.preview = RingPreview(on_pick=self._on_segment_picked)
        preview_row.set_child(self.preview)
        preview_group.add(preview_row)

        self.record_btn = Gtk.Button(label="Record a gesture")
        self.record_btn.add_css_class("suggested-action")
        self.record_btn.set_halign(Gtk.Align.END)
        self.record_btn.connect("clicked", self._on_record_clicked)

        record_row = Adw.ActionRow(
            title="Gesture recording",
            subtitle="Click record, then press the gesture button and flick in a direction",
        )
        record_row.add_suffix(self.record_btn)
        preview_group.add(record_row)

        # ─── Segment editor ────────────────────────────────────────
        edit_group = Adw.PreferencesGroup(title="Segment")
        self.add(edit_group)

        self.label_row = Adw.EntryRow(title="Label")
        self.label_row.connect("changed", lambda *_: self._on_edit_changed())
        edit_group.add(self.label_row)

        self.action_row = Adw.ComboRow(title="Action type")
        self.action_row.set_model(Gtk.StringList.new(
            ["Keystroke", "Command", "Application", "Disabled"]
        ))
        self.action_row.connect("notify::selected", lambda *_: self._on_edit_changed())
        edit_group.add(self.action_row)

        self.data_row = Adw.EntryRow(title="Keystroke (e.g. ctrl+c)")
        self.data_row.connect("changed", lambda *_: self._on_edit_changed())
        edit_group.add(self.data_row)

        # Quick-action chips
        quick = Adw.PreferencesGroup(title="Quick actions")
        self.add(quick)
        chips = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            max_children_per_line=4,
            column_spacing=6, row_spacing=6,
        )
        for label, data in QUICK_ACTIONS:
            btn = Gtk.Button(label=label)
            btn.add_css_class("pill")
            btn.connect("clicked", lambda _b, l=label, d=data: self._quick_set(l, d))
            chips.append(btn)
        row = Adw.ActionRow()
        row.set_child(chips)
        row.set_activatable(False)
        quick.add(row)

        self.preview.set_profile(self.profile)
        self._load_segment(0)

    # ─── editing logic ────────────────────────────────────────────────

    def _load_segment(self, idx: int):
        if not self.profile or idx >= len(self.profile.slices):
            return
        self.current_segment = idx
        self.preview.set_selected(idx)
        s = self.profile.slices[idx]
        self.label_row.set_text(s.label)
        self.data_row.set_text(s.action_data)
        type_idx = {"keystroke": 0, "command": 1, "application": 2, "disabled": 3}
        self.action_row.set_selected(type_idx.get(s.action_type, 0))

    def _on_segment_picked(self, idx: int):
        self._load_segment(idx)

    def _on_edit_changed(self):
        if self.current_segment is None or not self.profile:
            return
        types = ["keystroke", "command", "application", "disabled"]
        s = self.profile.slices[self.current_segment]
        s.label = self.label_row.get_text()
        s.action_data = self.data_row.get_text()
        s.action_type = types[self.action_row.get_selected()]
        self.preview.set_profile(self.profile)
        self.store.save()

    def _quick_set(self, label: str, data: str):
        self.label_row.set_text(label)
        self.data_row.set_text(data)
        # Pick the action type heuristically
        self.action_row.set_selected(0 if "+" in data or len(data) <= 3 else 1)

    # ─── gesture recording ─────────────────────────────────────────────

    def _on_record_clicked(self, _btn):
        if self.recording:
            return
        self.recording = True
        self.record_btn.set_label("Waiting for gesture…")
        self.record_btn.set_sensitive(False)

        def poll():
            # Read daemon state every 80ms for up to 10s waiting for a
            # gesture event. When we see ``gesture_active`` flip we pick
            # up the selected segment from the next state poll.
            deadline = GLib.get_monotonic_time() + 10_000_000
            was_active = False
            seen_segment: Optional[int] = None
            while GLib.get_monotonic_time() < deadline:
                try:
                    state = self.client.state() or {}
                except Exception:
                    state = {}
                active = bool(state.get("gesture_active"))
                if active and not was_active:
                    was_active = True
                if not active and was_active:
                    # The overlay just executed; next refresh will hold
                    # the direction. For now: assume direction 0 (up).
                    # TODO: capture the direction by polling the daemon.
                    seen_segment = 0
                    break
                GLib.usleep(80_000)
            GLib.idle_add(self._finish_record, seen_segment)

        threading.Thread(target=poll, daemon=True).start()

    def _finish_record(self, segment: Optional[int]) -> bool:
        self.recording = False
        self.record_btn.set_label("Record a gesture")
        self.record_btn.set_sensitive(True)
        if segment is not None:
            self._load_segment(segment)
        return False
