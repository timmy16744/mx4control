"""Haptics & Thumb Pad page — 0x19B0 Haptic Motor, 0x19C0 Force Sensing, Waveforms, Notifications."""

from __future__ import annotations

import math
import threading
from typing import Any, Optional

import cairo  # type: ignore[import-untyped]
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

from ..widgets.common import page_title, section_title, setting_row
from ...common.dbus import DaemonUnavailable
from ...config import ConfigStore


# Official MX Master 4 HAPTIC (0x19B0) waveform bank (0..14)
PATTERNS: list[tuple[int, str, str, str]] = [
    (0,  "Sharp State",   "Crisp micro-tick",    "click"),
    (1,  "Damp State",    "Soft state tick",     "pulse"),
    (2,  "Sharp Impact",  "Firm confirmation",   "click"),
    (3,  "Damp Impact",   "Cushioned tap",       "pulse"),
    (4,  "Subtle Impact", "Feather nudge",       "pulse"),
    (5,  "Happy Alert",   "Upbeat double-tap",   "double"),
    (6,  "Angry Alert",   "Urgent double-tap",   "double"),
    (7,  "Completed",     "Task-done cadence",   "ramp"),
    (8,  "Square",        "Sharp square pulse",  "wave"),
    (9,  "Wave",          "Smooth sine wave",    "wave"),
    (10, "Firework",      "Bursting pulse",      "ramp"),
    (11, "Mad",           "Strong warning",      "wave"),
    (12, "Knock",         "Double knock",        "double"),
    (13, "Jingle",        "Melodic ripple",      "ramp"),
    (14, "Ringing",       "Notification buzz",   "wave"),
]

STRENGTH_PRESETS = [
    (25,  "Subtle"),
    (50,  "Medium"),
    (75,  "High"),
    (100, "Max"),
]


class PatternCard(Gtk.ToggleButton):
    def __init__(self, pattern_id: int, name: str, sub: str, kind: str):
        super().__init__()
        self.pattern_id = pattern_id
        self.kind = kind
        self.add_css_class("mx4-pattern")
        self.set_size_request(144, 108)

        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=5,
            halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
        )
        self.set_child(box)

        vis = Gtk.DrawingArea()
        vis.set_size_request(54, 28)
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
            cr.line_to(cx, cy - 11); cr.line_to(cx + 4, cy + 5)
            cr.line_to(cx + 20, cy + 5); cr.stroke()
        elif self.kind == "double":
            for ox in (-10, 10):
                cr.move_to(cx + ox - 10, cy + 5)
                cr.line_to(cx + ox - 2, cy + 5)
                cr.line_to(cx + ox, cy - 9)
                cr.line_to(cx + ox + 2, cy + 5)
                cr.line_to(cx + ox + 10, cy + 5)
            cr.stroke()
        elif self.kind == "ramp":
            cr.move_to(cx - 20, cy + 9); cr.line_to(cx, cy - 8)
            cr.line_to(cx + 4, cy - 8); cr.line_to(cx + 20, cy + 9)
            cr.stroke()
        elif self.kind == "wave":
            cr.move_to(cx - 22, cy)
            for xi in range(-22, 23):
                cr.line_to(cx + xi, cy + math.sin(xi * 0.4) * 7)
            cr.stroke()
        else:
            base = (0.83, 0.65, 0.46) if self.get_active() else (0.55, 0.58, 0.62)
            for i, r in enumerate((5, 9, 13)):
                cr.set_source_rgba(*base, 1.0 - i * 0.3)
                cr.arc(cx, cy, r, 0, 2 * math.pi)
                cr.stroke()


class HapticsPage(Gtk.Box):
    def __init__(self, client, *, window=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.client = client
        self.window = window
        self.store = ConfigStore()
        self._updating = False
        self._cards: list[PatternCard] = []
        self._haptic_debounce: Optional[int] = None
        self._force_debounce: Optional[int] = None
        self._force_min = 4156
        self._force_max = 6909
        self._force_default = 5195

        self.set_margin_top(4)
        self.set_margin_bottom(24)

        self.append(page_title(
            "Haptics & Thumb Pad",
            "Hardware haptic motor strength, force-sensing thumb pad pressure, waveforms, and triggers.",
        ))

        # ─── Hardware Haptic Motor (0x19B0) ─────────────────────────
        self.append(section_title("Hardware haptic motor (0x19B0)"))

        self.motor_switch = Gtk.Switch()
        self.motor_switch.connect("notify::active", self._on_motor_toggle)
        self.append(setting_row(
            "Enable haptic motor",
            "Hardware power switch for the MX Master 4 tactile actuator. Turn off to silence the thumb-pad buzz completely.",
            self.motor_switch,
        ))

        i_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        i_card.add_css_class("mx4-card")
        self.append(i_card)
        self.strength_card = i_card

        i_head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        i_card.append(i_head)
        i_title = Gtk.Label(label="Motor strength", xalign=0, hexpand=True)
        i_title.add_css_class("mx4-card-title")
        i_head.append(i_title)
        self.i_value = Gtk.Label(label="50%", xalign=1)
        self.i_value.add_css_class("mx4-card-value-small")
        i_head.append(self.i_value)

        self.i_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1)
        self.i_scale.add_css_class("mx4-slider")
        self.i_scale.add_css_class("mx4-slider-large")
        self.i_scale.set_draw_value(False)
        self.i_scale.set_hexpand(True)
        self.i_scale.set_value(50)
        for pct, lbl in STRENGTH_PRESETS:
            self.i_scale.add_mark(pct, Gtk.PositionType.BOTTOM, lbl)
        self.i_scale.connect("value-changed", self._on_strength_changed)
        i_card.append(self.i_scale)

        chips = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=6, halign=Gtk.Align.CENTER,
        )
        i_card.append(chips)
        for pct, lbl in STRENGTH_PRESETS:
            b = Gtk.Button(label=f"{lbl} ({pct}%)")
            b.add_css_class("mx4-chip")
            b.connect("clicked", lambda _b, v=pct: self.i_scale.set_value(v))
            chips.append(b)

        # ─── Force-Sensing Thumb Pad (0x19C0) ───────────────────────
        self.append(section_title("Thumb pad press force (0x19C0)"))

        self.force_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.force_card.add_css_class("mx4-card")
        self.append(self.force_card)

        f_head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.force_card.append(f_head)
        f_title = Gtk.Label(label="Actuation force threshold", xalign=0, hexpand=True)
        f_title.add_css_class("mx4-card-title")
        f_head.append(f_title)
        self.force_val_label = Gtk.Label(label="Default", xalign=1)
        self.force_val_label.add_css_class("mx4-card-value-small")
        f_head.append(self.force_val_label)

        f_sub = Gtk.Label(
            label="Adjust how firmly you must squeeze the Haptic Sense thumb pad to trigger a press.",
            xalign=0,
        )
        f_sub.add_css_class("mx4-card-sub")
        f_sub.set_wrap(True)
        self.force_card.append(f_sub)

        self.force_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, self._force_min, self._force_max, 50,
        )
        self.force_scale.add_css_class("mx4-slider")
        self.force_scale.set_draw_value(False)
        self.force_scale.set_hexpand(True)
        self.force_scale.set_value(self._force_default)
        self.force_scale.add_mark(self._force_min, Gtk.PositionType.BOTTOM, "Light")
        self.force_scale.add_mark(self._force_default, Gtk.PositionType.BOTTOM, "Default")
        self.force_scale.add_mark(self._force_max, Gtk.PositionType.BOTTOM, "Firm")
        self.force_scale.connect("value-changed", self._on_force_changed)
        self.force_card.append(self.force_scale)

        f_foot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.force_card.append(f_foot)
        self.force_raw_lbl = Gtk.Label(label="", xalign=0, hexpand=True)
        self.force_raw_lbl.add_css_class("mx4-card-sub")
        f_foot.append(self.force_raw_lbl)

        reset_force = Gtk.Button(label="Reset to factory default")
        reset_force.add_css_class("mx4-btn-ghost")
        reset_force.connect("clicked", self._on_force_reset)
        f_foot.append(reset_force)

        # ─── Built-in Waveform Bank ─────────────────────────────────
        self.append(section_title("Hardware waveform bank (15 patterns)"))
        pat_hint = Gtk.Label(
            label="Click any waveform to feel it live on the mouse and set it as the ring confirmation pulse.",
            xalign=0,
        )
        pat_hint.add_css_class("mx4-card-sub")
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
            card.connect("toggled", self._on_card_toggled)
            flow.append(card)
            self._cards.append(card)

        # ─── Actions-Ring haptic customisation ──────────────────────
        self.append(section_title("Actions-Ring tactile feel"))
        ring_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        ring_card.add_css_class("mx4-card")
        self.append(ring_card)

        self.boundary_combo = self._pattern_combo()
        self.confirm_combo = self._pattern_combo()
        self.cancel_combo = self._pattern_combo()

        ring_card.append(self._labeled_combo(
            "Segment-crossing tick",
            "Played each time the highlighted slice changes.",
            self.boundary_combo, self._on_boundary_changed,
        ))
        ring_card.append(self._labeled_combo(
            "Confirmation pulse",
            "Played when releasing on an active action.",
            self.confirm_combo, self._on_confirm_changed,
        ))
        ring_card.append(self._labeled_combo(
            "Cancel-zone release",
            "Played when releasing in the centre cancel zone.",
            self.cancel_combo, self._on_cancel_changed,
        ))

        # ─── Desktop Notification Trigger ───────────────────────────
        self.append(section_title("Event triggers"))

        self.notif_switch = Gtk.Switch()
        self.notif_switch.connect("notify::active", self._on_notif_toggle)
        self.append(setting_row(
            "Desktop notifications",
            "Pulse the mouse when any app posts a desktop notification (org.freedesktop.Notifications).",
            self.notif_switch,
        ))

        notif_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        notif_card.add_css_class("mx4-card")
        self.append(notif_card)
        self.notif_combo = self._pattern_combo()
        notif_card.append(self._labeled_combo(
            "Notification waveform",
            "Waveform played on incoming desktop notifications (1.5 s cooldown).",
            self.notif_combo, self._on_notif_pattern_changed,
        ))

        self.refresh()

    # ─── sync from live hardware + session config ───────────────────

    def refresh(self) -> None:
        self._load_session_haptics()

        def fetch():
            try:
                state = self.client.get_state() or {}
            except Exception:
                state = {}
            GLib.idle_add(self._apply_hardware_state, state)
        threading.Thread(target=fetch, daemon=True).start()

    def apply_state_delta(self, delta: dict[str, Any]) -> None:
        if any(k in delta for k in ("haptic_enabled", "haptic_level", "force_value")):
            self._apply_hardware_state(delta, partial=True)

    def _load_session_haptics(self) -> None:
        self.store.invalidate()
        cfg = self.store.config.haptics
        self._updating = True
        try:
            self.boundary_combo.set_selected(cfg.ring_boundary_pattern)
            self.confirm_combo.set_selected(cfg.ring_confirm_pattern)
            self.cancel_combo.set_selected(cfg.ring_cancel_pattern)
            self.notif_switch.set_active(cfg.notification_enabled)
            self.notif_combo.set_selected(cfg.notification_pattern)
            for c in self._cards:
                c.set_active(c.pattern_id == cfg.ring_confirm_pattern)
        finally:
            self._updating = False

    def _apply_hardware_state(self, state: dict[str, Any], partial: bool = False) -> bool:
        if not partial and not state.get("connected"):
            return False
        self._updating = True
        try:
            if "haptic_enabled" in state:
                en = bool(state["haptic_enabled"])
                self.motor_switch.set_active(en)
                self.strength_card.set_sensitive(en)
            if "haptic_level" in state:
                lvl = max(1, min(100, int(state["haptic_level"]) or 50))
                self.i_scale.set_value(lvl)
                self.i_value.set_text(f"{lvl}%")

            if "force_supported" in state:
                self.force_card.set_visible(bool(state["force_supported"]))
            if "force_min" in state and "force_max" in state:
                fmin = int(state["force_min"])
                fmax = int(state["force_max"])
                fdef = int(state.get("force_default", (fmin + fmax) // 2))
                if fmin < fmax:
                    self._force_min, self._force_max, self._force_default = fmin, fmax, fdef
                    self.force_scale.clear_marks()
                    self.force_scale.set_range(fmin, fmax)
                    self.force_scale.add_mark(fmin, Gtk.PositionType.BOTTOM, "Light")
                    self.force_scale.add_mark(fdef, Gtk.PositionType.BOTTOM, "Default")
                    self.force_scale.add_mark(fmax, Gtk.PositionType.BOTTOM, "Firm")
            if "force_value" in state:
                fval = int(state["force_value"])
                self.force_scale.set_value(fval)
                self._update_force_labels(fval)
        finally:
            self._updating = False
        return False

    def _update_force_labels(self, fval: int) -> None:
        span = max(1, self._force_max - self._force_min)
        pct = max(0, min(100, round((fval - self._force_min) * 100 / span)))
        tag = " (factory default)" if abs(fval - self._force_default) <= 10 else ""
        self.force_val_label.set_text(f"{pct}%{tag}")
        self.force_raw_lbl.set_text(
            f"Raw sensor threshold: {fval}  (range {self._force_min}–{self._force_max})"
        )

    # ─── helpers ────────────────────────────────────────────────────

    def _pattern_combo(self) -> Gtk.DropDown:
        items = [f"{pid:>2}  {name}" for pid, name, *_rest in PATTERNS]
        dd = Gtk.DropDown.new_from_strings(items)
        dd.set_size_request(210, -1)
        return dd

    def _labeled_combo(
        self, title: str, sub: str, dropdown: Gtk.DropDown, handler
    ) -> Gtk.Box:
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

    def _save_and_reload_agent(self) -> None:
        self.store.save()
        if self.window is not None and self.window.agent is not None:
            threading.Thread(
                target=self.window.agent.reload_profiles, daemon=True
            ).start()

    def _toast(self, message: str) -> None:
        if self.window is not None:
            self.window.toast(message)

    def _play(self, pattern: int) -> None:
        def worker():
            try:
                if not self.client.trigger_haptic(pattern):
                    GLib.idle_add(self._toast, "Failed to play haptic")
            except DaemonUnavailable:
                GLib.idle_add(self._toast, "mx4-sysd not running?")
            except Exception as e:
                GLib.idle_add(self._toast, f"Haptic error: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def _write_motor(self, enabled: bool, level: int, preview: bool = False) -> None:
        def worker():
            try:
                ok = self.client.set_haptic(enabled, level, True)
                if ok and enabled and preview:
                    self.client.trigger_haptic(self.store.config.haptics.ring_confirm_pattern)
                if not ok:
                    GLib.idle_add(self._toast, "Failed to update haptic motor")
            except DaemonUnavailable:
                GLib.idle_add(self._toast, "mx4-sysd not running?")
            except Exception as e:
                GLib.idle_add(self._toast, f"Haptic motor error: {e}")
        threading.Thread(target=worker, daemon=True).start()

    # ─── handlers ───────────────────────────────────────────────────

    def _on_motor_toggle(self, sw, _):
        if self._updating:
            return
        on = sw.get_active()
        self.strength_card.set_sensitive(on)
        lvl = int(self.i_scale.get_value())
        self.store.config.haptics.enabled = on
        self._save_and_reload_agent()
        self._write_motor(on, lvl, preview=on)
        self._toast("Haptic motor enabled" if on else "Haptic motor disabled (silent)")

    def _on_strength_changed(self, scale):
        if self._updating:
            return
        lvl = int(scale.get_value())
        self.i_value.set_text(f"{lvl}%")
        if self._haptic_debounce is not None:
            GLib.source_remove(self._haptic_debounce)
        self._haptic_debounce = GLib.timeout_add(140, self._commit_strength, lvl)

    def _commit_strength(self, lvl: int) -> bool:
        self._haptic_debounce = None
        if self.motor_switch.get_active():
            self._write_motor(True, lvl, preview=True)
        return False

    def _on_force_changed(self, scale):
        if self._updating:
            return
        val = int(scale.get_value())
        self._update_force_labels(val)
        if self._force_debounce is not None:
            GLib.source_remove(self._force_debounce)
        self._force_debounce = GLib.timeout_add(150, self._commit_force, val)

    def _commit_force(self, val: int) -> bool:
        self._force_debounce = None

        def worker():
            try:
                ok = self.client.set_force_threshold(val, True)
                GLib.idle_add(
                    self._toast,
                    f"Thumb pad force updated ({val})" if ok else "Failed to set press force",
                )
            except Exception as e:
                GLib.idle_add(self._toast, f"Force update failed: {e}")
        threading.Thread(target=worker, daemon=True).start()
        return False

    def _on_force_reset(self, _btn):
        self._updating = True
        try:
            self.force_scale.set_value(self._force_default)
            self._update_force_labels(self._force_default)
        finally:
            self._updating = False

        def worker():
            try:
                ok = self.client.set_force_threshold(0, True)
                GLib.idle_add(
                    self._toast,
                    "Thumb pad force reset to factory default" if ok else "Reset failed",
                )
            except Exception as e:
                GLib.idle_add(self._toast, f"Reset failed: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def _on_card_toggled(self, card: PatternCard):
        if self._updating or not card.get_active():
            return
        self.store.config.haptics.ring_confirm_pattern = card.pattern_id
        self._save_and_reload_agent()
        self._play(card.pattern_id)
        self._updating = True
        try:
            self.confirm_combo.set_selected(card.pattern_id)
        finally:
            self._updating = False

    def _on_boundary_changed(self, dropdown, _):
        if self._updating:
            return
        val = dropdown.get_selected()
        self.store.config.haptics.ring_boundary_pattern = val
        self._save_and_reload_agent()
        self._play(val)

    def _on_confirm_changed(self, dropdown, _):
        if self._updating:
            return
        val = dropdown.get_selected()
        self.store.config.haptics.ring_confirm_pattern = val
        self._save_and_reload_agent()
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
        val = dropdown.get_selected()
        self.store.config.haptics.ring_cancel_pattern = val
        self._save_and_reload_agent()
        self._play(val)

    def _on_notif_toggle(self, sw, _):
        if self._updating:
            return
        self.store.config.haptics.notification_enabled = sw.get_active()
        self._save_and_reload_agent()
        self._toast(
            "Notification haptics enabled" if sw.get_active() else "Notification haptics disabled"
        )

    def _on_notif_pattern_changed(self, dropdown, _):
        if self._updating:
            return
        val = dropdown.get_selected()
        self.store.config.haptics.notification_pattern = val
        self._save_and_reload_agent()
        self._play(val)
