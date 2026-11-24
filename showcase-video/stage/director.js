/**
 * MX4 Studio Launch Video V2 — High-Octane 30s 128 BPM Director Engine
 *
 * Choreographs the REAL live MX4 Studio app (3D WebGL2 MX Master 4 + 625-cube floor
 * + live UI panels + 2x HiDPI Cairo Wayland Actions Ring) with relentless editorial
 * pacing, whip-pan/anamorphic impacts, kinetic typography slams, beat-reactive camera
 * micro-recoil, and continuous 3D orbit/crane sweeps locked to 128 BPM (1,800 frames).
 */

import {
  BPM,
  FPS,
  TOTAL_FRAMES,
  beatToFrame,
  beatToSec,
  clamp,
  easeInOutQuart,
  easeOutExpo,
  easeOutQuint,
  easeSnappy,
  frameToBeat,
  frameToSec,
  lerp,
  spring01,
} from '/__showcase/timeline.mjs';

const CID = {
  LEFT_CLICK: 80,
  RIGHT_CLICK: 81,
  MIDDLE_CLICK: 82,
  BACK: 83,
  FORWARD: 86,
  GESTURE: 195,
  SMART_SHIFT: 196,
  THUMB_PAD: 416,
  THUMB_WHEEL: 0x2150,
};

// ─────────────────────────── Procedural Sparks & Embers ──────────────────

class ParticleSystem {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.particles = [];
    this.embers = [];
    this.seed = 2028;
    this.resize();
    // Seed 28 subtle atmospheric drifting micro-embers for cinema depth
    const lw0 = document.documentElement.clientWidth || 1920;
    const lh0 = document.documentElement.clientHeight || 1080;
    for (let i = 0; i < 28; i++) {
      this.embers.push({
        x: this.rand() * lw0,
        y: this.rand() * lh0,
        vy: -14 - this.rand() * 24,
        vx: (this.rand() - 0.5) * 14,
        size: 1.0 + this.rand() * 1.8,
        alpha: 0.14 + this.rand() * 0.28,
        isCopper: i % 3 === 0,
      });
    }
  }

  rand() {
    this.seed = (this.seed * 1664525 + 1013904223) >>> 0;
    return this.seed / 4294967296;
  }

  resize() {
    const dpr = window.devicePixelRatio || 1;
    const lw = document.documentElement.clientWidth || 1920;
    const lh = document.documentElement.clientHeight || 1080;
    this.canvas.width = Math.round(lw * dpr);
    this.canvas.height = Math.round(lh * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  burst(x, y, { count = 24, color = '#ffe0b2', color2 = '#3ce0e8', speed = 320 } = {}) {
    for (let i = 0; i < count; i++) {
      const a = this.rand() * Math.PI * 2;
      const sp = speed * (0.25 + this.rand() * 0.90);
      this.particles.push({
        x, y,
        vx: Math.cos(a) * sp,
        vy: Math.sin(a) * sp,
        life: 0,
        maxLife: 0.28 + this.rand() * 0.36,
        size: 1.5 + this.rand() * 2.8,
        color: i % 2 === 0 ? color : color2,
      });
    }
  }

  step(dt, beatPulse = 0) {
    const ctx = this.ctx;
    const W = document.documentElement.clientWidth || 1920;
    const H = document.documentElement.clientHeight || 1080;
    ctx.clearRect(0, 0, W, H);
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';

    // Subtle atmospheric embers pulsing gently with the 128 BPM kick
    for (const e of this.embers) {
      e.x += e.vx * dt;
      e.y += (e.vy - beatPulse * 35) * dt;
      if (e.y < -10) { e.y = H + 10; e.x = this.rand() * W; }
      if (e.x < -10) e.x = W + 10;
      if (e.x > W + 10) e.x = -10;
      ctx.fillStyle = e.isCopper ? '#e8a864' : '#3ce0e8';
      ctx.globalAlpha = e.alpha * (0.65 + beatPulse * 0.55);
      ctx.beginPath();
      ctx.arc(e.x, e.y, e.size, 0, Math.PI * 2);
      ctx.fill();
    }

    // Impact sparks
    for (let i = this.particles.length - 1; i >= 0; i--) {
      const p = this.particles[i];
      p.life += dt;
      if (p.life >= p.maxLife) {
        this.particles.splice(i, 1);
        continue;
      }
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.vx *= Math.exp(-5.0 * dt);
      p.vy *= Math.exp(-5.0 * dt);
      const u = p.life / p.maxLife;
      const alpha = (1 - u) * (1 - u);
      ctx.fillStyle = p.color;
      ctx.globalAlpha = alpha * 0.92;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size * (1 - u * 0.45), 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }
}

// ─────────────────────────── Director Overlay DOM ────────────────────────

function mountDirectorDOM() {
  document.body.classList.add('showcase-mode');
  const params = new URLSearchParams(window.location.search);
  const mode = params.get('mode') || 'landscape';
  if (mode === 'vertical') document.body.classList.add('mode-vertical');

  const html = `
    <div id="vid-vignette"></div>
    <div class="vid-bar" id="vid-bar-top"></div>
    <div class="vid-bar" id="vid-bar-bot"></div>
    <canvas id="vid-particles"></canvas>

    <!-- Scene 0: High-Impact Cold Open Slams -->
    <div id="vid-cold-open">
      <div class="cold-eyebrow" id="cold-eyebrow">LOGITECH MX MASTER 4</div>
      <div class="cold-lines">
        <div class="cold-mask"><span class="cold-word" id="cold-w1">ON LINUX.</span></div>
        <div class="cold-mask"><span class="cold-word is-copper" id="cold-w2">UNLOCKED.</span></div>
      </div>
      <div class="cold-rule" id="cold-rule"></div>
      <div class="cold-telemetry" id="cold-telemetry">HID++ 2.0 · 8,000 DPI · 144 Hz MAGSPEED · 15 LRA HAPTICS</div>
    </div>

    <!-- High-Energy Kinetic Impact Stamp -->
    <div id="vid-slam">
      <span class="slam-kicker" id="slam-kicker">DARKFIELD</span>
      <span class="slam-headline" id="slam-headline">8,000 DPI</span>
    </div>

    <!-- Feature Showcase Lower-Third Callout -->
    <div id="vid-callout">
      <div class="callout-top">
        <span class="callout-pip" id="callout-pip"></span>
        <span class="callout-eyebrow" id="callout-eyebrow">FEATURE</span>
      </div>
      <div class="callout-title" id="callout-title">Title</div>
      <div class="callout-sub" id="callout-sub">Subtitle</div>
    </div>

    <!-- Scene 4: Real 60 FPS Wayland Cairo Actions Ring Layer -->
    <div id="vid-cairo-layer">
      <div class="cairo-badge">LIVE WAYLAND LAYER-SHELL · 60 FPS CAIRO OVERLAY</div>
      <img id="vid-cairo-img" alt="Actions Ring Overlay" />
      <div class="cairo-caption">Hold Thumb Pad · Flick · Instant Confirm</div>
    </div>

    <!-- Scene 6: Brand Lockup & CTA End Card -->
    <div id="vid-endcard">
      <div class="endcard-box">
        <div class="endcard-kicker" id="end-kicker"><span class="endcard-dot"></span><span>OPEN SOURCE HARDWARE STUDIO</span></div>
        <div class="endcard-logo" id="end-logo">MX4 STUDIO</div>
        <div class="endcard-tagline" id="end-tag">Precision Linux Control for Logitech MX Master 4.</div>
        <div class="endcard-pills" id="end-pills">
          <span class="endcard-pill">HID++ 2.0 Native</span>
          <span class="endcard-pill">15 LRA Haptics</span>
          <span class="endcard-pill">60 FPS Actions Ring</span>
          <span class="endcard-pill">144 Hz MagSpeed</span>
        </div>
        <div class="endcard-cta" id="end-cta">
          <span class="endcard-cta-tag">MIT</span>
          <span>github.com/timmy16744/mx4control</span>
        </div>
      </div>
    </div>

    <!-- Choreographed Custom Studio Pointer + Click Ripple -->
    <div id="vid-cursor-ripple"></div>
    <svg id="vid-cursor" viewBox="0 0 28 28" fill="none">
      <path d="M4.5 3.5L22.5 13.8L14.2 16.0L10.6 23.6L4.5 3.5Z" fill="#ffffff" stroke="#0a0d14" stroke-width="2.1" stroke-linejoin="round"/>
    </svg>

    <div id="vid-flare"></div>
    <div id="vid-flash"></div>
  `;
  const wrap = document.createElement('div');
  wrap.innerHTML = html;
  while (wrap.firstElementChild) document.body.appendChild(wrap.firstElementChild);

  return { mode };
}

function elCenter(selector, fallback = { x: 960, y: 540 }) {
  const el = typeof selector === 'string' ? document.querySelector(selector) : selector;
  if (!el) return fallback;
  const r = el.getBoundingClientRect();
  if (r.width === 0 && r.height === 0) return fallback;
  return { x: r.left + r.width * 0.5, y: r.top + r.height * 0.5 };
}

// ─────────────────────────── V2 Director State Machine ───────────────────

class ShowcaseDirectorV2 {
  constructor() {
    const { mode } = mountDirectorDOM();
    this.mode = mode;
    this.isVertical = mode === 'vertical';
    this.particles = new ParticleSystem(document.getElementById('vid-particles'));

    this.shell = document.querySelector('.studio-shell');
    this.topbar = document.querySelector('.studio-topbar');
    this.inspector = document.querySelector('.inspector-shell');
    this.stageIdentity = document.querySelector('.stage-identity');
    this.stageMetrics = document.querySelector('.stage-metrics');
    this.stageControls = document.querySelector('.stage-controls');

    this.firedEvents = new Set();
    this.currentFrame = -1;

    this.cursorX = (document.documentElement.clientWidth || 1920) * 0.55;
    this.cursorY = (document.documentElement.clientHeight || 1080) * 0.55;
    this.cursorVis = 0;
    this.rippleAge = 99;
    this.rippleX = 0;
    this.rippleY = 0;
    this.flashAge = 99;
    this.flareAge = 99;
    this.flareY = 50;

    this.callout = { visible: false, startFrame: 0, endFrame: 0 };
    this.slam = { visible: false, startFrame: 0, endFrame: 0 };

    // V2 Cairo ring sequence (Beats 44..50 @ 128 BPM)
    this.cairoStartFrame = beatToFrame(44.0);
    this.cairoEndFrame = beatToFrame(50.0);
    this.cairoImg = document.getElementById('vid-cairo-img');
    this.cairoLayer = document.getElementById('vid-cairo-layer');
    this._lastCairoIdx = -1;

    this._buildEventSchedule();
  }

  triggerImpact({ flash = true, flare = true, flareY = 50, color = '#3ce0e8', burstX = null, burstY = null } = {}) {
    if (flash) this.flashAge = 0;
    if (flare) {
      this.flareAge = 0;
      this.flareY = flareY;
      const fl = document.getElementById('vid-flare');
      if (fl) {
        fl.style.background = `linear-gradient(90deg, transparent 0%, ${color}bb 28%, rgba(255,248,236,0.98) 50%, ${color}bb 72%, transparent 100%)`;
        fl.style.boxShadow = `0 0 38px 8px ${color}88, 0 0 80px 16px ${color}44`;
      }
    }
    if (burstX != null && burstY != null) {
      this.particles.burst(burstX, burstY, { count: 28, color: '#ffffff', color2: color, speed: 360 });
    }
  }

  showSlam(startBeat, endBeat, kicker, headline, color = '#3ce0e8') {
    this.slam = { visible: true, startFrame: beatToFrame(startBeat), endFrame: beatToFrame(endBeat) };
    const k = document.getElementById('slam-kicker');
    const h = document.getElementById('slam-headline');
    k.textContent = kicker;
    k.style.color = color;
    h.textContent = headline;
  }

  showCallout(startBeat, endBeat, eyebrow, title, sub, accent = '#3ce0e8') {
    this.callout = { visible: true, startFrame: beatToFrame(startBeat), endFrame: beatToFrame(endBeat) };
    document.getElementById('callout-eyebrow').textContent = eyebrow;
    document.getElementById('callout-title').textContent = title;
    document.getElementById('callout-sub').textContent = sub;
    const pip = document.getElementById('callout-pip');
    pip.style.background = accent;
    pip.style.boxShadow = `0 0 14px ${accent}`;
  }

  clickAndRipple(selector, color = '#ffe0b2') {
    const el = document.querySelector(selector);
    if (!el) return;
    const pt = elCenter(el);
    this.cursorX = pt.x;
    this.cursorY = pt.y;
    this.rippleX = pt.x;
    this.rippleY = pt.y;
    this.rippleAge = 0;
    const rip = document.getElementById('vid-cursor-ripple');
    rip.style.borderColor = color;
    rip.style.boxShadow = `0 0 24px ${color}`;
    el.click();
    this.particles.burst(pt.x, pt.y, { count: 22, color, color2: '#3ce0e8', speed: 240 });
  }

  _snap3DToTarget() {
    const s3 = window.__MX4_STUDIO_3D__;
    if (!s3) return;
    s3.cam = { ...s3.camTarget };
    s3.modeWeights = { ...s3.modeTargets };
  }

  _buildEventSchedule() {
    this.events = [
      // ── Scene 0: Cold Open Impact (Beats 0..8) ──
      {
        beat: 0.0,
        fn: () => {
          const s3 = window.__MX4_STUDIO_3D__;
          if (s3) {
            s3.setTab('device');
            s3.modeWeights.cyanPool = 1.0;
            s3.camTarget = this.isVertical
              ? { az: 0.58, pol: 1.02, dist: 6.2, tx: 0.08, ty: 0.44, tz: 0.02, fov: 40 }
              : { az: 0.46, pol: 1.06, dist: 5.8, tx: 0.10, ty: 0.44, tz: 0.02, fov: 27 };
            s3.cam = { ...s3.camTarget };
            s3.triggerFloorBurst(1.65, 0.0);
          }
          const lw = document.documentElement.clientWidth || 1920;
          const lh = document.documentElement.clientHeight || 1080;
          this.triggerImpact({ flash: true, flare: true, flareY: 56, color: '#3ce0e8', burstX: lw * 0.5, burstY: lh * 0.60 });
        },
      },
      { beat: 4.0, fn: () => this.triggerImpact({ flash: false, flare: true, flareY: 44, color: '#3ce0e8' }) },
      { beat: 6.0, fn: () => this.triggerImpact({ flash: true, flare: true, flareY: 50, color: '#e8a864' }) },

      // ── Scene 1: Darkfield 8,000 DPI & Live Telemetry (Beats 8..18) ──
      {
        beat: 8.0,
        fn: () => {
          const s3 = window.__MX4_STUDIO_3D__;
          if (s3) {
            s3.setTab('device');
            s3.triggerFloorBurst(1.4, 0.25);
          }
          this.triggerImpact({ flash: true, flare: true, flareY: 50, color: '#3ce0e8' });
          this.showSlam(8.1, 12.2, 'OPTICAL SENSOR · 0x2201', '8,000 DPI', '#3ce0e8');
          this.showCallout(8.2, 17.6, 'DARKFIELD 8,000 DPI · 60 HZ TELEMETRY', 'Live Optical Matrix & Physical Mirroring', 'Every DPI step, glide, and hinged click reflects live on the 3D CAD mouse.', '#3ce0e8');
        },
      },
      { beat: 10.0, fn: () => this.clickAndRipple('#dpi-chips [data-dpi="2400"]', '#3ce0e8') },
      { beat: 12.0, fn: () => this.clickAndRipple('#dpi-chips [data-dpi="4000"]', '#3ce0e8') },
      {
        beat: 14.0,
        fn: () => {
          this.clickAndRipple('#dpi-chips [data-dpi="8000"]', '#ffe0b2');
          this.triggerImpact({ flash: false, flare: true, flareY: 64, color: '#3ce0e8' });
        },
      },
      { beat: 15.0, fn: () => window.__MX4_STUDIO_3D__?.setDomButtonPressed(CID.LEFT_CLICK, true) },
      { beat: 15.6, fn: () => window.__MX4_STUDIO_3D__?.setDomButtonPressed(CID.LEFT_CLICK, false) },
      { beat: 16.5, fn: () => window.__MX4_STUDIO_3D__?.setDomButtonPressed(CID.RIGHT_CLICK, true) },
      { beat: 17.1, fn: () => window.__MX4_STUDIO_3D__?.setDomButtonPressed(CID.RIGHT_CLICK, false) },

      // ── Scene 2: MagSpeed Flywheel & 144 Hz Smooth (Beats 18..28) ──
      {
        beat: 18.0,
        fn: () => {
          this.clickAndRipple('.dock-btn[data-tab="scroll"]', '#3ce0e8');
          this.triggerImpact({ flash: true, flare: true, flareY: 42, color: '#3ce0e8' });
          this.showSlam(18.1, 22.5, 'MAGSPEED · 0x2111', '144 Hz FLYWHEEL', '#3ce0e8');
          this.showCallout(18.2, 27.6, 'MAGSPEED · 0x2111 · 0x2121', 'Electromagnetic Flywheel & HD Smooth', 'Free-Spin at 1,000 lines/sec, tunable torque & custom S-curve feel.', '#3ce0e8');
        },
      },
      {
        beat: 20.0,
        fn: () => {
          this.clickAndRipple('.mode-pill[data-scroll-mode="free"]', '#3ce0e8');
          window.__MX4_STUDIO_3D__?.pulseWheel(1);
        },
      },
      {
        beat: 23.0,
        fn: () => {
          const pane = document.getElementById('inspector-pane');
          if (pane) pane.scrollTop = 270;
          this.clickAndRipple('#scroll-tuning-presets .studio-chip:nth-child(3)', '#3ce0e8');
          window.__MX4_STUDIO_3D__?.pulseWheel(1);
        },
      },
      {
        beat: 25.0,
        fn: () => {
          this.clickAndRipple('#scroll-tuning-presets .studio-chip:nth-child(4)', '#ffe0b2');
          window.__MX4_STUDIO_3D__?.pulseWheel(1);
        },
      },

      // ── Scene 3: LRA Haptics Cutaway & Force Pad (Beats 28..38) ──
      {
        beat: 28.0,
        fn: () => {
          this.clickAndRipple('.dock-btn[data-tab="haptics"]', '#e8a864');
          this.triggerImpact({ flash: true, flare: true, flareY: 52, color: '#e8a864' });
          this.showSlam(28.1, 32.2, 'LRA ACTUATOR · 0x19B0', '15 WAVEFORMS', '#e8a864');
          this.showCallout(28.2, 37.6, 'LRA HAPTICS · 0x19B0 · FORCE PAD 0x19C0', 'Smoked-Glass Cutaway & Force Sensor', 'Real copper oscilloscope, 15 waveforms & tunable thumb-pad actuation.', '#e8a864');
        },
      },
      { beat: 30.0, fn: () => this.clickAndRipple('.feel-pill[data-feel-wave="2"]', '#ffe0b2') },
      {
        beat: 32.0,
        fn: () => {
          this.clickAndRipple('.feel-pill[data-feel-wave="3"]', '#e8a864');
          this.triggerImpact({ flash: false, flare: true, flareY: 54, color: '#e8a864' });
        },
      },
      {
        beat: 34.0,
        fn: () => {
          const pane = document.getElementById('inspector-pane');
          if (pane) pane.scrollTop = 340;
          this.clickAndRipple('.wave-card[data-wave-id="10"]', '#ffe0b2');
          window.__MX4_MOCK_EMIT__('buttonState', { cids: [CID.THUMB_PAD] });
        },
      },
      { beat: 35.4, fn: () => window.__MX4_MOCK_EMIT__('buttonState', { cids: [] }) },

      // ── Scene 4: Actions Ring — 1-Beat Theme Morphs + Real 60fps Wayland Cairo (Beats 38..50) ──
      {
        beat: 38.0,
        fn: () => {
          this.clickAndRipple('.dock-btn[data-tab="ring"]', '#e8a864');
          this.triggerImpact({ flash: true, flare: true, flareY: 38, color: '#2ae4f0' });
          this.showSlam(38.1, 41.2, 'ACTIONS RING STUDIO', '6 THEMES · 8 PRESETS', '#2ae4f0');
          this.showCallout(38.2, 43.8, 'ACTIONS RING · 3D & WAYLAND SYNC', 'Instant Theme Morphs & 1-Click Presets', 'Every palette morphs the 3D hologram, cube floor & live Wayland overlay.', '#2ae4f0');
        },
      },
      // 1-beat punchy theme color hits!
      { beat: 40.0, fn: () => { this.clickAndRipple('.ring-theme-card:nth-child(2)', '#2ae4f0'); window.__MX4_STUDIO_3D__?.setSelectedRingSlice(1); } },
      { beat: 41.0, fn: () => { this.clickAndRipple('.ring-theme-card:nth-child(4)', '#ff9d3b'); window.__MX4_STUDIO_3D__?.setSelectedRingSlice(3); } },
      { beat: 42.0, fn: () => { this.clickAndRipple('.ring-theme-card:nth-child(5)', '#34e6a4'); window.__MX4_STUDIO_3D__?.setSelectedRingSlice(5); } },
      {
        beat: 43.0,
        fn: () => {
          const pane = document.getElementById('inspector-pane');
          if (pane) pane.scrollTop = 260;
          this.clickAndRipple('.ring-theme-card:nth-child(6)', '#b87dff');
          window.__MX4_STUDIO_3D__?.setSelectedRingSlice(7);
        },
      },
      { beat: 44.0, fn: () => this.triggerImpact({ flash: true, flare: true, flareY: 50, color: '#2ae4f0' }) },
      {
        beat: 49.0,
        fn: () => {
          const lw = document.documentElement.clientWidth || 1920;
          const lh = document.documentElement.clientHeight || 1080;
          this.triggerImpact({ flash: true, flare: true, flareY: 50, color: '#b0fbff', burstX: lw * 0.5, burstY: lh * 0.5 });
        },
      },

      // ── Scene 5: High-Adrenaline 1-Beat Climax Montage (Beats 50..56) ──
      {
        beat: 50.0,
        fn: () => {
          document.querySelector('.ring-theme-card:nth-child(1)')?.click();
          window.__MX4_STUDIO_UI__?.switchTab('device');
          this._snap3DToTarget();
          if (window.__MX4_STUDIO_3D__) window.__MX4_STUDIO_3D__.hoveredCid = CID.THUMB_WHEEL;
          this.triggerImpact({ flash: true, flare: false, color: '#ffffff' });
          this.showCallout(50.0, 50.95, 'WHITE SILHOUETTE HOVER', 'Click Any Physical Control', 'Precision viewpoint highlight on every button & wheel.', '#ffffff');
        },
      },
      {
        beat: 51.0,
        fn: () => {
          if (window.__MX4_STUDIO_3D__) window.__MX4_STUDIO_3D__.hoveredCid = null;
          window.__MX4_STUDIO_UI__?.openControlInspector(CID.THUMB_WHEEL);
          this._snap3DToTarget();
          window.__MX4_STUDIO_3D__?.applyThumbwheelDelta(30, 1);
          this.triggerImpact({ flash: true, flare: true, flareY: 46, color: '#ffffff' });
          this.showCallout(51.0, 51.95, 'DIRECT CONTROL INSPECTOR', 'Instant Macro Camera Focus', 'Live CNC Thumb Wheel tuning & PipeWire volume bindings.', '#3ce0e8');
        },
      },
      {
        beat: 52.0,
        fn: () => {
          window.__MX4_STUDIO_UI__?.closeControlInspector();
          window.__MX4_STUDIO_UI__?.switchTab('diagnostics');
          document.getElementById('btn-probe-features')?.click();
          this._snap3DToTarget();
          this.triggerImpact({ flash: true, flare: false, color: '#3ce0e8' });
          this.showCallout(52.0, 52.95, 'HARDWARE LAB · X-RAY CAD', '45 Native HID++ 2.0 Features', 'Live firmware probe & zero-compromise Linux diagnostics.', '#3ce0e8');
        },
      },
      {
        beat: 53.0,
        fn: () => {
          window.__MX4_STUDIO_UI__?.switchTab('scroll');
          this._snap3DToTarget();
          window.__MX4_STUDIO_3D__?.pulseWheel(1);
          this.triggerImpact({ flash: true, flare: true, flareY: 44, color: '#3ce0e8' });
          this.showCallout(53.0, 53.95, 'MAGSPEED FLYWHEEL', '1,000 Lines / Sec Free-Spin', 'CNC steel flywheel with live electromagnetic flux.', '#3ce0e8');
        },
      },
      {
        beat: 54.0,
        fn: () => {
          window.__MX4_STUDIO_UI__?.switchTab('haptics');
          this._snap3DToTarget();
          window.__MX4_STUDIO_3D__?.triggerHapticVisual(3);
          this.triggerImpact({ flash: true, flare: true, flareY: 52, color: '#e8a864' });
          this.showCallout(54.0, 54.95, 'LRA HAPTICS · 0x19B0', 'Feel Every Click & Detent', 'Molten-copper acoustic shockwaves in real time.', '#e8a864');
        },
      },
      {
        beat: 55.0,
        fn: () => {
          window.__MX4_STUDIO_UI__?.switchTab('ring');
          document.querySelector('.ring-theme-card:nth-child(6)')?.click();
          this._snap3DToTarget();
          window.__MX4_STUDIO_3D__?.setSelectedRingSlice(2);
          this.triggerImpact({ flash: true, flare: true, flareY: 42, color: '#b87dff' });
          this.showCallout(55.0, 55.9, 'ACTIONS RING · ULTRAVIOLET', 'Zero Compromise.', '60 FPS spatial hardware control on Linux.', '#b87dff');
        },
      },

      // ── Scene 6: Huge Beat 56 Hero Drop & Brand Lockup (Beats 56..64) ──
      {
        beat: 56.0,
        fn: () => {
          document.querySelector('.ring-theme-card:nth-child(1)')?.click();
          window.__MX4_STUDIO_UI__?.switchTab('device');
          const s3 = window.__MX4_STUDIO_3D__;
          if (s3) {
            s3.setHardwareState({ dpi: 2400 });
            s3.camTarget = this.isVertical
              ? { az: 0.72, pol: 1.06, dist: 7.2, tx: 0.12, ty: 0.44, tz: -0.02, fov: 40 }
              : { az: 0.74, pol: 1.12, dist: 7.25, tx: 0.16, ty: 0.44, tz: -0.04, fov: 27 };
            s3.cam = { ...s3.camTarget };
            s3.modeWeights = { ...s3.modeTargets };
            s3.triggerFloorBurst(1.65, 0.35);
          }
          this.callout.visible = false;
          this.slam.visible = false;
          const lw = document.documentElement.clientWidth || 1920;
          const lh = document.documentElement.clientHeight || 1080;
          this.triggerImpact({
            flash: true,
            flare: true,
            flareY: 50,
            color: '#ffe0b2',
            burstX: lw * (this.isVertical ? 0.5 : 0.68),
            burstY: lh * 0.5,
          });
        },
      },
    ].map((e, i) => ({ ...e, id: i, frame: beatToFrame(e.beat) }));
  }

  _updateCursorPath(beat) {
    const stops = [
      { b: 8.6,  sel: '#dpi-chips [data-dpi="1000"]', vis: 1 },
      { b: 9.8,  sel: '#dpi-chips [data-dpi="2400"]', vis: 1 },
      { b: 11.8, sel: '#dpi-chips [data-dpi="4000"]', vis: 1 },
      { b: 13.8, sel: '#dpi-chips [data-dpi="8000"]', vis: 1 },
      { b: 14.9, pt: { x: window.innerWidth * 0.27, y: window.innerHeight * 0.44 }, vis: 1 },
      { b: 17.8, sel: '.dock-btn[data-tab="scroll"]', vis: 1 },
      { b: 19.8, sel: '.mode-pill[data-scroll-mode="free"]', vis: 1 },
      { b: 22.8, sel: '#scroll-tuning-presets .studio-chip:nth-child(3)', vis: 1 },
      { b: 24.8, sel: '#scroll-tuning-presets .studio-chip:nth-child(4)', vis: 1 },
      { b: 27.8, sel: '.dock-btn[data-tab="haptics"]', vis: 1 },
      { b: 29.8, sel: '.feel-pill[data-feel-wave="2"]', vis: 1 },
      { b: 31.8, sel: '.feel-pill[data-feel-wave="3"]', vis: 1 },
      { b: 33.8, sel: '.wave-card[data-wave-id="10"]', vis: 1 },
      { b: 37.8, sel: '.dock-btn[data-tab="ring"]', vis: 1 },
      { b: 39.8, sel: '.ring-theme-card:nth-child(2)', vis: 1 },
      { b: 40.8, sel: '.ring-theme-card:nth-child(4)', vis: 1 },
      { b: 41.8, sel: '.ring-theme-card:nth-child(5)', vis: 1 },
      { b: 42.8, sel: '.ring-theme-card:nth-child(6)', vis: 1 },
      { b: 44.0, pt: { x: window.innerWidth * 0.5, y: window.innerHeight * 0.5 }, vis: 0 },
    ];

    const curEl = document.getElementById('vid-cursor');
    if (beat < 8.4 || beat >= 43.9) {
      this.cursorVis = lerp(this.cursorVis, 0, 0.35);
      curEl.style.opacity = String(this.cursorVis.toFixed(3));
      return;
    }

    let prev = stops[0];
    let next = stops[stops.length - 1];
    for (let i = 0; i < stops.length - 1; i++) {
      if (beat >= stops[i].b && beat <= stops[i + 1].b) {
        prev = stops[i];
        next = stops[i + 1];
        break;
      }
    }
    const p0 = prev.pt || elCenter(prev.sel, { x: this.cursorX, y: this.cursorY });
    const p1 = next.pt || elCenter(next.sel, { x: this.cursorX, y: this.cursorY });
    const span = Math.max(0.001, next.b - prev.b);
    const moveU = easeInOutQuart(clamp(((beat - prev.b) / span) / 0.85, 0, 1));
    this.cursorX = lerp(p0.x, p1.x, moveU);
    this.cursorY = lerp(p0.y, p1.y, moveU) + Math.sin(moveU * Math.PI) * -18;
    this.cursorVis = lerp(this.cursorVis, next.vis, 0.35);

    const pressScale = this.rippleAge < 0.12 ? 0.84 : 1.0;
    curEl.style.opacity = String(this.cursorVis.toFixed(3));
    curEl.style.transform = `translate3d(${this.cursorX - 4}px, ${this.cursorY - 3}px, 0) scale(${pressScale})`;
  }

  _updateSceneVisuals(frame, sec, beat) {
    const dt = 1 / FPS;
    const s3 = window.__MX4_STUDIO_3D__;

    // Beat-reactive kick drum pulse (Beats 8..55, exact 128 BPM phase!)
    const inGroove = beat >= 8.0 && beat < 55.5;
    const beatFrac = beat - Math.floor(beat);
    const beatPulse = inGroove ? Math.exp(-beatFrac * 9.0) : 0.0;

    // 1. Live mouse glide during Scene 1 (Beats 9..17.5)
    if (beat >= 9.0 && beat < 17.5 && s3) {
      s3.applyLiveTelemetry({ dx: Math.sin(sec * 3.1) * 12.0, dy: Math.cos(sec * 2.2) * 8.0 });
    }

    // 2. Cinema Letterbox Bars (40px in Cold Open -> snap open on Beat 8 -> sleek 26px on Finale!)
    const barOpen = easeOutQuint(clamp((beat - 7.0) / 1.4, 0, 1));
    const barEnd = easeOutQuint(clamp((beat - 55.6) / 1.2, 0, 1));
    const barH = this.isVertical ? 0 : Math.round(lerp(42, 0, barOpen) + barEnd * 26);
    document.getElementById('vid-bar-top').style.height = `${barH}px`;
    document.getElementById('vid-bar-bot').style.height = `${barH}px`;

    // 3. UI Chrome Entrance (Beat 7.4 -> 8.6) & Clean Finale Exit (Beat 55.5 -> 56.4)
    const chromeIn = easeSnappy(clamp((beat - 7.3) / 1.2, 0, 1));
    const chromeOut = beat < 55.6 ? 1.0 : easeOutQuint(clamp(1.0 - (beat - 55.6) / 0.8, 0, 1));
    const chromeAlpha = chromeIn * chromeOut;

    if (this.topbar) {
      this.topbar.style.opacity = String(chromeAlpha.toFixed(3));
      this.topbar.style.transform = `translateY(${((1 - chromeAlpha) * -28).toFixed(1)}px)`;
    }
    if (this.inspector) {
      this.inspector.style.opacity = String(chromeAlpha.toFixed(3));
      const panelTiltY = this.isVertical ? 0 : (-2.0 + Math.sin(sec * 0.75) * 1.5);
      const slideX = this.isVertical ? 0 : (1 - chromeAlpha) * 90;
      const slideY = this.isVertical ? (1 - chromeAlpha) * 80 : 0;
      this.inspector.style.transform = this.isVertical
        ? `translate3d(0, ${slideY.toFixed(1)}px, 0)`
        : `perspective(1800px) translate3d(${slideX.toFixed(1)}px, 0, 0) rotateY(${panelTiltY.toFixed(2)}deg)`;
    }
    for (const elm of [this.stageIdentity, this.stageMetrics, this.stageControls]) {
      if (elm) elm.style.opacity = String(chromeAlpha.toFixed(3));
    }

    // 4. Dynamic Continuous 3D Camera Orbit + Beat-Reactive Micro-Recoil!
    if (s3) {
      if (beat < 8.0) {
        // Sweeping dramatic Cold Open hero orbit
        const p = easeOutQuint(clamp(beat / 8.0, 0, 1));
        s3.userOrbitOffset.az = lerp(-0.34, 0.14, p);
        s3.userOrbitOffset.pol = lerp(0.08, -0.02, p);
      } else if (beat < 50.0) {
        s3.userOrbitOffset.az = Math.sin(sec * 0.78) * 0.13;
        s3.userOrbitOffset.pol = Math.cos(sec * 0.62) * 0.045;
      } else if (beat < 56.0) {
        // High-energy 1-beat climax sweep
        s3.userOrbitOffset.az = Math.sin(sec * 2.2) * 0.16;
        s3.userOrbitOffset.pol = -0.03;
      } else {
        const fp = easeOutQuint(clamp((beat - 56.0) / 7.5, 0, 1));
        s3.userOrbitOffset.az = lerp(-0.14, 0.18, fp);
        s3.userOrbitOffset.pol = -0.02;
      }
    }

    // Beat-reactive subtle scale punch + whip-cut zoom kick (safe 2D scale -> zero WebGL clipping!)
    if (this.shell) {
      let sc = 1.0 + beatPulse * 0.008;
      for (const hitB of [8, 18, 28, 38, 50, 51, 52, 53, 54, 55, 56]) {
        const d = beat - hitB;
        if (d >= 0 && d < 0.45) {
          sc += Math.sin((d / 0.45) * Math.PI) * Math.exp(-d * 6.5) * 0.034;
        }
      }
      this.shell.style.transform = sc > 1.0004 ? `scale(${sc.toFixed(4)})` : 'none';
    }

    // Camera framing offset (landscape vs 9:16 portrait)
    if (s3 && s3.camera) {
      const w = s3.canvas.clientWidth || window.innerWidth;
      const h = s3.canvas.clientHeight || window.innerHeight;
      if (this.isVertical) {
        if (s3.camTarget.fov < 39) s3.camTarget.fov = 40;
        if (s3.camera.fov < 39) { s3.cam.fov = 40; s3.camera.fov = 40; }
        const shiftY = beat < 7.2 ? Math.round(-h * 0.05) : (beat >= 56.0 ? Math.round(h * 0.14) : Math.round(h * 0.19));
        s3.camera.setViewOffset(w, h, 0, shiftY, w, h);
        s3.camera.updateProjectionMatrix();
      } else if (beat < 8.0) {
        const u = easeInOutQuart(clamp((beat - 6.4) / 1.6, 0, 1));
        s3.camera.setViewOffset(w, h, Math.round(w * 0.205 * u), 0, w, h);
        s3.camera.updateProjectionMatrix();
      } else if (beat >= 55.8) {
        const u = easeInOutQuart(clamp((beat - 55.8) / 1.6, 0, 1));
        s3.camera.setViewOffset(w, h, Math.round(lerp(w * 0.205, w * 0.22, u)), 0, w, h);
        s3.camera.updateProjectionMatrix();
      }
    }

    // 5. Scene 0: Fast Kinetic Cold Open Slams (Beats 0.6 .. 7.8)
    const cold = document.getElementById('vid-cold-open');
    if (beat < 8.0) {
      const fadeOut = beat > 6.8 ? clamp(1 - (beat - 6.8) / 0.9, 0, 1) : 1.0;
      const eySp = easeOutQuint(clamp((beat - 0.8) / 1.0, 0, 1));
      const w1Sp = spring01(Math.max(0, sec - beatToSec(2.0)), { stiffness: 320, damping: 22 });
      const w2Sp = spring01(Math.max(0, sec - beatToSec(4.0)), { stiffness: 320, damping: 22 });
      const rlSp = easeOutExpo(clamp((beat - 4.8) / 1.0, 0, 1));
      const tlSp = easeOutQuint(clamp((beat - 5.4) / 1.0, 0, 1));

      cold.style.opacity = String((fadeOut * (beat > 0.6 ? 1 : 0)).toFixed(3));
      document.getElementById('cold-eyebrow').style.opacity = String(eySp.toFixed(3));
      document.getElementById('cold-eyebrow').style.transform = `translateY(${((1 - eySp) * 12).toFixed(1)}px)`;
      document.getElementById('cold-w1').style.transform = `translateY(${((1 - w1Sp) * 112).toFixed(1)}%)`;
      document.getElementById('cold-w2').style.transform = `translateY(${((1 - w2Sp) * 112).toFixed(1)}%)`;
      document.getElementById('cold-rule').style.transform = `scaleX(${rlSp.toFixed(3)})`;
      document.getElementById('cold-telemetry').style.opacity = String(tlSp.toFixed(3));
      document.getElementById('cold-telemetry').style.transform = `translateY(${((1 - tlSp) * 14).toFixed(1)}px)`;
    } else {
      cold.style.opacity = '0';
    }

    // 6. Mid-Video Kinetic Impact Slam Stamp
    const slamEl = document.getElementById('vid-slam');
    if (this.slam.visible && frame >= this.slam.startFrame && frame <= this.slam.endFrame) {
      const inT = (frame - this.slam.startFrame) / FPS;
      const outRem = (this.slam.endFrame - frame) / FPS;
      const sp = spring01(inT, { stiffness: 340, damping: 22 });
      const outA = outRem < 0.22 ? clamp(outRem / 0.22, 0, 1) : 1.0;
      slamEl.style.opacity = String((clamp(sp * 1.2, 0, 1) * outA).toFixed(3));
      slamEl.style.transform = `translate3d(${((1 - sp) * -32).toFixed(1)}px, 0, 0) scale(${(0.92 + sp * 0.08).toFixed(3)})`;
    } else {
      slamEl.style.opacity = '0';
    }

    // 7. Lower-Third Feature Callout Card
    const callEl = document.getElementById('vid-callout');
    if (this.callout.visible && frame >= this.callout.startFrame && frame <= this.callout.endFrame) {
      const inElapsed = (frame - this.callout.startFrame) / FPS;
      const outRem = (this.callout.endFrame - frame) / FPS;
      const spIn = spring01(inElapsed, { stiffness: 300, damping: 22 });
      const fadeOut = outRem < 0.16 ? clamp(outRem / 0.16, 0, 1) : 1.0;
      callEl.style.opacity = String((clamp(spIn * 1.15, 0, 1) * fadeOut).toFixed(3));
      callEl.style.transform = `translate3d(0, ${((1 - spIn) * 26).toFixed(1)}px, 0)`;
    } else {
      callEl.style.opacity = '0';
    }

    // 8. Scene 4: Real 60 FPS Wayland Cairo Actions Ring Showcase (Beats 44..50)
    if (frame >= this.cairoStartFrame && frame <= this.cairoEndFrame) {
      const idx = frame - this.cairoStartFrame;
      const inA = easeOutQuint(clamp((beat - 44.0) / 0.45, 0, 1));
      const outA = beat > 49.4 ? easeOutQuint(clamp(1 - (beat - 49.4) / 0.55, 0, 1)) : 1.0;
      this.cairoLayer.style.opacity = String((inA * outA).toFixed(3));
      this.cairoImg.style.transform = `scale(${(1.0 + beatPulse * 0.015).toFixed(4)})`;
      if (idx !== this._lastCairoIdx) {
        this._lastCairoIdx = idx;
        this.cairoImg.src = `/__showcase/tmp/cairo_ring/frame_${String(idx).padStart(4, '0')}.png`;
      }
    } else {
      this.cairoLayer.style.opacity = '0';
    }

    // 9. Scene 6: Clean Brand Lockup & CTA (Beats 56.0 .. 64.0)
    const endEl = document.getElementById('vid-endcard');
    if (beat >= 56.0) {
      const t0 = sec - beatToSec(56.15);
      const spK = spring01(Math.max(0, t0), { stiffness: 260, damping: 22 });
      const spL = spring01(Math.max(0, t0 - 0.10), { stiffness: 240, damping: 20 });
      const spT = spring01(Math.max(0, t0 - 0.24), { stiffness: 250, damping: 22 });
      const spP = spring01(Math.max(0, t0 - 0.38), { stiffness: 250, damping: 22 });
      const spC = spring01(Math.max(0, sec - beatToSec(57.8)), { stiffness: 260, damping: 21 });
      const tailFade = beat > 62.6 ? clamp(1 - (beat - 62.6) / 1.3, 0, 1) : 1.0;

      endEl.style.opacity = String(tailFade.toFixed(3));
      const setSp = (id, sp, dy = 26) => {
        const n = document.getElementById(id);
        if (!n) return;
        n.style.opacity = String(clamp(sp * 1.15, 0, 1).toFixed(3));
        n.style.transform = `translate3d(0, ${((1 - sp) * dy).toFixed(1)}px, 0)`;
      };
      setSp('end-kicker', spK, 16);
      setSp('end-logo', spL, 38);
      setSp('end-tag', spT, 22);
      setSp('end-pills', spP, 18);
      setSp('end-cta', spC, 22);
    } else {
      endEl.style.opacity = '0';
    }

    // 10. Cursor, Click Ripple, Anamorphic Flare, Flash & Particles
    this._updateCursorPath(beat);

    this.rippleAge += dt;
    const rip = document.getElementById('vid-cursor-ripple');
    if (this.rippleAge < 0.32) {
      const u = this.rippleAge / 0.32;
      rip.style.opacity = String(((1 - u) * (1 - u) * 0.95).toFixed(3));
      rip.style.transform = `translate3d(${this.rippleX}px, ${this.rippleY}px, 0) scale(${(0.32 + easeOutExpo(u) * 1.45).toFixed(3)})`;
    } else {
      rip.style.opacity = '0';
    }

    this.flareAge += dt;
    const flare = document.getElementById('vid-flare');
    if (this.flareAge < 0.34) {
      const u = this.flareAge / 0.34;
      const a = Math.sin(Math.min(1, u * 4.5) * Math.PI * 0.5) * (1 - u) * (1 - u);
      const sx = 0.25 + easeOutExpo(u) * 1.25;
      flare.style.top = `${this.flareY}%`;
      flare.style.opacity = String((a * 0.92).toFixed(3));
      flare.style.transform = `scaleX(${sx.toFixed(3)}) scaleY(${(1.6 - u * 1.1).toFixed(3)})`;
    } else {
      flare.style.opacity = '0';
    }

    this.flashAge += dt;
    const fl = document.getElementById('vid-flash');
    if (this.flashAge < 0.18) {
      const u = this.flashAge / 0.18;
      fl.style.opacity = String(((1 - u) * (1 - u) * 0.90).toFixed(3));
    } else {
      fl.style.opacity = '0';
    }

    this.particles.step(dt, beatPulse);
  }

  async waitForCairoImage() {
    if (this.currentFrame >= this.cairoStartFrame && this.currentFrame <= this.cairoEndFrame) {
      if (!this.cairoImg.complete) {
        await new Promise((res) => {
          this.cairoImg.onload = res;
          this.cairoImg.onerror = res;
        });
      }
      try { await this.cairoImg.decode(); } catch {}
    }
  }

  async stepToFrame(targetFrame) {
    if (targetFrame <= this.currentFrame) return;
    const dtMs = 1000.0 / FPS;

    while (this.currentFrame < targetFrame) {
      this.currentFrame += 1;
      const f = this.currentFrame;
      const sec = frameToSec(f);
      const beat = frameToBeat(f);

      for (const ev of this.events) {
        if (!this.firedEvents.has(ev.id) && f >= ev.frame) {
          this.firedEvents.add(ev.id);
          try { ev.fn(); } catch (e) { console.error('[DirectorV2]', ev.beat, e); }
        }
      }

      this._updateSceneVisuals(f, sec, beat);
      window.__MX4_CLOCK__.advance(dtMs);
    }

    await this.waitForCairoImage();
    await new Promise((res) => window.__MX4_CLOCK__.nativeRaf(() => res()));
  }
}

async function waitUntilStudioReady() {
  const start = window.__MX4_CLOCK__.origNow();
  while (window.__MX4_CLOCK__.origNow() - start < 20000) {
    window.__MX4_CLOCK__.advance(16.666);
    const s3 = window.__MX4_STUDIO_3D__;
    const ui = window.__MX4_STUDIO_UI__;
    const hasThemes = document.querySelectorAll('.ring-theme-card').length >= 6;
    const hasMouse = Boolean(s3 && s3.lmbPivot && s3.mouseShellMeshes && s3.mouseShellMeshes.length > 0);
    if (s3 && ui && hasThemes && hasMouse) {
      const warmStart = window.__MX4_CLOCK__.origNow();
      while (window.__MX4_CLOCK__.origNow() - warmStart < 1800) {
        window.__MX4_CLOCK__.advance(16.666);
        s3.renderer.render(s3.scene, s3.camera);
        await new Promise((res) => window.__MX4_CLOCK__.nativeRaf(() => res()));
      }
      window.__MX4_CLOCK__.reset();
      if (s3.clock) {
        s3.clock.startTime = 0;
        s3.clock.oldTime = 0;
        s3.clock.elapsedTime = 0;
      }
      return true;
    }
    await new Promise((r) => setTimeout(r, 25));
  }
  throw new Error('MX4 Studio 3D stage did not finish loading in time');
}

window.__BOOT_DIRECTOR__ = async () => {
  await waitUntilStudioReady();
  const director = new ShowcaseDirectorV2();
  window.__DIRECTOR__ = director;
  return { ok: true, totalFrames: TOTAL_FRAMES, bpm: BPM, fps: FPS };
};
