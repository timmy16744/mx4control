/**
 * MX4 Studio (2027 Edition) — Frontend Controller
 *
 * Bridges the full-bleed 3D WebGL MX Master 4 stage, precision vernier controls,
 * interactive Precision Shift Force S-curve, and 60fps copper haptic oscilloscope
 * to Python/D-Bus (mx4-sysd + mx4-agent) over QWebChannel.
 */

import { BUTTON_META, CID, MouseStudio3D } from './mouse3d.js';

const DPI_PRESET_CHIPS = [600, 800, 1000, 1200, 1600, 2000, 3000, 4000, 8000];

const WAVEFORMS = [
  [0,  'Sharp State',   'M4 16 L22 16 L29 4 L36 16 L54 16'],
  [1,  'Damp State',    'M4 16 Q24 16 29 7 Q34 16 54 16'],
  [2,  'Sharp Impact',  'M4 18 L24 18 L29 2 L34 18 L54 18'],
  [3,  'Damp Impact',   'M4 16 C18 16 24 5 29 5 C34 5 40 16 54 16'],
  [4,  'Subtle Impact', 'M4 15 Q29 9 54 15'],
  [5,  'Happy Alert',   'M4 16 L17 16 L21 5 L25 16 L33 16 L37 5 L41 16 L54 16'],
  [6,  'Angry Alert',   'M4 18 L14 18 L18 3 L22 18 L29 3 L36 18 L40 3 L44 18 L54 18'],
  [7,  'Completed',     'M4 18 L24 12 L34 4 L44 12 L54 18'],
  [8,  'Square',        'M4 17 L16 17 L16 6 L28 6 L28 17 L40 17 L40 6 L54 6'],
  [9,  'Wave',          'M4 12 Q12 3 20 12 T36 12 T54 12'],
  [10, 'Firework',      'M4 16 L16 6 L24 17 L30 3 L38 17 L44 7 L54 16'],
  [11, 'Mad',           'M4 12 L10 4 L16 20 L22 4 L28 20 L34 4 L40 20 L46 4 L54 12'],
  [12, 'Knock',         'M4 16 L18 16 L21 4 L24 16 L35 16 L38 4 L41 16 L54 16'],
  [13, 'Jingle',        'M4 16 Q14 4 24 14 Q34 20 42 6 Q48 14 54 12'],
  [14, 'Ringing',       'M4 12 Q8 5 12 12 T20 12 T28 12 T36 12 T44 12 T52 12'],
];

const QUICK_RING_PRESETS = [
  ['Copy',        'keystroke',         'ctrl+c'],
  ['Paste',       'keystroke',         'ctrl+v'],
  ['Undo',        'keystroke',         'ctrl+z'],
  ['Redo',        'keystroke',         'ctrl+shift+z'],
  ['Save',        'keystroke',         'ctrl+s'],
  ['Find',        'keystroke',         'ctrl+f'],
  ['New Tab',     'keystroke',         'ctrl+t'],
  ['Close Tab',   'keystroke',         'ctrl+w'],
  ['Screenshot',  'command',           'hyprshot -m region'],
  ['Cycle DPI',   'dpi_cycle',         ''],
  ['Scroll Mode', 'smartshift_toggle', ''],
  ['Next Host',   'host_next',         ''],
];

const QUICK_REBIND_KEYS = [
  ['Copy', 'ctrl+c'], ['Paste', 'ctrl+v'], ['Undo', 'ctrl+z'], ['Redo', 'ctrl+shift+z'],
  ['New Tab', 'ctrl+t'], ['Close Tab', 'ctrl+w'], ['Play/Pause', 'XF86AudioPlay'],
  ['Vol +', 'XF86AudioRaiseVolume'], ['Vol -', 'XF86AudioLowerVolume'], ['Overview', 'super'],
];

const ALL_CONTROLS = [
  [CID.LEFT_CLICK,   'Left Click',       'Primary mouse button'],
  [CID.RIGHT_CLICK,  'Right Click',      'Secondary mouse button'],
  [CID.MIDDLE_CLICK, 'MagSpeed Wheel',   'Scroll wheel click & MagSpeed flywheel'],
  [CID.SMART_SHIFT,  'Mode Shift',       'Top button behind scroll wheel'],
  [CID.THUMB_WHEEL,  'Thumb Wheel',      'Horizontal CNC aluminum side scroll wheel (0x2150)'],
  [CID.BACK,         'Back',             'Rear side button'],
  [CID.FORWARD,      'Forward',          'Middle side button'],
  [CID.GESTURE,      'Gesture Button',   'Front side button (3rd side pill)'],
  [CID.THUMB_PAD,    'Haptic Sense Pad', 'Force-sensing thumb pad (0x01A0 / 0x19C0)'],
];

const FRIENDLY_ACTION = {
  default: 'Default',
  disabled: 'Disabled',
  remap: 'Hardware Remap',
  keystroke: 'Keystroke',
  key_hold: 'Hold Key',
  command: 'Command',
  application: 'App',
  dpi_cycle: 'Cycle DPI',
  dpi_set: 'Set DPI',
  smartshift_toggle: 'Toggle Scroll',
  host_next: 'Next Host',
  haptic: 'Haptic',
};

// ─────────────────────────── QWebChannel Bridge ──────────────────────────

let bridge = null;
let reqSeq = 0;
const pending = new Map();

function initBridge() {
  return new Promise((resolve) => {
    if (typeof window.QWebChannel === 'undefined' || !window.qt?.webChannelTransport) {
      resolve(null);
      return;
    }
    new window.QWebChannel(window.qt.webChannelTransport, (channel) => {
      bridge = channel.objects.mx4Bridge;
      bridge.responseReady.connect((reqId, payloadStr) => {
        const slot = pending.get(reqId);
        if (!slot) return;
        pending.delete(reqId);
        try {
          const parsed = JSON.parse(payloadStr);
          if (parsed.ok) slot.resolve(parsed.data);
          else slot.reject(new Error(parsed.error || 'Operation failed'));
        } catch (e) {
          slot.reject(e);
        }
      });
      bridge.liveEvent.connect((eventName, payloadStr) => {
        let data = {};
        try { data = JSON.parse(payloadStr); } catch {}
        onLiveEvent(eventName, data);
      });
      resolve(bridge);
    });
  });
}

function rpc(method, args = {}) {
  if (!bridge) {
    return Promise.reject(new Error('Hardware bridge not connected'));
  }
  const id = `r${++reqSeq}`;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    bridge.invoke(id, method, JSON.stringify(args));
    setTimeout(() => {
      if (pending.has(id)) {
        pending.delete(id);
        reject(new Error(`${method} timed out`));
      }
    }, 18000);
  });
}

// ─────────────────────────── App State ───────────────────────────────────

const state = {
  tab: 'device',
  snapshot: null,
  ringProfileId: 'default',
  ringSliceIdx: 0,
  ringThemeId: 'studio',
  ringSizeId: 'standard',
  ringShowHints: true,
  ringAnimate: true,
  buttonScope: 'global',
  probedFeatures: [],
  recordingKeys: false,
  recordingFocusKeys: false,
  focusedCid: null,
  rebindCid: null,
  promptCallback: null,
  activeFeelWave: 3, // Deep Thump default matching Mockup 3
  torqueValue: 75,
  scrollSpeed: 1.0,
  scrollSmoothness: 0,
  scrollAccel: 0,
  hapticEnabled: true,
  hapticLevel: 55,
  padPressCount: 0,
  padWasHeld: false,
  oscPulse: 0.0,
  oscPhase: 0.0,
  reducedMotion: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
};

let studio3d = null;
const timers = {};
function debounce(key, ms, fn) {
  clearTimeout(timers[key]);
  timers[key] = setTimeout(fn, ms);
}

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function toast(msg) {
  const stack = $('#toast-stack');
  const el = document.createElement('div');
  el.className = 'studio-toast';
  el.textContent = msg;
  stack.appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(8px)';
    setTimeout(() => el.remove(), 260);
  }, 2600);
}

// ─────────────────────────── Vernier Precision Rulers ────────────────────

function buildVernierTicks(containerSel, count = 51, majorEvery = 5) {
  const box = $(containerSel);
  if (!box) return;
  box.innerHTML = '';
  for (let i = 0; i < count; i++) {
    const t = document.createElement('span');
    t.className = `v-tick ${i % majorEvery === 0 ? 'is-major' : ''}`;
    box.appendChild(t);
  }
}

function updateVernierFill(inputSel, fillSel) {
  const inp = $(inputSel);
  const fill = $(fillSel);
  if (!inp || !fill) return;
  const min = Number(inp.min || 0);
  const max = Number(inp.max || 100);
  const val = Number(inp.value || 0);
  const pct = max > min ? ((val - min) / (max - min)) * 100 : 0;
  fill.style.width = `${Math.max(0, Math.min(100, pct))}%`;
}

function renderDpiStageMarkers(presets = [800, 1200, 1600, 2400, 4000]) {
  const box = $('#dpi-vernier-stages');
  const slider = $('#dpi-slider');
  if (!box || !slider) return;
  const min = Number(slider.min || 200);
  const max = Number(slider.max || 8000);
  box.innerHTML = '';
  for (const p of presets) {
    if (p < min || p > max) continue;
    const pct = ((p - min) / Math.max(1, max - min)) * 100;
    const m = document.createElement('button');
    m.type = 'button';
    m.className = 'v-stage-mark';
    m.style.left = `${pct}%`;
    m.title = `Jump to DPI Stage: ${p}`;
    m.setAttribute('aria-label', `Jump to ${p} DPI`);
    m.addEventListener('click', (e) => {
      e.stopPropagation();
      commitDpi(p);
    });
    box.appendChild(m);
  }
}

function hapticStrengthWord(lvl, enabled) {
  if (!enabled) return 'Silent';
  if (lvl <= 22) return 'Subtle';
  if (lvl <= 55) return 'Medium';
  if (lvl <= 80) return 'High';
  return 'Intense';
}

// ─────────────────────────── Interactive Precision Shift Curve (Scroll) ──

const CURVE_BOX = { left: 14, right: 406, top: 10, bottom: 130 };

function initTorqueCurveGraph() {
  const gridGroup = $('#curve-grid-group');
  const labelGroup = $('#curve-axis-labels');
  if (!gridGroup || !labelGroup) return;
  const ns = 'http://www.w3.org/2000/svg';
  gridGroup.innerHTML = '';
  labelGroup.innerHTML = '';

  const w = CURVE_BOX.right - CURVE_BOX.left;
  const h = CURVE_BOX.bottom - CURVE_BOX.top;

  // 10 vertical columns (0..100 by 10)
  for (let i = 0; i <= 10; i++) {
    const x = CURVE_BOX.left + (i / 10) * w;
    const line = document.createElementNS(ns, 'line');
    line.setAttribute('x1', String(x));
    line.setAttribute('y1', String(CURVE_BOX.top));
    line.setAttribute('x2', String(x));
    line.setAttribute('y2', String(CURVE_BOX.bottom));
    line.setAttribute('stroke', i === 0 || i === 10 ? 'rgba(255,255,255,0.12)' : 'rgba(255,255,255,0.065)');
    line.setAttribute('stroke-width', '1');
    gridGroup.appendChild(line);

    const txt = document.createElementNS(ns, 'text');
    txt.setAttribute('x', String(x));
    txt.setAttribute('y', String(CURVE_BOX.bottom + 17));
    txt.setAttribute('fill', 'rgba(175,185,202,0.58)');
    txt.setAttribute('font-size', '9.5');
    txt.setAttribute('font-family', 'JetBrains Mono, ui-monospace, monospace');
    txt.setAttribute('text-anchor', i === 0 ? 'start' : (i === 10 ? 'end' : 'middle'));
    txt.textContent = String(i * 10);
    labelGroup.appendChild(txt);
  }

  // 5 horizontal rows
  for (let r = 0; r <= 5; r++) {
    const y = CURVE_BOX.top + (r / 5) * h;
    const line = document.createElementNS(ns, 'line');
    line.setAttribute('x1', String(CURVE_BOX.left));
    line.setAttribute('y1', String(y));
    line.setAttribute('x2', String(CURVE_BOX.right));
    line.setAttribute('y2', String(y));
    line.setAttribute('stroke', r === 5 ? 'rgba(255,255,255,0.14)' : 'rgba(255,255,255,0.065)');
    line.setAttribute('stroke-width', '1');
    gridGroup.appendChild(line);
  }

  // Interactive pointer dragging on the S-curve graph
  const svg = $('#torque-curve-svg');
  let dragging = false;

  const updateFromClientX = (clientX, commit = false) => {
    const rect = svg.getBoundingClientRect();
    const viewX = ((clientX - rect.left) / rect.width) * 420;
    const norm = Math.max(0.01, Math.min(1, (viewX - CURVE_BOX.left) / w));
    const val = Math.max(1, Math.min(100, Math.round(norm * 100)));
    setTorqueUI(val);
    studio3d?.setHardwareState({ torque: val });
    if (commit) commitScrollMode();
    else debounce('torque', 110, () => commitScrollMode());
  };

  svg.addEventListener('pointerdown', (e) => {
    dragging = true;
    svg.setPointerCapture(e.pointerId);
    updateFromClientX(e.clientX, false);
  });
  svg.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    updateFromClientX(e.clientX, false);
  });
  svg.addEventListener('pointerup', (e) => {
    if (!dragging) return;
    dragging = false;
    try { svg.releasePointerCapture(e.pointerId); } catch {}
    updateFromClientX(e.clientX, true);
  });
  svg.addEventListener('keydown', (e) => {
    let delta = 0;
    if (e.key === 'ArrowRight' || e.key === 'ArrowUp') delta = 5;
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') delta = -5;
    if (!delta) return;
    e.preventDefault();
    const next = Math.max(1, Math.min(100, state.torqueValue + delta));
    setTorqueUI(next);
    studio3d?.setHardwareState({ torque: next });
    debounce('torque', 110, () => commitScrollMode());
  });
}

function setTorqueUI(val) {
  const v = Math.max(1, Math.min(100, Math.round(Number(val) || 50)));
  state.torqueValue = v;
  $('#torque-slider').value = String(v);
  $('#torque-readout').textContent = String(v);
  $('#torque-curve-svg')?.setAttribute('aria-valuenow', String(v));

  for (const chip of $$('[data-torque]')) {
    chip.classList.toggle('is-active', Number(chip.dataset.torque) === v);
  }

  // Render smooth sigmoid S-curve whose inflection point tracks `v` (1..100%)
  const w = CURVE_BOX.right - CURVE_BOX.left;
  const h = CURVE_BOX.bottom - CURVE_BOX.top;
  const center = 0.14 + (v / 100) * 0.72; // keeps clean S-curve inflection visible across [14%..86%]
  const steep = 8.2;
  const sig = (t) => 1 / (1 + Math.exp(-steep * (t - center)));
  const s0 = sig(0);
  const s1 = sig(1);
  const evalY = (t) => (sig(t) - s0) / Math.max(0.0001, s1 - s0);

  const steps = 56;
  let strokeD = '';
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const x = CURVE_BOX.left + t * w;
    const y = CURVE_BOX.bottom - evalY(t) * (h - 2);
    strokeD += (i === 0 ? `M ${x.toFixed(1)} ${y.toFixed(1)}` : ` L ${x.toFixed(1)} ${y.toFixed(1)}`);
  }
  const areaD = `${strokeD} L ${CURVE_BOX.right} ${CURVE_BOX.bottom} L ${CURVE_BOX.left} ${CURVE_BOX.bottom} Z`;

  $('#curve-stroke-path')?.setAttribute('d', strokeD);
  $('#curve-area-path')?.setAttribute('d', areaD);

  // Draggable glowing copper node positioned smoothly at torque X on the curve!
  const nodeT = v / 100;
  const nx = CURVE_BOX.left + nodeT * w;
  const ny = CURVE_BOX.bottom - evalY(nodeT) * (h - 2);
  $('#curve-node')?.setAttribute('cx', nx.toFixed(1));
  $('#curve-node')?.setAttribute('cy', ny.toFixed(1));
  $('#curve-node-halo')?.setAttribute('cx', nx.toFixed(1));
  $('#curve-node-halo')?.setAttribute('cy', ny.toFixed(1));
}

// ─────────────────────────── 60fps Copper Haptic Oscilloscope ────────────

function startHapticOscilloscope() {
  const canvas = $('#haptic-osc-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  const drawFrame = () => {
    requestAnimationFrame(drawFrame);

    // Only redraw actively when Haptics tab is visible (zero idle CPU cost on other tabs!)
    if (state.tab !== 'haptics') return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const rect = canvas.getBoundingClientRect();
    const W = Math.max(200, Math.round(rect.width));
    const H = Math.max(100, Math.round(rect.height));
    if (canvas.width !== W * dpr || canvas.height !== H * dpr) {
      canvas.width = W * dpr;
      canvas.height = H * dpr;
    }

    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, W, H);

    // 1. Technical Oscilloscope Graticule Grid (matches Mockup 3!)
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.055)';
    ctx.lineWidth = 1;
    const cols = 10, rows = 4;
    for (let c = 1; c < cols; c++) {
      const x = Math.round((c / cols) * W) + 0.5;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, H);
      ctx.stroke();
    }
    for (let r = 1; r < rows; r++) {
      const y = Math.round((r / rows) * H) + 0.5;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(W, y);
      ctx.stroke();
    }
    // Center zero-axis reference hairline
    ctx.strokeStyle = 'rgba(235, 175, 110, 0.14)';
    ctx.beginPath();
    ctx.moveTo(0, Math.round(H / 2) + 0.5);
    ctx.lineTo(W, Math.round(H / 2) + 0.5);
    ctx.stroke();

    // Advance phase & pulse decay
    if (!state.reducedMotion) {
      state.oscPhase += 0.065;
    }
    state.oscPulse *= 0.93;

    const enabled = state.hapticEnabled;
    const baseLevel = Math.max(0.24, state.hapticLevel / 100);
    const normLvl = enabled ? baseLevel : Math.max(0.32, baseLevel * 0.68);
    const midY = H * 0.5;
    const maxAmp = H * 0.42 * (normLvl * 0.88 + state.oscPulse * 0.44);

    // Character profile by active waveform / feel preset
    const wId = state.activeFeelWave;
    const carrierFreq = (wId === 2 || wId === 0 || wId === 6 || wId === 11) ? 44
      : (wId === 3 || wId === 1 || wId === 12) ? 28
      : (wId === 4) ? 34 : 36;
    const modFreq = (wId === 5 || wId === 10 || wId === 13) ? 4.4 : 2.6;

    const sampleY = (u) => {
      const edgeWin = Math.pow(Math.sin(u * Math.PI), 0.52);
      // Multi-packet harmonic acoustic envelope matching Mockup 3
      const p1 = Math.exp(-Math.pow((u - 0.23) / 0.14, 2)) * 0.72;
      const p2 = Math.exp(-Math.pow((u - 0.56) / 0.13, 2)) * (1.08 + state.oscPulse * 0.42);
      const p3 = Math.exp(-Math.pow((u - 0.84) / 0.11, 2)) * 0.62;
      const env = (0.16 + p1 + p2 + p3)
        * (0.78 + 0.22 * Math.sin(u * Math.PI * modFreq - state.oscPhase * 0.7))
        * edgeWin;

      const carrier =
        Math.sin(u * Math.PI * carrierFreq - state.oscPhase * 2.1) * 0.68 +
        Math.sin(u * Math.PI * (carrierFreq * 1.47) + state.oscPhase * 1.2) * 0.24 +
        Math.cos(u * Math.PI * (carrierFreq * 0.52) - state.oscPhase * 0.8) * 0.18;

      return midY + carrier * env * maxAmp;
    };

    const tracePath = () => {
      ctx.beginPath();
      const samples = Math.min(280, W);
      for (let i = 0; i <= samples; i++) {
        const u = i / samples;
        const x = 6 + u * (W - 12);
        const y = sampleY(u);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
    };

    const alphaBoost = enabled ? 1.0 : 0.76;

    // Pass 1: Wide warm copper phosphor bloom
    tracePath();
    ctx.strokeStyle = `rgba(232, 152, 74, ${(0.38 * alphaBoost).toFixed(2)})`;
    ctx.lineWidth = 7.0;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.stroke();

    // Pass 2: Medium glowing amber-gold body
    tracePath();
    ctx.strokeStyle = `rgba(246, 184, 114, ${(0.88 * alphaBoost).toFixed(2)})`;
    ctx.lineWidth = 2.4;
    ctx.stroke();

    // Pass 3: Razor-sharp white-gold filament core
    tracePath();
    ctx.strokeStyle = `rgba(255, 242, 218, ${(0.96 * alphaBoost).toFixed(2)})`;
    ctx.lineWidth = 1.15;
    ctx.stroke();

    ctx.restore();
  };

  requestAnimationFrame(drawFrame);
}

// ─────────────────────────── Top-Layer Dialog Helpers ────────────────────

function setupDialogLightDismissFallback() {
  if ('closedBy' in HTMLDialogElement.prototype) return;
  const outside = (e, dlg) => {
    const r = dlg.getBoundingClientRect();
    return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
  };
  for (const dlg of $$('dialog[closedby="any"]')) {
    let downOut = false;
    dlg.addEventListener('pointerdown', (e) => { downOut = outside(e, dlg); });
    dlg.addEventListener('pointerup', (e) => { if (downOut && outside(e, dlg)) dlg.close(); });
  }
}

// ─────────────────────────── Navigation (View Transitions) ───────────────

function switchTab(nextTab, { force = false } = {}) {
  if (nextTab === state.tab && state.focusedCid == null && !force) return;
  const apply = () => {
    state.tab = nextTab;
    state.focusedCid = null;
    state.recordingFocusKeys = false;
    const focusPanel = $('#control-focus-panel');
    if (focusPanel) focusPanel.hidden = true;

    const indicator = $('.dock-indicator');
    for (const btn of $$('.dock-btn')) {
      const active = btn.dataset.tab === nextTab;
      btn.classList.toggle('is-active', active);
      if (active && indicator) btn.prepend(indicator);
    }
    for (const panel of $$('.tab-panel')) {
      const show = panel.dataset.panel === nextTab;
      panel.hidden = !show;
      panel.classList.toggle('is-active', show);
    }
    $('#stage-pins').innerHTML = '';
    studio3d?.setTab(nextTab);
    if (nextTab === 'ring') renderRingDesigner();
    if (nextTab === 'buttons') renderButtonsList();
    if (nextTab === 'haptics') state.oscPulse = Math.max(state.oscPulse, 0.65);
  };

  const focusHeading = () => {
    const h = $(`#panel-${nextTab} .panel-title`);
    h?.focus({ preventScroll: true });
  };

  if (!document.startViewTransition) {
    apply();
    focusHeading();
    return;
  }
  const vt = document.startViewTransition(apply);
  vt.finished.finally(focusHeading);
}

// ─────────────────────────── Live D-Bus Events ───────────────────────────

function onLiveEvent(name, data) {
  if (name === 'telemetry' && data) {
    studio3d?.applyLiveTelemetry(data);
    return;
  }
  if (name === 'thumbwheel' && data) {
    studio3d?.applyThumbwheelDelta(Number(data.delta || 0), Number(data.direction || 0));
    return;
  }
  if (name === 'buttons' && Array.isArray(data)) {
    studio3d?.setPressedCids(data);
    // Live Haptic Sense Thumb Pad (0x01A0) actuation tester!
    const padHeld = data.includes(CID.THUMB_PAD);
    const meter = $('#pad-live-meter');
    if (meter) {
      meter.classList.toggle('is-pressed', padHeld);
      if (padHeld && !state.padWasHeld) {
        state.padPressCount += 1;
        $('#pad-press-count').textContent = `${state.padPressCount}×`;
        $('#pad-live-text').textContent = 'ACTUATED · Haptic Sense Pad (0x01A0)';
        state.oscPulse = 1.0;
        studio3d?.triggerHapticVisual(state.activeFeelWave);
      } else if (!padHeld && state.padWasHeld) {
        $('#pad-live-text').textContent = 'Press physical Thumb Pad to test actuation force';
      }
    }
    state.padWasHeld = padHeld;
    return;
  }
  if (name === 'profile' && data?.profile) {
    $('#hud-profile').textContent = data.profile;
    if (state.snapshot?.agent) {
      state.snapshot.agent.active_profile = data.profile;
    }
    return;
  }
  if (name === 'state' && state.snapshot) {
    Object.assign(state.snapshot.device, data);
    applySnapshotToUI(state.snapshot, { partial: true });
    return;
  }
  if (name === 'connected' || name === 'disconnected') {
    refreshSnapshot();
  }
}

// ─────────────────────────── Snapshot & Rendering ────────────────────────

async function refreshSnapshot() {
  try {
    const snap = await rpc('getSnapshot');
    state.snapshot = snap;
    applySnapshotToUI(snap);
  } catch (e) {
    $('#live-dot').className = 'live-dot is-offline';
    $('#live-status-text').textContent = 'Daemon offline';
    $('#hud-sub').textContent = e.message;
  }
}

function getBindingForCid(cid, scope = 'global') {
  const cfg = state.snapshot?.config;
  if (!cfg) return { action_type: 'default', action_data: '' };
  const list = scope === 'global'
    ? (cfg.button_bindings || [])
    : (cfg.ring_profiles?.[scope]?.button_overrides || []);
  const found = list.find((b) => Number(b.cid) === Number(cid));
  if (found) return found;
  if (scope === 'global') {
    const hw = (state.snapshot.buttons || []).find((b) => Number(b.cid) === Number(cid));
    if (hw && hw.remap_cid && hw.remap_cid !== hw.cid) {
      return { action_type: 'remap', action_data: String(hw.remap_cid) };
    }
  }
  return { action_type: 'default', action_data: '' };
}

function formatBindingLabel(cid, b) {
  const cfg = state.snapshot?.config;
  const triggerCid = Number(cfg?.daemon?.trigger_cid || CID.THUMB_PAD);
  if (b.action_type === 'default' && Number(cid) === triggerCid && cfg?.daemon?.autostart_gesture) {
    return 'Actions Ring Trigger';
  }
  const base = FRIENDLY_ACTION[b.action_type] || b.action_type;
  if (b.action_type === 'remap' && b.action_data) {
    const meta = BUTTON_META[Number(b.action_data)];
    return `Remap → ${meta ? meta.name : b.action_data}`;
  }
  return b.action_data ? `${base}: ${b.action_data}` : base;
}

function applySnapshotToUI(snap, { partial = false } = {}) {
  const dev = snap.device || {};
  const cfg = snap.config || {};
  const connected = Boolean(dev.connected);

  // Topbar status
  $('#live-dot').className = `live-dot ${connected ? 'is-online' : 'is-offline'}`;
  $('#live-status-text').textContent = connected
    ? `${dev.battery ?? 0}% · ${(dev.connection || 'bolt').toUpperCase()}`
    : (snap.sysd?.running ? 'Mouse asleep' : 'mx4-sysd stopped');

  // Stage HUD
  const mouseName = dev.friendly_name || dev.name || 'MX Master 4';
  $('#hud-mouse-name').textContent = mouseName;
  $('#hud-sub').textContent = connected
    ? `${(dev.connection || 'bolt').toUpperCase()} · FW ${dev.firmware || '—'} · Slot ${(dev.current_host ?? 0) + 1}/${dev.num_hosts || 3}${dev.charging ? ' · Charging' : ''}`
    : 'No MX Master 4 detected · Wake mouse or check Bolt receiver';
  $('#hud-battery').textContent = connected ? `${dev.battery ?? 0}%` : '—';
  $('#hud-dpi').textContent = connected ? `${dev.dpi ?? 1000}` : '—';
  $('#hud-mode').textContent = connected ? (dev.wheel_mode || 'smart').toUpperCase() : '—';
  $('#hud-profile').textContent = snap.agent?.active_profile || 'default';

  // Push hardware telemetry to 3D visualizer
  const fmin = dev.force_min || 4156;
  const fmax = dev.force_max || 6909;
  const fval = dev.force_value || dev.force_default || 5195;
  const forceNorm = fmax > fmin ? (fval - fmin) / (fmax - fmin) : 0.4;

  state.hapticEnabled = dev.haptic_enabled === undefined
    ? (cfg.haptics?.enabled ?? true)
    : Boolean(dev.haptic_enabled);
  state.hapticLevel = Number(dev.haptic_level ?? 65);

  const scCfgEarly = cfg.scroll || {};
  const twCfgEarly = cfg.thumbwheel || {};
  const twModeEarly = dev.thumbwheel_mode || twCfgEarly.mode || (dev.thumbwheel_diverted ? 'actions' : 'native');
  studio3d?.setHardwareState({
    dpi: Number(dev.dpi || 1000),
    scrollMode: dev.wheel_mode || (dev.smartshift ? 'smart' : 'ratchet'),
    smartshiftThreshold: Number(dev.smartshift_threshold ?? 15),
    torque: Number(dev.ratchet_torque ?? 75),
    scrollSpeed: Number(dev.scroll_speed ?? scCfgEarly.scroll_speed ?? 1.0),
    scrollSmoothness: Number(dev.scroll_smoothness ?? scCfgEarly.scroll_smoothness ?? 0),
    scrollAccel: Number(dev.scroll_accel ?? scCfgEarly.scroll_accel ?? 0),
    hiresInvert: Boolean(dev.hires_invert),
    hapticEnabled: state.hapticEnabled,
    hapticLevel: state.hapticLevel,
    activeFeelWave: Number(cfg.haptics?.ring_confirm_pattern ?? state.activeFeelWave),
    forceNorm,
    ringEnabled: Boolean(cfg.daemon?.autostart_gesture ?? true),
    ringCancelRadius: Number(cfg.daemon?.cancel_radius ?? 40),
    connected,
    battery: Number(dev.battery ?? 100),
    charging: Boolean(dev.charging),
    thumbwheelMode: twModeEarly,
  });

  // Remapped CID highlights on 3D mouse
  const remapped = new Set();
  for (const b of snap.buttons || []) {
    if (b.remap_cid && b.remap_cid !== b.cid) remapped.add(Number(b.cid));
  }
  for (const b of cfg.button_bindings || []) {
    if (b.action_type && b.action_type !== 'default') remapped.add(Number(b.cid));
  }
  studio3d?.setRemappedCids(remapped);

  // Device tab: DPI vernier
  const dpi = Number(dev.dpi || 1000);
  $('#dpi-slider').min = String(dev.dpi_min || 200);
  $('#dpi-slider').max = String(dev.dpi_max || 8000);
  $('#dpi-slider').step = String(dev.dpi_step || 50);
  $('#dpi-slider').value = String(dpi);
  $('#dpi-readout').textContent = String(dpi);
  for (const chip of $$('#dpi-chips .studio-chip')) {
    chip.classList.toggle('is-active', Number(chip.dataset.dpi) === dpi);
  }
  if (!partial && cfg.pointer?.dpi_presets) {
    $('#dpi-cycle-input').value = cfg.pointer.dpi_presets.join(', ');
    renderDpiStageMarkers(cfg.pointer.dpi_presets);
  }

  // Easy-Switch hosts
  if (!partial) renderHosts(snap.hosts || []);

  // Scroll tab
  const mode = dev.wheel_mode || (dev.smartshift ? 'smart' : 'ratchet');
  for (const pill of $$('.mode-pill')) {
    pill.classList.toggle('is-active', pill.dataset.scrollMode === mode);
  }
  const thr = Number(dev.smartshift_threshold ?? 15);
  $('#ss-thr-slider').value = String(thr);
  $('#ss-thr-readout').textContent = String(thr);
  updateVernierFill('#ss-thr-slider', '#ss-vernier-fill');
  $('#card-smartshift-thr').style.opacity = mode === 'smart' ? '1' : '0.52';

  const tq = Number(dev.ratchet_torque ?? 75);
  setTorqueUI(tq);
  $('#card-torque').hidden = dev.tunable_torque === false;

  // HD Smooth Scroll Engine (0x2121 · 144 Hz)
  const scCfg = cfg.scroll || {};
  const sp = Number(dev.scroll_speed ?? scCfg.scroll_speed ?? 1.0);
  const sm = Number(dev.scroll_smoothness ?? scCfg.scroll_smoothness ?? 0);
  const ac = Number(dev.scroll_accel ?? scCfg.scroll_accel ?? 0);
  updateScrollTuningUI(sp, sm, ac, Boolean(dev.hires_diverted));

  $('#sw-hires').checked = Boolean(dev.hires_enabled);
  $('#sw-hires-invert').checked = Boolean(dev.hires_invert);

  const twCfg = cfg.thumbwheel || {};
  const twMode = dev.thumbwheel_mode || twCfg.mode || (dev.thumbwheel_diverted ? 'actions' : 'native');
  updateThumbwheelUI({
    mode: twMode,
    invert: Boolean(dev.thumbwheel_invert ?? twCfg.invert),
    speed: Number(dev.thumbwheel_speed ?? twCfg.speed ?? 1.0),
    smoothness: Number(dev.thumbwheel_smoothness ?? twCfg.smoothness ?? 35),
    accel: Number(dev.thumbwheel_accel ?? twCfg.accel ?? 25),
    hires: dev.thumbwheel_hires === undefined ? (twCfg.hires !== false) : Boolean(dev.thumbwheel_hires),
    haptic_detent: Boolean(dev.thumbwheel_haptic_detent ?? twCfg.haptic_detent),
    haptic_density: Number(dev.thumbwheel_haptic_density ?? twCfg.haptic_density ?? 6),
    haptic_pattern: Number(dev.thumbwheel_haptic_pattern ?? twCfg.haptic_pattern ?? 1),
    engineActive: dev.thumbwheel_engine_active,
    nativeRes: Number(dev.thumbwheel_native_res || 20),
    divertedRes: Number(dev.thumbwheel_diverted_res || 120),
  });

  if (!partial && cfg.thumbwheel) {
    const tw = cfg.thumbwheel;
    const presetSel = $('#tw-preset');
    if (presetSel.options.length === 0 && snap.thumbwheel_presets) {
      for (const [k, info] of Object.entries(snap.thumbwheel_presets)) {
        presetSel.add(new Option(info.label, k));
      }
    }
    presetSel.value = tw.preset || 'tabs';
    $('#tw-pos-type').value = tw.positive_type || 'keystroke';
    $('#tw-pos-data').value = tw.positive_data || '';
    $('#tw-neg-type').value = tw.negative_type || 'keystroke';
    $('#tw-neg-data').value = tw.negative_data || '';
    const stVal = Math.max(1, Math.min(120, Number(tw.step || 16)));
    $('#tw-step-slider').value = String(stVal);
    $('#tw-step-readout').textContent = formatTwStepLabel(stVal);
    $('#sw-tw-haptic').checked = Boolean(tw.haptic_tick);
    if ($('#sw-tw-micro-haptics')) $('#sw-tw-micro-haptics').checked = tw.micro_haptics !== false;
    if ($('#tw-action-pattern')) $('#tw-action-pattern').value = String(tw.haptic_pattern ?? 1);
  }

  // Haptics tab
  $('#sw-haptic-motor').checked = state.hapticEnabled;
  $('#haptic-strength-wrap').style.opacity = state.hapticEnabled ? '1' : '0.45';
  $('#haptic-lvl-slider').value = String(state.hapticLevel);
  $('#haptic-strength-word').textContent = hapticStrengthWord(state.hapticLevel, state.hapticEnabled);
  $('#haptic-lvl-pct').textContent = `${state.hapticLevel}%`;
  updateVernierFill('#haptic-lvl-slider', '#haptic-vernier-fill');

  if (dev.force_supported === false) {
    $('#card-force-pad').hidden = true;
  } else {
    $('#card-force-pad').hidden = false;
    $('#force-slider').min = String(fmin);
    $('#force-slider').max = String(fmax);
    $('#force-slider').value = String(fval);
    updateForceReadout(fval, fmin, fmax, dev.force_default || 5195);
    updateVernierFill('#force-slider', '#force-vernier-fill');
  }

  if (!partial && cfg.haptics) {
    const h = cfg.haptics;
    $('#sel-ring-boundary').value = String(h.ring_boundary_pattern ?? 1);
    $('#sel-ring-confirm').value = String(h.ring_confirm_pattern ?? 2);
    $('#sel-ring-cancel').value = String(h.ring_cancel_pattern ?? 0);
    $('#sw-notif-haptic').checked = Boolean(h.notification_enabled);
    $('#sel-notif-pattern').value = String(h.notification_pattern ?? 5);
    for (const wc of $$('.wave-card')) {
      wc.classList.toggle('is-active', Number(wc.dataset.waveId) === Number(h.ring_confirm_pattern));
    }
  }

  // Ring tab
  if (!partial && cfg.daemon) {
    $('#sw-ring-enabled').checked = Boolean(cfg.daemon.autostart_gesture);
    $('#sel-ring-trigger').value = String(cfg.daemon.trigger_cid || CID.THUMB_PAD);
    $('#dz-slider').value = String(cfg.daemon.cancel_radius || 40);
    $('#dz-readout').textContent = String(cfg.daemon.cancel_radius || 40);

    state.ringThemeId = cfg.daemon.ring_theme || 'studio';
    state.ringSizeId = cfg.daemon.ring_size || 'standard';
    state.ringShowHints = cfg.daemon.ring_show_hints !== false;
    state.ringAnimate = cfg.daemon.ring_animate !== false;

    if ($('#sw-ring-hints')) $('#sw-ring-hints').checked = state.ringShowHints;
    if ($('#sw-ring-animate')) $('#sw-ring-animate').checked = state.ringAnimate;
    for (const pill of $$('#ring-size-pills .mode-pill')) {
      pill.classList.toggle('is-active', pill.dataset.ringSize === state.ringSizeId);
    }

    syncRingAppearanceTo3D({ pulse: false });
    rebuildProfileSelectors();
    renderRingThemes();
    renderRingPresets();
    renderRingDesigner();
  }

  // Buttons & Lab tabs
  if (!partial) {
    renderButtonsList();
    renderDiagnostics(snap);
  }
}

function updateForceReadout(val, min, max, def) {
  const pct = max > min ? Math.round(((val - min) / (max - min)) * 100) : 50;
  const tag = Math.abs(val - def) <= 15 ? ' (Default)' : '';
  $('#force-readout').textContent = `${pct}%${tag}`;
  $('#force-raw-text').textContent = `Raw sensor: ${val}  (${min}–${max})`;
  for (const chip of $$('#force-preset-chips .studio-chip')) {
    chip.classList.toggle('is-active', Math.abs(Number(chip.dataset.forceVal) - val) <= 60);
  }
}

function renderHosts(hosts) {
  const box = $('#hosts-stack');
  box.innerHTML = '';
  for (const h of hosts) {
    const card = document.createElement('div');
    card.className = `host-card ${h.current ? 'is-current' : ''} ${!h.paired ? 'is-empty' : ''}`;
    const name = h.name || (h.paired ? `Slot ${h.index + 1}` : 'Empty');
    card.innerHTML = `
      <div class="host-top">
        <span class="host-slot">SLOT ${h.index + 1}</span>
        ${h.paired && h.bus_label ? `<span class="host-bus">${h.bus_label}</span>` : ''}
      </div>
      <div class="host-name" title="${name}">${name}</div>
      <div class="host-foot"></div>
    `;
    const foot = card.querySelector('.host-foot');
    if (h.current) {
      const tag = document.createElement('span');
      tag.className = 'host-active-tag';
      tag.textContent = '● ACTIVE';
      foot.appendChild(tag);
    } else if (h.paired) {
      const sw = document.createElement('button');
      sw.type = 'button';
      sw.className = 'btn-secondary sm';
      sw.textContent = 'Switch';
      sw.addEventListener('click', async () => {
        try {
          await rpc('switchHost', { index: h.index });
          toast(`Switching mouse to Slot ${h.index + 1} (${name})`);
          setTimeout(refreshSnapshot, 600);
        } catch (e) { toast(e.message); }
      });
      foot.appendChild(sw);
    } else {
      const empty = document.createElement('span');
      empty.className = 'card-sub';
      empty.textContent = 'unpaired';
      foot.appendChild(empty);
    }
    if (h.paired && h.can_rename) {
      const ren = document.createElement('button');
      ren.type = 'button';
      ren.className = 'btn-secondary sm';
      ren.textContent = 'Rename';
      ren.addEventListener('click', () => openPromptDialog({
        title: `Rename Slot ${h.index + 1}`,
        desc: 'Stored inside the MX Master 4 HOSTS_INFO memory (max 24 chars).',
        label: 'HOST NAME',
        initial: name,
        maxLength: 24,
        onSave: async (newName) => {
          await rpc('renameHost', { index: h.index, name: newName });
          toast(`Slot ${h.index + 1} renamed to ${newName}`);
          await refreshSnapshot();
        },
      }));
      foot.appendChild(ren);
    }
    box.appendChild(card);
  }
}

// ─────────────────────────── Actions Ring Designer ───────────────────────

function rebuildProfileSelectors() {
  const profs = state.snapshot?.config?.ring_profiles || {};
  const ids = ['default', ...Object.keys(profs).filter((k) => k !== 'default').sort()];
  if (!ids.includes(state.ringProfileId)) state.ringProfileId = 'default';

  const ringSel = $('#sel-ring-profile');
  ringSel.innerHTML = '';
  for (const id of ids) {
    const label = id === 'default' ? 'Default (All Applications)' : `${profs[id].app_name} (${id})`;
    ringSel.add(new Option(label, id));
  }
  ringSel.value = state.ringProfileId;
  $('#btn-del-profile').disabled = state.ringProfileId === 'default';

  const scopeSel = $('#sel-button-scope');
  scopeSel.innerHTML = '';
  scopeSel.add(new Option('Global (All Applications)', 'global'));
  for (const id of ids.filter((k) => k !== 'default')) {
    scopeSel.add(new Option(`App Override: ${profs[id].app_name} (${id})`, id));
  }
  if (!['global', ...ids].includes(state.buttonScope)) state.buttonScope = 'global';
  scopeSel.value = state.buttonScope;
}

function getActiveRingTheme() {
  const list = state.snapshot?.ring_themes || [];
  return list.find((t) => t.id === state.ringThemeId) || list[0] || {
    id: 'studio',
    name: 'Studio Copper',
    accent: '#e8a864',
    accent_bright: '#ffe0b2',
    secondary: '#3ce0e8',
    bg_outer: '#0a0d14',
    bg_ring: '#121722',
    bg_core: '#0c1018',
    seg_idle: '#18202e',
    seg_hover: '#2e2318',
    border: '#334057',
    text: '#f5f7fc',
    text_sub: '#95a3ba',
    cancel: '#f06e6e',
  };
}

function getActiveRingSize() {
  const list = state.snapshot?.ring_sizes || [];
  return list.find((s) => s.id === state.ringSizeId) || { id: 'standard', label: 'Standard', scale_3d: 1.0 };
}

function syncRingAppearanceTo3D({ pulse = false } = {}) {
  const theme = getActiveRingTheme();
  const sizeSpec = getActiveRingSize();
  const panel = $('#panel-ring');
  if (panel) {
    panel.style.setProperty('--ring-accent', theme.accent);
    panel.style.setProperty('--ring-bright', theme.accent_bright);
    panel.style.setProperty('--ring-secondary', theme.secondary);
    panel.style.setProperty('--ring-seg-idle', theme.seg_idle);
    panel.style.setProperty('--ring-seg-hover', theme.seg_hover);
    panel.style.setProperty('--ring-border', theme.border);
    panel.style.setProperty('--ring-text', theme.text);
    panel.style.setProperty('--ring-text-sub', theme.text_sub);
  }
  const readout = $('#ring-theme-readout');
  if (readout) readout.textContent = theme.name || 'Studio Copper';

  studio3d?.setRingAppearance({
    theme,
    sizeScale: Number(sizeSpec.scale_3d || 1.0),
    enabled: Boolean($('#sw-ring-enabled')?.checked ?? true),
    cancelRadius: Number($('#dz-slider')?.value || 40),
    animate: Boolean(state.ringAnimate),
    pulse,
  });
}

function formatSliceHint(seg) {
  const at = (seg.action_type || '').toLowerCase();
  const ad = (seg.action_data || '').trim();
  if (at === 'disabled') return 'Off';
  if (at === 'dpi_cycle') return 'DPI Cycle';
  if (at === 'smartshift_toggle') return 'MagSpeed';
  if (at === 'host_next') return 'Easy-Switch';
  if (at === 'haptic') return `Wave #${ad || '2'}`;
  if (at === 'keystroke' && ad) {
    return ad
      .replace(/ctrl/gi, 'Ctrl')
      .replace(/shift/gi, 'Shft')
      .replace(/alt/gi, 'Alt')
      .slice(0, 11);
  }
  if (at === 'command' && ad) {
    if (ad.includes('grim')) return 'Capture';
    if (ad.includes('workspace +1')) return 'WS →';
    if (ad.includes('workspace -1')) return '← WS';
    if (ad.includes('fullscreen')) return 'Full';
    if (ad.includes('togglefloating')) return 'Float';
    if (ad.includes('killactive')) return 'Kill';
    if (ad.includes('playerctl')) return 'MPRIS';
    if (ad.includes('wpctl')) return 'PipeWire';
    return ad.split(/\s+/)[0].slice(0, 10);
  }
  return '';
}

function renderRingThemes() {
  const grid = $('#ring-theme-grid');
  if (!grid) return;
  const themes = state.snapshot?.ring_themes || [];
  grid.innerHTML = '';
  for (const t of themes) {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = `ring-theme-card ${t.id === state.ringThemeId ? 'is-active' : ''}`;
    card.style.setProperty('--theme-accent', t.accent);
    card.style.setProperty('--theme-bright', t.accent_bright);
    card.style.setProperty('--theme-secondary', t.secondary);
    card.style.setProperty('--theme-bg', t.bg_ring);
    card.innerHTML = `
      <span class="ring-theme-orb" aria-hidden="true"></span>
      <span class="ring-theme-meta">
        <span class="ring-theme-name">${t.name}</span>
        <span class="ring-theme-tag">${t.tagline}</span>
      </span>
    `;
    card.addEventListener('click', () => {
      state.ringThemeId = t.id;
      if (state.snapshot?.config?.daemon) state.snapshot.config.daemon.ring_theme = t.id;
      syncRingAppearanceTo3D({ pulse: true });
      renderRingThemes();
      renderRingDesigner();
      rpc('saveRingSettings', { ring_theme: t.id })
        .then(() => toast(`Ring theme → ${t.name}`))
        .catch((e) => toast(e.message));
    });
    grid.appendChild(card);
  }
}

function renderRingPresets() {
  const grid = $('#ring-preset-grid');
  if (!grid) return;
  const presets = state.snapshot?.ring_presets || [];
  const prof = state.snapshot?.config?.ring_profiles?.[state.ringProfileId];
  const targetLabel = $('#ring-preset-target');
  if (targetLabel) {
    targetLabel.textContent = `→ ${prof ? prof.app_name : state.ringProfileId}`;
  }

  // Detect if current profile's 8 slice labels match one of the presets
  const curSig = (prof?.slices || []).map((s) => `${s.label}:${s.action_type}`).join('|');

  grid.innerHTML = '';
  for (const p of presets) {
    const pSig = (p.slices || []).map((s) => `${s.label}:${s.action_type}`).join('|');
    const isMatch = curSig && curSig === pSig;
    const card = document.createElement('button');
    card.type = 'button';
    card.className = `ring-preset-card ${isMatch ? 'is-active' : ''}`;
    const previewLabels = (p.slices || []).slice(0, 4).map((s) => s.label).join(' · ');
    card.innerHTML = `
      <div class="ring-preset-top">
        <span class="ring-preset-name">${p.name}</span>
        <span class="ring-preset-badge">${p.badge || 'PRESET'}</span>
      </div>
      <div class="ring-preset-desc">${p.tagline}</div>
      <div class="ring-preset-slices">${previewLabels}…</div>
    `;
    card.addEventListener('click', async () => {
      try {
        await rpc('applyRingPreset', { profile_id: state.ringProfileId, preset_id: p.id });
        studio3d?.triggerRingConfirmPulse();
        toast(`Applied "${p.name}" preset to ${prof?.app_name || state.ringProfileId}`);
        await refreshSnapshot();
      } catch (e) { toast(e.message); }
    });
    grid.appendChild(card);
  }
}

function renderRingDesigner() {
  const prof = state.snapshot?.config?.ring_profiles?.[state.ringProfileId];
  if (!prof) return;
  const theme = getActiveRingTheme();
  const svg = $('#ring-svg');
  svg.innerHTML = '';

  const cx = 160, cy = 160, rOut = 136, rIn = 52;
  const ns = 'http://www.w3.org/2000/svg';

  // Outer frosted housing halo + precision vernier ring
  const bg = document.createElementNS(ns, 'circle');
  bg.setAttribute('cx', String(cx));
  bg.setAttribute('cy', String(cy));
  bg.setAttribute('r', '152');
  bg.setAttribute('fill', theme.bg_ring);
  bg.setAttribute('fill-opacity', '0.88');
  bg.setAttribute('stroke', theme.border);
  bg.setAttribute('stroke-width', '1.4');
  svg.appendChild(bg);

  // 32 precision outer vernier telemetry ticks
  for (let k = 0; k < 32; k++) {
    const a = -Math.PI / 2 + (k * Math.PI * 2) / 32;
    const major = k % 4 === 0;
    const r0 = 141, r1 = major ? 149 : 145.5;
    const line = document.createElementNS(ns, 'line');
    line.setAttribute('x1', String(cx + Math.cos(a) * r0));
    line.setAttribute('y1', String(cy + Math.sin(a) * r0));
    line.setAttribute('x2', String(cx + Math.cos(a) * r1));
    line.setAttribute('y2', String(cy + Math.sin(a) * r1));
    line.setAttribute('stroke', major ? theme.secondary : theme.border);
    line.setAttribute('stroke-opacity', major ? '0.78' : '0.45');
    line.setAttribute('stroke-width', major ? '1.6' : '1.0');
    svg.appendChild(line);
  }

  for (let i = 0; i < 8; i++) {
    const seg = prof.slices[i] || { label: '', action_type: 'disabled', action_data: '' };
    const isSel = i === state.ringSliceIdx;
    const mid = -Math.PI / 2 + (i * Math.PI * 2) / 8;
    const half = Math.PI / 8 - 0.036;
    const a1 = mid - half, a2 = mid + half;
    const sOut = isSel ? rOut + 5 : rOut;
    const sIn = isSel ? rIn + 1.5 : rIn;

    const x1 = cx + Math.cos(a1) * sOut, y1 = cy + Math.sin(a1) * sOut;
    const x2 = cx + Math.cos(a2) * sOut, y2 = cy + Math.sin(a2) * sOut;
    const x3 = cx + Math.cos(a2) * sIn,  y3 = cy + Math.sin(a2) * sIn;
    const x4 = cx + Math.cos(a1) * sIn,  y4 = cy + Math.sin(a1) * sIn;

    const path = document.createElementNS(ns, 'path');
    path.setAttribute('d', `M ${x1} ${y1} A ${sOut} ${sOut} 0 0 1 ${x2} ${y2} L ${x3} ${y3} A ${sIn} ${sIn} 0 0 0 ${x4} ${y4} Z`);
    path.setAttribute('class', `ring-slice-path ${isSel ? 'is-selected' : ''}`);
    path.addEventListener('click', () => {
      state.ringSliceIdx = i;
      studio3d?.setSelectedRingSlice(i);
      renderRingDesigner();
    });
    svg.appendChild(path);

    // Luminous outer accent arc on the selected slice!
    if (isSel) {
      const ar = sOut - 2;
      const ax1 = cx + Math.cos(a1 + 0.04) * ar, ay1 = cy + Math.sin(a1 + 0.04) * ar;
      const ax2 = cx + Math.cos(a2 - 0.04) * ar, ay2 = cy + Math.sin(a2 - 0.04) * ar;
      const arc = document.createElementNS(ns, 'path');
      arc.setAttribute('d', `M ${ax1} ${ay1} A ${ar} ${ar} 0 0 1 ${ax2} ${ay2}`);
      arc.setAttribute('fill', 'none');
      arc.setAttribute('stroke', theme.accent_bright);
      arc.setAttribute('stroke-width', '3.2');
      arc.setAttribute('stroke-linecap', 'round');
      arc.setAttribute('pointer-events', 'none');
      svg.appendChild(arc);
    }

    const lr = (sIn + sOut) / 2;
    const tx = cx + Math.cos(mid) * lr;
    const ty = cy + Math.sin(mid) * lr;
    const hint = state.ringShowHints ? formatSliceHint(seg) : '';

    const txt = document.createElementNS(ns, 'text');
    txt.setAttribute('x', String(tx));
    txt.setAttribute('y', String(hint ? ty - 5 : ty));
    txt.setAttribute('class', 'ring-slice-label');
    if (isSel) txt.setAttribute('fill', theme.accent_bright);
    txt.textContent = (seg.label || `Slice ${i + 1}`).slice(0, 10);
    svg.appendChild(txt);

    if (hint) {
      const sub = document.createElementNS(ns, 'text');
      sub.setAttribute('x', String(tx));
      sub.setAttribute('y', String(ty + 8));
      sub.setAttribute('class', 'ring-slice-hint');
      if (isSel) sub.setAttribute('fill', theme.accent);
      sub.textContent = hint;
      svg.appendChild(sub);
    }
  }

  // Center core hub + deadzone ring preview + live magnetic compass pointer!
  const hub = document.createElementNS(ns, 'circle');
  hub.setAttribute('cx', String(cx));
  hub.setAttribute('cy', String(cy));
  hub.setAttribute('r', '45');
  hub.setAttribute('fill', theme.bg_core);
  hub.setAttribute('stroke', theme.accent);
  hub.setAttribute('stroke-width', '1.6');
  svg.appendChild(hub);

  const dzVal = Number($('#dz-slider')?.value || 40);
  const dzR = Math.max(16, Math.min(41, (dzVal / 80) * 41));
  const dzRing = document.createElementNS(ns, 'circle');
  dzRing.setAttribute('cx', String(cx));
  dzRing.setAttribute('cy', String(cy));
  dzRing.setAttribute('r', String(dzR));
  dzRing.setAttribute('fill', 'none');
  dzRing.setAttribute('stroke', theme.secondary);
  dzRing.setAttribute('stroke-opacity', '0.52');
  dzRing.setAttribute('stroke-dasharray', '3 3');
  dzRing.setAttribute('stroke-width', '1.2');
  svg.appendChild(dzRing);

  // Magnetic compass tether + pointer aiming at selected slice
  const selAng = -Math.PI / 2 + (state.ringSliceIdx * Math.PI * 2) / 8;
  const tether = document.createElementNS(ns, 'line');
  tether.setAttribute('x1', String(cx));
  tether.setAttribute('y1', String(cy));
  tether.setAttribute('x2', String(cx + Math.cos(selAng) * 38));
  tether.setAttribute('y2', String(cy + Math.sin(selAng) * 38));
  tether.setAttribute('stroke', theme.accent_bright);
  tether.setAttribute('stroke-width', '2.0');
  tether.setAttribute('stroke-linecap', 'round');
  svg.appendChild(tether);

  const tipX = cx + Math.cos(selAng) * 51;
  const tipY = cy + Math.sin(selAng) * 51;
  const b1X = cx + Math.cos(selAng - 0.16) * 43;
  const b1Y = cy + Math.sin(selAng - 0.16) * 43;
  const b2X = cx + Math.cos(selAng + 0.16) * 43;
  const b2Y = cy + Math.sin(selAng + 0.16) * 43;
  const needle = document.createElementNS(ns, 'polygon');
  needle.setAttribute('points', `${tipX},${tipY} ${b1X},${b1Y} ${b2X},${b2Y}`);
  needle.setAttribute('fill', theme.accent_bright);
  svg.appendChild(needle);

  const core = document.createElementNS(ns, 'circle');
  core.setAttribute('cx', String(cx));
  core.setAttribute('cy', String(cy));
  core.setAttribute('r', '6.5');
  core.setAttribute('fill', theme.accent);
  svg.appendChild(core);

  const cur = prof.slices[state.ringSliceIdx] || { label: '', action_type: 'keystroke', action_data: '' };
  $('#slice-heading').textContent = `Slice ${state.ringSliceIdx + 1} · ${prof.app_name}`;
  $('#slice-label').value = cur.label || '';
  $('#slice-type').value = cur.action_type || 'keystroke';
  $('#slice-data').value = cur.action_data || '';
  const needsPayload = ['keystroke', 'command', 'application', 'haptic'].includes(cur.action_type);
  $('#slice-data').disabled = !needsPayload;
  studio3d?.setSelectedRingSlice(state.ringSliceIdx);
}

// ─────────────────────────── Buttons List & Rebind Modal ─────────────────

function formatThumbwheelSummary() {
  const dev = state.snapshot?.device || {};
  const tw = state.snapshot?.config?.thumbwheel || {};
  const mode = state.twMode || dev.thumbwheel_mode || tw.mode || (dev.thumbwheel_diverted ? 'actions' : 'native');
  if (mode === 'hd_scroll') {
    const sp = Number(state.twSpeed ?? dev.thumbwheel_speed ?? tw.speed ?? 1.0).toFixed(2);
    return `6× HD Scroll · ${sp}×`;
  }
  if (mode === 'actions') {
    return state.snapshot?.thumbwheel_presets?.[tw.preset]?.label || 'Custom Actions';
  }
  return 'Native Horizontal Scroll (1×)';
}

function renderButtonsList() {
  const list = $('#buttons-list');
  list.innerHTML = '';
  const hwMap = new Map((state.snapshot?.buttons || []).map((b) => [Number(b.cid), b]));

  for (const [cid, name, desc] of ALL_CONTROLS) {
    const isThumbWheel = cid === CID.THUMB_WHEEL;
    const hw = hwMap.get(cid);
    const editable = isThumbWheel || Boolean(hw && (hw.divertable || hw.remappable));
    const binding = getBindingForCid(cid, state.buttonScope);
    const label = isThumbWheel
      ? formatThumbwheelSummary()
      : formatBindingLabel(cid, binding);

    const row = document.createElement('div');
    row.className = 'control-row';
    row.innerHTML = `
      <div class="control-info">
        <div class="control-title-row">
          <strong>${name}</strong>
          <span class="cid-pill">0x${cid.toString(16).toUpperCase().padStart(4, '0')}</span>
        </div>
        <span class="card-sub">${desc}</span>
      </div>
      <div class="btn-group">
        <span class="binding-pill">${label}</span>
        <button type="button" class="btn-secondary sm">${editable ? 'Focus & Edit' : 'Inspect'}</button>
      </div>
    `;
    const btn = row.querySelector('button');
    btn.addEventListener('click', () => openControlInspector(cid));
    list.appendChild(row);
  }
}

/**
 * Click ANY physical button, clicker, scroll wheel, thumb wheel, or thumb pad on the 3D mouse:
 *   1. Smoothly zooms the 3D camera directly onto THAT exact clicked control!
 *   2. Opens its dedicated direct settings inspector right in the right pane!
 */
function openControlInspector(cid) {
  const numCid = Number(cid);
  state.focusedCid = numCid;
  state.recordingFocusKeys = false;
  if ($('#btn-focus-record')) $('#btn-focus-record').textContent = 'Record';

  // Zoom 3D camera directly onto the clicked control!
  studio3d?.focusControl(numCid);

  // Hide standard tab panels and show the direct focused control panel
  for (const panel of $$('.tab-panel')) {
    panel.hidden = true;
    panel.classList.remove('is-active');
  }
  const focusPanel = $('#control-focus-panel');
  focusPanel.hidden = false;
  $('#inspector-pane').scrollTop = 0;

  const meta = BUTTON_META[numCid] || { name: `Control 0x${numCid.toString(16).toUpperCase()}` };
  const ctrlInfo = ALL_CONTROLS.find(([c]) => Number(c) === numCid);
  const hexCid = `0x${numCid.toString(16).toUpperCase().padStart(4, '0')}`;

  $('#focus-cid-pill').textContent = hexCid;
  $('#focus-title').textContent = meta.name;
  $('#focus-desc').textContent = ctrlInfo ? ctrlInfo[2] : 'Direct hardware control configuration.';

  const isThumbWheel = numCid === CID.THUMB_WHEEL;
  const bindingCard = $('#focus-binding-card');
  const twCard = $('#focus-thumbwheel-card');
  const ctxCard = $('#focus-context-card');

  bindingCard.hidden = isThumbWheel;
  twCard.hidden = !isThumbWheel;

  if (isThumbWheel) {
    // Sync Direct Horizontal Thumb Wheel controls (0x2150) while camera stays zoomed on Thumb Wheel!
    const dev = state.snapshot?.device || {};
    const tw = state.snapshot?.config?.thumbwheel || {};
    const twMode = state.twMode || dev.thumbwheel_mode || tw.mode || (dev.thumbwheel_diverted ? 'actions' : 'native');
    updateThumbwheelUI({
      mode: twMode,
      invert: Boolean(dev.thumbwheel_invert ?? tw.invert),
      speed: Number(state.twSpeed ?? dev.thumbwheel_speed ?? tw.speed ?? 1.0),
      smoothness: Number(state.twSmoothness ?? dev.thumbwheel_smoothness ?? tw.smoothness ?? 35),
      accel: Number(state.twAccel ?? dev.thumbwheel_accel ?? tw.accel ?? 25),
      hires: dev.thumbwheel_hires === undefined ? (tw.hires !== false) : Boolean(dev.thumbwheel_hires),
      haptic_detent: Boolean(dev.thumbwheel_haptic_detent ?? tw.haptic_detent),
      haptic_density: Number(state.twHapticDensity ?? dev.thumbwheel_haptic_density ?? tw.haptic_density ?? 6),
      haptic_pattern: Number(state.twHapticPattern ?? dev.thumbwheel_haptic_pattern ?? tw.haptic_pattern ?? 1),
      engineActive: dev.thumbwheel_engine_active,
      nativeRes: Number(dev.thumbwheel_native_res || 20),
      divertedRes: Number(dev.thumbwheel_diverted_res || 120),
    });

    const pSel = $('#focus-tw-preset');
    if (pSel.options.length === 0 && state.snapshot?.thumbwheel_presets) {
      for (const [k, info] of Object.entries(state.snapshot.thumbwheel_presets)) {
        pSel.add(new Option(info.label, k));
      }
    }
    pSel.value = tw.preset || 'tabs';
    $('#focus-tw-pos-type').value = tw.positive_type || 'keystroke';
    $('#focus-tw-pos-data').value = tw.positive_data || '';
    $('#focus-tw-neg-type').value = tw.negative_type || 'keystroke';
    $('#focus-tw-neg-data').value = tw.negative_data || '';
    const stVal = Math.max(1, Math.min(120, Number(tw.step || 16)));
    $('#focus-tw-step').value = String(stVal);
    $('#focus-tw-step-readout').textContent = formatTwStepLabel(stVal);
    $('#focus-tw-haptic').checked = Boolean(tw.haptic_tick);
    if ($('#focus-tw-micro-haptics')) $('#focus-tw-micro-haptics').checked = tw.micro_haptics !== false;
    if ($('#focus-tw-action-pattern')) $('#focus-tw-action-pattern').value = String(tw.haptic_pattern ?? 1);
  } else {
    // Populate profile scope dropdown
    const scopeSel = $('#focus-scope-sel');
    scopeSel.innerHTML = '';
    scopeSel.add(new Option('Global (All Applications)', 'global'));
    for (const [appId, prof] of Object.entries(state.snapshot?.config?.ring_profiles || {})) {
      if (appId === 'default') continue;
      scopeSel.add(new Option(`App Override: ${prof.app_name || appId}`, appId));
    }
    scopeSel.value = state.buttonScope;

    const hw = (state.snapshot?.buttons || []).find((b) => Number(b.cid) === numCid);
    const locked = Boolean(hw && !hw.divertable && !hw.remappable);
    const cur = getBindingForCid(numCid, state.buttonScope);

    $('#focus-current-badge').textContent = formatBindingLabel(numCid, cur);
    $('#focus-locked-note').hidden = !locked;
    $('#focus-binding-editor').hidden = locked;

    if (!locked) {
      $('#focus-action-type').value = cur.action_type || 'default';
      $('#focus-action-data').value = cur.action_type !== 'remap' ? (cur.action_data || '') : '';
      if (cur.action_type === 'remap' && cur.action_data) {
        $('#focus-remap-target').value = cur.action_data;
      }
      syncFocusBindingFields();
    }
  }

  // Contextual Hardware Engine Quick-Jump Card (without stealing camera until clicked!)
  const ctxActions = $('#focus-ctx-actions');
  ctxActions.innerHTML = '';
  const addJumpBtn = (label, targetTab, isPrimary = false) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = isPrimary ? 'btn-primary sm' : 'btn-secondary sm';
    b.textContent = label;
    b.addEventListener('click', () => switchTab(targetTab, { force: true }));
    ctxActions.appendChild(b);
  };

  if (numCid === CID.MIDDLE_CLICK) {
    ctxCard.hidden = false;
    $('#focus-ctx-label').textContent = 'MAGSPEED ENGINE · 0x2111 / 0x2121';
    $('#focus-ctx-title').textContent = 'MagSpeed & HD Smooth Scroll';
    $('#focus-ctx-desc').textContent = 'Tune SmartShift disengage velocity, Precision Shift torque curve, and 144 Hz HD smooth scrolling.';
    addJumpBtn('Open MagSpeed Dynamics', 'scroll', true);
  } else if (numCid === CID.THUMB_PAD) {
    ctxCard.hidden = false;
    $('#focus-ctx-label').textContent = 'HAPTIC SENSE PAD · 0x19C0 / 0x01A0';
    $('#focus-ctx-title').textContent = 'Force Sensor & Actions Ring';
    $('#focus-ctx-desc').textContent = 'Customize the 8-slice Wayland Actions Ring overlay or tune actuation force & LRA haptic waveforms.';
    addJumpBtn('Open Actions Ring', 'ring', true);
    addJumpBtn('Force & Haptics', 'haptics', false);
  } else if (numCid === CID.SMART_SHIFT) {
    ctxCard.hidden = false;
    $('#focus-ctx-label').textContent = 'SMARTSHIFT CLUTCH · 0x2111';
    $('#focus-ctx-title').textContent = 'Wheel Clutch Dynamics';
    $('#focus-ctx-desc').textContent = 'By default Mode-Shift switches between Ratchet and Free-Spin. Tune clutch torque & threshold in Scroll.';
    addJumpBtn('Open Scroll Dynamics', 'scroll', false);
  } else if (numCid === CID.LEFT_CLICK || numCid === CID.RIGHT_CLICK) {
    ctxCard.hidden = false;
    $('#focus-ctx-label').textContent = 'DARKFIELD 8K SENSOR · 0x2201';
    $('#focus-ctx-title').textContent = 'Pointer Sensitivity & Hosts';
    $('#focus-ctx-desc').textContent = 'Adjust pointer DPI sensitivity, cycle stages, and Easy-Switch host slots.';
    addJumpBtn('Open Pointer Settings', 'device', false);
  } else {
    ctxCard.hidden = true;
  }
}

function closeControlInspector() {
  if (state.focusedCid == null) return;
  state.focusedCid = null;
  state.recordingFocusKeys = false;
  $('#control-focus-panel').hidden = true;
  for (const panel of $$('.tab-panel')) {
    const show = panel.dataset.panel === state.tab;
    panel.hidden = !show;
    panel.classList.toggle('is-active', show);
  }
  studio3d?.clearFocusedControl();
  if (state.tab === 'buttons') renderButtonsList();
}

function syncFocusBindingFields() {
  const t = $('#focus-action-type').value;
  const needsText = ['keystroke', 'key_hold', 'command', 'application', 'dpi_set', 'haptic'].includes(t);
  $('#focus-field-text').hidden = !needsText;
  $('#focus-field-remap').hidden = t !== 'remap';
  $('#btn-focus-record').hidden = t !== 'keystroke';
  $('#focus-quick-keys').hidden = t !== 'keystroke';

  if (t === 'keystroke') {
    $('#focus-data-label').textContent = 'KEYBOARD SHORTCUT';
    $('#focus-action-data').placeholder = 'ctrl+shift+t';
  } else if (t === 'key_hold') {
    $('#focus-data-label').textContent = 'HOLD KEY (EVDEV / PTT)';
    $('#focus-action-data').placeholder = 'PageDown or PageUp';
  } else if (t === 'command') {
    $('#focus-data-label').textContent = 'SHELL COMMAND';
    $('#focus-action-data').placeholder = 'hyprshot -m region';
  } else if (t === 'application') {
    $('#focus-data-label').textContent = 'APPLICATION (.desktop or binary)';
    $('#focus-action-data').placeholder = 'kitty';
  } else if (t === 'dpi_set') {
    $('#focus-data-label').textContent = 'TARGET DPI (200–8000)';
    $('#focus-action-data').placeholder = '1600';
  } else if (t === 'haptic') {
    $('#focus-data-label').textContent = 'WAVEFORM ID (0–14)';
    $('#focus-action-data').placeholder = '2';
  }
}

function openRebindDialog(cid) {
  openControlInspector(cid);
}

function syncRebindFields() {
  const t = $('#rebind-type').value;
  const needsText = ['keystroke', 'key_hold', 'command', 'application', 'dpi_set', 'haptic'].includes(t);
  $('#rebind-field-text').hidden = !needsText;
  $('#rebind-field-remap').hidden = t !== 'remap';
  $('#btn-record-keys').hidden = t !== 'keystroke';
  $('#rebind-quick-keys').hidden = t !== 'keystroke';

  if (t === 'keystroke') {
    $('#rebind-data-label').textContent = 'KEYBOARD SHORTCUT';
    $('#rebind-data').placeholder = 'ctrl+shift+t';
  } else if (t === 'key_hold') {
    $('#rebind-data-label').textContent = 'HOLD KEY (EVDEV / PTT)';
    $('#rebind-data').placeholder = 'PageDown or PageUp';
  } else if (t === 'command') {
    $('#rebind-data-label').textContent = 'SHELL COMMAND';
    $('#rebind-data').placeholder = 'hyprshot -m region';
  } else if (t === 'application') {
    $('#rebind-data-label').textContent = 'APPLICATION (.desktop or binary)';
    $('#rebind-data').placeholder = 'kitty';
  } else if (t === 'dpi_set') {
    $('#rebind-data-label').textContent = 'TARGET DPI (200–8000)';
    $('#rebind-data').placeholder = '1600';
  } else if (t === 'haptic') {
    $('#rebind-data-label').textContent = 'WAVEFORM ID (0–14)';
    $('#rebind-data').placeholder = '2';
  }
}

function openPromptDialog({ title, desc, label, initial = '', maxLength = 32, showTemplate = false, onSave }) {
  state.promptCallback = onSave;
  $('#dlg-prompt-title').textContent = title;
  $('#dlg-prompt-desc').textContent = desc || '';
  $('#prompt-label').textContent = label || 'VALUE';
  const input = $('#prompt-input');
  input.value = initial;
  input.maxLength = maxLength;
  $('#prompt-template-wrap').hidden = !showTemplate;
  $('#dlg-prompt').showModal();
}

// ─────────────────────────── Diagnostics / Lab ───────────────────────────

function renderDiagnostics(snap) {
  const grid = $('#health-grid');
  grid.innerHTML = '';
  const items = [
    ['mx4-sysd Daemon', snap.sysd?.running ? `Running · API v${snap.sysd.version}` : 'Stopped', snap.sysd?.running],
    ['mx4-agent Session', snap.agent?.running ? `Active · ${snap.agent.active_profile}` : 'Stopped', snap.agent?.running],
    ['MX Master 4 Link', snap.device?.connected ? `${snap.device.connection} · FW ${snap.device.firmware}` : 'Disconnected', snap.device?.connected],
    ['Wayland Stack', `${snap.environment?.compositor} · wtype=${snap.environment?.wtype ? 'ok' : 'no'}`, Boolean(snap.environment?.wtype && snap.environment?.layer_shell)],
  ];
  for (const [title, sub, ok] of items) {
    const el = document.createElement('div');
    el.className = 'health-tile';
    el.innerHTML = `<span class="live-dot ${ok ? 'is-online' : 'is-offline'}"></span><div><strong>${title}</strong><small>${sub}</small></div>`;
    grid.appendChild(el);
  }

  const d = snap.device || {};
  $('#telemetry-pre').textContent = d.connected
    ? [
        `Product:      ${d.name}  (Friendly: ${d.friendly_name})`,
        `Firmware:     ${d.firmware}  |  Transport: ${d.connection}`,
        `Battery:      ${d.battery}% (${d.battery_level_name}, charging=${d.charging})`,
        `DPI:          ${d.dpi}  [range ${d.dpi_min}–${d.dpi_max}, step ${d.dpi_step}]`,
        `MagSpeed:     mode=${d.wheel_mode}  threshold=${d.smartshift_threshold}  torque=${d.ratchet_torque}%`,
        `Hi-Res Wheel: enabled=${d.hires_enabled}  invert=${d.hires_invert}  diverted=${Boolean(d.hires_diverted)}`,
        `HD Scroll:    speed=${Number(d.scroll_speed ?? snap.config?.scroll?.scroll_speed ?? 1).toFixed(2)}x  smooth=${d.scroll_smoothness ?? snap.config?.scroll?.scroll_smoothness ?? 0}%  accel=${d.scroll_accel ?? snap.config?.scroll?.scroll_accel ?? 0}%`,
        `Thumb Wheel:  diverted=${d.thumbwheel_diverted}  invert=${d.thumbwheel_invert}`,
        `Haptic Motor: enabled=${d.haptic_enabled}  level=${d.haptic_level}%  waves=${(d.haptic_waveforms || []).length}`,
        `Force Sensor: supported=${d.force_supported}  value=${d.force_value} (default ${d.force_default})`,
        `Easy-Switch:  Slot ${(d.current_host ?? 0) + 1} / ${d.num_hosts || 3}`,
      ].join('\n')
    : 'Mouse disconnected.';
}

function renderProbedFeatures() {
  const box = $('#probe-list');
  const q = $('#probe-filter').value.trim().toLowerCase();
  const rows = state.probedFeatures.filter((f) => {
    if (!q) return true;
    return `${f.feature_hex} ${f.name} ${f.description}`.toLowerCase().includes(q);
  });
  box.innerHTML = '';
  for (const f of rows) {
    const el = document.createElement('div');
    el.className = 'probe-row';
    const right = f.locked
      ? `<span class="probe-locked">LOCKED (Options+)</span>`
      : `<span class="probe-hex">${(f.response_hex || f.error || '—').slice(0, 22)}</span>`;
    el.innerHTML = `
      <div class="control-info">
        <div class="control-title-row">
          <span class="cid-pill">#${String(f.index).padStart(2, '0')}</span>
          <span class="cid-pill">${f.feature_hex}</span>
          <strong>${f.name}</strong>
        </div>
        <span class="card-sub">${f.description}</span>
      </div>
      ${right}
    `;
    box.appendChild(el);
  }
}

// ─────────────────────────── Static Builders & Wiring ────────────────────

function buildStaticUI() {
  // Vernier tick scales across all precision controls
  buildVernierTicks('#dpi-vernier-ticks', 51, 5);
  buildVernierTicks('#ss-vernier-ticks', 51, 5);
  buildVernierTicks('#scroll-speed-ticks', 41, 5);
  buildVernierTicks('#scroll-smooth-ticks', 41, 5);
  buildVernierTicks('#scroll-accel-ticks', 41, 5);
  buildVernierTicks('#tw-speed-ticks', 41, 5);
  buildVernierTicks('#tw-smooth-ticks', 41, 5);
  buildVernierTicks('#tw-accel-ticks', 41, 5);
  buildVernierTicks('#haptic-vernier-ticks', 45, 5);
  buildVernierTicks('#force-vernier-ticks', 45, 5);
  renderDpiStageMarkers([800, 1200, 1600, 2400, 4000]);

  // Interactive Scroll Feel Test Pad ruler
  const ruler = $('#scroll-test-ruler');
  if (ruler) {
    ruler.innerHTML = '';
    for (let i = 1; i <= 48; i++) {
      const major = i % 4 === 0;
      const w = 18 + Math.round(Math.abs(Math.sin(i * 0.45)) * 52);
      const row = document.createElement('div');
      row.className = `scroll-test-line ${major ? 'is-major' : ''}`;
      row.innerHTML = `<span>${String(i * 10).padStart(3, '0')} px</span><span class="scroll-test-bar" style="width:${w}%"></span><span>${major ? 'DETENT' : '·'}</span>`;
      ruler.appendChild(row);
    }
  }

  // Interactive Horizontal Thumb Wheel 6× HD Timeline Test Ruler
  const hTrack = $('#hscroll-test-track');
  const hPad = $('#hscroll-test-pad');
  if (hTrack) {
    hTrack.innerHTML = '';
    for (let i = 0; i <= 120; i++) {
      const major = i % 6 === 0;
      const tick = document.createElement('div');
      tick.className = `hscroll-tick ${major ? 'is-major' : ''}`;
      tick.textContent = major ? String(i / 6).padStart(2, '0') : '';
      hTrack.appendChild(tick);
    }
    if (hPad) {
      requestAnimationFrame(() => { hPad.scrollLeft = Math.max(0, (hTrack.scrollWidth - hPad.clientWidth) / 2); });
    }
  }

  // Precision Shift Force S-curve graph
  initTorqueCurveGraph();
  setTorqueUI(75);

  // DPI preset chips
  const dpiChips = $('#dpi-chips');
  for (const p of DPI_PRESET_CHIPS) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'studio-chip';
    b.dataset.dpi = String(p);
    b.textContent = String(p);
    b.addEventListener('click', () => commitDpi(p));
    dpiChips.appendChild(b);
  }

  // 15 Waveform cards + dropdowns
  const waveGrid = $('#wave-grid');
  const waveDropdowns = ['#sel-ring-boundary', '#sel-ring-confirm', '#sel-ring-cancel', '#sel-notif-pattern'].map($);
  for (const [id, name, svgPath] of WAVEFORMS) {
    for (const dd of waveDropdowns) {
      dd.add(new Option(`${String(id).padStart(2, '0')} · ${name}`, String(id)));
    }
    const card = document.createElement('button');
    card.type = 'button';
    card.className = 'wave-card';
    card.dataset.waveId = String(id);
    card.innerHTML = `
      <svg class="wave-svg" viewBox="0 0 58 24" aria-hidden="true"><path d="${svgPath}"/></svg>
      <span class="wave-name">${name}</span>
      <span class="wave-id">WAVE ${String(id).padStart(2, '0')}</span>
    `;
    card.addEventListener('click', async () => {
      card.classList.add('is-pulsing');
      setTimeout(() => card.classList.remove('is-pulsing'), 420);
      state.activeFeelWave = id;
      state.oscPulse = 1.0;
      studio3d?.triggerHapticVisual(id);
      for (const c of $$('.wave-card')) c.classList.toggle('is-active', c === card);
      for (const fp of $$('.feel-pill')) fp.classList.toggle('is-active', Number(fp.dataset.feelWave) === id);
      $('#sel-ring-confirm').value = String(id);
      try {
        const res = await rpc('triggerHaptic', { pattern: id });
        if (res?.auto_enabled) syncHapticMotorOnUI();
        await rpc('saveHapticConfig', { ring_confirm_pattern: id });
      } catch (e) { toast(e.message); }
    });
    waveGrid.appendChild(card);
  }

  // Ring quick chips
  const quickRing = $('#ring-quick-chips');
  for (const [label, atype, data] of QUICK_RING_PRESETS) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'studio-chip';
    b.textContent = label;
    b.addEventListener('click', () => {
      $('#slice-label').value = label;
      $('#slice-type').value = atype;
      $('#slice-data').value = data;
      saveCurrentRingSlice();
    });
    quickRing.appendChild(b);
  }

  // Rebind quick keys (both modal & direct focus inspector!)
  for (const [sel, targetInput] of [['#rebind-quick-keys', '#rebind-data'], ['#focus-quick-keys', '#focus-action-data']]) {
    const box = $(sel);
    if (!box) continue;
    for (const [label, spec] of QUICK_REBIND_KEYS) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'studio-chip';
      b.textContent = label;
      b.addEventListener('click', () => { $(targetInput).value = spec; });
      box.appendChild(b);
    }
  }
}

async function commitDpi(dpi) {
  $('#dpi-slider').value = String(dpi);
  $('#dpi-readout').textContent = String(dpi);
  $('#hud-dpi').textContent = String(dpi);
  for (const chip of $$('#dpi-chips .studio-chip')) {
    chip.classList.toggle('is-active', Number(chip.dataset.dpi) === dpi);
  }
  studio3d?.setHardwareState({ dpi });
  studio3d?.triggerFloorBurst(0.95, 0.0);
  try {
    await rpc('setDpi', { dpi });
  } catch (e) { toast(e.message); }
}

function commitScrollMode(modeOverride = null) {
  const activePill = $('.mode-pill.is-active');
  const mode = modeOverride || activePill?.dataset.scrollMode || 'smart';
  const threshold = Number($('#ss-thr-slider').value);
  const torque = Number($('#torque-slider').value);
  studio3d?.setHardwareState({ scrollMode: mode, smartshiftThreshold: threshold, torque });
  studio3d?.pulseWheel(1);
  $('#hud-mode').textContent = mode.toUpperCase();
  rpc('setScrollMode', { mode, threshold, torque }).catch((e) => toast(e.message));
}

function updateScrollTuningUI(speed, smoothness, accel, diverted = null) {
  const sp = Math.max(0.20, Math.min(4.00, Number(speed) || 1.0));
  const sm = Math.max(0, Math.min(100, Math.round(Number(smoothness) || 0)));
  const ac = Math.max(0, Math.min(100, Math.round(Number(accel) || 0)));
  state.scrollSpeed = sp;
  state.scrollSmoothness = sm;
  state.scrollAccel = ac;
  studio3d?.setHardwareState({ scrollSpeed: sp, scrollSmoothness: sm, scrollAccel: ac });

  $('#scroll-speed-slider').value = sp.toFixed(2);
  $('#scroll-smooth-slider').value = String(sm);
  $('#scroll-accel-slider').value = String(ac);

  $('#scroll-speed-readout').textContent = sp.toFixed(2);
  $('#scroll-speed-val').textContent = `${sp.toFixed(2)}×`;
  $('#scroll-smooth-val').textContent = `${sm}%`;
  $('#scroll-accel-val').textContent = `${ac}%`;

  updateVernierFill('#scroll-speed-slider', '#scroll-speed-fill');
  updateVernierFill('#scroll-smooth-slider', '#scroll-smooth-fill');
  updateVernierFill('#scroll-accel-slider', '#scroll-accel-fill');

  const isActive = Math.abs(sp - 1.0) > 0.015 || sm > 0 || ac > 0;
  const badge = $('#smooth-engine-badge');
  if (badge) {
    if (!isActive) badge.textContent = 'Native bypass (zero latency)';
    else badge.textContent = diverted === false ? 'Configured · run sudo ./install.sh to activate' : '144 Hz active · uinput';
  }

  for (const chip of $$('#scroll-tuning-presets .studio-chip')) {
    const match = Math.abs(Number(chip.dataset.speed) - sp) < 0.02
      && Number(chip.dataset.smooth) === sm
      && Number(chip.dataset.accel) === ac;
    chip.classList.toggle('is-active', match);
  }
}

function commitScrollTuning() {
  const speed = Number($('#scroll-speed-slider').value);
  const smoothness = Number($('#scroll-smooth-slider').value);
  const accel = Number($('#scroll-accel-slider').value);
  updateScrollTuningUI(speed, smoothness, accel);
  studio3d?.pulseWheel(1);
  rpc('setScrollTuning', { speed, smoothness, accel })
    .then((res) => {
      if (res?.needs_install) {
        toast('Saved! Run sudo ./install.sh to activate live 144 Hz smooth scroll');
      }
    })
    .catch((e) => toast(e.message));
}

function formatTwStepLabel(step) {
  const s = Math.max(1, Math.min(120, Math.round(Number(step) || 16)));
  const perRev = 120 / s;
  const revStr = Number.isInteger(perRev) ? String(perRev) : perRev.toFixed(1);
  return `${s} ${s === 1 ? 'tick' : 'ticks'} · ${revStr}/rev`;
}

function updateThumbwheelUI({
  mode = 'native',
  invert = false,
  speed = 1.0,
  smoothness = 35,
  accel = 25,
  hires = true,
  haptic_detent = false,
  haptic_density = 6,
  haptic_pattern = 1,
  engineActive = null,
  nativeRes = 20,
  divertedRes = 120,
} = {}) {
  const m = ['hd_scroll', 'native', 'actions'].includes(mode) ? mode : 'native';
  const sp = Math.max(0.20, Math.min(4.00, Number(speed) || 1.0));
  const sm = Math.max(0, Math.min(100, Math.round(Number(smoothness) || 0)));
  const ac = Math.max(0, Math.min(100, Math.round(Number(accel) || 0)));
  const dens = [1, 2, 3, 6].includes(Number(haptic_density)) ? Number(haptic_density) : 6;
  const pat = Math.max(0, Math.min(14, Math.round(Number(haptic_pattern ?? 1))));
  const ratio = nativeRes > 0 ? Math.round(divertedRes / nativeRes) : 6;

  state.twMode = m;
  state.twInvert = Boolean(invert);
  state.twSpeed = sp;
  state.twSmoothness = sm;
  state.twAccel = ac;
  state.twHires = Boolean(hires);
  state.twHapticDetent = Boolean(haptic_detent);
  state.twHapticDensity = dens;
  state.twHapticPattern = pat;
  studio3d?.setHardwareState({ thumbwheelMode: m });

  for (const pill of $$('#tw-mode-pills .tw-mode-pill')) {
    pill.classList.toggle('is-active', pill.dataset.twMode === m);
  }
  for (const pill of $$('#focus-tw-mode-pills .tw-mode-pill')) {
    pill.classList.toggle('is-active', pill.dataset.focusTwMode === m);
  }

  let badgeText = `Native · ${nativeRes}/rev`;
  if (m === 'hd_scroll') {
    badgeText = engineActive === false
      ? 'Configured · run sudo ./install.sh to activate'
      : `${ratio}× HD · ${divertedRes}/rev · 144 Hz`;
  } else if (m === 'actions') {
    badgeText = `Actions · ${divertedRes}/rev`;
  }
  if ($('#tw-engine-badge')) $('#tw-engine-badge').textContent = badgeText;
  if ($('#focus-tw-badge')) $('#focus-tw-badge').textContent = badgeText;

  if ($('#sw-tw-invert')) $('#sw-tw-invert').checked = state.twInvert;
  if ($('#focus-tw-invert')) $('#focus-tw-invert').checked = state.twInvert;

  if ($('#tw-hd-block')) $('#tw-hd-block').hidden = m !== 'hd_scroll';
  if ($('#tw-custom-block')) $('#tw-custom-block').hidden = m !== 'actions';
  if ($('#focus-tw-hd-wrap')) $('#focus-tw-hd-wrap').hidden = m !== 'hd_scroll';
  if ($('#focus-tw-custom-wrap')) $('#focus-tw-custom-wrap').hidden = m !== 'actions';

  if ($('#tw-speed-slider')) $('#tw-speed-slider').value = sp.toFixed(2);
  if ($('#tw-smooth-slider')) $('#tw-smooth-slider').value = String(sm);
  if ($('#tw-accel-slider')) $('#tw-accel-slider').value = String(ac);
  if ($('#tw-speed-readout')) $('#tw-speed-readout').textContent = sp.toFixed(2);
  if ($('#tw-speed-val')) $('#tw-speed-val').textContent = `${sp.toFixed(2)}×`;
  if ($('#tw-smooth-val')) $('#tw-smooth-val').textContent = `${sm}%`;
  if ($('#tw-accel-val')) $('#tw-accel-val').textContent = `${ac}%`;
  if ($('#sw-tw-hires')) $('#sw-tw-hires').checked = state.twHires;
  if ($('#sw-tw-haptic-detent')) $('#sw-tw-haptic-detent').checked = state.twHapticDetent;
  if ($('#tw-haptic-density')) $('#tw-haptic-density').value = String(dens);
  if ($('#tw-haptic-pattern')) $('#tw-haptic-pattern').value = String(pat);

  if ($('#focus-tw-speed')) $('#focus-tw-speed').value = sp.toFixed(2);
  if ($('#focus-tw-smooth')) $('#focus-tw-smooth').value = String(sm);
  if ($('#focus-tw-accel')) $('#focus-tw-accel').value = String(ac);
  if ($('#focus-tw-speed-readout')) $('#focus-tw-speed-readout').innerHTML = `${sp.toFixed(2)}<small>×</small>`;
  if ($('#focus-tw-speed-val')) $('#focus-tw-speed-val').textContent = `${sp.toFixed(2)}×`;
  if ($('#focus-tw-smooth-val')) $('#focus-tw-smooth-val').textContent = `${sm}%`;
  if ($('#focus-tw-accel-val')) $('#focus-tw-accel-val').textContent = `${ac}%`;
  if ($('#focus-tw-hires')) $('#focus-tw-hires').checked = state.twHires;
  if ($('#focus-tw-haptic-detent')) $('#focus-tw-haptic-detent').checked = state.twHapticDetent;
  if ($('#focus-tw-haptic-density')) $('#focus-tw-haptic-density').value = String(dens);
  if ($('#focus-tw-haptic-pattern')) $('#focus-tw-haptic-pattern').value = String(pat);

  updateVernierFill('#tw-speed-slider', '#tw-speed-fill');
  updateVernierFill('#tw-smooth-slider', '#tw-smooth-fill');
  updateVernierFill('#tw-accel-slider', '#tw-accel-fill');

  for (const chip of $$('#tw-hd-presets .studio-chip, #focus-tw-hd-presets .studio-chip')) {
    const match = Math.abs(Number(chip.dataset.speed) - sp) < 0.02
      && Number(chip.dataset.smooth) === sm
      && Number(chip.dataset.accel) === ac;
    chip.classList.toggle('is-active', match);
  }
}

function commitThumbwheelTuning(overrides = {}) {
  const payload = {
    mode: overrides.mode ?? state.twMode ?? 'native',
    invert: overrides.invert ?? state.twInvert ?? false,
    speed: overrides.speed ?? state.twSpeed ?? 1.0,
    smoothness: overrides.smoothness ?? state.twSmoothness ?? 35,
    accel: overrides.accel ?? state.twAccel ?? 25,
    hires: overrides.hires ?? state.twHires ?? true,
    haptic_detent: overrides.haptic_detent ?? state.twHapticDetent ?? false,
    haptic_density: overrides.haptic_density ?? state.twHapticDensity ?? 6,
    haptic_pattern: overrides.haptic_pattern ?? state.twHapticPattern ?? 1,
  };
  updateThumbwheelUI(payload);
  studio3d?.pulseThumbWheel(payload.invert ? -1 : 1);
  if (state.snapshot?.device) {
    state.snapshot.device.thumbwheel_mode = payload.mode;
    state.snapshot.device.thumbwheel_diverted = payload.mode === 'actions';
    state.snapshot.device.thumbwheel_invert = payload.invert;
    state.snapshot.device.thumbwheel_speed = payload.speed;
    state.snapshot.device.thumbwheel_smoothness = payload.smoothness;
    state.snapshot.device.thumbwheel_accel = payload.accel;
    state.snapshot.device.thumbwheel_hires = payload.hires;
    state.snapshot.device.thumbwheel_haptic_detent = payload.haptic_detent;
    state.snapshot.device.thumbwheel_haptic_density = payload.haptic_density;
    state.snapshot.device.thumbwheel_haptic_pattern = payload.haptic_pattern;
  }
  rpc('setThumbwheelTuning', payload)
    .then((res) => {
      if (res?.needs_install) {
        toast('Saved! Run sudo ./install.sh to activate live 6× HD thumb-wheel scroll');
      }
    })
    .catch((e) => toast(e.message));
}

function saveCurrentRingSlice() {
  const prof = state.snapshot?.config?.ring_profiles?.[state.ringProfileId];
  if (!prof) return;
  const label = $('#slice-label').value;
  const action_type = $('#slice-type').value;
  const action_data = $('#slice-data').value;
  prof.slices[state.ringSliceIdx] = { label, icon: '', action_type, action_data };
  renderRingDesigner();
  debounce('ringSlice', 260, () => {
    rpc('saveRingSlice', {
      profile_id: state.ringProfileId,
      index: state.ringSliceIdx,
      label,
      action_type,
      action_data,
    }).catch((e) => toast(e.message));
  });
}

async function triggerIdentify() {
  state.oscPulse = 1.0;
  studio3d?.triggerHapticVisual(10);
  try {
    await rpc('triggerHaptic', { pattern: 10 });
    toast('Identify haptic sent');
  } catch (e) { toast(e.message); }
}

async function triggerSyncAll() {
  try {
    await rpc('reloadConfig');
    toast('All hardware settings re-applied');
    await refreshSnapshot();
  } catch (e) { toast(e.message); }
}

function syncHapticMotorOnUI() {
  state.hapticEnabled = true;
  const sw = $('#sw-haptic-motor');
  if (sw) sw.checked = true;
  $('#haptic-strength-wrap').style.opacity = '1';
  $('#haptic-strength-word').textContent = hapticStrengthWord(state.hapticLevel, true);
  studio3d?.setHardwareState({ hapticEnabled: true, hapticLevel: state.hapticLevel });
}

function wireEvents() {
  // Top pill navigation
  for (const btn of $$('.dock-btn')) {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  }

  $('#btn-refresh-all').addEventListener('click', () => {
    refreshSnapshot();
    toast('Synced live state from MX Master 4');
  });

  // Shared quick action buttons across tabs
  for (const b of $$('[data-action="identify"]')) b.addEventListener('click', triggerIdentify);
  for (const b of $$('[data-action="sync-all"]')) b.addEventListener('click', triggerSyncAll);

  // Stage quick links
  const pulseActiveHaptic = async () => {
    state.oscPulse = 1.0;
    studio3d?.triggerHapticVisual(state.activeFeelWave);
    try {
      const res = await rpc('triggerHaptic', { pattern: state.activeFeelWave });
      if (res?.auto_enabled) {
        syncHapticMotorOnUI();
        toast('Motor 0x19B0 enabled & haptic pulse sent');
      }
    } catch (e) { toast(e.message); }
  };
  $('#btn-pulse-haptic').addEventListener('click', pulseActiveHaptic);
  $('#btn-haptic-pulse-main').addEventListener('click', pulseActiveHaptic);

  $('#btn-reset-cam').addEventListener('click', () => studio3d?.resetCamera());
  $('#btn-toggle-motion').addEventListener('click', (e) => {
    const paused = !studio3d.ambientPaused;
    studio3d.setAmbientPaused(paused);
    e.currentTarget.textContent = paused ? 'Resume Motion' : 'Pause Motion';
  });

  $('#btn-rename-mouse').addEventListener('click', () => {
    const cur = state.snapshot?.device?.friendly_name || 'MX Master 4';
    openPromptDialog({
      title: 'Rename MX Master 4',
      desc: 'Stored inside the mouse hardware memory (max 14 characters).',
      label: 'FRIENDLY NAME',
      initial: cur,
      maxLength: 14,
      onSave: async (name) => {
        await rpc('setFriendlyName', { name });
        toast(`Mouse renamed to ${name}`);
        await refreshSnapshot();
      },
    });
  });

  // Device tab
  $('#dpi-slider').addEventListener('input', (e) => {
    const val = Number(e.target.value);
    $('#dpi-readout').textContent = String(val);
    $('#hud-dpi').textContent = String(val);
    for (const chip of $$('#dpi-chips .studio-chip')) {
      chip.classList.toggle('is-active', Number(chip.dataset.dpi) === val);
    }
    studio3d?.setHardwareState({ dpi: val });
    debounce('dpi', 110, () => commitDpi(val));
  });

  $('#btn-save-dpi-cycle').addEventListener('click', async () => {
    const presets = $('#dpi-cycle-input').value.split(/[,;\s]+/).map(Number).filter((n) => n >= 200 && n <= 8000);
    if (!presets.length) return toast('Enter valid DPI values between 200 and 8000');
    try {
      const res = await rpc('setDpiPresets', { presets });
      $('#dpi-cycle-input').value = res.presets.join(', ');
      renderDpiStageMarkers(res.presets);
      toast(`DPI cycle stages saved (${res.presets.join(', ')})`);
    } catch (e) { toast(e.message); }
  });

  $('#btn-identify-mouse').addEventListener('click', triggerIdentify);
  $('#btn-reapply-device').addEventListener('click', triggerSyncAll);

  // Scroll tab
  for (const pill of $$('.mode-pill')) {
    pill.addEventListener('click', () => {
      for (const p of $$('.mode-pill')) p.classList.toggle('is-active', p === pill);
      $('#card-smartshift-thr').style.opacity = pill.dataset.scrollMode === 'smart' ? '1' : '0.52';
      commitScrollMode(pill.dataset.scrollMode);
      toast(`MagSpeed → ${pill.querySelector('span').textContent}`);
    });
  }

  $('#ss-thr-slider').addEventListener('input', (e) => {
    const thr = Number(e.target.value);
    $('#ss-thr-readout').textContent = String(thr);
    updateVernierFill('#ss-thr-slider', '#ss-vernier-fill');
    studio3d?.setHardwareState({ smartshiftThreshold: thr });
    debounce('ssThr', 120, () => commitScrollMode());
  });

  for (const chip of $$('[data-torque]')) {
    chip.addEventListener('click', () => {
      const v = Number(chip.dataset.torque);
      setTorqueUI(v);
      studio3d?.setHardwareState({ torque: v });
      commitScrollMode();
    });
  }

  // HD Smooth Scroll Engine presets & 3 vernier sliders
  for (const chip of $$('#scroll-tuning-presets .studio-chip')) {
    chip.addEventListener('click', () => {
      updateScrollTuningUI(
        Number(chip.dataset.speed),
        Number(chip.dataset.smooth),
        Number(chip.dataset.accel),
      );
      commitScrollTuning();
      toast(`HD Scroll → ${chip.textContent}`);
    });
  }

  const onSmoothSliderInput = () => {
    updateScrollTuningUI(
      Number($('#scroll-speed-slider').value),
      Number($('#scroll-smooth-slider').value),
      Number($('#scroll-accel-slider').value),
    );
    debounce('scrollTuning', 110, commitScrollTuning);
  };
  $('#scroll-speed-slider').addEventListener('input', onSmoothSliderInput);
  $('#scroll-smooth-slider').addEventListener('input', onSmoothSliderInput);
  $('#scroll-accel-slider').addEventListener('input', onSmoothSliderInput);

  // Interactive Scroll Feel Test Pad
  const testPad = $('#scroll-test-pad');
  if (testPad) {
    testPad.addEventListener('wheel', (e) => {
      const d = Math.round(e.deltaY);
      $('#scroll-test-delta').textContent = `Δ ${d > 0 ? '+' : ''}${d} px`;
      studio3d?.pulseWheel(Math.sign(e.deltaY) || 1);
    }, { passive: true });
  }

  const syncHiRes = () => {
    const enabled = $('#sw-hires').checked;
    const invert = $('#sw-hires-invert').checked;
    studio3d?.setHardwareState({ hiresInvert: invert });
    studio3d?.pulseWheel(1);
    rpc('setHiRes', { enabled, invert }).catch((e) => toast(e.message));
  };
  $('#sw-hires').addEventListener('change', syncHiRes);
  $('#sw-hires-invert').addEventListener('change', syncHiRes);

  // Scroll tab: Thumb Wheel 6× HD Engine + Actions (0x2150)
  for (const pill of $$('#tw-mode-pills .tw-mode-pill')) {
    pill.addEventListener('click', () => {
      commitThumbwheelTuning({ mode: pill.dataset.twMode });
    });
  }
  $('#sw-tw-invert')?.addEventListener('change', (e) => {
    commitThumbwheelTuning({ invert: e.target.checked });
  });
  for (const chip of $$('#tw-hd-presets .studio-chip')) {
    chip.addEventListener('click', () => {
      commitThumbwheelTuning({
        mode: 'hd_scroll',
        speed: Number(chip.dataset.speed),
        smoothness: Number(chip.dataset.smooth),
        accel: Number(chip.dataset.accel),
      });
    });
  }
  const onTwHdSliderInput = () => {
    const sp = Number($('#tw-speed-slider').value);
    const sm = Number($('#tw-smooth-slider').value);
    const ac = Number($('#tw-accel-slider').value);
    updateThumbwheelUI({
      mode: 'hd_scroll',
      invert: state.twInvert,
      speed: sp,
      smoothness: sm,
      accel: ac,
      hires: state.twHires,
      haptic_detent: state.twHapticDetent,
    });
    debounce('twTuning', 110, () => commitThumbwheelTuning({ mode: 'hd_scroll', speed: sp, smoothness: sm, accel: ac }));
  };
  $('#tw-speed-slider')?.addEventListener('input', onTwHdSliderInput);
  $('#tw-smooth-slider')?.addEventListener('input', onTwHdSliderInput);
  $('#tw-accel-slider')?.addEventListener('input', onTwHdSliderInput);
  $('#sw-tw-hires')?.addEventListener('change', (e) => {
    commitThumbwheelTuning({ mode: 'hd_scroll', hires: e.target.checked });
  });
  $('#sw-tw-haptic-detent')?.addEventListener('change', (e) => {
    commitThumbwheelTuning({ mode: 'hd_scroll', haptic_detent: e.target.checked });
  });
  $('#tw-haptic-density')?.addEventListener('change', (e) => {
    commitThumbwheelTuning({ mode: 'hd_scroll', haptic_density: Number(e.target.value) });
  });
  $('#tw-haptic-pattern')?.addEventListener('change', (e) => {
    const pat = Number(e.target.value);
    commitThumbwheelTuning({ mode: 'hd_scroll', haptic_pattern: pat });
    rpc('triggerHaptic', { pattern: pat }).catch(() => {});
  });

  // Interactive Horizontal Thumb Wheel 6× HD Timeline Test Pad
  const hTestPad = $('#hscroll-test-pad');
  if (hTestPad) {
    hTestPad.addEventListener('wheel', (e) => {
      const dx = Math.abs(e.deltaX) > 0.01 ? e.deltaX : (e.shiftKey ? e.deltaY : 0);
      if (Math.abs(dx) < 0.01) return;
      const d = Math.round(dx * 10) / 10;
      $('#hscroll-test-delta').textContent = `ΔX ${d > 0 ? '+' : ''}${d} px`;
      studio3d?.pulseThumbWheel(Math.sign(dx) || 1);
    }, { passive: true });
  }

  const saveTwCfg = () => {
    debounce('twCfg', 220, () => {
      const payload = {
        preset: $('#tw-preset').value,
        positive_type: $('#tw-pos-type').value,
        positive_data: $('#tw-pos-data').value,
        negative_type: $('#tw-neg-type').value,
        negative_data: $('#tw-neg-data').value,
        step: Number($('#tw-step-slider').value),
        haptic_tick: $('#sw-tw-haptic').checked,
        micro_haptics: $('#sw-tw-micro-haptics') ? $('#sw-tw-micro-haptics').checked : true,
        haptic_pattern: $('#tw-action-pattern') ? Number($('#tw-action-pattern').value) : 1,
      };
      if ($('#focus-tw-step')) {
        $('#focus-tw-step').value = String(payload.step);
        $('#focus-tw-step-readout').textContent = formatTwStepLabel(payload.step);
      }
      if ($('#focus-tw-haptic')) $('#focus-tw-haptic').checked = payload.haptic_tick;
      if ($('#focus-tw-micro-haptics')) $('#focus-tw-micro-haptics').checked = payload.micro_haptics;
      if ($('#focus-tw-action-pattern')) $('#focus-tw-action-pattern').value = String(payload.haptic_pattern);
      rpc('saveThumbwheelConfig', payload).catch((e) => toast(e.message));
    });
  };
  $('#tw-preset').addEventListener('change', (e) => {
    const key = e.target.value;
    const preset = state.snapshot?.thumbwheel_presets?.[key];
    if (preset && key !== 'custom') {
      $('#tw-pos-type').value = preset.positive_type;
      $('#tw-pos-data').value = preset.positive_data;
      $('#tw-neg-type').value = preset.negative_type;
      $('#tw-neg-data').value = preset.negative_data;
    }
    saveTwCfg();
  });
  for (const id of ['#tw-pos-type', '#tw-pos-data', '#tw-neg-type', '#tw-neg-data']) {
    $(id).addEventListener('input', () => { $('#tw-preset').value = 'custom'; saveTwCfg(); });
    $(id).addEventListener('change', saveTwCfg);
  }
  $('#sw-tw-haptic')?.addEventListener('change', saveTwCfg);
  $('#sw-tw-micro-haptics')?.addEventListener('change', saveTwCfg);
  $('#tw-action-pattern')?.addEventListener('change', (e) => {
    const pat = Number(e.target.value);
    rpc('triggerHaptic', { pattern: pat }).catch(() => {});
    saveTwCfg();
  });
  $('#tw-step-slider').addEventListener('input', (e) => {
    $('#tw-step-readout').textContent = formatTwStepLabel(e.target.value);
    saveTwCfg();
  });

  // Haptics tab
  $('#sw-haptic-motor').addEventListener('change', (e) => {
    const enabled = e.target.checked;
    const level = Number($('#haptic-lvl-slider').value);
    state.hapticEnabled = enabled;
    state.hapticLevel = level;
    $('#haptic-strength-wrap').style.opacity = enabled ? '1' : '0.45';
    $('#haptic-strength-word').textContent = hapticStrengthWord(level, enabled);
    studio3d?.setHardwareState({ hapticEnabled: enabled, hapticLevel: level });
    if (enabled) {
      state.oscPulse = 0.9;
      studio3d?.triggerHapticVisual(state.activeFeelWave);
    }
    rpc('setHapticMotor', { enabled, level, preview: enabled })
      .then(() => toast(enabled ? 'Haptic motor enabled' : 'Haptic motor silenced'))
      .catch((err) => toast(err.message));
  });

  const commitHapticLevel = (lvl) => {
    state.hapticLevel = lvl;
    syncHapticMotorOnUI();
    $('#haptic-lvl-slider').value = String(lvl);
    $('#haptic-strength-word').textContent = hapticStrengthWord(lvl, true);
    $('#haptic-lvl-pct').textContent = `${lvl}%`;
    updateVernierFill('#haptic-lvl-slider', '#haptic-vernier-fill');
    studio3d?.setHardwareState({ hapticEnabled: true, hapticLevel: lvl });
    state.oscPulse = 0.85;
    studio3d?.triggerHapticVisual(state.activeFeelWave);
    rpc('setHapticMotor', { enabled: true, level: lvl, preview: true }).catch((e) => toast(e.message));
  };
  $('#haptic-lvl-slider').addEventListener('input', (e) => {
    const lvl = Number(e.target.value);
    state.hapticLevel = lvl;
    $('#haptic-strength-word').textContent = hapticStrengthWord(lvl, true);
    $('#haptic-lvl-pct').textContent = `${lvl}%`;
    updateVernierFill('#haptic-lvl-slider', '#haptic-vernier-fill');
    studio3d?.setHardwareState({ hapticLevel: lvl });
    debounce('hapLvl', 140, () => commitHapticLevel(lvl));
  });

  // Quick feel presets (Crisp Detent / Deep Thump / Subtle Tick)
  for (const pill of $$('.feel-pill')) {
    pill.addEventListener('click', async () => {
      const waveId = Number(pill.dataset.feelWave);
      state.activeFeelWave = waveId;
      state.oscPulse = 1.0;
      for (const p of $$('.feel-pill')) p.classList.toggle('is-active', p === pill);
      for (const wc of $$('.wave-card')) wc.classList.toggle('is-active', Number(wc.dataset.waveId) === waveId);
      $('#sel-ring-confirm').value = String(waveId);
      studio3d?.triggerHapticVisual(waveId);
      try {
        const res = await rpc('triggerHaptic', { pattern: waveId });
        if (res?.auto_enabled) syncHapticMotorOnUI();
        await rpc('saveHapticConfig', { ring_confirm_pattern: waveId });
      } catch (e) { toast(e.message); }
    });
  }

  // Force-sensing thumb pad presets (Feather / Light / Balanced / Firm)
  const applyForceValue = (val) => {
    const dev = state.snapshot?.device || {};
    const fmin = dev.force_min || 4156, fmax = dev.force_max || 6909, fdef = dev.force_default || 5195;
    const clamped = Math.max(fmin, Math.min(fmax, Number(val)));
    $('#force-slider').value = String(clamped);
    updateForceReadout(clamped, fmin, fmax, fdef);
    updateVernierFill('#force-slider', '#force-vernier-fill');
    studio3d?.setHardwareState({ forceNorm: (clamped - fmin) / Math.max(1, fmax - fmin) });
    return clamped;
  };
  for (const chip of $$('#force-preset-chips .studio-chip')) {
    chip.addEventListener('click', async () => {
      const val = applyForceValue(Number(chip.dataset.forceVal));
      try {
        await rpc('setForceThreshold', { value: val });
        const res = await rpc('triggerHaptic', { pattern: 2 });
        if (res?.auto_enabled) syncHapticMotorOnUI();
        toast(`Thumb pad force → ${chip.textContent} (${val})`);
      } catch (err) { toast(err.message); }
    });
  }

  $('#force-slider').addEventListener('input', (e) => {
    const val = applyForceValue(Number(e.target.value));
    debounce('force', 150, () => {
      rpc('setForceThreshold', { value: val })
        .then(() => toast(`Thumb pad force updated (${val})`))
        .catch((err) => toast(err.message));
    });
  });

  $('#btn-reset-force').addEventListener('click', async () => {
    const dev = state.snapshot?.device || {};
    const fdef = dev.force_default || 5195;
    applyForceValue(fdef);
    try {
      await rpc('setForceThreshold', { value: 0 });
      toast('Thumb pad force reset to factory default');
    } catch (e) { toast(e.message); }
  });

  // Ring & Notification haptic selectors
  const wireWaveSel = (sel, key) => {
    $(sel).addEventListener('change', (e) => {
      const pattern = Number(e.target.value);
      state.activeFeelWave = pattern;
      state.oscPulse = 0.9;
      studio3d?.triggerHapticVisual(pattern);
      rpc('triggerHaptic', { pattern }).then((res) => {
        if (res?.auto_enabled) syncHapticMotorOnUI();
      }).catch(() => {});
      rpc('saveHapticConfig', { [key]: pattern }).catch((err) => toast(err.message));
    });
  };
  wireWaveSel('#sel-ring-boundary', 'ring_boundary_pattern');
  wireWaveSel('#sel-ring-confirm', 'ring_confirm_pattern');
  wireWaveSel('#sel-ring-cancel', 'ring_cancel_pattern');
  wireWaveSel('#sel-notif-pattern', 'notification_pattern');

  $('#btn-test-notif').addEventListener('click', async () => {
    const pattern = Number($('#sel-notif-pattern').value || 5);
    state.activeFeelWave = pattern;
    state.oscPulse = 1.0;
    studio3d?.triggerHapticVisual(pattern);
    try {
      const res = await rpc('triggerHaptic', { pattern });
      if (res?.auto_enabled) syncHapticMotorOnUI();
      toast('Played notification haptic alert');
    } catch (e) { toast(e.message); }
  });

  $('#sw-notif-haptic').addEventListener('change', (e) => {
    rpc('saveHapticConfig', { notification_enabled: e.target.checked })
      .then(() => toast(e.target.checked ? 'Notification haptics enabled' : 'Notification haptics disabled'))
      .catch((err) => toast(err.message));
  });

  // Actions Ring tab
  $('#sw-ring-enabled').addEventListener('change', (e) => {
    studio3d?.setHardwareState({ ringEnabled: e.target.checked });
    studio3d?.triggerFloorBurst(0.65, e.target.checked ? 0.35 : 0.0);
    rpc('saveRingSettings', { autostart_gesture: e.target.checked }).catch((err) => toast(err.message));
  });
  $('#sel-ring-trigger').addEventListener('change', (e) => {
    rpc('saveRingSettings', { trigger_cid: Number(e.target.value) })
      .then(() => toast('Actions Ring trigger updated'))
      .catch((err) => toast(err.message));
  });
  $('#dz-slider').addEventListener('input', (e) => {
    const val = Number(e.target.value);
    $('#dz-readout').textContent = String(val);
    studio3d?.setHardwareState({ ringCancelRadius: val });
    renderRingDesigner();
    debounce('dz', 200, () => {
      rpc('saveRingSettings', { cancel_radius: val }).catch((err) => toast(err.message));
    });
  });

  for (const pill of $$('#ring-size-pills .mode-pill')) {
    pill.addEventListener('click', () => {
      const sz = pill.dataset.ringSize;
      state.ringSizeId = sz;
      if (state.snapshot?.config?.daemon) state.snapshot.config.daemon.ring_size = sz;
      for (const p of $$('#ring-size-pills .mode-pill')) p.classList.toggle('is-active', p === pill);
      syncRingAppearanceTo3D({ pulse: true });
      rpc('saveRingSettings', { ring_size: sz })
        .then(() => toast(`Ring scale → ${pill.querySelector('span').textContent}`))
        .catch((err) => toast(err.message));
    });
  }

  $('#sw-ring-hints')?.addEventListener('change', (e) => {
    state.ringShowHints = e.target.checked;
    if (state.snapshot?.config?.daemon) state.snapshot.config.daemon.ring_show_hints = state.ringShowHints;
    renderRingDesigner();
    rpc('saveRingSettings', { ring_show_hints: state.ringShowHints }).catch((err) => toast(err.message));
  });

  $('#sw-ring-animate')?.addEventListener('change', (e) => {
    state.ringAnimate = e.target.checked;
    if (state.snapshot?.config?.daemon) state.snapshot.config.daemon.ring_animate = state.ringAnimate;
    syncRingAppearanceTo3D({ pulse: state.ringAnimate });
    rpc('saveRingSettings', { ring_animate: state.ringAnimate }).catch((err) => toast(err.message));
  });

  $('#btn-preview-ring').addEventListener('click', async () => {
    studio3d?.triggerRingConfirmPulse();
    try {
      const res = await rpc('previewRing', { duration_ms: 2900 });
      if (res?.needs_install) {
        toast('Run sudo ./install.sh first to restart mx4-agent with live Ring Preview');
      } else if (res?.ok) {
        toast('Live Actions Ring shown at cursor');
      } else {
        toast(res?.error || 'Could not preview Actions Ring');
      }
    } catch (e) { toast(e.message); }
  });

  $('#sel-ring-profile').addEventListener('change', (e) => {
    state.ringProfileId = e.target.value;
    state.ringSliceIdx = 0;
    $('#btn-del-profile').disabled = state.ringProfileId === 'default';
    renderRingPresets();
    renderRingDesigner();
  });

  $('#btn-add-profile').addEventListener('click', () => openPromptDialog({
    title: 'Add Application Profile',
    desc: 'Enter a Hyprland/Sway window class (e.g. zen, code, kitty, blender).',
    label: 'APPLICATION CLASS',
    showTemplate: true,
    onSave: async (appId, template) => {
      const res = await rpc('addRingProfile', { app_id: appId, template });
      state.ringProfileId = res.app_id;
      toast(`Created profile '${res.app_id}'`);
      await refreshSnapshot();
    },
  }));

  $('#btn-del-profile').addEventListener('click', async () => {
    if (state.ringProfileId === 'default') return;
    const id = state.ringProfileId;
    try {
      await rpc('deleteRingProfile', { app_id: id });
      state.ringProfileId = 'default';
      toast(`Deleted profile '${id}'`);
      await refreshSnapshot();
    } catch (e) { toast(e.message); }
  });

  for (const id of ['#slice-label', '#slice-type', '#slice-data']) {
    $(id).addEventListener('input', saveCurrentRingSlice);
    $(id).addEventListener('change', saveCurrentRingSlice);
  }

  $('#btn-test-slice').addEventListener('click', () => {
    rpc('testAction', {
      action_type: $('#slice-type').value,
      action_data: $('#slice-data').value,
    }).then(() => toast('Triggered slice action')).catch((e) => toast(e.message));
  });

  // Direct Clicked-Control Focus Inspector events
  $('#btn-focus-back')?.addEventListener('click', closeControlInspector);

  $('#focus-scope-sel')?.addEventListener('change', (e) => {
    state.buttonScope = e.target.value;
    if (state.focusedCid != null) openControlInspector(state.focusedCid);
  });

  $('#focus-action-type')?.addEventListener('change', syncFocusBindingFields);

  const focusRecBtn = $('#btn-focus-record');
  focusRecBtn?.addEventListener('click', () => {
    state.recordingFocusKeys = !state.recordingFocusKeys;
    focusRecBtn.textContent = state.recordingFocusKeys ? 'Press keys…' : 'Record';
  });

  window.addEventListener('keydown', (e) => {
    if (state.recordingFocusKeys) {
      if (['Control', 'Shift', 'Alt', 'Meta'].includes(e.key)) return;
      e.preventDefault();
      e.stopPropagation();
      if (e.key === 'Escape') {
        state.recordingFocusKeys = false;
        if (focusRecBtn) focusRecBtn.textContent = 'Record';
        return;
      }
      const parts = [];
      if (e.ctrlKey) parts.push('ctrl');
      if (e.altKey) parts.push('alt');
      if (e.shiftKey) parts.push('shift');
      if (e.metaKey) parts.push('super');
      const keyMap = { ArrowLeft: 'Left', ArrowRight: 'Right', ArrowUp: 'Up', ArrowDown: 'Down', ' ': 'space' };
      const k = keyMap[e.key] || (e.key.length === 1 ? e.key.toLowerCase() : e.key);
      parts.push(k);
      $('#focus-action-data').value = parts.join('+');
      state.recordingFocusKeys = false;
      if (focusRecBtn) focusRecBtn.textContent = 'Record';
      return;
    }
    if (e.key === 'Escape' && state.focusedCid != null && !$('dialog[open]')) {
      closeControlInspector();
    }
  }, true);

  $('#btn-focus-apply')?.addEventListener('click', async () => {
    if (state.focusedCid == null) return;
    const at = $('#focus-action-type').value;
    const ad = at === 'remap'
      ? $('#focus-remap-target').value
      : (['keystroke', 'command', 'application', 'dpi_set', 'haptic'].includes(at) ? $('#focus-action-data').value.trim() : '');
    try {
      await rpc('applyButtonBinding', {
        cid: state.focusedCid,
        scope: state.buttonScope,
        action_type: at,
        action_data: ad,
      });
      studio3d?.triggerFloorBurst(1.05, 0.35);
      toast(`Updated ${BUTTON_META[state.focusedCid]?.name || 'control'} → ${FRIENDLY_ACTION[at] || at}`);
      await refreshSnapshot();
      if (state.focusedCid != null) openControlInspector(state.focusedCid);
    } catch (e) { toast(e.message); }
  });

  $('#btn-focus-reset-default')?.addEventListener('click', async () => {
    if (state.focusedCid == null) return;
    try {
      await rpc('applyButtonBinding', {
        cid: state.focusedCid,
        scope: state.buttonScope,
        action_type: 'default',
        action_data: '',
      });
      studio3d?.triggerFloorBurst(0.85, 0.0);
      toast(`Reset ${BUTTON_META[state.focusedCid]?.name || 'control'} to factory default`);
      await refreshSnapshot();
      if (state.focusedCid != null) openControlInspector(state.focusedCid);
    } catch (e) { toast(e.message); }
  });

  // Direct Focus Inspector -> Horizontal Thumb Wheel (0x2150) 6× HD & Actions live sync!
  for (const pill of $$('#focus-tw-mode-pills .tw-mode-pill')) {
    pill.addEventListener('click', () => {
      commitThumbwheelTuning({ mode: pill.dataset.focusTwMode });
    });
  }
  $('#focus-tw-invert')?.addEventListener('change', (e) => {
    commitThumbwheelTuning({ invert: e.target.checked });
  });
  for (const chip of $$('#focus-tw-hd-presets .studio-chip')) {
    chip.addEventListener('click', () => {
      commitThumbwheelTuning({
        mode: 'hd_scroll',
        speed: Number(chip.dataset.speed),
        smoothness: Number(chip.dataset.smooth),
        accel: Number(chip.dataset.accel),
      });
    });
  }
  const onFocusTwHdSlider = () => {
    const sp = Number($('#focus-tw-speed').value);
    const sm = Number($('#focus-tw-smooth').value);
    const ac = Number($('#focus-tw-accel').value);
    updateThumbwheelUI({
      mode: 'hd_scroll',
      invert: state.twInvert,
      speed: sp,
      smoothness: sm,
      accel: ac,
      hires: state.twHires,
      haptic_detent: state.twHapticDetent,
    });
    debounce('twTuning', 110, () => commitThumbwheelTuning({ mode: 'hd_scroll', speed: sp, smoothness: sm, accel: ac }));
  };
  $('#focus-tw-speed')?.addEventListener('input', onFocusTwHdSlider);
  $('#focus-tw-smooth')?.addEventListener('input', onFocusTwHdSlider);
  $('#focus-tw-accel')?.addEventListener('input', onFocusTwHdSlider);
  $('#focus-tw-hires')?.addEventListener('change', (e) => {
    commitThumbwheelTuning({ mode: 'hd_scroll', hires: e.target.checked });
  });
  $('#focus-tw-haptic-detent')?.addEventListener('change', (e) => {
    commitThumbwheelTuning({ mode: 'hd_scroll', haptic_detent: e.target.checked });
  });
  $('#focus-tw-haptic-density')?.addEventListener('change', (e) => {
    commitThumbwheelTuning({ mode: 'hd_scroll', haptic_density: Number(e.target.value) });
  });
  $('#focus-tw-haptic-pattern')?.addEventListener('change', (e) => {
    const pat = Number(e.target.value);
    commitThumbwheelTuning({ mode: 'hd_scroll', haptic_pattern: pat });
    rpc('triggerHaptic', { pattern: pat }).catch(() => {});
  });

  const saveFocusTwCfg = () => {
    const payload = {
      preset: $('#focus-tw-preset').value,
      positive_type: $('#focus-tw-pos-type').value,
      positive_data: $('#focus-tw-pos-data').value,
      negative_type: $('#focus-tw-neg-type').value,
      negative_data: $('#focus-tw-neg-data').value,
      step: Number($('#focus-tw-step').value),
      haptic_tick: $('#focus-tw-haptic').checked,
      micro_haptics: $('#focus-tw-micro-haptics') ? $('#focus-tw-micro-haptics').checked : true,
      haptic_pattern: $('#focus-tw-action-pattern') ? Number($('#focus-tw-action-pattern').value) : 1,
    };
    // Keep Scroll tab mirror inputs synced
    $('#tw-preset').value = payload.preset;
    $('#tw-pos-type').value = payload.positive_type;
    $('#tw-pos-data').value = payload.positive_data;
    $('#tw-neg-type').value = payload.negative_type;
    $('#tw-neg-data').value = payload.negative_data;
    $('#tw-step-slider').value = String(payload.step);
    $('#tw-step-readout').textContent = formatTwStepLabel(payload.step);
    $('#sw-tw-haptic').checked = payload.haptic_tick;
    if ($('#sw-tw-micro-haptics')) $('#sw-tw-micro-haptics').checked = payload.micro_haptics;
    if ($('#tw-action-pattern')) $('#tw-action-pattern').value = String(payload.haptic_pattern);
    debounce('twCfg', 220, () => {
      rpc('saveThumbwheelConfig', payload).catch((e) => toast(e.message));
    });
  };
  $('#focus-tw-preset')?.addEventListener('change', (e) => {
    const key = e.target.value;
    const preset = state.snapshot?.thumbwheel_presets?.[key];
    if (preset && key !== 'custom') {
      $('#focus-tw-pos-type').value = preset.positive_type;
      $('#focus-tw-pos-data').value = preset.positive_data;
      $('#focus-tw-neg-type').value = preset.negative_type;
      $('#focus-tw-neg-data').value = preset.negative_data;
    }
    studio3d?.pulseThumbWheel(1);
    saveFocusTwCfg();
  });
  for (const id of ['#focus-tw-pos-type', '#focus-tw-pos-data', '#focus-tw-neg-type', '#focus-tw-neg-data']) {
    $(id)?.addEventListener('input', () => { $('#focus-tw-preset').value = 'custom'; saveFocusTwCfg(); });
    $(id)?.addEventListener('change', saveFocusTwCfg);
  }
  $('#focus-tw-haptic')?.addEventListener('change', saveFocusTwCfg);
  $('#focus-tw-micro-haptics')?.addEventListener('change', saveFocusTwCfg);
  $('#focus-tw-action-pattern')?.addEventListener('change', (e) => {
    const pat = Number(e.target.value);
    rpc('triggerHaptic', { pattern: pat }).catch(() => {});
    saveFocusTwCfg();
  });
  $('#focus-tw-step')?.addEventListener('input', (e) => {
    $('#focus-tw-step-readout').textContent = formatTwStepLabel(e.target.value);
    studio3d?.pulseThumbWheel(1);
    saveFocusTwCfg();
  });

  // Reset Camera button also exits control focus smoothly
  $('#btn-reset-cam').addEventListener('click', () => {
    if (state.focusedCid != null) closeControlInspector();
  });

  // Buttons tab
  $('#sel-button-scope').addEventListener('change', (e) => {
    state.buttonScope = e.target.value;
    renderButtonsList();
  });
  $('#btn-reset-all-buttons').addEventListener('click', async () => {
    try {
      await rpc('resetAllButtons', { scope: state.buttonScope });
      toast('Reset all button bindings to default');
      await refreshSnapshot();
    } catch (e) { toast(e.message); }
  });

  // Diagnostics / Lab tab
  $('#btn-probe-features').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = 'Probing 45 features…';
    try {
      const res = await rpc('probeFeatures');
      state.probedFeatures = res.features || [];
      renderProbedFeatures();
      toast(`Probed ${state.probedFeatures.length} HID++ 2.0 features`);
    } catch (err) {
      toast(err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = 'Re-probe Features';
    }
  });
  $('#probe-filter').addEventListener('input', renderProbedFeatures);

  $('#btn-copy-diag').addEventListener('click', async () => {
    const txt = JSON.stringify({ ...state.snapshot, probed_features: state.probedFeatures }, null, 2);
    try {
      await navigator.clipboard.writeText(txt);
      toast('Diagnostics JSON copied to clipboard');
    } catch {
      toast('Clipboard unavailable');
    }
  });

  // Dialog close buttons
  for (const btn of $$('[data-close-dialog]')) {
    btn.addEventListener('click', () => {
      const dlg = document.getElementById(btn.dataset.closeDialog);
      dlg?.close('cancel');
    });
  }

  // Rebind dialog wiring (reading & resetting dialog.returnValue per modern-web-guidance!)
  $('#rebind-type').addEventListener('change', syncRebindFields);

  const recBtn = $('#btn-record-keys');
  recBtn.addEventListener('click', () => {
    state.recordingKeys = !state.recordingKeys;
    recBtn.textContent = state.recordingKeys ? 'Press keys…' : 'Record';
  });
  window.addEventListener('keydown', (e) => {
    if (!state.recordingKeys) return;
    if (['Control', 'Shift', 'Alt', 'Meta'].includes(e.key)) return;
    e.preventDefault();
    e.stopPropagation();
    if (e.key === 'Escape') {
      state.recordingKeys = false;
      recBtn.textContent = 'Record';
      return;
    }
    const parts = [];
    if (e.ctrlKey) parts.push('ctrl');
    if (e.altKey) parts.push('alt');
    if (e.shiftKey) parts.push('shift');
    if (e.metaKey) parts.push('super');
    const keyMap = { ArrowLeft: 'Left', ArrowRight: 'Right', ArrowUp: 'Up', ArrowDown: 'Down', ' ': 'space' };
    const k = keyMap[e.key] || (e.key.length === 1 ? e.key.toLowerCase() : e.key);
    parts.push(k);
    $('#rebind-data').value = parts.join('+');
    state.recordingKeys = false;
    recBtn.textContent = 'Record';
  }, true);

  const rebindDlg = $('#dlg-rebind');
  rebindDlg.addEventListener('close', async () => {
    state.recordingKeys = false;
    recBtn.textContent = 'Record';
    const rv = rebindDlg.returnValue;
    rebindDlg.returnValue = '';
    if (rv !== 'apply' || state.rebindCid == null) return;
    const at = $('#rebind-type').value;
    const ad = at === 'remap'
      ? $('#rebind-target').value
      : (['keystroke', 'command', 'application', 'dpi_set', 'haptic'].includes(at) ? $('#rebind-data').value.trim() : '');
    try {
      await rpc('applyButtonBinding', {
        cid: state.rebindCid,
        scope: state.buttonScope,
        action_type: at,
        action_data: ad,
      });
      toast(`Updated ${BUTTON_META[state.rebindCid]?.name || 'control'} → ${FRIENDLY_ACTION[at] || at}`);
      await refreshSnapshot();
    } catch (e) { toast(e.message); }
  });

  const promptDlg = $('#dlg-prompt');
  promptDlg.addEventListener('close', async () => {
    const rv = promptDlg.returnValue;
    promptDlg.returnValue = '';
    if (rv !== 'save' || !state.promptCallback) return;
    const val = $('#prompt-input').value.trim();
    const tpl = $('#prompt-template').value;
    const cb = state.promptCallback;
    state.promptCallback = null;
    if (!val) return;
    try { await cb(val, tpl); } catch (e) { toast(e.message); }
  });
}

// ─────────────────────────── Boot ────────────────────────────────────────

async function boot() {
  setupDialogLightDismissFallback();
  buildStaticUI();
  wireEvents();
  startHapticOscilloscope();

  const tooltip = $('#stage-tooltip');
  const pinsLayer = $('#stage-pins');

  studio3d = new MouseStudio3D($('#mx4-canvas'), {
    onHoverButton: (cid, cx, cy) => {
      if (cid == null) {
        tooltip.hidden = true;
        return;
      }
      const meta = BUTTON_META[cid];
      const hexCid = `0x${Number(cid).toString(16).toUpperCase().padStart(4, '0')}`;
      const isTw = Number(cid) === CID.THUMB_WHEEL;
      const label = isTw
        ? formatThumbwheelSummary()
        : formatBindingLabel(cid, getBindingForCid(cid, state.buttonScope));
      $('#tip-title').textContent = meta ? meta.name : `Control ${hexCid}`;
      $('#tip-cid').textContent = hexCid;
      $('#tip-sub').textContent = `${label} · Click to focus & edit`;
      const flipLeft = cx > window.innerWidth - 680;
      tooltip.style.transform = flipLeft ? 'translate(calc(-100% - 16px), -50%)' : 'translate(16px, -50%)';
      tooltip.style.left = `${cx}px`;
      tooltip.style.top = `${cy}px`;
      tooltip.hidden = false;
    },
    onClickButton: (cid) => openControlInspector(cid),
    onClickBackground: () => {
      if (state.focusedCid != null) {
        closeControlInspector();
      }
      if (state.tab !== 'device') {
        switchTab('device', { force: true });
      } else {
        studio3d?.resetCamera();
      }
    },
    onProjectPins: (pins) => {
      if (state.tab !== 'buttons') return;
      if (pinsLayer.childElementCount !== pins.length) {
        pinsLayer.innerHTML = '';
        for (const p of pins) {
          const btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'stage-pin';
          btn.dataset.cid = String(p.cid);
          btn.innerHTML = `<span class="pin-dot"></span><span>${p.name}</span>`;
          btn.addEventListener('click', () => openRebindDialog(p.cid));
          pinsLayer.appendChild(btn);
        }
      }
      const sorted = pins.map((p) => ({ ...p })).sort((a, b) => a.y - b.y);
      for (let i = 1; i < sorted.length; i++) {
        for (let j = 0; j < i; j++) {
          if (Math.abs(sorted[i].x - sorted[j].x) < 112 && Math.abs(sorted[i].y - sorted[j].y) < 30) {
            sorted[i].y = sorted[j].y + 30;
          }
        }
      }
      for (const p of sorted) {
        const el = pinsLayer.querySelector(`[data-cid="${p.cid}"]`);
        if (el) {
          el.style.left = `${p.x}px`;
          el.style.top = `${p.y}px`;
        }
      }
    },
  });

  window.__mx4 = { studio3d, openControlInspector, closeControlInspector };

  // Seamless DOM button-press fallback (merged cleanly with live evdev + D-Bus events!)
  const domBtnToCid = {
    0: CID.LEFT_CLICK,
    1: CID.MIDDLE_CLICK,
    2: CID.RIGHT_CLICK,
    3: CID.BACK,
    4: CID.FORWARD,
  };
  window.addEventListener('pointerdown', (e) => {
    const cid = domBtnToCid[e.button];
    if (cid != null) studio3d?.setDomButtonPressed(cid, true);
  }, { passive: true });
  window.addEventListener('pointerup', (e) => {
    const cid = domBtnToCid[e.button];
    if (cid != null) studio3d?.setDomButtonPressed(cid, false);
  }, { passive: true });
  window.addEventListener('blur', () => {
    for (const cid of Object.values(domBtnToCid)) studio3d?.setDomButtonPressed(cid, false);
  });

  if (studio3d.ambientPaused) {
    $('#btn-toggle-motion').textContent = 'Resume Motion';
  }

  window.__MX4_STUDIO_3D__ = studio3d;
  window.__MX4_STUDIO_UI__ = {
    switchTab,
    openControlInspector,
    closeControlInspector,
    refreshSnapshot,
    state,
  };

  await initBridge();
  await refreshSnapshot();
  setInterval(() => refreshSnapshot().catch(() => {}), 12000);
}

boot();
