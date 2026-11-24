/**
 * MX4 Studio Launch Video V2 — High-Octane 30-Second Director's Cut
 * Exact Lock: 128 BPM · 60 fps · 30.000 s · 64 Beats · 16 Bars · 1,800 Frames!
 */

export const BPM = 128;
export const FPS = 60;
export const DURATION_SEC = 30.0;
export const TOTAL_FRAMES = 1800; // 64 beats at 128 BPM = exact 30.000 s!
export const TOTAL_BEATS = 64;

export function beatToSec(beat) {
  return (beat * 60.0) / BPM;
}

export function beatToFrame(beat) {
  return Math.round(beatToSec(beat) * FPS);
}

export function frameToSec(frame) {
  return frame / FPS;
}

export function frameToBeat(frame) {
  return (frame / FPS) * (BPM / 60.0);
}

// ─────────────────────────── Physics & Easing Curves ─────────────────────

export function clamp(v, lo = 0, hi = 1) {
  return Math.max(lo, Math.min(hi, v));
}

export function lerp(a, b, t) {
  return a + (b - a) * t;
}

export function cubicBezier(x1, y1, x2, y2, t) {
  const u = clamp(t, 0, 1);
  if (u === 0 || u === 1) return u;
  const ax = 3 * x1 - 3 * x2 + 1;
  const bx = 3 * x2 - 6 * x1;
  const cx = 3 * x1;
  const ay = 3 * y1 - 3 * y2 + 1;
  const by = 3 * y2 - 6 * y1;
  const cy = 3 * y1;

  let s = u;
  for (let i = 0; i < 6; i++) {
    const x = ((ax * s + bx) * s + cx) * s - u;
    const dx = (3 * ax * s + 2 * bx) * s + cx;
    if (Math.abs(x) < 1e-6 || Math.abs(dx) < 1e-6) break;
    s = clamp(s - x / dx, 0, 1);
  }
  return ((ay * s + by) * s + cy) * s;
}

export const easeOutExpo = (t) => (t <= 0 ? 0 : t >= 1 ? 1 : 1 - Math.pow(2, -10 * t));
export const easeInOutQuart = (t) => cubicBezier(0.76, 0, 0.24, 1, t);
export const easeOutQuint = (t) => cubicBezier(0.22, 1, 0.36, 1, t);
export const easeSnappy = (t) => cubicBezier(0.16, 1, 0.3, 1, t);
export const easeOvershoot = (t) => cubicBezier(0.22, 1.32, 0.36, 1.0, t);

export function spring01(elapsedSec, { stiffness = 280, damping = 21, mass = 1.0 } = {}) {
  if (elapsedSec <= 0) return 0;
  const w0 = Math.sqrt(stiffness / mass);
  const zeta = damping / (2 * Math.sqrt(stiffness * mass));
  if (zeta < 1) {
    const wd = w0 * Math.sqrt(1 - zeta * zeta);
    const env = Math.exp(-zeta * w0 * elapsedSec);
    return 1 - env * (Math.cos(wd * elapsedSec) + (zeta * w0 / wd) * Math.sin(wd * elapsedSec));
  }
  const env = Math.exp(-w0 * elapsedSec);
  return 1 - env * (1 + w0 * elapsedSec);
}

// ─────────────────────────── V2 30s Scene Boundaries (128 BPM) ───────────

export const SCENES = [
  { id: 'cold_open', name: 'Cold Open Impact',       startBeat: 0,  endBeat: 8  },
  { id: 'darkfield', name: 'Darkfield 8000 DPI',     startBeat: 8,  endBeat: 18 },
  { id: 'magspeed',  name: 'MagSpeed 144Hz',         startBeat: 18, endBeat: 28 },
  { id: 'haptics',   name: 'LRA Haptics Cutaway',    startBeat: 28, endBeat: 38 },
  { id: 'ring',      name: 'Actions Ring + Wayland', startBeat: 38, endBeat: 50 },
  { id: 'montage',   name: '1-Beat Climax Montage',  startBeat: 50, endBeat: 56 },
  { id: 'finale',    name: 'Hero Drop & Lockup',     startBeat: 56, endBeat: 64 },
].map((s) => ({
  ...s,
  startSec: beatToSec(s.startBeat),
  endSec: beatToSec(s.endBeat),
  startFrame: beatToFrame(s.startBeat),
  endFrame: beatToFrame(s.endBeat),
}));

// ─────────────────────────── Frame-Synced Audio & Impact Cues ────────────

export const AUDIO_CUES = [
  // Cold Open (Beats 0..8)
  { beat: 0.0,  type: 'laser_ignite',    gain: 1.00 },
  { beat: 2.0,  type: 'title_slam',      gain: 0.88 },
  { beat: 4.0,  type: 'title_slam_hi',   gain: 0.92 },
  { beat: 6.0,  type: 'riser_impact',    gain: 0.90 },
  { beat: 8.0,  type: 'whip_drop',       gain: 0.96 },

  // Darkfield 8000 DPI (Beats 8..18)
  { beat: 10.0, type: 'vernier_tick',    gain: 0.80, pitch: 1.00 },
  { beat: 12.0, type: 'vernier_tick',    gain: 0.86, pitch: 1.22 },
  { beat: 14.0, type: 'vernier_tick',    gain: 0.94, pitch: 1.48 },
  { beat: 15.0, type: 'mouse_click',     gain: 0.82 },
  { beat: 16.0, type: 'riser_short',     gain: 0.84 },
  { beat: 16.5, type: 'mouse_click',     gain: 0.78 },

  // MagSpeed 144Hz (Beats 18..28)
  { beat: 18.0, type: 'clutch_whip',     gain: 0.96 },
  { beat: 20.0, type: 'flywheel_spin',   gain: 0.88 },
  { beat: 23.0, type: 'ui_chime',        gain: 0.74, note: 1 },
  { beat: 25.0, type: 'ui_chime',        gain: 0.78, note: 3 },
  { beat: 26.0, type: 'riser_impact',    gain: 0.90 },

  // LRA Haptics Cutaway (Beats 28..38)
  { beat: 28.0, type: 'glass_drop',      gain: 0.98 },
  { beat: 30.0, type: 'haptic_detent',   gain: 0.96 },
  { beat: 32.0, type: 'haptic_thump',    gain: 1.00 },
  { beat: 34.0, type: 'haptic_firework', gain: 0.98 },
  { beat: 36.0, type: 'riser_short',     gain: 0.88 },

  // Actions Ring: 1-Beat Theme Morphs + Real 60fps Wayland Cairo (Beats 38..50)
  { beat: 38.0, type: 'holo_bloom',      gain: 0.95 },
  { beat: 40.0, type: 'ui_chime',        gain: 0.82, note: 0 },
  { beat: 41.0, type: 'ui_chime',        gain: 0.84, note: 1 },
  { beat: 42.0, type: 'ui_chime',        gain: 0.86, note: 2 },
  { beat: 43.0, type: 'ui_chime',        gain: 0.90, note: 4 },
  { beat: 44.0, type: 'holo_bloom',      gain: 0.96 },
  { beat: 45.0, type: 'vernier_tick',    gain: 0.72, pitch: 1.10 },
  { beat: 46.5, type: 'vernier_tick',    gain: 0.76, pitch: 1.28 },
  { beat: 48.0, type: 'vernier_tick',    gain: 0.80, pitch: 1.48 },
  { beat: 49.0, type: 'confirm_burst',   gain: 1.00 },

  // Climax 1-Beat Montage (Beats 50..56)
  { beat: 50.0, type: 'montage_whip',    gain: 0.92 },
  { beat: 51.0, type: 'zoom_whoosh',     gain: 0.94 },
  { beat: 52.0, type: 'montage_whip',    gain: 0.92 },
  { beat: 53.0, type: 'clutch_whip',     gain: 0.92 },
  { beat: 54.0, type: 'haptic_thump',    gain: 0.98 },
  { beat: 54.5, type: 'riser_finale',    gain: 1.00 },

  // Hero Drop & Brand Lockup (Beats 56..64)
  { beat: 56.0, type: 'finale_drop',     gain: 1.00 },
  { beat: 58.0, type: 'brand_bell',      gain: 0.92 },
].map((c) => ({
  ...c,
  sec: beatToSec(c.beat),
  frame: beatToFrame(c.beat),
}));

export const CONTACT_FRAMES = [
  beatToFrame(1.0),   // Cold open laser strike on 625-cube floor
  beatToFrame(4.4),   // Cold open kinetic slam "ON LINUX."
  beatToFrame(6.8),   // Cold open "UNLOCKED." + anamorphic flare
  beatToFrame(9.5),   // Scene 1 Studio entrance
  beatToFrame(14.6),  // Scene 1 8,000 DPI slam + bright beam
  beatToFrame(19.5),  // Scene 2 MagSpeed CNC wheel macro + flux
  beatToFrame(25.5),  // Scene 2 HD Smooth S-curve Butter
  beatToFrame(30.6),  // Scene 3 LRA Haptics cutaway + copper shockwave
  beatToFrame(34.6),  // Scene 3 Firework + Thumb Pad press
  beatToFrame(40.4),  // Scene 4 Actions Ring Darkfield Cyber
  beatToFrame(43.4),  // Scene 4 Actions Ring Ultraviolet Pulse
  beatToFrame(46.8),  // Scene 4 Real 60fps Wayland Cairo Overlay
  beatToFrame(49.2),  // Scene 4 Real 60fps Wayland Cairo Confirm Burst
  beatToFrame(50.5),  // Scene 5 Montage: Hard white hover on Thumb Wheel
  beatToFrame(51.5),  // Scene 5 Montage: Direct Click-to-Zoom Macro Thumb Wheel
  beatToFrame(52.5),  // Scene 5 Montage: Hardware Lab X-Ray CAD
  beatToFrame(55.4),  // Scene 5 Montage: Ultraviolet Hologram Climax
  beatToFrame(59.8),  // Scene 6 Final Brand Lockup + MIT CTA
];
