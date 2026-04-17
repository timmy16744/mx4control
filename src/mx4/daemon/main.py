"""mx4d — the long-running MX Master 4 service.

Wires together:

* HID++ dispatcher + MXMaster4 wrapper (owns the hidraw fd)
* Gesture engine (HID++ diversion + evdev grab)
* Actions Ring overlay (GTK4 / layer-shell)
* Hyprland focus watcher + per-app profile resolution
* Unix-socket JSON-RPC server (for CLI / GUI clients)
* GLib main loop
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from typing import Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

from ..common.logging import configure as configure_logging
from ..config import ConfigStore
from ..hidpp import (
    HIDPPDispatcher, MXMaster4, HapticPattern, find_mx_master_4,
)
from .executor import execute as execute_action
from .gesture import GestureEngine, GestureEvent
from .hyprland import HyprlandFocusWatcher
from .ipc import IPCServer
from .overlay import ActionsRingOverlay
from .profiles import ProfileManager

logger = logging.getLogger("mx4.daemon")

RECONNECT_INTERVAL_S = 3
HEALTH_INTERVAL_S = 10
HEALTH_FAILURE_THRESHOLD = 3


class Daemon:
    def __init__(self, config_store: ConfigStore):
        self.config_store = config_store
        self.app = Adw.Application(application_id="io.github.mx4control.daemon")
        self.app.connect("activate", self._on_activate)

        self.device: Optional[MXMaster4] = None
        self.dispatcher: Optional[HIDPPDispatcher] = None
        self.gesture: Optional[GestureEngine] = None
        self.overlay: Optional[ActionsRingOverlay] = None

        self.profiles = ProfileManager(config_store.config)
        self.focus_watcher: Optional[HyprlandFocusWatcher] = None

        self.ipc = IPCServer()
        self._register_ipc_methods()

        self._reconnect_source: Optional[int] = None
        self._health_source: Optional[int] = None
        self._health_failures = 0

    # ─── lifecycle ──────────────────────────────────────────────────────

    def run(self) -> int:
        self.app.hold()  # prevent auto-exit without a window
        return self.app.run([])

    def _on_activate(self, _app) -> None:
        self.overlay = ActionsRingOverlay()
        self.ipc.start()
        self.profiles.start()
        GLib.idle_add(self._connect_device)

    # ─── device connect / reconnect ─────────────────────────────────────

    def _connect_device(self) -> bool:
        info = find_mx_master_4()
        if info is None:
            logger.info("MX Master 4 not found — will retry")
            self._schedule_reconnect()
            return False

        self.dispatcher = HIDPPDispatcher(info["path"], device_index=info["device_index"])
        if not self.dispatcher.open():
            logger.error("failed to open hidraw")
            self._schedule_reconnect()
            return False

        self.device = MXMaster4(self.dispatcher, connection_type=info["connection_type"])

        # Apply saved settings once
        cfg = self.config_store.config
        if cfg.pointer.dpi:
            self.device.set_dpi(cfg.pointer.dpi)
        self.device.set_smartshift(
            cfg.scroll.smartshift_enabled, cfg.scroll.smartshift_threshold
        )
        self.device.set_hires_scroll(cfg.scroll.hires_enabled, cfg.scroll.invert_vertical)
        if cfg.thumbwheel.diverted:
            self.device.set_thumbwheel_diverted(True, cfg.thumbwheel.invert)

        # Start gesture engine if configured
        if cfg.daemon.autostart_gesture:
            self._start_gesture()

        self._schedule_health_check()
        logger.info(f"Connected via {info['connection_type']} (slot={info['device_index']})")
        return False  # don't repeat this idle

    def _disconnect(self) -> None:
        if self.gesture:
            self.gesture.stop()
            self.gesture = None
        if self.dispatcher:
            self.dispatcher.close()
            self.dispatcher = None
        self.device = None

    def _schedule_reconnect(self) -> None:
        if self._reconnect_source is not None:
            return
        self._reconnect_source = GLib.timeout_add_seconds(
            RECONNECT_INTERVAL_S, self._reconnect_tick
        )

    def _reconnect_tick(self) -> bool:
        if self.device is not None:
            self._reconnect_source = None
            return False
        if self._connect_device() or self.device is not None:
            self._reconnect_source = None
            return False
        return True  # try again

    def _schedule_health_check(self) -> None:
        if self._health_source is not None:
            return
        self._health_source = GLib.timeout_add_seconds(
            HEALTH_INTERVAL_S, self._health_tick
        )

    def _health_tick(self) -> bool:
        if self.device is None:
            self._health_source = None
            return False
        ok = self.device.ping()
        if ok:
            self._health_failures = 0
            return True
        self._health_failures += 1
        if self._health_failures < HEALTH_FAILURE_THRESHOLD:
            return True
        logger.info("Device unresponsive — reconnecting")
        self._disconnect()
        self._health_failures = 0
        self._health_source = None
        self._schedule_reconnect()
        return False

    # ─── gesture engine ─────────────────────────────────────────────────

    def _start_gesture(self) -> bool:
        if self.gesture or self.device is None or self.overlay is None:
            return False

        engine = GestureEngine(
            self.device,
            on_start=self._on_gesture_start,
            on_move=self._on_gesture_move,
            on_end=self._on_gesture_end,
        )
        if not engine.start():
            return False
        self.gesture = engine
        return True

    def _on_gesture_start(self) -> None:
        """Called on evdev/HID++ threads — hop to main thread for GTK."""
        def show():
            profile = self.profiles.current_profile()
            assert self.overlay is not None
            self.overlay.load_profile(profile)
            self.overlay.show_at_cursor()
            return False
        GLib.idle_add(show)

    def _on_gesture_move(self, dx: int, dy: int, selected: Optional[int]) -> None:
        assert self.overlay is not None
        last = getattr(self, "_last_segment", object())
        if selected != last:
            self._last_segment = selected
            # Haptic tick on boundary crossings (not when entering the
            # cancel zone from a segment)
            if selected is not None and self.device is not None:
                pattern = self.config_store.config.haptics.ring_boundary_pattern
                try:
                    self.device.trigger_haptic(pattern)
                except Exception:
                    pass
            GLib.idle_add(
                lambda s=selected: (self.overlay.update_selection(s) or False)
            )

    def _on_gesture_end(self, event: GestureEvent) -> None:
        def finish():
            assert self.overlay is not None
            seg = self.overlay.hide_and_pick()
            if seg and seg.action_data:
                logger.info(f"gesture → {seg.label} ({seg.action_type}:{seg.action_data})")
                # Confirmation haptic
                if self.device is not None:
                    p = self.config_store.config.haptics.ring_confirm_pattern
                    try:
                        self.device.trigger_haptic(p)
                    except Exception:
                        pass
                execute_action(seg.action_type, seg.action_data)
            return False
        GLib.idle_add(finish)

    # ─── IPC handlers ───────────────────────────────────────────────────

    def _register_ipc_methods(self) -> None:
        self.ipc.register("ping", lambda: "pong")
        self.ipc.register("get_state", self._ipc_get_state)
        self.ipc.register("set_dpi", self._ipc_set_dpi)
        self.ipc.register("set_smartshift", self._ipc_set_smartshift)
        self.ipc.register("set_hires", self._ipc_set_hires)
        self.ipc.register("trigger_haptic", self._ipc_trigger_haptic)
        self.ipc.register("switch_host", self._ipc_switch_host)
        self.ipc.register("reload_config", self._ipc_reload)
        self.ipc.register("set_thumbwheel_diverted", self._ipc_set_thumbwheel)

    def _ipc_get_state(self) -> dict:
        if self.device is None:
            return {"connected": False}

        info = self.device.get_device_info()
        dpi = self.device.get_dpi()
        ss_on, ss_thr = self.device.get_smartshift()
        hosts = self.device.get_hosts()

        return {
            "connected": True,
            "name": info.name if info else "MX Master 4",
            "friendly_name": info.friendly_name if info else None,
            "firmware": info.firmware_version if info else None,
            "battery": info.battery_level if info else 0,
            "charging": info.battery_charging if info else False,
            "battery_status": info.battery_status if info else 0,
            "connection": info.connection_type if info else None,
            "dpi": dpi,
            "smartshift": ss_on,
            "smartshift_threshold": ss_thr,
            "hosts": _hosts_to_dict(hosts) if hosts else None,
            "gesture_active": self.gesture is not None,
        }

    def _ipc_set_dpi(self, dpi: int) -> bool:
        if self.device is None:
            return False
        ok = self.device.set_dpi(int(dpi))
        if ok:
            self.config_store.config.pointer.dpi = int(dpi)
            self.config_store.save()
        return ok

    def _ipc_set_smartshift(self, enabled: bool, threshold: int = 25) -> bool:
        if self.device is None:
            return False
        ok = self.device.set_smartshift(bool(enabled), int(threshold))
        if ok:
            self.config_store.config.scroll.smartshift_enabled = bool(enabled)
            self.config_store.config.scroll.smartshift_threshold = int(threshold)
            self.config_store.save()
        return ok

    def _ipc_set_hires(self, enabled: bool, invert: bool = False) -> bool:
        if self.device is None:
            return False
        ok = self.device.set_hires_scroll(bool(enabled), bool(invert))
        if ok:
            self.config_store.config.scroll.hires_enabled = bool(enabled)
            self.config_store.config.scroll.invert_vertical = bool(invert)
            self.config_store.save()
        return ok

    def _ipc_trigger_haptic(self, pattern: int) -> bool:
        if self.device is None:
            return False
        return self.device.trigger_haptic(int(pattern))

    def _ipc_switch_host(self, index: int) -> bool:
        if self.device is None:
            return False
        return self.device.switch_host(int(index))

    def _ipc_set_thumbwheel(self, diverted: bool, invert: bool = False) -> bool:
        if self.device is None:
            return False
        ok = self.device.set_thumbwheel_diverted(bool(diverted), bool(invert))
        if ok:
            self.config_store.config.thumbwheel.diverted = bool(diverted)
            self.config_store.config.thumbwheel.invert = bool(invert)
            self.config_store.save()
        return ok

    def _ipc_reload(self) -> bool:
        self.config_store._config = None
        self.config_store.load()
        return True


def _hosts_to_dict(hosts) -> dict:
    return {
        "num_hosts": hosts.num_hosts,
        "current_host": hosts.current_host,
        "hosts": [
            {
                "index": h.index, "paired": h.paired,
                "bus_type": h.bus_type, "name": h.name,
            }
            for h in hosts.hosts
        ],
    }


# ────────────────────────────── main ─────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(prog="mx4d")
    parser.add_argument("--log-level", default="INFO")
    args, _ = parser.parse_known_args()

    configure_logging(args.log_level, component="mx4d")
    store = ConfigStore()
    _ = store.config  # force load + migrate

    daemon = Daemon(store)

    def on_signal(*_):
        logger.info("shutting down")
        daemon._disconnect()
        daemon.ipc.stop()
        daemon.profiles.stop()
        daemon.app.quit()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    try:
        return daemon.run()
    finally:
        daemon._disconnect()
        daemon.ipc.stop()


if __name__ == "__main__":
    sys.exit(main())
