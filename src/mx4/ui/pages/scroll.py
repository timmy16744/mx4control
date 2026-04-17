"""Scroll page — SmartShift, hi-res, direction, thumb wheel."""

from __future__ import annotations

import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

from ..widgets.common import section_title, page_title, setting_row
from ...config import ConfigStore


MODES = [
    ("smart",   "SmartShift",    "Auto-switch by flick speed"),
    ("ratchet", "Ratchet only",  "Notched, precise"),
    ("free",    "Free-spin",     "Smooth momentum"),
]


class ScrollPage(Gtk.Box):
    def __init__(self, client):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.client = client
        self.store = ConfigStore()
        self.cfg = self.store.config.scroll
        self.tw_cfg = self.store.config.thumbwheel
        self._updating = False

        self.set_margin_top(4)
        self.set_margin_bottom(24)

        self.append(page_title(
            "Scroll",
            "Control the main wheel, SmartShift, and the thumb wheel."
        ))

        # ─── Mode group ─────────────────────────────────────────────
        self.append(section_title("Scroll mode"))
        modes_grid = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10,
                             homogeneous=True)
        self.append(modes_grid)

        self._mode_buttons: dict[str, Gtk.ToggleButton] = {}
        group_root: Gtk.ToggleButton | None = None
        current_mode = "smart" if self.cfg.smartshift_enabled else "ratchet"

        for mode_id, name, desc in MODES:
            b = Gtk.ToggleButton()
            b.add_css_class("mx4-mode")
            b.set_hexpand(True)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                          halign=Gtk.Align.CENTER,
                          margin_top=4, margin_bottom=4)
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
            b.set_active(mode_id == current_mode)
            b.connect("toggled", self._on_mode_toggled, mode_id)
            self._mode_buttons[mode_id] = b
            modes_grid.append(b)

        # SmartShift threshold
        ss_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        ss_card.add_css_class("mx4-card")
        self.append(ss_card)

        ss_head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        ss_card.append(ss_head)
        ss_title = Gtk.Label(label="SmartShift threshold", xalign=0)
        ss_title.add_css_class("mx4-card-title")
        ss_title.set_hexpand(True)
        ss_head.append(ss_title)
        self.ss_value = Gtk.Label(label=str(self.cfg.smartshift_threshold), xalign=1)
        self.ss_value.add_css_class("mx4-card-value-small")
        ss_head.append(self.ss_value)

        ss_sub = Gtk.Label(
            label="Lower values switch to free-spin at slower flick speeds.",
            xalign=0,
        )
        ss_sub.add_css_class("mx4-card-sub")
        ss_sub.set_wrap(True)
        ss_card.append(ss_sub)

        self.ss_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 1, 50, 1,
        )
        self.ss_scale.add_css_class("mx4-slider")
        self.ss_scale.set_draw_value(False)
        self.ss_scale.set_hexpand(True)
        self.ss_scale.set_value(self.cfg.smartshift_threshold)
        for mark in (1, 15, 30, 50):
            self.ss_scale.add_mark(mark, Gtk.PositionType.BOTTOM, str(mark))
        self.ss_scale.connect("value-changed", self._on_ss_changed)
        ss_card.append(self.ss_scale)

        # Hi-res toggle
        self.hires_switch = Gtk.Switch(active=self.cfg.hires_enabled)
        self.hires_switch.connect("notify::active", self._on_hires_toggle)
        self.append(setting_row(
            "High-resolution scrolling",
            "Smooth pixel-level scroll. Requires app support.",
            self.hires_switch,
        ))

        # ─── Direction ─────────────────────────────────────────────
        self.append(section_title("Direction"))

        self.inv_v_switch = Gtk.Switch(active=self.cfg.invert_vertical)
        self.inv_v_switch.connect("notify::active", self._on_invert_v)
        self.append(setting_row(
            "Invert vertical",
            "Natural scrolling (up-flick scrolls content down).",
            self.inv_v_switch,
        ))

        self.inv_h_switch = Gtk.Switch(active=self.cfg.invert_horizontal)
        self.inv_h_switch.connect("notify::active", self._on_invert_h)
        self.append(setting_row(
            "Invert horizontal",
            "Flip the thumb-wheel direction.",
            self.inv_h_switch,
        ))

        # ─── Thumb wheel ────────────────────────────────────────────
        self.append(section_title("Thumb wheel"))

        self.tw_divert_switch = Gtk.Switch(active=self.tw_cfg.diverted)
        self.tw_divert_switch.connect("notify::active", self._on_tw_divert)
        self.append(setting_row(
            "Divert to software",
            "When off, firmware does horizontal scroll by default.",
            self.tw_divert_switch,
        ))

        self.tw_invert_switch = Gtk.Switch(active=self.tw_cfg.invert)
        self.tw_invert_switch.connect("notify::active", self._on_tw_invert)
        self.append(setting_row(
            "Invert thumb wheel",
            "Flip direction even when firmware is handling it.",
            self.tw_invert_switch,
        ))

    # ─── handlers ───────────────────────────────────────────────────

    def _save(self) -> None:
        self.store.save()

    def _on_mode_toggled(self, btn, mode_id):
        if self._updating or not btn.get_active():
            return
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
        self.ss_value.set_text(str(thr))
        self.cfg.smartshift_threshold = thr
        self._save()
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
