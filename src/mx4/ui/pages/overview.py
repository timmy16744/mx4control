"""Device (Overview) page — live device status, DPI, and Easy-Switch."""

from __future__ import annotations

import threading
from typing import Any, Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

from ..widgets.common import section_title, page_title, stat_card
from ..widgets.mouse_svg import MouseSVG, BUTTON_LABELS
from ...hidpp import ControlID


DPI_PRESETS = [400, 800, 1000, 1600, 2000, 4000, 8000]

REMAP_TARGETS: list[tuple[str, Optional[int]]] = [
    ("Default (original function)", None),
    ("Left click",        ControlID.LEFT_CLICK),
    ("Right click",       ControlID.RIGHT_CLICK),
    ("Middle click",      ControlID.MIDDLE_CLICK),
    ("Back",              ControlID.BACK),
    ("Forward",           ControlID.FORWARD),
    ("SmartShift toggle", ControlID.SMART_SHIFT),
    ("Gesture button",    ControlID.GESTURE_BUTTON),
]

POLL_PRESSED_MS = 70


class OverviewPage(Gtk.Box):
    def __init__(self, client):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.client = client
        self._updating = False
        self._button_infos: dict[int, dict] = {}

        self.set_margin_top(4)
        self.set_margin_bottom(24)
        self.set_margin_start(4)
        self.set_margin_end(4)

        self.append(page_title("Device", "Live status, pointer settings, and paired hosts."))

        # ─── Hero card ──────────────────────────────────────────────
        hero = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        hero.add_css_class("mx4-hero")
        hero.set_valign(Gtk.Align.FILL)
        self.append(hero)

        # Left: big mouse preview
        self.mouse_svg = MouseSVG(pixel_size=190)
        self.mouse_svg.set_valign(Gtk.Align.CENTER)
        self.mouse_svg.connect("button-clicked", self._on_mouse_button_clicked)
        hero.append(self.mouse_svg)

        # Right: identity + quick actions
        hero_right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                             valign=Gtk.Align.CENTER, hexpand=True)
        hero.append(hero_right)

        self.name_label = Gtk.Label(label="MX Master 4", xalign=0)
        self.name_label.add_css_class("mx4-hero-name")
        hero_right.append(self.name_label)

        self.conn_label = Gtk.Label(label="Searching…", xalign=0)
        self.conn_label.add_css_class("mx4-hero-sub")
        self.conn_label.set_wrap(True)
        hero_right.append(self.conn_label)

        hint = Gtk.Label(
            label="Click any button above to remap it", xalign=0,
        )
        hint.add_css_class("mx4-hero-sub")
        hint.set_opacity(0.7)
        hero_right.append(hint)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
                          margin_top=10)
        hero_right.append(actions)

        test_btn = Gtk.Button(label="Test haptic")
        test_btn.add_css_class("mx4-btn-primary")
        test_btn.connect("clicked", self._on_test_haptic)
        actions.append(test_btn)

        id_btn = Gtk.Button(label="Identify device")
        id_btn.add_css_class("mx4-btn-ghost")
        id_btn.connect("clicked", self._on_identify)
        actions.append(id_btn)

        # ─── Status row (4 stat cards) ──────────────────────────────
        self.append(section_title("Device status"))

        stats_grid = Gtk.Grid()
        stats_grid.set_column_spacing(10)
        stats_grid.set_row_spacing(10)
        stats_grid.set_column_homogeneous(True)
        self.append(stats_grid)

        self.battery_card = stat_card("Battery", "—", "%", "battery-symbolic")
        self.dpi_card = stat_card("DPI", "—", "cpi", "input-tablet-symbolic")
        self.transport_card = stat_card("Transport", "—", "link", "network-wireless-symbolic")
        self.firmware_card = stat_card("Firmware", "—", "version", "emblem-system-symbolic")
        stats_grid.attach(self.battery_card,   0, 0, 1, 1)
        stats_grid.attach(self.dpi_card,       1, 0, 1, 1)
        stats_grid.attach(self.transport_card, 2, 0, 1, 1)
        stats_grid.attach(self.firmware_card,  3, 0, 1, 1)

        # ─── Pointer DPI controls ──────────────────────────────────
        self.append(section_title("Pointer"))
        dpi_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        dpi_card.add_css_class("mx4-card")
        self.append(dpi_card)

        dpi_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        dpi_card.append(dpi_row)
        title = Gtk.Label(label="Pointer speed", xalign=0)
        title.add_css_class("mx4-card-title")
        title.set_hexpand(True)
        dpi_row.append(title)

        self.dpi_spin = Gtk.SpinButton()
        self.dpi_spin.set_range(200, 8000)
        self.dpi_spin.set_increments(50, 400)
        self.dpi_spin.set_value(1000)
        self.dpi_spin.set_width_chars(6)
        self.dpi_spin.add_css_class("mx4-spin")
        self.dpi_spin.connect("value-changed", self._on_dpi_changed)
        dpi_row.append(self.dpi_spin)

        self.dpi_slider = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 200, 8000, 50,
        )
        self.dpi_slider.set_draw_value(False)
        self.dpi_slider.set_hexpand(True)
        self.dpi_slider.add_css_class("mx4-slider")
        self.dpi_slider.set_value(1000)
        self.dpi_slider.connect("value-changed", self._on_dpi_slider)
        dpi_card.append(self.dpi_slider)

        chips_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
                            halign=Gtk.Align.CENTER)
        dpi_card.append(chips_box)
        self._preset_buttons: list[tuple[int, Gtk.ToggleButton]] = []
        for p in DPI_PRESETS:
            b = Gtk.ToggleButton(label=f"{p}")
            b.add_css_class("mx4-chip")
            b.connect("toggled", self._on_preset_toggled, p)
            chips_box.append(b)
            self._preset_buttons.append((p, b))

        # ─── Easy-Switch hosts ──────────────────────────────────────
        self.append(section_title("Easy-Switch"))
        self.hosts_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10,
                                  homogeneous=True)
        self.append(self.hosts_box)

        # Initial + periodic refresh
        self.refresh()
        GLib.timeout_add_seconds(5, self._refresh_tick)
        GLib.timeout_add(POLL_PRESSED_MS, self._poll_pressed_tick)

    # ─── refresh ────────────────────────────────────────────────────

    def refresh(self) -> None:
        self._refresh_live()

    def _refresh_tick(self) -> bool:
        self._refresh_live()
        return True

    def _refresh_live(self) -> None:
        def fetch():
            try:
                state = self.client.state() or {}
                buttons = (self.client.call("get_buttons") or {}).get("result") or []
            except Exception:
                state = {"connected": False}
                buttons = []
            GLib.idle_add(self._apply_state, state, buttons)
        threading.Thread(target=fetch, daemon=True).start()

    def _poll_pressed_tick(self) -> bool:
        def fetch():
            try:
                r = self.client.call("get_pressed_buttons") or {}
                pressed = r.get("result") or []
            except Exception:
                pressed = []
            GLib.idle_add(self._apply_pressed, set(pressed))
        threading.Thread(target=fetch, daemon=True).start()
        return True

    def _apply_pressed(self, cids: set[int]) -> bool:
        self.mouse_svg.set_pressed_cids(cids)
        return False

    def _apply_state(self, state: dict, buttons: list[dict]) -> bool:
        self._updating = True
        try:
            self._button_infos = {b["cid"]: b for b in buttons}
            remapped = {
                b["cid"] for b in buttons
                if b.get("remap_cid") and b["remap_cid"] not in (0, b["cid"])
            }
            self.mouse_svg.set_remapped_cids(remapped)

            if not state.get("connected"):
                self.name_label.set_text("MX Master 4")
                self.conn_label.set_text(
                    "Disconnected. Is the daemon running?"
                )
                for c in (self.battery_card, self.dpi_card, self.transport_card,
                          self.firmware_card):
                    c.value_label.set_text("—")
                for c in (self.battery_card,):
                    c.remove_css_class("mx4-batt-ok")
                    c.remove_css_class("mx4-batt-low")
                    c.remove_css_class("mx4-batt-crit")
                self._render_hosts(None)
                return False

            name = state.get("friendly_name") or state.get("name", "MX Master 4")
            self.name_label.set_text(name)

            transport = (state.get("connection") or "").title() or "Unknown"
            battery = state.get("battery", 0)
            charging = state.get("charging")
            sub = transport
            if charging:
                sub += " · charging"
            elif battery <= 20:
                sub += " · low battery"
            sub += f" · firmware {state.get('firmware', '—')}"
            self.conn_label.set_text(sub)

            # Stats
            self.battery_card.value_label.set_text(str(battery))
            self.battery_card.remove_css_class("mx4-batt-ok")
            self.battery_card.remove_css_class("mx4-batt-low")
            self.battery_card.remove_css_class("mx4-batt-crit")
            if charging:
                self.battery_card.add_css_class("mx4-batt-ok")
            elif battery <= 10:
                self.battery_card.add_css_class("mx4-batt-crit")
            elif battery <= 20:
                self.battery_card.add_css_class("mx4-batt-low")

            dpi = int(state.get("dpi") or 1000)
            self.dpi_card.value_label.set_text(str(dpi))
            if int(self.dpi_spin.get_value()) != dpi:
                self.dpi_spin.set_value(dpi)
            if int(self.dpi_slider.get_value()) != dpi:
                self.dpi_slider.set_value(dpi)
            self._highlight_preset(dpi)

            self.transport_card.value_label.set_text(transport)
            self.firmware_card.value_label.set_text(state.get("firmware") or "—")

            self._render_hosts(state.get("hosts"))
        finally:
            self._updating = False
        return False

    def _highlight_preset(self, dpi: int) -> None:
        for p, b in self._preset_buttons:
            b.set_active(p == dpi)

    def _render_hosts(self, hosts: Optional[dict]) -> None:
        # Clear
        child = self.hosts_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.hosts_box.remove(child)
            child = nxt

        if not hosts:
            return

        current = hosts.get("current_host", -1)
        for h in hosts.get("hosts", []):
            idx = h.get("index", 0)
            paired = h.get("paired", False)
            name = h.get("name") or (f"Slot {idx + 1}" if paired else "Empty")

            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            card.add_css_class("mx4-card")
            num = Gtk.Label(label=f"{idx + 1}", xalign=0)
            num.add_css_class("mx4-card-value")
            card.append(num)
            name_label = Gtk.Label(label=name, xalign=0)
            name_label.add_css_class("mx4-card-title")
            name_label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
            name_label.set_max_width_chars(18)
            card.append(name_label)

            if idx == current:
                state_label = Gtk.Label(label="Active on this machine", xalign=0)
                state_label.add_css_class("mx4-card-sub")
                card.append(state_label)
            elif paired:
                btn = Gtk.Button(label="Switch to")
                btn.add_css_class("mx4-btn-ghost")
                btn.set_halign(Gtk.Align.START)
                btn.connect("clicked", lambda _b, i=idx: self._switch_host(i))
                card.append(btn)
            else:
                card.set_sensitive(False)
                state_label = Gtk.Label(label="Unpaired", xalign=0)
                state_label.add_css_class("mx4-card-sub")
                card.append(state_label)

            self.hosts_box.append(card)

    # ─── input handlers ─────────────────────────────────────────────

    def _on_dpi_changed(self, spin):
        if self._updating:
            return
        dpi = int(spin.get_value())
        if int(self.dpi_slider.get_value()) != dpi:
            self._updating = True
            try:
                self.dpi_slider.set_value(dpi)
            finally:
                self._updating = False
        self._highlight_preset(dpi)
        threading.Thread(
            target=lambda: self.client.set_dpi(dpi), daemon=True,
        ).start()
        self.dpi_card.value_label.set_text(str(dpi))

    def _on_dpi_slider(self, scale):
        if self._updating:
            return
        dpi = int(round(scale.get_value() / 50) * 50)
        if int(self.dpi_spin.get_value()) != dpi:
            self._updating = True
            try:
                self.dpi_spin.set_value(dpi)
            finally:
                self._updating = False
        self._highlight_preset(dpi)
        threading.Thread(
            target=lambda: self.client.set_dpi(dpi), daemon=True,
        ).start()
        self.dpi_card.value_label.set_text(str(dpi))

    def _on_preset_toggled(self, btn, preset):
        if self._updating or not btn.get_active():
            return
        self._updating = True
        try:
            self.dpi_spin.set_value(preset)
            self.dpi_slider.set_value(preset)
            for p, b in self._preset_buttons:
                b.set_active(p == preset)
        finally:
            self._updating = False
        self.dpi_card.value_label.set_text(str(preset))
        threading.Thread(
            target=lambda: self.client.set_dpi(preset), daemon=True,
        ).start()

    def _on_test_haptic(self, _btn):
        threading.Thread(
            target=lambda: self.client.trigger_haptic(2), daemon=True,
        ).start()

    def _on_identify(self, _btn):
        threading.Thread(
            target=lambda: self.client.call("identify"), daemon=True,
        ).start()

    def _switch_host(self, idx: int):
        threading.Thread(
            target=lambda: self.client.switch_host(idx), daemon=True,
        ).start()

    # ─── remap dialog ───────────────────────────────────────────────

    def _on_mouse_button_clicked(self, _w, cid: int):
        info = self._button_infos.get(cid)
        label = BUTTON_LABELS.get(cid, f"CID 0x{cid:04X}")
        remappable = bool(info and info.get("remappable"))

        dialog = Adw.AlertDialog(
            heading=f"Remap {label.lower()} button",
            body=(
                "Pick a new action. “Default” restores the firmware's original behaviour."
                if remappable else
                "This button is firmware-locked and can't be remapped."
            ),
        )
        dialog.add_response("cancel", "Cancel")

        if remappable:
            current_remap = info.get("remap_cid") if info else 0
            current_is_default = current_remap in (0, cid)

            list_box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            list_box.add_css_class("boxed-list")

            group_root: Optional[Gtk.CheckButton] = None
            for text, target_cid in REMAP_TARGETS:
                if target_cid == cid:
                    continue
                row = Adw.ActionRow(title=text)
                check = Gtk.CheckButton()
                if group_root is None:
                    group_root = check
                else:
                    check.set_group(group_root)
                active = (
                    (target_cid is None and current_is_default)
                    or (target_cid is not None and target_cid == current_remap)
                )
                check.set_active(active)
                check.cid = target_cid  # type: ignore[attr-defined]
                row.add_prefix(check)
                row.set_activatable_widget(check)
                list_box.append(row)

            dialog.add_response("apply", "Apply")
            dialog.set_response_appearance("apply", Adw.ResponseAppearance.SUGGESTED)
            dialog.set_extra_child(list_box)

            def on_response(_d, response):
                if response != "apply":
                    return
                # Walk the list-box to find the active radio
                row = list_box.get_first_child()
                while row is not None:
                    pending = [row]
                    while pending:
                        w = pending.pop()
                        if isinstance(w, Gtk.CheckButton) and w.get_active():
                            tid = getattr(w, "cid", None)
                            self._apply_remap(cid, tid)
                            return
                        sibling = w.get_next_sibling()
                        if sibling:
                            pending.append(sibling)
                        first = w.get_first_child()
                        if first:
                            pending.append(first)
                    row = row.get_next_sibling()

            dialog.connect("response", on_response)

        dialog.present(self.get_root())

    def _apply_remap(self, cid: int, target_cid: Optional[int]) -> None:
        target = target_cid if target_cid is not None else cid
        threading.Thread(
            target=lambda: self.client.call(
                "remap_button", cid=cid, target_cid=target,
            ),
            daemon=True,
        ).start()
        GLib.timeout_add(300, lambda: (self._refresh_live() or False))
