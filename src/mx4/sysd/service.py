"""mx4-sysd supervisor.

GLib main loop. Wires udev hotplug → connect → apply → serve, plus live
HID++ async notifications (diverted buttons, diverted thumb wheel,
wireless wake/reconnect, live battery status).
"""

from __future__ import annotations

import logging
import logging.handlers
import signal
import threading
from pathlib import Path
from typing import Any

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from ..common.logging import configure
from ..config.schema import ButtonDefault
from ..hidpp.raw import probe_all
from .apply import apply_persistent_settings
from .button_router import ButtonRouter
from .connection import ConnectionManager
from .dbus_service import SystemDBusService
from .deviceconfig import DeviceConfigStore
from .smooth_scroll import (
    HorizontalScrollEngine,
    ScrollTuning,
    SmoothScrollEngine,
    ThumbWheelTuning,
)
from .state import build_state, write_state_file

logger = logging.getLogger(__name__)

LIVENESS_INTERVAL_S = 30
UDEV_DEBOUNCE_MS = 400


class Supervisor:
    def __init__(self) -> None:
        self.config_store = DeviceConfigStore()
        self.conn = ConnectionManager()
        self.scroll_engine = SmoothScrollEngine()
        self.hscroll_engine = HorizontalScrollEngine(
            on_detent=self._on_thumbwheel_haptic_detent,
        )
        self.router = ButtonRouter(
            on_diverted=self._on_diverted_buttons_threadsafe,
            on_thumbwheel=None,
            on_thumbwheel_packet=self._on_thumbwheel_packet_direct,
            on_reconnect=self._on_wireless_reconnect_threadsafe,
            on_battery=self._on_battery_threadsafe,
            on_wheel=self._on_wheel_direct,
        )
        self.dbus = SystemDBusService(self)
        self.loop = GLib.MainLoop()
        self._state: dict[str, Any] = {"connected": False}
        self._connect_pending = False
        self._reapply_pending = False
        self._debounce_source = 0

    # ─── lifecycle ────────────────────────────────────────────────────────

    def run(self) -> int:
        for sig in (signal.SIGTERM, signal.SIGINT):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, self._on_signal)
        self.conn.set_udev_callback(self._udev_event_threadsafe)
        self.dbus.start(on_ready=self._on_dbus_ready)
        self.loop.run()
        return 0

    def _on_dbus_ready(self, ok: bool) -> None:
        if not ok:
            logger.error("could not own the system bus name — exiting")
            self.loop.quit()
            return
        self.conn.start_monitor()
        self._schedule_connect()
        GLib.timeout_add_seconds(LIVENESS_INTERVAL_S, self._liveness_tick)

    def _on_signal(self) -> bool:
        logger.info("signal received — shutting down")
        try:
            # Always un-divert 0x2121 and 0x2150 HD scroll before exiting so user never loses scrolling
            if self.conn.device is not None:
                cfg = self.config_store.config
                if self.scroll_engine.active:
                    try:
                        self.conn.device.set_hires_scroll(
                            cfg.hires_enabled, cfg.hires_invert, diverted=False,
                        )
                    except Exception:
                        pass
                if self.hscroll_engine.active:
                    try:
                        self.conn.device.set_thumbwheel_diverted(
                            False, cfg.thumbwheel_invert,
                        )
                    except Exception:
                        pass
            self.scroll_engine.stop()
            self.hscroll_engine.stop()
            self.dbus.stop()
            self.conn.stop()
        finally:
            self.loop.quit()
        return GLib.SOURCE_REMOVE

    # ─── connect / hotplug (worker threads, results marshalled back) ──────

    def _udev_event_threadsafe(self, action: str, devnode: str) -> None:
        GLib.idle_add(self._on_udev_event, action, devnode)

    def _on_udev_event(self, action: str, devnode: str) -> bool:
        if action in ("add", "change", "online"):
            if self._debounce_source:
                GLib.source_remove(self._debounce_source)
            self._debounce_source = GLib.timeout_add(
                UDEV_DEBOUNCE_MS, self._debounced_connect)
        elif action == "remove" and self.conn.connected:
            self._schedule_liveness_check()
        return GLib.SOURCE_REMOVE

    def _debounced_connect(self) -> bool:
        self._debounce_source = 0
        self._schedule_connect()
        return GLib.SOURCE_REMOVE

    def _schedule_connect(self) -> None:
        if self._connect_pending or self.conn.connected:
            return
        self._connect_pending = True
        threading.Thread(target=self._connect_worker, daemon=True,
                         name="mx4-connect").start()

    def _sync_scroll_engine_for_config(self) -> bool:
        """Configure SmoothScrollEngine from DeviceConfig. Returns True if wheel should be diverted."""
        cfg = self.config_store.config
        tuning = ScrollTuning(
            speed=cfg.scroll_speed,
            smoothness=cfg.scroll_smoothness,
            accel=cfg.scroll_accel,
            invert=cfg.hires_invert,
            hires=cfg.hires_enabled,
        )
        if self.conn.device is not None:
            caps = self.conn.device.get_hires_capabilities()
            if caps.get("multiplier"):
                self.scroll_engine.set_hw_multiplier(int(caps["multiplier"]))
        if tuning.needs_diversion:
            if self.scroll_engine.configure(tuning):
                return True
            logger.warning("smooth scroll engine failed to open uinput — falling back to native wheel")
        else:
            self.scroll_engine.configure(tuning)
        return False

    def _sync_thumbwheel_engine_for_config(self) -> bool:
        """Configure HorizontalScrollEngine from DeviceConfig. Returns True if 0x2150 is diverted for HD Scroll."""
        cfg = self.config_store.config
        mode = (cfg.thumbwheel_mode or ("actions" if cfg.thumbwheel_diverted else "native")).lower()
        tuning = ThumbWheelTuning(
            enabled=(mode == "hd_scroll"),
            speed=cfg.thumbwheel_speed,
            smoothness=cfg.thumbwheel_smoothness,
            accel=cfg.thumbwheel_accel,
            invert=cfg.thumbwheel_invert,
            hires=cfg.thumbwheel_hires,
            haptic_detent=cfg.thumbwheel_haptic_detent,
            haptic_density=cfg.thumbwheel_haptic_density,
            haptic_pattern=cfg.thumbwheel_haptic_pattern,
        )
        if self.conn.device is not None:
            info = self.conn.device.get_thumbwheel_info()
            if info.get("native_res") and info.get("diverted_res"):
                self.hscroll_engine.set_hardware_resolution(
                    int(info["native_res"]), int(info["diverted_res"]),
                )
        if tuning.enabled:
            if self.hscroll_engine.configure(tuning):
                return True
            logger.warning("horizontal HD scroll engine failed to open uinput — falling back to native thumbwheel")
        else:
            self.hscroll_engine.configure(tuning)
        return False

    def _enrich_state(self, state: dict[str, Any]) -> dict[str, Any]:
        cfg = self.config_store.config
        tw_mode = (cfg.thumbwheel_mode or ("actions" if cfg.thumbwheel_diverted else "native")).lower()
        state["hires_enabled"] = cfg.hires_enabled
        state["hires_invert"] = cfg.hires_invert
        state["scroll_speed"] = cfg.scroll_speed
        state["scroll_smoothness"] = cfg.scroll_smoothness
        state["scroll_accel"] = cfg.scroll_accel
        state["scroll_engine_active"] = self.scroll_engine.active
        state["thumbwheel_mode"] = tw_mode
        state["thumbwheel_diverted"] = (tw_mode == "actions")
        state["thumbwheel_invert"] = cfg.thumbwheel_invert
        state["thumbwheel_speed"] = cfg.thumbwheel_speed
        state["thumbwheel_smoothness"] = cfg.thumbwheel_smoothness
        state["thumbwheel_accel"] = cfg.thumbwheel_accel
        state["thumbwheel_hires"] = cfg.thumbwheel_hires
        state["thumbwheel_haptic_detent"] = cfg.thumbwheel_haptic_detent
        state["thumbwheel_haptic_density"] = cfg.thumbwheel_haptic_density
        state["thumbwheel_haptic_pattern"] = cfg.thumbwheel_haptic_pattern
        state["thumbwheel_engine_active"] = self.hscroll_engine.active
        return state

    def _connect_worker(self) -> None:
        ok = self.conn.connect()
        if ok:
            try:
                divert_wheel = self._sync_scroll_engine_for_config()
                divert_tw_hd = self._sync_thumbwheel_engine_for_config()
                apply_persistent_settings(
                    self.conn.device,
                    self.config_store.config,
                    divert_wheel=divert_wheel,
                    divert_thumbwheel_hd=divert_tw_hd,
                )
                self.router.bind(self.conn.dispatcher)
            except Exception:
                logger.exception("apply/bind failed")
            state = self._enrich_state(build_state(self.conn.device, self.conn.info))
        else:
            state = {"connected": False}
        GLib.idle_add(self._after_connect, ok, state)

    def _after_connect(self, ok: bool, state: dict) -> bool:
        self._connect_pending = False
        self._state = state
        write_state_file(state)
        if ok and self.conn.info:
            self.dbus.emit_connected(
                self.conn.info.get("connection_type", "bolt"),
                self.conn.info.get("device_index", 0xFF))
            self.dbus.emit_state_changed(state)
            logger.info("device ready; settings applied")
        return GLib.SOURCE_REMOVE

    # ─── wireless wake / reconnect (0x1D4B) ───────────────────────────────

    def _on_wireless_reconnect_threadsafe(self) -> None:
        GLib.idle_add(self._schedule_reapply)

    def _schedule_reapply(self) -> bool:
        if self._reapply_pending or not self.conn.connected:
            return GLib.SOURCE_REMOVE
        self._reapply_pending = True
        threading.Thread(target=self._reapply_worker, daemon=True,
                         name="mx4-reapply").start()
        return GLib.SOURCE_REMOVE

    def _reapply_worker(self) -> None:
        state: dict[str, Any] = {}
        try:
            if self.conn.device is not None:
                logger.info("wireless wake/reconnect detected — re-applying settings")
                divert_wheel = self._sync_scroll_engine_for_config()
                divert_tw_hd = self._sync_thumbwheel_engine_for_config()
                apply_persistent_settings(
                    self.conn.device,
                    self.config_store.config,
                    divert_wheel=divert_wheel,
                    divert_thumbwheel_hd=divert_tw_hd,
                )
                state = self._enrich_state(build_state(self.conn.device, self.conn.info))
        except Exception:
            logger.exception("wireless reconnect re-apply failed")
        GLib.idle_add(self._after_reapply, state)

    def _after_reapply(self, state: dict[str, Any]) -> bool:
        self._reapply_pending = False
        if state:
            self._state = state
            write_state_file(state)
            if self.conn.info:
                self.dbus.emit_connected(
                    self.conn.info.get("connection_type", "bolt"),
                    self.conn.info.get("device_index", 0xFF),
                )
            self.dbus.emit_state_changed(state)
        return GLib.SOURCE_REMOVE

    # ─── live battery updates (0x1004) ────────────────────────────────────

    def _on_battery_threadsafe(
        self, percent: int, charging: bool, status: int, bucket: int
    ) -> None:
        GLib.idle_add(self._apply_battery_update, percent, charging, status, bucket)

    def _apply_battery_update(
        self, percent: int, charging: bool, status: int, bucket: int
    ) -> bool:
        level_name = {8: "full", 4: "good", 2: "low", 1: "critical"}.get(bucket, "unknown")
        delta = {
            "battery": percent,
            "charging": charging,
            "battery_status": status,
            "battery_bucket": bucket,
            "battery_level_name": level_name,
        }
        self._state.update(delta)
        write_state_file(self._state)
        self.dbus.emit_state_changed(delta)
        return GLib.SOURCE_REMOVE

    # ─── liveness ─────────────────────────────────────────────────────────

    def _liveness_tick(self) -> bool:
        self._schedule_liveness_check()
        return GLib.SOURCE_CONTINUE

    def _schedule_liveness_check(self) -> None:
        if not self.conn.connected:
            self._schedule_connect()
            return
        threading.Thread(target=self._liveness_worker, daemon=True,
                         name="mx4-ping").start()

    def _liveness_worker(self) -> None:
        alive = self.conn.alive()
        GLib.idle_add(self._after_liveness, alive)

    def _after_liveness(self, alive: bool) -> bool:
        if not alive and self.conn.connected:
            logger.info("device stopped responding — disconnecting")
            self.conn.disconnect()
            self._state = {"connected": False}
            write_state_file(self._state)
            self.dbus.emit_disconnected()
            self._schedule_connect()
        return GLib.SOURCE_REMOVE

    # ─── diverted buttons, vertical wheel & thumbwheel (reader thread) ────

    def _on_wheel_direct(self, delta: int, hi_res: bool) -> None:
        """Hot path directly from HID++ reader thread → 144Hz SmoothScrollEngine."""
        self.scroll_engine.feed(delta, hi_res=hi_res)

    def _on_diverted_buttons_threadsafe(self, cids: list[int]) -> None:
        GLib.idle_add(self._emit_diverted, cids)

    def _emit_diverted(self, cids: list[int]) -> bool:
        self.dbus.emit_diverted_button(cids)
        return GLib.SOURCE_REMOVE

    def _on_thumbwheel_haptic_detent(self, pattern: int = 1) -> None:
        """Fire a non-blocking LRA micro-detent tick on virtual HD horizontal detent."""
        dev = self.conn.device
        if dev is None or not self.config_store.config.haptic_enabled:
            return
        pat = max(0, min(14, int(pattern)))
        threading.Thread(
            target=dev.trigger_haptic, args=(pat,), daemon=True, name="mx4-tw-detent",
        ).start()

    def _on_thumbwheel_packet_direct(
        self, delta: int, elapsed_ms: int, status: int, flags: int
    ) -> None:
        """Hot path directly from HID++ reader thread for diverted 0x2150 thumb wheel."""
        cfg = self.config_store.config
        if cfg.thumbwheel_mode == "hd_scroll" and self.hscroll_engine.active:
            self.hscroll_engine.feed(delta, elapsed_ms=elapsed_ms, status=status)
            return
        direction = 1 if delta > 0 else -1
        GLib.idle_add(self._emit_thumbwheel, delta, direction)

    def _on_thumbwheel_threadsafe(self, delta: int, direction: int) -> None:
        GLib.idle_add(self._emit_thumbwheel, delta, direction)

    def _emit_thumbwheel(self, delta: int, direction: int) -> bool:
        self.dbus.emit_thumbwheel(delta, direction)
        return GLib.SOURCE_REMOVE

    # ─── D-Bus backend (called on the main loop) ──────────────────────────

    @property
    def _dev(self):
        return self.conn.device

    def _update_state(self, delta: dict[str, Any]) -> None:
        self._state.update(delta)
        write_state_file(self._state)
        self.dbus.emit_state_changed(delta)

    def get_state(self) -> dict:
        return dict(self._state)

    def get_dpi(self) -> int:
        return int(self._state.get("dpi", 1000))

    def set_dpi(self, dpi: int, persist: bool) -> bool:
        if not self._dev:
            return False
        dpi = max(200, min(8000, int(dpi)))
        ok = self._dev.set_dpi(dpi)
        if ok:
            if persist:
                self.config_store.config.dpi = dpi
                self.config_store.save()
            self._update_state({"dpi": dpi})
        return ok

    def get_smartshift(self) -> tuple[bool, int]:
        return (bool(self._state.get("smartshift", False)),
                int(self._state.get("smartshift_threshold", 15)))

    def set_smartshift(self, enabled: bool, threshold: int, persist: bool) -> bool:
        mode = "smart" if enabled else "ratchet"
        torque = int(self._state.get("ratchet_torque", self.config_store.config.ratchet_torque))
        return self.set_scroll_mode(mode, threshold, torque, persist)

    def set_scroll_mode(
        self, mode: str, threshold: int, torque: int, persist: bool
    ) -> bool:
        if not self._dev:
            return False
        mode = mode.lower()
        if mode not in ("smart", "ratchet", "free"):
            mode = "smart"
        threshold = max(1, min(50, int(threshold)))
        torque = max(1, min(100, int(torque)))
        ok = self._dev.set_scroll_mode(mode, threshold, torque=torque)
        if ok:
            enabled = mode == "smart"
            if persist:
                cfg = self.config_store.config
                cfg.wheel_mode = mode
                cfg.smartshift_enabled = enabled
                cfg.smartshift_threshold = threshold
                cfg.ratchet_torque = torque
                self.config_store.save()
            self._update_state({
                "wheel_mode": mode,
                "smartshift": enabled,
                "smartshift_threshold": threshold,
                "ratchet_torque": torque,
            })
        return ok

    def set_hires(self, enabled: bool, invert: bool) -> bool:
        if not self._dev:
            return False
        cfg = self.config_store.config
        cfg.hires_enabled = bool(enabled)
        cfg.hires_invert = bool(invert)
        divert_wheel = self._sync_scroll_engine_for_config()
        hw_invert = False if divert_wheel else cfg.hires_invert
        ok = self._dev.set_hires_scroll(
            cfg.hires_enabled or divert_wheel, hw_invert, diverted=divert_wheel,
        )
        if ok:
            self.config_store.save()
            self._update_state({
                "hires_enabled": cfg.hires_enabled,
                "hires_invert": cfg.hires_invert,
                "hires_diverted": divert_wheel,
                "scroll_engine_active": self.scroll_engine.active,
            })
        return ok

    def set_scroll_tuning(
        self, speed: float, smoothness: int, accel: int, persist: bool
    ) -> bool:
        if not self._dev:
            return False
        speed = round(max(0.20, min(4.00, float(speed))), 2)
        smoothness = max(0, min(100, int(smoothness)))
        accel = max(0, min(100, int(accel)))

        cfg = self.config_store.config
        cfg.scroll_speed = speed
        cfg.scroll_smoothness = smoothness
        cfg.scroll_accel = accel

        divert_wheel = self._sync_scroll_engine_for_config()
        hw_invert = False if divert_wheel else cfg.hires_invert
        ok = self._dev.set_hires_scroll(
            cfg.hires_enabled or divert_wheel, hw_invert, diverted=divert_wheel,
        )
        if ok:
            if persist:
                self.config_store.save()
            self._update_state({
                "scroll_speed": speed,
                "scroll_smoothness": smoothness,
                "scroll_accel": accel,
                "hires_diverted": divert_wheel,
                "scroll_engine_active": self.scroll_engine.active,
            })
        return ok

    def get_haptic(self) -> tuple[bool, int]:
        if self._dev:
            en, lvl = self._dev.get_haptic()
            return en, lvl
        return (
            bool(self._state.get("haptic_enabled", False)),
            int(self._state.get("haptic_level", 50)),
        )

    def set_haptic(self, enabled: bool, level: int, persist: bool) -> bool:
        if not self._dev:
            return False
        level = max(1, min(100, int(level)))
        ok = self._dev.set_haptic(enabled, level)
        if ok:
            if persist:
                self.config_store.config.haptic_enabled = enabled
                self.config_store.config.haptic_level = level
                self.config_store.save()
            self._update_state({"haptic_enabled": enabled, "haptic_level": level})
        return ok

    def trigger_haptic(self, pattern: int) -> bool:
        return bool(self._dev and self._dev.trigger_haptic(pattern))

    def get_force_button(self) -> dict[str, Any]:
        if not self._dev:
            return {"supported": False}
        fb = self._dev.get_force_button(0)
        if fb is None:
            return {"supported": False}
        return {
            "supported": True,
            "changeable": fb.changeable,
            "value": fb.current_force,
            "min": fb.min_force,
            "max": fb.max_force,
            "default": fb.default_force,
            "percent": fb.percent,
        }

    def set_force_threshold(self, value: int, persist: bool) -> bool:
        if not self._dev:
            return False
        # 0 means reset to device default
        fb = self._dev.get_force_button(0)
        if fb is None:
            return False
        target = fb.default_force if value <= 0 else max(fb.min_force, min(fb.max_force, int(value)))
        ok = self._dev.set_force_button(target, 0)
        if ok:
            if persist:
                self.config_store.config.force_threshold = 0 if value <= 0 else target
                self.config_store.save()
            self._update_state({"force_value": target})
        return ok

    def set_friendly_name(self, name: str) -> bool:
        clean = str(name).strip()
        if not self._dev or not clean:
            return False
        ok = self._dev.set_friendly_name(clean)
        if ok:
            actual = self._dev.get_friendly_name() or clean
            self._update_state({"friendly_name": actual})
        return ok

    def switch_host(self, index: int) -> bool:
        return bool(self._dev and self._dev.switch_host(index))

    def rename_host(self, index: int, name: str) -> bool:
        clean = str(name).strip()
        if not self._dev or not clean:
            return False
        return self._dev.set_host_name(index, clean)

    def get_hosts(self) -> list[dict]:
        if not self._dev:
            return []
        hosts = self._dev.get_hosts()
        if not hosts:
            return []
        return [
            {
                "index": h.index,
                "paired": h.paired,
                "bus_type": h.bus_type,
                "bus_label": h.bus_label,
                "name": h.name,
                "max_name_len": h.max_name_len,
                "current": h.index == hosts.current_host,
                "can_rename": hosts.can_set_name,
            }
            for h in hosts.hosts
        ]

    def get_buttons(self) -> list[dict]:
        if not self._dev:
            return []
        out = []
        for i in range(self._dev.get_button_count()):
            bi = self._dev.get_button_info(i)
            if bi:
                out.append({
                    "index": bi.index, "cid": bi.cid, "task_id": bi.task_id,
                    "flags": bi.flags, "remap_cid": bi.remap_cid,
                    "diverted": bi.diverted, "remappable": bi.remappable,
                    "divertable": bi.divertable,
                })
        return out

    def divert_button(self, cid: int, on: bool) -> bool:
        return bool(self._dev and self._dev.divert_button(cid, on))

    def remap_button(self, cid: int, target: int) -> bool:
        if not self._dev:
            return False
        ok = self._dev.remap_button(cid, target)
        if ok:
            self._persist_button(cid, "remap", target)
        return ok

    def reset_button(self, cid: int) -> bool:
        if not self._dev:
            return False
        ok = self._dev.reset_button(cid)
        if ok:
            cfg = self.config_store.config
            cfg.buttons = [b for b in cfg.buttons if b.cid != cid]
            self.config_store.save()
        return ok

    def set_thumbwheel(self, diverted: bool, invert: bool) -> bool:
        cfg = self.config_store.config
        mode = "actions" if diverted else "native"
        return self.set_thumbwheel_tuning(
            mode,
            invert,
            cfg.thumbwheel_speed,
            cfg.thumbwheel_smoothness,
            cfg.thumbwheel_accel,
            cfg.thumbwheel_hires,
            cfg.thumbwheel_haptic_detent,
            True,
        )

    def set_thumbwheel_tuning(
        self,
        mode: str,
        invert: bool,
        speed: float,
        smoothness: int,
        accel: int,
        hires: bool,
        haptic_detent: bool,
        persist: bool,
    ) -> bool:
        if not self._dev:
            return False
        mode = str(mode or "native").lower()
        if mode not in ("native", "hd_scroll", "actions"):
            mode = "native"
        invert = bool(invert)
        speed = round(max(0.20, min(4.00, float(speed))), 2)
        smoothness = max(0, min(100, int(smoothness)))
        accel = max(0, min(100, int(accel)))
        hires = bool(hires)
        haptic_detent = bool(haptic_detent)

        cfg = self.config_store.config
        cfg.thumbwheel_mode = mode
        cfg.thumbwheel_diverted = (mode == "actions")
        cfg.thumbwheel_invert = invert
        cfg.thumbwheel_speed = speed
        cfg.thumbwheel_smoothness = smoothness
        cfg.thumbwheel_accel = accel
        cfg.thumbwheel_hires = hires
        cfg.thumbwheel_haptic_detent = haptic_detent

        divert_hd = self._sync_thumbwheel_engine_for_config()
        if mode == "hd_scroll" and divert_hd:
            hw_div, hw_inv = True, False
        elif mode == "actions":
            hw_div, hw_inv = True, invert
        else:
            hw_div, hw_inv = False, invert

        ok = self._dev.set_thumbwheel_diverted(hw_div, hw_inv)
        if ok:
            if persist:
                self.config_store.save()
            self._update_state({
                "thumbwheel_mode": mode,
                "thumbwheel_diverted": (mode == "actions"),
                "thumbwheel_invert": invert,
                "thumbwheel_speed": speed,
                "thumbwheel_smoothness": smoothness,
                "thumbwheel_accel": accel,
                "thumbwheel_hires": hires,
                "thumbwheel_haptic_detent": haptic_detent,
                "thumbwheel_haptic_density": cfg.thumbwheel_haptic_density,
                "thumbwheel_haptic_pattern": cfg.thumbwheel_haptic_pattern,
                "thumbwheel_engine_active": self.hscroll_engine.active,
            })
        return ok

    def set_thumbwheel_haptics(self, density: int, pattern: int, persist: bool) -> bool:
        dens = int(density)
        if dens not in (1, 2, 3, 6):
            dens = 6
        pat = max(0, min(14, int(pattern)))
        cfg = self.config_store.config
        cfg.thumbwheel_haptic_density = dens
        cfg.thumbwheel_haptic_pattern = pat
        self._sync_thumbwheel_engine_for_config()
        if persist:
            self.config_store.save()
        self._update_state({
            "thumbwheel_haptic_density": dens,
            "thumbwheel_haptic_pattern": pat,
        })
        return True

    def probe_features(self) -> list[dict]:
        if not self._dev:
            return []
        probed = probe_all(self._dev.dispatcher)
        out = []
        for fid, row in probed.items():
            out.append({
                "feature_id": int(fid),
                "feature_hex": f"0x{fid:04X}",
                "index": int(row["index"]),
                "name": str(row["name"]),
                "description": str(row["description"]),
                "response_hex": str(row["response_hex"] or ""),
                "error": str(row["error"] or ""),
                "locked": bool(row["locked"]),
            })
        return out

    def raw_call(self, feature: int, fn: int, args: list[int], use_long: bool) -> bytes:
        if not self._dev:
            return b""
        r = self._dev.dispatcher.request(feature, fn, *args, use_long=use_long)
        return bytes(r) if r else b""

    def reload_config(self) -> bool:
        self.config_store.invalidate()
        if self._dev:
            divert_wheel = self._sync_scroll_engine_for_config()
            divert_tw_hd = self._sync_thumbwheel_engine_for_config()
            apply_persistent_settings(
                self._dev,
                self.config_store.config,
                divert_wheel=divert_wheel,
                divert_thumbwheel_hd=divert_tw_hd,
            )
            state = self._enrich_state(build_state(self._dev, self.conn.info))
            self._state = state
            write_state_file(state)
            self.dbus.emit_state_changed(state)
        return True

    def _persist_button(self, cid: int, mode: str, target: int) -> None:
        cfg = self.config_store.config
        cfg.buttons = [b for b in cfg.buttons if b.cid != cid]
        cfg.buttons.append(ButtonDefault(cid=cid, mode=mode, target=target))
        self.config_store.save()


def _setup_logging() -> None:
    configure(component="mx4-sysd")
    try:
        logdir = Path("/var/log/mx4control")
        logdir.mkdir(parents=True, exist_ok=True)
        h = logging.handlers.RotatingFileHandler(
            logdir / "mx4-sysd.log", maxBytes=512_000, backupCount=2)
        h.setFormatter(logging.Formatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s"))
        logging.getLogger().addHandler(h)
    except Exception:
        pass


def main() -> int:
    _setup_logging()
    logger.info("mx4-sysd starting")
    return Supervisor().run()
