"""Pre-render crisp 2x HiDPI 60 FPS transparent PNG frames from the REAL
Wayland Actions Ring Cairo renderer (`src/mx4/agent/overlay.py`) for V2 Scene 4 (Beats 44..50 @ 128 BPM).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import cairo
from mx4.agent.overlay import render_ring_frame
from mx4.agent.profiles import clone_preset_slices
from mx4.agent.ring_themes import get_ring_size, get_ring_theme

BPM = 128.0
FPS = 60.0
OUT_DIR = Path(__file__).resolve().parent / "tmp" / "cairo_ring"


def beat_to_frame(beat: float) -> int:
    return round((beat * 60.0 / BPM) * FPS)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Remove any old v1 frames cleanly
    for old in OUT_DIR.glob("frame_*.png"):
        old.unlink()

    f_start = beat_to_frame(44.0)
    f_end = beat_to_frame(50.0)
    f_confirm = beat_to_frame(49.0)

    size_spec = get_ring_size("standard")
    scale_2x = 2.0
    canvas_px = int(size_spec.canvas * scale_2x)
    slices = clone_preset_slices("hyprland")
    theme_cyber = get_ring_theme("cyber")

    dt = 1.0 / FPS
    slice_lifts = [0.0] * 8
    ptr_x, ptr_y = 0.0, 0.0
    ambient_phase = 0.0
    seg_angle = math.tau / 8.0

    # Snappy 6-beat (2.81s) choreography:
    # 44.0 - 44.7: fast spring overshoot bloom open + deadzone fill
    # 44.7 - 46.2: flick -> Slice 1 (Next WS)
    # 46.2 - 47.6: sweep -> Slice 3 (Float)
    # 47.6 - 49.0: sweep -> Slice 5 (Screenshot)
    # 49.0 - 50.0: bright expanding Confirm-Burst shockwave + clean exit!
    total = f_end - f_start + 1
    for i, frame in enumerate(range(f_start, f_end + 1)):
        beat = (frame / FPS) * (BPM / 60.0)
        elapsed = (frame - f_start) * dt
        ambient_phase += dt * 1.4

        open_t = min(1.0, elapsed / 0.16)
        closing = frame >= f_confirm
        close_t = min(1.0, (frame - f_confirm) * dt / 0.44) if closing else 0.0

        if beat < 44.65:
            p = max(0.0, (beat - 44.1) / 0.55)
            tx = math.cos(-math.pi * 0.5 + seg_angle) * (36.0 * p)
            ty = math.sin(-math.pi * 0.5 + seg_angle) * (36.0 * p)
            selected = None
        elif beat < 46.2:
            ang = -math.pi * 0.5 + 1 * seg_angle
            tx, ty = math.cos(ang) * 68.0, math.sin(ang) * 68.0
            selected = 1
        elif beat < 47.6:
            ang = -math.pi * 0.5 + 3 * seg_angle
            tx, ty = math.cos(ang) * 68.0, math.sin(ang) * 68.0
            selected = 3
        else:
            ang = -math.pi * 0.5 + 5 * seg_angle
            tx, ty = math.cos(ang) * 70.0, math.sin(ang) * 70.0
            selected = 5

        ptr_k = 1.0 - math.exp(-22.0 * dt)
        ptr_x += (tx - ptr_x) * ptr_k
        ptr_y += (ty - ptr_y) * ptr_k

        lift_k = 1.0 - math.exp(-24.0 * dt)
        for s_idx in range(8):
            goal = 1.0 if s_idx == selected else 0.0
            slice_lifts[s_idx] += (goal - slice_lifts[s_idx]) * lift_k

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, canvas_px, canvas_px)
        cr = cairo.Context(surface)
        cr.scale(scale_2x, scale_2x)

        render_ring_frame(
            cr,
            size_spec.canvas,
            size_spec.canvas,
            slices=slices,
            profile_name="Hyprland WM · Darkfield Cyber",
            theme=theme_cyber,
            size_spec=size_spec,
            selected=selected,
            slice_lifts=slice_lifts,
            open_t=open_t,
            close_t=close_t,
            confirm_idx=5 if closing else None,
            ptr_dx=ptr_x,
            ptr_dy=ptr_y,
            cancel_radius=40.0,
            ambient_phase=ambient_phase,
            show_hints=True,
        )

        out_path = OUT_DIR / f"frame_{i:04d}.png"
        surface.write_to_png(str(out_path))

    print(f"Rendered {total} V2 2x HiDPI Cairo Wayland Actions Ring frames ({canvas_px}x{canvas_px})")


if __name__ == "__main__":
    main()
