"""The agent's own session-bus service: ``org.mx4control.Agent``."""

from __future__ import annotations

import logging
from typing import Callable, Optional

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import GLib, Gio  # noqa: E402

from ..common.dbus import (
    AGENT_IFACE,
    AGENT_INTROSPECTION_XML,
    AGENT_OBJECT_PATH,
    INTERFACE_VERSION,
    dict_to_asv,
)

logger = logging.getLogger(__name__)


class AgentService:
    """Registers the ``org.mx4control.Agent`` object on a connection."""

    def __init__(
        self,
        *,
        get_active_profile: Callable[[], dict],
        get_gesture_status: Callable[[], tuple[bool, int]],
        set_gesture_enabled: Callable[[bool], bool],
        reload_profiles: Callable[[], bool],
        list_profiles: Callable[[], list[str]],
        test_action: Optional[Callable[[str, str], bool]] = None,
        preview_ring: Optional[Callable[[int], bool]] = None,
    ):
        self._get_active_profile = get_active_profile
        self._get_gesture_status = get_gesture_status
        self._set_gesture_enabled = set_gesture_enabled
        self._reload_profiles = reload_profiles
        self._list_profiles = list_profiles
        self._test_action = test_action
        self._preview_ring = preview_ring

        self._conn: Optional[Gio.DBusConnection] = None
        self._reg_id: int = 0
        node = Gio.DBusNodeInfo.new_for_xml(AGENT_INTROSPECTION_XML)
        self._iface_info = node.lookup_interface(AGENT_IFACE)

    def register(self, conn: Gio.DBusConnection) -> bool:
        self._conn = conn
        try:
            self._reg_id = conn.register_object(
                AGENT_OBJECT_PATH,
                self._iface_info,
                self._on_method_call,
                None,
                None,
            )
        except GLib.Error as e:
            logger.error("failed to register Agent object: %s", e.message)
            return False
        logger.info("registered %s at %s", AGENT_IFACE, AGENT_OBJECT_PATH)
        return True

    def unregister(self) -> None:
        if self._conn is not None and self._reg_id:
            self._conn.unregister_object(self._reg_id)
        self._reg_id = 0

    def _on_method_call(
        self, _conn, _sender, _path, _iface, method, params, invocation,
    ) -> None:
        try:
            if method == "GetInterfaceVersion":
                invocation.return_value(GLib.Variant("(u)", (INTERFACE_VERSION,)))

            elif method == "GetActiveProfile":
                profile = self._get_active_profile() or {}
                invocation.return_value(GLib.Variant.new_tuple(dict_to_asv(profile)))

            elif method == "GetGestureStatus":
                active, trigger_cid = self._get_gesture_status()
                invocation.return_value(
                    GLib.Variant("(bq)", (bool(active), int(trigger_cid) & 0xFFFF))
                )

            elif method == "SetGestureEnabled":
                enabled = params.get_child_value(0).get_boolean()
                ok = bool(self._set_gesture_enabled(enabled))
                invocation.return_value(GLib.Variant("(b)", (ok,)))

            elif method == "ReloadProfiles":
                ok = bool(self._reload_profiles())
                invocation.return_value(GLib.Variant("(b)", (ok,)))

            elif method == "ListProfiles":
                ids = [str(x) for x in (self._list_profiles() or [])]
                invocation.return_value(GLib.Variant("(as)", (ids,)))

            elif method == "TestAction":
                at = params.get_child_value(0).get_string()
                ad = params.get_child_value(1).get_string()
                ok = bool(self._test_action(at, ad)) if self._test_action else False
                invocation.return_value(GLib.Variant("(b)", (ok,)))

            elif method == "PreviewRing":
                dur = int(params.get_child_value(0).get_uint32())
                ok = bool(self._preview_ring(dur)) if self._preview_ring else False
                invocation.return_value(GLib.Variant("(b)", (ok,)))

            else:
                invocation.return_error_literal(
                    Gio.dbus_error_quark(),
                    Gio.DBusError.UNKNOWN_METHOD,
                    f"unknown method: {method}",
                )
        except Exception as e:
            logger.exception("Agent.%s raised", method)
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.FAILED, str(e),
            )

    def emit_gesture_started(self) -> None:
        self._emit("GestureStarted", None)

    def emit_gesture_ended(self, action: str) -> None:
        self._emit("GestureEnded", GLib.Variant("(s)", (action or "",)))

    def emit_profile_changed(self, app_id: str) -> None:
        self._emit("ProfileChanged", GLib.Variant("(s)", (app_id or "",)))

    def _emit(self, signal: str, body: Optional[GLib.Variant]) -> None:
        if self._conn is None:
            return
        try:
            self._conn.emit_signal(
                None, AGENT_OBJECT_PATH, AGENT_IFACE, signal, body,
            )
        except GLib.Error as e:
            logger.debug("emit %s failed: %s", signal, e.message)
