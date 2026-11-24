"""Wayland layer-shell Actions Ring overlay (GTK4 + Cairo, 60 FPS spring-animated).

Visual & behavioral highlights
------------------------------
* **Theme-driven precision glass instrument:** 6 curated palettes from
  :mod:`.ring_themes` (Studio Copper, Darkfield Cyber, Monochrome Pro,
  Amber Forge, Nordic Emerald, Ultraviolet Pulse) with dynamic sizing
  (``compact`` / ``standard`` / ``large``).
* **60 FPS fluid motion:** Spring overshoot bloom-in, per-slice radial hover
  lift & luminous outer arc rim, rotating precision vernier ticks, and a
  150 ms expanding confirm-burst on release (while returning the chosen
  :class:`ActionSlice` synchronously with zero execution latency).
* **Live analog cursor tracking:** Tracks actual hand movement ``(dx, dy)``
  from :class:`GestureEngine` to render a live magnetic compass needle,
  deadzone activation progress ring, and glowing cursor tether puck.
* **Crisp Cairo geometric vector icons:** Every common action draws a razor-
  sharp stroked vector glyph directly in Cairo (no blurry emoji or font
  fallback boxes) plus optional compact shortcut/action hints.
"""

from __future__ import annotations

import logging
import math
import subprocess
import time
from typing import Optional

import cairo

from ..config import ActionSlice, RingProfile
from .ring_themes import (
    RingSizeSpec,
    RingTheme,
    get_ring_size,
    get_ring_theme,
    hex_to_rgb,
)

logger = logging.getLogger(__name__)

# GTK4 + gtk4-layer-shell are imported lazily inside the window class so that
# the pure Cairo renderer ``render_ring_frame`` can be unit-tested and rendered
# offscreen in headless environments without a Wayland compositor.
_GTK_LOADED = False
_HAS_LAYER_SHELL = False
GLib = None
Gdk = None
Gtk = None
LayerShell = None


def _ensure_gtk() -> None:
    global _GTK_LOADED, _HAS_LAYER_SHELL, GLib, Gdk, Gtk, LayerShell
    if _GTK_LOADED:
        return
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    gi.require_version("GLib", "2.0")
    from gi.repository import Gdk as _Gdk, GLib as _GLib, Gtk as _Gtk

    Gdk, GLib, Gtk = _Gdk, _GLib, _Gtk
    try:
        gi.require_version("Gtk4LayerShell", "1.0")
        from gi.repository import Gtk4LayerShell as _LayerShell

        LayerShell = _LayerShell
        _HAS_LAYER_SHELL = True
    except (ValueError, ImportError):
        LayerShell = None
        _HAS_LAYER_SHELL = False
    _GTK_LOADED = True


# ─────────────────────────── Action Icon & Hint Helpers ───────────────────

def resolve_icon_kind(seg: ActionSlice) -> str:
    """Map an ActionSlice's icon name, label, and action type to a vector glyph."""
    ic = (seg.icon or "").lower()
    lbl = (seg.label or "").lower()
    at = (seg.action_type or "").lower()
    ad = (seg.action_data or "").lower()

    if at == "dpi_cycle" or at == "dpi_set" or "dpi" in lbl or "mouse" in ic:
        return "dpi"
    if at == "smartshift_toggle" or "smartshift" in lbl:
        return "wheel"
    if at == "host_next" or "host" in lbl or "wireless" in ic:
        return "host"
    if at == "haptic" or "haptic" in lbl:
        return "haptic"

    if "undo" in ic or "undo" in lbl or "reopen" in lbl:
        return "undo"
    if "redo" in ic or "redo" in lbl:
        return "redo"
    if "copy" in ic or "copy" in lbl or "duplicate" in lbl:
        return "copy"
    if "paste" in ic or "paste" in lbl:
        return "paste"
    if "save" in ic or "save" in lbl:
        return "save"
    if "camera" in ic or "screenshot" in lbl or "grim" in ad:
        return "camera"
    if "find" in ic or "search" in ic or "find" in lbl or "palette" in lbl:
        return "search"
    if "tab-new" in ic or "new tab" in lbl or "plus" in ic:
        return "plus"
    if "close" in ic or "close" in lbl or "killactive" in ad or "quit" in lbl:
        return "close"
    if "refresh" in ic or "reload" in lbl or "hide" in lbl:
        return "refresh"
    if "fullscreen" in ic or "fullscreen" in lbl:
        return "fullscreen"
    if "window-new" in ic or "float" in lbl:
        return "float"
    if "terminal" in ic or "terminal" in lbl:
        return "terminal"
    if "microphone" in ic or "mic" in lbl or "audio_source" in ad:
        return "mic"
    if "volume-muted" in ic or "mute" in lbl:
        return "mute"
    if "volume-high" in ic or "vol +" in lbl or "vol up" in lbl or "5%+" in ad:
        return "vol_up"
    if "volume-low" in ic or "vol -" in lbl or "vol down" in lbl or "5%-" in ad:
        return "vol_down"
    if "playback" in ic or "play" in lbl:
        return "play"
    if "skip-forward" in ic or ("next" in lbl and "ws" not in lbl and "host" not in lbl):
        return "next_track"
    if "skip-backward" in ic or ("prev" in lbl and "ws" not in lbl):
        return "prev_track"
    if "previous" in ic or "back" in lbl or "prev" in lbl:
        return "back"
    if "next" in ic or "forward" in lbl or "next" in lbl:
        return "forward"
    if "bookmark" in ic or "bookmark" in lbl:
        return "bookmark"
    if "zoom-in" in ic or "zoom in" in lbl or "zoom fit" in lbl:
        return "zoom_in"
    if "zoom-out" in ic or "zoom out" in lbl:
        return "zoom_out"
    if "export" in ic or "export" in lbl or "open" in ic:
        return "export"
    if "clear" in ic or "clear" in lbl:
        return "clear"
    if "format" in ic or "comment" in lbl or "format" in lbl or "jump" in ic:
        return "code"
    return "spark"


def format_action_hint(seg: ActionSlice) -> str:
    """Produce a concise, clean telemetry subtitle for a slice (max ~12 chars)."""
    at = (seg.action_type or "").lower()
    ad = (seg.action_data or "").strip()

    if at == "disabled":
        return "Off"
    if at == "dpi_cycle":
        return "DPI Cycle"
    if at == "dpi_set":
        return f"{ad} DPI" if ad else "Set DPI"
    if at == "smartshift_toggle":
        return "MagSpeed"
    if at == "host_next":
        return "Easy-Switch"
    if at == "haptic":
        return f"Wave #{ad or '2'}"

    if at == "keystroke" and ad:
        parts = [p.strip() for p in ad.split("+") if p.strip()]
        nice = []
        mapping = {
            "ctrl": "Ctrl", "control": "Ctrl",
            "shift": "Shift", "alt": "Alt",
            "super": "Super", "meta": "Super",
            "left": "Left", "right": "Right", "up": "Up", "down": "Down",
            "plus": "+", "minus": "-", "grave": "`", "space": "Space",
        }
        for p in parts:
            nice.append(mapping.get(p.lower(), p.upper() if len(p) == 1 else p.capitalize()))
        out = "+".join(nice)
        return out if len(out) <= 13 else out[:12] + "..."

    if at == "command" and ad:
        low = ad.lower()
        if "grim" in low or "slurp" in low:
            return "Region PNG"
        if "movetoworkspace +1" in low:
            return "Move WS +1"
        if "movetoworkspace -1" in low:
            return "Move WS -1"
        if "workspace +1" in low:
            return "WS +1"
        if "workspace -1" in low:
            return "WS -1"
        if "fullscreen" in low:
            return "Hypr Full"
        if "togglefloating" in low:
            return "Hypr Float"
        if "killactive" in low:
            return "Hypr Kill"
        if "playerctl" in low:
            return "MPRIS"
        if "wpctl" in low:
            if "source" in low:
                return "PipeWire Mic"
            return "PipeWire"
        first = ad.split()[0].rsplit("/", 1)[-1]
        return first[:12]

    if at == "application" and ad:
        return ad.rsplit("/", 1)[-1][:12]
    return ""


def _draw_vector_icon(
    cr: cairo.Context,
    kind: str,
    cx: float,
    cy: float,
    r: float,
    rgb: tuple[float, float, float],
    alpha: float,
) -> None:
    """Draw a crisp 1.75px geometric vector icon centered at ``(cx, cy)``."""
    cr.save()
    cr.translate(cx, cy)
    cr.set_source_rgba(rgb[0], rgb[1], rgb[2], alpha)
    cr.set_line_width(max(1.45, r * 0.21))
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)

    if kind == "undo":
        cr.arc(0, r * 0.12, r * 0.62, -math.pi * 0.85, math.pi * 0.45)
        cr.stroke()
        cr.move_to(-r * 0.68, -r * 0.36)
        cr.line_to(-r * 0.68, r * 0.04)
        cr.line_to(-r * 0.28, -r * 0.06)
        cr.stroke()
    elif kind == "redo":
        cr.arc_negative(0, r * 0.12, r * 0.62, -math.pi * 0.15, math.pi * 0.55)
        cr.stroke()
        cr.move_to(r * 0.68, -r * 0.36)
        cr.line_to(r * 0.68, r * 0.04)
        cr.line_to(r * 0.28, -r * 0.06)
        cr.stroke()
    elif kind == "copy":
        cr.rectangle(-r * 0.24, -r * 0.32, r * 0.82, r * 0.96)
        cr.stroke()
        cr.move_to(-r * 0.24, r * 0.36)
        cr.line_to(-r * 0.58, r * 0.36)
        cr.line_to(-r * 0.58, -r * 0.66)
        cr.line_to(r * 0.24, -r * 0.66)
        cr.line_to(r * 0.24, -r * 0.32)
        cr.stroke()
    elif kind == "paste":
        cr.rectangle(-r * 0.56, -r * 0.48, r * 1.12, r * 1.18)
        cr.stroke()
        cr.rectangle(-r * 0.26, -r * 0.72, r * 0.52, r * 0.32)
        cr.stroke()
    elif kind == "save":
        cr.move_to(-r * 0.62, -r * 0.62)
        cr.line_to(r * 0.34, -r * 0.62)
        cr.line_to(r * 0.62, -r * 0.34)
        cr.line_to(r * 0.62, r * 0.62)
        cr.line_to(-r * 0.62, r * 0.62)
        cr.close_path()
        cr.stroke()
        cr.rectangle(-r * 0.32, r * 0.04, r * 0.64, r * 0.58)
        cr.stroke()
        cr.rectangle(-r * 0.26, -r * 0.62, r * 0.44, r * 0.32)
        cr.stroke()
    elif kind == "camera":
        cr.rectangle(-r * 0.72, -r * 0.42, r * 1.44, r * 0.98)
        cr.stroke()
        cr.move_to(-r * 0.32, -r * 0.42)
        cr.line_to(-r * 0.18, -r * 0.66)
        cr.line_to(r * 0.18, -r * 0.66)
        cr.line_to(r * 0.32, -r * 0.42)
        cr.stroke()
        cr.arc(0, r * 0.06, r * 0.28, 0, math.tau)
        cr.stroke()
    elif kind == "search":
        cr.arc(-r * 0.14, -r * 0.14, r * 0.48, 0, math.tau)
        cr.stroke()
        cr.move_to(r * 0.22, r * 0.22)
        cr.line_to(r * 0.68, r * 0.68)
        cr.stroke()
    elif kind == "plus":
        cr.move_to(-r * 0.62, 0)
        cr.line_to(r * 0.62, 0)
        cr.move_to(0, -r * 0.62)
        cr.line_to(0, r * 0.62)
        cr.stroke()
    elif kind == "close":
        cr.move_to(-r * 0.52, -r * 0.52)
        cr.line_to(r * 0.52, r * 0.52)
        cr.move_to(r * 0.52, -r * 0.52)
        cr.line_to(-r * 0.52, r * 0.52)
        cr.stroke()
    elif kind == "refresh":
        cr.arc(0, 0, r * 0.58, -math.pi * 0.75, math.pi * 0.85)
        cr.stroke()
        cr.move_to(r * 0.14, -r * 0.72)
        cr.line_to(r * 0.54, -r * 0.48)
        cr.line_to(r * 0.24, -r * 0.16)
        cr.stroke()
    elif kind == "back":
        cr.move_to(r * 0.58, 0)
        cr.line_to(-r * 0.54, 0)
        cr.move_to(-r * 0.08, -r * 0.48)
        cr.line_to(-r * 0.56, 0)
        cr.line_to(-r * 0.08, r * 0.48)
        cr.stroke()
    elif kind == "forward":
        cr.move_to(-r * 0.58, 0)
        cr.line_to(r * 0.54, 0)
        cr.move_to(r * 0.08, -r * 0.48)
        cr.line_to(r * 0.56, 0)
        cr.line_to(r * 0.08, r * 0.48)
        cr.stroke()
    elif kind == "fullscreen":
        s = r * 0.62
        d = r * 0.28
        for sx in (-1, 1):
            for sy in (-1, 1):
                cr.move_to(sx * s, sy * (s - d))
                cr.line_to(sx * s, sy * s)
                cr.line_to(sx * (s - d), sy * s)
        cr.stroke()
    elif kind == "float":
        cr.rectangle(-r * 0.66, -r * 0.56, r * 0.90, r * 0.76)
        cr.stroke()
        cr.rectangle(-r * 0.20, -r * 0.14, r * 0.86, r * 0.72)
        cr.stroke()
    elif kind == "terminal":
        cr.move_to(-r * 0.58, -r * 0.40)
        cr.line_to(-r * 0.12, 0)
        cr.line_to(-r * 0.58, r * 0.40)
        cr.move_to(r * 0.04, r * 0.40)
        cr.line_to(r * 0.62, r * 0.40)
        cr.stroke()
    elif kind == "code":
        cr.move_to(-r * 0.30, -r * 0.44)
        cr.line_to(-r * 0.68, 0)
        cr.line_to(-r * 0.30, r * 0.44)
        cr.move_to(r * 0.30, -r * 0.44)
        cr.line_to(r * 0.68, 0)
        cr.line_to(r * 0.30, r * 0.44)
        cr.move_to(r * 0.10, -r * 0.50)
        cr.line_to(-r * 0.10, r * 0.50)
        cr.stroke()
    elif kind == "play":
        cr.move_to(-r * 0.44, -r * 0.56)
        cr.line_to(r * 0.56, 0)
        cr.line_to(-r * 0.44, r * 0.56)
        cr.close_path()
        cr.stroke()
    elif kind == "next_track":
        cr.move_to(-r * 0.56, -r * 0.48)
        cr.line_to(r * 0.18, 0)
        cr.line_to(-r * 0.56, r * 0.48)
        cr.close_path()
        cr.move_to(r * 0.44, -r * 0.48)
        cr.line_to(r * 0.44, r * 0.48)
        cr.stroke()
    elif kind == "prev_track":
        cr.move_to(r * 0.56, -r * 0.48)
        cr.line_to(-r * 0.18, 0)
        cr.line_to(r * 0.56, r * 0.48)
        cr.close_path()
        cr.move_to(-r * 0.44, -r * 0.48)
        cr.line_to(-r * 0.44, r * 0.48)
        cr.stroke()
    elif kind in ("vol_up", "vol_down", "mute"):
        cr.move_to(-r * 0.68, -r * 0.22)
        cr.line_to(-r * 0.36, -r * 0.22)
        cr.line_to(r * 0.02, -r * 0.54)
        cr.line_to(r * 0.02, r * 0.54)
        cr.line_to(-r * 0.36, r * 0.22)
        cr.line_to(-r * 0.68, r * 0.22)
        cr.close_path()
        cr.stroke()
        if kind == "vol_up":
            cr.arc(r * 0.14, 0, r * 0.30, -0.8, 0.8)
            cr.stroke()
            cr.arc(r * 0.14, 0, r * 0.56, -0.8, 0.8)
            cr.stroke()
        elif kind == "vol_down":
            cr.arc(r * 0.14, 0, r * 0.34, -0.75, 0.75)
            cr.stroke()
        else:
            cr.move_to(r * 0.26, -r * 0.26)
            cr.line_to(r * 0.70, r * 0.26)
            cr.move_to(r * 0.70, -r * 0.26)
            cr.line_to(r * 0.26, r * 0.26)
            cr.stroke()
    elif kind == "mic":
        cr.arc(0, -r * 0.28, r * 0.24, math.pi, 0)
        cr.line_to(r * 0.24, r * 0.08)
        cr.arc(0, r * 0.08, r * 0.24, 0, math.pi)
        cr.close_path()
        cr.stroke()
        cr.arc(0, r * 0.08, r * 0.48, 0.15, math.pi - 0.15)
        cr.stroke()
        cr.move_to(0, r * 0.56)
        cr.line_to(0, r * 0.74)
        cr.stroke()
    elif kind == "dpi":
        cr.arc(0, 0, r * 0.58, 0, math.tau)
        cr.stroke()
        cr.move_to(-r * 0.78, 0)
        cr.line_to(-r * 0.34, 0)
        cr.move_to(r * 0.34, 0)
        cr.line_to(r * 0.78, 0)
        cr.move_to(0, -r * 0.78)
        cr.line_to(0, -r * 0.34)
        cr.move_to(0, r * 0.34)
        cr.line_to(0, r * 0.78)
        cr.stroke()
        cr.arc(0, 0, r * 0.14, 0, math.tau)
        cr.fill()
    elif kind == "wheel":
        cr.arc(0, 0, r * 0.62, 0, math.tau)
        cr.stroke()
        cr.arc(0, 0, r * 0.24, 0, math.tau)
        cr.stroke()
        for k in range(6):
            a = k * (math.tau / 6.0)
            cr.move_to(math.cos(a) * r * 0.24, math.sin(a) * r * 0.24)
            cr.line_to(math.cos(a) * r * 0.62, math.sin(a) * r * 0.62)
        cr.stroke()
    elif kind == "host":
        cr.arc(0, r * 0.36, r * 0.14, 0, math.tau)
        cr.fill()
        cr.arc(0, r * 0.36, r * 0.42, -math.pi * 0.78, -math.pi * 0.22)
        cr.stroke()
        cr.arc(0, r * 0.36, r * 0.72, -math.pi * 0.78, -math.pi * 0.22)
        cr.stroke()
    elif kind == "haptic":
        cr.arc(0, 0, r * 0.18, 0, math.tau)
        cr.fill()
        cr.arc(0, 0, r * 0.44, -0.9, 0.9)
        cr.stroke()
        cr.arc(0, 0, r * 0.44, math.pi - 0.9, math.pi + 0.9)
        cr.stroke()
        cr.arc(0, 0, r * 0.72, -0.75, 0.75)
        cr.stroke()
        cr.arc(0, 0, r * 0.72, math.pi - 0.75, math.pi + 0.75)
        cr.stroke()
    elif kind == "bookmark":
        cr.move_to(-r * 0.42, -r * 0.64)
        cr.line_to(r * 0.42, -r * 0.64)
        cr.line_to(r * 0.42, r * 0.64)
        cr.line_to(0, r * 0.26)
        cr.line_to(-r * 0.42, r * 0.64)
        cr.close_path()
        cr.stroke()
    elif kind in ("zoom_in", "zoom_out"):
        cr.arc(-r * 0.12, -r * 0.12, r * 0.48, 0, math.tau)
        cr.stroke()
        cr.move_to(r * 0.24, r * 0.24)
        cr.line_to(r * 0.66, r * 0.66)
        cr.move_to(-r * 0.34, -r * 0.12)
        cr.line_to(r * 0.10, -r * 0.12)
        if kind == "zoom_in":
            cr.move_to(-r * 0.12, -r * 0.34)
            cr.line_to(-r * 0.12, r * 0.10)
        cr.stroke()
    elif kind == "export":
        cr.move_to(-r * 0.56, r * 0.10)
        cr.line_to(-r * 0.56, r * 0.60)
        cr.line_to(r * 0.56, r * 0.60)
        cr.line_to(r * 0.56, r * 0.10)
        cr.move_to(0, r * 0.24)
        cr.line_to(0, -r * 0.62)
        cr.move_to(-r * 0.32, -r * 0.30)
        cr.line_to(0, -r * 0.62)
        cr.line_to(r * 0.32, -r * 0.30)
        cr.stroke()
    elif kind == "clear":
        cr.move_to(-r * 0.60, r * 0.54)
        cr.line_to(r * 0.60, r * 0.54)
        cr.move_to(-r * 0.46, r * 0.12)
        cr.line_to(r * 0.08, -r * 0.52)
        cr.line_to(r * 0.54, -r * 0.12)
        cr.line_to(r * 0.06, r * 0.46)
        cr.line_to(-r * 0.30, r * 0.46)
        cr.close_path()
        cr.stroke()
    else:
        # Crisp 4-point instrument diamond star
        cr.move_to(0, -r * 0.68)
        cr.line_to(r * 0.22, -r * 0.22)
        cr.line_to(r * 0.68, 0)
        cr.line_to(r * 0.22, r * 0.22)
        cr.line_to(0, r * 0.68)
        cr.line_to(-r * 0.22, r * 0.22)
        cr.line_to(-r * 0.68, 0)
        cr.line_to(-r * 0.22, -r * 0.22)
        cr.close_path()
        cr.stroke()

    cr.restore()


# ─────────────────────────── Pure Cairo Frame Renderer ────────────────────

def _rounded_pill(cr: cairo.Context, x: float, y: float, w: float, h: float, r: float) -> None:
    r = min(r, h * 0.5, w * 0.5)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi * 0.5, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi * 0.5)
    cr.arc(x + r, y + h - r, r, math.pi * 0.5, math.pi)
    cr.arc(x + r, y + r, r, math.pi, math.pi * 1.5)
    cr.close_path()


def _spring_overshoot(t: float) -> float:
    """Smooth spring ease-out curve ``[0..1]`` with subtle ~2.5% tactile overshoot."""
    t = max(0.0, min(1.0, t))
    if t >= 1.0:
        return 1.0
    return 1.0 - math.exp(-7.2 * t) * math.cos(5.4 * t)


def render_ring_frame(
    cr: cairo.Context,
    width: int,
    height: int,
    *,
    slices: list[ActionSlice],
    profile_name: str,
    theme: RingTheme,
    size_spec: RingSizeSpec,
    selected: Optional[int],
    slice_lifts: list[float],
    open_t: float = 1.0,
    close_t: float = 0.0,
    confirm_idx: Optional[int] = None,
    ptr_dx: float = 0.0,
    ptr_dy: float = 0.0,
    cancel_radius: float = 40.0,
    ambient_phase: float = 0.0,
    show_hints: bool = True,
) -> None:
    """Render one cinema-grade frame of the MX4 Actions Ring onto ``cr``."""
    cr.set_operator(cairo.OPERATOR_CLEAR)
    cr.paint()
    cr.set_operator(cairo.OPERATOR_OVER)

    if not slices:
        return

    open_s = _spring_overshoot(open_t)
    fade_in = min(1.0, open_t * 2.2)
    fade_out = max(0.0, 1.0 - close_t * 1.25)
    master_alpha = max(0.0, min(1.0, fade_in * fade_out))
    if master_alpha <= 0.01:
        return

    # Scale smoothly from 0.78 -> 1.00 on entrance; subtle expand on confirm burst
    scale = (0.78 + 0.22 * open_s) * (1.0 + (0.045 if confirm_idx is not None else -0.08) * close_t)

    cx = width / 2.0
    cy = height / 2.0 - 16.0  # Reserve sleek space at bottom for telemetry HUD pill

    r_out = size_spec.outer_r
    r_in = size_spec.inner_r
    n = len(slices)
    seg_angle = math.tau / n
    gap_rad = 0.042

    accent = hex_to_rgb(theme.accent)
    accent_hi = hex_to_rgb(theme.accent_bright)
    secondary = hex_to_rgb(theme.secondary)
    bg_outer = hex_to_rgb(theme.bg_outer)
    bg_ring = hex_to_rgb(theme.bg_ring)
    bg_core = hex_to_rgb(theme.bg_core)
    seg_idle = hex_to_rgb(theme.seg_idle)
    seg_hover = hex_to_rgb(theme.seg_hover)
    border = hex_to_rgb(theme.border)
    ink = hex_to_rgb(theme.text)
    ink_sub = hex_to_rgb(theme.text_sub)
    cancel_rgb = hex_to_rgb(theme.cancel)

    cr.save()
    cr.translate(cx, cy)
    cr.scale(scale, scale)

    # ── 1. Ambient atmospheric aura + deep machined drop shadow ───────────
    aura = cairo.RadialGradient(0, 0, r_out * 0.60, 0, 0, r_out + 44.0)
    aura.add_color_stop_rgba(0.0, bg_outer[0], bg_outer[1], bg_outer[2], 0.62 * master_alpha)
    aura.add_color_stop_rgba(0.68, accent[0] * 0.32, accent[1] * 0.32, accent[2] * 0.32, 0.24 * master_alpha)
    aura.add_color_stop_rgba(1.0, 0.0, 0.0, 0.0, 0.0)
    cr.set_source(aura)
    cr.arc(0, 0, r_out + 44.0, 0, math.tau)
    cr.fill()

    # ── 2. Frosted obsidian glass chassis disc ──────────────────────────
    chassis_r = r_out + 14.0
    chassis_grad = cairo.RadialGradient(-r_out * 0.28, -r_out * 0.35, 10.0, 0, 0, chassis_r)
    chassis_grad.add_color_stop_rgba(0.0, bg_ring[0] * 1.18, bg_ring[1] * 1.18, bg_ring[2] * 1.18, 0.93 * master_alpha)
    chassis_grad.add_color_stop_rgba(0.75, bg_ring[0], bg_ring[1], bg_ring[2], 0.92 * master_alpha)
    chassis_grad.add_color_stop_rgba(1.0, bg_outer[0], bg_outer[1], bg_outer[2], 0.95 * master_alpha)
    cr.set_source(chassis_grad)
    cr.arc(0, 0, chassis_r, 0, math.tau)
    cr.fill()

    # Crisp machined outer specular bezel ring
    cr.set_line_width(1.6)
    bezel_grad = cairo.LinearGradient(-chassis_r, -chassis_r, chassis_r, chassis_r)
    bezel_grad.add_color_stop_rgba(0.0, accent_hi[0], accent_hi[1], accent_hi[2], 0.42 * master_alpha)
    bezel_grad.add_color_stop_rgba(0.5, border[0], border[1], border[2], 0.55 * master_alpha)
    bezel_grad.add_color_stop_rgba(1.0, secondary[0], secondary[1], secondary[2], 0.36 * master_alpha)
    cr.set_source(bezel_grad)
    cr.arc(0, 0, chassis_r - 0.8, 0, math.tau)
    cr.stroke()

    # ── 3. Precision outer vernier telemetry ticks (64 divisions) ───────
    tick_r0 = r_out + 4.5
    tick_r1_minor = r_out + 8.5
    tick_r1_major = r_out + 11.5
    vernier_rot = ambient_phase * 0.14
    for k in range(64):
        ang = -math.pi * 0.5 + k * (math.tau / 64.0) + vernier_rot
        is_major = (k % 8) == 0
        tr1 = tick_r1_major if is_major else tick_r1_minor
        cr.set_line_width(1.5 if is_major else 0.95)
        if is_major:
            cr.set_source_rgba(secondary[0], secondary[1], secondary[2], 0.58 * master_alpha)
        else:
            cr.set_source_rgba(border[0], border[1], border[2], 0.42 * master_alpha)
        cr.move_to(math.cos(ang) * tick_r0, math.sin(ang) * tick_r0)
        cr.line_to(math.cos(ang) * tr1, math.sin(ang) * tr1)
        cr.stroke()

    # ── 4. Eight Spring-Animated Action Slices ──────────────────────────
    scale_k = r_out / 174.0
    for i, seg in enumerate(slices):
        lift = slice_lifts[i] if i < len(slice_lifts) else (1.0 if i == selected else 0.0)
        is_sel = (i == selected) or (i == confirm_idx and close_t > 0.0)
        is_disabled = (seg.action_type or "").lower() == "disabled"

        mid = -math.pi * 0.5 + i * seg_angle
        a1 = mid - seg_angle * 0.5 + gap_rad
        a2 = mid + seg_angle * 0.5 - gap_rad

        # Spring radial outward lift on hover/selection
        s_in = r_in + 3.5 + lift * 2.5
        s_out = r_out - 2.0 + lift * 10.5

        cr.new_sub_path()
        cr.arc(0, 0, s_out, a1, a2)
        cr.arc_negative(0, 0, s_in, a2, a1)
        cr.close_path()

        # Rich radial glass gradient per slice
        mid_x = math.cos(mid) * ((s_in + s_out) * 0.52)
        mid_y = math.sin(mid) * ((s_in + s_out) * 0.52)
        sg = cairo.RadialGradient(mid_x, mid_y, 8.0, 0, 0, s_out + 12.0)

        if lift > 0.02:
            # Blend smoothly from idle glass into luminous theme highlight
            r0 = seg_idle[0] + (seg_hover[0] - seg_idle[0]) * lift
            g0 = seg_idle[1] + (seg_hover[1] - seg_idle[1]) * lift
            b0 = seg_idle[2] + (seg_hover[2] - seg_idle[2]) * lift
            sg.add_color_stop_rgba(
                0.0,
                r0 + (accent[0] - r0) * (0.34 * lift),
                g0 + (accent[1] - g0) * (0.34 * lift),
                b0 + (accent[2] - b0) * (0.34 * lift),
                (0.84 + 0.13 * lift) * master_alpha,
            )
            sg.add_color_stop_rgba(
                1.0,
                r0,
                g0,
                b0,
                (0.76 + 0.18 * lift) * master_alpha,
            )
        else:
            alpha_idle = (0.45 if is_disabled else 0.78) * master_alpha
            sg.add_color_stop_rgba(0.0, seg_idle[0] * 1.15, seg_idle[1] * 1.15, seg_idle[2] * 1.15, alpha_idle)
            sg.add_color_stop_rgba(1.0, seg_idle[0] * 0.90, seg_idle[1] * 0.90, seg_idle[2] * 0.90, alpha_idle)

        cr.set_source(sg)
        cr.fill_preserve()

        # Crisp bevel rim (glows bright on hover / confirm)
        if lift > 0.05:
            cr.set_source_rgba(
                border[0] + (accent_hi[0] - border[0]) * lift,
                border[1] + (accent_hi[1] - border[1]) * lift,
                border[2] + (accent_hi[2] - border[2]) * lift,
                (0.45 + 0.52 * lift) * master_alpha,
            )
            cr.set_line_width(1.2 + 1.3 * lift)
        else:
            cr.set_source_rgba(border[0], border[1], border[2], 0.42 * master_alpha)
            cr.set_line_width(1.1)
        cr.stroke()

        # Luminous energy arc bar along outer edge of lifted/active slice
        if lift > 0.05:
            cr.save()
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            # Soft outer bloom pass
            cr.set_source_rgba(accent[0], accent[1], accent[2], 0.34 * lift * master_alpha)
            cr.set_line_width(7.5 * scale_k)
            cr.arc(0, 0, s_out - 2.2, a1 + 0.04, a2 - 0.04)
            cr.stroke()
            # Razor-sharp specular core bar
            cr.set_source_rgba(accent_hi[0], accent_hi[1], accent_hi[2], 0.95 * lift * master_alpha)
            cr.set_line_width(2.6 * scale_k)
            cr.arc(0, 0, s_out - 2.2, a1 + 0.04, a2 - 0.04)
            cr.stroke()
            cr.restore()

        # Slice geometric icon + title + optional shortcut hint
        content_r = (s_in + s_out) * 0.525
        lx = math.cos(mid) * content_r
        ly = math.sin(mid) * content_r

        hint = format_action_hint(seg) if show_hints else ""
        icon_y_off = (-13.5 if hint else -9.5) * scale_k
        title_y_off = (6.0 if hint else 10.5) * scale_k
        hint_y_off = 19.5 * scale_k

        icon_rgb = (
            ink[0] + (accent_hi[0] - ink[0]) * lift,
            ink[1] + (accent_hi[1] - ink[1]) * lift,
            ink[2] + (accent_hi[2] - ink[2]) * lift,
        )
        icon_alpha = (0.35 if is_disabled else (0.76 + 0.24 * lift)) * master_alpha
        _draw_vector_icon(cr, resolve_icon_kind(seg), lx, ly + icon_y_off, 10.2 * scale_k, icon_rgb, icon_alpha)

        # Title text
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if is_sel else cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size((12.4 if is_sel else 11.4) * scale_k)
        label = seg.label or f"Slice {i + 1}"
        if len(label) > 12:
            label = label[:11] + "…"
        ext = cr.text_extents(label)
        txt_alpha = (0.38 if is_disabled else (0.86 + 0.14 * lift)) * master_alpha
        cr.set_source_rgba(ink[0], ink[1], ink[2], txt_alpha)
        cr.move_to(lx - ext.width / 2.0 - ext.x_bearing, ly + title_y_off)
        cr.show_text(label)

        # Optional telemetry shortcut subtitle
        if hint:
            cr.select_font_face("Monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(8.8 * scale_k)
            hext = cr.text_extents(hint)
            if lift > 0.2:
                cr.set_source_rgba(accent_hi[0], accent_hi[1], accent_hi[2], (0.75 + 0.20 * lift) * master_alpha)
            else:
                cr.set_source_rgba(ink_sub[0], ink_sub[1], ink_sub[2], 0.72 * master_alpha)
            cr.move_to(lx - hext.width / 2.0 - hext.x_bearing, ly + hint_y_off)
            cr.show_text(hint)

    # ── 5. Confirm-Burst Shockwave Ring (on release) ────────────────────
    if confirm_idx is not None and close_t > 0.0:
        burst_r = r_in + (r_out - r_in + 28.0) * close_t
        burst_a = max(0.0, (1.0 - close_t) * 0.85)
        cr.set_source_rgba(accent_hi[0], accent_hi[1], accent_hi[2], burst_a)
        cr.set_line_width(3.2 * (1.0 - close_t * 0.5))
        cr.arc(0, 0, burst_r, 0, math.tau)
        cr.stroke()

    # ── 6. Center Deadzone Core + Live Analog Magnetic Compass ──────────
    hub_r = r_in - 3.5
    hub_grad = cairo.RadialGradient(-hub_r * 0.25, -hub_r * 0.30, 4.0, 0, 0, hub_r)
    hub_grad.add_color_stop_rgba(0.0, bg_core[0] * 1.45, bg_core[1] * 1.45, bg_core[2] * 1.45, 0.96 * master_alpha)
    hub_grad.add_color_stop_rgba(1.0, bg_outer[0], bg_outer[1], bg_outer[2], 0.97 * master_alpha)
    cr.set_source(hub_grad)
    cr.arc(0, 0, hub_r, 0, math.tau)
    cr.fill()

    dist = math.hypot(ptr_dx, ptr_dy)
    dz = max(12.0, float(cancel_radius))
    progress = min(1.0, dist / dz)

    # Base inner hub bezel
    cr.set_line_width(1.6)
    if selected is None:
        cr.set_source_rgba(cancel_rgb[0], cancel_rgb[1], cancel_rgb[2], (0.35 + 0.30 * progress) * master_alpha)
    else:
        cr.set_source_rgba(accent[0], accent[1], accent[2], 0.82 * master_alpha)
    cr.arc(0, 0, hub_r, 0, math.tau)
    cr.stroke()

    # Live analog deadzone activation progress arc
    if progress > 0.04 and selected is None:
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_width(2.6)
        cr.set_source_rgba(secondary[0], secondary[1], secondary[2], 0.85 * master_alpha)
        cr.arc(0, 0, hub_r - 3.2, -math.pi * 0.5, -math.pi * 0.5 + math.tau * progress)
        cr.stroke()

    # Live magnetic compass needle + cursor tether puck tracking real hand vector!
    if dist > 2.5 or selected is not None:
        if dist > 2.5:
            ang = math.atan2(ptr_dy, ptr_dx)
            puck_r = min(hub_r - 6.5, (dist / dz) * (hub_r - 6.5))
        else:
            ang = -math.pi * 0.5 + (selected or 0) * seg_angle
            puck_r = hub_r - 6.5

        px = math.cos(ang) * puck_r
        py = math.sin(ang) * puck_r

        # Luminous directional arc sweep along the hub bezel facing the pointer angle
        cr.save()
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source_rgba(accent[0], accent[1], accent[2], 0.42 * master_alpha)
        cr.set_line_width(5.5 * scale_k)
        cr.arc(0, 0, hub_r, ang - 0.34, ang + 0.34)
        cr.stroke()
        cr.set_source_rgba(accent_hi[0], accent_hi[1], accent_hi[2], 0.96 * master_alpha)
        cr.set_line_width(2.2 * scale_k)
        cr.arc(0, 0, hub_r, ang - 0.28, ang + 0.28)
        cr.stroke()
        cr.restore()

        # Subtle outer tether + glowing cursor puck (keeps center readout 100% crisp!)
        if puck_r > hub_r * 0.48:
            sx = math.cos(ang) * (hub_r * 0.56)
            sy = math.sin(ang) * (hub_r * 0.56)
            tether = cairo.LinearGradient(sx, sy, px, py)
            tether.add_color_stop_rgba(0.0, secondary[0], secondary[1], secondary[2], 0.08 * master_alpha)
            tether.add_color_stop_rgba(1.0, accent_hi[0], accent_hi[1], accent_hi[2], 0.85 * master_alpha)
            cr.set_source(tether)
            cr.set_line_width(1.8)
            cr.move_to(sx, sy)
            cr.line_to(px, py)
            cr.stroke()

        # Glowing directional cursor puck
        cr.set_source_rgba(accent[0], accent[1], accent[2], 0.34 * master_alpha)
        cr.arc(px, py, 6.2 * scale_k, 0, math.tau)
        cr.fill()
        cr.set_source_rgba(accent_hi[0], accent_hi[1], accent_hi[2], 0.96 * master_alpha)
        cr.arc(px, py, 2.7 * scale_k, 0, math.tau)
        cr.fill()

        # Precision outer hub compass pointer wedge aiming directly into active slice
        if selected is not None:
            tip_r = hub_r + 8.0 * scale_k
            base_r = hub_r - 0.5
            spread = 0.14
            cr.move_to(math.cos(ang) * tip_r, math.sin(ang) * tip_r)
            cr.line_to(math.cos(ang - spread) * base_r, math.sin(ang - spread) * base_r)
            cr.line_to(math.cos(ang + spread) * base_r, math.sin(ang + spread) * base_r)
            cr.close_path()
            cr.set_source_rgba(accent_hi[0], accent_hi[1], accent_hi[2], 0.96 * master_alpha)
            cr.fill()

    # Center status readout
    cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    if selected is None:
        cr.set_font_size(10.0 * scale_k)
        c_txt = "CANCEL"
        ce = cr.text_extents(c_txt)
        cr.set_source_rgba(ink_sub[0], ink_sub[1], ink_sub[2], 0.76 * master_alpha)
        cr.move_to(-ce.width / 2.0 - ce.x_bearing, 3.5 * scale_k)
        cr.show_text(c_txt)
    else:
        sel_seg = slices[selected]
        cr.set_font_size(10.8 * scale_k)
        s_txt = (sel_seg.label or "Action")[:10]
        se = cr.text_extents(s_txt)
        cr.set_source_rgba(accent_hi[0], accent_hi[1], accent_hi[2], 0.96 * master_alpha)
        cr.move_to(-se.width / 2.0 - se.x_bearing, 3.5 * scale_k)
        cr.show_text(s_txt)

    cr.restore()

    # ── 7. Floating Precision Telemetry HUD Pill at Bottom ──────────────
    pill_y = cy + r_out + 22.0
    if selected is not None and 0 <= selected < n:
        active = slices[selected]
        hint_part = format_action_hint(active)
        hud_text = f"{profile_name}  ·  {active.label}" + (f"  [{hint_part}]" if hint_part else "")
    else:
        hud_text = f"{profile_name}  ·  Flick to select · Release center to cancel"

    cr.save()
    cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    cr.set_font_size(11.0)
    te = cr.text_extents(hud_text)
    pw = min(width - 20.0, te.width + 28.0)
    ph = 24.0
    px0 = cx - pw / 2.0
    py0 = min(height - ph - 4.0, pill_y)

    _rounded_pill(cr, px0, py0, pw, ph, ph * 0.5)
    cr.set_source_rgba(bg_outer[0], bg_outer[1], bg_outer[2], 0.90 * master_alpha)
    cr.fill_preserve()
    cr.set_line_width(1.1)
    if selected is not None:
        cr.set_source_rgba(accent[0], accent[1], accent[2], 0.65 * master_alpha)
    else:
        cr.set_source_rgba(border[0], border[1], border[2], 0.55 * master_alpha)
    cr.stroke()

    # Small glowing status pip inside HUD pill
    pip_rgb = accent if selected is not None else secondary
    cr.set_source_rgba(pip_rgb[0], pip_rgb[1], pip_rgb[2], 0.95 * master_alpha)
    cr.arc(px0 + 11.0, py0 + ph * 0.5, 3.0, 0, math.tau)
    cr.fill()

    cr.set_source_rgba(ink[0], ink[1], ink[2], 0.92 * master_alpha)
    cr.move_to(px0 + 19.0, py0 + ph * 0.5 + te.height * 0.36)
    cr.show_text(hud_text)
    cr.restore()


# ─────────────────────────── Wayland GTK4 Layer-Shell Window ──────────────

class ActionsRingOverlay:
    """Floating 60 FPS transparent radial menu positioned at the cursor."""

    def __init__(self, slices: Optional[list[ActionSlice]] = None):
        _ensure_gtk()
        self._win = Gtk.Window()
        self._slices: list[ActionSlice] = list(slices) if slices else []
        self._profile_name: str = "Default"
        self._selected: Optional[int] = None

        self._theme: RingTheme = get_ring_theme("studio")
        self._size: RingSizeSpec = get_ring_size("standard")
        self._show_hints: bool = True
        self._animate: bool = True
        self._cancel_radius: float = 40.0

        # 60 FPS animation state
        self._open_t: float = 0.0
        self._close_t: float = 0.0
        self._closing: bool = False
        self._confirm_idx: Optional[int] = None
        self._slice_lifts: list[float] = [0.0] * 8
        self._ptr_target: tuple[float, float] = (0.0, 0.0)
        self._ptr_smooth: tuple[float, float] = (0.0, 0.0)
        self._ambient_phase: float = 0.0
        self._last_tick: float = 0.0
        self._tick_id: int = 0

        self._setup_window()
        self._setup_layer_shell()
        self._setup_drawing_area()

    # ─── GTK proxy helpers ──────────────────────────────────────────────

    def get_visible(self) -> bool:
        return self._win.get_visible()

    def set_visible(self, visible: bool) -> None:
        if not visible:
            self._stop_ticker()
            self._closing = False
        self._win.set_visible(visible)

    def _setup_window(self) -> None:
        self._win.set_title("MX4 Actions Ring")
        self._win.set_decorated(False)
        self._win.set_resizable(False)
        self._win.set_default_size(self._size.canvas, self._size.canvas)

        css = Gtk.CssProvider()
        css.load_from_data(b"window, window.background { background: transparent; }")
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _setup_layer_shell(self) -> None:
        if not _HAS_LAYER_SHELL or LayerShell is None:
            logger.warning("gtk4-layer-shell unavailable — overlay will float")
            return
        LayerShell.init_for_window(self._win)
        LayerShell.set_layer(self._win, LayerShell.Layer.OVERLAY)
        LayerShell.set_namespace(self._win, "mx4-actions-ring")
        LayerShell.set_keyboard_mode(self._win, LayerShell.KeyboardMode.NONE)
        LayerShell.set_exclusive_zone(self._win, -1)
        LayerShell.set_anchor(self._win, LayerShell.Edge.TOP, True)
        LayerShell.set_anchor(self._win, LayerShell.Edge.LEFT, True)

    def _setup_drawing_area(self) -> None:
        self._area = Gtk.DrawingArea()
        self._area.set_content_width(self._size.canvas)
        self._area.set_content_height(self._size.canvas)
        self._area.set_draw_func(self._draw)
        self._win.set_child(self._area)

    # ─── Configuration & Theme API ──────────────────────────────────────

    def configure(
        self,
        *,
        theme_id: str | None = None,
        size_id: str | None = None,
        show_hints: bool | None = None,
        animate: bool | None = None,
        cancel_radius: float | None = None,
    ) -> None:
        if theme_id is not None:
            self._theme = get_ring_theme(theme_id)
        if size_id is not None:
            new_size = get_ring_size(size_id)
            if new_size.canvas != self._size.canvas:
                self._size = new_size
                self._win.set_default_size(new_size.canvas, new_size.canvas)
                self._area.set_content_width(new_size.canvas)
                self._area.set_content_height(new_size.canvas)
            else:
                self._size = new_size
        if show_hints is not None:
            self._show_hints = bool(show_hints)
        if animate is not None:
            self._animate = bool(animate)
        if cancel_radius is not None:
            self._cancel_radius = max(15.0, min(120.0, float(cancel_radius)))
        self._area.queue_draw()

    # ─── Public Gesture / Preview API ───────────────────────────────────

    def load_profile(self, profile: RingProfile) -> None:
        self._slices = list(profile.slices)
        self._profile_name = profile.app_name
        self._selected = None
        self._slice_lifts = [0.0] * max(8, len(self._slices))
        self._area.queue_draw()

    def show_at_cursor(self) -> None:
        self._closing = False
        self._close_t = 0.0
        self._confirm_idx = None
        self._selected = None
        self._ptr_target = (0.0, 0.0)
        self._ptr_smooth = (0.0, 0.0)
        self._slice_lifts = [0.0] * max(8, len(self._slices))
        self._open_t = 0.0 if self._animate else 1.0

        cx, cy = self._cursor_pos()
        half = self._size.canvas // 2
        if _HAS_LAYER_SHELL and LayerShell is not None:
            mon_x, mon_y, mon_w, mon_h = self._monitor_at(cx, cy)
            lx = max(0, min(cx - mon_x - half, mon_w - self._size.canvas))
            ly = max(0, min(cy - mon_y - half + 16, mon_h - self._size.canvas))
            LayerShell.set_margin(self._win, LayerShell.Edge.LEFT, int(lx))
            LayerShell.set_margin(self._win, LayerShell.Edge.TOP, int(ly))

        self._win.set_visible(True)
        self._area.queue_draw()
        self._start_ticker()

    def update_selection(self, seg: Optional[int]) -> None:
        if seg != self._selected:
            self._selected = seg
            if not self._animate:
                self._slice_lifts = [1.0 if i == seg else 0.0 for i in range(max(8, len(self._slices)))]
            self._area.queue_draw()

    def update_pointer(self, dx: float, dy: float, seg: Optional[int]) -> None:
        """Feed live analog hand movement ``(dx, dy)`` + discrete slice selection."""
        self._ptr_target = (float(dx), float(dy))
        self._selected = seg
        if not self._animate:
            self._ptr_smooth = self._ptr_target
            self._slice_lifts = [1.0 if i == seg else 0.0 for i in range(max(8, len(self._slices)))]
            self._area.queue_draw()

    def hide_and_pick(self) -> Optional[ActionSlice]:
        """Return the selected ActionSlice immediately and play a crisp confirm burst."""
        idx = self._selected
        chosen = (
            self._slices[idx]
            if (idx is not None and 0 <= idx < len(self._slices))
            else None
        )
        if self._animate and self._win.get_visible():
            self._closing = True
            self._close_t = 0.0
            self._confirm_idx = idx if chosen is not None else None
            self._start_ticker()
        else:
            self.set_visible(False)
            self._selected = None
        return chosen

    # ─── 60 FPS Spring Animation Loop ───────────────────────────────────

    def _start_ticker(self) -> None:
        if self._tick_id:
            return
        self._last_tick = time.monotonic()
        self._tick_id = GLib.timeout_add(16, self._tick)

    def _stop_ticker(self) -> None:
        if self._tick_id:
            GLib.source_remove(self._tick_id)
            self._tick_id = 0

    def _tick(self) -> bool:
        if not self._win.get_visible():
            self._tick_id = 0
            return False

        now = time.monotonic()
        dt = max(0.001, min(0.05, now - self._last_tick))
        self._last_tick = now

        if self._animate:
            self._ambient_phase += dt
            if not self._closing:
                self._open_t = min(1.0, self._open_t + dt / 0.165)
            else:
                self._close_t = min(1.0, self._close_t + dt / 0.145)
                if self._close_t >= 1.0:
                    self._closing = False
                    self._selected = None
                    self._confirm_idx = None
                    self._win.set_visible(False)
                    self._tick_id = 0
                    return False

            # Smooth spring hover lift per slice
            lift_k = 1.0 - math.exp(-18.0 * dt)
            n = max(8, len(self._slices))
            if len(self._slice_lifts) < n:
                self._slice_lifts.extend([0.0] * (n - len(self._slice_lifts)))
            active_idx = self._confirm_idx if self._closing else self._selected
            for i in range(n):
                goal = 1.0 if i == active_idx else 0.0
                self._slice_lifts[i] += (goal - self._slice_lifts[i]) * lift_k

            # Silky low-pass pointer tether tracking
            ptr_k = 1.0 - math.exp(-22.0 * dt)
            self._ptr_smooth = (
                self._ptr_smooth[0] + (self._ptr_target[0] - self._ptr_smooth[0]) * ptr_k,
                self._ptr_smooth[1] + (self._ptr_target[1] - self._ptr_smooth[1]) * ptr_k,
            )

        self._area.queue_draw()
        return True

    # ─── Cursor / Monitor Placement ─────────────────────────────────────

    def _cursor_pos(self) -> tuple[int, int]:
        try:
            r = subprocess.run(
                ["hyprctl", "cursorpos"],
                capture_output=True, text=True, timeout=0.4,
            )
            if r.returncode == 0:
                a, b = r.stdout.strip().split(",")
                return int(a.strip()), int(b.strip())
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
        return 960, 540

    def _monitor_at(self, x: int, y: int) -> tuple[int, int, int, int]:
        try:
            import json

            r = subprocess.run(
                ["hyprctl", "monitors", "-j"],
                capture_output=True, text=True, timeout=0.4,
            )
            if r.returncode == 0:
                for m in json.loads(r.stdout):
                    mx, my = int(m.get("x", 0)), int(m.get("y", 0))
                    scale = float(m.get("scale", 1.0) or 1.0)
                    mw = int(m.get("width", 1920) / scale)
                    mh = int(m.get("height", 1080) / scale)
                    if mx <= x < mx + mw and my <= y < my + mh:
                        self._set_monitor_by_name(m.get("name"))
                        return mx, my, mw, mh
        except Exception as e:
            logger.debug("monitor lookup failed: %s", e)
        return 0, 0, 1920, 1080

    def _set_monitor_by_name(self, name: Optional[str]) -> None:
        if not name or not _HAS_LAYER_SHELL or LayerShell is None:
            return
        display = Gdk.Display.get_default()
        if not display:
            return
        monitors = display.get_monitors()
        for i in range(monitors.get_n_items()):
            mon = monitors.get_item(i)
            if mon.get_connector() == name:
                LayerShell.set_monitor(self._win, mon)
                return

    # ─── Cairo Draw Callback ────────────────────────────────────────────

    def _draw(self, _area, cr: cairo.Context, width: int, height: int) -> None:
        render_ring_frame(
            cr,
            width,
            height,
            slices=self._slices,
            profile_name=self._profile_name,
            theme=self._theme,
            size_spec=self._size,
            selected=self._selected,
            slice_lifts=self._slice_lifts,
            open_t=self._open_t,
            close_t=self._close_t,
            confirm_idx=self._confirm_idx,
            ptr_dx=self._ptr_smooth[0],
            ptr_dy=self._ptr_smooth[1],
            cancel_radius=self._cancel_radius,
            ambient_phase=self._ambient_phase,
            show_hints=self._show_hints,
        )
