"""Config store + migration tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mx4.config import ConfigStore
from mx4.config.schema import CONFIG_VERSION
from mx4.config.store import _m1_to_2


def test_default_config_roundtrip(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.toml")
    cfg = store.config
    assert cfg.version == CONFIG_VERSION
    assert "default" in cfg.ring_profiles
    assert store.save()
    assert (tmp_path / "config.toml").exists()

    # Load back
    store2 = ConfigStore(tmp_path / "config.toml")
    cfg2 = store2.config
    assert cfg2.version == CONFIG_VERSION
    assert "default" in cfg2.ring_profiles
    # Default slices round-tripped
    assert len(cfg2.ring_profiles["default"].slices) == 8


def test_v1_to_v2_migration():
    old = {
        "version": 1,
        "haptics": {"intensity": 2},
        "pointer": {"dpi": 1600},
        "scroll": {"smartshift_enabled": True, "smartshift_threshold": 20},
        "actions_ring": {
            "slices": [
                {"label": "Copy", "icon": "", "action_type": "keystroke", "action_data": "ctrl+c"},
            ],
        },
        "app_profiles": [
            {
                "name": "Firefox",
                "app_pattern": "firefox",
                "actions_ring": {
                    "slices": [
                        {"label": "New Tab", "icon": "", "action_type": "keystroke", "action_data": "ctrl+t"},
                    ],
                },
            },
        ],
    }
    new = _m1_to_2(old)
    assert new["version"] == 2
    assert new["pointer"]["dpi"] == 1600
    assert "default" in new["ring_profiles"]
    assert "firefox" in new["ring_profiles"]
    assert new["ring_profiles"]["firefox"]["app_name"] == "Firefox"
