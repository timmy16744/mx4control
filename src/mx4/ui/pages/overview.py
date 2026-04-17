"""Overview / Device page.

Shows live mouse state plus quick-access controls. The mouse widget on
the left lights up in real time as physical buttons are pressed (polled
from the daemon every ~80 ms), and clicking a button on it opens a
remap dialog.

All state comes from the daemon over IPC — the GUI never opens hidraw.
"""

from __future__ import annotations

import threading
from typing import Any, Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

from ..widgets.mouse_svg import MouseSVG, BUTTON_LABELS
from ...hidpp import ControlID


# DPI presets shown as one-click chips. The mouse supports 200–8000,
# we offer the common values.
DPI_PRESETS = [400, 800, 1000, 1600, 2000, 4000, 8000]

# Remap targets presented in the dialog. Only includes CIDs with
# sensible default firmware behaviour; picking "Default" clears the
# remap so the button resumes its original function.
REMAP_TARGETS: list[tuple[str, Optional[int]]] = [
    ("Default (original function)", None),
    ("Left click", ControlID.LEFT_CLICK),
    ("Right click", ControlID.RIGHT_CLICK),
    ("Middle click", ControlID.MIDDLE_CLICK),
    ("Back", ControlID.BACK),
    ("Forward", ControlID.FORWARD),
    ("SmartShift toggle", ControlID.SMART_SHIFT),
    ("Gesture button", ControlID.GESTURE_BUTTON),
]

POLL_PRESSED_MS = 80  # ≈12 polls/s — imperceptible latency, no CPU cost


class OverviewPage(Adw.PreferencesPage):
    def __init__(self, client):
        super().__init__()
        self.client = client

        self.set_title("Device")
        self.set_icon_name("input-mouse-symbolic")

        self._updating = False

        # ─── Hero group: preview + name + connection ──────────────
        hero = Adw.PreferencesGroup()
        self.add(hero)

        hero_row = Adw.ActionRow()
        hero_row.set_activatable(False)

        self.mouse_svg = MouseSVG(pixel_size=160)
        self.mouse_svg.connect("button-clicked", self._on_mouse_button_clicked)
        hero_row.add_prefix(self.mouse_svg)

        self.name_label = Gtk.Label(label="MX Master 4")
        self.name_label.add_css_class("title-2")
        self.name_label.set_halign(Gtk.Align.START)

        self.conn_label = Gtk.Label(label="Searching…")
        self.conn_label.add_css_class("dim-label")
        self.conn_label.set_halign(Gtk.Align.START)
        self.conn_label.set_wrap(True)

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                      valign=Gtk.Align.CENTER)
        col.append(self.name_label)
        col.append(self.conn_label)

        # Quick actions: test haptic + identify
        quick = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        quick.set_margin_top(6)
        test_haptic = Gtk.Button(label="Test haptic")
        test_haptic.add_css_class("pill")
        test_haptic.connect("clicked", self._on_test_haptic)
        quick.append(test_haptic)
        identify = Gtk.Button(label="Identify")
        identify.add_css_class("pill")
        identify.connect("clicked", self._on_identify)
        quick.append(identify)
        col.append(quick)

        hero_row.set_child(col)
        hero.add(hero_row)

        # ─── Status group ────────────────────────────────────────────
        status = Adw.PreferencesGroup(title="Status")
        self.add(status)

        self.battery_row = Adw.ActionRow(title="Battery", subtitle="—")
        status.add(self.battery_row)
        self.firmware_row = Adw.ActionRow(title="Firmware", subtitle="—")
        status.add(self.firmware_row)
        self.transport_row = Adw.ActionRow(title="Transport", subtitle="—")
        status.add(self.transport_row)
        self.protocol_row = Adw.ActionRow(title="Protocol", subtitle="HID++ 2.0")
        status.add(self.protocol_row)

        # ─── Pointer / DPI group ─────────────────────────────────────
        ptr = Adw.PreferencesGroup(title="Pointer")
        self.add(ptr)

        self.dpi_row = Adw.ActionRow(title="DPI")
        self.dpi_spin = Gtk.SpinButton()
        self.dpi_spin.set_range(200, 8000)
        self.dpi_spin.set_increments(50, 400)
        self.dpi_spin.set_value(1000)
        self.dpi_spin.set_valign(Gtk.Align.CENTER)
        self.dpi_spin.set_width_chars(6)
        self.dpi_spin.connect("value-changed", self._on_dpi_changed)
        self.dpi_row.add_suffix(self.dpi_spin)
        ptr.add(self.dpi_row)

        # Preset chip row
        preset_row = Adw.ActionRow(title="Presets")
        chips_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4,
                            valign=Gtk.Align.CENTER)
        self._preset_buttons: list[tuple[int, Gtk.ToggleButton]] = []
        for p in DPI_PRESETS:
            b = Gtk.ToggleButton(label=f"{p}")
            b.add_css_class("pill")
            b.connect("toggled", self._on_preset_toggled, p)
            chips_box.append(b)
            self._preset_buttons.append((p, b))
        preset_row.add_suffix(chips_box)
        ptr.add(preset_row)

        # ─── Hosts group ─────────────────────────────────────────────
        self.hosts_group = Adw.PreferencesGroup(title="Easy-Switch")
        self.hosts_group.set_description(
            "Switch the mouse between paired devices"
        )
        self.add(self.hosts_group)
        self._host_rows: list[Adw.ActionRow] = []

        # ─── Initial load + periodic refresh ─────────────────────────
        self._refresh_live()
        GLib.timeout_add_seconds(5, self._refresh_tick)
        GLib.timeout_add(POLL_PRESSED_MS, self._poll_pressed_tick)

        self._button_infos: dict[int, dict] = {}

    # ─── periodic refresh ────────────────────────────────────────────

    def _refresh_tick(self) -> bool:
        self._refresh_live()
        return True

    def _refresh_live(self) -> None:
        def fetch():
            try:
                state = self.client.state()
                buttons = self.client.call("get_buttons").get("result") or []
            except Exception as e:
                state = {"connected": False, "error": str(e)}
                buttons = []
            GLib.idle_add(self._apply_state, state, buttons)

        threading.Thread(target=fetch, daemon=True).start()

    def _poll_pressed_tick(self) -> bool:
        def fetch():
            try:
                pressed = self.client.call("get_pressed_buttons").get("result") or []
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
            # Store button metadata keyed by CID for the remap dialog
            self._button_infos = {b["cid"]: b for b in buttons}
            remapped = {
                b["cid"] for b in buttons
                if b["remap_cid"] and b["remap_cid"] != b["cid"] and b["cid"] != 0
            }
            self.mouse_svg.set_remapped_cids(remapped)

            if not state.get("connected"):
                self.name_label.set_text("MX Master 4")
                self.conn_label.set_text(
                    "Disconnected. Is mx4d running? "
                    "systemctl --user status mx4d"
                )
                self.battery_row.set_subtitle("—")
                self.firmware_row.set_subtitle("—")
                self.transport_row.set_subtitle("—")
                self.dpi_row.set_subtitle("Unavailable")
                self._render_hosts(None)
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
            self.transport_row.set_subtitle(transport)

            dpi = int(state.get("dpi") or 1000)
            if int(self.dpi_spin.get_value()) != dpi:
                self.dpi_spin.set_value(dpi)
            self.dpi_row.set_subtitle(f"{dpi} cpi")
            self._highlight_preset(dpi)

            self._render_hosts(state.get("hosts"))
        finally:
            self._updating = False
        return False

    def _highlight_preset(self, dpi: int) -> None:
        self._updating = True
        try:
            for p, b in self._preset_buttons:
                b.set_active(p == dpi)
        finally:
            self._updating = False

    def _render_hosts(self, hosts: Optional[dict]) -> None:
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
        self._highlight_preset(dpi)
        threading.Thread(
            target=lambda: self.client.set_dpi(dpi), daemon=True,
        ).start()
        self.dpi_row.set_subtitle(f"{dpi} cpi")

    def _on_preset_toggled(self, btn, preset):
        if self._updating:
            return
        if not btn.get_active():
            # Prevent deactivating the current preset — the spin button
            # owns the exact value when a preset is toggled off
            return
        self._highlight_preset(preset)
        self.dpi_spin.set_value(preset)  # triggers _on_dpi_changed

    def _on_test_haptic(self, _btn):
        threading.Thread(
            target=lambda: self.client.trigger_haptic(2),
            daemon=True,
        ).start()

    def _on_identify(self, _btn):
        threading.Thread(
            target=lambda: self.client.call("identify"),
            daemon=True,
        ).start()

    def _switch_host(self, idx: int):
        threading.Thread(
            target=lambda: self.client.switch_host(idx),
            daemon=True,
        ).start()

    # ─── click-to-remap ────────────────────────────────────────────────

    def _on_mouse_button_clicked(self, _widget, cid: int):
        info = self._button_infos.get(cid)
        label = BUTTON_LABELS.get(cid, f"CID 0x{cid:04X}")
        remappable = bool(info and info.get("remappable"))

        dialog = Adw.AlertDialog(
            heading=f"Remap '{label}'",
            body=(
                "Pick a new action for this button. "
                "Default restores the original firmware behaviour."
                if remappable else
                "This button can't be remapped — the firmware reserves it "
                "for the listed action."
            ),
        )
        dialog.add_response("cancel", "Cancel")

        if remappable:
            # Radio-button list of targets
            group = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
            group.add_css_class("boxed-list")
            selected_row: list[int] = []  # mutable holder for closure
            current_remap = info.get("remap_cid") if info else 0
            current_is_default = current_remap in (0, cid)

            for label_text, target_cid in REMAP_TARGETS:
                if target_cid == cid:
                    continue  # don't offer the button's own CID
                row = Adw.ActionRow(title=label_text)
                active = (
                    (target_cid is None and current_is_default)
                    or (target_cid is not None and target_cid == current_remap)
                )
                check = Gtk.CheckButton()
                check.set_group(selected_row[0] if selected_row else None)
                if not selected_row:
                    selected_row.append(check)
                check.set_active(active)
                check.cid = target_cid  # type: ignore[attr-defined]
                row.add_prefix(check)
                row.set_activatable_widget(check)
                group.append(row)

            dialog.add_response("apply", "Apply")
            dialog.set_response_appearance("apply", Adw.ResponseAppearance.SUGGESTED)
            dialog.set_extra_child(group)

            def on_response(_d, response: str):
                if response != "apply":
                    return
                # Find the active radio button in the list box
                r = group.get_first_child()
                while r is not None:
                    # r is an AdwActionRow; its prefix widget is the CheckButton
                    child = r.get_first_child()
                    # Adw.ActionRow layout: box > prefixes > title > suffixes
                    # Easier: iterate descendants to find the active CheckButton
                    pending = [child]
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
                    r = r.get_next_sibling()

            dialog.connect("response", on_response)

        dialog.present(self.get_root())

    def _apply_remap(self, cid: int, target_cid: Optional[int]) -> None:
        # None = reset: remap to itself = restore default
        target = target_cid if target_cid is not None else cid
        threading.Thread(
            target=lambda: self.client.call(
                "remap_button", cid=cid, target_cid=target,
            ),
            daemon=True,
        ).start()
        GLib.timeout_add(300, lambda: (self._refresh_live() or False))
