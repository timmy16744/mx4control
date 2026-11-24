"""Tests for Actions Ring themes, presets, schema persistence, and Cairo renderer."""

from __future__ import annotations

import cairo
import pytest

from mx4.agent.overlay import format_action_hint, render_ring_frame, resolve_icon_kind
from mx4.agent.profiles import (
    CATEGORY_TEMPLATES,
    RING_PRESETS,
    clone_preset_slices,
    list_ring_presets,
)
from mx4.agent.ring_themes import (
    RING_SIZES,
    RING_THEMES,
    get_ring_size,
    get_ring_theme,
    hex_to_rgb,
    list_ring_sizes,
    list_ring_themes,
)
from mx4.config import ConfigStore


def test_ring_themes_complete_and_valid():
    assert set(RING_THEMES.keys()) == {
        "studio", "cyber", "obsidian", "solar", "emerald", "violet"
    }
    listed = list_ring_themes()
    assert len(listed) == 6
    for theme in RING_THEMES.values():
        for field_name in (
            "accent", "accent_bright", "secondary", "bg_outer", "bg_ring",
            "bg_core", "seg_idle", "seg_hover", "border", "text", "text_sub", "cancel",
        ):
            val = getattr(theme, field_name)
            assert val.startswith("#") and len(val) == 7
            r, g, b = hex_to_rgb(val)
            assert 0.0 <= r <= 1.0 and 0.0 <= g <= 1.0 and 0.0 <= b <= 1.0

    # Unknown theme falls back gracefully
    assert get_ring_theme("nonexistent").id == "studio"
    assert get_ring_theme("CYBER").id == "cyber"


def test_ring_sizes_complete():
    assert set(RING_SIZES.keys()) == {"compact", "standard", "large"}
    assert len(list_ring_sizes()) == 3
    assert get_ring_size("compact").canvas < get_ring_size("standard").canvas < get_ring_size("large").canvas
    assert get_ring_size("unknown").id == "standard"


def test_ring_presets_all_have_eight_slices_and_clone_safely():
    expected = {"default", "hyprland", "browser", "editor", "terminal", "media", "creative", "hardware"}
    assert expected.issubset(set(RING_PRESETS.keys()))
    assert expected.issubset(set(CATEGORY_TEMPLATES.keys()))

    serialized = list_ring_presets()
    assert len(serialized) == len(RING_PRESETS)

    for pid, preset in RING_PRESETS.items():
        assert len(preset["slices"]) == 8
        cloned = clone_preset_slices(pid)
        assert len(cloned) == 8
        cloned[0].label = "Mutated"
        assert preset["slices"][0].label != "Mutated"


def test_daemon_ring_settings_round_trip(tmp_path):
    cfg_path = tmp_path / "config.toml"
    store = ConfigStore(cfg_path)
    cfg = store.config
    assert cfg.daemon.ring_theme == "studio"
    assert cfg.daemon.ring_size == "standard"
    assert cfg.daemon.ring_show_hints is True
    assert cfg.daemon.ring_animate is True

    cfg.daemon.ring_theme = "cyber"
    cfg.daemon.ring_size = "large"
    cfg.daemon.ring_show_hints = False
    cfg.daemon.ring_animate = False
    assert store.save()

    reloaded = ConfigStore(cfg_path).config
    assert reloaded.daemon.ring_theme == "cyber"
    assert reloaded.daemon.ring_size == "large"
    assert reloaded.daemon.ring_show_hints is False
    assert reloaded.daemon.ring_animate is False


def test_legacy_toml_loads_with_ring_defaults(tmp_path):
    cfg_path = tmp_path / "legacy.toml"
    cfg_path.write_text(
        "version = 2\n"
        "[daemon]\n"
        "autostart_gesture = true\n"
        "trigger_cid = 416\n"
        "cancel_radius = 45\n"
    )
    cfg = ConfigStore(cfg_path).config
    assert cfg.daemon.cancel_radius == 45
    assert cfg.daemon.ring_theme == "studio"
    assert cfg.daemon.ring_size == "standard"
    assert cfg.daemon.ring_show_hints is True
    assert cfg.daemon.ring_animate is True


@pytest.mark.parametrize("theme_id", list(RING_THEMES.keys()))
def test_cairo_renderer_all_themes(theme_id):
    theme = get_ring_theme(theme_id)
    size = get_ring_size("standard")
    slices = clone_preset_slices("hyprland" if theme_id == "cyber" else "hardware")
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size.canvas, size.canvas)
    cr = cairo.Context(surface)

    lifts = [0.0] * 8
    lifts[2] = 1.0
    render_ring_frame(
        cr,
        size.canvas,
        size.canvas,
        slices=slices,
        profile_name="Hyprland",
        theme=theme,
        size_spec=size,
        selected=2,
        slice_lifts=lifts,
        open_t=1.0,
        close_t=0.0,
        ptr_dx=65.0,
        ptr_dy=-10.0,
        cancel_radius=40.0,
        ambient_phase=0.5,
        show_hints=True,
    )
    # Confirm non-empty rendered alpha pixels
    data = bytes(surface.get_data())
    assert any(b != 0 for b in data)

    # Confirm icon & hint helpers return clean strings
    for s in slices:
        assert isinstance(resolve_icon_kind(s), str) and resolve_icon_kind(s)
        assert isinstance(format_action_hint(s), str)
