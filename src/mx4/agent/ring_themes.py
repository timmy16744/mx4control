"""Curated visual themes and geometry presets for the MX4 Actions Ring.

Pure Python (no GTK/Cairo imports) so the same palette definitions drive:
  1. The live Wayland GTK4/Cairo Actions Ring overlay (mx4-agent)
  2. The 3D WebGL holographic Actions Ring & cube floor in MX4 Studio
  3. The 2D interactive SVG Ring Designer & Theme Picker in MX4 Studio
"""

from __future__ import annotations

from dataclasses import dataclass, asdict


def hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    """Convert ``#RRGGBB`` to normalized ``(r, g, b)`` floats in ``[0, 1]``."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (1.0, 1.0, 1.0)
    return (
        int(h[0:2], 16) / 255.0,
        int(h[2:4], 16) / 255.0,
        int(h[4:6], 16) / 255.0,
    )


@dataclass(frozen=True)
class RingTheme:
    id: str
    name: str
    tagline: str
    accent: str          # Primary highlight (selected slice, compass, confirm burst)
    accent_bright: str   # Specular bright rim / hot core
    secondary: str       # Secondary telemetry accent (vernier ticks, outer glow)
    bg_outer: str        # Outer frosted housing dark edge
    bg_ring: str         # Main translucent ring housing body
    bg_core: str         # Inner hub fill
    seg_idle: str        # Unselected slice fill
    seg_hover: str       # Selected slice rich tinted fill
    border: str          # Subtle hairline bevel border
    text: str            # Primary label ink
    text_sub: str        # Secondary shortcut / hint ink
    cancel: str          # Deadzone cancel ring tint

    def to_dict(self) -> dict:
        return asdict(self)


RING_THEMES: dict[str, RingTheme] = {
    "studio": RingTheme(
        id="studio",
        name="Studio Copper",
        tagline="Smoked obsidian · brushed copper · Darkfield cyan",
        accent="#e8a864",
        accent_bright="#ffe0b2",
        secondary="#3ce0e8",
        bg_outer="#0a0d14",
        bg_ring="#121722",
        bg_core="#0c1018",
        seg_idle="#18202e",
        seg_hover="#2e2318",
        border="#334057",
        text="#f5f7fc",
        text_sub="#95a3ba",
        cancel="#f06e6e",
    ),
    "cyber": RingTheme(
        id="cyber",
        name="Darkfield Cyber",
        tagline="Deep midnight · electric cyan · cryo-white",
        accent="#2ae4f0",
        accent_bright="#b0fbff",
        secondary="#4c8dff",
        bg_outer="#050a14",
        bg_ring="#091324",
        bg_core="#060d18",
        seg_idle="#0e1e33",
        seg_hover="#0c3448",
        border="#1e4260",
        text="#effbff",
        text_sub="#7eaac4",
        cancel="#ff6b84",
    ),
    "obsidian": RingTheme(
        id="obsidian",
        name="Monochrome Pro",
        tagline="Stealth matte graphite · pure white · tungsten",
        accent="#f2f5fa",
        accent_bright="#ffffff",
        secondary="#9ca8ba",
        bg_outer="#08090c",
        bg_ring="#12141a",
        bg_core="#0b0d11",
        seg_idle="#1a1d24",
        seg_hover="#303642",
        border="#373e4c",
        text="#ffffff",
        text_sub="#949ca8",
        cancel="#f87171",
    ),
    "solar": RingTheme(
        id="solar",
        name="Amber Forge",
        tagline="Warm basalt · molten gold-amber · ember glow",
        accent="#ff9d3b",
        accent_bright="#ffe099",
        secondary="#ff5d42",
        bg_outer="#120b07",
        bg_ring="#1d120c",
        bg_core="#140c08",
        seg_idle="#291a12",
        seg_hover="#452512",
        border="#543522",
        text="#fff7ee",
        text_sub="#bf9c80",
        cancel="#ff5959",
    ),
    "emerald": RingTheme(
        id="emerald",
        name="Nordic Emerald",
        tagline="Carbon slate · luminous mint · glacier teal",
        accent="#34e6a4",
        accent_bright="#b2ffe0",
        secondary="#28c7d9",
        bg_outer="#06110e",
        bg_ring="#0c1c17",
        bg_core="#081410",
        seg_idle="#132a22",
        seg_hover="#104230",
        border="#214c3d",
        text="#effdf7",
        text_sub="#80b8a4",
        cancel="#f87171",
    ),
    "violet": RingTheme(
        id="violet",
        name="Ultraviolet Pulse",
        tagline="Cosmos indigo · electric violet · neon magenta",
        accent="#b87dff",
        accent_bright="#e7ccff",
        secondary="#f464c2",
        bg_outer="#0c0716",
        bg_ring="#150e28",
        bg_core="#0e091c",
        seg_idle="#1f1538",
        seg_hover="#392061",
        border="#412d6b",
        text="#f8f2ff",
        text_sub="#a490c9",
        cancel="#ff6685",
    ),
}

DEFAULT_RING_THEME_ID = "studio"


@dataclass(frozen=True)
class RingSizeSpec:
    id: str
    label: str
    canvas: int
    outer_r: float
    inner_r: float
    scale_3d: float

    def to_dict(self) -> dict:
        return asdict(self)


RING_SIZES: dict[str, RingSizeSpec] = {
    "compact": RingSizeSpec(
        id="compact",
        label="Compact",
        canvas=416,
        outer_r=148.0,
        inner_r=50.0,
        scale_3d=0.86,
    ),
    "standard": RingSizeSpec(
        id="standard",
        label="Standard",
        canvas=480,
        outer_r=174.0,
        inner_r=58.0,
        scale_3d=1.00,
    ),
    "large": RingSizeSpec(
        id="large",
        label="Large",
        canvas=552,
        outer_r=202.0,
        inner_r=66.0,
        scale_3d=1.15,
    ),
}

DEFAULT_RING_SIZE_ID = "standard"


def get_ring_theme(theme_id: str | None) -> RingTheme:
    if not theme_id:
        return RING_THEMES[DEFAULT_RING_THEME_ID]
    return RING_THEMES.get(str(theme_id).strip().lower(), RING_THEMES[DEFAULT_RING_THEME_ID])


def get_ring_size(size_id: str | None) -> RingSizeSpec:
    if not size_id:
        return RING_SIZES[DEFAULT_RING_SIZE_ID]
    return RING_SIZES.get(str(size_id).strip().lower(), RING_SIZES[DEFAULT_RING_SIZE_ID])


def list_ring_themes() -> list[dict]:
    return [t.to_dict() for t in RING_THEMES.values()]


def list_ring_sizes() -> list[dict]:
    return [s.to_dict() for s in RING_SIZES.values()]
