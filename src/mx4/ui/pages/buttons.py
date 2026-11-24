"""Buttons page — global & per-app button bindings for all 9 MX Master 4 controls."""

from __future__ import annotations

import threading
from typing import Optional

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

from ..widgets.common import page_title, section_title
from ..widgets.mouse_svg import BUTTON_LABELS
from ..widgets.rebind_dialog import RebindDialog
from ...common.dbus import DaemonUnavailable
from ...config import ButtonBinding, ConfigStore
from ...hidpp import ControlID


_ALL_CONTROLS: list[tuple[int, str, str]] = [
    (ControlID.LEFT_CLICK,      "Left Click",     "Primary mouse click"),
    (ControlID.RIGHT_CLICK,     "Right Click",    "Secondary mouse click"),
    (ControlID.MIDDLE_CLICK,    "Wheel Click",    "Press scroll wheel"),
    (ControlID.BACK,            "Back",           "Upper-middle side button"),
    (ControlID.FORWARD,         "Forward",        "Lower side button"),
    (ControlID.SMART_SHIFT,     "Mode Shift",     "Third side button under thumb wheel"),
    (ControlID.GESTURE_BUTTON,  "Gesture Button", "Thumb rest click"),
    (ControlID.VIRTUAL_GESTURE, "Thumb Pad",      "Force-sensing Haptic Sense pad"),
    (ControlID.THUMB_WHEEL,     "Thumb Wheel",    "Horizontal wheel control"),
]

_FRIENDLY_TYPE = {
    "default":           "Default",
    "disabled":          "Disabled",
    "remap":             "Hardware Remap",
    "keystroke":         "Keystroke",
    "command":           "Command",
    "application":       "Application",
    "dpi_cycle":         "Cycle DPI",
    "dpi_set":           "Set DPI",
    "smartshift_toggle": "Toggle Scroll Mode",
    "host_next":         "Next Host",
    "haptic":            "Play Haptic",
}


class ButtonsPage(Gtk.Box):
    def __init__(self, client, *, window=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.client = client
        self.window = window
        self.store = ConfigStore()
        self._button_infos: dict[int, dict] = {}
        self._scope_ids: list[str] = ["global"]
        self._scope: str = "global"
        self._updating = False

        self.set_margin_top(4)
        self.set_margin_bottom(24)

        self.append(page_title(
            "Buttons",
            "Rebind any divertable or remappable control globally or per application.",
        ))

        # Scope bar
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bar.add_css_class("mx4-card")
        bar.add_css_class("compact")
        self.append(bar)

        lbl = Gtk.Label(label="Scope", xalign=0)
        lbl.add_css_class("mx4-card-title")
        bar.append(lbl)

        self.scope_dd = Gtk.DropDown()
        self.scope_dd.set_hexpand(True)
        self.scope_dd.connect("notify::selected", self._on_scope_changed)
        bar.append(self.scope_dd)

        reset_all = Gtk.Button(label="Reset all")
        reset_all.add_css_class("mx4-btn-ghost")
        reset_all.connect("clicked", self._on_reset_all)
        bar.append(reset_all)

        self.append(section_title("Physical controls"))
        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.append(self.list_box)

        self.refresh()

    def refresh(self) -> None:
        self.store.invalidate()
        self._rebuild_scopes()

        def fetch():
            try:
                btns = self.client.get_buttons() or []
            except Exception:
                btns = []
            GLib.idle_add(self._apply_buttons, btns)
        threading.Thread(target=fetch, daemon=True).start()

    def _rebuild_scopes(self) -> None:
        self._updating = True
        try:
            profs = self.store.config.ring_profiles
            app_ids = sorted(k for k in profs if k != "default")
            self._scope_ids = ["global"] + app_ids
            labels = ["Global (All Applications)"] + [
                f"App Override: {profs[k].app_name} ({k})" for k in app_ids
            ]
            self.scope_dd.set_model(Gtk.StringList.new(labels))
            idx = self._scope_ids.index(self._scope) if self._scope in self._scope_ids else 0
            self._scope = self._scope_ids[idx]
            self.scope_dd.set_selected(idx)
        finally:
            self._updating = False

    def _on_scope_changed(self, dd, _):
        if self._updating:
            return
        idx = dd.get_selected()
        if 0 <= idx < len(self._scope_ids):
            self._scope = self._scope_ids[idx]
            self._render_rows()

    def _apply_buttons(self, btns: list[dict]) -> bool:
        self._button_infos = {int(b["cid"]): b for b in btns}
        self._render_rows()
        return False

    def _current_bindings_list(self) -> list[ButtonBinding]:
        if self._scope == "global":
            return self.store.config.button_bindings
        prof = self.store.config.ring_profiles.get(self._scope)
        return prof.button_overrides if prof else []

    def _binding_for(self, cid: int) -> tuple[str, str]:
        for b in self._current_bindings_list():
            if b.cid == cid:
                return b.action_type, b.action_data
        if self._scope == "global":
            info = self._button_infos.get(cid)
            if info:
                remap = info.get("remap_cid")
                if remap and remap not in (0, cid):
                    return "remap", str(remap)
        return "default", ""

    def _format_binding(self, cid: int, at: str, ad: str) -> str:
        trigger_cid = int(self.store.config.daemon.trigger_cid or ControlID.VIRTUAL_GESTURE)
        if cid == trigger_cid and self.store.config.daemon.autostart_gesture and at == "default":
            return "Actions Ring Trigger"
        label = _FRIENDLY_TYPE.get(at, at)
        if at == "remap" and ad.isdigit():
            target_lbl = BUTTON_LABELS.get(int(ad), f"0x{int(ad):04X}")
            return f"Remap → {target_lbl}"
        if ad:
            return f"{label}: {ad}"
        return label

    def _render_rows(self) -> None:
        child = self.list_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.list_box.remove(child)
            child = nxt

        for cid, name, desc in _ALL_CONTROLS:
            info = self._button_infos.get(int(cid))
            remappable = bool(info and info.get("remappable"))
            divertable = bool(info and info.get("divertable"))
            at, ad = self._binding_for(int(cid))

            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.add_css_class("mx4-row")

            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
            row.append(col)

            title_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            col.append(title_line)
            t = Gtk.Label(label=name, xalign=0)
            t.add_css_class("mx4-row-title")
            title_line.append(t)

            cid_badge = Gtk.Label(label=f"0x{int(cid):04X}")
            cid_badge.add_css_class("mx4-badge")
            title_line.append(cid_badge)

            caps = []
            if divertable:
                caps.append("divertable")
            if remappable:
                caps.append("remappable")
            if not caps:
                caps.append("firmware-locked")
            sub = Gtk.Label(label=f"{desc} · {', '.join(caps)}", xalign=0)
            sub.add_css_class("mx4-row-sub")
            col.append(sub)

            act_lbl = Gtk.Label(label=self._format_binding(int(cid), at, ad))
            act_lbl.add_css_class("mx4-badge")
            act_lbl.set_valign(Gtk.Align.CENTER)
            row.append(act_lbl)

            btn = Gtk.Button(label="Configure")
            btn.add_css_class("mx4-btn-ghost")
            btn.set_valign(Gtk.Align.CENTER)
            btn.set_sensitive(remappable or divertable)
            btn.connect("clicked", lambda _b, c=int(cid), n=name: self._open_dialog(c, n))
            row.append(btn)

            self.list_box.append(row)

    def _open_dialog(self, cid: int, label: str) -> None:
        info = self._button_infos.get(cid)
        remappable = bool(info and info.get("remappable"))
        divertable = bool(info and info.get("divertable"))
        at, ad = self._binding_for(cid)
        scope_label = "Global" if self._scope == "global" else f"App: {self._scope}"

        dlg = RebindDialog(
            button_label=label, cid=cid,
            current_action_type=at, current_action_data=ad,
            remappable=remappable and self._scope == "global",
            divertable=divertable,
            scope_label=scope_label,
            on_apply=lambda new_at, new_ad: self._apply_binding(cid, new_at, new_ad, label),
        )
        dlg.present(self.get_root())

    def _apply_binding(self, cid: int, action_type: str, action_data: str, label: str) -> None:
        self.store.invalidate()
        target_list = self._current_bindings_list()
        target_list[:] = [b for b in target_list if b.cid != cid]
        if action_type != "default":
            target_list.append(ButtonBinding(cid=cid, action_type=action_type, action_data=action_data))
        self.store.save()

        def worker():
            try:
                if self._scope == "global":
                    if action_type == "remap":
                        self.client.remap_button(cid, int(action_data))
                    elif action_type == "default":
                        self.client.reset_button(cid)
                    else:
                        self.client.divert_button(cid, True)
                if self.window is not None and self.window.agent is not None:
                    self.window.agent.reload_profiles()
                GLib.idle_add(self._toast, f"{label} → {_FRIENDLY_TYPE.get(action_type, action_type)}")
            except DaemonUnavailable:
                GLib.idle_add(self._toast, "mx4-sysd not running?")
            except Exception as e:
                GLib.idle_add(self._toast, f"Failed: {e}")
            GLib.idle_add(self.refresh)
        threading.Thread(target=worker, daemon=True).start()

    def _on_reset_all(self, _btn) -> None:
        self.store.invalidate()
        target_list = self._current_bindings_list()
        cids = [b.cid for b in target_list]
        target_list.clear()
        self.store.save()

        def worker():
            if self._scope == "global":
                for cid in set(cids) | {int(c) for c, _, _ in _ALL_CONTROLS}:
                    info = self._button_infos.get(cid)
                    if info and (info.get("remappable") or info.get("divertable")):
                        try:
                            self.client.reset_button(cid)
                        except Exception:
                            pass
            if self.window is not None and self.window.agent is not None:
                try:
                    self.window.agent.reload_profiles()
                except Exception:
                    pass
            GLib.idle_add(self._toast, "All button bindings reset to default")
            GLib.idle_add(self.refresh)
        threading.Thread(target=worker, daemon=True).start()

    def _toast(self, msg: str) -> None:
        if self.window is not None:
            self.window.toast(msg)
