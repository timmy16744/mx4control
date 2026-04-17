"""Scroll page.

Full granular control over the main wheel + thumb wheel:

* Scroll mode: SmartShift (auto) / Ratchet only / Free-spin.
* SmartShift threshold slider — how sensitive the auto-switch is.
* Hi-res scrolling toggle (smooth pixel-level scroll).
* Invert vertical + invert horizontal toggles.
* Thumb-wheel diversion (off = firmware does horizontal scroll,
  on = daemon captures events so they can be bound to custom actions).
* Thumb-wheel invert.

All settings are pushed to the daemon and persisted in TOML.
"""

from __future__ import annotations

import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

from ...config import ConfigStore


class ScrollPage(Adw.PreferencesPage):
    def __init__(self, client):
        super().__init__()
        self.client = client
        self.set_title("Scroll")
        self.set_icon_name("view-continuous-symbolic")

        self.store = ConfigStore()
        self.cfg = self.store.config.scroll
        self.tw_cfg = self.store.config.thumbwheel

        self._updating = False

        # ─── Scroll mode radio ────────────────────────────────────────
        mode_group = Adw.PreferencesGroup(
            title="Scroll mode",
            description="How the main wheel behaves when you flick it.",
        )
        self.add(mode_group)

        mode_row = Adw.ActionRow()
        mode_row.set_activatable(False)

        mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
                           homogeneous=True, hexpand=True)

        self._mode_buttons: dict[str, Gtk.ToggleButton] = {}
        modes = [
            ("smart",   "SmartShift",     "Auto-switch by flick speed"),
            ("ratchet", "Ratchet only",   "Notched, precise"),
            ("free",    "Free-spin",      "Smooth momentum"),
        ]
        group_root: Gtk.ToggleButton | None = None
        for mode_id, name, desc in modes:
            b = Gtk.ToggleButton()
            b.add_css_class("card")
            b.set_hexpand(True)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                          halign=Gtk.Align.CENTER,
                          margin_top=10, margin_bottom=10,
                          margin_start=6, margin_end=6)
            title = Gtk.Label(label=name)
            title.add_css_class("heading")
            col.append(title)
            sub = Gtk.Label(label=desc)
            sub.add_css_class("caption")
            sub.add_css_class("dim-label")
            sub.set_wrap(True)
            col.append(sub)
            b.set_child(col)
            if group_root is None:
                group_root = b
            else:
                b.set_group(group_root)
            b.set_active(self._current_mode() == mode_id)
            b.connect("toggled", self._on_mode_toggled, mode_id)
            self._mode_buttons[mode_id] = b
            mode_box.append(b)

        mode_row.set_child(mode_box)
        mode_group.add(mode_row)

        # SmartShift sensitivity
        ss_row = Adw.ActionRow(title="SmartShift threshold")
        ss_row.set_subtitle(
            "Lower values switch to free-spin at slower flick speeds"
        )
        self.ss_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 1, 50, 1
        )
        self.ss_scale.set_draw_value(True)
        self.ss_scale.set_value(self.cfg.smartshift_threshold)
        self.ss_scale.set_hexpand(True)
        self.ss_scale.set_size_request(240, -1)
        for mark in (1, 15, 30, 50):
            self.ss_scale.add_mark(mark, Gtk.PositionType.BOTTOM, str(mark))
        self.ss_scale.connect("value-changed", self._on_ss_changed)
        ss_row.add_suffix(self.ss_scale)
        mode_group.add(ss_row)

        # Hi-res toggle
        self.hires_row = Adw.SwitchRow(title="High-resolution scrolling")
        self.hires_row.set_subtitle("Smooth pixel-level scroll (may not work in all apps)")
        self.hires_row.set_active(self.cfg.hires_enabled)
        self.hires_row.connect("notify::active", self._on_hires_toggle)
        mode_group.add(self.hires_row)

        # ─── Direction group ──────────────────────────────────────────
        dir_group = Adw.PreferencesGroup(title="Scroll direction")
        self.add(dir_group)

        self.inv_v_row = Adw.SwitchRow(title="Invert vertical")
        self.inv_v_row.set_subtitle("Natural scrolling (up-flick scrolls down)")
        self.inv_v_row.set_active(self.cfg.invert_vertical)
        self.inv_v_row.connect("notify::active", self._on_invert_v)
        dir_group.add(self.inv_v_row)

        self.inv_h_row = Adw.SwitchRow(title="Invert horizontal")
        self.inv_h_row.set_subtitle("Flip the thumb wheel direction")
        self.inv_h_row.set_active(self.cfg.invert_horizontal)
        self.inv_h_row.connect("notify::active", self._on_invert_h)
        dir_group.add(self.inv_h_row)

        # ─── Thumb wheel group ────────────────────────────────────────
        tw_group = Adw.PreferencesGroup(
            title="Thumb wheel",
            description=(
                "The sideways wheel under the thumb. Enable diversion "
                "to capture events in software for custom bindings."
            ),
        )
        self.add(tw_group)

        self.tw_divert_row = Adw.SwitchRow(title="Divert to software")
        self.tw_divert_row.set_subtitle(
            "When off, firmware does horizontal scroll by default"
        )
        self.tw_divert_row.set_active(self.tw_cfg.diverted)
        self.tw_divert_row.connect("notify::active", self._on_tw_divert)
        tw_group.add(self.tw_divert_row)

        self.tw_invert_row = Adw.SwitchRow(title="Invert thumb wheel")
        self.tw_invert_row.set_subtitle("Flip the thumb-wheel direction")
        self.tw_invert_row.set_active(self.tw_cfg.invert)
        self.tw_invert_row.connect("notify::active", self._on_tw_invert)
        tw_group.add(self.tw_invert_row)

    # ─── helpers ────────────────────────────────────────────────────

    def _current_mode(self) -> str:
        if self.cfg.smartshift_enabled:
            return "smart"
        return "ratchet"  # "free" chosen explicitly via button

    def _save(self) -> None:
        self.store.save()

    # ─── handlers ───────────────────────────────────────────────────

    def _on_mode_toggled(self, btn, mode_id):
        if self._updating or not btn.get_active():
            return
        # Map UI mode onto HID++ setSmartShift:
        #   smart:   smartshift_enabled=True,  wheel_mode=ratchet, auto_disengage=threshold
        #   ratchet: smartshift_enabled=False, wheel_mode=ratchet, auto_disengage=0
        #   free:    smartshift_enabled=False, wheel_mode=freespin, auto_disengage=0
        enabled = mode_id == "smart"
        self.cfg.smartshift_enabled = enabled
        self._save()
        threshold = int(self.ss_scale.get_value())
        threading.Thread(
            target=lambda: self.client.set_smartshift(enabled, threshold),
            daemon=True,
        ).start()

    def _on_ss_changed(self, scale):
        if self._updating:
            return
        thr = int(scale.get_value())
        self.cfg.smartshift_threshold = thr
        self._save()
        # Only write to device when SmartShift is the active mode
        if self.cfg.smartshift_enabled:
            threading.Thread(
                target=lambda: self.client.set_smartshift(True, thr),
                daemon=True,
            ).start()

    def _on_hires_toggle(self, row, _):
        on = row.get_active()
        self.cfg.hires_enabled = on
        self._save()
        threading.Thread(
            target=lambda: self.client.call(
                "set_hires", enabled=on, invert=self.cfg.invert_vertical,
            ),
            daemon=True,
        ).start()

    def _on_invert_v(self, row, _):
        on = row.get_active()
        self.cfg.invert_vertical = on
        self._save()
        threading.Thread(
            target=lambda: self.client.call(
                "set_hires", enabled=self.cfg.hires_enabled, invert=on,
            ),
            daemon=True,
        ).start()

    def _on_invert_h(self, row, _):
        self.cfg.invert_horizontal = row.get_active()
        self._save()
        # Horizontal invert is handled by the thumb-wheel diversion path
        # when enabled, or by the compositor otherwise; no firmware call.

    def _on_tw_divert(self, row, _):
        on = row.get_active()
        self.tw_cfg.diverted = on
        self._save()
        threading.Thread(
            target=lambda: self.client.call(
                "set_thumbwheel_diverted",
                diverted=on, invert=self.tw_cfg.invert,
            ),
            daemon=True,
        ).start()

    def _on_tw_invert(self, row, _):
        self.tw_cfg.invert = row.get_active()
        self._save()
        if self.tw_cfg.diverted:
            threading.Thread(
                target=lambda: self.client.call(
                    "set_thumbwheel_diverted",
                    diverted=True, invert=self.tw_cfg.invert,
                ),
                daemon=True,
            ).start()
