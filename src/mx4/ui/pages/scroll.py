"""Scroll & Wheel page — SmartShift, Ratchet Torque, Free-Spin, Hi-Res, Thumb Wheel."""

from __future__ import annotations

import threading
from typing import Any, Optional

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

from ..widgets.common import page_title, section_title, setting_row
from ...agent.thumbwheel import THUMBWHEEL_PRESETS
from ...common.dbus import DaemonUnavailable
from ...config import ConfigStore


MODES = [
    ("smart",   "SmartShift",   "Auto-switch by flick speed"),
    ("ratchet", "Ratchet only", "Notched, precise, zero buzz"),
    ("free",    "Free-spin",    "Frictionless smooth momentum"),
]

TORQUE_PRESETS = [
    (25, "Light"),
    (50, "Balanced"),
    (75, "Crisp"),
    (100, "Heavy"),
]

_TW_PRESET_KEYS = list(THUMBWHEEL_PRESETS.keys())


class ScrollPage(Gtk.Box):
    def __init__(self, client, *, window=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.client = client
        self.window = window
        self.store = ConfigStore()
        self._updating = False
        self._current_mode = "smart"
        self._ss_debounce: Optional[int] = None
        self._tw_reload_debounce: Optional[int] = None

        self.set_margin_top(4)
        self.set_margin_bottom(24)

        self.append(page_title(
            "Scroll & Wheel",
            "MagSpeed scroll mode, ratchet torque, hi-res scrolling, and thumb-wheel actions.",
        ))

        # ─── Mode group ─────────────────────────────────────────────
        self.append(section_title("MagSpeed scroll mode"))
        modes_grid = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=10, homogeneous=True,
        )
        self.append(modes_grid)

        self._mode_buttons: dict[str, Gtk.ToggleButton] = {}
        group_root: Gtk.ToggleButton | None = None

        for mode_id, name, desc in MODES:
            b = Gtk.ToggleButton()
            b.add_css_class("mx4-mode")
            b.set_hexpand(True)
            col = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL, spacing=4,
                halign=Gtk.Align.CENTER, margin_top=4, margin_bottom=4,
            )
            name_lbl = Gtk.Label(label=name)
            name_lbl.add_css_class("mx4-mode-title")
            col.append(name_lbl)
            sub = Gtk.Label(label=desc)
            sub.add_css_class("mx4-mode-sub")
            sub.set_wrap(True)
            col.append(sub)
            b.set_child(col)
            if group_root is None:
                group_root = b
            else:
                b.set_group(group_root)
            b.connect("toggled", self._on_mode_toggled, mode_id)
            self._mode_buttons[mode_id] = b
            modes_grid.append(b)

        # ─── SmartShift sensitivity + Ratchet torque ────────────────
        ss_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        ss_card.add_css_class("mx4-card")
        self.append(ss_card)

        ss_head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        ss_card.append(ss_head)
        ss_title = Gtk.Label(label="SmartShift auto-disengage threshold", xalign=0, hexpand=True)
        ss_title.add_css_class("mx4-card-title")
        ss_head.append(ss_title)
        self.ss_value = Gtk.Label(label="15", xalign=1)
        self.ss_value.add_css_class("mx4-card-value-small")
        ss_head.append(self.ss_value)

        ss_sub = Gtk.Label(
            label="Lower values switch to free-spin on gentler flicks (active in SmartShift mode).",
            xalign=0,
        )
        ss_sub.add_css_class("mx4-card-sub")
        ss_sub.set_wrap(True)
        ss_card.append(ss_sub)

        self.ss_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 50, 1)
        self.ss_scale.add_css_class("mx4-slider")
        self.ss_scale.set_draw_value(False)
        self.ss_scale.set_hexpand(True)
        self.ss_scale.set_value(15)
        for mark in (1, 15, 30, 50):
            self.ss_scale.add_mark(mark, Gtk.PositionType.BOTTOM, str(mark))
        self.ss_scale.connect("value-changed", self._on_ss_changed)
        ss_card.append(self.ss_scale)

        # Ratchet Torque (0x2111 tunableTorque)
        self.torque_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.torque_card.add_css_class("mx4-card")
        self.append(self.torque_card)

        tq_head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.torque_card.append(tq_head)
        tq_title = Gtk.Label(label="MagSpeed ratchet torque", xalign=0, hexpand=True)
        tq_title.add_css_class("mx4-card-title")
        tq_head.append(tq_title)
        self.tq_value = Gtk.Label(label="75%", xalign=1)
        self.tq_value.add_css_class("mx4-card-value-small")
        tq_head.append(self.tq_value)

        tq_sub = Gtk.Label(
            label="Controls the magnetic resistance of each notched wheel detent in hardware.",
            xalign=0,
        )
        tq_sub.add_css_class("mx4-card-sub")
        tq_sub.set_wrap(True)
        self.torque_card.append(tq_sub)

        self.tq_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1)
        self.tq_scale.add_css_class("mx4-slider")
        self.tq_scale.set_draw_value(False)
        self.tq_scale.set_hexpand(True)
        self.tq_scale.set_value(75)
        for mark in (1, 25, 50, 75, 100):
            self.tq_scale.add_mark(mark, Gtk.PositionType.BOTTOM, f"{mark}%")
        self.tq_scale.connect("value-changed", self._on_torque_changed)
        self.torque_card.append(self.tq_scale)

        tq_chips = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=6, halign=Gtk.Align.CENTER,
        )
        self.torque_card.append(tq_chips)
        for pct, lbl in TORQUE_PRESETS:
            b = Gtk.Button(label=f"{lbl} ({pct}%)")
            b.add_css_class("mx4-chip")
            b.connect("clicked", lambda _b, v=pct: self.tq_scale.set_value(v))
            tq_chips.append(b)

        # ─── Main wheel reporting (0x2121) ──────────────────────────
        self.append(section_title("Main wheel"))

        self.hires_switch = Gtk.Switch()
        self.hires_switch.connect("notify::active", self._on_hires_toggle)
        self.append(setting_row(
            "High-resolution scrolling",
            "Smooth sub-detent pixel scrolling via HID++ 0x2121.",
            self.hires_switch,
        ))

        self.inv_v_switch = Gtk.Switch()
        self.inv_v_switch.connect("notify::active", self._on_invert_v)
        self.append(setting_row(
            "Invert vertical scroll",
            "Natural scrolling handled directly in mouse hardware.",
            self.inv_v_switch,
        ))

        # ─── Thumb wheel (0x2150) ───────────────────────────────────
        self.append(section_title("Thumb wheel"))

        self.tw_invert_switch = Gtk.Switch()
        self.tw_invert_switch.connect("notify::active", self._on_tw_invert)
        self.append(setting_row(
            "Invert thumb wheel",
            "Flip horizontal scroll direction in hardware (0x2150).",
            self.tw_invert_switch,
        ))

        self.tw_divert_switch = Gtk.Switch()
        self.tw_divert_switch.connect("notify::active", self._on_tw_divert)
        self.append(setting_row(
            "Custom thumb-wheel actions (divert to software)",
            "When off, the thumb wheel sends native horizontal scroll. When on, scroll fires custom actions below.",
            self.tw_divert_switch,
        ))

        # Custom thumb-wheel action card
        self.tw_actions_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.tw_actions_card.add_css_class("mx4-card")
        self.append(self.tw_actions_card)

        preset_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.tw_actions_card.append(preset_row)
        p_lbl = Gtk.Label(label="Action preset", xalign=0, hexpand=True)
        p_lbl.add_css_class("mx4-card-title")
        preset_row.append(p_lbl)

        self.tw_preset_dd = Gtk.DropDown.new_from_strings(
            [THUMBWHEEL_PRESETS[k][0] for k in _TW_PRESET_KEYS]
        )
        self.tw_preset_dd.connect("notify::selected", self._on_tw_preset_changed)
        preset_row.append(self.tw_preset_dd)

        # Positive / Negative action rows
        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        self.tw_actions_card.append(grid)

        pos_lbl = Gtk.Label(label="Scroll forward", xalign=0)
        pos_lbl.add_css_class("mx4-card-sub")
        grid.attach(pos_lbl, 0, 0, 1, 1)

        self.tw_pos_type = Gtk.DropDown.new_from_strings(["Keystroke", "Command", "Application", "Disabled"])
        self.tw_pos_type.connect("notify::selected", self._on_tw_custom_changed)
        grid.attach(self.tw_pos_type, 1, 0, 1, 1)

        self.tw_pos_entry = Gtk.Entry(hexpand=True)
        self.tw_pos_entry.add_css_class("mx4-entry")
        self.tw_pos_entry.connect("changed", self._on_tw_custom_changed)
        grid.attach(self.tw_pos_entry, 2, 0, 1, 1)

        neg_lbl = Gtk.Label(label="Scroll back", xalign=0)
        neg_lbl.add_css_class("mx4-card-sub")
        grid.attach(neg_lbl, 0, 1, 1, 1)

        self.tw_neg_type = Gtk.DropDown.new_from_strings(["Keystroke", "Command", "Application", "Disabled"])
        self.tw_neg_type.connect("notify::selected", self._on_tw_custom_changed)
        grid.attach(self.tw_neg_type, 1, 1, 1, 1)

        self.tw_neg_entry = Gtk.Entry(hexpand=True)
        self.tw_neg_entry.add_css_class("mx4-entry")
        self.tw_neg_entry.connect("changed", self._on_tw_custom_changed)
        grid.attach(self.tw_neg_entry, 2, 1, 1, 1)

        # Sensitivity step + haptic tick
        step_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.tw_actions_card.append(step_row)
        step_lbl = Gtk.Label(label="Trigger sensitivity (lower = faster)", xalign=0, hexpand=True)
        step_lbl.add_css_class("mx4-card-sub")
        step_row.append(step_lbl)
        self.tw_step_val = Gtk.Label(label="40", xalign=1)
        self.tw_step_val.add_css_class("mx4-card-value-small")
        step_row.append(self.tw_step_val)

        self.tw_step_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 10, 120, 5)
        self.tw_step_scale.add_css_class("mx4-slider")
        self.tw_step_scale.set_draw_value(False)
        self.tw_step_scale.connect("value-changed", self._on_tw_step_changed)
        self.tw_actions_card.append(self.tw_step_scale)

        tick_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.tw_actions_card.append(tick_row)
        tick_lbl = Gtk.Label(label="Play subtle haptic tick on each action step", xalign=0, hexpand=True)
        tick_lbl.add_css_class("mx4-card-sub")
        tick_row.append(tick_lbl)
        self.tw_haptic_switch = Gtk.Switch()
        self.tw_haptic_switch.connect("notify::active", self._on_tw_haptic_toggle)
        tick_row.append(self.tw_haptic_switch)

        self.refresh()

    # ─── sync from live hardware + session config ───────────────────

    def refresh(self) -> None:
        self._load_session_thumbwheel()

        def fetch():
            try:
                state = self.client.get_state() or {}
            except Exception:
                state = {}
            GLib.idle_add(self._apply_hardware_state, state)
        threading.Thread(target=fetch, daemon=True).start()

    def apply_state_delta(self, delta: dict[str, Any]) -> None:
        if any(k in delta for k in (
            "wheel_mode", "smartshift", "smartshift_threshold", "ratchet_torque",
            "hires_enabled", "hires_invert", "thumbwheel_diverted", "thumbwheel_invert",
        )):
            self._apply_hardware_state(delta, partial=True)

    def _load_session_thumbwheel(self) -> None:
        self.store.invalidate()
        tw = self.store.config.thumbwheel
        self._updating = True
        try:
            idx = _TW_PRESET_KEYS.index(tw.preset) if tw.preset in _TW_PRESET_KEYS else 0
            self.tw_preset_dd.set_selected(idx)
            type_map = {"keystroke": 0, "command": 1, "application": 2, "disabled": 3}
            self.tw_pos_type.set_selected(type_map.get(tw.positive_type, 0))
            self.tw_pos_entry.set_text(tw.positive_data)
            self.tw_neg_type.set_selected(type_map.get(tw.negative_type, 0))
            self.tw_neg_entry.set_text(tw.negative_data)
            self.tw_step_scale.set_value(tw.step)
            self.tw_step_val.set_text(str(tw.step))
            self.tw_haptic_switch.set_active(tw.haptic_tick)
            self.tw_actions_card.set_sensitive(tw.diverted)
        finally:
            self._updating = False

    def _apply_hardware_state(self, state: dict[str, Any], partial: bool = False) -> bool:
        if not partial and not state.get("connected"):
            return False
        self._updating = True
        try:
            if "wheel_mode" in state:
                mode = str(state["wheel_mode"])
                if mode in self._mode_buttons:
                    self._current_mode = mode
                    self._mode_buttons[mode].set_active(True)
                    self.ss_scale.set_sensitive(mode == "smart")
            elif "smartshift" in state:
                mode = "smart" if state["smartshift"] else "ratchet"
                self._current_mode = mode
                self._mode_buttons[mode].set_active(True)
                self.ss_scale.set_sensitive(mode == "smart")

            if "smartshift_threshold" in state:
                thr = max(1, min(50, int(state["smartshift_threshold"])))
                self.ss_scale.set_value(thr)
                self.ss_value.set_text(str(thr))

            if "ratchet_torque" in state:
                tq = max(1, min(100, int(state["ratchet_torque"])))
                self.tq_scale.set_value(tq)
                self.tq_value.set_text(f"{tq}%")
            if "tunable_torque" in state:
                self.torque_card.set_visible(bool(state["tunable_torque"]))

            if "hires_enabled" in state:
                self.hires_switch.set_active(bool(state["hires_enabled"]))
            if "hires_invert" in state:
                self.inv_v_switch.set_active(bool(state["hires_invert"]))

            if "thumbwheel_diverted" in state:
                div = bool(state["thumbwheel_diverted"])
                self.tw_divert_switch.set_active(div)
                self.tw_actions_card.set_sensitive(div)
            if "thumbwheel_invert" in state:
                self.tw_invert_switch.set_active(bool(state["thumbwheel_invert"]))
        finally:
            self._updating = False
        return False

    # ─── helpers ────────────────────────────────────────────────────

    def _toast(self, message: str) -> None:
        if self.window is not None:
            self.window.toast(message)

    def _run_write(self, fn, ok_msg: str, fail_msg: str) -> None:
        def worker():
            try:
                ok = fn()
                if ok_msg or not ok:
                    GLib.idle_add(self._toast, ok_msg if ok else fail_msg)
            except DaemonUnavailable:
                GLib.idle_add(self._toast, "mx4-sysd not running?")
            except Exception as e:
                GLib.idle_add(self._toast, f"{fail_msg}: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def _save_tw_and_reload_agent(self) -> None:
        self.store.save()
        if self._tw_reload_debounce is not None:
            GLib.source_remove(self._tw_reload_debounce)
        self._tw_reload_debounce = GLib.timeout_add(300, self._do_agent_reload)

    def _do_agent_reload(self) -> bool:
        self._tw_reload_debounce = None
        if self.window is not None and self.window.agent is not None:
            threading.Thread(
                target=self.window.agent.reload_profiles, daemon=True
            ).start()
        return False

    def _schedule_scroll_mode_write(self, msg: str) -> None:
        if self._ss_debounce is not None:
            GLib.source_remove(self._ss_debounce)
        self._ss_debounce = GLib.timeout_add(120, self._commit_scroll_mode, msg)

    def _commit_scroll_mode(self, msg: str) -> bool:
        self._ss_debounce = None
        mode = self._current_mode
        thr = int(self.ss_scale.get_value())
        torque = int(self.tq_scale.get_value())
        self._run_write(
            lambda: self.client.set_scroll_mode(mode, thr, torque, True),
            msg, "Failed to update scroll hardware",
        )
        return False

    # ─── handlers ───────────────────────────────────────────────────

    def _on_mode_toggled(self, btn, mode_id: str):
        if self._updating or not btn.get_active():
            return
        self._current_mode = mode_id
        self.ss_scale.set_sensitive(mode_id == "smart")
        label = {"smart": "SmartShift mode", "ratchet": "Ratchet-only mode", "free": "Free-spin mode"}[mode_id]
        self._commit_scroll_mode(f"Scroll set to {label}")

    def _on_ss_changed(self, scale):
        if self._updating:
            return
        thr = int(scale.get_value())
        self.ss_value.set_text(str(thr))
        if self._current_mode == "smart":
            self._schedule_scroll_mode_write(f"SmartShift threshold {thr}")

    def _on_torque_changed(self, scale):
        if self._updating:
            return
        tq = int(scale.get_value())
        self.tq_value.set_text(f"{tq}%")
        self._schedule_scroll_mode_write(f"Ratchet torque {tq}%")

    def _on_hires_toggle(self, sw, _):
        if self._updating:
            return
        on = sw.get_active()
        inv = self.inv_v_switch.get_active()
        self._run_write(
            lambda: self.client.set_hires(on, inv),
            "Hi-res scrolling " + ("enabled" if on else "disabled"),
            "Failed to set hi-res scrolling",
        )

    def _on_invert_v(self, sw, _):
        if self._updating:
            return
        inv = sw.get_active()
        on = self.hires_switch.get_active()
        self._run_write(
            lambda: self.client.set_hires(on, inv),
            "Vertical scroll " + ("inverted" if inv else "normal"),
            "Failed to set vertical scroll direction",
        )

    def _on_tw_divert(self, sw, _):
        if self._updating:
            return
        div = sw.get_active()
        inv = self.tw_invert_switch.get_active()
        self.tw_actions_card.set_sensitive(div)
        self.store.config.thumbwheel.diverted = div
        self._save_tw_and_reload_agent()
        self._run_write(
            lambda: self.client.set_thumbwheel(div, inv),
            "Thumb wheel " + ("custom actions enabled" if div else "native horizontal scroll"),
            "Failed to configure thumb wheel",
        )

    def _on_tw_invert(self, sw, _):
        if self._updating:
            return
        inv = sw.get_active()
        div = self.tw_divert_switch.get_active()
        self.store.config.thumbwheel.invert = inv
        self.store.save()
        self._run_write(
            lambda: self.client.set_thumbwheel(div, inv),
            "Thumb wheel " + ("inverted" if inv else "normal"),
            "Failed to invert thumb wheel",
        )

    def _on_tw_preset_changed(self, dd, _):
        if self._updating:
            return
        key = _TW_PRESET_KEYS[dd.get_selected()]
        _lbl, pt, pd, nt, nd = THUMBWHEEL_PRESETS[key]
        tw = self.store.config.thumbwheel
        tw.preset = key
        if key != "custom":
            tw.positive_type, tw.positive_data = pt, pd
            tw.negative_type, tw.negative_data = nt, nd
            type_map = {"keystroke": 0, "command": 1, "application": 2, "disabled": 3}
            self._updating = True
            try:
                self.tw_pos_type.set_selected(type_map.get(pt, 0))
                self.tw_pos_entry.set_text(pd)
                self.tw_neg_type.set_selected(type_map.get(nt, 0))
                self.tw_neg_entry.set_text(nd)
            finally:
                self._updating = False
        self._save_tw_and_reload_agent()

    def _on_tw_custom_changed(self, *_a):
        if self._updating:
            return
        types = ["keystroke", "command", "application", "disabled"]
        tw = self.store.config.thumbwheel
        tw.preset = "custom"
        tw.positive_type = types[self.tw_pos_type.get_selected()]
        tw.positive_data = self.tw_pos_entry.get_text().strip()
        tw.negative_type = types[self.tw_neg_type.get_selected()]
        tw.negative_data = self.tw_neg_entry.get_text().strip()
        self._updating = True
        try:
            self.tw_preset_dd.set_selected(_TW_PRESET_KEYS.index("custom"))
        finally:
            self._updating = False
        self._save_tw_and_reload_agent()

    def _on_tw_step_changed(self, scale):
        if self._updating:
            return
        val = int(scale.get_value())
        self.tw_step_val.set_text(str(val))
        self.store.config.thumbwheel.step = val
        self._save_tw_and_reload_agent()

    def _on_tw_haptic_toggle(self, sw, _):
        if self._updating:
            return
        self.store.config.thumbwheel.haptic_tick = sw.get_active()
        self._save_tw_and_reload_agent()
