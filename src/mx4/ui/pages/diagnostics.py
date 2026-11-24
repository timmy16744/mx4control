"""Diagnostics & Hardware Explorer page — health checks, telemetry, live HID++ probe."""

from __future__ import annotations

import json
import os
import shutil
import threading
from typing import Any

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gtk

from ..widgets.common import page_title, section_title


class DiagnosticsPage(Gtk.Box):
    def __init__(self, client, *, window=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.client = client
        self.window = window
        self._last_snapshot: dict[str, Any] = {}
        self._features: list[dict[str, Any]] = []

        self.set_margin_top(4)
        self.set_margin_bottom(24)

        self.append(page_title(
            "Diagnostics & Hardware",
            "Service health checks, live device telemetry, and HID++ 2.0 feature explorer.",
        ))

        # ─── Health checklist ───────────────────────────────────────
        self.append(section_title("System health"))
        self.health_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.append(self.health_box)

        # ─── Telemetry JSON summary ─────────────────────────────────
        self.append(section_title("Live hardware telemetry"))
        tele_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        tele_card.add_css_class("mx4-card")
        self.append(tele_card)

        self.tele_label = Gtk.Label(label="Loading…", xalign=0)
        self.tele_label.add_css_class("mx4-mono")
        self.tele_label.set_selectable(True)
        self.tele_label.set_wrap(True)
        tele_card.append(self.tele_label)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        tele_card.append(btn_row)

        copy_btn = Gtk.Button(label="Copy diagnostics JSON")
        copy_btn.add_css_class("mx4-btn-ghost")
        copy_btn.connect("clicked", self._on_copy_json)
        btn_row.append(copy_btn)

        reapply_btn = Gtk.Button(label="Re-apply all hardware settings")
        reapply_btn.add_css_class("mx4-btn-ghost")
        reapply_btn.connect("clicked", self._on_reapply)
        btn_row.append(reapply_btn)

        # ─── HID++ 2.0 Feature Explorer ─────────────────────────────
        self.append(section_title("HID++ 2.0 feature explorer"))
        exp_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.append(exp_bar)

        self.probe_btn = Gtk.Button(label="Probe all 45 hardware features")
        self.probe_btn.add_css_class("mx4-btn-primary")
        self.probe_btn.connect("clicked", self._on_probe)
        exp_bar.append(self.probe_btn)

        self.filter_entry = Gtk.SearchEntry(hexpand=True)
        self.filter_entry.set_placeholder_text("Filter by name or hex ID (e.g. 19B0, HAPTIC, SMART)…")
        self.filter_entry.connect("search-changed", lambda *_: self._render_features())
        exp_bar.append(self.filter_entry)

        self.features_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.append(self.features_box)

        self.refresh()

    def refresh(self) -> None:
        def worker():
            sys_ok = self.client.available()
            sys_ver = self.client.get_interface_version() if sys_ok else 0
            state = {}
            if sys_ok:
                try:
                    state = self.client.get_state() or {}
                except Exception:
                    state = {}

            agent = self.window.agent if self.window else None
            agent_ok = bool(agent and agent.available())
            agent_ver = agent.get_interface_version() if agent_ok else 0
            gesture_active, trigger_cid = (False, 0)
            active_prof = {}
            if agent_ok:
                try:
                    gesture_active, trigger_cid = agent.gesture_status()
                    active_prof = agent.get_active_profile() or {}
                except Exception:
                    pass

            wtype_path = shutil.which("wtype") or ""
            xdotool_path = shutil.which("xdotool") or ""
            hypr_sig = bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"))
            sway_sock = bool(os.environ.get("SWAYSOCK"))
            layer_shell = os.path.exists("/usr/lib/libgtk4-layer-shell.so") or os.path.exists(
                "/usr/lib64/libgtk4-layer-shell.so"
            )

            snap = {
                "sysd": {"running": sys_ok, "interface_version": sys_ver},
                "agent": {
                    "running": agent_ok,
                    "interface_version": agent_ver,
                    "gesture_active": gesture_active,
                    "trigger_cid": f"0x{trigger_cid:04X}" if trigger_cid else "none",
                    "active_profile": active_prof.get("app_id", "default"),
                },
                "environment": {
                    "compositor": "Hyprland" if hypr_sig else ("Sway" if sway_sock else os.environ.get("XDG_CURRENT_DESKTOP", "unknown")),
                    "wtype": bool(wtype_path),
                    "xdotool": bool(xdotool_path),
                    "gtk4_layer_shell": layer_shell,
                },
                "device": state,
            }
            GLib.idle_add(self._apply_snapshot, snap)
        threading.Thread(target=worker, daemon=True).start()

    def _apply_snapshot(self, snap: dict[str, Any]) -> bool:
        self._last_snapshot = snap
        self._render_health(snap)
        dev = snap.get("device", {})
        if dev.get("connected"):
            lines = [
                f"Device:        {dev.get('name')} (Friendly: {dev.get('friendly_name')})",
                f"Firmware:      {dev.get('firmware')}  |  Transport: {dev.get('connection')}",
                f"Battery:       {dev.get('battery')}% ({dev.get('battery_level_name')}, charging={dev.get('charging')})",
                f"DPI:           {dev.get('dpi')} (range {dev.get('dpi_min')}–{dev.get('dpi_max')}, step {dev.get('dpi_step')})",
                f"Scroll:        mode={dev.get('wheel_mode')}  threshold={dev.get('smartshift_threshold')}  torque={dev.get('ratchet_torque')}%",
                f"Hi-Res Wheel:  enabled={dev.get('hires_enabled')}  invert={dev.get('hires_invert')}",
                f"Thumb Wheel:   diverted={dev.get('thumbwheel_diverted')}  invert={dev.get('thumbwheel_invert')}",
                f"Haptic Motor:  enabled={dev.get('haptic_enabled')}  level={dev.get('haptic_level')}%  waveforms={len(dev.get('haptic_waveforms', []))}",
                f"Force Pad:     supported={dev.get('force_supported')}  value={dev.get('force_value')} (default={dev.get('force_default')})",
                f"Easy-Switch:   slot {int(dev.get('current_host', 0)) + 1} of {dev.get('num_hosts', 3)}",
            ]
            self.tele_label.set_text("\n".join(lines))
        else:
            self.tele_label.set_text("Mouse not connected.")
        return False

    def _render_health(self, snap: dict[str, Any]) -> None:
        child = self.health_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.health_box.remove(child)
            child = nxt

        sysd = snap["sysd"]
        agent = snap["agent"]
        env = snap["environment"]
        dev = snap["device"]

        checks = [
            (
                "System daemon (mx4-sysd)",
                f"Running · D-Bus API v{sysd['interface_version']}" if sysd["running"] else "Not running (sudo systemctl start mx4-sysd)",
                "ok" if sysd["running"] else "err",
            ),
            (
                "Session agent (mx4-agent)",
                f"Running · trigger {agent['trigger_cid']} · profile '{agent['active_profile']}'" if agent["running"] else "Not running (systemctl --user start mx4-agent)",
                "ok" if agent["running"] else "warn",
            ),
            (
                "MX Master 4 hardware link",
                f"Connected via {dev.get('connection')} · FW {dev.get('firmware')}" if dev.get("connected") else "No mouse detected",
                "ok" if dev.get("connected") else "err",
            ),
            (
                "Wayland keystroke & overlay stack",
                f"Compositor: {env['compositor']} · wtype={'yes' if env['wtype'] else 'missing'} · layer-shell={'yes' if env['gtk4_layer_shell'] else 'missing'}",
                "ok" if (env["wtype"] and env["gtk4_layer_shell"]) else "warn",
            ),
        ]

        for title, detail, level in checks:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.add_css_class("mx4-row")

            dot = Gtk.Box()
            dot.set_size_request(10, 10)
            dot.set_valign(Gtk.Align.CENTER)
            dot.add_css_class("mx4-status-dot")
            dot.add_css_class({"ok": "connected", "warn": "searching", "err": "disconnected"}[level])
            row.append(dot)

            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
            row.append(col)
            t = Gtk.Label(label=title, xalign=0)
            t.add_css_class("mx4-row-title")
            col.append(t)
            s = Gtk.Label(label=detail, xalign=0)
            s.add_css_class("mx4-row-sub")
            s.set_wrap(True)
            col.append(s)

            self.health_box.append(row)

    def _on_probe(self, _btn) -> None:
        self.probe_btn.set_sensitive(False)
        self.probe_btn.set_label("Probing…")

        def worker():
            try:
                rows = self.client.probe_features()
                GLib.idle_add(self._after_probe, rows, "")
            except Exception as e:
                GLib.idle_add(self._after_probe, [], str(e))
        threading.Thread(target=worker, daemon=True).start()

    def _after_probe(self, rows: list[dict], err: str) -> bool:
        self.probe_btn.set_sensitive(True)
        self.probe_btn.set_label("Re-probe hardware features")
        if err:
            if self.window:
                self.window.toast(f"Probe failed: {err}")
            return False
        self._features = rows
        self._render_features()
        if self.window:
            self.window.toast(f"Probed {len(rows)} HID++ 2.0 features")
        return False

    def _render_features(self) -> None:
        child = self.features_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.features_box.remove(child)
            child = nxt

        q = self.filter_entry.get_text().strip().lower()
        for f in self._features:
            hay = f"{f.get('feature_hex', '')} {f.get('name', '')} {f.get('description', '')}".lower()
            if q and q not in hay:
                continue
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.add_css_class("mx4-row")

            idx_lbl = Gtk.Label(label=f"#{int(f.get('index', 0)):02d}")
            idx_lbl.add_css_class("mx4-badge")
            row.append(idx_lbl)

            hex_lbl = Gtk.Label(label=str(f.get("feature_hex", "")))
            hex_lbl.add_css_class("mx4-mono")
            row.append(hex_lbl)

            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
            row.append(col)
            name_l = Gtk.Label(label=str(f.get("name", "")), xalign=0)
            name_l.add_css_class("mx4-row-title")
            col.append(name_l)
            desc_l = Gtk.Label(label=str(f.get("description", "")), xalign=0)
            desc_l.add_css_class("mx4-row-sub")
            desc_l.set_wrap(True)
            col.append(desc_l)

            if f.get("locked"):
                badge = Gtk.Label(label="Locked (Options+)")
                badge.add_css_class("mx4-badge")
            elif f.get("response_hex"):
                hx = str(f["response_hex"])
                badge = Gtk.Label(label=hx[:24] + ("…" if len(hx) > 24 else ""))
                badge.add_css_class("mx4-mono")
            else:
                badge = Gtk.Label(label=str(f.get("error") or "—"))
                badge.add_css_class("mx4-row-sub")
            badge.set_valign(Gtk.Align.CENTER)
            row.append(badge)

            self.features_box.append(row)

    def _on_copy_json(self, _btn) -> None:
        payload = json.dumps(
            {**self._last_snapshot, "probed_features": self._features},
            indent=2,
        )
        display = Gdk.Display.get_default()
        if display is not None:
            display.get_clipboard().set(payload)
            if self.window:
                self.window.toast("Diagnostics JSON copied to clipboard")

    def _on_reapply(self, _btn) -> None:
        def worker():
            try:
                ok = self.client.reload_config()
                if self.window:
                    GLib.idle_add(
                        self.window.toast,
                        "Hardware settings re-applied" if ok else "Reload failed",
                    )
            except Exception as e:
                if self.window:
                    GLib.idle_add(self.window.toast, f"Reload failed: {e}")
            GLib.idle_add(self.refresh)
        threading.Thread(target=worker, daemon=True).start()
