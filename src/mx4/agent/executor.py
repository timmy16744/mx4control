"""Execute a ring slice's / button's / thumbwheel's action.

Pure stdlib (no GTK / Gio / Wayland) so shortcut parsing is unit-testable
anywhere. Supports both desktop actions (``keystroke``, ``command``,
``application``) and mouse hardware actions (``dpi_cycle``, ``dpi_set``,
``smartshift_toggle``, ``host_next``, ``haptic``) via an optional
``hardware_handler`` callback injected by the agent.
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Friendly names → Linux evdev keycodes for kernel-level hold-to-talk (key_hold)
_EVDEV_KEY_ALIASES: dict[str, int] = {
    "pageup": 104, "page_up": 104, "pgup": 104, "prior": 104,
    "pagedown": 109, "page_down": 109, "pgdn": 109, "next": 109,
    "home": 102, "end": 107, "insert": 110, "delete": 111, "del": 111,
    "esc": 1, "escape": 1, "tab": 15, "enter": 28, "return": 28, "space": 57,
    "backspace": 14, "left": 105, "right": 106, "up": 103, "down": 108,
    "pause": 119, "scrolllock": 70, "print": 99,
    "f1": 59, "f2": 60, "f3": 61, "f4": 62, "f5": 63, "f6": 64,
    "f7": 65, "f8": 66, "f9": 67, "f10": 68, "f11": 87, "f12": 88,
    "f13": 183, "f14": 184, "f15": 185, "f16": 186, "f17": 187, "f18": 188,
    "f19": 189, "f20": 190, "f21": 191, "f22": 192, "f23": 193, "f24": 194,
}


_WTYPE_MOD_MAP = {
    "ctrl": "ctrl", "control": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "super": "logo", "win": "logo", "meta": "logo", "logo": "logo",
}

_STANDALONE_MOD_KEYSYM = {
    "logo": "Super_L",
}

_KEYSYM_ALIASES = {
    "left": "Left", "right": "Right", "up": "Up", "down": "Down",
    "tab": "Tab", "enter": "Return", "return": "Return",
    "esc": "Escape", "escape": "Escape",
    "backspace": "BackSpace", "delete": "Delete", "del": "Delete",
    "pageup": "Prior", "pgup": "Prior", "pagedown": "Next", "pgdn": "Next",
    "home": "Home", "end": "End", "space": "space",
}

HARDWARE_ACTION_TYPES = frozenset({
    "dpi_cycle",
    "dpi_set",
    "smartshift_toggle",
    "host_next",
    "haptic",
})

HardwareHandler = Callable[[str, str], bool]


def parse_keyspec(spec: str) -> tuple[list[str], Optional[str]]:
    """Split a shortcut string into ``(modifiers, key)`` preserving keysym case."""
    mods: list[str] = []
    key: Optional[str] = None
    for raw in spec.replace("+", " ").split():
        token = raw.strip()
        if not token:
            continue
        mod = _WTYPE_MOD_MAP.get(token.lower())
        if mod is not None:
            mods.append(mod)
        else:
            key = _KEYSYM_ALIASES.get(token.lower(), token)
    if key is None and len(mods) == 1 and mods[0] in _STANDALONE_MOD_KEYSYM:
        key = _STANDALONE_MOD_KEYSYM[mods[0]]
        mods = []
    return mods, key


def wtype_argv(spec: str) -> Optional[list[str]]:
    """Build the ``wtype`` argv for a shortcut, or ``None`` if no key."""
    mods, key = parse_keyspec(spec)
    if not key:
        return None
    cmd = ["wtype"]
    for m in mods:
        cmd.extend(["-M", m])
    cmd.extend(["-k", key])
    for m in reversed(mods):
        cmd.extend(["-m", m])
    return cmd


def xdotool_argv(spec: str) -> Optional[list[str]]:
    """Build the ``xdotool key`` argv for a shortcut, or ``None``."""
    mods, key = parse_keyspec(spec)
    if not key:
        return None
    return ["xdotool", "key", "+".join(mods + [key])]


def execute(
    action_type: str,
    action_data: str,
    hardware_handler: Optional[HardwareHandler] = None,
) -> bool:
    if not action_type or action_type.lower() == "disabled":
        return False
    at = action_type.lower()
    if at in HARDWARE_ACTION_TYPES:
        if hardware_handler is not None:
            return bool(hardware_handler(at, action_data or ""))
        logger.debug("no hardware handler wired for %s", at)
        return False
    if not action_data:
        return False
    if at == "keystroke":
        return _keystroke(action_data)
    if at == "command":
        return _command(action_data)
    if at == "application":
        return _application(action_data)
    logger.warning("unknown action type: %s", at)
    return False


def _keystroke(shortcut: str) -> bool:
    """Send a keystroke via wtype (Wayland-native) → xdotool fallback."""
    cmd = wtype_argv(shortcut)
    if cmd is None:
        return False

    try:
        r = subprocess.run(cmd, capture_output=True, timeout=2)
        if r.returncode == 0:
            return True
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug("wtype error: %s", e)

    fallback = xdotool_argv(shortcut)
    if fallback is None:
        return False
    try:
        r = subprocess.run(fallback, capture_output=True, timeout=2)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _command(cmd: str) -> bool:
    try:
        args = shlex.split(cmd)
        subprocess.Popen(
            args, shell=False, start_new_session=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True
    except Exception as e:
        logger.error("command launch failed (%s): %s", cmd, e)
        return False


def resolve_evdev_keycode(spec: str) -> Optional[int]:
    """Resolve a key name or code (e.g. ``PageDown``, ``KEY_PAGEUP``, ``109``) to a Linux evdev keycode."""
    clean = (spec or "").strip()
    if not clean:
        return None
    if clean.isdigit():
        return int(clean)
    low = clean.lower().replace("-", "_")
    if low in _EVDEV_KEY_ALIASES:
        return _EVDEV_KEY_ALIASES[low]
    if low.startswith("key_") and low[4:] in _EVDEV_KEY_ALIASES:
        return _EVDEV_KEY_ALIASES[low[4:]]
    try:
        from evdev import ecodes  # type: ignore[import-not-found]
        upper = clean.upper().replace("-", "_")
        name = upper if upper.startswith("KEY_") else f"KEY_{upper}"
        val = getattr(ecodes, name, None)
        if isinstance(val, int):
            return val
    except Exception:
        pass
    return None


def hold_key(keycode: int, pressed: bool) -> bool:
    """Emit a true kernel evdev press (``1``) or release (``0``) via ``ydotool``.

    Works with push-to-talk daemons and compositor hooks that watch
    ``/dev/input/event*`` or poll ``EVIOCGKEY`` for real key-hold duration.
    """
    env = dict(os.environ)
    if "YDOTOOL_SOCKET" not in env:
        runtime = env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
        sock = os.path.join(runtime, ".ydotool_socket")
        if os.path.exists(sock):
            env["YDOTOOL_SOCKET"] = sock
    state = "1" if pressed else "0"
    try:
        r = subprocess.run(
            ["ydotool", "key", f"{int(keycode)}:{state}"],
            env=env,
            capture_output=True,
            timeout=2,
        )
        return r.returncode == 0
    except Exception as e:
        logger.warning("ydotool hold_key(%s, %s) failed: %s", keycode, pressed, e)
        return False


def _application(name: str) -> bool:
    """Try direct exec → gtk-launch → gio launch."""
    for launcher in (
        [name],
        ["gtk-launch", name],
        ["gio", "launch", f"{name}.desktop"],
    ):
        try:
            subprocess.Popen(
                launcher, start_new_session=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            continue
    return False
