"""MX4 Studio (2027 Edition) — Native QtWebEngine + WebGL2 3D Hardware Studio.

Hosts a hardware-accelerated Three.js 3D MX Master 4 studio inside a native
Wayland/Qt6 desktop window with zero localhost ports (served via the custom
``mx4studio://`` URL scheme) and a thread-safe ``QWebChannel`` bridge directly
to ``org.mx4control.System`` and ``org.mx4control.Agent``.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import select
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QFile,
    QIODevice,
    QObject,
    Qt,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
    QWebEngineUrlRequestJob,
    QWebEngineUrlScheme,
    QWebEngineUrlSchemeHandler,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from ..agent.profiles import CATEGORY_TEMPLATES, clone_preset_slices, list_ring_presets
from ..agent.ring_themes import (
    get_ring_size,
    get_ring_theme,
    list_ring_sizes,
    list_ring_themes,
)
from ..agent.thumbwheel import THUMBWHEEL_PRESETS
from ..common.dbus import AgentClient, DaemonUnavailable, SystemClient
from ..common.logging import configure as configure_logging
from ..config import ActionSlice, ButtonBinding, ConfigStore, RingProfile
from ..hidpp import ControlID

logger = logging.getLogger("mx4.studio")

SCHEME_NAME = b"mx4studio"

_STUDIO_DIRS = [
    Path(__file__).resolve().parents[3] / "data" / "studio",
    Path("/usr/share/mx4control/studio"),
]


def _find_studio_dir() -> Path:
    for p in _STUDIO_DIRS:
        if (p / "index.html").exists():
            return p
    return _STUDIO_DIRS[0]


# ─────────────────────────── URL Scheme Handler ──────────────────────────


class StudioSchemeHandler(QWebEngineUrlSchemeHandler):
    """Serves bundled static assets (including ES modules) over ``mx4studio://``."""

    def __init__(self, root: Path, parent: QObject | None = None):
        super().__init__(parent)
        self._root = root.resolve()

    def requestStarted(self, job: QWebEngineUrlRequestJob) -> None:
        rel = job.requestUrl().path().lstrip("/") or "index.html"

        # Serve PySide6's built-in qwebchannel.js cleanly
        if rel == "vendor/qwebchannel.js":
            qf = QFile(":/qtwebchannel/qwebchannel.js")
            if qf.open(QIODevice.OpenModeFlag.ReadOnly):
                raw = bytes(qf.readAll())
                qf.close()
                self._reply(job, b"application/javascript; charset=utf-8", raw)
                return

        target = (self._root / rel).resolve()
        if not str(target).startswith(str(self._root)) or not target.is_file():
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
            return

        mime, _ = mimetypes.guess_type(str(target))
        if target.suffix == ".js" or target.suffix == ".mjs":
            mime = "application/javascript; charset=utf-8"
        elif target.suffix == ".css":
            mime = "text/css; charset=utf-8"
        elif target.suffix == ".html":
            mime = "text/html; charset=utf-8"
        elif target.suffix == ".svg":
            mime = "image/svg+xml"
        elif target.suffix == ".glb":
            mime = "model/gltf-binary"
        else:
            mime = mime or "application/octet-stream"

        try:
            data = target.read_bytes()
        except OSError:
            job.fail(QWebEngineUrlRequestJob.Error.RequestFailed)
            return
        self._reply(job, mime.encode("ascii"), data)

    @staticmethod
    def _reply(job: QWebEngineUrlRequestJob, mime: bytes, data: bytes) -> None:
        buf = QBuffer(job)
        buf.setData(QByteArray(data))
        buf.open(QIODevice.OpenModeFlag.ReadOnly)
        job.reply(mime, buf)


# ─────────────────────────── QWebChannel Bridge ──────────────────────────


class StudioBridge(QObject):
    """Thread-safe async RPC + live D-Bus event push bridge for MX4 Studio."""

    responseReady = Signal(str, str)       # (req_id, json_payload)
    liveEvent = Signal(str, str)           # (event_name, json_payload)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._sys = SystemClient()
        self._agent = AgentClient()
        self._store = ConfigStore()
        self._glib_loop: GLib.MainLoop | None = None
        self._glib_thread: threading.Thread | None = None
        self._input_stop = threading.Event()
        self._input_thread: threading.Thread | None = None
        self._start_dbus_listener()
        self._start_live_input_monitor()

    def _start_dbus_listener(self) -> None:
        """Pump live D-Bus signals on a lightweight GLib thread."""
        try:
            self._sys.subscribe_signals(
                on_diverted=lambda cids: self.liveEvent.emit(
                    "buttons", json.dumps(sorted(int(c) for c in cids))
                ),
                on_thumbwheel=lambda delta, direction: self.liveEvent.emit(
                    "thumbwheel", json.dumps({"delta": int(delta), "direction": int(direction)})
                ),
                on_state_changed=lambda delta: self.liveEvent.emit(
                    "state", json.dumps(delta)
                ),
                on_connected=lambda conn, idx: self.liveEvent.emit(
                    "connected", json.dumps({"connection": conn, "index": idx})
                ),
                on_disconnected=lambda: self.liveEvent.emit("disconnected", "{}"),
            )
            self._agent.subscribe_profile_changed(
                lambda app_id: self.liveEvent.emit("profile", json.dumps({"app_id": app_id}))
            )
            self._glib_loop = GLib.MainLoop()
            self._glib_thread = threading.Thread(
                target=self._glib_loop.run, name="MX4StudioDBus", daemon=True
            )
            self._glib_thread.start()
        except Exception as e:
            logger.debug("live D-Bus signal thread skipped: %s", e)

    def _start_live_input_monitor(self) -> None:
        """Stream real-time read-only hardware motion, clicks, and wheel deltas from evdev at 60 Hz."""
        def worker() -> None:
            try:
                import evdev
                from evdev import ecodes
            except Exception as e:
                logger.debug("evdev live monitor unavailable: %s", e)
                return

            key_to_cid = {
                ecodes.BTN_LEFT: int(ControlID.LEFT_CLICK),
                ecodes.BTN_RIGHT: int(ControlID.RIGHT_CLICK),
                ecodes.BTN_MIDDLE: int(ControlID.MIDDLE_CLICK),
                ecodes.BTN_SIDE: int(ControlID.BACK),
                ecodes.BTN_EXTRA: int(ControlID.FORWARD),
                getattr(ecodes, "BTN_BACK", -1): int(ControlID.BACK),
                getattr(ecodes, "BTN_FORWARD", -1): int(ControlID.FORWARD),
            }
            key_to_cid.pop(-1, None)

            def open_mouse_devices() -> list:
                found = []
                for path in evdev.list_devices():
                    try:
                        dev = evdev.InputDevice(path)
                        low = (dev.name or "").lower()
                        caps = dev.capabilities()
                        rels = set(caps.get(ecodes.EV_REL, []))
                        keys = set(caps.get(ecodes.EV_KEY, []))
                        is_mouse_cap = (
                            (ecodes.BTN_LEFT in keys)
                            or (ecodes.REL_WHEEL in rels)
                            or (ecodes.REL_HWHEEL in rels)
                            or (ecodes.REL_HWHEEL_HI_RES in rels)
                        )
                        is_mx = any(tok in low for tok in ("logitech", "mx master", "mx4 studio"))
                        if is_mouse_cap and is_mx:
                            found.append(dev)
                        else:
                            dev.close()
                    except Exception:
                        continue
                return found

            devices = open_mouse_devices()
            if not devices:
                logger.debug("No readable Logitech/MX4 evdev nodes found for live animation")
                return

            pressed_cids: set[int] = set()
            dx = dy = 0
            wy = wx = 0.0
            has_hires_y = False
            has_hires_x = False
            dirty_btns = False
            last_emit = time.monotonic()

            try:
                while not self._input_stop.is_set():
                    if not devices:
                        time.sleep(0.5)
                        devices = open_mouse_devices()
                        continue
                    try:
                        rlist, _, _ = select.select(devices, [], [], 0.016)
                    except (OSError, ValueError):
                        for d in devices:
                            try:
                                d.close()
                            except Exception:
                                pass
                        devices = open_mouse_devices()
                        continue

                    for dev in rlist:
                        try:
                            for ev in dev.read():
                                if ev.type == ecodes.EV_REL:
                                    if ev.code == ecodes.REL_X:
                                        dx += ev.value
                                    elif ev.code == ecodes.REL_Y:
                                        dy += ev.value
                                    elif ev.code == ecodes.REL_WHEEL_HI_RES:
                                        wy += ev.value / 120.0
                                        has_hires_y = True
                                    elif ev.code == ecodes.REL_WHEEL and not has_hires_y:
                                        wy += float(ev.value)
                                    elif ev.code == ecodes.REL_HWHEEL_HI_RES:
                                        wx += ev.value / 120.0
                                        has_hires_x = True
                                    elif ev.code == ecodes.REL_HWHEEL and not has_hires_x:
                                        wx += float(ev.value)
                                elif ev.type == ecodes.EV_KEY and ev.code in key_to_cid:
                                    cid = key_to_cid[ev.code]
                                    if ev.value:
                                        if cid not in pressed_cids:
                                            pressed_cids.add(cid)
                                            dirty_btns = True
                                    else:
                                        if cid in pressed_cids:
                                            pressed_cids.discard(cid)
                                            dirty_btns = True
                        except OSError:
                            try:
                                dev.close()
                            except Exception:
                                pass
                            if dev in devices:
                                devices.remove(dev)

                    now = time.monotonic()
                    if (dx or dy or abs(wy) > 1e-4 or abs(wx) > 1e-4 or dirty_btns) and (
                        dirty_btns or (now - last_emit) >= 0.015
                    ):
                        payload = {
                            "dx": int(dx),
                            "dy": int(dy),
                            "wy": round(wy, 3),
                            "wx": round(wx, 3),
                            "btns": sorted(pressed_cids),
                        }
                        self.liveEvent.emit("telemetry", json.dumps(payload))
                        dx = dy = 0
                        wy = wx = 0.0
                        dirty_btns = False
                        last_emit = now
            finally:
                for d in devices:
                    try:
                        d.close()
                    except Exception:
                        pass

        self._input_thread = threading.Thread(
            target=worker, name="MX4StudioLiveInput", daemon=True
        )
        self._input_thread.start()

    def shutdown(self) -> None:
        self._input_stop.set()
        if self._glib_loop is not None:
            try:
                self._glib_loop.quit()
            except Exception:
                pass

    @Slot(str, str, str)
    def invoke(self, req_id: str, method: str, args_json: str) -> None:
        """Run any backend command off the UI thread and return JSON."""
        def worker():
            try:
                args = json.loads(args_json) if args_json else {}
                data = self._dispatch(method, args)
                payload = json.dumps({"ok": True, "data": data})
            except DaemonUnavailable as e:
                payload = json.dumps({"ok": False, "error": str(e), "daemon_down": True})
            except Exception as e:
                logger.exception("StudioBridge.%s failed", method)
                payload = json.dumps({"ok": False, "error": str(e)})
            self.responseReady.emit(req_id, payload)

        threading.Thread(target=worker, daemon=True).start()

    # ─── RPC handlers ────────────────────────────────────────────────────

    def _dispatch(self, method: str, a: dict[str, Any]) -> Any:
        if method == "getSnapshot":
            return self._get_snapshot()

        if method == "setDpi":
            dpi = int(a["dpi"])
            ok = self._sys.set_dpi(dpi, True)
            return {"ok": ok, "dpi": dpi}

        if method == "setDpiPresets":
            vals = sorted({max(200, min(8000, int(x))) for x in a.get("presets", [])})
            if not vals:
                raise ValueError("Provide at least one DPI preset")
            self._store.invalidate()
            self._store.config.pointer.dpi_presets = vals
            self._store.save()
            self._reload_agent_quiet()
            return {"presets": vals}

        if method == "setScrollMode":
            mode = str(a.get("mode", "smart"))
            thr = int(a.get("threshold", 15))
            torque = int(a.get("torque", 75))
            ok = self._sys.set_scroll_mode(mode, thr, torque, True)
            return {"ok": ok}

        if method == "setHiRes":
            ok = self._sys.set_hires(bool(a["enabled"]), bool(a["invert"]))
            return {"ok": ok}

        if method == "setScrollTuning":
            speed = float(a.get("speed", 1.0))
            smoothness = int(a.get("smoothness", 0))
            accel = int(a.get("accel", 0))
            self._store.invalidate()
            self._store.config.scroll.scroll_speed = round(max(0.20, min(4.00, speed)), 2)
            self._store.config.scroll.scroll_smoothness = max(0, min(100, smoothness))
            self._store.config.scroll.scroll_accel = max(0, min(100, accel))
            self._store.save()
            try:
                ok = self._sys.set_scroll_tuning(speed, smoothness, accel, True)
                return {"ok": ok}
            except Exception as e:
                if "UnknownMethod" in str(e) or "No such method" in str(e):
                    return {"ok": False, "needs_install": True}
                raise

        if method == "setThumbwheel":
            div = bool(a["diverted"])
            inv = bool(a["invert"])
            mode = "actions" if div else "native"
            self._store.invalidate()
            self._store.config.thumbwheel.mode = mode
            self._store.config.thumbwheel.diverted = div
            self._store.config.thumbwheel.invert = inv
            self._store.save()
            ok = self._sys.set_thumbwheel(div, inv)
            self._reload_agent_quiet()
            return {"ok": ok}

        if method == "setThumbwheelTuning":
            mode = str(a.get("mode", "hd_scroll")).lower()
            if mode not in ("native", "hd_scroll", "actions"):
                mode = "native"
            inv = bool(a.get("invert", False))
            speed = round(max(0.20, min(4.00, float(a.get("speed", 1.0)))), 2)
            smoothness = max(0, min(100, int(a.get("smoothness", 35))))
            accel = max(0, min(100, int(a.get("accel", 25))))
            hires = bool(a.get("hires", True))
            haptic_detent = bool(a.get("haptic_detent", False))
            haptic_density = int(a.get("haptic_density", self._store.config.thumbwheel.haptic_density))
            if haptic_density not in (1, 2, 3, 6):
                haptic_density = 6
            haptic_pattern = max(0, min(14, int(a.get("haptic_pattern", self._store.config.thumbwheel.haptic_pattern))))
            self._store.invalidate()
            tw = self._store.config.thumbwheel
            tw.mode = mode
            tw.diverted = (mode == "actions")
            tw.invert = inv
            tw.speed = speed
            tw.smoothness = smoothness
            tw.accel = accel
            tw.hires = hires
            tw.haptic_detent = haptic_detent
            tw.haptic_density = haptic_density
            tw.haptic_pattern = haptic_pattern
            self._store.save()
            self._reload_agent_quiet()
            try:
                ok = self._sys.set_thumbwheel_tuning(
                    mode, inv, speed, smoothness, accel, hires, haptic_detent, True,
                )
                try:
                    self._sys.set_thumbwheel_haptics(haptic_density, haptic_pattern, True)
                except Exception:
                    pass
                return {"ok": ok}
            except Exception as e:
                if "UnknownMethod" in str(e) or "No such method" in str(e):
                    # Older installed daemon without SetThumbwheelTuning: fall back for native/actions
                    if mode in ("native", "actions"):
                        ok = self._sys.set_thumbwheel(mode == "actions", inv)
                        return {"ok": ok, "needs_install": False}
                    return {"ok": False, "needs_install": True}
                raise

        if method == "saveThumbwheelConfig":
            self._store.invalidate()
            tw = self._store.config.thumbwheel
            tw.preset = str(a.get("preset", tw.preset))
            tw.positive_type = str(a.get("positive_type", tw.positive_type))
            tw.positive_data = str(a.get("positive_data", tw.positive_data))
            tw.negative_type = str(a.get("negative_type", tw.negative_type))
            tw.negative_data = str(a.get("negative_data", tw.negative_data))
            tw.step = max(1, min(120, int(a.get("step", tw.step))))
            tw.haptic_tick = bool(a.get("haptic_tick", tw.haptic_tick))
            tw.micro_haptics = bool(a.get("micro_haptics", tw.micro_haptics))
            if "haptic_pattern" in a:
                tw.haptic_pattern = max(0, min(14, int(a["haptic_pattern"])))
            self._store.save()
            self._reload_agent_quiet()
            return {"ok": True}

        if method == "setHapticMotor":
            en = bool(a["enabled"])
            lvl = max(1, min(100, int(a.get("level", 50))))
            self._store.invalidate()
            self._store.config.haptics.enabled = en
            self._store.save()
            ok = self._sys.set_haptic(en, lvl, True)
            if ok and en and a.get("preview"):
                self._sys.trigger_haptic(self._store.config.haptics.ring_confirm_pattern)
            self._reload_agent_quiet()
            return {"ok": ok}

        if method == "triggerHaptic":
            # Auto-enable hardware motor (0x19B0) if currently muted so clicking any
            # waveform or Pulse Haptic ALWAYS produces a real tactile pulse in hand!
            auto_enabled = False
            try:
                en, lvl = self._sys.get_haptic()
                if not en:
                    target_lvl = max(25, min(100, lvl or 65))
                    if self._sys.set_haptic(True, target_lvl, True):
                        self._store.invalidate()
                        self._store.config.haptics.enabled = True
                        self._store.save()
                        self._reload_agent_quiet()
                        auto_enabled = True
            except Exception:
                pass
            ok = self._sys.trigger_haptic(int(a["pattern"]))
            return {"ok": ok, "auto_enabled": auto_enabled}

        if method == "previewRing":
            dur = int(a.get("duration_ms", 2600))
            if not self._agent.available():
                return {"ok": False, "error": "mx4-agent is not running"}
            try:
                ok = self._agent.preview_ring(dur)
                return {"ok": ok}
            except Exception as e:
                if "UnknownMethod" in str(e) or "No such method" in str(e):
                    return {"ok": False, "needs_install": True}
                raise

        if method == "setForceThreshold":
            val = int(a["value"])
            return {"ok": self._sys.set_force_threshold(val, True)}

        if method == "saveHapticConfig":
            self._store.invalidate()
            h = self._store.config.haptics
            for k in (
                "ring_boundary_pattern",
                "ring_confirm_pattern",
                "ring_cancel_pattern",
                "notification_pattern",
            ):
                if k in a:
                    setattr(h, k, int(a[k]))
            if "notification_enabled" in a:
                h.notification_enabled = bool(a["notification_enabled"])
            self._store.save()
            self._reload_agent_quiet()
            return {"ok": True}

        if method == "setFriendlyName":
            return {"ok": self._sys.set_friendly_name(str(a["name"]))}

        if method == "switchHost":
            return {"ok": self._sys.switch_host(int(a["index"]))}

        if method == "renameHost":
            return {"ok": self._sys.rename_host(int(a["index"]), str(a["name"]))}

        if method == "applyButtonBinding":
            cid = int(a["cid"])
            scope = str(a.get("scope", "global"))
            at = str(a.get("action_type", "default"))
            ad = str(a.get("action_data", ""))
            self._store.invalidate()
            if scope == "global":
                target_list = self._store.config.button_bindings
            else:
                prof = self._store.config.ring_profiles.get(scope)
                if prof is None:
                    raise ValueError(f"Unknown profile {scope}")
                target_list = prof.button_overrides
            target_list[:] = [b for b in target_list if b.cid != cid]
            if at != "default":
                target_list.append(ButtonBinding(cid=cid, action_type=at, action_data=ad))
            self._store.save()

            ok = True
            if scope == "global" and self._sys.available():
                if at == "remap":
                    ok = self._sys.remap_button(cid, int(ad))
                elif at == "default":
                    ok = self._sys.reset_button(cid)
                else:
                    ok = self._sys.divert_button(cid, True)
            self._reload_agent_quiet()
            return {"ok": ok}

        if method == "resetAllButtons":
            scope = str(a.get("scope", "global"))
            self._store.invalidate()
            if scope == "global":
                self._store.config.button_bindings.clear()
                self._store.save()
                if self._sys.available():
                    for b in self._sys.get_buttons():
                        if b.get("remappable") or b.get("divertable"):
                            try:
                                self._sys.reset_button(int(b["cid"]))
                            except Exception:
                                pass
            else:
                prof = self._store.config.ring_profiles.get(scope)
                if prof:
                    prof.button_overrides.clear()
                    self._store.save()
            self._reload_agent_quiet()
            return {"ok": True}

        if method == "saveRingSettings":
            self._store.invalidate()
            d = self._store.config.daemon
            if "autostart_gesture" in a:
                d.autostart_gesture = bool(a["autostart_gesture"])
                if self._agent.available():
                    self._agent.set_gesture_enabled(d.autostart_gesture)
            if "trigger_cid" in a:
                d.trigger_cid = int(a["trigger_cid"])
            if "cancel_radius" in a:
                d.cancel_radius = max(15, min(100, int(a["cancel_radius"])))
            if "ring_theme" in a:
                d.ring_theme = get_ring_theme(str(a["ring_theme"])).id
            if "ring_size" in a:
                d.ring_size = get_ring_size(str(a["ring_size"])).id
            if "ring_show_hints" in a:
                d.ring_show_hints = bool(a["ring_show_hints"])
            if "ring_animate" in a:
                d.ring_animate = bool(a["ring_animate"])
            self._store.save()
            self._reload_agent_quiet()
            return {"ok": True}

        if method == "applyRingPreset":
            app_id = str(a.get("profile_id", "default"))
            preset_id = str(a.get("preset_id", "default"))
            self._store.invalidate()
            prof = self._store.config.ring_profiles.get(app_id)
            if prof is None:
                raise ValueError(f"Profile '{app_id}' not found")
            prof.slices = clone_preset_slices(preset_id)
            self._store.save()
            self._reload_agent_quiet()
            return {"ok": True, "profile_id": app_id, "preset_id": preset_id}

        if method == "saveRingSlice":
            app_id = str(a.get("profile_id", "default"))
            idx = int(a["index"])
            self._store.invalidate()
            prof = self._store.config.ring_profiles.get(app_id)
            if prof is None:
                raise ValueError(f"Profile '{app_id}' not found")
            while len(prof.slices) < 8:
                prof.slices.append(ActionSlice("", "", "disabled", ""))
            s = prof.slices[idx]
            s.label = str(a.get("label", ""))
            s.action_type = str(a.get("action_type", "keystroke"))
            s.action_data = str(a.get("action_data", ""))
            self._store.save()
            self._reload_agent_quiet()
            return {"ok": True}

        if method == "addRingProfile":
            app_id = str(a["app_id"]).strip().lower()
            tpl = str(a.get("template", "default"))
            if not app_id or app_id == "default":
                raise ValueError("Invalid application ID")
            self._store.invalidate()
            if tpl in CATEGORY_TEMPLATES:
                slices = clone_preset_slices(tpl)
            else:
                slices = [
                    ActionSlice(**s.__dict__)
                    for s in self._store.config.ring_profiles["default"].slices
                ]
            self._store.config.ring_profiles[app_id] = RingProfile(
                app_id=app_id, app_name=app_id.title(), slices=slices,
            )
            self._store.save()
            self._reload_agent_quiet()
            return {"ok": True, "app_id": app_id}

        if method == "deleteRingProfile":
            app_id = str(a["app_id"])
            if app_id == "default":
                raise ValueError("Cannot delete default profile")
            self._store.invalidate()
            self._store.config.ring_profiles.pop(app_id, None)
            self._store.save()
            self._reload_agent_quiet()
            return {"ok": True}

        if method == "testAction":
            ok = self._agent.test_action(str(a["action_type"]), str(a.get("action_data", "")))
            return {"ok": ok}

        if method == "probeFeatures":
            return {"features": self._sys.probe_features()}

        if method == "reloadConfig":
            ok = self._sys.reload_config()
            self._reload_agent_quiet()
            return {"ok": ok}

        raise ValueError(f"Unknown bridge method: {method}")

    def _reload_agent_quiet(self) -> None:
        try:
            if self._agent.available():
                self._agent.reload_profiles()
        except Exception:
            pass

    def _get_snapshot(self) -> dict[str, Any]:
        sys_ok = self._sys.available()
        sys_ver = self._sys.get_interface_version() if sys_ok else 0
        state: dict[str, Any] = {"connected": False}
        buttons: list[dict[str, Any]] = []
        hosts: list[dict[str, Any]] = []
        if sys_ok:
            try:
                state = self._sys.get_state() or {"connected": False}
                if state.get("connected"):
                    buttons = self._sys.get_buttons() or []
                    hosts = self._sys.get_hosts() or []
            except Exception as e:
                logger.debug("sysd snapshot error: %s", e)

        agent_ok = self._agent.available()
        agent_ver = self._agent.get_interface_version() if agent_ok else 0
        gesture_active, trigger_cid = (False, int(ControlID.VIRTUAL_GESTURE))
        active_profile = "default"
        if agent_ok:
            try:
                gesture_active, trigger_cid = self._agent.gesture_status()
                prof = self._agent.get_active_profile() or {}
                active_profile = str(prof.get("app_id") or "default")
            except Exception:
                pass

        self._store.invalidate()
        cfg = self._store.config

        profiles_out = {}
        for k, p in cfg.ring_profiles.items():
            slices = [
                {
                    "label": s.label,
                    "icon": s.icon,
                    "action_type": s.action_type,
                    "action_data": s.action_data,
                }
                for s in p.slices
            ]
            while len(slices) < 8:
                slices.append({"label": "", "icon": "", "action_type": "disabled", "action_data": ""})
            profiles_out[k] = {
                "app_id": p.app_id,
                "app_name": p.app_name,
                "slices": slices[:8],
                "button_overrides": [
                    {"cid": b.cid, "action_type": b.action_type, "action_data": b.action_data}
                    for b in p.button_overrides
                ],
            }

        return {
            "sysd": {"running": sys_ok, "version": sys_ver},
            "agent": {
                "running": agent_ok,
                "version": agent_ver,
                "gesture_active": gesture_active,
                "trigger_cid": trigger_cid,
                "active_profile": active_profile,
            },
            "environment": {
                "compositor": (
                    "Hyprland"
                    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
                    else ("Sway" if os.environ.get("SWAYSOCK") else os.environ.get("XDG_CURRENT_DESKTOP", "Linux"))
                ),
                "wtype": bool(shutil.which("wtype")),
                "xdotool": bool(shutil.which("xdotool")),
                "layer_shell": (
                    os.path.exists("/usr/lib/libgtk4-layer-shell.so")
                    or os.path.exists("/usr/lib64/libgtk4-layer-shell.so")
                ),
            },
            "device": state,
            "buttons": buttons,
            "hosts": hosts,
            "config": {
                "pointer": {"dpi_presets": list(cfg.pointer.dpi_presets)},
                "scroll": {
                    "scroll_speed": cfg.scroll.scroll_speed,
                    "scroll_smoothness": cfg.scroll.scroll_smoothness,
                    "scroll_accel": cfg.scroll.scroll_accel,
                },
                "haptics": {
                    "enabled": cfg.haptics.enabled,
                    "ring_boundary_pattern": cfg.haptics.ring_boundary_pattern,
                    "ring_confirm_pattern": cfg.haptics.ring_confirm_pattern,
                    "ring_cancel_pattern": cfg.haptics.ring_cancel_pattern,
                    "notification_enabled": cfg.haptics.notification_enabled,
                    "notification_pattern": cfg.haptics.notification_pattern,
                },
                "thumbwheel": {
                    "mode": cfg.thumbwheel.mode or ("actions" if cfg.thumbwheel.diverted else "native"),
                    "diverted": cfg.thumbwheel.diverted,
                    "invert": cfg.thumbwheel.invert,
                    "speed": cfg.thumbwheel.speed,
                    "smoothness": cfg.thumbwheel.smoothness,
                    "accel": cfg.thumbwheel.accel,
                    "hires": cfg.thumbwheel.hires,
                    "haptic_detent": cfg.thumbwheel.haptic_detent,
                    "haptic_density": cfg.thumbwheel.haptic_density,
                    "haptic_pattern": cfg.thumbwheel.haptic_pattern,
                    "preset": cfg.thumbwheel.preset,
                    "step": cfg.thumbwheel.step,
                    "haptic_tick": cfg.thumbwheel.haptic_tick,
                    "micro_haptics": cfg.thumbwheel.micro_haptics,
                    "positive_type": cfg.thumbwheel.positive_type,
                    "positive_data": cfg.thumbwheel.positive_data,
                    "negative_type": cfg.thumbwheel.negative_type,
                    "negative_data": cfg.thumbwheel.negative_data,
                },
                "daemon": {
                    "autostart_gesture": cfg.daemon.autostart_gesture,
                    "trigger_cid": cfg.daemon.trigger_cid,
                    "cancel_radius": cfg.daemon.cancel_radius,
                    "ring_theme": get_ring_theme(cfg.daemon.ring_theme).id,
                    "ring_size": get_ring_size(cfg.daemon.ring_size).id,
                    "ring_show_hints": cfg.daemon.ring_show_hints,
                    "ring_animate": cfg.daemon.ring_animate,
                },
                "button_bindings": [
                    {"cid": b.cid, "action_type": b.action_type, "action_data": b.action_data}
                    for b in cfg.button_bindings
                ],
                "ring_profiles": profiles_out,
            },
            "ring_themes": list_ring_themes(),
            "ring_sizes": list_ring_sizes(),
            "ring_presets": list_ring_presets(),
            "thumbwheel_presets": {
                k: {
                    "label": v[0],
                    "positive_type": v[1],
                    "positive_data": v[2],
                    "negative_type": v[3],
                    "negative_data": v[4],
                }
                for k, v in THUMBWHEEL_PRESETS.items()
            },
        }


# ─────────────────────────── Main Studio Window ──────────────────────────


class _StudioPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            logger.warning("JS error [%s:%d]: %s", sourceID, lineNumber, message)


class StudioWindow(QMainWindow):
    def __init__(self, studio_dir: Path):
        super().__init__()
        self.setWindowTitle("MX4 Studio — Logitech MX Master 4")
        self.resize(1320, 840)
        self.setMinimumSize(940, 640)
        self.setWindowIcon(QIcon.fromTheme("input-mouse"))
        self.setStyleSheet("background-color: #0b0c10;")

        self._profile = QWebEngineProfile("mx4studio", self)
        self._handler = StudioSchemeHandler(studio_dir, self)
        self._profile.installUrlSchemeHandler(SCHEME_NAME, self._handler)

        self._view = QWebEngineView(self)
        self._page = _StudioPage(self._profile, self._view)
        self._page.setBackgroundColor(QColor("#0b0c10"))
        self._view.setPage(self._page)

        settings = self._view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)

        self._channel = QWebChannel(self._page)
        self._bridge = StudioBridge(self)
        self._channel.registerObject("mx4Bridge", self._bridge)
        self._page.setWebChannel(self._channel)

        self.setCentralWidget(self._view)
        self._view.setUrl(QUrl("mx4studio://app/index.html"))

    def closeEvent(self, event) -> None:
        self._bridge.shutdown()
        self._view.setPage(None)
        self._page.deleteLater()
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    configure_logging("INFO", component="mx4-studio")

    # Enable crisp hardware WebGL2 on Wayland/Hyprland
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--enable-gpu-rasterization --enable-webgl --ignore-gpu-blocklist")

    scheme = QWebEngineUrlScheme(SCHEME_NAME)
    scheme.setFlags(
        QWebEngineUrlScheme.Flag.SecureScheme
        | QWebEngineUrlScheme.Flag.LocalScheme
        | QWebEngineUrlScheme.Flag.LocalAccessAllowed
        | QWebEngineUrlScheme.Flag.CorsEnabled
        | QWebEngineUrlScheme.Flag.FetchApiAllowed
    )
    QWebEngineUrlScheme.registerScheme(scheme)

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("MX4 Studio")
    app.setOrganizationName("mx4control")
    app.setDesktopFileName("io.github.mx4control")
    app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    studio_dir = _find_studio_dir()
    win = StudioWindow(studio_dir)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
