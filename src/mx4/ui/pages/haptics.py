"""Haptics page — intensity, pattern picker, event triggers."""

from __future__ import annotations

import math
import threading
from typing import Optional

import cairo  # type: ignore[import-untyped]
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

from ..widgets.common import section_title, page_title, setting_row
from ...config import ConfigStore


# (pattern_id, name, subtitle, kind)
PATTERNS: list[tuple[int, str, str, str]] = [
    (0,  "Subtle tick",  "Light pressure",    "pulse"),
    (1,  "Light click",  "Subtle tap",        "click"),
    (2,  "Medium click", "Standard feel",     "click"),
    (3,  "Strong click", "Firm response",     "click"),
    (4,  "Soft bump",    "Gentle nudge",      "pulse"),
    (5,  "Double tap",   "Two quick taps",    "double"),
    (6,  "Triple tap",   "Three quick taps",  "double"),
    (7,  "Ramp up",      "Building intensity","ramp"),
    (8,  "Ramp down",    "Fading intensity",  "ramp"),
    (9,  "Pulse",        "Light vibration",   "wave"),
    (10, "Strong pulse", "Strong vibration",  "wave"),
    (11, "Alert",        "Attention grab",    "pulse"),
    (12, "Success",      "Confirmation",      "click"),
    (13, "Error",        "Warning signal",    "pulse"),
    (14, "Notification", "System alert",      "pulse"),
]

INTENSITY_LABELS = ["Subtle", "Low", "Medium", "High"]


class PatternCard(Gtk.ToggleButton):
    def __init__(self, pattern_id: int, name: str, sub: str, kind: str):
        super().__init__()
        self.pattern_id = pattern_id
        self.kind = kind
        self.add_css_class("mx4-pattern")
        self.set_size_request(150, 110)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                      halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.set_child(box)

        vis = Gtk.DrawingArea()
        vis.set_size_request(54, 30)
        vis.set_draw_func(lambda a, c, w, h: self._draw(c, w, h))
        self._vis = vis
        box.append(vis)

        name_label = Gtk.Label(label=name)
        name_label.add_css_class("mx4-pattern-name")
        box.append(name_label)

        sub_label = Gtk.Label(label=sub)
        sub_label.add_css_class("mx4-pattern-sub")
        sub_label.set_wrap(True)
        sub_label.set_justify(Gtk.Justification.CENTER)
        box.append(sub_label)

        # Redraw when selection toggles so the glyph colour updates
        self.connect("toggled", lambda *_: self._vis.queue_draw())

    def _stroke(self, cr):
        if self.get_active():
            cr.set_source_rgb(0.83, 0.65, 0.46)
        else:
            cr.set_source_rgb(0.55, 0.58, 0.62)
        cr.set_line_width(1.6)
        cr.set_line_cap(cairo.LineCap.ROUND)

    def _draw(self, cr, w: int, h: int):
        cx, cy = w / 2, h / 2
        self._stroke(cr)

        if self.kind == "click":
            cr.move_to(cx - 20, cy + 5); cr.line_to(cx - 4, cy + 5)
            cr.line_to(cx, cy - 12); cr.line_to(cx + 4, cy + 5)
            cr.line_to(cx + 20, cy + 5); cr.stroke()
        elif self.kind == "double":
            for ox in (-10, 10):
                cr.move_to(cx + ox - 10, cy + 5)
                cr.line_to(cx + ox - 2, cy + 5)
                cr.line_to(cx + ox, cy - 10)
                cr.line_to(cx + ox + 2, cy + 5)
                cr.line_to(cx + ox + 10, cy + 5)
            cr.stroke()
        elif self.kind == "ramp":
            cr.move_to(cx - 20, cy + 10); cr.line_to(cx, cy - 8)
            cr.line_to(cx + 4, cy - 8); cr.line_to(cx + 20, cy + 10)
            cr.stroke()
        elif self.kind == "wave":
            cr.move_to(cx - 22, cy)
            for xi in range(-22, 23):
                cr.line_to(cx + xi, cy + math.sin(xi * 0.4) * 7)
            cr.stroke()
        else:  # pulse
            if self.get_active():
                base = (0.83, 0.65, 0.46)
            else:
                base = (0.55, 0.58, 0.62)
            for i, r in enumerate((5, 10, 15)):
                cr.set_source_rgba(*base, 1.0 - i * 0.3)
                cr.arc(cx, cy, r, 0, 2 * math.pi)
                cr.stroke()


class HapticsPage(Gtk.Box):
    def __init__(self, client):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.client = client
        self.store = ConfigStore()
        self.cfg = self.store.config.haptics
        self._updating = False
        self._cards: list[PatternCard] = []

        self.set_margin_top(4)
        self.set_margin_bottom(24)

        self.append(page_title(
            "Haptics",
            "Tactile feedback for the ring and system events.",
        ))

        # ─── Intensity card ─────────────────────────────────────────
        self.append(section_title("Haptic intensity"))
        i_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        i_card.add_css_class("mx4-card")
        self.append(i_card)

        i_head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        i_card.append(i_head)
        i_title = Gtk.Label(label="Device-level strength", xalign=0)
        i_title.add_css_class("mx4-card-title")
        i_title.set_hexpand(True)
        i_head.append(i_title)
        self.i_value = Gtk.Label(
            label=INTENSITY_LABELS[self.cfg.intensity], xalign=1,
        )
        self.i_value.add_css_class("mx4-card-value-small")
        i_head.append(self.i_value)

        self.i_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 3, 1,
        )
        self.i_scale.add_css_class("mx4-slider")
        self.i_scale.add_css_class("mx4-slider-large")
        self.i_scale.set_draw_value(False)
        self.i_scale.set_hexpand(True)
        self.i_scale.set_value(self.cfg.intensity)
        for i, label in enumerate(INTENSITY_LABELS):
            self.i_scale.add_mark(i, Gtk.PositionType.BOTTOM, label)
        self.i_scale.connect("value-changed", self._on_intensity_changed)
        i_card.append(self.i_scale)

        # ─── Pattern picker ─────────────────────────────────────────
        self.append(section_title("Feedback patterns"))
        pat_hint = Gtk.Label(
            label="Click to play and set as the ring's confirmation haptic.",
            xalign=0,
        )
        pat_hint.add_css_class("mx4-card-sub")
        pat_hint.set_margin_bottom(4)
        self.append(pat_hint)

        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_homogeneous(True)
        flow.set_max_children_per_line(5)
        flow.set_min_children_per_line(2)
        flow.set_column_spacing(10)
        flow.set_row_spacing(10)
        self.append(flow)

        group_root: Optional[PatternCard] = None
        for pid, name, sub, kind in PATTERNS:
            card = PatternCard(pid, name, sub, kind)
            if group_root is None:
                group_root = card
            else:
                card.set_group(group_root)
            card.set_active(pid == self.cfg.ring_confirm_pattern)
            card.connect("toggled", self._on_card_toggled)
            flow.append(card)
            self._cards.append(card)

        # ─── Ring haptic customisation ──────────────────────────────
        self.append(section_title("Actions-Ring feel"))
        ring_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        ring_card.add_css_class("mx4-card")
        self.append(ring_card)

        self.boundary_combo = self._pattern_combo(self.cfg.ring_boundary_pattern)
        self.confirm_combo  = self._pattern_combo(self.cfg.ring_confirm_pattern)
        self.cancel_combo   = self._pattern_combo(self.cfg.ring_cancel_pattern)

        ring_card.append(self._labeled_combo(
            "Segment-crossing tick",
            "Played each time the highlighted segment changes.",
            self.boundary_combo, self._on_boundary_changed,
        ))
        ring_card.append(self._labeled_combo(
            "Confirmation click",
            "Played when the gesture releases on a segment.",
            self.confirm_combo, self._on_confirm_changed,
        ))
        ring_card.append(self._labeled_combo(
            "Cancel-zone release",
            "Played when the gesture cancels in the centre.",
            self.cancel_combo, self._on_cancel_changed,
        ))

        # ─── Event triggers ─────────────────────────────────────────
        self.append(section_title("Event triggers"))

        self.notif_switch = Gtk.Switch(active=self.cfg.notification_enabled)
        self.notif_switch.connect("notify::active", self._on_notif_toggle)
        self.append(setting_row(
            "Desktop notifications",
            "Pulse when any app posts a notification.",
            self.notif_switch,
        ))

        self.scroll_switch = Gtk.Switch(active=self.cfg.scroll_end_enabled)
        self.scroll_switch.connect("notify::active", self._on_scroll_toggle)
        self.append(setting_row(
            "Scroll endpoints",
            "Tick when reaching the top or bottom of a page.",
            self.scroll_switch,
        ))

    # ─── helpers ────────────────────────────────────────────────────

    def _pattern_combo(self, initial: int) -> Gtk.DropDown:
        items = [f"{i:>2}  {name}" for i, (pid, name, *_rest) in enumerate(PATTERNS)]
        dd = Gtk.DropDown.new_from_strings(items)
        dd.set_selected(initial)
        dd.set_size_request(220, -1)
        return dd

    def _labeled_combo(self, title: str, sub: str,
                        dropdown: Gtk.DropDown, handler) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        t = Gtk.Label(label=title, xalign=0)
        t.add_css_class("mx4-row-title")
        col.append(t)
        s = Gtk.Label(label=sub, xalign=0)
        s.add_css_class("mx4-row-sub")
        s.set_wrap(True)
        col.append(s)
        row.append(col)
        dropdown.set_valign(Gtk.Align.CENTER)
        dropdown.connect("notify::selected", handler)
        row.append(dropdown)
        return row

    def _save(self) -> None:
        self.store.save()

    def _play(self, pattern: int) -> None:
        threading.Thread(
            target=lambda: self.client.trigger_haptic(pattern),
            daemon=True,
        ).start()

    # ─── handlers ───────────────────────────────────────────────────

    def _on_intensity_changed(self, scale):
        if self._updating:
            return
        val = int(scale.get_value())
        self.cfg.intensity = val
        self.i_value.set_text(INTENSITY_LABELS[val])
        self._save()
        self._play(self.cfg.ring_confirm_pattern)

    def _on_card_toggled(self, card: PatternCard):
        if self._updating or not card.get_active():
            return
        self.cfg.ring_confirm_pattern = card.pattern_id
        self._save()
        self._play(card.pattern_id)
        self._updating = True
        try:
            self.confirm_combo.set_selected(card.pattern_id)
        finally:
            self._updating = False

    def _on_boundary_changed(self, dropdown, _):
        if self._updating:
            return
        self.cfg.ring_boundary_pattern = dropdown.get_selected()
        self._save()
        self._play(self.cfg.ring_boundary_pattern)

    def _on_confirm_changed(self, dropdown, _):
        if self._updating:
            return
        val = dropdown.get_selected()
        self.cfg.ring_confirm_pattern = val
        self._save()
        self._play(val)
        self._updating = True
        try:
            for c in self._cards:
                c.set_active(c.pattern_id == val)
        finally:
            self._updating = False

    def _on_cancel_changed(self, dropdown, _):
        if self._updating:
            return
        self.cfg.ring_cancel_pattern = dropdown.get_selected()
        self._save()

    def _on_notif_toggle(self, sw, _):
        self.cfg.notification_enabled = sw.get_active()
        self._save()

    def _on_scroll_toggle(self, sw, _):
        self.cfg.scroll_end_enabled = sw.get_active()
        self._save()
