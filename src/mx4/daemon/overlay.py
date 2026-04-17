"""GTK4 Actions Ring overlay window.

Lives in the daemon process because it's driven by gesture events; the
settings GUI doesn't need GTK in this process. The overlay is a
layer-shell surface at the OVERLAY layer with KeyboardMode.NONE so it
can't steal focus.
"""

from __future__ import annotations

import json
import logging
import math
import subprocess
from dataclasses import dataclass
from typing import Optional

import cairo  # type: ignore[import-untyped]
import gi
gi.require_version("Gtk", "4.0")
try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell
    _HAVE_LAYER_SHELL = True
except (ValueError, ImportError):
    Gtk4LayerShell = None  # type: ignore[assignment]
    _HAVE_LAYER_SHELL = False

from gi.repository import GLib, Gtk, Gdk

from ..config import RingProfile

logger = logging.getLogger(__name__)


WINDOW_SIZE = 420
OUTER_RADIUS = 170
INNER_RADIUS = 54
SEGMENT_COUNT = 8

# Nord-compatible accent palette — matches the rest of Tim's desktop.
_ACCENT = (0.51, 0.63, 0.76)       # #81A1C1
_ACCENT_BRIGHT = (0.53, 0.75, 0.82) # #88C0D0
_BG_DEEP = (0.055, 0.055, 0.070, 0.95)
_BG_RING = (0.09, 0.09, 0.11, 0.92)
_SEGMENT_BG = (0.14, 0.14, 0.17, 0.92)
_SEGMENT_HOVER = (0.19, 0.22, 0.27, 0.96)
_SEGMENT_ACTIVE = (0.51, 0.63, 0.76, 0.22)
_BORDER = (1, 1, 1, 0.07)
_TEXT = (0.94, 0.94, 0.94)
_TEXT_DIM = (0.55, 0.58, 0.63)
_CANCEL = (0.75, 0.38, 0.42)


@dataclass
class Segment:
    label: str
    icon: str
    action_type: str
    action_data: str


def _profile_to_segments(profile: RingProfile) -> list[Segment]:
    segs = []
    for s in profile.slices[:SEGMENT_COUNT]:
        segs.append(Segment(s.label, s.icon, s.action_type, s.action_data))
    while len(segs) < SEGMENT_COUNT:
        segs.append(Segment("", "", "disabled", ""))
    return segs


def _cursor_position() -> tuple[int, int]:
    """Return the live cursor position in global layout coordinates."""
    # Hyprland first — most accurate on Wayland
    try:
        r = subprocess.run(
            ["hyprctl", "cursorpos", "-j"],
            capture_output=True, text=True, timeout=0.2,
        )
        if r.returncode == 0:
            d = json.loads(r.stdout)
            return int(d["x"]), int(d["y"])
    except Exception:
        pass
    # xdotool fallback (XWayland / X11)
    try:
        r = subprocess.run(
            ["xdotool", "getmouselocation", "--shell"],
            capture_output=True, text=True, timeout=0.2,
        )
        if r.returncode == 0:
            x = y = 0
            for line in r.stdout.splitlines():
                if line.startswith("X="):
                    x = int(line.split("=", 1)[1])
                elif line.startswith("Y="):
                    y = int(line.split("=", 1)[1])
            return x, y
    except Exception:
        pass
    return 960, 540


def _monitor_for(x: int, y: int) -> Optional[Gdk.Monitor]:
    display = Gdk.Display.get_default()
    if not display:
        return None
    monitors = display.get_monitors()
    n = monitors.get_n_items() if monitors else 0
    first = monitors.get_item(0) if n > 0 else None
    for i in range(n):
        m = monitors.get_item(i)
        g = m.get_geometry()
        if g.x <= x < g.x + g.width and g.y <= y < g.y + g.height:
            return m
    return first


class ActionsRingOverlay(Gtk.Window):
    """Layer-shell overlay window rendering the radial menu in Cairo."""

    def __init__(self):
        super().__init__()
        self._segments: list[Segment] = [Segment("", "", "disabled", "")] * SEGMENT_COUNT
        self._selected_index: Optional[int] = None
        self._hover_progress = 0.0  # 0..1 for animated boundary ring
        self._app_name: str = ""

        self.set_decorated(False)
        self.set_resizable(False)
        self.set_default_size(WINDOW_SIZE, WINDOW_SIZE)
        self.set_focusable(False)
        self.set_can_focus(False)

        if _HAVE_LAYER_SHELL:
            Gtk4LayerShell.init_for_window(self)
            Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.OVERLAY)
            Gtk4LayerShell.set_keyboard_mode(self, Gtk4LayerShell.KeyboardMode.NONE)
        else:
            logger.warning("gtk4-layer-shell not available — overlay may steal focus")

        # Make the window fully transparent so only Cairo draws show
        self.add_css_class("mx4-ring-overlay")
        self._drawing = Gtk.DrawingArea()
        self._drawing.set_draw_func(self._draw)
        self._drawing.set_content_width(WINDOW_SIZE)
        self._drawing.set_content_height(WINDOW_SIZE)
        self.set_child(self._drawing)

        # Add an inline stylesheet so we don't depend on external CSS
        css = Gtk.CssProvider()
        css.load_from_string(
            ".mx4-ring-overlay, .mx4-ring-overlay > * { background-color: transparent; }"
        )
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    # ─── public API (called from gesture engine handlers) ───────────────

    def load_profile(self, profile: RingProfile) -> None:
        self._segments = _profile_to_segments(profile)
        self._app_name = profile.app_name
        self._drawing.queue_draw()

    def show_at_cursor(self) -> None:
        self._selected_index = None
        cx, cy = _cursor_position()
        self._position(cx, cy)
        self.present()
        self._drawing.queue_draw()

    def update_selection(self, segment_index: Optional[int]) -> None:
        if segment_index != self._selected_index:
            self._selected_index = segment_index
            self._drawing.queue_draw()

    def hide_and_pick(self) -> Optional[Segment]:
        """Hide the overlay and return the currently-selected segment
        (or None if the user was in the cancel zone)."""
        selected = None
        if self._selected_index is not None:
            seg = self._segments[self._selected_index]
            if seg.action_data and seg.action_type != "disabled":
                selected = seg
        self.set_visible(False)
        return selected

    # ─── layer-shell positioning ────────────────────────────────────────

    def _position(self, global_x: int, global_y: int) -> None:
        if not _HAVE_LAYER_SHELL:
            return
        monitor = _monitor_for(global_x, global_y)
        if not monitor:
            return
        geom = monitor.get_geometry()
        half = WINDOW_SIZE // 2
        local_x = global_x - geom.x - half
        local_y = global_y - geom.y - half
        local_x = max(0, min(geom.width - WINDOW_SIZE, local_x))
        local_y = max(0, min(geom.height - WINDOW_SIZE, local_y))
        Gtk4LayerShell.set_monitor(self, monitor)
        for edge in (Gtk4LayerShell.Edge.BOTTOM, Gtk4LayerShell.Edge.RIGHT):
            Gtk4LayerShell.set_anchor(self, edge, False)
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.TOP, True)
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.LEFT, True)
        Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.TOP, int(local_y))
        Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.LEFT, int(local_x))

    # ─── Cairo paint ────────────────────────────────────────────────────

    def _draw(self, _area, cr: cairo.Context, width: int, height: int) -> None:
        cx = width / 2
        cy = height / 2

        # Outer drop shadow — soft radial gradient
        shadow = cairo.RadialGradient(cx, cy, 0, cx, cy, OUTER_RADIUS + 40)
        shadow.add_color_stop_rgba(0.0, 0, 0, 0, 0.45)
        shadow.add_color_stop_rgba(0.75, 0, 0, 0, 0.22)
        shadow.add_color_stop_rgba(1.0, 0, 0, 0, 0.0)
        cr.set_source(shadow)
        cr.arc(cx, cy, OUTER_RADIUS + 36, 0, 2 * math.pi)
        cr.fill()

        # Ring background disk (between INNER and OUTER)
        cr.set_source_rgba(*_BG_RING)
        cr.arc(cx, cy, OUTER_RADIUS + 8, 0, 2 * math.pi)
        cr.fill()

        # Segments
        for i in range(SEGMENT_COUNT):
            self._draw_segment(cr, cx, cy, i)

        # Center cancel zone
        self._draw_center(cr, cx, cy)

        # Selected label below the ring
        self._draw_title(cr, cx, cy + OUTER_RADIUS + 38)

    def _draw_segment(self, cr, cx, cy, i):
        half = math.pi / SEGMENT_COUNT
        mid = -math.pi / 2 + (i * 2 * math.pi / SEGMENT_COUNT)
        start = mid - half
        end = mid + half
        selected = (i == self._selected_index)
        seg = self._segments[i]
        disabled = not seg.label or seg.action_type == "disabled"

        # Fill
        if selected:
            cr.set_source_rgba(*_SEGMENT_ACTIVE)
        elif disabled:
            cr.set_source_rgba(*_SEGMENT_BG[:3], _SEGMENT_BG[3] * 0.5)
        else:
            cr.set_source_rgba(*_SEGMENT_BG)
        cr.new_path()
        cr.arc(cx, cy, OUTER_RADIUS, start, end)
        cr.arc_negative(cx, cy, INNER_RADIUS, end, start)
        cr.close_path()
        cr.fill()

        # Border
        if selected:
            cr.set_source_rgba(*_ACCENT, 1.0)
            cr.set_line_width(2.5)
        else:
            cr.set_source_rgba(*_BORDER)
            cr.set_line_width(1)
        cr.new_path()
        cr.arc(cx, cy, OUTER_RADIUS, start, end)
        cr.arc_negative(cx, cy, INNER_RADIUS, end, start)
        cr.close_path()
        cr.stroke()

        # Label
        if not seg.label:
            return
        label_r = (INNER_RADIUS + OUTER_RADIUS) / 2
        lx = cx + math.cos(mid) * label_r
        ly = cy + math.sin(mid) * label_r

        # Dot marker above the label
        dot_color = _ACCENT if selected else _TEXT if not disabled else _TEXT_DIM
        cr.set_source_rgb(*dot_color)
        cr.arc(lx, ly - 12, 3.2, 0, 2 * math.pi)
        cr.fill()

        # Label text
        cr.select_font_face(
            "Inter",
            cairo.FONT_SLANT_NORMAL,
            cairo.FONT_WEIGHT_BOLD if selected else cairo.FONT_WEIGHT_NORMAL,
        )
        cr.set_font_size(12)
        cr.set_source_rgb(*dot_color)
        ext = cr.text_extents(seg.label)
        cr.move_to(lx - ext.width / 2, ly + 10)
        cr.show_text(seg.label)

    def _draw_center(self, cr, cx, cy):
        in_cancel = self._selected_index is None
        radius = INNER_RADIUS - 6

        if in_cancel:
            # Soft red glow
            grad = cairo.RadialGradient(cx, cy, 0, cx, cy, radius + 4)
            grad.add_color_stop_rgba(0.0, _CANCEL[0], _CANCEL[1], _CANCEL[2], 0.22)
            grad.add_color_stop_rgba(1.0, _CANCEL[0], _CANCEL[1], _CANCEL[2], 0.0)
            cr.set_source(grad)
            cr.arc(cx, cy, radius + 4, 0, 2 * math.pi)
            cr.fill()

        cr.set_source_rgba(*_BG_DEEP)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.fill()

        if in_cancel:
            # X icon
            cr.set_source_rgb(*_CANCEL)
            cr.set_line_width(3.2)
            cr.set_line_cap(cairo.LineCap.ROUND)
            s = 14
            cr.move_to(cx - s, cy - s); cr.line_to(cx + s, cy + s); cr.stroke()
            cr.move_to(cx + s, cy - s); cr.line_to(cx - s, cy + s); cr.stroke()
        else:
            # Inner dot
            cr.set_source_rgba(*_ACCENT, 0.85)
            cr.arc(cx, cy, 6, 0, 2 * math.pi)
            cr.fill()

    def _draw_title(self, cr, cx, y):
        if self._selected_index is not None:
            seg = self._segments[self._selected_index]
            label = seg.label or ""
            cr.set_source_rgb(*_ACCENT_BRIGHT)
        else:
            label = "Cancel"
            cr.set_source_rgb(*_CANCEL)

        if self._app_name:
            label = f"{label}   ·   {self._app_name}"
        cr.select_font_face("Inter", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(13)
        ext = cr.text_extents(label)
        cr.move_to(cx - ext.width / 2, y)
        cr.show_text(label)
