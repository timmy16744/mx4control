"""The ``org.mx4control.System`` D-Bus service (system bus)."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from ..common.dbus import (
    INTERFACE_VERSION,
    SYSTEM_BUS_NAME,
    SYSTEM_IFACE,
    SYSTEM_INTROSPECTION_XML,
    SYSTEM_OBJECT_PATH,
    dict_to_asv,
)

logger = logging.getLogger(__name__)


class SystemDBusService:
    """Marshals D-Bus calls on ``org.mx4control.System`` to the supervisor."""

    def __init__(self, backend: Any) -> None:
        self._backend = backend
        self._node = Gio.DBusNodeInfo.new_for_xml(SYSTEM_INTROSPECTION_XML)
        self._iface = self._node.lookup_interface(SYSTEM_IFACE)
        self._conn: Optional[Gio.DBusConnection] = None
        self._reg_id = 0
        self._owner_id = 0
        self._on_ready: Optional[Callable[[bool], None]] = None

    def start(self, on_ready: Optional[Callable[[bool], None]] = None) -> None:
        self._on_ready = on_ready
        self._owner_id = Gio.bus_own_name(
            Gio.BusType.SYSTEM, SYSTEM_BUS_NAME,
            Gio.BusNameOwnerFlags.NONE,
            self._on_bus_acquired, self._on_name_acquired, self._on_name_lost,
        )

    def stop(self) -> None:
        if self._reg_id and self._conn:
            self._conn.unregister_object(self._reg_id)
            self._reg_id = 0
        if self._owner_id:
            Gio.bus_unown_name(self._owner_id)
            self._owner_id = 0

    # ─── name lifecycle ───────────────────────────────────────────────────

    def _on_bus_acquired(self, conn: Gio.DBusConnection, name: str) -> None:
        self._conn = conn
        try:
            self._reg_id = conn.register_object(
                SYSTEM_OBJECT_PATH, self._iface, self._handle_call, None, None)
            logger.info("registered %s at %s", SYSTEM_IFACE, SYSTEM_OBJECT_PATH)
        except Exception:
            logger.exception("register_object failed")

    def _on_name_acquired(self, conn: Gio.DBusConnection, name: str) -> None:
        logger.info("owning bus name %s", name)
        if self._on_ready:
            self._on_ready(True)

    def _on_name_lost(self, conn: Gio.DBusConnection, name: str) -> None:
        logger.error("lost/failed bus name %s (already running? policy missing?)", name)
        if self._on_ready:
            self._on_ready(False)

    # ─── method dispatch ──────────────────────────────────────────────────

    def _handle_call(self, conn, sender, path, iface, method, params,
                     invocation) -> None:
        args = tuple(params.unpack())
        # Offload slow 45-feature HID++ probing so smooth scroll & buttons never stall
        if method == "ProbeFeatures":
            import threading
            def _probe_worker():
                try:
                    result = _array_of_asv(self._backend.probe_features())
                    GLib.idle_add(invocation.return_value, GLib.Variant.new_tuple(result))
                except Exception as e:
                    logger.exception("ProbeFeatures failed")
                    GLib.idle_add(
                        invocation.return_dbus_error,
                        "org.mx4control.Error.Failed",
                        f"ProbeFeatures: {e}",
                    )
            threading.Thread(target=_probe_worker, daemon=True, name="mx4-probe").start()
            return
        try:
            result = self._invoke(method, args)
            invocation.return_value(result)
        except Exception as e:
            logger.exception("method %s failed", method)
            invocation.return_dbus_error(
                "org.mx4control.Error.Failed", f"{method}: {e}")

    def _invoke(self, method: str, a: tuple) -> GLib.Variant:
        b = self._backend
        if method == "GetInterfaceVersion":
            return GLib.Variant("(u)", (INTERFACE_VERSION,))
        if method == "GetState":
            return GLib.Variant.new_tuple(dict_to_asv(b.get_state()))
        if method == "GetDpi":
            return GLib.Variant("(u)", (int(b.get_dpi()),))
        if method == "SetDpi":
            return GLib.Variant("(b)", (b.set_dpi(int(a[0]), bool(a[1])),))
        if method == "GetSmartShift":
            en, thr = b.get_smartshift()
            return GLib.Variant("(bu)", (bool(en), int(thr)))
        if method == "SetSmartShift":
            return GLib.Variant("(b)", (b.set_smartshift(bool(a[0]), int(a[1]), bool(a[2])),))
        if method == "SetScrollMode":
            return GLib.Variant("(b)", (b.set_scroll_mode(str(a[0]), int(a[1]), int(a[2]), bool(a[3])),))
        if method == "SetHiRes":
            return GLib.Variant("(b)", (b.set_hires(bool(a[0]), bool(a[1])),))
        if method == "SetScrollTuning":
            return GLib.Variant(
                "(b)",
                (b.set_scroll_tuning(float(a[0]), int(a[1]), int(a[2]), bool(a[3])),),
            )
        if method == "GetHaptic":
            en, lvl = b.get_haptic()
            return GLib.Variant("(bu)", (bool(en), int(lvl)))
        if method == "SetHaptic":
            return GLib.Variant("(b)", (b.set_haptic(bool(a[0]), int(a[1]), bool(a[2])),))
        if method == "TriggerHaptic":
            return GLib.Variant("(b)", (b.trigger_haptic(int(a[0])),))
        if method == "GetForceButton":
            return GLib.Variant.new_tuple(dict_to_asv(b.get_force_button()))
        if method == "SetForceThreshold":
            return GLib.Variant("(b)", (b.set_force_threshold(int(a[0]), bool(a[1])),))
        if method == "SetFriendlyName":
            return GLib.Variant("(b)", (b.set_friendly_name(str(a[0])),))
        if method == "SwitchHost":
            return GLib.Variant("(b)", (b.switch_host(int(a[0])),))
        if method == "RenameHost":
            return GLib.Variant("(b)", (b.rename_host(int(a[0]), str(a[1])),))
        if method == "GetHosts":
            return GLib.Variant.new_tuple(_array_of_asv(b.get_hosts()))
        if method == "GetButtons":
            return GLib.Variant.new_tuple(_array_of_asv(b.get_buttons()))
        if method == "DivertButton":
            return GLib.Variant("(b)", (b.divert_button(int(a[0]), bool(a[1])),))
        if method == "RemapButton":
            return GLib.Variant("(b)", (b.remap_button(int(a[0]), int(a[1])),))
        if method == "ResetButton":
            return GLib.Variant("(b)", (b.reset_button(int(a[0])),))
        if method == "SetThumbwheel":
            return GLib.Variant("(b)", (b.set_thumbwheel(bool(a[0]), bool(a[1])),))
        if method == "SetThumbwheelTuning":
            return GLib.Variant(
                "(b)",
                (
                    b.set_thumbwheel_tuning(
                        str(a[0]),
                        bool(a[1]),
                        float(a[2]),
                        int(a[3]),
                        int(a[4]),
                        bool(a[5]),
                        bool(a[6]),
                        bool(a[7]),
                    ),
                ),
            )
        if method == "SetThumbwheelHaptics":
            return GLib.Variant(
                "(b)",
                (b.set_thumbwheel_haptics(int(a[0]), int(a[1]), bool(a[2])),),
            )
        if method == "ProbeFeatures":
            return GLib.Variant.new_tuple(_array_of_asv(b.probe_features()))
        if method == "RawFeatureCall":
            resp = b.raw_call(int(a[0]), int(a[1]), list(a[2]), bool(a[3])) or b""
            return GLib.Variant("(ay)", (list(resp),))
        if method == "ReloadConfig":
            return GLib.Variant("(b)", (b.reload_config(),))
        raise ValueError(f"unknown method {method}")

    # ─── signal emission (call on the GLib main thread) ───────────────────

    def _emit(self, name: str, body: Optional[GLib.Variant]) -> None:
        if not self._conn:
            return
        try:
            self._conn.emit_signal(None, SYSTEM_OBJECT_PATH, SYSTEM_IFACE, name, body)
        except Exception:
            logger.debug("emit %s failed", name, exc_info=True)

    def emit_connected(self, connection: str, device_index: int) -> None:
        self._emit("DeviceConnected", GLib.Variant("(su)", (connection, device_index)))

    def emit_disconnected(self) -> None:
        self._emit("DeviceDisconnected", None)

    def emit_diverted_button(self, cids: list[int]) -> None:
        self._emit("DivertedButtonEvent", GLib.Variant("(aq)", (cids,)))

    def emit_thumbwheel(self, delta: int, direction: int) -> None:
        self._emit("ThumbwheelEvent", GLib.Variant("(ii)", (int(delta), int(direction))))

    def emit_state_changed(self, delta: dict[str, Any]) -> None:
        self._emit("StateChanged", GLib.Variant.new_tuple(dict_to_asv(delta)))


def _array_of_asv(items: list[dict]) -> GLib.Variant:
    children = [dict_to_asv(d) for d in items]
    return GLib.Variant.new_array(GLib.VariantType("a{sv}"), children)
