"""Overview page — live device status, battery, hosts, quick settings.

All state comes from the daemon over IPC. No direct HID++ calls here.
"""

from __future__ import annotations

import threading
from typing import Any

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

from ..widgets.mouse_svg import MouseSVG


class OverviewPage(Adw.PreferencesPage):
    def __init__(self, client):
        super().__init__()
        self.client = client

        self.set_title("Device")
        self.set_icon_name("input-mouse-symbolic")

        # ─── Hero group: preview + connection status ───────────────
        hero = Adw.PreferencesGroup()
        self.add(hero)

        hero_row = Adw.ActionRow()
        self.mouse_svg = MouseSVG(pixel_size=160)
        hero_row.add_prefix(self.mouse_svg)

        self.name_label = Gtk.Label(label="MX Master 4")
        self.name_label.add_css_class("title-2")
        self.name_label.set_halign(Gtk.Align.START)

        self.conn_label = Gtk.Label(label="Searching…")
        self.conn_label.add_css_class("dim-label")
        self.conn_label.set_halign(Gtk.Align.START)

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                      valign=Gtk.Align.CENTER)
        col.append(self.name_label)
        col.append(self.conn_label)
        hero_row.set_child(col)
        hero.add(hero_row)

        # ─── Live stats group ────────────────────────────────────────
        stats = Adw.PreferencesGroup(title="Status")
        self.add(stats)

        self.battery_row = Adw.ActionRow(title="Battery", subtitle="—")
        stats.add(self.battery_row)

        self.firmware_row = Adw.ActionRow(title="Firmware", subtitle="—")
        stats.add(self.firmware_row)

        self.dpi_row = Adw.ActionRow(title="Pointer DPI", subtitle="—")
        stats.add(self.dpi_row)

        # DPI adjuster (talks to daemon)
        self.dpi_spin = Gtk.SpinButton()
        self.dpi_spin.set_range(200, 8000)
        self.dpi_spin.set_increments(50, 400)
        self.dpi_spin.set_value(1000)
        self.dpi_spin.set_valign(Gtk.Align.CENTER)
        self.dpi_spin.connect("value-changed", self._on_dpi_changed)
        self.dpi_row.add_suffix(self.dpi_spin)

        # SmartShift toggle
        self.ss_row = Adw.SwitchRow(title="SmartShift")
        self.ss_row.set_subtitle("Auto-freewheel on fast scroll")
        self.ss_row.connect("notify::active", self._on_ss_toggled)
        stats.add(self.ss_row)

        # ─── Hosts group ─────────────────────────────────────────────
        self.hosts_group = Adw.PreferencesGroup(title="Easy-Switch")
        self.hosts_group.set_description("Switch the mouse between paired devices")
        self.add(self.hosts_group)

        self._host_rows: list[Adw.ActionRow] = []

        # Refresh button at the bottom
        self._updating = False
        self._refresh_live()
        GLib.timeout_add_seconds(5, self._refresh_tick)

    # ─── refresh loop ─────────────────────────────────────────────────

    def _refresh_tick(self) -> bool:
        self._refresh_live()
        return True

    def _refresh_live(self) -> None:
        def fetch():
            try:
                state = self.client.state()
            except Exception as e:
                state = {"connected": False, "error": str(e)}
            GLib.idle_add(self._apply_state, state)

        threading.Thread(target=fetch, daemon=True).start()

    def _apply_state(self, state: dict) -> bool:
        self._updating = True
        try:
            if not state.get("connected"):
                self.name_label.set_text("MX Master 4")
                self.conn_label.set_text("Disconnected — mx4d not running?")
                self.battery_row.set_subtitle("—")
                self.firmware_row.set_subtitle("—")
                self.dpi_row.set_subtitle("—")
                return False

            name = state.get("friendly_name") or state.get("name", "MX Master 4")
            self.name_label.set_text(name)

            transport = (state.get("connection") or "").title() or "Unknown"
            charging = state.get("charging")
            battery = state.get("battery", 0)
            self.conn_label.set_text(
                f"{transport}"
                + (" · charging" if charging else "")
                + (" · low battery" if battery <= 20 and not charging else "")
            )

            batt_suffix = f"{battery}%"
            if charging:
                batt_suffix += " (charging)"
            elif battery <= 20:
                batt_suffix += " (low)"
            self.battery_row.set_subtitle(batt_suffix)

            self.firmware_row.set_subtitle(state.get("firmware") or "—")
            dpi = state.get("dpi", 1000)
            self.dpi_row.set_subtitle(f"{dpi} DPI")
            if int(self.dpi_spin.get_value()) != dpi:
                self.dpi_spin.set_value(dpi)

            self.ss_row.set_active(state.get("smartshift", True))

            self._render_hosts(state.get("hosts"))
        finally:
            self._updating = False
        return False

    def _render_hosts(self, hosts: dict | None) -> None:
        for r in self._host_rows:
            self.hosts_group.remove(r)
        self._host_rows.clear()

        if not hosts:
            return

        current = hosts.get("current_host", -1)
        for h in hosts.get("hosts", []):
            idx = h.get("index", 0)
            paired = h.get("paired", False)
            name = h.get("name") or (f"Slot {idx + 1}" if paired else "Empty")
            row = Adw.ActionRow(title=name)
            if idx == current:
                row.set_subtitle("Active")
                row.add_css_class("success")
            elif paired:
                btn = Gtk.Button(label="Switch to")
                btn.add_css_class("flat")
                btn.set_valign(Gtk.Align.CENTER)
                btn.connect("clicked", lambda _b, i=idx: self._switch_host(i))
                row.add_suffix(btn)
            else:
                row.set_subtitle("Empty")
                row.set_sensitive(False)
            self.hosts_group.add(row)
            self._host_rows.append(row)

    # ─── event handlers ────────────────────────────────────────────────

    def _on_dpi_changed(self, spin):
        if self._updating:
            return
        dpi = int(spin.get_value())
        threading.Thread(
            target=lambda: self.client.set_dpi(dpi),
            daemon=True,
        ).start()

    def _on_ss_toggled(self, row, _pspec):
        if self._updating:
            return
        threading.Thread(
            target=lambda: self.client.set_smartshift(row.get_active()),
            daemon=True,
        ).start()

    def _switch_host(self, idx: int):
        threading.Thread(
            target=lambda: self.client.switch_host(idx),
            daemon=True,
        ).start()
