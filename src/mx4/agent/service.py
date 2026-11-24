"""mx4-agent supervisor.

Wires together everything that needs the Wayland session and drives it
off the system daemon's D-Bus signals:

* :class:`SystemClient`              — device I/O + DivertedButtonEvent + ThumbwheelEvent
* :class:`GestureEngine`             — evdev grab + cursor freeze (local)
* :class:`ActionsRingOverlay`        — GTK4 / layer-shell radial menu (local)
* :class:`ProfileManager`            — per-app ring + button resolution
* :class:`ActionDispatcher`          — diverted-button → software/hardware action
* :class:`ThumbWheelHandler`         — diverted thumb-wheel → custom action
* :class:`NotificationHapticWatcher` — desktop notifications → haptic pulse
* :class:`AgentService`              — the ``org.mx4control.Agent`` session bus
"""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import math
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import GLib, Gio, Gtk  # noqa: E402

from ..common.dbus import AGENT_BUS_NAME
from ..common.logging import configure as configure_logging
from ..config import ConfigStore
from .actions import ActionDispatcher
from .dbus_service import AgentService
from .executor import execute as execute_action
from .gesture import GestureEngine, GestureEvent
from .notifications import NotificationHapticWatcher
from .overlay import ActionsRingOverlay
from .profiles import ProfileManager
from .sysclient import SystemClient
from .thumbwheel import ThumbWheelHandler

logger = logging.getLogger("mx4.agent")

# Physical Haptic Sense Thumb Pad (0x01A0 = 416) is FIRST!
# (0x00D7 is Logitech's virtual gesture CID and does NOT fire on physical pad press.)
TRIGGER_CANDIDATES = (0x01A0, 0x00C3, 0x00C4, 0x0053)


def _state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))
    return Path(base) / "mx4control"


def configure_agent_logging(level: str = "INFO") -> None:
    configure_logging(level, component="mx4-agent")
    try:
        log_dir = _state_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            log_dir / "agent.log", maxBytes=1_000_000, backupCount=3,
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s.%(msecs)03d %(name)s %(levelname)s %(message)s",
            datefmt="%H:%M:%S",
        ))
        logging.getLogger().addHandler(handler)
    except OSError as e:
        logger.warning("could not open agent.log: %s", e)


class Agent:
    """The session-agent supervisor."""

    def __init__(self, store: ConfigStore):
        self.store = store

        self.sys = SystemClient()
        self.profiles = ProfileManager(store)
        self.overlay: Optional[ActionsRingOverlay] = None
        self.gesture: Optional[GestureEngine] = None
        self.actions: Optional[ActionDispatcher] = None
        self.thumbwheel: Optional[ThumbWheelHandler] = None
        self.notif_watcher: Optional[NotificationHapticWatcher] = None
        self.dbus: Optional[AgentService] = None

        self._trigger_cid = int(store.config.daemon.trigger_cid or TRIGGER_CANDIDATES[0])
        self._diverted: set[int] = set()
        self._loop = GLib.MainLoop()
        self._owner_id = 0
        self._shutting_down = False
        self._last_app_id = ""
        self._last_segment: object = object()
        self._last_ptr_push: float = 0.0
        self._preview_gen: int = 0

    def _sync_overlay_style(self) -> None:
        if self.overlay is None:
            return
        d = self.store.config.daemon
        self.overlay.configure(
            theme_id=d.ring_theme,
            size_id=d.ring_size,
            show_hints=d.ring_show_hints,
            animate=d.ring_animate,
            cancel_radius=d.cancel_radius,
        )

    # ─── lifecycle ──────────────────────────────────────────────────────

    def run(self) -> int:
        Gtk.init()
        self.overlay = ActionsRingOverlay()
        self._sync_overlay_style()

        self.sys.connect()

        self._trigger_cid = self._choose_trigger_cid()
        self.gesture = GestureEngine(
            trigger_cid=self._trigger_cid,
            on_start=self._on_gesture_start,
            on_move=self._on_gesture_move,
            on_end=self._on_gesture_end,
            cancel_radius=self.store.config.daemon.cancel_radius,
        )
        self.gesture.set_enabled(self.store.config.daemon.autostart_gesture)

        self.actions = ActionDispatcher(
            bindings_provider=self.profiles.current_button_bindings,
            skip_cids={self._trigger_cid},
            hardware_handler=self._execute_hardware_action,
        )
        self.thumbwheel = ThumbWheelHandler(
            config_provider=lambda: self.store.config,
            execute_fn=lambda at, ad: execute_action(at, ad, self._execute_hardware_action),
            haptic_fn=self._trigger_haptic_async,
        )
        self.notif_watcher = NotificationHapticWatcher(
            config_provider=lambda: self.store.config,
            trigger_haptic=self._trigger_haptic_async,
        )

        self.profiles.start(on_change=self._on_focus_change)
        self.gesture.start()
        self.notif_watcher.sync()

        self.sys.connect_diverted_buttons(self._on_diverted_buttons)
        self.sys.connect_thumbwheel(self._on_thumbwheel)
        self.sys.connect_device_signals(
            on_connected=self._on_device_connected,
            on_disconnected=self._on_device_disconnected,
        )

        self._apply_diversions()

        self._owner_id = Gio.bus_own_name(
            Gio.BusType.SESSION, AGENT_BUS_NAME,
            Gio.BusNameOwnerFlags.NONE,
            self._on_bus_acquired,
            None,
            self._on_name_lost,
        )

        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, 2, self._on_signal)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, 15, self._on_signal)

        logger.info("mx4-agent running (trigger CID 0x%04X)", self._trigger_cid)
        try:
            self._loop.run()
        finally:
            self._teardown()
        return 0

    def _choose_trigger_cid(self) -> int:
        preferred = int(self.store.config.daemon.trigger_cid or TRIGGER_CANDIDATES[0])
        ordered = [preferred] + [c for c in TRIGGER_CANDIDATES if c != preferred]
        if not self.sys.available:
            return ordered[0]
        for cid in ordered:
            if self.sys.divert_button(cid, True):
                self._diverted.add(cid)
                logger.info("gesture trigger = CID 0x%04X", cid)
                return cid
        logger.warning("no gesture trigger CID could be diverted; using default")
        return ordered[0]

    def _apply_diversions(self) -> None:
        wanted: set[int] = set()
        if self.gesture is None or self.gesture.enabled:
            wanted.add(self._trigger_cid)
        if self.actions is not None:
            wanted |= self.actions.action_bound_cids()

        if wanted == self._diverted:
            return

        for cid in wanted - self._diverted:
            if self.sys.divert_button(cid, True):
                self._diverted.add(cid)
        for cid in self._diverted - wanted:
            self.sys.divert_button(cid, False)
            self._diverted.discard(cid)
        logger.info("diverted CIDs: %s", sorted(hex(c) for c in self._diverted))

    # ─── hardware action execution (DPI cycle, SmartShift, Easy-Switch) ─

    def _trigger_haptic_async(self, pattern: int) -> bool:
        threading.Thread(
            target=self.sys.trigger_haptic, args=(int(pattern),), daemon=True
        ).start()
        return True

    def _execute_hardware_action(self, action_type: str, action_data: str) -> bool:
        at = action_type.lower()
        if at == "dpi_cycle":
            presets = sorted(set(self.store.config.pointer.dpi_presets or [800, 1200, 1600, 2400, 4000]))
            state = self.sys.get_state()
            cur = int(state.get("dpi", 1000))
            nxt = next((p for p in presets if p > cur), presets[0])
            ok = self.sys.set_dpi(nxt, persist=True)
            if ok and self.store.config.haptics.enabled:
                self._trigger_haptic_async(self.store.config.haptics.ring_confirm_pattern)
            logger.info("dpi_cycle: %d → %d (ok=%s)", cur, nxt, ok)
            return ok

        if at == "dpi_set":
            try:
                val = int(action_data)
            except ValueError:
                return False
            ok = self.sys.set_dpi(val, persist=True)
            if ok and self.store.config.haptics.enabled:
                self._trigger_haptic_async(self.store.config.haptics.ring_confirm_pattern)
            return ok

        if at == "smartshift_toggle":
            state = self.sys.get_state()
            cur_mode = str(state.get("wheel_mode", "ratchet"))
            thr = int(state.get("smartshift_threshold", 15))
            torque = int(state.get("ratchet_torque", 75))
            nxt_mode = "free" if cur_mode != "free" else "smart"
            ok = self.sys.set_scroll_mode(nxt_mode, thr, torque, persist=True)
            if ok and self.store.config.haptics.enabled:
                self._trigger_haptic_async(self.store.config.haptics.ring_boundary_pattern)
            logger.info("smartshift_toggle: %s → %s (ok=%s)", cur_mode, nxt_mode, ok)
            return ok

        if at == "host_next":
            hosts = [h for h in self.sys.get_hosts() if h.get("paired")]
            if len(hosts) < 2:
                return False
            cur_idx = next((i for i, h in enumerate(hosts) if h.get("current")), 0)
            target = int(hosts[(cur_idx + 1) % len(hosts)]["index"])
            logger.info("host_next: switching to slot %d", target)
            return self.sys.switch_host(target)

        if at == "haptic":
            try:
                pat = int(action_data)
            except ValueError:
                pat = 2
            return self.sys.trigger_haptic(pat)

        return False

    # ─── System bus signal handlers (GLib main thread) ───────────────────

    def _on_diverted_buttons(self, held_cids: set[int]) -> None:
        if self.gesture is not None:
            self.gesture.feed_diverted(held_cids)
        if self.actions is not None:
            self.actions.feed_diverted(held_cids)

    def _on_thumbwheel(self, delta: int, direction: int) -> None:
        if self.thumbwheel is not None:
            self.thumbwheel.feed(delta, direction)

    def _on_device_connected(self, connection: str, index: int) -> None:
        logger.info("device connected (%s, slot %d) — re-applying diversions",
                    connection, index)
        self._diverted.clear()
        self._trigger_cid = self._choose_trigger_cid()
        if self.gesture is not None:
            self.gesture._trigger_cid = self._trigger_cid
            self.gesture.rebind_device()
        if self.actions is not None:
            self.actions._skip_cids = {self._trigger_cid}
        self._apply_diversions()

    def _on_device_disconnected(self) -> None:
        logger.info("device disconnected")
        if self.actions is not None:
            self.actions.release_all()
        self._diverted.clear()

    # ─── gesture handlers ────────────────────────────────────────────────

    def _on_gesture_start(self) -> None:
        self._last_segment = object()
        self._last_ptr_push = 0.0
        # Crisp tactile Force-Touch press pulse on the Haptic Sense Thumb Pad
        if self.store.config.haptics.enabled:
            self._trigger_haptic_async(self.store.config.haptics.ring_boundary_pattern)

        def show():
            assert self.overlay is not None
            self._sync_overlay_style()
            profile = self.profiles.current_profile()
            self.overlay.load_profile(profile)
            self.overlay.show_at_cursor()
            if self.dbus is not None:
                self.dbus.emit_gesture_started()
            return False
        GLib.idle_add(show)

    def _on_gesture_move(self, dx: int, dy: int, selected: Optional[int]) -> None:
        seg_changed = selected != self._last_segment
        now = time.monotonic()
        if not seg_changed and (now - self._last_ptr_push) < 0.012:
            return
        self._last_ptr_push = now
        if seg_changed:
            self._last_segment = selected

        def update(mx=dx, my=dy, sel=selected, fire_haptic=seg_changed):
            assert self.overlay is not None
            if fire_haptic and sel is not None and self.store.config.haptics.enabled:
                pattern = self.store.config.haptics.ring_boundary_pattern
                self._trigger_haptic_async(pattern)
            self.overlay.update_pointer(mx, my, sel)
            return False
        GLib.idle_add(update)

    def _on_gesture_end(self, event: GestureEvent) -> None:
        def finish():
            assert self.overlay is not None
            seg = self.overlay.hide_and_pick()
            action_label = ""
            if seg:
                action_label = seg.label
                logger.info("gesture → %s (%s:%s)",
                            seg.label, seg.action_type, seg.action_data)
                if self.store.config.haptics.enabled:
                    self._trigger_haptic_async(self.store.config.haptics.ring_confirm_pattern)
                threading.Thread(
                    target=execute_action,
                    args=(seg.action_type, seg.action_data, self._execute_hardware_action),
                    daemon=True,
                ).start()
            else:
                if self.store.config.haptics.enabled:
                    self._trigger_haptic_async(self.store.config.haptics.ring_cancel_pattern)
            if self.dbus is not None:
                self.dbus.emit_gesture_ended(action_label)
            return False
        GLib.idle_add(finish)

    # ─── focus change ────────────────────────────────────────────────────

    def _on_focus_change(self, app_class: str, _title: str) -> None:
        if not app_class or app_class == self._last_app_id:
            return
        self._last_app_id = app_class

        def emit(a=app_class):
            self._apply_diversions()
            if self.dbus is not None:
                self.dbus.emit_profile_changed(a)
            return False
        GLib.idle_add(emit)

    # ─── Agent D-Bus service callbacks ───────────────────────────────────

    def _on_bus_acquired(self, conn, _name) -> None:
        self.dbus = AgentService(
            get_active_profile=self._svc_active_profile,
            get_gesture_status=self._svc_gesture_status,
            set_gesture_enabled=self._svc_set_gesture_enabled,
            reload_profiles=self._svc_reload_profiles,
            list_profiles=self._svc_list_profiles,
            test_action=self._svc_test_action,
            preview_ring=self._svc_preview_ring,
        )
        self.dbus.register(conn)

    def _on_name_lost(self, _conn, _name) -> None:
        logger.error("lost session bus name %s — another agent running?",
                     AGENT_BUS_NAME)

    def _svc_active_profile(self) -> dict:
        p = self.profiles.current_profile()
        return {
            "app_id": p.app_id,
            "app_name": p.app_name,
            "slices": [
                {"label": s.label, "icon": s.icon,
                 "action_type": s.action_type, "action_data": s.action_data}
                for s in p.slices
            ],
        }

    def _svc_gesture_status(self) -> tuple[bool, int]:
        active = bool(self.gesture and self.gesture.enabled)
        return active, self._trigger_cid

    def _svc_set_gesture_enabled(self, enabled: bool) -> bool:
        if self.gesture is None:
            return False
        self.gesture.set_enabled(enabled)
        self.store.config.daemon.autostart_gesture = bool(enabled)
        self.store.save()
        self._apply_diversions()
        return True

    def _svc_reload_profiles(self) -> bool:
        self.store.invalidate()
        cfg = self.store.config
        new_trigger = int(cfg.daemon.trigger_cid or TRIGGER_CANDIDATES[0])
        if new_trigger != self._trigger_cid:
            self._trigger_cid = new_trigger
            if self.gesture is not None:
                self.gesture._trigger_cid = new_trigger
            if self.actions is not None:
                self.actions._skip_cids = {new_trigger}
        if self.gesture is not None:
            self.gesture._cancel_radius = max(15, min(120, int(cfg.daemon.cancel_radius)))
            self.gesture.set_enabled(cfg.daemon.autostart_gesture)
        self._sync_overlay_style()
        self._apply_diversions()
        if self.notif_watcher is not None:
            self.notif_watcher.sync()
        return True

    def _svc_list_profiles(self) -> list[str]:
        return sorted(self.store.config.ring_profiles.keys())

    def _svc_test_action(self, action_type: str, action_data: str) -> bool:
        threading.Thread(
            target=execute_action,
            args=(action_type, action_data, self._execute_hardware_action),
            daemon=True,
        ).start()
        return True

    def _svc_preview_ring(self, duration_ms: int = 2800) -> bool:
        """Pop the real Wayland layer-shell Actions Ring at the cursor with a live sweep demo."""
        if self.overlay is None:
            return False
        self.store.invalidate()
        self._sync_overlay_style()
        dur = max(600, min(10000, int(duration_ms)))
        profile = self.profiles.current_profile()
        self.overlay.load_profile(profile)
        self.overlay.show_at_cursor()
        if self.store.config.haptics.enabled:
            self._trigger_haptic_async(self.store.config.haptics.ring_boundary_pattern)

        self._preview_gen += 1
        gen = self._preview_gen
        dz = float(self.store.config.daemon.cancel_radius or 40)

        # Smoothly sweep a virtual cursor vector across slices 0 -> 2 -> 5 -> confirm burst!
        def _sweep(seg_idx: int, haptic: bool) -> bool:
            if gen != self._preview_gen or self.overlay is None or not self.overlay.get_visible():
                return False
            if self.gesture and self.gesture.active:
                return False
            ang = -math.pi * 0.5 + (seg_idx % 8) * (math.tau / 8.0)
            rad = dz * 1.45
            self.overlay.update_pointer(math.cos(ang) * rad, math.sin(ang) * rad, seg_idx % 8)
            if haptic and self.store.config.haptics.enabled:
                self._trigger_haptic_async(self.store.config.haptics.ring_boundary_pattern)
            return False

        def _hide() -> bool:
            if gen == self._preview_gen and self.overlay is not None and not (self.gesture and self.gesture.active):
                self.overlay.hide_and_pick()
            return False

        GLib.timeout_add(340, _sweep, 0, True)
        GLib.timeout_add(920, _sweep, 2, True)
        GLib.timeout_add(1540, _sweep, 5, True)
        GLib.timeout_add(2120, _sweep, 7, False)
        GLib.timeout_add(dur, _hide)
        return True

    # ─── shutdown ────────────────────────────────────────────────────────

    def _on_signal(self) -> bool:
        logger.info("signal received — shutting down")
        self._loop.quit()
        return GLib.SOURCE_REMOVE

    def _teardown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True

        if self.notif_watcher is not None:
            self.notif_watcher.stop()
        if self.actions is not None:
            self.actions.release_all()

        if self.gesture is not None:
            try:
                self.gesture.stop()
            except Exception:
                logger.exception("gesture stop failed")

        for cid in list(self._diverted):
            try:
                self.sys.divert_button(cid, False)
            except Exception:
                pass
        self._diverted.clear()

        self.profiles.stop()
        if self.dbus is not None:
            self.dbus.unregister()
        if self._owner_id:
            Gio.bus_unown_name(self._owner_id)
            self._owner_id = 0
        self.sys.disconnect()
        logger.info("mx4-agent stopped")


def main() -> int:
    parser = argparse.ArgumentParser(prog="mx4-agent")
    parser.add_argument("--log-level", default="INFO")
    args, _ = parser.parse_known_args()

    configure_agent_logging(args.log_level)
    store = ConfigStore()
    _ = store.config

    agent = Agent(store)
    return agent.run()


if __name__ == "__main__":
    sys.exit(main())
