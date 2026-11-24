"""Shared D-Bus contract for mx4control 1.0.

Two services, defined here once so the daemon (server) and every client
(agent, CLI, GUI) agree on names, paths, and signatures:

* ``org.mx4control.System``  — system bus, owned by ``mx4-sysd`` (root).
  All device I/O. Reachable pre-login (greeter) per the installed
  ``org.mx4control.System.conf`` policy.
* ``org.mx4control.Agent``   — session bus, owned by ``mx4-agent``.
  Gesture/overlay/profile/thumbwheel state for the GUI.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import GLib, Gio  # noqa: E402


# ─────────────────────────────── identity ────────────────────────────────

INTERFACE_VERSION = 2

SYSTEM_BUS_NAME = "org.mx4control.System"
SYSTEM_OBJECT_PATH = "/org/mx4control/System"
SYSTEM_IFACE = "org.mx4control.System"

AGENT_BUS_NAME = "org.mx4control.Agent"
AGENT_OBJECT_PATH = "/org/mx4control/Agent"
AGENT_IFACE = "org.mx4control.Agent"

# polkit action ids gating privileged System methods
POLKIT_SWITCH_HOST = "org.mx4control.switch-host"
POLKIT_WRITE_CONFIG = "org.mx4control.write-config"
POLKIT_RAW_CALL = "org.mx4control.raw-call"


# ─────────────────────────── introspection XML ───────────────────────────

SYSTEM_INTROSPECTION_XML = f"""
<node>
  <interface name="{SYSTEM_IFACE}">
    <method name="GetInterfaceVersion">
      <arg type="u" name="version" direction="out"/>
    </method>

    <!-- Aggregate device state as a dict: connected, name, friendly_name,
         firmware, battery, battery_bucket, battery_level_name, charging,
         battery_status, connection, dpi, dpi_min, dpi_max, dpi_step,
         smartshift, smartshift_threshold, wheel_mode, ratchet_torque,
         tunable_torque, hires_enabled, hires_invert, thumbwheel_diverted,
         thumbwheel_invert, haptic_enabled, haptic_level, haptic_discrete,
         haptic_waveforms, force_supported, force_changeable, force_value,
         force_min, force_max, force_default, current_host, num_hosts,
         can_rename_hosts. -->
    <method name="GetState">
      <arg type="a{{sv}}" name="state" direction="out"/>
    </method>

    <method name="GetDpi"><arg type="u" name="dpi" direction="out"/></method>
    <method name="SetDpi">
      <arg type="u" name="dpi" direction="in"/>
      <arg type="b" name="persist" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>

    <method name="GetSmartShift">
      <arg type="b" name="enabled" direction="out"/>
      <arg type="u" name="threshold" direction="out"/>
    </method>
    <method name="SetSmartShift">
      <arg type="b" name="enabled" direction="in"/>
      <arg type="u" name="threshold" direction="in"/>
      <arg type="b" name="persist" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>
    <method name="SetScrollMode">
      <arg type="s" name="mode" direction="in"/>
      <arg type="u" name="threshold" direction="in"/>
      <arg type="u" name="torque" direction="in"/>
      <arg type="b" name="persist" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>

    <method name="SetHiRes">
      <arg type="b" name="enabled" direction="in"/>
      <arg type="b" name="invert" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>
    <method name="SetScrollTuning">
      <arg type="d" name="speed" direction="in"/>
      <arg type="u" name="smoothness" direction="in"/>
      <arg type="u" name="accel" direction="in"/>
      <arg type="b" name="persist" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>

    <method name="GetHaptic">
      <arg type="b" name="enabled" direction="out"/>
      <arg type="u" name="level" direction="out"/>
    </method>
    <method name="SetHaptic">
      <arg type="b" name="enabled" direction="in"/>
      <arg type="u" name="level" direction="in"/>
      <arg type="b" name="persist" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>
    <method name="TriggerHaptic">
      <arg type="y" name="pattern" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>

    <method name="GetForceButton">
      <arg type="a{{sv}}" name="info" direction="out"/>
    </method>
    <method name="SetForceThreshold">
      <arg type="u" name="value" direction="in"/>
      <arg type="b" name="persist" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>

    <method name="SetFriendlyName">
      <arg type="s" name="name" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>

    <method name="SwitchHost">
      <arg type="u" name="index" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>
    <method name="RenameHost">
      <arg type="u" name="index" direction="in"/>
      <arg type="s" name="name" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>
    <method name="GetHosts">
      <arg type="aa{{sv}}" name="hosts" direction="out"/>
    </method>

    <method name="GetButtons">
      <arg type="aa{{sv}}" name="buttons" direction="out"/>
    </method>
    <method name="DivertButton">
      <arg type="q" name="cid" direction="in"/>
      <arg type="b" name="diverted" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>
    <method name="RemapButton">
      <arg type="q" name="cid" direction="in"/>
      <arg type="q" name="target" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>
    <method name="ResetButton">
      <arg type="q" name="cid" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>

    <method name="SetThumbwheel">
      <arg type="b" name="diverted" direction="in"/>
      <arg type="b" name="invert" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>
    <method name="SetThumbwheelTuning">
      <arg type="s" name="mode" direction="in"/>
      <arg type="b" name="invert" direction="in"/>
      <arg type="d" name="speed" direction="in"/>
      <arg type="u" name="smoothness" direction="in"/>
      <arg type="u" name="accel" direction="in"/>
      <arg type="b" name="hires" direction="in"/>
      <arg type="b" name="haptic_detent" direction="in"/>
      <arg type="b" name="persist" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>
    <method name="SetThumbwheelHaptics">
      <arg type="u" name="density" direction="in"/>
      <arg type="y" name="pattern" direction="in"/>
      <arg type="b" name="persist" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>

    <method name="ProbeFeatures">
      <arg type="aa{{sv}}" name="features" direction="out"/>
    </method>

    <!-- Raw HID++ for reverse-engineering / debug. -->
    <method name="RawFeatureCall">
      <arg type="q" name="feature" direction="in"/>
      <arg type="y" name="function" direction="in"/>
      <arg type="ay" name="args" direction="in"/>
      <arg type="b" name="use_long" direction="in"/>
      <arg type="ay" name="response" direction="out"/>
    </method>

    <method name="ReloadConfig"><arg type="b" name="ok" direction="out"/></method>

    <signal name="DeviceConnected">
      <arg type="s" name="connection"/>
      <arg type="u" name="device_index"/>
    </signal>
    <signal name="DeviceDisconnected"/>
    <!-- Raw diverted-button CIDs currently held (REPROG_CONTROLS_V4
         divertedButtonsEvent), up to four, zero-padded dropped. -->
    <signal name="DivertedButtonEvent"><arg type="aq" name="cids"/></signal>
    <!-- Diverted thumb-wheel delta (signed int16) + direction (-1/0/+1). -->
    <signal name="ThumbwheelEvent">
      <arg type="i" name="delta"/>
      <arg type="i" name="direction"/>
    </signal>
    <signal name="StateChanged"><arg type="a{{sv}}" name="delta"/></signal>
  </interface>
</node>
"""

AGENT_INTROSPECTION_XML = f"""
<node>
  <interface name="{AGENT_IFACE}">
    <method name="GetInterfaceVersion">
      <arg type="u" name="version" direction="out"/>
    </method>
    <method name="GetActiveProfile">
      <arg type="a{{sv}}" name="profile" direction="out"/>
    </method>
    <method name="GetGestureStatus">
      <arg type="b" name="active" direction="out"/>
      <arg type="q" name="trigger_cid" direction="out"/>
    </method>
    <method name="SetGestureEnabled">
      <arg type="b" name="enabled" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>
    <method name="ReloadProfiles"><arg type="b" name="ok" direction="out"/></method>
    <method name="ListProfiles"><arg type="as" name="ids" direction="out"/></method>
    <method name="TestAction">
      <arg type="s" name="action_type" direction="in"/>
      <arg type="s" name="action_data" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>
    <method name="PreviewRing">
      <arg type="u" name="duration_ms" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>

    <signal name="GestureStarted"/>
    <signal name="GestureEnded"><arg type="s" name="action"/></signal>
    <signal name="ProfileChanged"><arg type="s" name="app_id"/></signal>
  </interface>
</node>
"""


# ─────────────────────────── GVariant helpers ────────────────────────────

def _pack_value(v: Any) -> GLib.Variant:
    """Pack a Python scalar into a GLib.Variant for an a{sv} entry."""
    if isinstance(v, bool):
        return GLib.Variant("b", v)
    if isinstance(v, int):
        return GLib.Variant("x", v)
    if isinstance(v, float):
        return GLib.Variant("d", v)
    if isinstance(v, str):
        return GLib.Variant("s", v)
    if isinstance(v, (list, tuple)):
        return GLib.Variant("av", [_pack_value(i) for i in v])
    if isinstance(v, dict):
        return GLib.Variant("a{sv}", {str(k): _pack_value(val) for k, val in v.items()})
    return GLib.Variant("s", str(v))


def dict_to_asv(d: dict[str, Any]) -> GLib.Variant:
    """Build an ``a{sv}`` GVariant from a flat/nested Python dict."""
    return GLib.Variant("a{sv}", {str(k): _pack_value(v) for k, v in d.items()})


def asv_to_dict(variant: GLib.Variant) -> dict[str, Any]:
    """Unpack an ``a{sv}`` (or a tuple wrapping one) GVariant to a dict."""
    if variant is None:
        return {}
    if variant.get_type_string().startswith("("):
        variant = variant.get_child_value(0)
    out: dict[str, Any] = {}
    for i in range(variant.n_children()):
        entry = variant.get_child_value(i)
        key = entry.get_child_value(0).get_string()
        out[key] = entry.get_child_value(1).unpack()
    return out


def system_proxy(timeout_ms: int | None = None) -> Gio.DBusProxy:
    """Return a proxy to the system daemon (does not fail if it's down)."""
    return Gio.DBusProxy.new_for_bus_sync(
        Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
        SYSTEM_BUS_NAME, SYSTEM_OBJECT_PATH, SYSTEM_IFACE, None,
    )


def agent_proxy() -> Gio.DBusProxy:
    return Gio.DBusProxy.new_for_bus_sync(
        Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None,
        AGENT_BUS_NAME, AGENT_OBJECT_PATH, AGENT_IFACE, None,
    )


class DaemonUnavailable(RuntimeError):
    """Raised when the target D-Bus service has no owner (daemon down)."""


# ─────────────────────────── typed clients ───────────────────────────────

class SystemClient:
    """Synchronous client + optional signal subscriber for ``org.mx4control.System``."""

    def __init__(self, timeout_ms: int = 4000):
        self._timeout = timeout_ms
        self._proxy = system_proxy()
        self._signal_id = 0
        self._on_diverted: Optional[Callable[[set[int]], None]] = None
        self._on_state_changed: Optional[Callable[[dict[str, Any]], None]] = None
        self._on_connected: Optional[Callable[[str, int], None]] = None
        self._on_disconnected: Optional[Callable[[], None]] = None

    def available(self) -> bool:
        return self._proxy.get_name_owner() is not None

    def _call(self, method: str, body: GLib.Variant | None,
              timeout_ms: int | None = None) -> GLib.Variant:
        if not self.available():
            raise DaemonUnavailable("mx4-sysd is not running")
        return self._proxy.call_sync(
            method, body, Gio.DBusCallFlags.NONE,
            timeout_ms or self._timeout, None,
        )

    def get_interface_version(self) -> int:
        try:
            return int(self._call("GetInterfaceVersion", None).unpack()[0])
        except Exception:
            return 1

    def get_state(self) -> dict:
        return asv_to_dict(self._call("GetState", None))

    def get_dpi(self) -> int:
        return int(self._call("GetDpi", None).unpack()[0])

    def set_dpi(self, dpi: int, persist: bool = True) -> bool:
        return bool(self._call("SetDpi", GLib.Variant("(ub)", (dpi, persist))).unpack()[0])

    def get_smartshift(self) -> tuple[bool, int]:
        en, thr = self._call("GetSmartShift", None).unpack()
        return bool(en), int(thr)

    def set_smartshift(self, enabled: bool, threshold: int = 15, persist: bool = True) -> bool:
        return bool(self._call(
            "SetSmartShift", GLib.Variant("(bub)", (enabled, threshold, persist))).unpack()[0])

    def set_scroll_mode(
        self, mode: str, threshold: int = 15, torque: int = 75, persist: bool = True
    ) -> bool:
        return bool(self._call(
            "SetScrollMode",
            GLib.Variant("(suub)", (str(mode), int(threshold), int(torque), bool(persist))),
        ).unpack()[0])

    def set_hires(self, enabled: bool, invert: bool = False) -> bool:
        return bool(self._call("SetHiRes", GLib.Variant("(bb)", (enabled, invert))).unpack()[0])

    def set_scroll_tuning(
        self, speed: float = 1.0, smoothness: int = 0, accel: int = 0, persist: bool = True
    ) -> bool:
        return bool(self._call(
            "SetScrollTuning",
            GLib.Variant("(duub)", (float(speed), int(smoothness), int(accel), bool(persist))),
        ).unpack()[0])

    def get_haptic(self) -> tuple[bool, int]:
        en, lvl = self._call("GetHaptic", None).unpack()
        return bool(en), int(lvl)

    def set_haptic(self, enabled: bool, level: int = 50, persist: bool = True) -> bool:
        return bool(self._call(
            "SetHaptic",
            GLib.Variant("(bub)", (bool(enabled), int(level), bool(persist))),
        ).unpack()[0])

    def trigger_haptic(self, pattern: int) -> bool:
        return bool(self._call("TriggerHaptic", GLib.Variant("(y)", (pattern,))).unpack()[0])

    def get_force_button(self) -> dict:
        return asv_to_dict(self._call("GetForceButton", None))

    def set_force_threshold(self, value: int, persist: bool = True) -> bool:
        return bool(self._call(
            "SetForceThreshold",
            GLib.Variant("(ub)", (int(value), bool(persist))),
        ).unpack()[0])

    def set_friendly_name(self, name: str) -> bool:
        return bool(self._call("SetFriendlyName", GLib.Variant("(s)", (str(name),))).unpack()[0])

    def switch_host(self, index: int) -> bool:
        return bool(self._call("SwitchHost", GLib.Variant("(u)", (index,))).unpack()[0])

    def rename_host(self, index: int, name: str) -> bool:
        return bool(self._call(
            "RenameHost", GLib.Variant("(us)", (int(index), str(name)))
        ).unpack()[0])

    def get_hosts(self) -> list[dict]:
        return list(self._call("GetHosts", None).unpack()[0])

    def get_buttons(self) -> list[dict]:
        return list(self._call("GetButtons", None).unpack()[0])

    def divert_button(self, cid: int, diverted: bool) -> bool:
        return bool(self._call("DivertButton", GLib.Variant("(qb)", (cid, diverted))).unpack()[0])

    def remap_button(self, cid: int, target: int) -> bool:
        return bool(self._call("RemapButton", GLib.Variant("(qq)", (cid, target))).unpack()[0])

    def reset_button(self, cid: int) -> bool:
        return bool(self._call("ResetButton", GLib.Variant("(q)", (cid,))).unpack()[0])

    def set_thumbwheel(self, diverted: bool, invert: bool = False) -> bool:
        return bool(self._call("SetThumbwheel", GLib.Variant("(bb)", (diverted, invert))).unpack()[0])

    def set_thumbwheel_tuning(
        self,
        mode: str = "hd_scroll",
        invert: bool = False,
        speed: float = 1.0,
        smoothness: int = 35,
        accel: int = 25,
        hires: bool = True,
        haptic_detent: bool = False,
        persist: bool = True,
    ) -> bool:
        return bool(self._call(
            "SetThumbwheelTuning",
            GLib.Variant(
                "(sbduubbb)",
                (
                    str(mode),
                    bool(invert),
                    float(speed),
                    int(smoothness),
                    int(accel),
                    bool(hires),
                    bool(haptic_detent),
                    bool(persist),
                ),
            ),
        ).unpack()[0])

    def set_thumbwheel_haptics(
        self, density: int = 6, pattern: int = 1, persist: bool = True
    ) -> bool:
        return bool(self._call(
            "SetThumbwheelHaptics",
            GLib.Variant("(uyb)", (int(density), int(pattern) & 0xFF, bool(persist))),
        ).unpack()[0])

    def probe_features(self) -> list[dict]:
        return list(self._call("ProbeFeatures", None, timeout_ms=15000).unpack()[0])

    def raw_call(self, feature: int, fn: int, args: list[int], use_long: bool = False) -> bytes:
        r = self._call("RawFeatureCall",
                       GLib.Variant("(qyayb)", (feature, fn, bytes(args), use_long)))
        return bytes(r.unpack()[0])

    def reload_config(self) -> bool:
        return bool(self._call("ReloadConfig", None).unpack()[0])

    # ─── live signal subscriptions (for GUI) ────────────────────────────

    def subscribe_signals(
        self,
        *,
        on_diverted: Optional[Callable[[set[int]], None]] = None,
        on_thumbwheel: Optional[Callable[[int, int], None]] = None,
        on_state_changed: Optional[Callable[[dict[str, Any]], None]] = None,
        on_connected: Optional[Callable[[str, int], None]] = None,
        on_disconnected: Optional[Callable[[], None]] = None,
    ) -> None:
        if on_diverted is not None:
            self._on_diverted = on_diverted
        if on_thumbwheel is not None:
            self._on_thumbwheel = on_thumbwheel
        if on_state_changed is not None:
            self._on_state_changed = on_state_changed
        if on_connected is not None:
            self._on_connected = on_connected
        if on_disconnected is not None:
            self._on_disconnected = on_disconnected
        if not self._signal_id:
            self._signal_id = self._proxy.connect("g-signal", self._on_g_signal)

    def _on_g_signal(self, _proxy, _sender, signal_name: str, params: GLib.Variant) -> None:
        try:
            if signal_name == "DivertedButtonEvent" and self._on_diverted:
                arr = params.get_child_value(0)
                cids = {int(arr.get_child_value(i).get_uint16()) for i in range(arr.n_children())}
                cids.discard(0)
                self._on_diverted(cids)
            elif signal_name == "ThumbwheelEvent" and getattr(self, "_on_thumbwheel", None):
                self._on_thumbwheel(
                    int(params.get_child_value(0).get_int32()),
                    int(params.get_child_value(1).get_int32()),
                )
            elif signal_name == "StateChanged" and self._on_state_changed:
                self._on_state_changed(asv_to_dict(params))
            elif signal_name == "DeviceConnected" and self._on_connected:
                self._on_connected(
                    params.get_child_value(0).get_string(),
                    int(params.get_child_value(1).get_uint32()),
                )
            elif signal_name == "DeviceDisconnected" and self._on_disconnected:
                self._on_disconnected()
        except Exception:
            pass


class AgentClient:
    """Synchronous client for ``org.mx4control.Agent`` (session bus)."""

    def __init__(self, timeout_ms: int = 2000):
        self._timeout = timeout_ms
        self._proxy = agent_proxy()
        self._signal_id = 0
        self._on_profile: Optional[Callable[[str], None]] = None

    def subscribe_profile_changed(self, cb: Callable[[str], None]) -> None:
        self._on_profile = cb
        if not self._signal_id:
            self._signal_id = self._proxy.connect("g-signal", self._on_g_signal)

    def _on_g_signal(self, _proxy, _sender, signal_name: str, params: GLib.Variant) -> None:
        try:
            if signal_name == "ProfileChanged" and self._on_profile:
                self._on_profile(params.get_child_value(0).get_string())
        except Exception:
            pass

    def available(self) -> bool:
        return self._proxy.get_name_owner() is not None

    def get_interface_version(self) -> int:
        if not self.available():
            return 0
        try:
            return int(self._proxy.call_sync(
                "GetInterfaceVersion", None, Gio.DBusCallFlags.NONE, self._timeout, None
            ).unpack()[0])
        except Exception:
            return 1

    def get_active_profile(self) -> dict:
        if not self.available():
            return {}
        return asv_to_dict(self._proxy.call_sync(
            "GetActiveProfile", None, Gio.DBusCallFlags.NONE, self._timeout, None))

    def gesture_status(self) -> tuple[bool, int]:
        if not self.available():
            return False, 0
        active, cid = self._proxy.call_sync(
            "GetGestureStatus", None, Gio.DBusCallFlags.NONE, self._timeout, None).unpack()
        return bool(active), int(cid)

    def set_gesture_enabled(self, enabled: bool) -> bool:
        if not self.available():
            return False
        return bool(self._proxy.call_sync(
            "SetGestureEnabled", GLib.Variant("(b)", (bool(enabled),)),
            Gio.DBusCallFlags.NONE, self._timeout, None,
        ).unpack()[0])

    def list_profiles(self) -> list[str]:
        if not self.available():
            return []
        return list(self._proxy.call_sync(
            "ListProfiles", None, Gio.DBusCallFlags.NONE, self._timeout, None,
        ).unpack()[0])

    def reload_profiles(self) -> bool:
        if not self.available():
            return False
        return bool(self._proxy.call_sync(
            "ReloadProfiles", None, Gio.DBusCallFlags.NONE,
            self._timeout, None).unpack()[0])

    def test_action(self, action_type: str, action_data: str) -> bool:
        if not self.available():
            return False
        return bool(self._proxy.call_sync(
            "TestAction", GLib.Variant("(ss)", (str(action_type), str(action_data))),
            Gio.DBusCallFlags.NONE, self._timeout, None,
        ).unpack()[0])

    def preview_ring(self, duration_ms: int = 2600) -> bool:
        if not self.available():
            return False
        return bool(self._proxy.call_sync(
            "PreviewRing", GLib.Variant("(u)", (max(400, min(10000, int(duration_ms))),)),
            Gio.DBusCallFlags.NONE, self._timeout, None,
        ).unpack()[0])
