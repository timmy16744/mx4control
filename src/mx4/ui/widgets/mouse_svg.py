"""Interactive MX Master 4 mouse preview.

Rendered in Cairo so we can:

* Hit-test clicks to identify which physical button was clicked (for
  click-to-remap).
* Overlay a "pressed" glow on any button currently held down, driven
  by the daemon's live evdev-tracked CID set.
* Stay crisp at any size — everything is vector.

The shapes are deliberately geometric rather than photorealistic;
precision matters more than skeuomorphism for a click-target.
"""

from __future__ import annotations

import math
from typing import Callable, Optional

import cairo  # type: ignore[import-untyped]
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk, GLib

from ...hidpp import ControlID


# Normalised (0..1) hit-test rectangles for each clickable button.
# Coordinates are relative to the 200×280 canvas; the drawing code
# scales to actual pixel dims.
_BUTTON_RECTS: list[tuple[int, str, tuple[float, float, float, float]]] = [
    (ControlID.LEFT_CLICK,    "Left",         (0.20, 0.10, 0.30, 0.28)),
    (ControlID.RIGHT_CLICK,   "Right",        (0.50, 0.10, 0.30, 0.28)),
    (ControlID.MIDDLE_CLICK,  "Wheel click",  (0.45, 0.15, 0.10, 0.17)),
    (ControlID.SMART_SHIFT,   "Mode shift",   (0.47, 0.33, 0.06, 0.04)),
    (ControlID.BACK,          "Back",         (0.14, 0.34, 0.09, 0.05)),
    (ControlID.FORWARD,       "Forward",      (0.14, 0.40, 0.09, 0.05)),
    (ControlID.THUMB_WHEEL,   "Thumb wheel",  (0.12, 0.46, 0.03, 0.15)),
    (ControlID.GESTURE_BUTTON,"Gesture",      (0.14, 0.66, 0.14, 0.13)),
]


class MouseSVG(Gtk.DrawingArea):
    """Interactive vector mouse preview.

    Public API:

        mouse.set_pressed_cids({0x0050})     # list of currently-held CIDs
        mouse.set_remapped_cids({0x0053})    # buttons that have a non-default remap
        mouse.connect("button-clicked", handler)   # emits cid (int)
    """

    __gsignals__ = {
        "button-clicked": (
            # (signal, flags, return-type, arg-types)
            __import__("gi").repository.GObject.SignalFlags.RUN_FIRST,
            None,
            (int,),
        ),
    }

    BASE_W = 200
    BASE_H = 280

    def __init__(self, pixel_size: int = 200):
        super().__init__()
        self._pressed: set[int] = set()
        self._remapped: set[int] = set()
        self._hover_cid: Optional[int] = None

        self.set_size_request(pixel_size, int(pixel_size * self.BASE_H / self.BASE_W))
        self.set_draw_func(self._draw)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion)
        motion.connect("leave", self._on_leave)
        self.add_controller(motion)

        click = Gtk.GestureClick()
        click.connect("pressed", self._on_click)
        self.add_controller(click)

        # Animate the pressed-button pulse at ~60 FPS while something is held
        self._anim_progress = 0.0
        self._anim_source: Optional[int] = None

    # ─── state mutators ─────────────────────────────────────────────────

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

    # ─── animation loop for the press glow ──────────────────────────────

    def _start_anim(self) -> None:
        if self._anim_source is not None:
            return
        self._anim_progress = 0.0
        self._anim_source = GLib.timeout_add(16, self._anim_tick)

    def _stop_anim(self) -> None:
        if self._anim_source is not None:
            GLib.source_remove(self._anim_source)
            self._anim_source = None
        self._anim_progress = 0.0

    def _anim_tick(self) -> bool:
        self._anim_progress = (self._anim_progress + 0.06) % 1.0
        self.queue_draw()
        return True

    # ─── input handling ─────────────────────────────────────────────────

    def _hit_test(self, x: float, y: float) -> Optional[int]:
        w, h = self.get_width(), self.get_height()
        nx, ny = x / w, y / h
        for cid, _name, (rx, ry, rw, rh) in _BUTTON_RECTS:
            if rx <= nx < rx + rw and ry <= ny < ry + rh:
                return cid
        return None

    def _on_motion(self, _ctrl, x, y):
        cid = self._hit_test(x, y)
        if cid != self._hover_cid:
            self._hover_cid = cid
            self.set_cursor(
                Gdk.Cursor.new_from_name("pointer" if cid else "default", None)
            )
            self.queue_draw()

    def _on_leave(self, _ctrl):
        if self._hover_cid is not None:
            self._hover_cid = None
            self.queue_draw()

    def _on_click(self, _g, _n, x, y):
        cid = self._hit_test(x, y)
        if cid is not None:
            self.emit("button-clicked", cid)

    # ─── drawing ────────────────────────────────────────────────────────

    def _draw(self, _area, cr: cairo.Context, width: int, height: int) -> None:
        # Scale to natural coords
        sx = width / self.BASE_W
        sy = height / self.BASE_H
        s = min(sx, sy)
        # Center the mouse in the allocated area
        cr.translate((width - self.BASE_W * s) / 2, (height - self.BASE_H * s) / 2)
        cr.scale(s, s)

        # Body silhouette
        self._draw_body(cr)

        # Buttons, with hover + pressed + remapped states
        for cid, _name, rect in _BUTTON_RECTS:
            self._draw_button(cr, cid, rect)

        # Center wheel ridges and mode-shift button are part of the body
        self._draw_wheel_details(cr)

    def _draw_body(self, cr) -> None:
        # Deep shadow
        cr.set_source_rgba(0, 0, 0, 0.45)
        cr.translate(0, 6)
        self._body_path(cr)
        cr.fill()
        cr.translate(0, -6)

        # Main gradient body
        g = cairo.LinearGradient(0, 0, 0, self.BASE_H)
        g.add_color_stop_rgb(0.00, 0.18, 0.18, 0.21)
        g.add_color_stop_rgb(0.55, 0.10, 0.10, 0.12)
        g.add_color_stop_rgb(1.00, 0.05, 0.05, 0.07)
        cr.set_source(g)
        self._body_path(cr)
        cr.fill()

        # Subtle highlight
        hi = cairo.RadialGradient(100, 70, 0, 100, 70, 110)
        hi.add_color_stop_rgba(0, 1, 1, 1, 0.10)
        hi.add_color_stop_rgba(1, 1, 1, 1, 0.0)
        cr.set_source(hi)
        self._body_path(cr)
        cr.fill()

        # Rim stroke
        cr.set_source_rgba(1, 1, 1, 0.06)
        cr.set_line_width(1)
        self._body_path(cr)
        cr.stroke()

    @staticmethod
    def _body_path(cr) -> None:
        cr.new_path()
        cr.move_to(50, 40)
        cr.curve_to(40, 15, 160, 15, 150, 40)
        cr.curve_to(170, 90, 168, 170, 140, 220)
        cr.curve_to(110, 260, 90, 258, 70, 220)
        cr.curve_to(42, 175, 30, 95, 50, 40)
        cr.close_path()

    def _draw_button(self, cr, cid: int, rect) -> None:
        rx, ry, rw, rh = rect
        x = rx * self.BASE_W
        y = ry * self.BASE_H
        w = rw * self.BASE_W
        h = rh * self.BASE_H

        pressed = cid in self._pressed
        hover = cid == self._hover_cid
        remapped = cid in self._remapped

        # Fill
        radius = 4
        self._rounded(cr, x, y, w, h, radius)
        if pressed:
            # Pulsing copper glow
            pulse = 0.55 + 0.25 * math.sin(self._anim_progress * 2 * math.pi)
            cr.set_source_rgba(0.83, 0.65, 0.46, pulse)
        elif hover:
            cr.set_source_rgba(0.51, 0.63, 0.76, 0.35)  # Nord blue
        elif remapped:
            cr.set_source_rgba(0.71, 0.56, 0.68, 0.28)  # Nord purple
        else:
            # Don't fill idle buttons — the body shows through. Just stroke.
            cr.set_source_rgba(1, 1, 1, 0.03)
        cr.fill()

        # Border
        self._rounded(cr, x, y, w, h, radius)
        if pressed:
            cr.set_source_rgba(1, 0.85, 0.60, 0.85)
            cr.set_line_width(1.8)
        elif hover:
            cr.set_source_rgba(0.53, 0.75, 0.82, 0.95)
            cr.set_line_width(1.4)
        elif remapped:
            cr.set_source_rgba(0.71, 0.56, 0.68, 0.55)
            cr.set_line_width(1.2)
        else:
            cr.set_source_rgba(1, 1, 1, 0.08)
            cr.set_line_width(0.8)
        cr.stroke()

    @staticmethod
    def _rounded(cr, x, y, w, h, r) -> None:
        cr.new_path()
        cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
        cr.arc(x + w - r, y + r, r, 1.5 * math.pi, 2 * math.pi)
        cr.arc(x + w - r, y + h - r, r, 0, 0.5 * math.pi)
        cr.arc(x + r, y + h - r, r, 0.5 * math.pi, math.pi)
        cr.close_path()

    def _draw_wheel_details(self, cr) -> None:
        # Wheel ridges
        cr.set_source_rgba(0, 0, 0, 0.30)
        for i in range(5):
            y = 48 + i * 7
            cr.rectangle(91, y, 18, 1.5)
            cr.fill()

        # Copper accent dot
        cr.set_source_rgba(0.83, 0.65, 0.46, 0.40)
        cr.arc(100, 158, 3, 0, 2 * math.pi)
        cr.fill()


# Expose button labels for external use (e.g., the remap dialog)
BUTTON_LABELS = {cid: name for cid, name, _ in _BUTTON_RECTS}
