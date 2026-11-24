"""Phase 3: per-app profile + button-override resolution (pure, no D-Bus)."""

from __future__ import annotations

from mx4.agent.profiles import (
    merge_button_bindings, normalize_app_id, resolve_profile,
)
from mx4.config.schema import ButtonBinding, Config, RingProfile
from mx4.config.store import ConfigStore


def test_normalize_app_id_aliases():
    assert normalize_app_id("Google-Chrome-Stable") == "google-chrome"
    assert normalize_app_id("  Firefox ") == "firefox"


def test_resolve_explicit_then_category_then_default():
    cfg = Config()
    cfg.ring_profiles["zen"] = RingProfile(app_id="zen", app_name="Zen")
    # explicit
    assert resolve_profile(cfg, "zen").app_name == "Zen"
    # category template (kitty -> terminal)
    assert resolve_profile(cfg, "kitty").slices[0].label == "New Tab"
    # default fallback
    assert resolve_profile(cfg, "unknown-app").app_id == "default"


def test_merge_button_bindings_per_app_wins():
    glob = [ButtonBinding(cid=0x53, action_type="keystroke", action_data="alt+Left"),
            ButtonBinding(cid=0x56, action_type="keystroke", action_data="alt+Right")]
    profile = RingProfile(
        app_id="code",
        button_overrides=[ButtonBinding(cid=0x53, action_type="command",
                                        action_data="code --new-window")],
    )
    merged = {b.cid: b for b in merge_button_bindings(glob, profile)}
    assert merged[0x53].action_type == "command"        # per-app override won
    assert merged[0x56].action_data == "alt+Right"       # global preserved


def test_config_roundtrip_with_button_overrides(tmp_path):
    store = ConfigStore(tmp_path / "config.toml")
    cfg = store.config
    cfg.ring_profiles["code"] = RingProfile(
        app_id="code", app_name="VS Code",
        button_overrides=[ButtonBinding(cid=0x53, action_type="command",
                                        action_data="xdg-open .")],
    )
    assert store.save()

    fresh = ConfigStore(tmp_path / "config.toml").load()
    ov = fresh.ring_profiles["code"].button_overrides
    assert len(ov) == 1
    assert ov[0].cid == 0x53
    assert ov[0].action_type == "command"
