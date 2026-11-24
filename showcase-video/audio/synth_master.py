"""MX4 Studio Launch Video V2 — 30s 128 BPM High-Impact Electronic Score + Foley.

Full production DSP engine (48 kHz stereo float64):
  * 7-voice detuned stereo supersaw chord swells with dynamic filter envelope
  * Punchy layered club/cinema kick + growling Reese sub-bass with -6 dB sidechain pump
  * Memorable syncopated FM lead hook with dotted-eighth (3/16) stereo ping-pong delay
  * Layered stereo snare/claps, 16th-note groove hats, accelerating 32nd-note climax roll
  * Frame-synced bespoke hardware/UI foley (laser, clutch whip, LRA thumps, chimes, drops)
  * Two-pass FFmpeg EBU R128 mastering to -14.0 LUFS / <= -1.0 dBTP (zero clipping)
"""

from __future__ import annotations

import json
import math
import subprocess
import wave
from pathlib import Path

import numpy as np

SR = 48000
BPM = 128.0
DURATION = 30.0
N_SAMPLES = int(SR * DURATION)
BEAT_SEC = 60.0 / BPM

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "out"
TMP_DIR = ROOT / "tmp"


def beat_to_sec(beat: float) -> float:
    return beat * BEAT_SEC


def beat_to_sample(beat: float) -> int:
    return int(round(beat_to_sec(beat) * SR))


def load_audio_cues() -> list[dict]:
    cmd = [
        "node",
        "--input-type=module",
        "-e",
        "import { AUDIO_CUES } from './timeline.mjs'; console.log(JSON.stringify(AUDIO_CUES));",
    ]
    res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, check=True)
    return json.loads(res.stdout)


def add_stereo(buf: np.ndarray, start: int, sig_l: np.ndarray, sig_r: np.ndarray | None = None, gain: float = 1.0) -> None:
    if sig_r is None:
        sig_r = sig_l
    n = len(sig_l)
    if start >= N_SAMPLES or start + n <= 0:
        return
    src_s = max(0, -start)
    dst_s = max(0, start)
    length = min(n - src_s, N_SAMPLES - dst_s)
    if length <= 0:
        return
    buf[0, dst_s:dst_s + length] += sig_l[src_s:src_s + length] * gain
    buf[1, dst_s:dst_s + length] += sig_r[src_s:src_s + length] * gain


def lp_fft(sig: np.ndarray, cutoff_hz: float, order: int = 4) -> np.ndarray:
    spec = np.fft.rfft(sig)
    freqs = np.fft.rfftfreq(len(sig), 1.0 / SR)
    resp = 1.0 / (1.0 + (freqs / max(20.0, cutoff_hz)) ** order)
    return np.fft.irfft(spec * resp, n=len(sig))


def hp_fft(sig: np.ndarray, cutoff_hz: float, order: int = 4) -> np.ndarray:
    spec = np.fft.rfft(sig)
    freqs = np.fft.rfftfreq(len(sig), 1.0 / SR)
    resp = 1.0 / (1.0 + (max(10.0, cutoff_hz) / np.maximum(freqs, 1.0)) ** order)
    return np.fft.irfft(spec * resp, n=len(sig))


def bp_fft(sig: np.ndarray, lo_hz: float, hi_hz: float) -> np.ndarray:
    spec = np.fft.rfft(sig)
    freqs = np.fft.rfftfreq(len(sig), 1.0 / SR)
    hp = 1.0 / (1.0 + (max(10.0, lo_hz) / np.maximum(freqs, 1.0)) ** 4)
    lp = 1.0 / (1.0 + (freqs / max(lo_hz + 10.0, hi_hz)) ** 4)
    return np.fft.irfft(spec * hp * lp, n=len(sig))


def ping_pong_delay(bus: np.ndarray, delay_beats: float = 0.75, feedback: float = 0.36, mix: float = 0.32) -> np.ndarray:
    """Tempo-locked dotted-eighth (3/16) stereo ping-pong delay."""
    d_samp = int(round(delay_beats * BEAT_SEC * SR))
    wet = np.zeros_like(bus)
    l_src = lp_fft(hp_fft(bus[0], 260.0), 5200.0)
    r_src = lp_fft(hp_fft(bus[1], 260.0), 5200.0)
    g = feedback
    for tap in range(1, 7):
        sh = tap * d_samp
        if sh >= N_SAMPLES:
            break
        if tap % 2 == 1:
            wet[1, sh:] += l_src[:-sh] * g
            wet[0, sh:] += r_src[:-sh] * (g * 0.45)
        else:
            wet[0, sh:] += l_src[:-sh] * g
            wet[1, sh:] += r_src[:-sh] * (g * 0.45)
        g *= feedback
    return bus + wet * mix


def studio_hall_reverb(bus: np.ndarray, mix: float = 0.28) -> np.ndarray:
    out = np.zeros_like(bus)
    taps_l = [(0.023, 0.44), (0.047, 0.36), (0.083, 0.29), (0.131, 0.23), (0.199, 0.17), (0.293, 0.12), (0.431, 0.08)]
    taps_r = [(0.031, 0.42), (0.059, 0.35), (0.097, 0.28), (0.149, 0.22), (0.223, 0.16), (0.331, 0.11), (0.467, 0.07)]
    for d, g in taps_l:
        sh = int(d * SR)
        if sh < N_SAMPLES:
            out[0, sh:] += bus[0, :-sh] * g + bus[1, :-sh] * (g * 0.38)
    for d, g in taps_r:
        sh = int(d * SR)
        if sh < N_SAMPLES:
            out[1, sh:] += bus[1, :-sh] * g + bus[0, :-sh] * (g * 0.38)
    out[0] = lp_fft(hp_fft(out[0], 180.0), 5400.0)
    out[1] = lp_fft(hp_fft(out[1], 180.0), 5200.0)
    return bus * (1.0 - mix * 0.25) + out * mix


# ─────────────────────────── V2 High-Impact Synths ───────────────────────

def bandlimited_saw(freq: float, t: np.ndarray, phase_off: float = 0.0, harmonics: int = 12) -> np.ndarray:
    s = np.zeros_like(t)
    nyq = SR * 0.44
    for h in range(1, harmonics + 1):
        if freq * h >= nyq:
            break
        s += ((-1) ** (h + 1)) * (1.0 / h) * np.sin(2.0 * np.pi * freq * h * t + phase_off * h)
    return s * 0.62


def synth_kick_v2() -> np.ndarray:
    """Punchy club/cinema kick with crisp transient click & tight D1 (36.7Hz -> 46Hz) body."""
    n = int(0.30 * SR)
    t = np.arange(n) / SR
    freq = 46.0 + 145.0 * np.exp(-t * 42.0) + 42.0 * np.exp(-t * 14.0)
    phase = 2.0 * np.pi * np.cumsum(freq) / SR
    body = np.sin(phase) * np.exp(-t * 9.5)
    punch = np.sin(2.0 * np.pi * (95.0 + 180.0 * np.exp(-t * 90.0)) * t) * np.exp(-t * 28.0) * 0.42
    click = np.sin(2.0 * np.pi * 2900.0 * t) * np.exp(-t * 240.0) * 0.32
    env = np.minimum(1.0, t / 0.0018)
    return np.tanh((body + punch + click) * 1.65) * env


def synth_snare_v2(rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Modern crisp layered snare + stereo clap with tight body punch."""
    n = int(0.24 * SR)
    t = np.arange(n) / SR
    body = np.sin(2.0 * np.pi * (185.0 + 115.0 * np.exp(-t * 55.0)) * t) * np.exp(-t * 24.0) * 0.65
    noise_l = bp_fft(rng.standard_normal(n), 950.0, 9200.0)
    noise_r = bp_fft(rng.standard_normal(n), 1050.0, 9600.0)
    snap = (
        np.exp(-t * 85.0)
        + 0.72 * np.exp(-np.maximum(0.0, t - 0.008) * 75.0) * (t >= 0.008)
        + 0.85 * np.exp(-np.maximum(0.0, t - 0.015) * 18.0) * (t >= 0.015)
    )
    l = np.tanh((body + noise_l * snap * 0.58) * 1.35) * np.minimum(1.0, t / 0.001)
    r = np.tanh((body + noise_r * snap * 0.58) * 1.35) * np.minimum(1.0, t / 0.001)
    return l, r


def synth_hat_v2(open_hat: bool, rng: np.random.Generator) -> np.ndarray:
    dur = 0.19 if open_hat else 0.042
    n = int(dur * SR)
    t = np.arange(n) / SR
    # Metallic FM ring + filtered crisp air noise
    metal = np.sin(2.0 * np.pi * 7400.0 * t + 2.2 * np.sin(2.0 * np.pi * 5180.0 * t)) * 0.25
    air = bp_fft(rng.standard_normal(n), 7200.0, 16500.0) * 0.90
    decay = 13.5 if open_hat else 78.0
    return (metal + air) * np.exp(-t * decay) * np.minimum(1.0, t / 0.0008)


def synth_reese_bass(freq: float, dur_sec: float, bright: float = 0.6) -> tuple[np.ndarray, np.ndarray]:
    """Growling modern cyberpunk/electro Reese + pure sub foundation."""
    n = int(dur_sec * SR)
    t = np.arange(n) / SR
    sub = np.sin(2.0 * np.pi * freq * t)
    s1 = bandlimited_saw(freq * 0.996, t, 0.2, harmonics=10)
    s2 = bandlimited_saw(freq * 1.004, t, 1.7, harmonics=10)
    s3 = bandlimited_saw(freq * 2.002, t, 0.9, harmonics=6) * 0.35
    cut = 320.0 + bright * 980.0
    mid_l = lp_fft(s1 + s3, cut)
    mid_r = lp_fft(s2 + s3, cut * 1.04)
    atk = np.minimum(1.0, t / 0.006)
    rel = np.minimum(1.0, (dur_sec - t) / 0.032)
    env = atk * np.maximum(0.0, rel)
    l = np.tanh((sub * 0.85 + mid_l * 0.58) * 1.35) * env
    r = np.tanh((sub * 0.85 + mid_r * 0.58) * 1.35) * env
    return l, r


def synth_supersaw_chord(freqs: list[float], dur_sec: float, cutoff: float = 3200.0, atk_s: float = 0.08) -> tuple[np.ndarray, np.ndarray]:
    """7-voice wide detuned stereo supersaw pad/stab!"""
    n = int(dur_sec * SR)
    t = np.arange(n) / SR
    l = np.zeros(n)
    r = np.zeros(n)
    detunes = [-0.011, -0.007, -0.003, 0.0, 0.003, 0.007, 0.011]
    pans = [0.12, 0.88, 0.28, 0.50, 0.72, 0.18, 0.82]
    for f in freqs:
        for d, pan in zip(detunes, pans):
            sig = bandlimited_saw(f * (1.0 + d), t, phase_off=d * 90.0, harmonics=8)
            l += sig * (1.0 - pan * 0.55)
            r += sig * (0.45 + pan * 0.55)
    norm = 1.0 / (len(freqs) * math.sqrt(len(detunes)))
    l = lp_fft(hp_fft(l * norm, 140.0), cutoff)
    r = lp_fft(hp_fft(r * norm, 140.0), cutoff * 1.05)
    atk = np.minimum(1.0, t / max(0.006, atk_s))
    rel = np.minimum(1.0, (dur_sec - t) / min(0.35, dur_sec * 0.35))
    env = atk * np.maximum(0.0, rel)
    return l * env, r * env


def synth_lead_pluck(freq: float, dur_sec: float = 0.26, drive: float = 1.2) -> tuple[np.ndarray, np.ndarray]:
    """Anthemic glassy FM + saw precision lead hook."""
    n = int(dur_sec * SR)
    t = np.arange(n) / SR
    mod = np.sin(2.0 * np.pi * freq * 2.0 * t) * (2.6 * np.exp(-t * 19.0))
    fm = np.sin(2.0 * np.pi * freq * t + mod)
    saw = lp_fft(bandlimited_saw(freq, t, 0.4, harmonics=10), 4200.0) * 0.45
    air = np.sin(2.0 * np.pi * freq * 3.0 * t) * np.exp(-t * 32.0) * 0.25
    env = np.minimum(1.0, t / 0.0025) * np.exp(-t * 8.2)
    s = np.tanh((fm + saw + air) * drive) * env
    return s, s * 0.96


def synth_brass_bram(freq: float, dur_sec: float) -> tuple[np.ndarray, np.ndarray]:
    """Cinematic dark trailer sub-brass swell (Hans Zimmer / Cyberpunk feel)."""
    n = int(dur_sec * SR)
    t = np.arange(n) / SR
    p = t / dur_sec
    l = np.zeros(n)
    r = np.zeros(n)
    for oct_m, g in [(1.0, 1.0), (2.0, 0.72), (3.0, 0.35)]:
        l += bandlimited_saw(freq * oct_m * 0.996, t, 0.1, harmonics=12) * g
        r += bandlimited_saw(freq * oct_m * 1.004, t, 1.3, harmonics=12) * g
    l = lp_fft(l, 780.0)
    r = lp_fft(r, 820.0)
    env = np.sin(np.minimum(1.0, p / 0.25) * math.pi * 0.5) * np.exp(-np.maximum(0.0, p - 0.25) * 2.6)
    return np.tanh(l * 1.4) * env * 0.48, np.tanh(r * 1.4) * env * 0.48


# ─────────────────────────── Bespoke V2 Foley & Impact SFX ───────────────

def render_foley_v2(cue: dict, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    kind = cue["type"]

    if kind == "laser_ignite":
        n = int(1.2 * SR)
        t = np.arange(n) / SR
        f = 82.0 + 2600.0 * np.exp(-t * 16.0)
        sweep = np.sin(2.0 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 5.8) * 0.52
        sub = np.sin(2.0 * np.pi * (38.0 + 44.0 * np.exp(-t * 7.5)) * t) * np.exp(-t * 2.4) * 0.85
        air = bp_fft(rng.standard_normal(n), 2200, 9500) * np.exp(-t * 7.0) * 0.22
        s = np.tanh((sweep + sub + air) * 1.25) * np.minimum(1.0, t / 0.004)
        return s, s * 0.96

    if kind in ("title_slam", "title_slam_hi"):
        n = int(0.45 * SR)
        t = np.arange(n) / SR
        base = 46.0 if kind == "title_slam" else 62.0
        sub = np.sin(2.0 * np.pi * (base + 95.0 * np.exp(-t * 32.0)) * t) * np.exp(-t * 9.5) * 0.82
        clang_f = 1174.66 if kind == "title_slam_hi" else 880.0
        clang = np.sin(2.0 * np.pi * clang_f * t) * np.exp(-t * 14.0) * 0.34
        air = bp_fft(rng.standard_normal(n), 1200, 6800) * np.exp(-t * 16.0) * 0.24
        s = np.tanh((sub + clang + air) * 1.35) * np.minimum(1.0, t / 0.0015)
        return s, np.roll(s, 14)

    if kind in ("whip_drop", "glass_drop", "montage_whip", "clutch_whip", "zoom_whoosh"):
        dur = 0.42 if kind != "glass_drop" else 0.58
        n = int(dur * SR)
        t = np.arange(n) / SR
        p = t / dur
        env = np.sin(p * math.pi) ** 1.4
        noise = bp_fft(rng.standard_normal(n), 500.0, 5800.0) * env * 0.46
        sub = np.sin(2.0 * np.pi * (48.0 + 120.0 * np.exp(-t * 34.0)) * t) * np.exp(-t * 11.0) * 0.72
        metal = np.sin(2.0 * np.pi * (3900.0 if kind == "clutch_whip" else 1480.0) * t) * np.exp(-t * 48.0) * 0.38
        pan_l = np.sqrt(1.0 - p * 0.55)
        pan_r = np.sqrt(0.45 + p * 0.55)
        l = np.tanh((noise * pan_l + sub + metal) * 1.25) * np.minimum(1.0, t / 0.0015)
        r = np.tanh((noise * pan_r + sub + metal) * 1.25) * np.minimum(1.0, t / 0.0015)
        return l, r

    if kind in ("riser_short", "riser_impact", "riser_finale"):
        dur = 0.88 if kind == "riser_short" else (0.94 if kind == "riser_impact" else 0.72)
        n = int(dur * SR)
        t = np.arange(n) / SR
        p = t / dur
        # Screaming supersaw + white-noise reverse cymbal riser!
        f = 146.83 * (2.0 ** (p * 3.4))
        tone = np.sin(2.0 * np.pi * np.cumsum(f) / SR) * (p ** 2.0) * 0.36
        air = bp_fft(rng.standard_normal(n), 800.0, 9200.0) * (p ** 2.5) * 0.54
        cut = np.minimum(1.0, (dur - t) / 0.012)
        return (tone + air) * cut, (tone * 0.95 + np.roll(air, 48)) * cut

    if kind == "vernier_tick":
        pitch = float(cue.get("pitch", 1.0))
        n = int(0.042 * SR)
        t = np.arange(n) / SR
        f = 2850.0 * pitch
        s = (
            np.sin(2.0 * np.pi * f * t) * np.exp(-t * 165.0) * 0.65
            + np.sin(2.0 * np.pi * (f * 0.36) * t) * np.exp(-t * 115.0) * 0.35
        ) * np.minimum(1.0, t / 0.0006)
        return s, s

    if kind == "mouse_click":
        n = int(0.055 * SR)
        t = np.arange(n) / SR
        snap = np.sin(2.0 * np.pi * 3350.0 * t) * np.exp(-t * 240.0) * 0.65
        thock = np.sin(2.0 * np.pi * 640.0 * t) * np.exp(-t * 130.0) * 0.52
        s = (snap + thock) * np.minimum(1.0, t / 0.0005)
        return s, s

    if kind == "flywheel_spin":
        dur = 1.40
        n = int(dur * SR)
        t = np.arange(n) / SR
        env = np.minimum(1.0, t / 0.08) * np.exp(-t * 1.7)
        whir = bp_fft(rng.standard_normal(n), 1800.0, 7400.0) * env * 0.32
        turbine = np.sin(2.0 * np.pi * (520.0 + 480.0 * np.exp(-t * 2.4)) * t) * env * 0.24
        return whir + turbine, np.roll(whir, 28) + turbine

    if kind == "haptic_detent":
        n = int(0.14 * SR)
        t = np.arange(n) / SR
        lra = np.sin(2.0 * np.pi * 165.0 * t) * np.exp(-t * 45.0) * 0.92
        sub = np.sin(2.0 * np.pi * 76.0 * t) * np.exp(-t * 30.0) * 0.62
        return np.tanh((lra + sub) * 1.35), np.tanh((lra + sub) * 1.35)

    if kind == "haptic_thump":
        n = int(0.32 * SR)
        t = np.arange(n) / SR
        lra = np.sin(2.0 * np.pi * (62.0 + 55.0 * np.exp(-t * 28.0)) * t) * np.exp(-t * 11.5) * 1.00
        buzz = np.sin(2.0 * np.pi * 145.0 * t) * np.exp(-t * 25.0) * 0.42
        return np.tanh((lra + buzz) * 1.45), np.tanh((lra + buzz) * 1.45)

    if kind == "haptic_firework":
        n = int(0.40 * SR)
        s = np.zeros(n)
        for delay, freq in [(0.0, 150.0), (0.075, 195.0), (0.155, 112.0)]:
            st = int(delay * SR)
            m = int(0.15 * SR)
            tt = np.arange(m) / SR
            s[st:st + m] += (
                np.sin(2.0 * np.pi * freq * tt) * np.exp(-tt * 32.0) * 0.80
                + np.sin(2.0 * np.pi * (freq * 3.0) * tt) * np.exp(-tt * 55.0) * 0.28
            ) * np.minimum(1.0, tt / 0.001)
        return np.tanh(s * 1.3), np.tanh(s * 1.3)

    if kind in ("holo_bloom", "ui_chime", "confirm_burst", "brand_bell"):
        notes = [587.33, 659.25, 698.46, 880.0, 1046.50, 1174.66]
        if kind == "ui_chime":
            f0 = notes[int(cue.get("note", 0)) % len(notes)]
            chord = [f0, f0 * 1.5]
            dur = 0.58
        elif kind == "holo_bloom":
            chord = [293.66, 440.0, 587.33, 880.0]
            dur = 0.85
        elif kind == "confirm_burst":
            chord = [587.33, 880.0, 1174.66, 1760.0]
            dur = 0.90
        else:
            chord = [293.66, 440.0, 587.33, 659.25, 880.0, 1174.66]
            dur = 2.60
        n = int(dur * SR)
        t = np.arange(n) / SR
        l = np.zeros(n)
        r = np.zeros(n)
        for idx, f in enumerate(chord):
            dec = 4.0 if kind != "brand_bell" else 1.45
            mod = np.sin(2.0 * np.pi * f * 2.0 * t) * (1.4 * np.exp(-t * 14.0))
            tone = np.sin(2.0 * np.pi * f * t + mod) * np.exp(-t * dec)
            pan = 0.30 + 0.40 * (idx / max(1, len(chord) - 1))
            l += tone * (1.0 - pan * 0.5)
            r += tone * (0.5 + pan * 0.5)
        env = np.minimum(1.0, t / 0.004)
        sc = 0.44 / math.sqrt(len(chord))
        return l * env * sc, r * env * sc

    if kind == "finale_drop":
        n = int(2.8 * SR)
        t = np.arange(n) / SR
        sub = np.sin(2.0 * np.pi * (36.71 + 65.0 * np.exp(-t * 13.0)) * t) * np.exp(-t * 1.35) * 1.05
        air = bp_fft(rng.standard_normal(n), 280.0, 5200.0) * np.exp(-t * 2.4) * 0.36
        s = np.tanh((sub + air) * 1.35) * np.minimum(1.0, t / 0.0025)
        return s, s

    return np.zeros(1), np.zeros(1)


# ─────────────────────────── Full V2 30s Anthem Mix ──────────────────────

def build_mix_v2() -> np.ndarray:
    rng = np.random.default_rng(2028)
    drums = np.zeros((2, N_SAMPLES), dtype=np.float64)
    bass = np.zeros((2, N_SAMPLES), dtype=np.float64)
    chords_bus = np.zeros((2, N_SAMPLES), dtype=np.float64)
    lead_bus = np.zeros((2, N_SAMPLES), dtype=np.float64)
    fx = np.zeros((2, N_SAMPLES), dtype=np.float64)
    sidechain = np.ones(N_SAMPLES, dtype=np.float64)

    kick = synth_kick_v2()
    snare_l, snare_r = synth_snare_v2(rng)
    hat_c = synth_hat_v2(False, rng)
    hat_o = synth_hat_v2(True, rng)

    # ── 1. Cold Open Cinematic Sub-Brass Swell (Beats 0..8) ──────────────
    bl, br = synth_brass_bram(36.71, 6.2 * BEAT_SEC)  # Massive D1 trailer bram
    add_stereo(chords_bus, beat_to_sample(0.0), bl, br, gain=0.72)

    # Accelerating cold-open percussion build (Beats 4..7.75)
    for idx, b in enumerate([4.0, 5.0, 6.0, 6.5, 7.0, 7.25, 7.5, 7.75]):
        g = 0.24 + 0.32 * (idx / 7.0)
        add_stereo(drums, beat_to_sample(b), snare_l * 0.85, snare_r * 0.85, gain=g)

    # ── 2. Driving 128 BPM Kick, Snare, Hats & -6dB Sidechain Pump ───────
    for beat in range(8, 56):
        # Half-time cinematic pocket at Haptics reveal (Beat 28-29) & Cairo overlay lift (Beat 44-45)
        if beat in (29, 44, 45, 55):
            continue
        pos = beat_to_sample(beat)
        add_stereo(drums, pos, kick, kick, gain=0.80)

        # Deep -6 dB sidechain pump envelope (makes the supersaws & bass THROB!)
        duck_len = int(0.24 * SR)
        t_d = np.arange(duck_len) / SR
        curve = 1.0 - 0.54 * np.exp(-t_d * 14.5)
        end = min(N_SAMPLES, pos + duck_len)
        sidechain[pos:end] = np.minimum(sidechain[pos:end], curve[:end - pos])

        # Stereo layered snare/clap on beats 2 & 4
        if beat % 2 == 1 and beat not in (29, 45, 55):
            add_stereo(drums, pos, snare_l, snare_r, gain=0.52)

        # Crisp 16th-note metallic hi-hat groove with open-hat lift on the '&'
        if beat not in (28, 44, 55):
            for sub, g, is_open in [(0.25, 0.13, False), (0.50, 0.28, beat >= 18), (0.75, 0.16, False)]:
                h = hat_o if is_open else hat_c
                pan_l = 0.92 if sub == 0.25 else 0.78
                pan_r = 0.78 if sub == 0.25 else 0.95
                add_stereo(drums, beat_to_sample(beat + sub), h * pan_l, h * pan_r, gain=g)

    # Massive accelerating 16th -> 32nd-note climax snare roll (Beats 53.0 .. 55.75)!
    roll_beats = [53.0, 53.5, 54.0, 54.25, 54.5, 54.75, 55.0, 55.125, 55.25, 55.375, 55.5, 55.625, 55.75]
    for idx, b in enumerate(roll_beats):
        g = 0.22 + 0.42 * (idx / (len(roll_beats) - 1))
        add_stereo(drums, beat_to_sample(b), snare_l, snare_r, gain=g)

    # ── 3. Growling Reese & Sub Bassline (D1 -> F1 -> Bb0 -> C1 -> A0) ───
    # 16th-note syncopated electro-techno bass pattern
    bass_sections = [
        # (start_beat, end_beat, root_seq_per_2_beats, bright)
        (8,  18, [36.71, 36.71, 43.65, 32.70, 36.71], 0.55),  # Darkfield D1 -> F1 -> C1
        (18, 28, [36.71, 43.65, 49.00, 32.70, 55.00], 0.78),  # MagSpeed D1 -> F1 -> G1 -> C1 -> A1
        (28, 38, [29.14, 29.14, 32.70, 36.71, 36.71], 0.65),  # Haptics deep Bb0 -> C1 -> D1
        (38, 50, [36.71, 29.14, 32.70, 55.00, 36.71, 32.70], 0.82),  # Actions Ring lifted
        (50, 55.5, [36.71, 43.65, 49.00], 0.98),              # Climax maximum growl!
    ]
    for s_b, e_b, roots, bright in bass_sections:
        b = float(s_b)
        step = 0
        while b < e_b:
            root = roots[(step // 4) % len(roots)]
            # Pumping 8th-note syncopated hits
            dur_b = 0.46 if (step % 2 == 0) else 0.40
            f = root * (2.0 if (step % 8 == 7) else 1.0)  # octave jump turnaround!
            bl, br = synth_reese_bass(f, dur_b * BEAT_SEC, bright=bright)
            add_stereo(bass, beat_to_sample(b), bl, br, gain=0.52)
            b += 0.5
            step += 1

    # ── 4. 7-Voice Wide Detuned Supersaw Chord Progression ───────────────
    # Dm9, Bbmaj7, Csus2, Am7
    Dm9    = [146.83, 220.00, 261.63, 329.63, 349.23]
    Bbmaj7 = [116.54, 174.61, 220.00, 293.66, 349.23]
    Csus2  = [130.81, 196.00, 261.63, 293.66, 392.00]
    Am7    = [110.00, 164.81, 196.00, 261.63, 329.63]

    chord_events = [
        (8.0,  4.0, Dm9,    1800.0, 0.24),
        (12.0, 4.0, Bbmaj7, 2200.0, 0.26),
        (16.0, 2.0, Csus2,  2600.0, 0.28),
        (18.0, 4.0, Dm9,    3200.0, 0.30),
        (22.0, 4.0, Csus2,  3600.0, 0.32),
        (26.0, 2.0, Am7,    3800.0, 0.32),
        (28.0, 4.0, Bbmaj7, 2400.0, 0.32),
        (32.0, 4.0, Csus2,  3200.0, 0.34),
        (36.0, 2.0, Dm9,    3600.0, 0.34),
        # 1-beat chord stabs synced to Actions Ring 4-theme morph (Beats 40..43)!
        (38.0, 2.0, Dm9,    3800.0, 0.34),
        (40.0, 1.0, Bbmaj7, 4400.0, 0.38),
        (41.0, 1.0, Csus2,  4600.0, 0.38),
        (42.0, 1.0, Dm9,    5000.0, 0.40),
        (43.0, 1.0, Am7,    5200.0, 0.40),
        (44.0, 6.0, Csus2,  3000.0, 0.30),  # Cairo Wayland overlay lush bed
        (50.0, 5.5, Dm9,    5800.0, 0.44),  # Climax full-open supersaw!
        (56.0, 7.6, [73.42, 146.83, 220.00, 261.63, 329.63, 440.00], 2600.0, 0.38),  # Finale wide Dmin9
    ]
    for st, dur, freqs, cut, g in chord_events:
        sl, sr = synth_supersaw_chord(freqs, dur * BEAT_SEC, cutoff=cut, atk_s=0.03 if dur <= 1.5 else 0.10)
        add_stereo(chords_bus, beat_to_sample(st), sl, sr, gain=g)

    # ── 5. Catchy Syncopated Anthemic FM Lead Hook + Ping-Pong Delay ─────
    # Iconic 8-beat D-minor melodic riff (beats 18..28, 38..44, 50..55.5)
    riff = [
        (0.00, 587.33), (0.75, 698.46), (1.50, 880.00), (2.00, 783.99),
        (2.50, 698.46), (3.00, 659.25), (3.50, 587.33),
        (4.00, 523.25), (4.75, 587.33), (5.50, 659.25), (6.00, 880.00),
        (6.75, 1046.50), (7.50, 880.00),
    ]
    for bar_start, g_lead in [(18.0, 0.30), (38.0, 0.34), (50.0, 0.38)]:
        for off_b, freq in riff:
            b = bar_start + off_b
            if b >= 55.5 or (bar_start == 38.0 and b >= 44.0):
                continue
            ll, lr = synth_lead_pluck(freq, dur_sec=0.25, drive=1.25)
            add_stereo(lead_bus, beat_to_sample(b), ll, lr, gain=g_lead)

    # Apply dotted-eighth stereo ping-pong delay to lead hook!
    lead_wet = ping_pong_delay(lead_bus, delay_beats=0.75, feedback=0.40, mix=0.38)

    # Apply true -6 dB sidechain pump to bass, supersaw chords & lead!
    for bus in (bass, chords_bus, lead_wet):
        bus[0] *= sidechain
        bus[1] *= sidechain

    # ── 6. Frame-Synced Bespoke Foley & SFX Layer ────────────────────────
    cues = load_audio_cues()
    for cue in cues:
        fl, fr = render_foley_v2(cue, rng)
        add_stereo(fx, beat_to_sample(float(cue["beat"])), fl, fr, gain=float(cue.get("gain", 0.85)) * 0.64)

    # ── 7. Bus Reverb + Parallel Glue Compression + Clean Master Tail ────
    melodic = studio_hall_reverb(chords_bus + lead_wet, mix=0.30)
    fx_wet = studio_hall_reverb(fx, mix=0.18)
    drums_punch = np.tanh(drums * 1.18) * 0.92
    master = drums_punch + bass + melodic + fx_wet

    master = np.tanh(master * 0.86) * 0.92

    # Crisp 10ms fade-in + 1.4s silky exponential tail to pure zero at 30.000s
    fi = int(0.010 * SR)
    master[:, :fi] *= np.linspace(0.0, 1.0, fi)
    fo = int(1.4 * SR)
    master[:, -fo:] *= (np.linspace(1.0, 0.0, fo) ** 1.9)
    master[:, -int(0.06 * SR):] = 0.0
    return master


def write_wav_16bit(path: Path, stereo: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(stereo, -0.999, 0.999)
    interleaved = np.empty(clipped.shape[1] * 2, dtype=np.int16)
    interleaved[0::2] = np.round(clipped[0] * 32767.0).astype(np.int16)
    interleaved[1::2] = np.round(clipped[1] * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(interleaved.tobytes())


def master_to_lufs14(raw_wav: Path, out_wav: Path) -> None:
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    p1 = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-y", "-i", str(raw_wav),
            "-af", "loudnorm=I=-14.0:TP=-1.0:LRA=8.0:print_format=json",
            "-f", "null", "-",
        ],
        capture_output=True, text=True, check=True,
    )
    stats = json.loads(p1.stderr[p1.stderr.rfind("{"):p1.stderr.rfind("}") + 1])
    filt = (
        f"loudnorm=I=-14.0:TP=-1.0:LRA=8.0:linear=true:"
        f"measured_I={stats['input_i']}:measured_LRA={stats['input_lra']}:"
        f"measured_TP={stats['input_tp']}:measured_thresh={stats['input_thresh']}:"
        f"offset={stats['target_offset']}"
    )
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-y", "-i", str(raw_wav),
            "-af", filt, "-ar", str(SR), "-c:a", "pcm_s24le", str(out_wav),
        ],
        capture_output=True, text=True, check=True,
    )
    chk = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(out_wav), "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True, check=True,
    )
    print(f"Mastered V2 audio -> {out_wav}")
    for ln in [l.strip() for l in chk.stderr.splitlines() if any(k in l for k in ("I:", "LRA:", "Peak:"))][-4:]:
        print("  ", ln)


def main() -> None:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Synthesizing V2 30.00s 128 BPM high-impact electronic score + foley...")
    mix = build_mix_v2()
    raw_wav = TMP_DIR / "raw_mix_v2.wav"
    out_wav = OUT_DIR / "mx4_studio_master_audio.wav"
    write_wav_16bit(raw_wav, mix)
    master_to_lufs14(raw_wav, out_wav)


if __name__ == "__main__":
    main()
