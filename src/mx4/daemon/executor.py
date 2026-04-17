"""Execute a ring slice's action — keystroke, command, or application."""

from __future__ import annotations

import logging
import shlex
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


_WTYPE_MOD_MAP = {
    "ctrl": "ctrl", "control": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "super": "logo", "win": "logo", "meta": "logo",
}


def execute(action_type: str, action_data: str) -> bool:
    if not action_data or action_type == "disabled":
        return False
    action_type = action_type.lower()
    if action_type == "keystroke":
        return _keystroke(action_data)
    if action_type == "command":
        return _command(action_data)
    if action_type == "application":
        return _application(action_data)
    logger.warning(f"unknown action type: {action_type}")
    return False


def _keystroke(shortcut: str) -> bool:
    """Send a keystroke via wtype (Wayland-native) → xdotool fallback."""
    parts = [p.strip().lower() for p in shortcut.replace("+", " ").split()]
    mods = []
    key: Optional[str] = None
    for p in parts:
        if p in _WTYPE_MOD_MAP:
            mods.append(_WTYPE_MOD_MAP[p])
        else:
            key = p
    if not key:
        return False

    # wtype
    cmd = ["wtype"]
    for m in mods:
        cmd.extend(["-M", m])
    cmd.extend(["-k", key])
    for m in reversed(mods):
        cmd.extend(["-m", m])
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=2)
        if r.returncode == 0:
            return True
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug(f"wtype error: {e}")

    # xdotool (X11 / XWayland)
    try:
        r = subprocess.run(
            ["xdotool", "key", "+".join(mods + [key])],
            capture_output=True, timeout=2,
        )
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
        logger.error(f"command launch failed ({cmd}): {e}")
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
