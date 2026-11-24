"""MX Master 4 vector mouse preview.

Ported from the reference SVG in the design spec. Rendered in Cairo
rather than as an embedded SVG image so we can:

* Hit-test clicks and tell the caller which physical CID was clicked.
* Overlay a pulsing highlight on any button whose CID is in the live
  ``pressed`` set (driven by the daemon's evdev tracker at 70 ms).
* Mark buttons with a subtle indicator when they've been rebound so
  the user can see at a glance which controls are customised.

Geometry matches the reference SVG 1:1 against a 400×600 viewBox; the
widget scales to its allocated size while preserving aspect ratio.
"""

from __future__ import annotations

import math
from typing import Optional

import cairo  # type: ignore[import-untyped]
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk, GLib, GObject

from ...hidpp import ControlID


# ─── Colours from the reference SVG ───────────────────────────────────

_BG_TOP        = (0.165, 0.165, 0.180)  # #2a2a2e
_BG_BOT        = (0.122, 0.122, 0.133)  # #1f1f22
_CHASSIS_HI    = (0.196, 0.196, 0.220)  # #323238
_CHASSIS_LO    = (0.110, 0.110, 0.125)  # #1c1c20
_BUTTON        = (0.208, 0.208, 0.227)  # #35353a
_BUTTON_DARK   = (0.133, 0.133, 0.149)  # #222226
_WHEEL_BG      = (0.071, 0.071, 0.078)  # #121214
_WHEEL_RIDGE   = (0.200, 0.200, 0.200)  # #333333
_THUMB_BG      = (0.176, 0.176, 0.196)  # #2d2d32
_THUMB_DOT     = (0.102, 0.102, 0.118)  # #1a1a1e
_GLYPH_BLUE    = (0.529, 0.808, 0.922)  # #87CEEB
_PINK_GLOW     = (1.0, 0.412, 0.706)    # #FF69B4
_ACCENT_COPPER = (0.83, 0.65, 0.46)     # copper — shared with the rest of the app


# Normalised hit-test rects (x, y, w, h in viewBox coords) per CID.
# Side layout, top to bottom:
#   thumb wheel → SmartShift (new 3rd side button) → Back → Forward → gesture
# pad. The MX Master 4 places SmartShift on the side, not behind the
# wheel like older models.
_VIEWBOX_W, _VIEWBOX_H = 400.0, 600.0

_HIT_RECTS: list[tuple[int, str, tuple[float, float, float, float]]] = [
    (ControlID.THUMB_WHEEL,    "Thumb wheel",  (80,  218,  8,  44)),
    (ControlID.SMART_SHIFT,    "Mode shift",   (120, 222, 28,  22)),
    (ControlID.BACK,           "Back",         (120, 252, 28,  24)),
    (ControlID.FORWARD,        "Forward",      (120, 282, 28,  24)),
    (ControlID.GESTURE_BUTTON, "Gesture",      (102, 316, 58,  78)),
    # Middle wheel click inside the scroll-wheel housing
    (ControlID.MIDDLE_CLICK,   "Wheel click",  (188, 150, 24,  60)),
    # Big main clicks last so they act as the fallback hit target
    (ControlID.LEFT_CLICK,     "Left click",   (110, 140, 65,  95)),
    (ControlID.RIGHT_CLICK,    "Right click",  (225, 140, 65,  95)),
]

# Convenient export for dialog labels
BUTTON_LABELS = {cid: name for cid, name, _ in _HIT_RECTS}


class MouseSVG(Gtk.DrawingArea):
    """Interactive mouse preview.

    Signals
    -------
    ``button-clicked (int)`` — user clicked the region for this CID.
    """

    __gsignals__ = {
        "button-clicked": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
    }

    def __init__(self, pixel_size: int = 260, *, show_label: bool = False):
        super().__init__()
        self._pressed: set[int] = set()
        self._remapped: set[int] = set()
        self._hover: Optional[int] = None

        # The widget reserves footer space (and a taller viewBox) only when
        # the caller opts into the name/status label. No caller does today,
        # but the parameter keeps the geometry correct if one ever does.
        self._show_label = show_label
        if show_label:
            effective_h = _VIEWBOX_H
        else:
            effective_h = 470
        self._viewbox_h_effective = effective_h

        height = int(pixel_size * effective_h / _VIEWBOX_W)
        self.set_size_request(pixel_size, height)
        self.set_draw_func(self._draw)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion)
        motion.connect("leave", self._on_leave)
        self.add_controller(motion)

        click = Gtk.GestureClick()
        click.connect("pressed", self._on_click)
        self.add_controller(click)

        # Pulse animation for pressed / glow effect
        self._anim_t = 0.0
        self._anim_src: Optional[int] = None

    # ─── state mutators ─────────────────────────────────────────────

    def set_pressed_cids(self, cids: set[int]) -> None:
        if cids == self._pressed:
            return
        was_empty = not self._pressed
        self._pressed = set(cids)
        self.queue_draw()
        if self._pressed and was_empty:
            self._start_anim()
        elif not self._pressed:
            self._stop_anim()

    def set_remapped_cids(self, cids: set[int]) -> None:
        if cids != self._remapped:
            self._remapped = set(cids)
            self.queue_draw()

    # ─── animation ──────────────────────────────────────────────────

    def _start_anim(self) -> None:
        if self._anim_src is not None:
            return
        self._anim_src = GLib.timeout_add(16, self._tick)

    def _stop_anim(self) -> None:
        if self._anim_src is not None:
            GLib.source_remove(self._anim_src)
            self._anim_src = None
        self._anim_t = 0.0

    def _tick(self) -> bool:
        self._anim_t = (self._anim_t + 0.05) % 1.0
        self.queue_draw()
        return True

    # ─── input ──────────────────────────────────────────────────────

    def _to_viewbox(self, x: float, y: float) -> tuple[float, float]:
        """Convert widget-pixel (x, y) into the SVG viewBox space."""
        w, h = self.get_width(), self.get_height()
        vh = self._viewbox_h_effective
        scale = min(w / _VIEWBOX_W, h / vh)
        dx = (w - _VIEWBOX_W * scale) / 2
        dy = (h - vh * scale) / 2
        return (x - dx) / scale, (y - dy) / scale

    def _hit(self, x: float, y: float) -> Optional[int]:
        vx, vy = self._to_viewbox(x, y)
        for cid, _name, (rx, ry, rw, rh) in _HIT_RECTS:
            if rx <= vx < rx + rw and ry <= vy < ry + rh:
                return cid
        return None

    def _on_motion(self, _ctrl, x, y):
        cid = self._hit(x, y)
        if cid != self._hover:
            self._hover = cid
            self.set_cursor(
                Gdk.Cursor.new_from_name("pointer" if cid else "default", None)
            )
            self.queue_draw()

    def _on_leave(self, _ctrl):
        if self._hover is not None:
            self._hover = None
            self.queue_draw()

    def _on_click(self, _g, _n, x, y):
        cid = self._hit(x, y)
        if cid is not None:
            self.emit("button-clicked", cid)

    # ─── drawing ────────────────────────────────────────────────────

    def _draw(self, _area, cr: cairo.Context, width: int, height: int) -> None:
        vh = self._viewbox_h_effective
        scale = min(width / _VIEWBOX_W, height / vh)
        cr.translate((width - _VIEWBOX_W * scale) / 2,
                     (height - vh * scale) / 2)
        cr.scale(scale, scale)

        self._draw_card(cr, vh)
        self._draw_pink_glow(cr)
        self._draw_chassis(cr)
        self._draw_scroll_housing(cr)
        self._draw_main_buttons(cr)
        self._draw_wheel(cr)
        self._draw_side_buttons(cr)
        self._draw_thumb_wheel(cr)
        self._draw_thumb_pad(cr)
        # Pressed / hover overlays drawn last so they sit above everything
        self._draw_overlays(cr)

    # --- Building blocks (all drawn in viewBox 400×600 coords) ---

    @staticmethod
    def _rounded_rect(cr, x, y, w, h, r) -> None:
        cr.new_path()
        cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
        cr.arc(x + w - r, y + r, r, 1.5 * math.pi, 2 * math.pi)
        cr.arc(x + w - r, y + h - r, r, 0, 0.5 * math.pi)
        cr.arc(x + r, y + h - r, r, 0.5 * math.pi, math.pi)
        cr.close_path()

    @staticmethod
    def _chassis_path(cr) -> None:
        """Port of the reference SVG path for the mouse body silhouette."""
        cr.new_path()
        cr.move_to(150, 130)
        cr.curve_to(180, 120, 220, 120, 250, 130)
        cr.curve_to(290, 160, 310, 260, 280, 370)
        cr.curve_to(260, 440, 170, 460, 130, 400)
        cr.curve_to(80, 330, 80, 230, 110, 180)
        cr.curve_to(120, 150, 135, 140, 150, 130)
        cr.close_path()

    def _draw_card(self, cr, vh: float) -> None:
        # Soft drop shadow under the whole card
        cr.set_source_rgba(0, 0, 0, 0.45)
        self._rounded_rect(cr, 8, 16, _VIEWBOX_W - 16, vh - 16, 24)
        cr.fill()

        # Card gradient
        grad = cairo.LinearGradient(0, 0, 0, vh)
        grad.add_color_stop_rgb(0, *_BG_TOP)
        grad.add_color_stop_rgb(1, *_BG_BOT)
        cr.set_source(grad)
        self._rounded_rect(cr, 0, 0, _VIEWBOX_W, vh, 24)
        cr.fill()

        # Card rim highlight
        cr.set_source_rgba(1, 1, 1, 0.04)
        self._rounded_rect(cr, 0, 0, _VIEWBOX_W, vh, 24)
        cr.set_line_width(1)
        cr.stroke()

    def _draw_pink_glow(self, cr) -> None:
        """Approximate the SVG's Gaussian-blurred hot-pink underglow.

        Real blur in Cairo would be expensive per-frame; stacking four
        translucent strokes at increasing widths produces a visually
        similar halo at near-zero cost.
        """
        for i, (width, alpha) in enumerate(
            ((22, 0.04), (16, 0.06), (10, 0.08), (5, 0.10))
        ):
            cr.set_source_rgba(*_PINK_GLOW, alpha)
            cr.set_line_width(width)
            self._chassis_path(cr)
            cr.stroke()

    def _draw_chassis(self, cr) -> None:
        # Body radial gradient
        grad = cairo.RadialGradient(120, 180, 0, 120, 180, 320)
        grad.add_color_stop_rgb(0, *_CHASSIS_HI)
        grad.add_color_stop_rgb(1, *_CHASSIS_LO)
        cr.set_source(grad)
        self._chassis_path(cr)
        cr.fill()

        # Rim
        cr.set_source_rgba(1, 1, 1, 0.04)
        cr.set_line_width(1.5)
        self._chassis_path(cr)
        cr.stroke()

    def _draw_scroll_housing(self, cr) -> None:
        cr.set_source_rgb(*_BUTTON_DARK)
        self._rounded_rect(cr, 180, 145, 40, 90, 8)
        cr.fill()

    def _draw_main_buttons(self, cr) -> None:
        for x in (110, 225):
            cr.set_source_rgb(*_BUTTON)
            self._rounded_rect(cr, x, 140, 65, 95, 10)
            cr.fill()
            cr.set_source_rgba(1, 1, 1, 0.04)
            cr.set_line_width(1)
            self._rounded_rect(cr, x, 140, 65, 95, 10)
            cr.stroke()

    def _draw_wheel(self, cr) -> None:
        # Wheel well
        cr.set_source_rgb(*_WHEEL_BG)
        self._rounded_rect(cr, 190, 155, 20, 50, 6)
        cr.fill()
        # Ridges
        cr.set_source_rgb(*_WHEEL_RIDGE)
        cr.set_line_width(2)
        cr.set_line_cap(cairo.LineCap.ROUND)
        for y in (165, 173, 181, 189, 197):
            cr.move_to(192, y)
            cr.line_to(208, y)
        cr.stroke()

    def _draw_thumb_wheel(self, cr) -> None:
        # Horizontal scroll strip at the top of the side
        cr.set_source_rgb(*_BUTTON)
        self._rounded_rect(cr, 80, 218, 8, 44, 4)
        cr.fill()
        cr.set_source_rgb(*_THUMB_DOT)
        cr.set_line_width(2)
        for y in (226, 234, 242, 250, 258):
            cr.move_to(80, y)
            cr.line_to(88, y)
        cr.stroke()

    def _draw_side_buttons(self, cr) -> None:
        """Three stacked side buttons from top to bottom:

        Mode Shift (under the thumb wheel) → Back → Forward. Each has a
        subtle blue glyph on the sky-blue tint from the reference SVG.
        """
        buttons = [
            # (y, glyph_kind)
            (222, "mode"),      # SmartShift / Mode Shift (new 3rd side button)
            (252, "back"),      # Back
            (282, "forward"),   # Forward
        ]
        for y, kind in buttons:
            cr.set_source_rgb(*_BUTTON)
            self._rounded_rect(cr, 120, y, 28, 24, 6)
            cr.fill()
            cr.set_source_rgba(1, 1, 1, 0.04)
            cr.set_line_width(1)
            self._rounded_rect(cr, 120, y, 28, 24, 6)
            cr.stroke()

            cr.set_source_rgba(*_GLYPH_BLUE, 0.75)
            cr.set_line_width(1.8)
            cr.set_line_cap(cairo.LineCap.ROUND)
            cx, cy = 134, y + 12
            if kind == "mode":
                # Two short horizontal bars stacked — "mode shift" glyph
                cr.move_to(cx - 5, cy - 3)
                cr.line_to(cx + 5, cy - 3)
                cr.move_to(cx - 5, cy + 3)
                cr.line_to(cx + 5, cy + 3)
            elif kind == "back":
                # Left-pointing chevron
                cr.move_to(cx + 3, cy - 4)
                cr.line_to(cx - 3, cy)
                cr.line_to(cx + 3, cy + 4)
            elif kind == "forward":
                # Right-pointing chevron
                cr.move_to(cx - 3, cy - 4)
                cr.line_to(cx + 3, cy)
                cr.line_to(cx - 3, cy + 4)
            cr.stroke()

    def _draw_thumb_pad(self, cr) -> None:
        # Larger thumb pad matching the updated hit rect (x=102 y=316 w=58 h=78)
        cr.set_source_rgb(*_THUMB_BG)
        self._rounded_rect(cr, 102, 316, 58, 78, 10)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 0.02)
        cr.set_line_width(1)
        self._rounded_rect(cr, 102, 316, 58, 78, 10)
        cr.stroke()

        # Dot matrix — 4 columns × 5 rows
        cr.set_source_rgb(*_THUMB_DOT)
        for row_y in (330, 344, 358, 372, 386):
            for col_x in (114, 126, 138, 150):
                cr.new_sub_path()
                cr.arc(col_x, row_y, 2.2, 0, 2 * math.pi)
        cr.fill()

    def _draw_overlays(self, cr) -> None:
        """Draw hover / pressed / remapped accents on top of everything."""
        # Pulse intensity — a sine-wave from 0.35 → 0.80 for pressed buttons
        pulse = 0.35 + 0.45 * (0.5 + 0.5 * math.sin(self._anim_t * 2 * math.pi))

        for cid, _name, (rx, ry, rw, rh) in _HIT_RECTS:
            pressed = cid in self._pressed
            hover = cid == self._hover
            remapped = cid in self._remapped

            if not (pressed or hover or remapped):
                continue

            # Round corners roughly matching the base button
            r = self._corner_radius_for(cid)

            if pressed:
                cr.set_source_rgba(*_ACCENT_COPPER, pulse)
                self._rounded_rect(cr, rx, ry, rw, rh, r)
                cr.fill()
                cr.set_source_rgba(1.0, 0.84, 0.58, 0.9)
                cr.set_line_width(2.2)
                self._rounded_rect(cr, rx, ry, rw, rh, r)
                cr.stroke()
            elif hover:
                cr.set_source_rgba(*_GLYPH_BLUE, 0.20)
                self._rounded_rect(cr, rx, ry, rw, rh, r)
                cr.fill()
                cr.set_source_rgba(*_GLYPH_BLUE, 0.85)
                cr.set_line_width(1.6)
                self._rounded_rect(cr, rx, ry, rw, rh, r)
                cr.stroke()
            elif remapped:
                # Subtle dot marker in the corner — unobtrusive indicator
                cr.set_source_rgba(*_ACCENT_COPPER, 0.75)
                cr.arc(rx + rw - 5, ry + 5, 3, 0, 2 * math.pi)
                cr.fill()

    @staticmethod
    def _corner_radius_for(cid: int) -> float:
        """Match the corner radius each button uses in the base render."""
        if cid in (ControlID.LEFT_CLICK, ControlID.RIGHT_CLICK):
            return 10
        if cid == ControlID.GESTURE_BUTTON:
            return 10
        if cid in (ControlID.BACK, ControlID.FORWARD):
            return 6
        if cid == ControlID.MIDDLE_CLICK:
            return 6
        if cid == ControlID.SMART_SHIFT:
            return 4
        if cid == ControlID.THUMB_WHEEL:
            return 4
        return 6
