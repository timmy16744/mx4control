"""
Actions Ring Overlay Window

A transparent overlay that displays the radial menu when the gesture
button is held, allowing quick action selection.
"""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

# Try to load gtk4-layer-shell for proper Wayland overlay support
try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell
    LAYER_SHELL_AVAILABLE = True
except (ValueError, ImportError):
    LAYER_SHELL_AVAILABLE = False
    Gtk4LayerShell = None

from gi.repository import Gtk, Gdk, GLib
import cairo
import math
import logging
import subprocess
from typing import Optional, Callable, Tuple
from dataclasses import dataclass

from .gesture_detector import GestureDirection

logger = logging.getLogger(__name__)

# Log layer shell availability
if LAYER_SHELL_AVAILABLE:
    logger.info("gtk4-layer-shell available - using proper Wayland overlay")
else:
    logger.warning("gtk4-layer-shell not available - overlay may affect window focus")


def get_mouse_position() -> Tuple[int, int]:
    """Return the cursor position in global layout coordinates.

    Tries Hyprland's IPC first (reliable on Wayland), then xdotool (X11 /
    XWayland). Falls back to primary-monitor center.
    """
    # Hyprland IPC
    try:
        result = subprocess.run(
            ["hyprctl", "cursorpos", "-j"],
            capture_output=True, text=True, timeout=0.3,
        )
        if result.returncode == 0:
            import json as _json
            data = _json.loads(result.stdout)
            return int(data["x"]), int(data["y"])
    except Exception as e:
        logger.debug(f"hyprctl cursorpos failed: {e}")

    # xdotool fallback (X11)
    try:
        result = subprocess.run(
            ["xdotool", "getmouselocation", "--shell"],
            capture_output=True, text=True, timeout=0.3,
        )
        if result.returncode == 0:
            x, y = 0, 0
            for line in result.stdout.strip().split("\n"):
                if line.startswith("X="):
                    x = int(line.split("=")[1])
                elif line.startswith("Y="):
                    y = int(line.split("=")[1])
            return x, y
    except Exception as e:
        logger.debug(f"xdotool failed: {e}")

    # Fallback to screen center
    display = Gdk.Display.get_default()
    if display:
        monitors = display.get_monitors()
        if monitors.get_n_items() > 0:
            monitor = monitors.get_item(0)
            geometry = monitor.get_geometry()
            return geometry.x + geometry.width // 2, geometry.y + geometry.height // 2

    return 960, 540


def _find_monitor_for_point(x: int, y: int):
    """Return the GdkMonitor that contains the point (x, y), or the primary monitor."""
    display = Gdk.Display.get_default()
    if not display:
        return None
    monitors = display.get_monitors()
    n = monitors.get_n_items() if monitors else 0
    primary = monitors.get_item(0) if n > 0 else None
    for i in range(n):
        m = monitors.get_item(i)
        g = m.get_geometry()
        if g.x <= x < g.x + g.width and g.y <= y < g.y + g.height:
            return m
    return primary


@dataclass
class RingSegment:
    """Configuration for a single ring segment"""
    label: str
    icon: str
    action_type: str  # keystroke, command, application
    action_data: str


class ActionsRingOverlay(Gtk.Window):
    """
    Transparent overlay window showing the Actions Ring radial menu.

    Displays 8 configurable segments around a center point.
    Highlights the segment corresponding to the current gesture direction.
    """

    WINDOW_SIZE = 450
    OUTER_RADIUS = 180
    INNER_RADIUS = 55
    SEGMENT_COUNT = 8

    def __init__(self):
        super().__init__()

        self.selected_index: Optional[int] = None
        self.on_action_selected: Optional[Callable[[int, RingSegment], None]] = None
        # Fires on every selection change (including None<->segment) so the
        # gesture service can play a haptic tick at each boundary crossing.
        self.on_segment_change: Optional[Callable[[Optional[int]], None]] = None

        # Default segments - arranged clockwise from top
        self.segments: list[RingSegment] = [
            RingSegment("Undo", "edit-undo", "keystroke", "ctrl+z"),           # Top (up gesture)
            RingSegment("Paste", "edit-paste", "keystroke", "ctrl+v"),         # Top-right
            RingSegment("Copy", "edit-copy", "keystroke", "ctrl+c"),           # Right
            RingSegment("Cut", "edit-cut", "keystroke", "ctrl+x"),             # Bottom-right
            RingSegment("Redo", "edit-redo", "keystroke", "ctrl+shift+z"),     # Bottom (down gesture)
            RingSegment("Screenshot", "camera-photo", "command", "gnome-screenshot -a"),  # Bottom-left
            RingSegment("Terminal", "utilities-terminal", "command", "kitty"),  # Left
            RingSegment("Files", "system-file-manager", "command", "nautilus"), # Top-left
        ]

        self._setup_window()
        self._setup_drawing()

    def _setup_window(self):
        """Configure window properties for centered overlay"""
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_default_size(self.WINDOW_SIZE, self.WINDOW_SIZE)

        # CRITICAL: Don't steal focus from the active window
        self.set_focusable(False)
        self.set_can_focus(False)
        self.set_deletable(False)

        # Use gtk4-layer-shell for proper Wayland overlay (doesn't affect focus)
        if LAYER_SHELL_AVAILABLE:
            try:
                Gtk4LayerShell.init_for_window(self)
                Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.OVERLAY)
                Gtk4LayerShell.set_keyboard_mode(self, Gtk4LayerShell.KeyboardMode.NONE)
                # Don't set anchors - let it float in center
                Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.TOP, False)
                Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.BOTTOM, False)
                Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.LEFT, False)
                Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.RIGHT, False)
                print(">>> Layer shell initialized - overlay won't affect focus")
            except Exception as e:
                print(f">>> Layer shell init failed: {e}")

        # Enable transparency (CSS for this class is defined in the app's main stylesheet)
        self.add_css_class("actions-ring-overlay")

    def _setup_drawing(self):
        """Set up the drawing area"""
        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.set_draw_func(self._draw)
        self.drawing_area.set_content_width(self.WINDOW_SIZE)
        self.drawing_area.set_content_height(self.WINDOW_SIZE)
        self.set_child(self.drawing_area)

    def _draw(self, area, cr: cairo.Context, width: int, height: int):
        """Draw the radial menu centered in the window"""
        cx = width / 2
        cy = height / 2

        # Colors - warm copper theme
        bg_color = (0.08, 0.08, 0.10, 0.95)
        segment_color = (0.15, 0.15, 0.17, 0.95)
        selected_color = (0.83, 0.65, 0.46, 0.35)
        border_color = (1, 1, 1, 0.08)
        accent_color = (0.83, 0.65, 0.46)
        text_color = (0.94, 0.93, 0.91)
        dim_text = (0.6, 0.6, 0.62)

        # Draw outer glow/shadow
        cr.set_source_rgba(0, 0, 0, 0.3)
        cr.arc(cx, cy, self.OUTER_RADIUS + 25, 0, 2 * math.pi)
        cr.fill()

        # Draw semi-transparent background circle
        cr.set_source_rgba(*bg_color)
        cr.arc(cx, cy, self.OUTER_RADIUS + 15, 0, 2 * math.pi)
        cr.fill()

        # Draw segments
        for i in range(self.SEGMENT_COUNT):
            # Segment angles - start from top (12 o'clock)
            start_angle = (i * 2 * math.pi / self.SEGMENT_COUNT) - math.pi / 2 - math.pi / self.SEGMENT_COUNT
            end_angle = ((i + 1) * 2 * math.pi / self.SEGMENT_COUNT) - math.pi / 2 - math.pi / self.SEGMENT_COUNT

            # Determine segment color based on selection
            if i == self.selected_index:
                cr.set_source_rgba(*selected_color)
            else:
                cr.set_source_rgba(*segment_color)

            # Draw segment arc
            cr.new_path()
            cr.arc(cx, cy, self.OUTER_RADIUS, start_angle, end_angle)
            cr.arc_negative(cx, cy, self.INNER_RADIUS, end_angle, start_angle)
            cr.close_path()
            cr.fill()

            # Draw segment border
            if i == self.selected_index:
                cr.set_source_rgba(*accent_color, 1)
                cr.set_line_width(3)
            else:
                cr.set_source_rgba(*border_color)
                cr.set_line_width(1)

            cr.new_path()
            cr.arc(cx, cy, self.OUTER_RADIUS, start_angle, end_angle)
            cr.arc_negative(cx, cy, self.INNER_RADIUS, end_angle, start_angle)
            cr.close_path()
            cr.stroke()

            # Draw segment label
            mid_angle = (start_angle + end_angle) / 2
            mid_radius = (self.INNER_RADIUS + self.OUTER_RADIUS) / 2

            label_x = cx + math.cos(mid_angle) * mid_radius
            label_y = cy + math.sin(mid_angle) * mid_radius

            if i < len(self.segments):
                segment = self.segments[i]

                # Icon circle
                icon_y = label_y - 12

                if i == self.selected_index:
                    cr.set_source_rgb(*accent_color)
                else:
                    cr.set_source_rgb(*text_color)

                cr.arc(label_x, icon_y, 16, 0, 2 * math.pi)
                cr.set_line_width(2)
                cr.stroke()

                # Icon dot
                cr.arc(label_x, icon_y, 4, 0, 2 * math.pi)
                cr.fill()

                # Label text
                cr.select_font_face("sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
                cr.set_font_size(13)

                label = segment.label
                extents = cr.text_extents(label)
                cr.move_to(label_x - extents.width / 2, label_y + 22)
                cr.show_text(label)

        # Draw center cancel zone
        cancel_color = (0.8, 0.2, 0.2)  # Red for cancel

        # Center circle background
        if self.selected_index is None:
            # Highlighted when in cancel zone
            cr.set_source_rgba(*cancel_color, 0.3)
        else:
            cr.set_source_rgba(0.1, 0.1, 0.12, 1)
        cr.arc(cx, cy, self.INNER_RADIUS - 5, 0, 2 * math.pi)
        cr.fill()

        # Center ring
        if self.selected_index is None:
            cr.set_source_rgba(*cancel_color, 0.8)
        else:
            cr.set_source_rgba(*accent_color, 0.4)
        cr.set_line_width(3)
        cr.arc(cx, cy, self.INNER_RADIUS - 5, 0, 2 * math.pi)
        cr.stroke()

        # Cancel X icon in center
        cr.set_line_width(3)
        if self.selected_index is None:
            cr.set_source_rgb(*cancel_color)
            # Draw X
            size = 15
            cr.move_to(cx - size, cy - size)
            cr.line_to(cx + size, cy + size)
            cr.stroke()
            cr.move_to(cx + size, cy - size)
            cr.line_to(cx - size, cy + size)
            cr.stroke()
        else:
            # Small dot when not in cancel zone
            cr.set_source_rgba(*accent_color, 0.5)
            cr.arc(cx, cy, 8, 0, 2 * math.pi)
            cr.fill()

        # Label below ring
        cr.set_source_rgb(*text_color)
        cr.select_font_face("sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(13)

        if self.selected_index is None:
            label = "Cancel"
            cr.set_source_rgb(*cancel_color)
        elif self.selected_index < len(self.segments):
            label = self.segments[self.selected_index].label
        else:
            label = ""

        if label:
            extents = cr.text_extents(label)
            cr.move_to(cx - extents.width / 2, cy + self.INNER_RADIUS + 35)
            cr.show_text(label)

    def show_overlay(self):
        """Show the overlay positioned at the current cursor location.

        On Hyprland (Wayland) we ask the compositor for the live cursor
        coordinates and use layer-shell margins to anchor the ring at
        that point, centred on the cursor. Falls back to a centred
        overlay on the primary monitor when the cursor position can't
        be determined.
        """
        self.selected_index = None

        cursor_x, cursor_y = get_mouse_position()
        self._position_at(cursor_x, cursor_y)

        self.present()
        self.drawing_area.queue_draw()

    def _position_at(self, global_x: int, global_y: int):
        """Anchor the overlay at the given global (layout) coordinates.

        Uses layer-shell edge anchors + margins scoped to whatever
        monitor contains the cursor. Clamps so the ring stays fully
        on-screen even near edges.
        """
        if not LAYER_SHELL_AVAILABLE:
            return

        monitor = _find_monitor_for_point(global_x, global_y)
        if monitor is None:
            return

        geom = monitor.get_geometry()
        local_x = global_x - geom.x
        local_y = global_y - geom.y

        size = self.WINDOW_SIZE
        half = size // 2

        # Top-left corner of the overlay within the monitor, clamped so
        # the full ring is visible even if the cursor is near a corner.
        margin_left = max(0, min(geom.width - size, local_x - half))
        margin_top = max(0, min(geom.height - size, local_y - half))

        try:
            Gtk4LayerShell.set_monitor(self, monitor)
            # Anchor to top-left so margins behave as offsets from (0, 0)
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.TOP, True)
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.LEFT, True)
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.BOTTOM, False)
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.RIGHT, False)
            Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.TOP, margin_top)
            Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.LEFT, margin_left)
        except Exception as e:
            logger.debug(f"layer-shell positioning failed: {e}")

    def hide_overlay(self) -> Optional[RingSegment]:
        """Hide the overlay and return the selected segment"""
        selected = None
        if self.selected_index is not None and self.selected_index < len(self.segments):
            selected = self.segments[self.selected_index]

        self.set_visible(False)
        return selected

    def update_direction(self, direction: GestureDirection):
        """Update the highlighted segment based on gesture direction"""
        # Map direction to segment index
        # Segments are arranged clockwise from top:
        # 0=top, 1=top-right, 2=right, 3=bottom-right,
        # 4=bottom, 5=bottom-left, 6=left, 7=top-left

        direction_to_index = {
            GestureDirection.UP: 0,
            GestureDirection.RIGHT: 2,
            GestureDirection.DOWN: 4,
            GestureDirection.LEFT: 6,
            GestureDirection.CENTER: None,
            GestureDirection.NONE: None,
        }

        new_index = direction_to_index.get(direction)

        if new_index != self.selected_index:
            self.selected_index = new_index
            self.drawing_area.queue_draw()

    def update_from_position(self, dx: int, dy: int):
        """Update selection based on relative mouse movement - very responsive.

        Fires ``on_segment_change`` whenever the highlighted segment changes
        so callers can play a haptic tick at each boundary crossing.
        """
        distance = math.sqrt(dx*dx + dy*dy)

        # Center deadzone = cancel zone (about 40 pixels)
        if distance < 40:
            new_index: Optional[int] = None
        else:
            angle = math.atan2(dy, dx)
            # Rotate so segment 0 is at the top (up direction)
            angle = angle + math.pi / 2
            if angle < 0:
                angle += 2 * math.pi
            segment_angle = 2 * math.pi / self.SEGMENT_COUNT
            new_index = int((angle + segment_angle / 2) / segment_angle) % self.SEGMENT_COUNT

        if new_index != self.selected_index:
            self.selected_index = new_index
            self.drawing_area.queue_draw()
            if self.on_segment_change:
                try:
                    self.on_segment_change(new_index)
                except Exception as e:
                    logger.debug(f"on_segment_change handler raised: {e}")

    def set_segments(self, segments: list[RingSegment]):
        """Update the segment configuration"""
        self.segments = segments
        self.drawing_area.queue_draw()

    def load_from_config(self, config):
        """Load segments from application config"""
        if hasattr(config, 'actions_ring') and config.actions_ring:
            ring_config = config.actions_ring
            if hasattr(ring_config, 'slices') and ring_config.slices:
                self.segments = []
                for slice_config in ring_config.slices:
                    self.segments.append(RingSegment(
                        label=slice_config.label,
                        icon=slice_config.icon,
                        action_type=slice_config.action_type,
                        action_data=slice_config.action_data,
                    ))
                # Pad to 8 segments if needed
                while len(self.segments) < 8:
                    self.segments.append(RingSegment("", "", "disabled", ""))
                self.drawing_area.queue_draw()
