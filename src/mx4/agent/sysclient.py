"""Thin client for the root system daemon (``org.mx4control.System``)."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import GLib, Gio  # noqa: E402

from ..common.dbus import SYSTEM_IFACE, asv_to_dict, system_proxy

logger = logging.getLogger(__name__)

_CALL_TIMEOUT_MS = 2000


DivertedButtonsCallback = Callable[[set[int]], None]
ThumbwheelCallback = Callable[[int, int], None]
DeviceConnectedCallback = Callable[[str, int], None]
DeviceDisconnectedCallback = Callable[[], None]


class SystemClient:
    """Wraps the System proxy with friendly, fail-soft methods."""

    def __init__(self) -> None:
        self._proxy: Optional[Gio.DBusProxy] = None
        self._signal_handler_id: int = 0
        self._on_diverted: Optional[DivertedButtonsCallback] = None
        self._on_thumbwheel: Optional[ThumbwheelCallback] = None
        self._on_connected: Optional[DeviceConnectedCallback] = None
        self._on_disconnected: Optional[DeviceDisconnectedCallback] = None

    # ─── connection ──────────────────────────────────────────────────────

    def connect(self) -> bool:
        if self._proxy is not None:
            return True
        try:
            self._proxy = system_proxy(_CALL_TIMEOUT_MS)
            logger.info("connected to %s", SYSTEM_IFACE)
            return True
        except GLib.Error as e:
            logger.warning("system daemon unreachable: %s", e.message)
            self._proxy = None
            return False

    @property
    def available(self) -> bool:
        return self._proxy is not None and self._proxy.get_name_owner() is not None

    def _call(self, method: str, args: Optional[GLib.Variant]) -> Optional[GLib.Variant]:
        if self._proxy is None and not self.connect():
            logger.debug("skip %s: system daemon unavailable", method)
            return None
        assert self._proxy is not None
        try:
            return self._proxy.call_sync(
                method, args, Gio.DBusCallFlags.NONE, _CALL_TIMEOUT_MS, None,
            )
        except GLib.Error as e:
            logger.warning("System.%s failed: %s", method, e.message)
            return None

    # ─── device methods ──────────────────────────────────────────────────

    def trigger_haptic(self, pattern: int) -> bool:
        r = self._call("TriggerHaptic", GLib.Variant("(y)", (int(pattern) & 0xFF,)))
        return bool(r and r.get_child_value(0).get_boolean())

    def divert_button(self, cid: int, on: bool) -> bool:
        r = self._call(
            "DivertButton", GLib.Variant("(qb)", (int(cid) & 0xFFFF, bool(on))),
        )
        return bool(r and r.get_child_value(0).get_boolean())

    def set_dpi(self, dpi: int, persist: bool = True) -> bool:
        r = self._call(
            "SetDpi", GLib.Variant("(ub)", (int(dpi) & 0xFFFFFFFF, bool(persist))),
        )
        return bool(r and r.get_child_value(0).get_boolean())

    def set_smartshift(self, enabled: bool, thr: int, persist: bool = False) -> bool:
        r = self._call(
            "SetSmartShift",
            GLib.Variant("(bub)", (bool(enabled), int(thr) & 0xFFFFFFFF, bool(persist))),
        )
        return bool(r and r.get_child_value(0).get_boolean())

    def set_scroll_mode(
        self, mode: str, thr: int, torque: int = 75, persist: bool = True
    ) -> bool:
        r = self._call(
            "SetScrollMode",
            GLib.Variant("(suub)", (str(mode), int(thr), int(torque), bool(persist))),
        )
        return bool(r and r.get_child_value(0).get_boolean())

    def switch_host(self, index: int) -> bool:
        r = self._call("SwitchHost", GLib.Variant("(u)", (int(index),)))
        return bool(r and r.get_child_value(0).get_boolean())

    def get_hosts(self) -> list[dict[str, Any]]:
        r = self._call("GetHosts", None)
        if r is None:
            return []
        arr = r.get_child_value(0)
        return [asv_to_dict(arr.get_child_value(i)) for i in range(arr.n_children())]

    def get_state(self) -> dict[str, Any]:
        r = self._call("GetState", None)
        if r is None:
            return {"connected": False}
        return asv_to_dict(r)

    def get_buttons(self) -> list[dict[str, Any]]:
        r = self._call("GetButtons", None)
        if r is None:
            return []
        arr = r.get_child_value(0)
        return [asv_to_dict(arr.get_child_value(i)) for i in range(arr.n_children())]

    # ─── signal subscription ─────────────────────────────────────────────

    def connect_diverted_buttons(self, callback: DivertedButtonsCallback) -> None:
        self._on_diverted = callback
        self._ensure_signal_handler()

    def connect_thumbwheel(self, callback: ThumbwheelCallback) -> None:
        self._on_thumbwheel = callback
        self._ensure_signal_handler()

    def connect_device_signals(
        self,
        *,
        on_connected: Optional[DeviceConnectedCallback] = None,
        on_disconnected: Optional[DeviceDisconnectedCallback] = None,
    ) -> None:
        if on_connected is not None:
            self._on_connected = on_connected
        if on_disconnected is not None:
            self._on_disconnected = on_disconnected
        self._ensure_signal_handler()

    def _ensure_signal_handler(self) -> None:
        if self._proxy is None and not self.connect():
            logger.debug("cannot subscribe to signals: daemon unavailable")
            return
        assert self._proxy is not None
        if self._signal_handler_id:
            return
        self._signal_handler_id = self._proxy.connect("g-signal", self._on_g_signal)

    def _on_g_signal(self, _proxy, _sender, signal_name, params) -> None:
        try:
            if signal_name == "DivertedButtonEvent" and self._on_diverted:
                self._on_diverted(_decode_cids(params))
            elif signal_name == "ThumbwheelEvent" and self._on_thumbwheel:
                delta = int(params.get_child_value(0).get_int32())
                direction = int(params.get_child_value(1).get_int32())
                self._on_thumbwheel(delta, direction)
            elif signal_name == "DeviceConnected" and self._on_connected:
                conn = params.get_child_value(0).get_string()
                idx = int(params.get_child_value(1).get_uint32())
                self._on_connected(conn, idx)
            elif signal_name == "DeviceDisconnected" and self._on_disconnected:
                self._on_disconnected()
        except Exception:
            logger.exception("error handling System signal %s", signal_name)

    def disconnect(self) -> None:
        if self._proxy is not None and self._signal_handler_id:
            try:
                self._proxy.disconnect(self._signal_handler_id)
            except Exception:
                pass
        self._signal_handler_id = 0
        self._proxy = None


def _decode_cids(params: GLib.Variant) -> set[int]:
    if params is None:
        return set()
    arr = params
    if arr.get_type_string().startswith("("):
        arr = arr.get_child_value(0)
    out: set[int] = set()
    for i in range(arr.n_children()):
        cid = int(arr.get_child_value(i).get_uint16())
        if cid:
            out.add(cid)
    return out
