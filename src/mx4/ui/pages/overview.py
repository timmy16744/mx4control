"""Device (Overview) page — live hardware status, DPI, friendly name, and Easy-Switch."""

from __future__ import annotations

import threading
from typing import Any, Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Pango", "1.0")
from gi.repository import Adw, GLib, Gtk, Pango

from ..widgets.common import page_title, section_title, stat_card
from ..widgets.mouse_svg import BUTTON_LABELS, MouseSVG
from ..widgets.rebind_dialog import RebindDialog
from ...common.dbus import DaemonUnavailable
from ...config import ButtonBinding, ConfigStore


DPI_PRESETS = [400, 800, 1000, 1200, 1600, 2400, 4000, 8000]


class OverviewPage(Gtk.Box):
    def __init__(self, client, *, window=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.client = client
        self.window = window
        self.store = ConfigStore()
        self._updating = False
        self._connected = False
        self._button_infos: dict[int, dict] = {}
        self._dpi_debounce: Optional[int] = None
        self._friendly_name: str = "MX Master 4"

        self.set_margin_top(4)
        self.set_margin_bottom(24)
        self.set_margin_start(4)
        self.set_margin_end(4)

        self.append(page_title("Device", "Live hardware status, pointer DPI, and Easy-Switch hosts."))

        # ─── Hero card ──────────────────────────────────────────────
        hero = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        hero.add_css_class("mx4-hero")
        hero.set_valign(Gtk.Align.FILL)
        self.append(hero)

        self.mouse_svg = MouseSVG(pixel_size=260, show_label=False)
        self.mouse_svg.set_valign(Gtk.Align.CENTER)
        self.mouse_svg.connect("button-clicked", self._on_mouse_button_clicked)
        hero.append(self.mouse_svg)

        hero_right = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=6,
            valign=Gtk.Align.CENTER, hexpand=True,
        )
        hero.append(hero_right)

        name_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        hero_right.append(name_row)

        self.name_label = Gtk.Label(label="MX Master 4", xalign=0)
        self.name_label.add_css_class("mx4-hero-name")
        name_row.append(self.name_label)

        self.rename_dev_btn = Gtk.Button.new_from_icon_name("document-edit-symbolic")
        self.rename_dev_btn.add_css_class("flat")
        self.rename_dev_btn.set_tooltip_text("Rename mouse (stored in hardware)")
        self.rename_dev_btn.connect("clicked", self._on_rename_device)
        name_row.append(self.rename_dev_btn)

        self.conn_label = Gtk.Label(label="Searching…", xalign=0)
        self.conn_label.add_css_class("mx4-hero-sub")
        self.conn_label.set_wrap(True)
        hero_right.append(self.conn_label)

        hint = Gtk.Label(
            label="Click any button on the mouse to configure · Live presses glow in real time",
            xalign=0,
        )
        hint.add_css_class("mx4-hero-sub")
        hint.set_opacity(0.75)
        hint.set_wrap(True)
        hero_right.append(hint)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, margin_top=10)
        hero_right.append(actions)

        self.test_btn = Gtk.Button(label="Test haptic")
        self.test_btn.add_css_class("mx4-btn-primary")
        self.test_btn.connect("clicked", self._on_test_haptic)
        actions.append(self.test_btn)

        self.id_btn = Gtk.Button(label="Identify mouse")
        self.id_btn.add_css_class("mx4-btn-ghost")
        self.id_btn.connect("clicked", self._on_identify)
        actions.append(self.id_btn)

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
        self.append(section_title("Pointer sensitivity"))
        dpi_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        dpi_card.add_css_class("mx4-card")
        self.append(dpi_card)

        dpi_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        dpi_card.append(dpi_row)
        title = Gtk.Label(label="Pointer DPI (200–8000, step 50)", xalign=0)
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

        chips_box = Gtk.FlowBox()
        chips_box.set_selection_mode(Gtk.SelectionMode.NONE)
        chips_box.set_column_spacing(6)
        chips_box.set_row_spacing(6)
        chips_box.set_max_children_per_line(8)
        chips_box.set_halign(Gtk.Align.CENTER)
        dpi_card.append(chips_box)
        self._preset_buttons: list[tuple[int, Gtk.ToggleButton]] = []
        for p in DPI_PRESETS:
            b = Gtk.ToggleButton(label=f"{p}")
            b.add_css_class("mx4-chip")
            b.connect("toggled", self._on_preset_toggled, p)
            chips_box.append(b)
            self._preset_buttons.append((p, b))

        # DPI cycle stages row
        cycle_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        dpi_card.append(cycle_row)
        cycle_lbl = Gtk.Label(
            label="DPI Cycle stages (for Cycle DPI button/ring action):",
            xalign=0,
        )
        cycle_lbl.add_css_class("mx4-card-sub")
        cycle_row.append(cycle_lbl)

        self.dpi_cycle_entry = Gtk.Entry(hexpand=True)
        self.dpi_cycle_entry.add_css_class("mx4-entry")
        self.dpi_cycle_entry.set_text(
            ", ".join(str(x) for x in self.store.config.pointer.dpi_presets)
        )
        self.dpi_cycle_entry.set_placeholder_text("800, 1200, 1600, 2400, 4000")
        self.dpi_cycle_entry.connect("activate", self._on_dpi_cycle_save)
        cycle_row.append(self.dpi_cycle_entry)

        save_cycle = Gtk.Button(label="Save")
        save_cycle.add_css_class("mx4-btn-ghost")
        save_cycle.connect("clicked", self._on_dpi_cycle_save)
        cycle_row.append(save_cycle)

        # ─── Easy-Switch hosts ──────────────────────────────────────
        self.append(section_title("Easy-Switch hosts"))
        self.hosts_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=10, homogeneous=True,
        )
        self.append(self.hosts_box)

        self.refresh()

    # ─── live signal hooks ──────────────────────────────────────────

    def set_pressed_cids(self, cids: set[int]) -> None:
        self.mouse_svg.set_pressed_cids(cids)

    def apply_state_delta(self, delta: dict[str, Any]) -> None:
        if "dpi" in delta and not self._updating:
            self._updating = True
            try:
                dpi = int(delta["dpi"])
                self.dpi_card.value_label.set_text(str(dpi))
                if int(self.dpi_spin.get_value()) != dpi:
                    self.dpi_spin.set_value(dpi)
                if int(self.dpi_slider.get_value()) != dpi:
                    self.dpi_slider.set_value(dpi)
                self._highlight_preset(dpi)
            finally:
                self._updating = False
        if "battery" in delta:
            self._update_battery_card(
                int(delta.get("battery", 0)),
                bool(delta.get("charging", False)),
                str(delta.get("battery_level_name", "")),
            )
        if "friendly_name" in delta:
            self._friendly_name = str(delta["friendly_name"])
            self.name_label.set_text(self._friendly_name)

    # ─── refresh ────────────────────────────────────────────────────

    def refresh(self) -> None:
        self._refresh_live()

    def _refresh_live(self) -> None:
        self.store.invalidate()
        bindings = [
            {"cid": b.cid, "action_type": b.action_type, "action_data": b.action_data}
            for b in self.store.config.button_bindings
        ]

        def fetch():
            try:
                state = self.client.get_state() or {}
                buttons = self.client.get_buttons() or []
                hosts = self.client.get_hosts() or []
            except DaemonUnavailable:
                state, buttons, hosts = {"connected": False, "daemon": False}, [], []
            except Exception:
                state, buttons, hosts = {"connected": False}, [], []
            GLib.idle_add(self._apply_state, state, buttons, bindings, hosts)
        threading.Thread(target=fetch, daemon=True).start()

    def _update_battery_card(self, battery: int, charging: bool, level_name: str = "") -> None:
        self.battery_card.value_label.set_text(str(battery))
        unit = "% · charging" if charging else (f"% · {level_name}" if level_name and level_name != "unknown" else "%")
        if hasattr(self.battery_card, "unit_label"):
            self.battery_card.unit_label.set_text(unit)
        for cls in ("mx4-batt-ok", "mx4-batt-low", "mx4-batt-crit"):
            self.battery_card.remove_css_class(cls)
        if charging:
            self.battery_card.add_css_class("mx4-batt-ok")
        elif battery <= 10:
            self.battery_card.add_css_class("mx4-batt-crit")
        elif battery <= 20:
            self.battery_card.add_css_class("mx4-batt-low")

    def _apply_state(
        self, state: dict, buttons: list[dict],
        bindings: list[dict] | None = None, hosts: list[dict] | None = None,
    ) -> bool:
        self._updating = True
        try:
            self._connected = bool(state.get("connected"))
            self._button_infos = {b["cid"]: b for b in buttons}
            remapped = {
                b["cid"] for b in buttons
                if b.get("remap_cid") and b["remap_cid"] not in (0, b["cid"])
            }
            for b in bindings or []:
                if b.get("action_type") not in (None, "default"):
                    remapped.add(b["cid"])
            self.mouse_svg.set_remapped_cids(remapped)

            self._set_controls_sensitive(self._connected)

            if not self._connected:
                self.name_label.set_text("MX Master 4")
                if state.get("daemon") is False:
                    self.conn_label.set_text("Disconnected · mx4-sysd service is not running")
                else:
                    self.conn_label.set_text("No MX Master 4 detected · wake mouse or check Bolt receiver")
                for c in (self.battery_card, self.dpi_card, self.transport_card, self.firmware_card):
                    c.value_label.set_text("—")
                self._render_hosts(None, -1)
                return False

            friendly = state.get("friendly_name") or state.get("name", "MX Master 4")
            self._friendly_name = str(friendly)
            self.name_label.set_text(self._friendly_name)

            transport = (state.get("connection") or "").title() or "Unknown"
            battery = int(state.get("battery", 0))
            charging = bool(state.get("charging"))
            level_name = str(state.get("battery_level_name", ""))
            sub = transport
            if charging:
                sub += " · charging"
            elif battery <= 20:
                sub += " · low battery"
            sub += f" · firmware {state.get('firmware', '—')}"
            self.conn_label.set_text(sub)

            self._update_battery_card(battery, charging, level_name)

            # DPI range from hardware
            dpi_min = int(state.get("dpi_min") or 200)
            dpi_max = int(state.get("dpi_max") or 8000)
            dpi_step = int(state.get("dpi_step") or 50)
            self.dpi_spin.set_range(dpi_min, dpi_max)
            self.dpi_spin.set_increments(dpi_step, dpi_step * 8)
            self.dpi_slider.set_range(dpi_min, dpi_max)

            dpi = int(state.get("dpi") or 1000)
            self.dpi_card.value_label.set_text(str(dpi))
            if int(self.dpi_spin.get_value()) != dpi:
                self.dpi_spin.set_value(dpi)
            if int(self.dpi_slider.get_value()) != dpi:
                self.dpi_slider.set_value(dpi)
            self._highlight_preset(dpi)

            self.transport_card.value_label.set_text(transport)
            self.firmware_card.value_label.set_text(state.get("firmware") or "—")

            self._render_hosts(hosts, int(state.get("current_host", -1)))
        finally:
            self._updating = False
        return False

    def _highlight_preset(self, dpi: int) -> None:
        for p, b in self._preset_buttons:
            b.set_active(p == dpi)

    def _set_controls_sensitive(self, on: bool) -> None:
        for w in (self.dpi_spin, self.dpi_slider, self.test_btn, self.id_btn, self.rename_dev_btn):
            w.set_sensitive(on)
        for _p, b in self._preset_buttons:
            b.set_sensitive(on)

    def _render_hosts(self, hosts: Optional[list[dict]], current: int = -1) -> None:
        child = self.hosts_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.hosts_box.remove(child)
            child = nxt

        if not hosts:
            return

        for h in hosts:
            idx = int(h.get("index", 0))
            paired = bool(h.get("paired", False))
            name = h.get("name") or (f"Slot {idx + 1}" if paired else "Empty")
            bus_label = h.get("bus_label") or ""
            is_current = bool(h.get("current", idx == current))
            can_rename = bool(h.get("can_rename", False))

            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            card.add_css_class("mx4-card")
            if is_current:
                card.add_css_class("mx4-host-active")

            top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            card.append(top)

            num = Gtk.Label(label=f"Slot {idx + 1}", xalign=0, hexpand=True)
            num.add_css_class("mx4-card-value-small")
            top.append(num)

            if bus_label and paired:
                bus = Gtk.Label(label=bus_label)
                bus.add_css_class("mx4-badge")
                top.append(bus)

            name_label = Gtk.Label(label=name, xalign=0)
            name_label.add_css_class("mx4-card-title")
            name_label.set_ellipsize(Pango.EllipsizeMode.END)
            name_label.set_max_width_chars(20)
            card.append(name_label)

            btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, margin_top=4)
            card.append(btn_row)

            if is_current:
                state_label = Gtk.Label(label="● Active on this PC", xalign=0, hexpand=True)
                state_label.add_css_class("mx4-host-active-label")
                btn_row.append(state_label)
            elif paired:
                btn = Gtk.Button(label="Switch to")
                btn.add_css_class("mx4-btn-ghost")
                btn.connect("clicked", lambda _b, i=idx: self._switch_host(i))
                btn_row.append(btn)
            else:
                card.set_sensitive(False)
                state_label = Gtk.Label(label="Unpaired", xalign=0)
                state_label.add_css_class("mx4-card-sub")
                btn_row.append(state_label)

            if paired and can_rename:
                ren = Gtk.Button.new_from_icon_name("document-edit-symbolic")
                ren.add_css_class("flat")
                ren.set_tooltip_text(f"Rename Slot {idx + 1}")
                ren.connect("clicked", lambda _b, i=idx, cur=name: self._on_rename_host(i, cur))
                btn_row.append(ren)

            self.hosts_box.append(card)

    # ─── helpers ────────────────────────────────────────────────────

    def _toast(self, message: str) -> None:
        if self.window is not None:
            self.window.toast(message)

    def _reload_agent(self) -> None:
        if self.window is not None and self.window.agent is not None:
            try:
                self.window.agent.reload_profiles()
            except Exception:
                pass

    def _run_write(self, fn, ok_msg: str, fail_msg: str, after=None) -> None:
        def worker():
            try:
                ok = fn()
                if ok_msg or not ok:
                    GLib.idle_add(self._toast, ok_msg if ok else fail_msg)
            except DaemonUnavailable:
                GLib.idle_add(self._toast, "mx4-sysd not running?")
            except Exception as e:
                GLib.idle_add(self._toast, f"{fail_msg}: {e}")
            if after is not None:
                GLib.idle_add(after)
        threading.Thread(target=worker, daemon=True).start()

    def _schedule_dpi_write(self, dpi: int) -> None:
        self.dpi_card.value_label.set_text(str(dpi))
        if self._dpi_debounce is not None:
            GLib.source_remove(self._dpi_debounce)
        self._dpi_debounce = GLib.timeout_add(120, self._commit_dpi, dpi)

    def _commit_dpi(self, dpi: int) -> bool:
        self._dpi_debounce = None
        self._run_write(
            lambda: self.client.set_dpi(dpi),
            f"DPI set to {dpi}", "Failed to set DPI",
        )
        return False

    # ─── input handlers ─────────────────────────────────────────────

    def _on_dpi_changed(self, spin):
        if self._updating:
            return
        dpi = int(round(spin.get_value() / 50) * 50)
        if int(self.dpi_slider.get_value()) != dpi:
            self._updating = True
            try:
                self.dpi_slider.set_value(dpi)
            finally:
                self._updating = False
        self._highlight_preset(dpi)
        self._schedule_dpi_write(dpi)

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
        self._schedule_dpi_write(dpi)

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
        self._commit_dpi(preset)

    def _on_dpi_cycle_save(self, *_a):
        raw = self.dpi_cycle_entry.get_text()
        vals = []
        for part in raw.replace(";", ",").split(","):
            part = part.strip()
            if part.isdigit():
                v = max(200, min(8000, int(part)))
                if v not in vals:
                    vals.append(v)
        if not vals:
            self._toast("Enter at least one valid DPI (200–8000)")
            return
        vals.sort()
        self.store.invalidate()
        self.store.config.pointer.dpi_presets = vals
        self.store.save()
        self.dpi_cycle_entry.set_text(", ".join(str(x) for x in vals))
        threading.Thread(target=self._reload_agent, daemon=True).start()
        self._toast(f"DPI cycle stages saved: {', '.join(str(x) for x in vals)}")

    def _on_test_haptic(self, _btn):
        self._run_write(
            lambda: self.client.trigger_haptic(2),
            "Haptic pulse played", "Failed to play haptic",
        )

    def _on_identify(self, _btn):
        self._run_write(
            lambda: self.client.trigger_haptic(10),
            "Identifying MX Master 4", "Failed to identify device",
        )

    def _on_rename_device(self, _btn):
        dlg = Adw.AlertDialog(
            heading="Rename mouse",
            body="Stored directly in the MX Master 4 firmware (max 14 characters).",
        )
        entry = Gtk.Entry(text=self._friendly_name, max_length=14)
        dlg.set_extra_child(entry)
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("save", "Save")
        dlg.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

        def on_resp(_d, resp):
            if resp == "save":
                new_name = entry.get_text().strip()
                if new_name:
                    self._run_write(
                        lambda: self.client.set_friendly_name(new_name),
                        f"Mouse renamed to {new_name}",
                        "Failed to rename mouse",
                        after=self._refresh_live,
                    )
        dlg.connect("response", on_resp)
        dlg.present(self.get_root())

    def _on_rename_host(self, idx: int, current_name: str):
        dlg = Adw.AlertDialog(
            heading=f"Rename Easy-Switch Slot {idx + 1}",
            body="Written to the mouse's HOSTS_INFO memory (max 24 characters).",
        )
        entry = Gtk.Entry(text=current_name, max_length=24)
        dlg.set_extra_child(entry)
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("save", "Save")
        dlg.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

        def on_resp(_d, resp):
            if resp == "save":
                new_name = entry.get_text().strip()
                if new_name:
                    self._run_write(
                        lambda: self.client.rename_host(idx, new_name),
                        f"Slot {idx + 1} renamed to {new_name}",
                        "Failed to rename host slot",
                        after=self._refresh_live,
                    )
        dlg.connect("response", on_resp)
        dlg.present(self.get_root())

    def _switch_host(self, idx: int):
        self._run_write(
            lambda: self.client.switch_host(idx),
            f"Switching to host slot {idx + 1}", "Failed to switch host",
            after=lambda: (GLib.timeout_add(500, self._refresh_after) or None),
        )

    def _refresh_after(self) -> bool:
        self._refresh_live()
        return False

    # ─── rebind dialog ──────────────────────────────────────────────

    def _on_mouse_button_clicked(self, _w, cid: int):
        info = self._button_infos.get(cid)
        label = BUTTON_LABELS.get(cid, f"CID 0x{cid:04X}")
        remappable = bool(info and info.get("remappable"))
        divertable = bool(info and info.get("divertable"))

        self.store.invalidate()
        current_type = "default"
        current_data = ""
        for b in self.store.config.button_bindings:
            if b.cid == cid:
                current_type = b.action_type
                current_data = b.action_data
                break
        if current_type == "default" and info:
            remap = info.get("remap_cid")
            if remap and remap not in (0, cid):
                current_type = "remap"
                current_data = str(remap)

        dialog = RebindDialog(
            button_label=label, cid=cid,
            current_action_type=current_type, current_action_data=current_data,
            remappable=remappable, divertable=divertable,
            on_apply=lambda at, ad: self._apply_binding(cid, at, ad, label),
        )
        dialog.present(self.get_root())

    def _apply_binding(self, cid: int, action_type: str, action_data: str, label: str) -> None:
        self.store.invalidate()
        bindings = self.store.config.button_bindings
        bindings[:] = [b for b in bindings if b.cid != cid]
        if action_type != "default":
            bindings.append(ButtonBinding(cid=cid, action_type=action_type, action_data=action_data))
        self.store.save()

        def device_op() -> bool:
            if action_type == "remap":
                try:
                    target = int(action_data)
                except (TypeError, ValueError):
                    target = 0
                ok = self.client.remap_button(cid, target)
            elif action_type == "default":
                ok = self.client.reset_button(cid)
            else:
                ok = self.client.divert_button(cid, True)
            self._reload_agent()
            return ok

        self._run_write(
            device_op,
            f"{label} → {action_type}", f"Failed to configure {label.lower()}",
            after=lambda: (GLib.timeout_add(300, self._refresh_after) or None),
        )
