"""Load/save the device-scope config (``/etc/mx4control/device.toml``).

Owned exclusively by the system daemon — the single writer, so there is
no multi-writer staleness. Values are validated/clamped on load so a bad
file can never stop the daemon from booting.
"""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import fields
from pathlib import Path
from typing import Optional

from ..config.paths import device_config_path
from ..config.schema import ButtonDefault, CONFIG_VERSION, DeviceConfig

logger = logging.getLogger(__name__)

_VALID_BUTTON_MODES = {"default", "disabled", "remap"}
_VALID_WHEEL_MODES = {"smart", "ratchet", "free"}
_VALID_THUMBWHEEL_MODES = {"native", "hd_scroll", "actions"}


class DeviceConfigStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = path or device_config_path()
        self._cfg: Optional[DeviceConfig] = None

    @property
    def config(self) -> DeviceConfig:
        if self._cfg is None:
            self._cfg = self.load()
        return self._cfg

    def invalidate(self) -> None:
        self._cfg = None

    # ─── load / save ──────────────────────────────────────────────────────

    def load(self) -> DeviceConfig:
        if not self.path.exists():
            logger.info("no device config at %s — using defaults (SmartShift off)",
                        self.path)
            self._cfg = DeviceConfig()
            return self._cfg
        try:
            with self.path.open("rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            logger.error("device config load failed (%s); using defaults", e)
            self._cfg = DeviceConfig()
            return self._cfg
        self._cfg = _from_dict(data)
        return self._cfg

    def save(self) -> bool:
        cfg = self.config
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            with tmp.open("w") as f:
                _write_toml(f, cfg)
            os.replace(tmp, self.path)
            return True
        except Exception as e:
            logger.error("device config save failed: %s", e)
            return False


# ─────────────────────────── (de)serialize ───────────────────────────────

def _from_dict(data: dict) -> DeviceConfig:
    scalar_names = {f.name for f in fields(DeviceConfig)} - {"buttons"}
    kwargs = {k: v for k, v in data.items() if k in scalar_names}
    # If an older device.toml lacked wheel_mode, derive it from smartshift_enabled
    if "wheel_mode" not in kwargs and "smartshift_enabled" in kwargs:
        kwargs["wheel_mode"] = "smart" if kwargs["smartshift_enabled"] else "ratchet"
    # If an older device.toml lacked thumbwheel_mode, derive it from thumbwheel_diverted
    if "thumbwheel_mode" not in kwargs and "thumbwheel_diverted" in kwargs:
        kwargs["thumbwheel_mode"] = "actions" if kwargs["thumbwheel_diverted"] else "native"
    cfg = DeviceConfig(**kwargs)
    cfg.buttons = [
        ButtonDefault(
            cid=int(b.get("cid", 0)),
            mode=b.get("mode", "default"),
            target=int(b.get("target", 0)),
        )
        for b in data.get("buttons", [])
        if isinstance(b, dict) and b.get("cid")
    ]
    return _validate(cfg)


def _validate(cfg: DeviceConfig) -> DeviceConfig:
    cfg.version = CONFIG_VERSION
    cfg.dpi = max(200, min(8000, int(cfg.dpi)))
    cfg.smartshift_threshold = max(1, min(255, int(cfg.smartshift_threshold)))
    if cfg.wheel_mode not in _VALID_WHEEL_MODES:
        cfg.wheel_mode = "smart" if cfg.smartshift_enabled else "ratchet"
    cfg.ratchet_torque = max(1, min(100, int(cfg.ratchet_torque)))
    cfg.haptic_level = max(1, min(100, int(cfg.haptic_level)))
    cfg.force_threshold = max(0, min(0xFFFF, int(cfg.force_threshold)))
    cfg.scroll_speed = round(max(0.20, min(4.00, float(cfg.scroll_speed))), 2)
    cfg.scroll_smoothness = max(0, min(100, int(cfg.scroll_smoothness)))
    cfg.scroll_accel = max(0, min(100, int(cfg.scroll_accel)))
    if cfg.thumbwheel_mode not in _VALID_THUMBWHEEL_MODES:
        cfg.thumbwheel_mode = "actions" if cfg.thumbwheel_diverted else "native"
    cfg.thumbwheel_diverted = cfg.thumbwheel_mode == "actions"
    cfg.thumbwheel_speed = round(max(0.20, min(4.00, float(cfg.thumbwheel_speed))), 2)
    cfg.thumbwheel_smoothness = max(0, min(100, int(cfg.thumbwheel_smoothness)))
    cfg.thumbwheel_accel = max(0, min(100, int(cfg.thumbwheel_accel)))
    cfg.thumbwheel_hires = bool(cfg.thumbwheel_hires)
    cfg.thumbwheel_haptic_detent = bool(cfg.thumbwheel_haptic_detent)
    if int(cfg.thumbwheel_haptic_density) not in (1, 2, 3, 6):
        cfg.thumbwheel_haptic_density = 6
    else:
        cfg.thumbwheel_haptic_density = int(cfg.thumbwheel_haptic_density)
    cfg.thumbwheel_haptic_pattern = max(0, min(14, int(cfg.thumbwheel_haptic_pattern)))
    cfg.preferred_host = max(0, min(7, int(cfg.preferred_host)))
    cfg.buttons = [b for b in cfg.buttons if b.mode in _VALID_BUTTON_MODES]
    return cfg


def _write_toml(f, cfg: DeviceConfig) -> None:
    f.write("# mx4control device-scope config (managed by mx4-sysd)\n")
    f.write("# Applied to the mouse on every connect, including at the login screen.\n\n")
    f.write(f"version = {cfg.version}\n")
    f.write(f"dpi = {cfg.dpi}\n")
    f.write(f"smartshift_enabled = {_b(cfg.smartshift_enabled)}\n")
    f.write(f"smartshift_threshold = {cfg.smartshift_threshold}\n")
    f.write(f'wheel_mode = "{cfg.wheel_mode}"\n')
    f.write(f"ratchet_torque = {cfg.ratchet_torque}\n")
    f.write(f"haptic_enabled = {_b(cfg.haptic_enabled)}\n")
    f.write(f"haptic_level = {cfg.haptic_level}\n")
    f.write(f"force_threshold = {cfg.force_threshold}\n")
    f.write(f"hires_enabled = {_b(cfg.hires_enabled)}\n")
    f.write(f"hires_invert = {_b(cfg.hires_invert)}\n")
    f.write(f"scroll_speed = {cfg.scroll_speed:.2f}\n")
    f.write(f"scroll_smoothness = {cfg.scroll_smoothness}\n")
    f.write(f"scroll_accel = {cfg.scroll_accel}\n")
    f.write(f'thumbwheel_mode = "{cfg.thumbwheel_mode}"\n')
    f.write(f"thumbwheel_diverted = {_b(cfg.thumbwheel_diverted)}\n")
    f.write(f"thumbwheel_invert = {_b(cfg.thumbwheel_invert)}\n")
    f.write(f"thumbwheel_speed = {cfg.thumbwheel_speed:.2f}\n")
    f.write(f"thumbwheel_smoothness = {cfg.thumbwheel_smoothness}\n")
    f.write(f"thumbwheel_accel = {cfg.thumbwheel_accel}\n")
    f.write(f"thumbwheel_hires = {_b(cfg.thumbwheel_hires)}\n")
    f.write(f"thumbwheel_haptic_detent = {_b(cfg.thumbwheel_haptic_detent)}\n")
    f.write(f"thumbwheel_haptic_density = {cfg.thumbwheel_haptic_density}\n")
    f.write(f"thumbwheel_haptic_pattern = {cfg.thumbwheel_haptic_pattern}\n")
    f.write(f"restore_host = {_b(cfg.restore_host)}\n")
    f.write(f"preferred_host = {cfg.preferred_host}\n\n")
    for b in cfg.buttons:
        f.write("[[buttons]]\n")
        f.write(f"cid = {b.cid}\n")
        f.write(f'mode = "{b.mode}"\n')
        f.write(f"target = {b.target}\n\n")


def _b(v: bool) -> str:
    return "true" if v else "false"
