"""Load / save / migrate the TOML config file."""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import asdict, fields, is_dataclass
from pathlib import Path
from typing import Any, Optional

import tomlkit

from .schema import (
    Config, HapticSettings, PointerSettings, ScrollSettings,
    ThumbWheelSettings, DaemonSettings, RingProfile, ActionSlice,
    ButtonBinding,
)

logger = logging.getLogger(__name__)


def _xdg_config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


DEFAULT_CONFIG_PATH = _xdg_config_home() / "mx4control" / "config.toml"


class ConfigStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = path or DEFAULT_CONFIG_PATH
        self._config: Optional[Config] = None

    @property
    def config(self) -> Config:
        if self._config is None:
            self._config = self.load()
        return self._config

    # ─── load / save ────────────────────────────────────────────────────

    def load(self) -> Config:
        if not self.path.exists():
            logger.info(f"no config at {self.path}, using defaults")
            cfg = Config()
            self._config = cfg
            self.save()
            return cfg

        try:
            with self.path.open("rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            logger.error(f"config load failed: {e}; using defaults")
            return Config()

        # Run migrations in order until we reach CONFIG_VERSION
        data_version = int(data.get("version", 1))
        for migration in _MIGRATIONS:
            if data_version < migration.to_version:
                data = migration(data)
                data_version = migration.to_version

        cfg = _from_dict(Config, data)
        # Auto-heal legacy MX4 CID bug: 0x00D7 (215) is Virtual Gesture Button;
        # physical Haptic Sense Thumb Pad is 0x01A0 (416).
        migrated = False
        if cfg.daemon.trigger_cid == 0x00D7:
            cfg.daemon.trigger_cid = 0x01A0
            migrated = True
        if (
            cfg.thumbwheel.preset == "volume"
            and cfg.thumbwheel.positive_data == "XF86AudioRaiseVolume"
        ):
            cfg.thumbwheel.positive_type = "command"
            cfg.thumbwheel.positive_data = "wpctl set-volume -l 1.5 @DEFAULT_AUDIO_SINK@ 5%+"
            cfg.thumbwheel.negative_type = "command"
            cfg.thumbwheel.negative_data = "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-"
            migrated = True
        if migrated:
            self._config = cfg
            self.save()
        return cfg

    def save(self) -> bool:
        if self._config is None:
            return False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            # tomlkit serialises the dataclass tree (no None fields in the
            # schema, so this is total) — robust, vs the old hand-rolled
            # writer that emitted invalid TOML for unexpected value types.
            tmp.write_text(tomlkit.dumps(asdict(self._config)))
            os.replace(tmp, self.path)
            return True
        except Exception as e:
            logger.error(f"config save failed: {e}")
            return False

    def invalidate(self) -> None:
        """Drop the cached Config so the next access reloads from disk."""
        self._config = None

    def update(self, **kwargs) -> None:
        cfg = self.config
        for k, v in kwargs.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        self.save()


# ────────────────────────────── migrations ───────────────────────────────

class _Migration:
    """One step from version N-1 to version N."""

    def __init__(self, to_version: int, fn):
        self.to_version = to_version
        self._fn = fn

    def __call__(self, data: dict) -> dict:
        out = self._fn(data)
        out["version"] = self.to_version
        logger.info(f"migrated config to v{self.to_version}")
        return out


def _m1_to_2(data: dict) -> dict:
    """v1 (JSON) → v2 (TOML). Flatten old ``actions_ring`` to
    ``ring_profiles.default`` and drop removed keys."""
    out: dict[str, Any] = {
        "version": 2,
        "haptics": data.get("haptics", {}),
        "pointer": data.get("pointer", {}),
        "scroll": data.get("scroll", {}),
        "thumbwheel": {},
        "daemon": {},
    }
    # Old actions_ring -> ring_profiles.default
    profiles: dict[str, Any] = {}
    if old := data.get("actions_ring"):
        profiles["default"] = {
            "app_id": "default",
            "app_name": "Default",
            "app_icon": "application-x-executable",
            "slices": old.get("slices", []),
        }
    for p in data.get("app_profiles", []):
        ar = p.get("actions_ring")
        if ar:
            profiles[p["app_pattern"]] = {
                "app_id": p["app_pattern"],
                "app_name": p.get("name", p["app_pattern"]),
                "app_icon": "application-x-executable",
                "slices": ar.get("slices", []),
            }
    out["ring_profiles"] = profiles
    return out


_MIGRATIONS = [_Migration(2, _m1_to_2)]


# ────────────────────────────── (de)serialize ────────────────────────────

def _from_dict(cls, data: dict) -> Any:
    """Reconstruct a dataclass from a dict, honouring nested defaults."""
    if not is_dataclass(cls):
        return data
    kwargs: dict[str, Any] = {}
    for f in fields(cls):
        if f.name not in data:
            continue
        val = data[f.name]
        # Handle nested dataclasses
        if f.type == list[ActionSlice] or f.name == "slices":
            kwargs[f.name] = [_from_dict(ActionSlice, s) for s in val]
        elif f.name == "button_overrides":
            kwargs[f.name] = [_from_dict(ButtonBinding, b) for b in val]
        elif f.name == "ring_profiles":
            kwargs[f.name] = {
                k: _from_dict(RingProfile, v) for k, v in val.items()
            }
        elif f.name == "button_bindings":
            kwargs[f.name] = [_from_dict(ButtonBinding, b) for b in val]
        elif f.name == "haptics":
            kwargs[f.name] = _from_dict(HapticSettings, val)
        elif f.name == "pointer":
            kwargs[f.name] = _from_dict(PointerSettings, val)
        elif f.name == "scroll":
            kwargs[f.name] = _from_dict(ScrollSettings, val)
        elif f.name == "thumbwheel":
            kwargs[f.name] = _from_dict(ThumbWheelSettings, val)
        elif f.name == "daemon":
            kwargs[f.name] = _from_dict(DaemonSettings, val)
        else:
            kwargs[f.name] = val
    return cls(**kwargs)


