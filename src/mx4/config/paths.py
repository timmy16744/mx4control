"""Config path resolution, split by privilege scope.

* **device scope** — settings the system daemon must apply at boot, before
  any user session exists. Lives in ``/etc/mx4control/device.toml`` (root
  owned, world-readable). A dev override is honoured via
  ``MX4_DEVICE_CONFIG`` so the daemon can run unprivileged from a checkout.
* **session scope** — per-user ring/profile/button-action config under XDG.
"""

from __future__ import annotations

import os
from pathlib import Path

SYSTEM_CONFIG_DIR = Path("/etc/mx4control")
RUNTIME_STATE_DIR = Path(os.environ.get("RUNTIME_DIRECTORY", "/run/mx4control"))


def device_config_path() -> Path:
    override = os.environ.get("MX4_DEVICE_CONFIG")
    if override:
        return Path(override)
    return SYSTEM_CONFIG_DIR / "device.toml"


def runtime_state_path() -> Path:
    override = os.environ.get("MX4_STATE_FILE")
    if override:
        return Path(override)
    return RUNTIME_STATE_DIR / "state.json"


def _xdg_config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def session_config_path() -> Path:
    override = os.environ.get("MX4_SESSION_CONFIG")
    if override:
        return Path(override)
    return _xdg_config_home() / "mx4control" / "config.toml"
