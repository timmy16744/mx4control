"""Load / save / migrate the TOML config file."""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import asdict, fields, is_dataclass
from pathlib import Path
from typing import Any, Optional

from .schema import (
    Config, HapticSettings, PointerSettings, ScrollSettings,
    ThumbWheelSettings, DaemonSettings, RingProfile, ActionSlice,
    CONFIG_VERSION, _default_ring,
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

        return _from_dict(Config, data)

    def save(self) -> bool:
        if self._config is None:
            return False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            with tmp.open("w") as f:
                _write_toml(f, asdict(self._config))
            os.replace(tmp, self.path)
            return True
        except Exception as e:
            logger.error(f"config save failed: {e}")
            return False

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
        elif f.name == "ring_profiles":
            kwargs[f.name] = {
                k: _from_dict(RingProfile, v) for k, v in val.items()
            }
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


def _write_toml(f, data: dict) -> None:
    """Simple TOML writer — we control the schema so we don't need a
    round-trip library. Emits the version header first, then tables in
    a stable order, then ``[ring_profiles.*]`` sections last.
    """
    f.write("# mx4control configuration\n")
    f.write("# Edited? Run `mx4ctl reload` to pick up changes without restart.\n\n")
    f.write(f"version = {data.get('version', CONFIG_VERSION)}\n\n")

    table_order = ["haptics", "pointer", "scroll", "thumbwheel", "daemon"]
    for table in table_order:
        section = data.get(table, {})
        if not section:
            continue
        f.write(f"[{table}]\n")
        for k, v in section.items():
            f.write(f"{k} = {_toml_value(v)}\n")
        f.write("\n")

    # Ring profiles — one [ring_profiles.default] + nested slices arrays
    for app_id, profile in (data.get("ring_profiles") or {}).items():
        f.write(f"[ring_profiles.{_toml_key(app_id)}]\n")
        for k, v in profile.items():
            if k == "slices":
                continue
            f.write(f"{k} = {_toml_value(v)}\n")
        f.write("\n")
        for i, s in enumerate(profile.get("slices", [])):
            f.write(f"[[ring_profiles.{_toml_key(app_id)}.slices]]\n")
            for k, v in s.items():
                f.write(f"{k} = {_toml_value(v)}\n")
            f.write("\n")


def _toml_key(k: str) -> str:
    # Bare keys allow [A-Za-z0-9_-]+
    if all(c.isalnum() or c in "_-" for c in k):
        return k
    return f'"{k}"'


def _toml_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        esc = v.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{esc}"'
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(i) for i in v) + "]"
    return repr(v)
