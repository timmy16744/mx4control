/**
 * MX4 Studio (2027 Edition) — v3 Hard-Surface Real-Scan MX Master 4 Engine
 * Three.js r170 · Hard-Surface Crisp Scan GLB · Molded Rubber-Bump Thumb Pad
 * Real Separate Top/Side CAD Buttons & Knurled Thumb Wheel · Live 6-DOF Part Alignment Studio
 *
 * Right-handed anatomical coordinates (+Y up, +Z nose, +X left thumb wing):
 *   Real scan bounds: X [-0.93, +1.54], Y [0.00, 1.43], Z [-1.80, +1.80]
 */

import * as THREE from './vendor/three.module.min.js';
import { GLTFLoader } from './vendor/GLTFLoader.js';

export const CID = {
  LEFT_CLICK: 0x0050,
  RIGHT_CLICK: 0x0051,
  MIDDLE_CLICK: 0x0052,
  BACK: 0x0053,
  FORWARD: 0x0056,
  GESTURE: 0x00C3,
  SMART_SHIFT: 0x00C4,
  THUMB_PAD: 0x01A0,      // Real physical Haptic Sense Thumb Pad (416 = 0x01A0)!
  VIRTUAL_GESTURE: 0x00D7,
  THUMB_WHEEL: 0x2150,    // Horizontal Thumb Wheel (feature 0x2150)
};

export const BUTTON_META = {
  [CID.LEFT_CLICK]:   { name: 'Left Click',       anchor: [ 0.46, 0.90,  1.10], box: [0.56, 0.22, 0.95] },
  [CID.RIGHT_CLICK]:  { name: 'Right Click',      anchor: [-0.42, 0.78,  1.10], box: [0.56, 0.22, 0.95] },
  [CID.MIDDLE_CLICK]: { name: 'MagSpeed Wheel',   anchor: [ 0.025, 0.96, 0.955], box: [0.24, 0.26, 0.52] },
  [CID.SMART_SHIFT]:  { name: 'Mode Shift',       anchor: [ 0.03, 1.18,  0.34], box: [0.22, 0.14, 0.28] },
  [CID.THUMB_WHEEL]:  { name: 'Thumb Wheel',      anchor: [ 0.84, 1.15,  0.04], box: [0.22, 0.26, 0.54] },
  [CID.GESTURE]:      { name: 'Gesture Button',   anchor: [ 0.84, 0.73,  0.36], box: [0.14, 0.14, 0.24] },
  [CID.FORWARD]:      { name: 'Forward',          anchor: [ 0.84, 0.83,  0.10], box: [0.14, 0.14, 0.24] },
  [CID.BACK]:         { name: 'Back',             anchor: [ 0.84, 0.93, -0.17], box: [0.14, 0.14, 0.24] },
  [CID.THUMB_PAD]:    { name: 'Haptic Sense Pad', anchor: [ 1.18, 0.38, -0.28], box: [0.55, 0.34, 0.96] },
};

// Default sub-millimeter part transforms fitted directly to v5 Multi-Part CAD mx_master_4.glb
// Factory-calibrated 3D component transforms and material parameters.
export const DEFAULT_ALIGN_CONFIG = {
  parts: {
    magSpeedWheel:  { label: 'MagSpeed Wheel',    x: 0.025, y: 0.748, z:  0.955, rx:  0.00, ry:  0.00, rz:  0.00, scale: 1.00, visible: true },
    scrollBezel:    { label: 'Scroll Bezel',      x: 0.025, y: 0.842, z:  0.955, rx:  0.26, ry:  0.00, rz:  0.12, scale: 1.00, visible: false },
    modeShiftBtn:   { label: 'Top Mode-Shift',    x: 0.030, y: 1.186, z:  0.265, rx:  0.34, ry:  0.00, rz:  0.15, scale: 1.00, visible: true },
    thumbWheel:     { label: 'Side Thumb Wheel',  x: 0.790, y: 1.126, z:  0.030, rx:  0.38, ry:  0.02, rz: -0.06, scale: 1.00, visible: true },
    sideGestureBtn: { label: 'Side Gesture Btn',  x: 0.818, y: 0.722, z:  0.395, rx:  0.38, ry:  0.02, rz: -0.06, scale: 1.00, visible: true },
    sideForwardBtn: { label: 'Side Forward Btn',  x: 0.822, y: 0.832, z:  0.105, rx:  0.38, ry:  0.01, rz: -0.06, scale: 1.00, visible: true },
    sideBackBtn:    { label: 'Side Back Btn',     x: 0.820, y: 0.930, z: -0.155, rx:  0.38, ry: -0.01, rz: -0.06, scale: 1.00, visible: true },
    lraCoil:        { label: 'Internal LRA Coil', x: 0.580, y: 0.440, z: -0.060, rx:  0.08, ry:  0.98, rz:  0.24, scale: 1.00, visible: true },
    opticalBeam:    { label: 'Optical Beam',      x: 0.120, y: 0.000, z:  0.080, rx:  0.00, ry:  0.00, rz:  0.00, scale: 1.00, visible: true },
  },
  materials: {
    shellRoughness: 0.78,
    shellClearcoat: 0.00,
    thumbBumpDepth: 0.052,
    thumbBumpScale: 16,
    exposure: 1.15,
  },
};

const CAMERA_PRESETS = {
  device:      { az:  0.80, pol: 1.18, dist: 8.15, tx:  0.14, ty: 0.44, tz: -0.04, fov: 27 },
  scroll:      { az:  0.56, pol: 0.74, dist: 1.98, tx:  0.03, ty: 0.94, tz:  0.88, fov: 26 },
  haptics:     { az:  0.84, pol: 1.16, dist: 7.90, tx:  0.18, ty: 0.44, tz: -0.05, fov: 27 },
  ring:        { az:  0.66, pol: 0.80, dist: 8.20, tx:  0.12, ty: 0.80, tz: -0.02, fov: 28 },
  buttons:     { az:  0.90, pol: 1.10, dist: 7.95, tx:  0.18, ty: 0.50, tz: -0.02, fov: 27 },
  diagnostics: { az:  0.82, pol: 1.12, dist: 7.95, tx:  0.14, ty: 0.48, tz: -0.04, fov: 27 },
};

// Bespoke macro focus camera for EVERY physical control on the MX Master 4!
// Clicking any button/wheel/pad zooms smoothly right onto THAT exact control.
const CONTROL_CAMERAS = {
  [CID.LEFT_CLICK]:   { az:  0.54, pol: 0.82, dist: 3.45, tx:  0.34, ty: 0.82, tz:  1.02, fov: 25 },
  [CID.RIGHT_CLICK]:  { az: -0.58, pol: 0.84, dist: 3.45, tx: -0.34, ty: 0.78, tz:  1.02, fov: 25 },
  [CID.MIDDLE_CLICK]: { az:  0.54, pol: 0.74, dist: 2.02, tx:  0.03, ty: 0.92, tz:  0.92, fov: 25 },
  [CID.SMART_SHIFT]:  { az:  0.42, pol: 0.56, dist: 2.40, tx:  0.03, ty: 1.16, tz:  0.27, fov: 25 },
  [CID.THUMB_WHEEL]:  { az:  1.28, pol: 1.00, dist: 2.46, tx:  0.79, ty: 1.12, tz: -0.04, fov: 25 },
  [CID.GESTURE]:      { az:  1.36, pol: 1.14, dist: 2.32, tx:  0.82, ty: 0.73, tz:  0.39, fov: 25 },
  [CID.FORWARD]:      { az:  1.42, pol: 1.12, dist: 2.32, tx:  0.82, ty: 0.83, tz:  0.11, fov: 25 },
  [CID.BACK]:         { az:  1.48, pol: 1.10, dist: 2.32, tx:  0.82, ty: 0.92, tz: -0.15, fov: 25 },
  [CID.THUMB_PAD]:    { az:  1.22, pol: 0.96, dist: 2.88, tx:  1.12, ty: 0.42, tz: -0.18, fov: 25 },
};

// ─────────────────────────── Procedural Studio Textures ──────────────────

/**
 * Fine injection-molded bead-blasted polycarbonate tangent-space RGB Normal Map.
 */
function createBeadBlastedNormalMap() {
  const S = 256;
  const c = document.createElement('canvas');
  c.width = S;
  c.height = S;
  const ctx = c.getContext('2d');
  const img = ctx.createImageData(S, S);
  const h = new Float32Array(S * S);
  let seed = 4201;
  const rand = () => {
    seed = (seed * 16807) % 2147483647;
    return (seed - 1) / 2147483646;
  };
  for (let i = 0; i < S * S; i++) h[i] = rand();
  for (let y = 0; y < S; y++) {
    for (let x = 0; x < S; x++) {
      const xm = (x + S - 1) % S, xp = (x + 1) % S;
      const ym = (y + S - 1) % S, yp = (y + 1) % S;
      const dx = (h[y * S + xp] - h[y * S + xm]) * 0.55;
      const dy = (h[yp * S + x] - h[ym * S + x]) * 0.55;
      const dz = 1.0;
      const inv = 1.0 / Math.hypot(dx, dy, dz);
      const idx = (y * S + x) * 4;
      img.data[idx]     = Math.round((-dx * inv * 0.5 + 0.5) * 255);
      img.data[idx + 1] = Math.round((-dy * inv * 0.5 + 0.5) * 255);
      img.data[idx + 2] = Math.round(( dz * inv * 0.5 + 0.5) * 255);
      img.data[idx + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(22, 22);
  return tex;
}

/**
 * Authentic Logitech MX Master 4 Haptic Sense Thumb Pad Concentric Circular Pattern (1024x1024).
 * Reference hardware geometry:
 *   - Origin centered right below the gap between Gesture & Forward buttons (u=0.80, v=0.30).
 *   - Center smooth circular dimple containing the iconic 8-dot Actions Ring emblem.
 *   - Smooth concentric circular ripple rings radiating out from the 8-dot emblem.
 *   - Sweeping concentric circular arcs of raised tactile micro-bumps across the entire pad!
 */
function createThumbPadRubberBumpMaps(ringDensity = 16) {
  const S = 1024;
  const hField = new Float32Array(S * S);

  const cCanvas = document.createElement('canvas');
  cCanvas.width = S;
  cCanvas.height = S;
  const cctx = cCanvas.getContext('2d');
  const cImg = cctx.createImageData(S, S);

  const rCanvas = document.createElement('canvas');
  rCanvas.width = S;
  rCanvas.height = S;
  const rctx = rCanvas.getContext('2d');
  const rImg = rctx.createImageData(S, S);

  // Exact 1:1 metric orthonormal UV origin right below the gap between Gesture & Forward buttons!
  // Verified from Blender glTF export in (PAD_U, PAD_V) plane (equal 1.50 span -> aspect = 1.000!):
  const ox = 0.757;
  const oy = 0.730;
  const aspect = 1.0; // Exact 1:1 metric UV projection -> 100% geometrically round circles!
  const kRing = Math.max(10, Math.min(40, Number(ringDensity) || 16)) * 2.25;

  const smoothstep = (e0, e1, x) => {
    const t = Math.max(0, Math.min(1, (x - e0) / (e1 - e0)));
    return t * t * (3 - 2 * t);
  };

  for (let py = 0; py < S; py++) {
    const v = 1.0 - py / (S - 1);
    const dv = (v - oy) / aspect;
    for (let px = 0; px < S; px++) {
      const u = px / (S - 1);
      const du = u - ox;
      const r = Math.hypot(du, dv);
      const theta = Math.atan2(dv, du);

      let h = 0.0;
      let rough = 188;
      let shade = 1.0;

      // 1. Subtle recessed smooth circular thumb-target dimple + 8-dot Actions Ring emblem!
      if (r < 0.086) {
        // Gentle dish depression around the Actions Ring icon
        h = -0.32 * (1.0 - (r / 0.086) ** 2);
        rough = 158;
      } else {
        // 2. Concentric circular ripples originating from the Actions Ring center!
        const phaseR = (r - 0.086) * kRing * Math.PI * 2.0;
        const ringIdx = Math.floor((r - 0.086) * kRing);
        const ripple = 0.5 + 0.5 * Math.cos(phaseR);

        // Smooth fade-in of micro-bump segmentation outside the first 2.5 smooth circular rings
        const dotBlend = smoothstep(0.145, 0.255, r);
        // Keep angular bump spacing constant around every concentric circle!
        const nSpokes = Math.max(16, Math.round(2.0 * Math.PI * (0.086 + (ringIdx + 0.5) / kRing) * kRing * 0.90));
        const spokeWave = 0.5 + 0.5 * Math.cos(theta * nSpokes);

        // Smooth fade out gently near the far rear corner (matching Photos 4 & 5!)
        const farFade = 1.0 - smoothstep(0.72, 0.96, r);

        // Combine smooth concentric rings (near center) + concentric circular micro-bumps (outer field)
        const smoothRing = Math.pow(ripple, 1.35) * 0.72;
        const microBump = Math.pow(ripple * spokeWave, 0.85) * 1.15;
        h = (smoothRing * (1.0 - dotBlend * 0.48) + microBump * dotBlend) * farFade;

        // Satin crests vs slightly more matte valleys (real molded silicone sheen!)
        rough = Math.round(218 - h * 58);
        shade = 0.93 + h * 0.11;
      }

      // Draw the iconic subtle matte-grey 8-dot Actions Ring emblem inside the center dimple!
      let isIconDot = false;
      if (r > 0.018 && r < 0.068) {
        for (let d = 0; d < 8; d++) {
          const ang = (d / 8) * Math.PI * 2.0;
          const ddx = du - Math.cos(ang) * 0.043;
          const ddy = dv - Math.sin(ang) * 0.043;
          if (ddx * ddx + ddy * ddy < 0.0102 * 0.0102) {
            isIconDot = true;
            break;
          }
        }
      }

      hField[py * S + px] = h;
      const idx = (py * S + px) * 4;
      const base = isIconDot ? 210 : Math.max(105, Math.min(165, Math.round(128 * shade)));
      cImg.data[idx]     = base;
      cImg.data[idx + 1] = Math.round(base * 1.02);
      cImg.data[idx + 2] = Math.round(base * 1.05);
      cImg.data[idx + 3] = 255;

      const rv = isIconDot ? 215 : Math.max(115, Math.min(238, rough));
      rImg.data[idx] = rImg.data[idx + 1] = rImg.data[idx + 2] = rv;
      rImg.data[idx + 3] = 255;
    }
  }

  // Analytical finite-difference tangent-space RGB Normal Map from heightfield
  const nCanvas = document.createElement('canvas');
  nCanvas.width = S;
  nCanvas.height = S;
  const nctx = nCanvas.getContext('2d');
  const nImg = nctx.createImageData(S, S);
  const strength = 5.4;

  for (let py = 0; py < S; py++) {
    const ym = Math.max(0, py - 1);
    const yp = Math.min(S - 1, py + 1);
    for (let px = 0; px < S; px++) {
      const xm = Math.max(0, px - 1);
      const xp = Math.min(S - 1, px + 1);
      const dhdx = (hField[py * S + xp] - hField[py * S + xm]) * strength;
      const dhdy = (hField[yp * S + px] - hField[ym * S + px]) * strength;
      let nx = -dhdx;
      let ny = dhdy;
      let nz = 1.0;
      const inv = 1.0 / Math.hypot(nx, ny, nz);
      nx *= inv;
      ny *= inv;
      nz *= inv;
      const idx = (py * S + px) * 4;
      nImg.data[idx]     = Math.round((nx * 0.5 + 0.5) * 255);
      nImg.data[idx + 1] = Math.round((ny * 0.5 + 0.5) * 255);
      nImg.data[idx + 2] = Math.round((nz * 0.5 + 0.5) * 255);
      nImg.data[idx + 3] = 255;
    }
  }

  cctx.putImageData(cImg, 0, 0);
  rctx.putImageData(rImg, 0, 0);
  nctx.putImageData(nImg, 0, 0);

  const colorMap = new THREE.CanvasTexture(cCanvas);
  colorMap.colorSpace = THREE.SRGBColorSpace;
  colorMap.anisotropy = 8;

  const normalMap = new THREE.CanvasTexture(nCanvas);
  normalMap.anisotropy = 8;

  const roughnessMap = new THREE.CanvasTexture(rCanvas);
  roughnessMap.anisotropy = 8;

  return { colorMap, normalMap, bumpMap: normalMap, roughnessMap };
}

/**
 * Subtle debossed 'logi' branding map baked into LMB's planar top UV.
 * Positioned at verified Blender glTF UV (0.623, 0.344) on the rear-left of MX4_LMB.
 */
function createLmbLogiRoughnessMap() {
  const S = 1024;
  const c = document.createElement('canvas');
  c.width = S;
  c.height = S;
  const ctx = c.getContext('2d');
  // Base uniform foggy roughness (~0.42 -> 108/255)
  ctx.fillStyle = 'rgb(112,112,112)';
  ctx.fillRect(0, 0, S, S);

  // Subtle glossy-etched / debossed 'logi' mark oriented facing the user (nose = +Z)
  // With flipY = true: UV (u, v_gltf) maps to px = u * S, py = (1 - v_gltf) * S
  ctx.save();
  ctx.translate(0.623 * S, (1.0 - 0.344) * S);
  // Rotate so 'logi' reads horizontally across LMB right in front of the diagonal seam
  ctx.rotate(Math.PI);
  ctx.font = '700 36px "Inter", "Plus Jakarta Sans", "DejaVu Sans", sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  // Ultra-subtle etched letters inside foggy polycarbonate (matches real Photos 6 & 7!)
  ctx.fillStyle = 'rgb(76,76,76)';
  ctx.fillText('logi', 0, 0);
  ctx.restore();

  const tex = new THREE.CanvasTexture(c);
  tex.anisotropy = 8;
  return tex;
}

function createBrushedMetalTexture() {
  const c = document.createElement('canvas');
  c.width = 512;
  c.height = 512;
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#d4dae4';
  ctx.fillRect(0, 0, 512, 512);
  for (let y = 0; y < 512; y++) {
    const v = 198 + Math.floor(Math.sin(y * 1.7) * 14 + (Math.random() - 0.5) * 20);
    ctx.fillStyle = `rgb(${v},${v + 2},${v + 5})`;
    ctx.fillRect(0, y, 512, 1);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function createCopperCoilTexture() {
  const c = document.createElement('canvas');
  c.width = 512;
  c.height = 256;
  const ctx = c.getContext('2d');
  const turns = 48;
  const step = 512 / turns;
  for (let i = 0; i < turns; i++) {
    const x = i * step;
    const g = ctx.createLinearGradient(x, 0, x + step, 0);
    g.addColorStop(0.0,  '#45200a');
    g.addColorStop(0.28, '#d98f46');
    g.addColorStop(0.52, '#ffe8c2');
    g.addColorStop(0.78, '#bd6e2c');
    g.addColorStop(1.0,  '#321605');
    ctx.fillStyle = g;
    ctx.fillRect(x, 0, step + 0.5, 256);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
}

function createStudioEnvironment(renderer) {
  const pmrem = new THREE.PMREMGenerator(renderer);
  const envScene = new THREE.Scene();
  envScene.background = new THREE.Color(0x06080b);

  // Luxury industrial product photography softbox rig (neutral-warm diffused strips, zero cyan wash!)
  const panels = [
    { pos: [ 0.5, 9.8,  2.2], rot: [Math.PI / 2, 0, -0.06],  size: [11.0, 4.8], color: 0xfbfcff, intensity: 2.40 },
    { pos: [-0.6, 8.2,  5.6], rot: [Math.PI / 2.3, 0, 0],    size: [7.2, 2.0],  color: 0xffffff, intensity: 3.40 },
    { pos: [ 8.8, 4.2,  4.8], rot: [0, -Math.PI / 2.8, 0],   size: [7.6, 4.4],  color: 0xfff0dc, intensity: 1.85 },
    { pos: [-8.5, 4.5,  1.2], rot: [0,  Math.PI / 2.2, 0],   size: [7.0, 4.2],  color: 0xdce6f2, intensity: 1.25 },
    { pos: [-2.0, 3.6, -8.5], rot: [0, Math.PI, 0],          size: [9.0, 3.4],  color: 0xe4ecf8, intensity: 1.15 },
    { pos: [ 0.0, -5.0, 0.0], rot: [-Math.PI / 2, 0, 0],     size: [16, 16],    color: 0x0b0e14, intensity: 0.30 },
  ];

  for (const p of panels) {
    const mat = new THREE.MeshBasicMaterial({
      color: new THREE.Color(p.color).multiplyScalar(p.intensity),
      side: THREE.DoubleSide,
    });
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(p.size[0], p.size[1]), mat);
    mesh.position.set(...p.pos);
    mesh.rotation.set(...p.rot);
    envScene.add(mesh);
  }

  const rt = pmrem.fromScene(envScene, 0.024);
  pmrem.dispose();
  return rt.texture;
}

// ─────────────────────────── Hard-Surface CAD Part Builders ──────────────

/**
 * Precision CNC-machined gear-fluted stainless steel band.
 * Axis is along X by default (for vertical MagSpeed wheel).
 */
function createKnurledWheelBand(radius, width, teeth = 60, depth = 0.009) {
  const shape = new THREE.Shape();
  const pts = teeth * 4;
  for (let i = 0; i <= pts; i++) {
    const a = (i / pts) * Math.PI * 2;
    const mod = i % 4;
    const r = (mod === 0 || mod === 1) ? radius : radius - depth;
    const x = Math.cos(a) * r;
    const y = Math.sin(a) * r;
    if (i === 0) shape.moveTo(x, y);
    else shape.lineTo(x, y);
  }
  const geo = new THREE.ExtrudeGeometry(shape, {
    depth: width,
    bevelEnabled: true,
    bevelThickness: 0.0038,
    bevelSize: 0.0032,
    bevelSegments: 2,
    curveSegments: 1,
  });
  geo.rotateY(Math.PI / 2);
  geo.center();
  return geo;
}

/**
 * Horizontal knurled stainless steel Thumb Wheel cylinder (axis along Z!).
 */
function createThumbWheelCylinder(radius, length, teeth = 36, depth = 0.0065) {
  const shape = new THREE.Shape();
  const pts = teeth * 4;
  for (let i = 0; i <= pts; i++) {
    const a = (i / pts) * Math.PI * 2;
    const mod = i % 4;
    const r = (mod === 0 || mod === 1) ? radius : radius - depth;
    const x = Math.cos(a) * r;
    const y = Math.sin(a) * r;
    if (i === 0) shape.moveTo(x, y);
    else shape.lineTo(x, y);
  }
  const geo = new THREE.ExtrudeGeometry(shape, {
    depth: length,
    bevelEnabled: true,
    bevelThickness: 0.005,
    bevelSize: 0.004,
    bevelSegments: 2,
    curveSegments: 1,
  });
  geo.center(); // ExtrudeGeometry extrudes along Z -> cylinder axis IS Z!
  return geo;
}

function createScrollPocketCollar() {
  const outer = new THREE.Shape();
  const ow = 0.34, od = 0.72, or = 0.08;
  outer.moveTo(-ow / 2 + or, -od / 2);
  outer.lineTo( ow / 2 - or, -od / 2);
  outer.absarc( ow / 2 - or, -od / 2 + or, or, -Math.PI / 2, 0, false);
  outer.lineTo( ow / 2,  od / 2 - or);
  outer.absarc( ow / 2 - or,  od / 2 - or, or, 0, Math.PI / 2, false);
  outer.lineTo(-ow / 2 + or,  od / 2);
  outer.absarc(-ow / 2 + or,  od / 2 - or, or, Math.PI / 2, Math.PI, false);
  outer.lineTo(-ow / 2, -od / 2 + or);
  outer.absarc(-ow / 2 + or, -od / 2 + or, or, Math.PI, Math.PI * 1.5, false);

  const hole = new THREE.Path();
  const iw = 0.242, id = 0.57, ir = 0.042;
  hole.moveTo(-iw / 2 + ir, -id / 2);
  hole.lineTo( iw / 2 - ir, -id / 2);
  hole.absarc( iw / 2 - ir, -id / 2 + ir, ir, -Math.PI / 2, 0, false);
  hole.lineTo( iw / 2,  id / 2 - ir);
  hole.absarc( iw / 2 - ir,  id / 2 - ir, ir, 0, Math.PI / 2, false);
  hole.lineTo(-iw / 2 + ir,  id / 2);
  hole.absarc(-iw / 2 + ir,  id / 2 - ir, ir, Math.PI / 2, Math.PI, false);
  hole.lineTo(-iw / 2, -id / 2 + ir);
  hole.absarc(-iw / 2 + ir, -id / 2 + ir, ir, Math.PI, Math.PI * 1.5, false);
  outer.holes.push(hole);

  const geo = new THREE.ExtrudeGeometry(outer, {
    depth: 0.06,
    bevelEnabled: true,
    bevelThickness: 0.014,
    bevelSize: 0.012,
    bevelSegments: 4,
  });
  geo.rotateX(-Math.PI / 2);
  geo.center();
  return geo;
}

/**
 * Crisp chamfered hard-surface CAD button cap (sharp beveled industrial edges!).
 */
function createHardSurfaceButton(w, h, d, r = 0.022, bevel = 0.009) {
  const shape = new THREE.Shape();
  const hw = Math.max(0.002, w / 2 - r);
  const hh = Math.max(0.002, d / 2 - r);
  shape.moveTo(-hw, -d / 2);
  shape.lineTo(hw, -d / 2);
  shape.absarc(hw, -hh, r, -Math.PI / 2, 0, false);
  shape.lineTo(w / 2, hh);
  shape.absarc(hw, hh, r, 0, Math.PI / 2, false);
  shape.lineTo(-hw, d / 2);
  shape.absarc(-hw, hh, r, Math.PI / 2, Math.PI, false);
  shape.lineTo(-w / 2, -hh);
  shape.absarc(-hw, -hh, r, Math.PI, Math.PI * 1.5, false);
  const geo = new THREE.ExtrudeGeometry(shape, {
    depth: h,
    bevelEnabled: true,
    bevelThickness: bevel,
    bevelSize: bevel,
    bevelSegments: 3,
  });
  geo.rotateX(-Math.PI / 2);
  geo.center();
  return geo;
}

// ─────────────────────────── Cinema GLSL Shaders ─────────────────────────

/**
 * Precision chamfered 3D anodized block geometry for the instanced pulse cube grid.
 */
function createBeveledCubeGeo(size = 0.255, height = 0.24, bevel = 0.016) {
  const s = size * 0.5 - bevel;
  const shape = new THREE.Shape();
  shape.moveTo(-s, -s);
  shape.lineTo(s, -s);
  shape.lineTo(s, s);
  shape.lineTo(-s, s);
  shape.closePath();

  const geo = new THREE.ExtrudeGeometry(shape, {
    depth: Math.max(0.04, height - bevel * 2),
    bevelEnabled: true,
    bevelThickness: bevel,
    bevelSize: bevel,
    bevelSegments: 2,
    curveSegments: 1,
  });
  geo.rotateX(-Math.PI / 2);
  geo.center();
  return geo;
}

/**
 * GPU-Instanced 3D Cube Matrix Shader:
 *   - Real 3D beveled obsidian-graphite cubes separated by architectural gaps.
 *   - Reacts physically (vertical recoil & outward 3D echo ripples) to the live downward
 *     optical pulse beam AND adapts dynamically to DPI, Scroll Mode/Torque, Haptics
 *     Intensity/Waveform, and Actions Ring Slice direction!
 *   - Illuminates chamfered top edges, inner trench walls facing the beam, and impact core.
 */
function createCubeMatrixMaterial() {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: true,
    uniforms: {
      uBeamPhase:    { value: 0 },
      uWavePhase:    { value: 0 },
      uWavePhase2:   { value: 0 },
      uImpact:       { value: new THREE.Vector2(0.12, 0.08) },
      uWaveSpeed:    { value: 2.2 },
      uWaveFreq:     { value: 3.2 },
      uWaveAmp:      { value: 0.072 },
      uBurstAge:     { value: 99.0 },
      uBurstStrength:{ value: 0.0 },
      uColorA:       { value: new THREE.Color(0x28dce8) },
      uColorB:       { value: new THREE.Color(0xf6aa5c) },
      uColorMix:     { value: 0.0 },
      uSliceAngle:   { value: 0.0 },
      uSliceWeight:  { value: 0.0 },
      uEnergyScale:  { value: 1.0 },
    },
    vertexShader: /* glsl */ `
      uniform float uBeamPhase;
      uniform float uWavePhase;
      uniform float uWavePhase2;
      uniform vec2  uImpact;
      uniform float uWaveSpeed;
      uniform float uWaveFreq;
      uniform float uWaveAmp;
      uniform float uBurstAge;
      uniform float uBurstStrength;
      uniform float uSliceAngle;
      uniform float uSliceWeight;
      uniform float uEnergyScale;

      varying vec3  vNormal;
      varying vec3  vWorldPos;
      varying vec3  vLocalPos;
      varying float vPulseGlow;
      varying float vImpactHot;
      varying float vFade;
      varying vec2  vToCenter;

      void main() {
        vec3 instCenter = (modelMatrix * instanceMatrix * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
        vec2 delta = instCenter.xz - uImpact;
        float r = length(delta);

        vFade = smoothstep(4.65, 1.55, r);

        // 1. Silky continuous breathing pulse (ZERO sawtooth strobe or phase jump!)
        float smoothBeat = pow(0.5 + 0.5 * sin(uBeamPhase * 6.2831853), 2.0);

        // 2. Continuous integrated primary + secondary harmonic 3D echo waves
        float ring1 = pow(max(0.0, 0.5 + 0.5 * sin(r * uWaveFreq - uWavePhase)), 2.6);
        float ring2 = pow(max(0.0, 0.5 + 0.5 * sin(r * (uWaveFreq * 1.38) - uWavePhase2 + 1.4)), 3.6) * 0.48;

        // 3. Smooth damped one-shot echo shockwave
        float burstR = uBurstAge * (max(1.8, uWaveSpeed) * 1.25);
        float burstWave = exp(-pow((r - burstR) * 2.3, 2.0)) * exp(-uBurstAge * 1.8) * smoothstep(0.0, 0.09, uBurstAge) * uBurstStrength;

        // 4. Directional Actions Ring slice highlight echo
        float dirBoost = 0.0;
        if (uSliceWeight > 0.01 && r > 0.18) {
          float ang = atan(delta.y, delta.x);
          float dAng = abs(atan(sin(ang - uSliceAngle), cos(ang - uSliceAngle)));
          dirBoost = exp(-dAng * dAng * 4.2) * exp(-r * 0.45) * uSliceWeight * (0.68 + 0.32 * sin(r * 4.0 - uWavePhase * 1.1));
        }

        // Smooth physical center cushion recoil + fluid radial 3D wave
        float centerWell = exp(-r * r * 3.0);
        float recoil = -centerWell * (0.040 + 0.028 * smoothBeat) * uEnergyScale;
        float env = exp(-r * 0.42);
        float rippleLift = ((ring1 * 0.85 + ring2) * env + burstWave * 1.15 + dirBoost * 0.80) * uWaveAmp * uEnergyScale;

        vec4 worldPos = modelMatrix * instanceMatrix * vec4(position, 1.0);
        worldPos.y += (recoil + rippleLift) * vFade;

        vWorldPos = worldPos.xyz;
        vLocalPos = position;
        vNormal = normalize(mat3(modelMatrix) * mat3(instanceMatrix) * normal);
        vPulseGlow = clamp((ring1 * 0.85 + ring2 * 0.65) * env * 1.05 + burstWave * 1.35 + dirBoost * 1.20, 0.0, 1.85) * uEnergyScale;
        vImpactHot = centerWell * (0.72 + 0.42 * smoothBeat) * uEnergyScale;
        vToCenter = r > 0.001 ? normalize(-delta) : vec2(0.0, 0.0);

        gl_Position = projectionMatrix * viewMatrix * worldPos;
      }
    `,
    fragmentShader: /* glsl */ `
      uniform vec3  uColorA;
      uniform vec3  uColorB;
      uniform float uColorMix;
      uniform float uEnergyScale;

      varying vec3  vNormal;
      varying vec3  vWorldPos;
      varying vec3  vLocalPos;
      varying float vPulseGlow;
      varying float vImpactHot;
      varying float vFade;
      varying vec2  vToCenter;

      void main() {
        if (vFade < 0.015) discard;

        vec3 N = normalize(vNormal);
        vec3 V = normalize(cameraPosition - vWorldPos);
        vec3 accent = mix(uColorA, uColorB, clamp(uColorMix, 0.0, 1.0));
        vec3 hotCore = mix(accent, vec3(0.95, 0.99, 1.0), 0.58);

        vec3 baseCol = vec3(0.045, 0.052, 0.068);

        vec3 L1 = normalize(vec3(3.8, 7.5, 4.6));
        vec3 H1 = normalize(L1 + V);
        float diff1 = max(dot(N, L1), 0.0);
        float spec1 = pow(max(dot(N, H1), 0.0), 42.0);

        vec3 L2 = normalize(vec3(-4.5, 4.2, -3.5));
        float diff2 = max(dot(N, L2), 0.0);

        vec3 col = baseCol * (0.48 + diff1 * 0.78 + diff2 * 0.25) + vec3(0.42, 0.48, 0.58) * spec1 * 0.45;

        float topMask = smoothstep(0.06, 0.115, vLocalPos.y);
        float edgeDist = max(abs(vLocalPos.x), abs(vLocalPos.z));
        float bevelRim = smoothstep(0.092, 0.124, edgeDist) * smoothstep(-0.02, 0.11, vLocalPos.y);

        float sideFacing = max(0.0, dot(normalize(vec2(N.x, N.z) + vec2(0.0001)), vToCenter)) * (1.0 - abs(N.y));
        float lowerTrench = smoothstep(0.09, -0.10, vLocalPos.y) * (1.0 - abs(N.y));

        float rimEnergy = (bevelRim * 1.12 + topMask * 0.22) * vPulseGlow;
        float wallEnergy = (sideFacing * 0.62 + lowerTrench * 0.68) * (vPulseGlow * 0.82 + vImpactHot * 0.88);
        float impactBloom = (topMask * 0.68 + bevelRim * 1.38) * vImpactHot;

        col += accent * bevelRim * 0.11 * uEnergyScale;
        col += mix(accent, hotCore, clamp(vPulseGlow * 0.45, 0.0, 1.0)) * (rimEnergy * 0.76 + wallEnergy * 0.72);
        col += hotCore * impactBloom * 0.90;

        float fres = pow(1.0 - max(dot(N, V), 0.0), 3.2);
        col += mix(vec3(0.18, 0.24, 0.30), accent, clamp(vPulseGlow * 0.6 + vImpactHot, 0.0, 1.0)) * fres * 0.24;

        gl_FragColor = vec4(col, vFade);
      }
    `,
  });
}

/**
 * Radiant Sub-Floor Gap Glow Bed sitting directly beneath the 3D cube matrix
 * using continuous integrated phases (zero phase-jump strobing!).
 */
function createFloorGridShaderMaterial() {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    uniforms: {
      uBeamPhase:     { value: 0 },
      uWavePhase:     { value: 0 },
      uWavePhase2:    { value: 0 },
      uImpact:        { value: new THREE.Vector2(0.12, 0.08) },
      uWaveSpeed:     { value: 2.2 },
      uWaveFreq:      { value: 3.2 },
      uBurstAge:      { value: 99.0 },
      uBurstStrength: { value: 0.0 },
      uColorA:        { value: new THREE.Color(0x24dae8) },
      uColorB:        { value: new THREE.Color(0xf6aa5c) },
      uColorMix:      { value: 0.0 },
      uEnergyScale:   { value: 1.0 },
    },
    vertexShader: /* glsl */ `
      varying vec3 vWorldPos;
      void main() {
        vec4 wp = modelMatrix * vec4(position, 1.0);
        vWorldPos = wp.xyz;
        gl_Position = projectionMatrix * viewMatrix * wp;
      }
    `,
    fragmentShader: /* glsl */ `
      varying vec3 vWorldPos;
      uniform float uBeamPhase;
      uniform float uWavePhase;
      uniform float uWavePhase2;
      uniform vec2  uImpact;
      uniform float uWaveSpeed;
      uniform float uWaveFreq;
      uniform float uBurstAge;
      uniform float uBurstStrength;
      uniform vec3  uColorA;
      uniform vec3  uColorB;
      uniform float uColorMix;
      uniform float uEnergyScale;

      void main() {
        vec2 p = vWorldPos.xz - uImpact;
        float r = length(p);
        float fade = smoothstep(5.0, 1.2, r);
        if (fade < 0.01) discard;

        float smoothBeat = pow(0.5 + 0.5 * sin(uBeamPhase * 6.2831853), 2.0);
        float ring1 = pow(max(0.0, 0.5 + 0.5 * sin(r * uWaveFreq - uWavePhase)), 2.6);
        float ring2 = pow(max(0.0, 0.5 + 0.5 * sin(r * (uWaveFreq * 1.38) - uWavePhase2 + 1.4)), 3.8) * 0.50;
        float env = exp(-r * 0.52);

        float burstR = uBurstAge * (max(1.8, uWaveSpeed) * 1.25);
        float burst = exp(-pow((r - burstR) * 2.3, 2.0)) * exp(-uBurstAge * 1.8) * smoothstep(0.0, 0.09, uBurstAge) * uBurstStrength;

        float corePool = exp(-r * r * 1.85) * (0.78 + 0.36 * smoothBeat);
        float amp = ((ring1 + ring2) * env * 0.88 + burst * 1.30 + corePool) * uEnergyScale;

        vec3 accent = mix(uColorA, uColorB, clamp(uColorMix, 0.0, 1.0));
        vec3 hot = mix(accent, vec3(0.96, 0.99, 1.0), 0.52);
        vec3 col = mix(accent, hot, clamp(corePool * 0.72 + burst * 0.75, 0.0, 1.0)) * amp;

        gl_FragColor = vec4(col, clamp(amp * fade * 0.86, 0.0, 0.90));
      }
    `,
  });
}

/**
 * Silky Continuous Volumetric Optical Pulse Beam Shader (zero strobing, fluid downward energy flow!).
 */
function createVolumetricOpticalBeamMaterial() {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending,
    uniforms: {
      uBeamPhase: { value: 0 },
      uOpacity:   { value: 1.0 },
      uFocus:     { value: 0.45 },
      uColorA:    { value: new THREE.Color(0x24dce8) },
      uColorB:    { value: new THREE.Color(0xf6aa5c) },
      uColorMix:  { value: 0.0 },
    },
    vertexShader: /* glsl */ `
      varying vec2 vUv;
      varying vec3 vNormal;
      varying vec3 vViewDir;
      void main() {
        vUv = uv;
        vec4 wp = modelMatrix * vec4(position, 1.0);
        vNormal = normalize(mat3(modelMatrix) * normal);
        vViewDir = normalize(cameraPosition - wp.xyz);
        gl_Position = projectionMatrix * viewMatrix * wp;
      }
    `,
    fragmentShader: /* glsl */ `
      varying vec2 vUv;
      varying vec3 vNormal;
      varying vec3 vViewDir;
      uniform float uBeamPhase;
      uniform float uOpacity;
      uniform float uFocus;
      uniform vec3  uColorA;
      uniform vec3  uColorB;
      uniform float uColorMix;

      void main() {
        float bottomFade = smoothstep(0.0, 0.16, vUv.y);
        float topFade    = smoothstep(1.0, 0.84, vUv.y);
        float ndv = abs(dot(normalize(vNormal), normalize(vViewDir)));
        float mistEdge = pow(ndv, mix(1.25, 2.05, uFocus));

        // Silky seamless sinusoidal downward flow (zero wrap-snap strobe!)
        float flow1 = pow(0.5 + 0.5 * sin((vUv.y * 1.35 + uBeamPhase) * 6.2831853), 3.0);
        float flow2 = pow(0.5 + 0.5 * sin((vUv.y * 2.40 + uBeamPhase * 1.45) * 6.2831853), 4.0) * 0.42;
        float smoothBeat = pow(0.5 + 0.5 * sin(uBeamPhase * 6.2831853), 2.0);

        float rays = 0.86 + 0.14 * sin(vUv.x * 37.699 + uBeamPhase * 2.4);
        float impactHot = exp(-vUv.y * 4.2) * (0.52 + 0.34 * smoothBeat);
        float emitterHot = pow(vUv.y, 2.4) * 0.68;

        vec3 accent = mix(uColorA, uColorB, clamp(uColorMix, 0.0, 1.0));
        vec3 coreWhite = mix(accent, vec3(0.96, 1.0, 1.0), 0.68);
        float pulseIntensity = 0.34 + flow1 * 0.82 + flow2 + impactHot + emitterHot;

        vec3 col = mix(accent, coreWhite, clamp(flow1 * 0.65 + impactHot * 0.58, 0.0, 1.0));
        float alpha = bottomFade * topFade * mistEdge * rays * pulseIntensity * 0.44 * uOpacity;
        gl_FragColor = vec4(col, clamp(alpha, 0.0, 0.88));
      }
    `,
  });
}

/**
 * Layer 1: True Viewpoint-Aligned HARD Pure White Silhouette Outline Shader (BackSide Inverted Hull)!
 * Extrudes vertices in screen-aligned clip space by a constant pixel width so ANY visible silhouette
 * of the hovered/selected control from the current camera viewpoint gets a razor-crisp hard white outline!
 */
function createControlOutlineMaterial() {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthTest: true,
    depthWrite: false,
    side: THREE.BackSide,
    uniforms: {
      uIntensity:  { value: 0.0 },
      uColor:      { value: new THREE.Color(0xffffff) },
      uOutlinePx:  { value: 3.2 },
      uResolution: { value: new THREE.Vector2(1360, 820) },
    },
    vertexShader: /* glsl */ `
      uniform float uOutlinePx;
      uniform vec2  uResolution;
      void main() {
        vec4 clipPos = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        vec3 viewNorm = normalize(normalMatrix * normal);
        vec2 clipNorm = (projectionMatrix * vec4(viewNorm, 0.0)).xy;
        float len = length(clipNorm);
        if (len > 0.0001) {
          vec2 offset = (clipNorm / len) * (uOutlinePx * 2.0 / max(uResolution, vec2(1.0))) * clipPos.w;
          clipPos.xy += offset;
        }
        // Push slightly BEHIND front faces so the control's own surface occludes the interior
        // 100%, leaving ONLY a razor-sharp hard white silhouette outline around what we see!
        clipPos.z += 0.00045 * clipPos.w;
        gl_Position = clipPos;
      }
    `,
    fragmentShader: /* glsl */ `
      uniform float uIntensity;
      uniform vec3  uColor;
      void main() {
        if (uIntensity < 0.01) discard;
        // Hard crisp pure white outline!
        float hardAlpha = smoothstep(0.08, 0.40, uIntensity);
        gl_FragColor = vec4(uColor, clamp(hardAlpha * 0.98, 0.0, 1.0));
      }
    `,
  });
}

/**
 * Layer 2: Front-Facing Hard Pure White Bevel Contour Rim + Clean Subtle White Selection Wash!
 * Highlights visible front-facing CAD creases & rims from the current viewpoint in crisp pure white.
 */
function createControlHighlightMaterial() {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthTest: true,
    depthWrite: false,
    side: THREE.FrontSide,
    blending: THREE.NormalBlending,
    polygonOffset: true,
    polygonOffsetFactor: -2,
    polygonOffsetUnits: -2,
    uniforms: {
      uTime:      { value: 0 },
      uIntensity: { value: 0.0 },
      uColor:     { value: new THREE.Color(0xffffff) },
      uInflate:   { value: 0.0038 },
    },
    vertexShader: /* glsl */ `
      uniform float uInflate;
      varying vec3 vNormal;
      varying vec3 vWorldPos;
      varying vec3 vViewDir;
      void main() {
        vec3 inflated = position + normal * uInflate;
        vec4 wp = modelMatrix * vec4(inflated, 1.0);
        vWorldPos = wp.xyz;
        vNormal = normalize(mat3(modelMatrix) * normal);
        vViewDir = normalize(cameraPosition - wp.xyz);
        gl_Position = projectionMatrix * viewMatrix * wp;
      }
    `,
    fragmentShader: /* glsl */ `
      uniform float uTime;
      uniform float uIntensity;
      uniform vec3  uColor;
      varying vec3 vNormal;
      varying vec3 vWorldPos;
      varying vec3 vViewDir;

      void main() {
        if (uIntensity < 0.008) discard;
        vec3 N = normalize(vNormal);
        vec3 V = normalize(vViewDir);
        float ndv = clamp(abs(dot(N, V)), 0.0, 1.0);

        // HARD crisp white viewpoint-aligned bevel rim + clean bright white hover sheen
        float fres = pow(1.0 - ndv, 1.85);
        float hardRim = smoothstep(0.22, 0.50, fres);
        float cleanTint = 0.13;

        float alpha = (hardRim * 0.96 + cleanTint) * uIntensity;
        gl_FragColor = vec4(uColor, clamp(alpha, 0.0, 0.98));
      }
    `,
  });
}

function createFluxFilamentMaterial(phaseOffset = 0, bright = 1.0) {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    uniforms: {
      uFluxPhase: { value: 0 },
      uOpacity:   { value: 0.0 },
      uPhase:     { value: phaseOffset },
      uBright:    { value: bright },
    },
    vertexShader: /* glsl */ `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: /* glsl */ `
      varying vec2 vUv;
      uniform float uFluxPhase;
      uniform float uOpacity;
      uniform float uPhase;
      uniform float uBright;

      void main() {
        float tip = pow(max(0.0, sin(vUv.x * 3.14159265)), 1.65);
        float pulse = 0.55 + 0.45 * sin(vUv.x * 7.5 - uFluxPhase + uPhase);
        vec3 col = mix(vec3(0.20, 0.78, 0.86), vec3(0.82, 0.98, 1.0), pulse * tip);
        float a = tip * (0.42 + 0.58 * pulse) * uOpacity * uBright;
        gl_FragColor = vec4(col, a);
      }
    `,
  });
}

function createFresnelGlassMaterial() {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    side: THREE.FrontSide,
    blending: THREE.AdditiveBlending,
    uniforms: {
      uOpacity: { value: 0.0 },
      uColor:   { value: new THREE.Color(0xc8d6e8) },
    },
    vertexShader: /* glsl */ `
      varying vec3 vNormal;
      varying vec3 vViewDir;
      void main() {
        vec4 wp = modelMatrix * vec4(position, 1.0);
        vNormal = normalize(mat3(modelMatrix) * normal);
        vViewDir = normalize(cameraPosition - wp.xyz);
        gl_Position = projectionMatrix * viewMatrix * wp;
      }
    `,
    fragmentShader: /* glsl */ `
      varying vec3 vNormal;
      varying vec3 vViewDir;
      uniform float uOpacity;
      uniform vec3 uColor;
      void main() {
        float fresnel = pow(1.0 - max(0.0, dot(normalize(vNormal), normalize(vViewDir))), 2.8);
        gl_FragColor = vec4(uColor, fresnel * 0.44 * uOpacity);
      }
    `,
  });
}

// ─────────────────────────── 3D Studio Engine v3 ─────────────────────────

export class MouseStudio3D {
  constructor(canvas, { onHoverButton, onClickButton, onClickBackground, onProjectPins }) {
    this.canvas = canvas;
    this.onHoverButton = onHoverButton || (() => {});
    this.onClickButton = onClickButton || (() => {});
    this.onClickBackground = onClickBackground || (() => {});
    this.onProjectPins = onProjectPins || (() => {});

    this.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.ambientPaused = this.reducedMotion;
    this.tab = 'device';

    // Deep-cloned live alignment & material state
    this.alignConfig = JSON.parse(JSON.stringify(DEFAULT_ALIGN_CONFIG));
    this.tunableParts = {}; // key -> THREE.Group

    this.modeWeights = {
      cyanPool: 1,
      scrollMacro: 0,
      hapticGlass: 0,
      ringHalo: 0,
      xrayLab: 0,
    };
    this.modeTargets = { ...this.modeWeights };

    this.forceNorm = 0.38;
    this.selectedRingSlice = 0;
    this.ringEnabled = true;
    this.ringCancelRadius = 40;
    this.connected = true;
    this.batteryPct = 100;
    this.charging = false;
    this.thumbwheelMode = 'native';
    this.twLedPulse = 0.0;

    this.dpi = 1100;
    this.scrollMode = 'smart';
    this.smartshiftThreshold = 15;
    this.torque = 75;
    this.scrollSpeed = 1.0;
    this.scrollSmoothness = 0;
    this.scrollAccel = 0;
    this.hiresInvert = false;
    this.hapticEnabled = true;
    this.hapticLevel = 65;
    this.activeFeelWave = 3;
    this.pressedCids = new Set();
    this.divertedPressedCids = new Set();
    this.evdevPressedCids = new Set();
    this.domPressedCids = new Set();
    this.pressAnim = new Map();
    this.liveMotion = {
      vx: 0, vz: 0,
      targetVx: 0, targetVz: 0,
      px: 0, pz: 0,
      pitch: 0, bank: 0, yaw: 0,
      speed: 0,
    };
    // Continuous monotonically-integrated shader phases (ZERO phase-jump strobing when speed/DPI/motion changes!)
    this.phases = {
      beam: 0.0,
      wave1: 0.0,
      wave2: 0.0,
      flux: 0.0,
      acoustic: 0.0,
      ring: 0.0,
    };
    this.ringTheme = {
      id: 'studio',
      accent: new THREE.Color('#e8a864'),
      accentBright: new THREE.Color('#ffe0b2'),
      secondary: new THREE.Color('#3ce0e8'),
      segIdle: new THREE.Color('#18202e'),
      segHover: new THREE.Color('#2e2318'),
    };
    this.ringThemeCurrent = {
      accent: new THREE.Color('#e8a864'),
      accentBright: new THREE.Color('#ffe0b2'),
      secondary: new THREE.Color('#3ce0e8'),
      segIdle: new THREE.Color('#18202e'),
    };
    this.ringSizeScale = 1.0;
    this.ringSizeScaleSmooth = 1.0;
    this.ringAnimate = true;
    this.ringSliceLifts = new Array(8).fill(0);
    this.ringCompassAngle = -Math.PI / 2;
    this.ringConfirmPulse = 0.0;
    this.smoothAnim = {
      pulseRate: 1.05,
      waveSpeed: 2.1,
      waveFreq: 3.1,
      waveAmp: 0.068,
      energy: 0.92,
      colorMix: 0.0,
      impactX: 0.12,
      impactZ: 0.08,
      motionBoost: 0.0,
    };
    this.lastRealScrollAge = 99.0;
    this.modeShiftCap = null;
    this.sideBtnCaps = new Map();
    this.lmbPivot = null;
    this.rmbPivot = null;
    this.thumbPadMesh = null;
    this.thumbPadBasePos = null;
    this.remappedCids = new Set();
    this.hoveredCid = null;
    this.selectedCid = null;

    this.wheelAngle = 0;
    this.wheelVelocity = 1.2;
    this.thumbWheelAngle = 0;
    this.thumbWheelVelocity = 0;
    this.shockwaves = [];
    this.vibeIntensity = 0;
    this.vibeTime = 0;
    this.vibeFreq = 45;
    this.hapticBurstAge = 99.0;
    this.floorBurstAge = 99.0;
    this.floorBurstStrength = 0.0;
    this.floorBurstColorMix = -1.0;

    const p0 = CAMERA_PRESETS.device;
    this.cam = { ...p0 };
    this.camTarget = { ...p0 };
    this.userOrbitOffset = { az: 0, pol: 0 };
    this.dragging = false;
    this.dragMoved = false;
    this.lastPtr = { x: 0, y: 0 };
    this.ptrNdc = new THREE.Vector2(-9, -9);

    this.interactables = [];
    this.mouseShellMeshes = [];
    this.buttonMeshes = new Map();
    this.buttonHalos = new Map();
    this.controlHighlights = new Map();      // cid -> [{ mesh, mat }]
    this.controlHighlightLevels = new Map(); // cid -> current smoothed intensity
    this.ringSliceMeshes = [];
    this.beamRings = [];
    this.fluxMaterials = [];
    this.scanShellMats = [];
    this.shellMat = null;
    this.thumbPadMat = null;
    this._lastThumbRingDensity = Math.round(this.alignConfig.materials.thumbBumpScale);
    this.thumbPadMaps = createThumbPadRubberBumpMaps(this._lastThumbRingDensity);
    this.depthPrepassMeshes = [];
    this.glassRimMeshes = [];
    this.xrayWireMeshes = [];
    this.ledDots = [];

    this._initRenderer();
    this._initScene();
    this._buildStudioFloor();
    this._buildOpticalBeam();
    this._buildMouseAssembly();
    this._loadRealMXMaster4GLB();
    this._buildScrollFlux();
    this._buildHapticCutaway();
    this._buildHolographicRing();
    this.applyAlignConfig(this.alignConfig);
    this._bindEvents();

    this.clock = new THREE.Clock();
    this._animate = this._animate.bind(this);
    this._raf = requestAnimationFrame(this._animate);
  }

  _initRenderer() {
    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      antialias: true,
      alpha: true,
      powerPreference: 'high-performance',
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = this.alignConfig.materials.exposure;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.resize();
  }

  _initScene() {
    this.scene = new THREE.Scene();
    this.scene.environment = createStudioEnvironment(this.renderer);

    const w = this.canvas.clientWidth || 1360;
    const h = this.canvas.clientHeight || 820;
    this.camera = new THREE.PerspectiveCamera(27, w / h, 0.08, 80);

    // Sculpted high-contrast hard-surface lighting rig
    const key = new THREE.SpotLight(0xfff6ec, 30, 26, Math.PI / 4.0, 0.74, 1.3);
    key.position.set(4.8, 7.6, 5.4);
    key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    key.shadow.bias = -0.0004;
    this.scene.add(key);

    // Overhead crisp specular strip defining hard lines & CNC MagSpeed wheel ribs
    const topSpec = new THREE.DirectionalLight(0xf6faff, 1.65);
    topSpec.position.set(-0.6, 8.6, 4.4);
    this.scene.add(topSpec);

    // Raking side rim light specifically illuminating the molded rubber bumps on the +X thumb pad!
    const thumbRake = new THREE.DirectionalLight(0xfff0dc, 1.55);
    thumbRake.position.set(6.5, 2.2, 1.8);
    this.scene.add(thumbRake);

    const coolRim = new THREE.DirectionalLight(0x74c6d4, 0.55);
    coolRim.position.set(-5.8, 2.8, -4.4);
    this.scene.add(coolRim);

    const hemi = new THREE.HemisphereLight(0xdce4f0, 0x090b10, 0.50);
    this.scene.add(hemi);

    this.lraLight = new THREE.PointLight(0xffac54, 0.0, 4.2, 1.6);
    this.scene.add(this.lraLight);

    this.sensorBounce = new THREE.PointLight(0x36e6f0, 2.2, 5.2, 1.55);
    this.sensorBounce.position.set(0.12, 0.24, 0.08);
    this.scene.add(this.sensorBounce);

    this.echoLight = new THREE.PointLight(0x28dce8, 1.6, 7.0, 1.45);
    this.echoLight.position.set(0.12, 0.06, 0.08);
    this.scene.add(this.echoLight);

    this.raycaster = new THREE.Raycaster();
    this.resize();
  }

  _buildStudioFloor() {
    // 1. Radiant Sub-Floor Pulse Bed sitting directly beneath the 3D cubes
    //    so light floods UP through the crisp architectural gaps between cubes!
    this.floorMat = createFloorGridShaderMaterial();
    const underBed = new THREE.Mesh(new THREE.PlaneGeometry(14, 14), this.floorMat);
    underBed.rotation.x = -Math.PI / 2;
    underBed.position.y = -0.22;
    underBed.renderOrder = 0;
    this.scene.add(underBed);

    // 2. Real 3D Instanced Matrix of 625 Chamfered Anodized Cubes (25 × 25 with 0.070 gaps!)
    const gridN = 25;
    const pitch = 0.330;
    const cubeSize = 0.258; // Crisp 0.072 architectural gap between every cube!
    const cubeHeight = 0.24;
    const cubeGeo = createBeveledCubeGeo(cubeSize, cubeHeight, 0.015);
    this.cubeMatrixMat = createCubeMatrixMaterial();

    const total = gridN * gridN;
    this.cubeMatrix = new THREE.InstancedMesh(cubeGeo, this.cubeMatrixMat, total);
    this.cubeMatrix.renderOrder = 1;
    this.cubeMatrix.frustumCulled = false;

    const dummy = new THREE.Object3D();
    const half = (gridN - 1) * 0.5;
    let idx = 0;
    for (let ix = 0; ix < gridN; ix++) {
      for (let iz = 0; iz < gridN; iz++) {
        const cx = (ix - half) * pitch + 0.12;
        const cz = (iz - half) * pitch + 0.08;
        dummy.position.set(cx, -0.145, cz);
        dummy.rotation.set(0, 0, 0);
        dummy.scale.set(1, 1, 1);
        dummy.updateMatrix();
        this.cubeMatrix.setMatrixAt(idx++, dummy.matrix);
      }
    }
    this.cubeMatrix.instanceMatrix.needsUpdate = true;
    this.scene.add(this.cubeMatrix);
  }

  _buildOpticalBeam() {
    this.beamGroup = new THREE.Group();
    this.scene.add(this.beamGroup);
    this.tunableParts.opticalBeam = this.beamGroup;

    this.beamMat = createVolumetricOpticalBeamMaterial();

    // Outer volumetric optical cone shooting down from the Darkfield 8K sensor into the 3D cubes
    this.beamOuterCone = new THREE.Mesh(
      new THREE.CylinderGeometry(0.11, 0.78, 0.74, 32, 1, true),
      this.beamMat,
    );
    this.beamOuterCone.position.y = 0.34;
    this.beamOuterCone.renderOrder = 2;
    this.beamGroup.add(this.beamOuterCone);

    // Tight high-energy laser pulse shaft firing straight into the center cube cluster (continuous phase!)
    this.beamCoreMat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uBeamPhase: { value: 0 },
        uOpacity:   { value: 1.0 },
        uColorA:    { value: new THREE.Color(0x36ecfa) },
        uColorB:    { value: new THREE.Color(0xffbd6e) },
        uColorMix:  { value: 0.0 },
      },
      vertexShader: /* glsl */ `
        varying vec2 vUv;
        void main() {
          vUv = uv;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: /* glsl */ `
        varying vec2 vUv;
        uniform float uBeamPhase;
        uniform float uOpacity;
        uniform vec3  uColorA;
        uniform vec3  uColorB;
        uniform float uColorMix;
        void main() {
          float dx = abs(vUv.x - 0.5) * 2.0;
          float spine = exp(-dx * dx * 22.0);
          float vFade = smoothstep(0.0, 0.10, vUv.y) * smoothstep(1.0, 0.86, vUv.y);
          float bolt = pow(0.5 + 0.5 * sin((vUv.y * 1.35 + uBeamPhase) * 6.2831853), 4.0);
          float bolt2 = pow(0.5 + 0.5 * sin((vUv.y * 2.40 + uBeamPhase * 1.45) * 6.2831853), 5.0) * 0.45;
          vec3 accent = mix(uColorA, uColorB, clamp(uColorMix, 0.0, 1.0));
          vec3 hot = mix(accent, vec3(1.0, 1.0, 1.0), clamp(0.48 + bolt * 0.48, 0.0, 1.0));
          float alpha = spine * vFade * (0.44 + bolt * 0.82 + bolt2) * uOpacity;
          gl_FragColor = vec4(hot, clamp(alpha, 0.0, 0.94));
        }
      `,
    });
    const coreA = new THREE.Mesh(new THREE.PlaneGeometry(0.32, 0.74), this.beamCoreMat);
    coreA.position.y = 0.34;
    coreA.rotation.y = 0.78;
    coreA.renderOrder = 2;
    this.beamGroup.add(coreA);

    const coreB = coreA.clone();
    coreB.rotation.y = -0.78;
    this.beamGroup.add(coreB);

    // 3 Animated Descending Pulse Rings firing straight down the laser into the 3D cubes
    this.beamRings = [];
    for (let i = 0; i < 3; i++) {
      const rMat = new THREE.MeshBasicMaterial({
        color: 0x56f2ff,
        transparent: true,
        opacity: 0.0,
        side: THREE.DoubleSide,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
      const ring = new THREE.Mesh(new THREE.RingGeometry(0.08, 0.125, 40), rMat);
      ring.rotation.x = -Math.PI / 2;
      ring.renderOrder = 2;
      this.beamGroup.add(ring);
      this.beamRings.push({ mesh: ring, mat: rMat, phaseOffset: i / 3 });
    }

    // Impact Splash Flare directly on top of the center 3D cubes (silky breathing glow, zero strobe!)
    this.beamImpactMat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uBeamPhase: { value: 0 },
        uOpacity:   { value: 1.0 },
        uColorA:    { value: new THREE.Color(0x36ecfa) },
        uColorB:    { value: new THREE.Color(0xffba68) },
        uColorMix:  { value: 0.0 },
      },
      vertexShader: /* glsl */ `
        varying vec2 vUv;
        void main() {
          vUv = uv;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: /* glsl */ `
        varying vec2 vUv;
        uniform float uBeamPhase;
        uniform float uOpacity;
        uniform vec3  uColorA;
        uniform vec3  uColorB;
        uniform float uColorMix;
        void main() {
          vec2 p = vUv * 2.0 - 1.0;
          float r = length(p);
          if (r > 1.0) discard;
          float smoothBeat = pow(0.5 + 0.5 * sin(uBeamPhase * 6.2831853), 2.0);
          float core = exp(-r * r * 12.0) * (0.82 + 0.36 * smoothBeat);
          float pRing = fract(uBeamPhase);
          float ringEnv = sin(pRing * 3.14159265);
          float ring = exp(-pow((r - (0.20 + pRing * 0.72)) * 9.0, 2.0)) * ringEnv * (1.0 - r);
          vec3 accent = mix(uColorA, uColorB, clamp(uColorMix, 0.0, 1.0));
          vec3 col = mix(accent, vec3(1.0, 1.0, 1.0), clamp(core * 0.68, 0.0, 1.0));
          gl_FragColor = vec4(col, clamp((core + ring * 0.75) * 0.84 * uOpacity, 0.0, 0.92));
        }
      `,
    });
    const impactDisc = new THREE.Mesh(new THREE.PlaneGeometry(1.15, 1.15), this.beamImpactMat);
    impactDisc.rotation.x = -Math.PI / 2;
    impactDisc.position.y = 0.005;
    impactDisc.renderOrder = 2;
    this.beamGroup.add(impactDisc);
  }

  _registerInteractable(mesh, cid, inflate = 0.0045) {
    mesh.userData.cid = cid;
    this.interactables.push(mesh);
    if (!this.buttonMeshes.has(cid)) this.buttonMeshes.set(cid, []);
    this.buttonMeshes.get(cid).push(mesh);

    // Layer 1: Hard Viewpoint-Aligned Pure White Silhouette Outline (BackSide clip-space hull!)
    const oMat = createControlOutlineMaterial();
    const oMesh = new THREE.Mesh(mesh.geometry, oMat);
    oMesh.renderOrder = 7;
    oMesh.visible = false;
    oMesh.raycast = () => {};
    mesh.add(oMesh);

    // Layer 2: Crisp Hard Front-Facing Pure White Bevel Contour Rim!
    const hMat = createControlHighlightMaterial();
    hMat.uniforms.uInflate.value = inflate;
    const hMesh = new THREE.Mesh(mesh.geometry, hMat);
    hMesh.renderOrder = 8;
    hMesh.visible = false;
    hMesh.raycast = () => {};
    mesh.add(hMesh);

    // Layer 3: Razor-Hard Pure White CAD Perimeter Contour Line (keeps recessed panels like
    // Thumb Pad & Clickers sharply outlined in crisp white from every viewpoint!)
    let edgeLine = null;
    let edgeMat = null;
    if (cid !== CID.MIDDLE_CLICK && cid !== CID.THUMB_WHEEL) {
      const eGeo = new THREE.EdgesGeometry(mesh.geometry, 28);
      edgeMat = new THREE.LineBasicMaterial({
        color: 0xffffff,
        transparent: true,
        opacity: 0.0,
        depthTest: true,
        depthWrite: false,
      });
      edgeLine = new THREE.LineSegments(eGeo, edgeMat);
      edgeLine.renderOrder = 9;
      edgeLine.visible = false;
      edgeLine.raycast = () => {};
      mesh.add(edgeLine);
    }

    if (!this.controlHighlights.has(cid)) this.controlHighlights.set(cid, []);
    this.controlHighlights.get(cid).push({
      mesh: hMesh, mat: hMat,
      outlineMesh: oMesh, outlineMat: oMat,
      edgeLine, edgeMat,
    });
    if (!this.controlHighlightLevels.has(cid)) this.controlHighlightLevels.set(cid, 0.0);
  }

  _buildMouseAssembly() {
    this.hoverBaseY = 0.62;
    this.mouseRoot = new THREE.Group();
    this.mouseRoot.position.y = this.hoverBaseY;
    this.scene.add(this.mouseRoot);

    const brushedMetal = createBrushedMetalTexture();

    const cncSteelMat = new THREE.MeshStandardMaterial({
      color: 0xe6ecf5,
      map: brushedMetal,
      metalness: 0.96,
      roughness: 0.16,
      emissive: new THREE.Color(0x000000),
    });

    const mirrorChromeMat = new THREE.MeshStandardMaterial({
      color: 0xf8fbff,
      metalness: 0.99,
      roughness: 0.05,
    });

    const darkFluteMat = new THREE.MeshStandardMaterial({
      color: 0x262b35,
      metalness: 0.82,
      roughness: 0.32,
    });

    // ─── PART 1: Rotating 60-Tooth Dual-Band CNC MagSpeed Wheel ─────────
    this.wheelContainer = new THREE.Group();
    this.mouseRoot.add(this.wheelContainer);
    this.tunableParts.magSpeedWheel = this.wheelContainer;

    this.wheelGroup = new THREE.Group();
    this.wheelContainer.add(this.wheelGroup);

    const wheelCore = new THREE.Mesh(
      new THREE.CylinderGeometry(0.228, 0.228, 0.194, 56),
      darkFluteMat,
    );
    wheelCore.rotation.z = Math.PI / 2;
    this.wheelGroup.add(wheelCore);

    const bandGeo = createKnurledWheelBand(0.240, 0.072, 60, 0.0095);
    const leftBand = new THREE.Mesh(bandGeo, cncSteelMat);
    leftBand.position.x = -0.052;
    leftBand.castShadow = true;
    this.wheelGroup.add(leftBand);
    this._registerInteractable(leftBand, CID.MIDDLE_CLICK);

    const rightBand = new THREE.Mesh(bandGeo, cncSteelMat);
    rightBand.position.x = 0.052;
    rightBand.castShadow = true;
    this.wheelGroup.add(rightBand);
    this._registerInteractable(rightBand, CID.MIDDLE_CLICK);

    const centerCollar = new THREE.Mesh(
      new THREE.CylinderGeometry(0.236, 0.236, 0.032, 64),
      mirrorChromeMat,
    );
    centerCollar.rotation.z = Math.PI / 2;
    this.wheelGroup.add(centerCollar);
    this._registerInteractable(centerCollar, CID.MIDDLE_CLICK);

    for (const rx of [-0.091, -0.017, 0.017, 0.091]) {
      const rMesh = new THREE.Mesh(new THREE.TorusGeometry(0.234, 0.0042, 10, 64), mirrorChromeMat);
      rMesh.rotation.y = Math.PI / 2;
      rMesh.position.x = rx;
      this.wheelGroup.add(rMesh);
    }

    const hubMat = new THREE.MeshStandardMaterial({
      color: 0xa2acb8,
      map: brushedMetal,
      metalness: 0.92,
      roughness: 0.22,
    });
    const hubRecessMat = new THREE.MeshStandardMaterial({
      color: 0x3b4250,
      metalness: 0.85,
      roughness: 0.28,
    });
    for (const sx of [-0.092, 0.092]) {
      const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.188, 0.188, 0.012, 40), hubMat);
      hub.rotation.z = Math.PI / 2;
      hub.position.x = sx;
      this.wheelGroup.add(hub);

      const innerHub = new THREE.Mesh(new THREE.CylinderGeometry(0.115, 0.115, 0.016, 32), hubRecessMat);
      innerHub.rotation.z = Math.PI / 2;
      innerHub.position.x = sx;
      this.wheelGroup.add(innerHub);
    }

    // ─── PART 2: Razor-Sharp Chamfered Anodized Scroll Bezel Collar ─────
    this.scrollBezelGroup = new THREE.Group();
    // ─── PART 2: Scroll Bezel (hidden by default — real MX4 wheel cuts straight through clickers!) ──
    this.scrollBezelGroup = new THREE.Group();
    this.scrollBezelGroup.visible = false;
    this.mouseRoot.add(this.scrollBezelGroup);
    this.tunableParts.scrollBezel = this.scrollBezelGroup;

    // ─── PART 3: Crisp Hard-Surface Top Mode-Shift Button (0x00C4) ──────
    this.modeShiftGroup = new THREE.Group();
    this.mouseRoot.add(this.modeShiftGroup);
    this.tunableParts.modeShiftBtn = this.modeShiftGroup;

    const msCapMat = new THREE.MeshPhysicalMaterial({
      color: 0x35383f,
      roughness: 0.56,
      metalness: 0.04,
      clearcoat: 0.08,
      clearcoatRoughness: 0.52,
      emissive: new THREE.Color(0x000000),
    });
    const msCap = new THREE.Mesh(
      createHardSurfaceButton(0.118, 0.044, 0.205, 0.024, 0.007),
      msCapMat,
    );
    msCap.position.y = 0.008;
    msCap.castShadow = true;
    this.modeShiftGroup.add(msCap);
    this.modeShiftCap = msCap;
    this._registerInteractable(msCap, CID.SMART_SHIFT);

    // ─── PART 4: TWO-BAND CNC Aluminum Horizontal Thumb Wheel (Un-Ribbed Center Line) ──
    // Two ribbed brushed-aluminum bands split halfway by a smooth polished un-ribbed center band.
    this.thumbWheelContainer = new THREE.Group();
    this.mouseRoot.add(this.thumbWheelContainer);
    this.tunableParts.thumbWheel = this.thumbWheelContainer;

    // Machined dark inner bearing drum inside the carved side cavity
    const twBacking = new THREE.Mesh(
      new THREE.CylinderGeometry(0.114, 0.114, 0.500, 36),
      new THREE.MeshStandardMaterial({ color: 0x0b0d12, roughness: 0.55, metalness: 0.45 }),
    );
    twBacking.rotation.x = Math.PI / 2;
    twBacking.position.set(-0.016, 0, 0);
    this.thumbWheelContainer.add(twBacking);

    // Rotating horizontal thumb wheel barrel (axis along Z!)
    this.thumbWheelSpinner = new THREE.Group();
    this.thumbWheelSpinner.position.set(0.0, 0.0, 0);
    this.thumbWheelContainer.add(this.thumbWheelSpinner);

    // Dark anodized inner flute valley drum
    const twCore = new THREE.Mesh(
      new THREE.CylinderGeometry(0.115, 0.115, 0.476, 48),
      darkFluteMat,
    );
    twCore.rotation.x = Math.PI / 2;
    this.thumbWheelSpinner.add(twCore);

    const twMat = new THREE.MeshStandardMaterial({
      color: 0xe8edf4,
      map: brushedMetal,
      metalness: 0.92,
      roughness: 0.18,
      emissive: new THREE.Color(0x000000),
    });

    // Two ribbed machined aluminum bands (front & rear) leaving the un-ribbed center band!
    const twBandGeo = createThumbWheelCylinder(0.126, 0.198, 44, 0.0088);
    const twFrontBand = new THREE.Mesh(twBandGeo, twMat);
    twFrontBand.position.z = 0.136;
    twFrontBand.castShadow = true;
    this.thumbWheelSpinner.add(twFrontBand);
    this._registerInteractable(twFrontBand, CID.THUMB_WHEEL);

    const twRearBand = new THREE.Mesh(twBandGeo, twMat);
    twRearBand.position.z = -0.136;
    twRearBand.castShadow = true;
    this.thumbWheelSpinner.add(twRearBand);
    this._registerInteractable(twRearBand, CID.THUMB_WHEEL);

    // Smooth UN-RIBBED polished silver center band right halfway (Images 4, 5 & 7!)
    const twCenterCollar = new THREE.Mesh(
      new THREE.CylinderGeometry(0.124, 0.124, 0.068, 56),
      mirrorChromeMat,
    );
    twCenterCollar.rotation.x = Math.PI / 2;
    this.thumbWheelSpinner.add(twCenterCollar);
    this._registerInteractable(twCenterCollar, CID.THUMB_WHEEL);

    // Subtle crisp bevel rings flanking the center band & wheel ends
    for (const tz of [-0.238, -0.036, 0.036, 0.238]) {
      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(0.122, 0.0032, 10, 56),
        mirrorChromeMat,
      );
      ring.position.z = tz;
      this.thumbWheelSpinner.add(ring);
    }

    for (const tz of [-0.242, 0.242]) {
      const hubCap = new THREE.Mesh(
        new THREE.CylinderGeometry(0.118, 0.118, 0.012, 40),
        hubMat,
      );
      hubCap.rotation.x = Math.PI / 2;
      hubCap.position.z = tz;
      this.thumbWheelSpinner.add(hubCap);
    }

    // ─── Rear Status Light-Pipe Halo & Matte Dome Cap Behind Thumb Wheel ──
    // Authentic MX Master 4 matte-charcoal rear dome cap nestled inside a thin
    // smoked translucent polycarbonate horseshoe light-pipe rim (-Z behind wheel).
    const twLightGroup = new THREE.Group();
    twLightGroup.position.set(0.0, 0.0, -0.244);
    this.thumbWheelContainer.add(twLightGroup);

    // 1. Exposed matte-charcoal elongated dome cap (protrudes cleanly through the rim!)
    const twRearDomeGeo = new THREE.SphereGeometry(0.106, 40, 26, 0, Math.PI * 2, 0, Math.PI * 0.56);
    twRearDomeGeo.rotateX(-Math.PI / 2); // Dome apex points toward -Z (rear)
    const twRearDomeMat = new THREE.MeshPhysicalMaterial({
      color: 0x2a2d34,
      roughness: 0.42,
      metalness: 0.06,
      clearcoat: 0.20,
      clearcoatRoughness: 0.34,
      emissive: new THREE.Color(0x000000),
    });
    const twRearDome = new THREE.Mesh(twRearDomeGeo, twRearDomeMat);
    twRearDome.scale.set(1.06, 0.95, 1.40);
    twRearDome.position.set(0.014, 0.0, 0.004);
    twRearDome.castShadow = true;
    twLightGroup.add(twRearDome);

    // 2. Internal diffused LED light-guide strip tucked inside the outer smoked perimeter
    const twLedCoreGeo = new THREE.SphereGeometry(0.114, 40, 22, 0, Math.PI * 2, 0.02, Math.PI * 0.54);
    twLedCoreGeo.rotateX(-Math.PI / 2);
    this.thumbWheelLedMat = new THREE.MeshStandardMaterial({
      color: 0x1e2c26,
      emissive: new THREE.Color(0x28e88e),
      emissiveIntensity: 0.42,
      roughness: 0.30,
      metalness: 0.08,
    });
    const twLedCore = new THREE.Mesh(twLedCoreGeo, this.thumbWheelLedMat);
    twLedCore.scale.set(0.90, 1.03, 1.50);
    twLedCore.position.set(-0.004, 0.001, 0.003);
    twLightGroup.add(twLedCore);

    // 3. Outer translucent smoked frosted-polycarbonate horseshoe light-pipe rim
    const twLightPipeGeo = new THREE.SphereGeometry(0.122, 44, 24, 0, Math.PI * 2, 0.02, Math.PI * 0.54);
    twLightPipeGeo.rotateX(-Math.PI / 2);
    this.thumbWheelPipeMat = new THREE.MeshPhysicalMaterial({
      color: 0x747e8c,
      roughness: 0.18,
      metalness: 0.16,
      transparent: true,
      opacity: 0.66,
      clearcoat: 1.0,
      clearcoatRoughness: 0.12,
      emissive: new THREE.Color(0x28e88e),
      emissiveIntensity: 0.14,
    });
    const twLightPipe = new THREE.Mesh(twLightPipeGeo, this.thumbWheelPipeMat);
    twLightPipe.scale.set(0.96, 1.07, 1.58);
    twLightPipe.position.set(-0.002, 0.001, 0.004);
    twLightGroup.add(twLightPipe);

    // Crisp dark recessed seam ring separating the knurled metal wheel from the rear cap
    const twRearSeam = new THREE.Mesh(
      new THREE.TorusGeometry(0.122, 0.0048, 12, 48),
      new THREE.MeshStandardMaterial({ color: 0x0d1016, roughness: 0.65, metalness: 0.20 }),
    );
    twRearSeam.position.z = 0.003;
    twLightGroup.add(twRearSeam);

    // ─── PARTS 5, 6, 7: Three Sleek Rounded Matte-Charcoal Side Buttons (Image 4 & 5!) ──
    const makeSideBtn = (key, cid, len) => {
      const grp = new THREE.Group();
      this.mouseRoot.add(grp);
      this.tunableParts[key] = grp;

      const capMat = new THREE.MeshPhysicalMaterial({
        color: 0x2e3138,
        roughness: 0.50,
        metalness: 0.04,
        clearcoat: 0.10,
        clearcoatRoughness: 0.45,
        emissive: new THREE.Color(0x000000),
      });
      const cap = new THREE.Mesh(
        createHardSurfaceButton(0.062, 0.052, len, 0.022, 0.010),
        capMat,
      );
      cap.position.x = 0.016;
      cap.castShadow = true;
      grp.add(cap);
      this.sideBtnCaps.set(cid, cap);
      this._registerInteractable(cap, cid);
    };

    makeSideBtn('sideGestureBtn', CID.GESTURE, 0.195);
    makeSideBtn('sideForwardBtn', CID.FORWARD, 0.215);
    makeSideBtn('sideBackBtn',    CID.BACK,    0.215);

    // ─── Single Authentic Status LED Pinhole Behind Mode-Shift (Image 7!) ──
    const ledDot = new THREE.Mesh(
      new THREE.SphereGeometry(0.0085, 12, 12),
      new THREE.MeshStandardMaterial({
        color: 0x1e222a,
        emissive: new THREE.Color(0x45dbe0),
        emissiveIntensity: 0.42,
        roughness: 0.38,
        metalness: 0.15,
      }),
    );
    ledDot.position.set(0.030, 1.236, 0.045);
    this.mouseRoot.add(ledDot);
    this.ledDots.push(ledDot);
    // Note: Left Click (MX4_LMB), Right Click (MX4_RMB), and Haptic Sense Thumb Pad (MX4_ThumbPad)
    // are registered directly on their real high-res CAD meshes in _loadRealMXMaster4GLB()!
  }

  _loadRealMXMaster4GLB() {
    const loader = new GLTFLoader();
    const beadNormal = createBeadBlastedNormalMap();
    const lmbLogiRough = createLmbLogiRoughnessMap();
    this.frostedMats = [];
    this.innerChassisMeshes = [];

    loader.load(
      './models/mx_master_4.glb',
      (gltf) => {
        const model = gltf.scene;
        const scanMeshes = [];
        model.traverse((c) => {
          if (c.isMesh) scanMeshes.push(c);
        });

        const mc = this.alignConfig.materials;

        for (const child of scanMeshes) {
          child.castShadow = true;
          child.receiveShadow = true;
          const origMats = Array.isArray(child.material) ? child.material : [child.material];
          let isInnerChassis = false;

          const upgraded = origMats.map((om) => {
            const mname = om?.name || '';

            // 1. Recessed Haptic Sense Silicone Thumb Pad — Concentric Circular Pattern + 8-Dot Emblem!
            if (mname.includes('HapticThumbPad') || mname.includes('ThumbPad')) {
              const nStrength = Math.max(0.0, Math.min(3.5, (mc.thumbBumpDepth || 0.052) * 32.0));
              const mat = new THREE.MeshPhysicalMaterial({
                color: 0x565a64,
                map: this.thumbPadMaps.colorMap,
                roughness: 0.80,
                roughnessMap: this.thumbPadMaps.roughnessMap,
                metalness: 0.02,
                normalMap: this.thumbPadMaps.normalMap,
                normalScale: new THREE.Vector2(nStrength, nStrength),
                clearcoat: 0.03,
                clearcoatRoughness: 0.74,
                sheen: 0.16,
                sheenRoughness: 0.86,
                sheenColor: new THREE.Color(0x6c727e),
                transparent: false,
                opacity: 1.0,
                depthWrite: true,
                side: THREE.FrontSide,
              });
              this.thumbPadMat = mat;
              this.scanShellMats.push(mat);
              return mat;
            }

            // 2. Primary & Secondary Clickers — same charcoal-grey as shell,
            //    rendered as frosted/foggy glassy polycarbonate.
            if (mname.includes('FoggyGlassyClicker') || mname.includes('FrostedClickPlate')) {
              const isLeft = mname.endsWith('_L') || child.name === 'MX4_LMB';
              const mat = new THREE.MeshPhysicalMaterial({
                color: 0x35383f,
                roughness: isLeft ? 1.0 : 0.42,
                roughnessMap: isLeft ? lmbLogiRough : null,
                metalness: 0.01,
                clearcoat: 0.22,
                clearcoatRoughness: 0.56,
                transmission: 0.18,
                thickness: 0.20,
                ior: 1.49,
                attenuationColor: new THREE.Color(0x23262c),
                attenuationDistance: 0.28,
                sheen: 0.24,
                sheenRoughness: 0.62,
                sheenColor: new THREE.Color(0x9ca8b8),
                normalMap: beadNormal,
                normalScale: new THREE.Vector2(0.028, 0.028),
                transparent: false,
                opacity: 1.0,
                depthWrite: true,
                side: THREE.FrontSide,
              });
              this.frostedMats.push(mat);
              this.scanShellMats.push(mat);
              return mat;
            }

            // 3. Curved Right-Side Satin Silicone Grip
            if (mname.includes('RightSiliconeGrip') || mname.includes('SiliconeGrip')) {
              const mat = new THREE.MeshPhysicalMaterial({
                color: 0x292c33,
                roughness: 0.84,
                metalness: 0.01,
                clearcoat: 0.0,
                sheen: 0.20,
                sheenRoughness: 0.88,
                sheenColor: new THREE.Color(0x5c6270),
                normalMap: beadNormal,
                normalScale: new THREE.Vector2(0.06, 0.06),
                transparent: false,
                opacity: 1.0,
                depthWrite: true,
                side: THREE.FrontSide,
              });
              this.scanShellMats.push(mat);
              return mat;
            }

            // 4. Deep Watertight Opaque Matte-Black Internal Chassis (blocks 100% of internal light leaks!)
            if (mname.includes('DarkInnerChassis') || mname.includes('DarkRecess')) {
              isInnerChassis = true;
              const mat = new THREE.MeshStandardMaterial({
                color: 0x050609,
                roughness: 0.90,
                metalness: 0.04,
                transparent: false,
                opacity: 1.0,
                depthWrite: true,
                side: THREE.DoubleSide,
              });
              return mat;
            }

            // 5. Cleanly Recessed Front-Nose USB-C Metal Shield
            if (mname.includes('USBCMetal')) {
              return new THREE.MeshStandardMaterial({
                color: 0x8a929e,
                metalness: 0.88,
                roughness: 0.32,
              });
            }

            // 6. Main Body Shell — Authentic MATTE CHARCOAL-GREY Fine-Textured Plastic (Photos 3–7!)
            const mat = new THREE.MeshPhysicalMaterial({
              color: 0x35383f,
              roughness: mc.shellRoughness,
              metalness: 0.01,
              clearcoat: mc.shellClearcoat,
              clearcoatRoughness: 0.72,
              sheen: 0.14,
              sheenRoughness: 0.90,
              sheenColor: new THREE.Color(0x606672),
              normalMap: beadNormal,
              normalScale: new THREE.Vector2(0.12, 0.12),
              transparent: false,
              opacity: 1.0,
              depthWrite: true,
              side: THREE.FrontSide,
            });
            this.shellMat = mat;
            this.scanShellMats.push(mat);
            return mat;
          });

          child.material = Array.isArray(child.material) ? upgraded : upgraded[0];
          child.renderOrder = isInnerChassis ? 2 : 3;

          if (isInnerChassis) {
            this.innerChassisMeshes.push(child);
            continue;
          }

          // Register real multi-part CAD meshes directly for exact 1:1 raycasting, contour hover glow,
          // AND live physical click/squeeze mechanical actuation!
          const m0 = origMats[0]?.name || '';
          const cname = child.name || '';
          if (cname.includes('MX4_LMB') || m0.endsWith('Clicker_L')) {
            this._registerInteractable(child, CID.LEFT_CLICK, 0.0045);
            // Wrap LMB in a mechanical hinge pivot right at the real rear diagonal seam!
            const parentObj = child.parent || model;
            const pivot = new THREE.Group();
            pivot.name = 'MX4_LMB_HingePivot';
            pivot.position.set(0.32, 1.06, 0.46);
            parentObj.add(pivot);
            child.position.sub(pivot.position);
            pivot.add(child);
            this.lmbPivot = pivot;
          } else if (cname.includes('MX4_RMB') || m0.endsWith('Clicker_R')) {
            this._registerInteractable(child, CID.RIGHT_CLICK, 0.0045);
            const parentObj = child.parent || model;
            const pivot = new THREE.Group();
            pivot.name = 'MX4_RMB_HingePivot';
            pivot.position.set(-0.32, 1.06, 0.46);
            parentObj.add(pivot);
            child.position.sub(pivot.position);
            pivot.add(child);
            this.rmbPivot = pivot;
          } else if (cname.includes('MX4_ThumbPad') || m0.includes('HapticThumbPad')) {
            this._registerInteractable(child, CID.THUMB_PAD, 0.0055);
            this.thumbPadMesh = child;
            this.thumbPadBasePos = child.position.clone();
          } else {
            this.mouseShellMeshes.push(child);
          }

          // TWO-PASS SMOKED GLASS DEPTH PREPASS (eliminates all interior triangle bleed-through!)
          const prepassMat = new THREE.MeshBasicMaterial({
            colorWrite: false,
            depthWrite: true,
            side: THREE.FrontSide,
          });
          const prepass = new THREE.Mesh(child.geometry, prepassMat);
          prepass.renderOrder = 1;
          prepass.visible = false;
          child.add(prepass);
          this.depthPrepassMeshes.push(prepass);

          // Crisp Fresnel glass silhouette rim glow
          const rimMat = createFresnelGlassMaterial();
          const rim = new THREE.Mesh(child.geometry, rimMat);
          rim.scale.setScalar(1.0025);
          rim.renderOrder = 4;
          rim.visible = false;
          child.add(rim);
          this.glassRimMeshes.push({ mesh: rim, mat: rimMat });

          // Zero-cost GPU wireframe overlay for Lab X-Ray mode
          const wireMat = new THREE.MeshBasicMaterial({
            color: 0xd8a873,
            wireframe: true,
            transparent: true,
            opacity: 0.0,
            depthWrite: false,
          });
          const wire = new THREE.Mesh(child.geometry, wireMat);
          wire.scale.setScalar(1.003);
          wire.renderOrder = 4;
          wire.visible = false;
          child.add(wire);
          this.xrayWireMeshes.push({ mesh: wire, mat: wireMat });
        }

        this.mouseRoot.add(model);
      },
      undefined,
      (err) => {
        console.error('Failed to load MX Master 4 GLB:', err);
      },
    );
  }

  _buildScrollFlux() {
    this.fluxGroup = new THREE.Group();
    this.fluxGroup.visible = false;
    this.wheelContainer.add(this.fluxGroup);

    const arcConfigs = [
      { x: -0.122, r: 0.268, span: 1.48, thick: 0.0036, phase: 0.0, bright: 1.0 },
      { x: -0.138, r: 0.305, span: 1.28, thick: 0.0024, phase: 1.4, bright: 0.72 },
      { x: -0.152, r: 0.342, span: 1.05, thick: 0.0018, phase: 2.8, bright: 0.45 },
      { x:  0.122, r: 0.268, span: 1.48, thick: 0.0036, phase: 3.1, bright: 1.0 },
      { x:  0.138, r: 0.305, span: 1.28, thick: 0.0024, phase: 4.5, bright: 0.72 },
      { x:  0.152, r: 0.342, span: 1.05, thick: 0.0018, phase: 5.9, bright: 0.45 },
    ];

    for (const cfg of arcConfigs) {
      const pts = [];
      const steps = 48;
      const startA = -cfg.span * 0.5 + 0.14;
      for (let i = 0; i <= steps; i++) {
        const a = startA + (i / steps) * cfg.span;
        pts.push(new THREE.Vector3(cfg.x, Math.cos(a) * cfg.r, Math.sin(a) * cfg.r));
      }
      const curve = new THREE.CatmullRomCurve3(pts);
      const geo = new THREE.TubeGeometry(curve, 56, cfg.thick, 8, false);
      const mat = createFluxFilamentMaterial(cfg.phase, cfg.bright);
      const mesh = new THREE.Mesh(geo, mat);
      mesh.renderOrder = 5;
      this.fluxGroup.add(mesh);
      this.fluxMaterials.push(mat);
    }

    const cadPts = [];
    for (let i = -3; i <= 3; i++) {
      cadPts.push(new THREE.Vector3(-0.85, 0.76, 1.44 + i * 0.14), new THREE.Vector3(0.85, 0.76, 1.44 + i * 0.14));
      cadPts.push(new THREE.Vector3(i * 0.22, 0.76, 1.02), new THREE.Vector3(i * 0.22, 0.76, 1.88));
    }
    this.scrollCadMat = new THREE.LineBasicMaterial({
      color: 0x4ae0e8,
      transparent: true,
      opacity: 0.0,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    this.scrollCadGrid = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(cadPts), this.scrollCadMat);
    this.scrollCadGrid.renderOrder = 5;
    this.mouseRoot.add(this.scrollCadGrid);
  }

  _buildHapticCutaway() {
    this.lraGroup = new THREE.Group();
    this.lraGroup.visible = false;
    this.mouseRoot.add(this.lraGroup);
    this.tunableParts.lraCoil = this.lraGroup;

    const copperTex = createCopperCoilTexture();
    this.lraCoilMat = new THREE.MeshStandardMaterial({
      color: 0xffce92,
      map: copperTex,
      metalness: 0.90,
      roughness: 0.18,
      emissive: new THREE.Color(0xe6882c),
      emissiveIntensity: 0.58,
      depthTest: false,
    });

    const coilBody = new THREE.Mesh(
      new THREE.CylinderGeometry(0.148, 0.148, 0.52, 44),
      this.lraCoilMat,
    );
    coilBody.rotation.z = Math.PI / 2;
    coilBody.renderOrder = 2;
    this.lraGroup.add(coilBody);

    const wireMat = new THREE.MeshStandardMaterial({
      color: 0xffcf94,
      metalness: 0.96,
      roughness: 0.14,
      emissive: new THREE.Color(0xda7c24),
      emissiveIntensity: 0.48,
      depthTest: false,
    });
    for (let i = -11; i <= 11; i++) {
      const turn = new THREE.Mesh(new THREE.TorusGeometry(0.150, 0.0082, 8, 36), wireMat);
      turn.rotation.y = Math.PI / 2;
      turn.position.x = i * 0.021;
      turn.renderOrder = 2;
      this.lraGroup.add(turn);
    }

    const steelCapMat = new THREE.MeshStandardMaterial({
      color: 0xe2e8f2,
      metalness: 0.96,
      roughness: 0.14,
      depthTest: false,
    });
    for (const ex of [-0.285, 0.285]) {
      const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.164, 0.164, 0.056, 36), steelCapMat);
      cap.rotation.z = Math.PI / 2;
      cap.position.x = ex;
      cap.renderOrder = 2;
      this.lraGroup.add(cap);
    }

    this.acousticMat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      depthTest: false,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uTime:    { value: 0 },
        uOpacity: { value: 0.0 },
        uAmp:     { value: 0.72 },
        uBurst:   { value: 0.0 },
      },
      vertexShader: /* glsl */ `
        varying vec2 vUv;
        void main() {
          vUv = uv;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: /* glsl */ `
        varying vec2 vUv;
        uniform float uTime;
        uniform float uOpacity;
        uniform float uAmp;
        uniform float uBurst;

        void main() {
          vec2 p = vUv * 2.0 - 1.0;
          float r = length(p);
          if (r > 1.0) discard;

          float phase = r * 21.0 - uTime * 3.1;
          float wave = pow(max(0.0, 0.5 + 0.5 * sin(phase)), 5.2);
          float env = smoothstep(1.0, 0.24, r) * smoothstep(0.18, 0.30, r);
          float coreHalo = exp(-r * r * 6.5) * 0.44;

          vec3 copper = vec3(0.95, 0.64, 0.32);
          vec3 goldHi = vec3(1.0, 0.88, 0.64);
          float glow = (wave * env * 1.05 + coreHalo) * (0.52 + 0.48 * uAmp + uBurst * 0.85);
          vec3 col = mix(copper, goldHi, clamp(wave * 0.65 + uBurst * 0.5, 0.0, 1.0));
          gl_FragColor = vec4(col, clamp(glow * uOpacity, 0.0, 0.88));
        }
      `,
    });

    this.lraWavesGroup = new THREE.Group();
    this.lraWavesGroup.rotation.set(0.08, 0.80, 0.0);
    this.lraWavesGroup.visible = false;
    this.mouseRoot.add(this.lraWavesGroup);

    const waveDisc = new THREE.Mesh(new THREE.PlaneGeometry(2.10, 2.10), this.acousticMat);
    waveDisc.renderOrder = 5;
    this.lraWavesGroup.add(waveDisc);

    this.labInternals = new THREE.Group();
    this.labInternals.visible = false;
    this.mouseRoot.add(this.labInternals);

    const sensorLens = new THREE.Mesh(
      new THREE.CylinderGeometry(0.24, 0.30, 0.16, 28),
      new THREE.MeshBasicMaterial({ color: 0x45dbe0, wireframe: true, transparent: true, opacity: 0.85 }),
    );
    sensorLens.position.set(0.08, 0.24, 0.10);
    sensorLens.renderOrder = 2;
    this.labInternals.add(sensorLens);

    const pcbFrame = new THREE.Mesh(
      new THREE.BoxGeometry(1.18, 0.03, 2.05),
      new THREE.MeshBasicMaterial({ color: 0x3ad6de, wireframe: true, transparent: true, opacity: 0.22 }),
    );
    pcbFrame.position.set(0.06, 0.28, 0.05);
    pcbFrame.renderOrder = 2;
    this.labInternals.add(pcbFrame);
  }

  _buildHolographicRing() {
    this.ringHaloGroup = new THREE.Group();
    this.ringHaloGroup.position.set(0.06, 2.20, 0.02);
    this.ringHaloGroup.visible = false;
    this.scene.add(this.ringHaloGroup);

    // 1. Subtle holographic projection cone connecting the mouse up to the floating ring
    this.ringBeamMat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uPhase: { value: 0 },
        uOpacity: { value: 0 },
        uColorA: { value: new THREE.Color('#3ce0e8') },
        uColorB: { value: new THREE.Color('#e8a864') },
      },
      vertexShader: /* glsl */ `
        varying vec2 vUv;
        void main() {
          vUv = uv;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: /* glsl */ `
        varying vec2 vUv;
        uniform float uPhase;
        uniform float uOpacity;
        uniform vec3  uColorA;
        uniform vec3  uColorB;
        void main() {
          float vertical = smoothstep(0.0, 0.25, vUv.y) * smoothstep(1.0, 0.15, vUv.y);
          float scan = 0.72 + 0.28 * sin(vUv.y * 18.0 - uPhase * 2.2);
          vec3 col = mix(uColorA, uColorB, vUv.y * 0.65);
          gl_FragColor = vec4(col, vertical * scan * 0.14 * uOpacity);
        }
      `,
    });
    const projCone = new THREE.Mesh(
      new THREE.CylinderGeometry(1.36, 0.34, 1.48, 48, 1, true),
      this.ringBeamMat,
    );
    projCone.position.y = -0.76;
    projCone.renderOrder = 3;
    this.ringHaloGroup.add(projCone);

    // 2. Dark smoked glass backdrop ring disc for high contrast against the 3D scene
    this.ringGlassMat = new THREE.MeshBasicMaterial({
      color: 0x0b0f18,
      transparent: true,
      opacity: 0.0,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const glassDisc = new THREE.Mesh(new THREE.RingGeometry(0.42, 1.50, 72), this.ringGlassMat);
    glassDisc.rotation.x = -Math.PI / 2;
    glassDisc.position.y = -0.015;
    glassDisc.renderOrder = 4;
    this.ringHaloGroup.add(glassDisc);

    // 3. Precision Outer Bezel + Inner Deadzone Telemetry Rings
    this.ringOuterBezelMat = new THREE.MeshBasicMaterial({
      color: 0x3ce0e8, transparent: true, opacity: 0.0, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false,
    });
    this.ringInnerOrbitMat = new THREE.MeshBasicMaterial({
      color: 0xe8a864, transparent: true, opacity: 0.0, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false,
    });
    this.ringOrbitMat = this.ringOuterBezelMat;

    const outerBezel = new THREE.Mesh(new THREE.RingGeometry(1.48, 1.505, 96), this.ringOuterBezelMat);
    outerBezel.rotation.x = -Math.PI / 2;
    outerBezel.renderOrder = 5;
    this.ringHaloGroup.add(outerBezel);

    const midRim = new THREE.Mesh(new THREE.RingGeometry(1.38, 1.395, 96), this.ringOuterBezelMat);
    midRim.rotation.x = -Math.PI / 2;
    midRim.renderOrder = 5;
    this.ringHaloGroup.add(midRim);

    this.ringInnerOrbit = new THREE.Mesh(new THREE.RingGeometry(0.46, 0.486, 72), this.ringInnerOrbitMat);
    this.ringInnerOrbit.rotation.x = -Math.PI / 2;
    this.ringInnerOrbit.renderOrder = 6;
    this.ringHaloGroup.add(this.ringInnerOrbit);

    // 4. Rotating 48-Tick Precision Vernier Reticle
    this.ringVernierGroup = new THREE.Group();
    this.ringHaloGroup.add(this.ringVernierGroup);
    this.ringTickMat = new THREE.MeshBasicMaterial({
      color: 0x3ce0e8, transparent: true, opacity: 0.0, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false,
    });
    for (let k = 0; k < 48; k++) {
      const ang = (k / 48) * Math.PI * 2;
      const isMajor = (k % 6) === 0;
      const len = isMajor ? 0.082 : 0.042;
      const wid = isMajor ? 0.015 : 0.008;
      const tick = new THREE.Mesh(new THREE.PlaneGeometry(wid, len), this.ringTickMat);
      tick.rotation.x = -Math.PI / 2;
      tick.rotation.z = -ang;
      const rTick = 1.435 + len * 0.2;
      tick.position.set(Math.sin(ang) * rTick, 0.004, Math.cos(ang) * rTick);
      tick.renderOrder = 5;
      this.ringVernierGroup.add(tick);
    }

    // 5. Eight Cinema GLSL Holographic Action Slices (spring vertical lift + radial energy rim!)
    const sliceVert = /* glsl */ `
      varying vec3 vLocal;
      void main() {
        vLocal = position;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `;
    const sliceFrag = /* glsl */ `
      varying vec3  vLocal;
      uniform float uPhase;
      uniform float uOpacity;
      uniform float uLift;
      uniform float uConfirm;
      uniform float uStartAng;
      uniform float uEndAng;
      uniform vec3  uBaseCol;
      uniform vec3  uAccentCol;
      uniform vec3  uBrightCol;
      uniform vec3  uSecCol;

      void main() {
        float r = length(vLocal.xy);
        float rn = clamp((r - 0.56) / (1.34 - 0.56), 0.0, 1.0);
        float ang = atan(vLocal.y, vLocal.x);
        float midAng = 0.5 * (uStartAng + uEndAng);
        float halfSpan = 0.5 * (uEndAng - uStartAng);
        float dAng = abs(atan(sin(ang - midAng), cos(ang - midAng)));
        float edgeAng = smoothstep(halfSpan - 0.042, halfSpan - 0.004, dAng);

        // Soft holographic micro-bands (continuous phase -> zero strobing)
        float band = 0.88 + 0.12 * sin(rn * 16.0 - uPhase * 2.4);

        // Luminous outer rim bar & crisp inner edge bevel
        float outerBar = smoothstep(0.86, 0.99, rn);
        float innerRim = smoothstep(0.11, 0.0, rn);
        float borderGlow = max(max(outerBar, innerRim * 0.65), edgeAng * 0.72);

        vec3 idleGlass = mix(uBaseCol * 1.15, uSecCol * 0.38, rn * 0.35);
        vec3 activeGlass = mix(uAccentCol * 0.48, uAccentCol * 1.18, rn * 0.78) * band;
        vec3 col = mix(idleGlass, activeGlass, uLift);

        // Bright specular rim bar along active wedge outer edge + crisp idle sector glass
        col += mix(uSecCol * 0.65, uBrightCol * 1.38, uLift) * outerBar * (0.38 + 0.85 * uLift);
        col += mix(uSecCol * 0.42, uAccentCol * 0.88, uLift) * borderGlow * (0.36 + 0.56 * uLift);
        col += uBrightCol * uConfirm * 0.75;

        float baseAlpha = mix(0.44, 0.88, uLift) + borderGlow * (0.24 + 0.28 * uLift);
        gl_FragColor = vec4(col, clamp(baseAlpha * uOpacity, 0.0, 0.96));
      }
    `;

    this.ringSliceMeshes = [];
    for (let i = 0; i < 8; i++) {
      const segAngle = (Math.PI * 2) / 8;
      // Match 2D SVG & Wayland overlay slice ordering: Slice 0 = Top (-Z / 12 o'clock), clockwise!
      const start = Math.PI / 2 - i * segAngle - segAngle / 2 + 0.045;
      const span = segAngle - 0.09;
      const geo = new THREE.RingGeometry(0.56, 1.34, 28, 1, start, span);
      const mat = new THREE.ShaderMaterial({
        transparent: true,
        depthWrite: false,
        side: THREE.DoubleSide,
        uniforms: {
          uPhase:     { value: 0 },
          uOpacity:   { value: 0 },
          uLift:      { value: i === 0 ? 1.0 : 0.0 },
          uConfirm:   { value: 0.0 },
          uStartAng:  { value: start },
          uEndAng:    { value: start + span },
          uBaseCol:   { value: new THREE.Color('#18202e') },
          uAccentCol: { value: new THREE.Color('#e8a864') },
          uBrightCol: { value: new THREE.Color('#ffe0b2') },
          uSecCol:    { value: new THREE.Color('#3ce0e8') },
        },
        vertexShader: sliceVert,
        fragmentShader: sliceFrag,
      });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.rotation.x = -Math.PI / 2;
      mesh.renderOrder = 6;
      this.ringHaloGroup.add(mesh);
      this.ringSliceMeshes.push(mesh);
    }

    // 6. Center Energy Core + Live 3D Magnetic Compass Needle & Tether
    this.ringCoreMat = new THREE.MeshBasicMaterial({
      color: 0xffe0b2, transparent: true, opacity: 0.0, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false,
    });
    const coreDot = new THREE.Mesh(new THREE.CircleGeometry(0.11, 32), this.ringCoreMat);
    coreDot.rotation.x = -Math.PI / 2;
    coreDot.position.y = 0.014;
    coreDot.renderOrder = 7;
    this.ringHaloGroup.add(coreDot);

    this.ringCompassGroup = new THREE.Group();
    this.ringCompassGroup.position.y = 0.018;
    this.ringHaloGroup.add(this.ringCompassGroup);

    this.ringNeedleMat = new THREE.MeshBasicMaterial({
      color: 0xffe0b2, transparent: true, opacity: 0.0, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false,
    });
    // Laser tether ray from center core out to the deadzone bezel
    const tetherMesh = new THREE.Mesh(new THREE.PlaneGeometry(0.022, 0.42), this.ringNeedleMat);
    tetherMesh.rotation.x = -Math.PI / 2;
    tetherMesh.position.z = -0.24;
    tetherMesh.renderOrder = 7;
    this.ringCompassGroup.add(tetherMesh);

    // Crisp triangular chevron pointer aiming right into the selected slice!
    const ptrShape = new THREE.Shape();
    ptrShape.moveTo(0, 0.14);
    ptrShape.lineTo(-0.075, 0.0);
    ptrShape.lineTo(0.075, 0.0);
    ptrShape.closePath();
    const ptrGeo = new THREE.ShapeGeometry(ptrShape);
    ptrGeo.rotateX(-Math.PI / 2);
    const ptrMesh = new THREE.Mesh(ptrGeo, this.ringNeedleMat);
    ptrMesh.position.z = -0.45;
    ptrMesh.renderOrder = 8;
    this.ringCompassGroup.add(ptrMesh);

    // 7. Expanding Confirm Pulse Ring (fires when switching slice / theme / preset)
    this.ringPulseMat = new THREE.MeshBasicMaterial({
      color: 0xffe0b2, transparent: true, opacity: 0.0, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false,
    });
    this.ringPulseMesh = new THREE.Mesh(new THREE.RingGeometry(0.48, 0.53, 72), this.ringPulseMat);
    this.ringPulseMesh.rotation.x = -Math.PI / 2;
    this.ringPulseMesh.position.y = 0.024;
    this.ringPulseMesh.renderOrder = 8;
    this.ringHaloGroup.add(this.ringPulseMesh);
  }

  // ─── 3D Component Alignment & Material Configuration ─────────────────

  getAlignConfig() {
    return JSON.parse(JSON.stringify(this.alignConfig));
  }

  resetAlignConfig() {
    this.applyAlignConfig(JSON.parse(JSON.stringify(DEFAULT_ALIGN_CONFIG)));
    return this.getAlignConfig();
  }

  applyAlignConfig(cfg) {
    if (!cfg) return;
    if (cfg.parts) {
      for (const [key, def] of Object.entries(DEFAULT_ALIGN_CONFIG.parts)) {
        const incoming = cfg.parts[key] || {};
        const merged = { ...def, ...incoming };
        this.alignConfig.parts[key] = merged;
        this.setPartTransform(key, merged);
      }
    }
    if (cfg.materials) {
      const merged = { ...DEFAULT_ALIGN_CONFIG.materials, ...cfg.materials };
      this.alignConfig.materials = merged;
      this.setMaterialTuning(merged);
    }
  }

  setPartTransform(key, t) {
    const grp = this.tunableParts[key];
    if (!grp) return;
    const cur = this.alignConfig.parts[key] || {};
    const next = { ...cur, ...t };
    this.alignConfig.parts[key] = next;

    grp.position.set(Number(next.x), Number(next.y), Number(next.z));
    grp.rotation.set(Number(next.rx), Number(next.ry), Number(next.rz));
    grp.scale.setScalar(Math.max(0.2, Math.min(2.5, Number(next.scale || 1))));
    if (key !== 'lraCoil' && key !== 'opticalBeam') {
      grp.visible = next.visible !== false;
    }
    // Keep acoustic wave center synced with LRA coil position
    if (key === 'lraCoil' && this.lraWavesGroup) {
      this.lraWavesGroup.position.set(Number(next.x), Number(next.y), Number(next.z));
    }
    // Keep Buttons tab hotspot pins synced with moved CAD parts
    const pinMap = {
      magSpeedWheel: CID.MIDDLE_CLICK,
      modeShiftBtn: CID.SMART_SHIFT,
      thumbWheel: CID.THUMB_WHEEL,
      sideGestureBtn: CID.GESTURE,
      sideBackBtn: CID.BACK,
      sideForwardBtn: CID.FORWARD,
    };
    if (pinMap[key] && BUTTON_META[pinMap[key]]) {
      BUTTON_META[pinMap[key]].anchor = [Number(next.x), Number(next.y) + 0.08, Number(next.z)];
    }
  }

  setMaterialTuning(m) {
    const next = { ...this.alignConfig.materials, ...m };
    this.alignConfig.materials = next;

    if (this.shellMat) {
      this.shellMat.roughness = Number(next.shellRoughness);
      this.shellMat.clearcoat = Number(next.shellClearcoat);
    }
    if (this.frostedMats?.length) {
      for (const fm of this.frostedMats) {
        if (!fm.roughnessMap) {
          fm.roughness = Math.max(0.26, Number(next.shellRoughness) - 0.34);
        }
        fm.clearcoat = Math.min(0.48, Number(next.shellClearcoat) + 0.22);
      }
    }
    if (this.thumbPadMat) {
      const nStrength = Math.max(0.0, Math.min(3.5, Number(next.thumbBumpDepth) * 32.0));
      this.thumbPadMat.normalScale.set(nStrength, nStrength);
    }
    const rep = Math.max(8, Math.min(32, Math.round(Number(next.thumbBumpScale || 16))));
    if (rep !== this._lastThumbRingDensity) {
      this._lastThumbRingDensity = rep;
      const maps = createThumbPadRubberBumpMaps(rep);
      this.thumbPadMaps = maps;
      if (this.thumbPadMat) {
        this.thumbPadMat.map = maps.colorMap;
        this.thumbPadMat.normalMap = maps.normalMap;
        this.thumbPadMat.roughnessMap = maps.roughnessMap;
        this.thumbPadMat.needsUpdate = true;
      }
    }
    if (this.renderer) {
      this.renderer.toneMappingExposure = Number(next.exposure || 1.18);
    }
  }

  _bindEvents() {
    this.canvas.addEventListener('pointerdown', (e) => {
      this.dragging = true;
      this.dragMoved = false;
      this.lastPtr = { x: e.clientX, y: e.clientY };
      this.canvas.setPointerCapture(e.pointerId);
    });

    this.canvas.addEventListener('pointermove', (e) => {
      const rect = this.canvas.getBoundingClientRect();
      this.ptrNdc.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      this.ptrNdc.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      if (this.dragging) {
        const dx = e.clientX - this.lastPtr.x;
        const dy = e.clientY - this.lastPtr.y;
        if (Math.hypot(dx, dy) > 3) this.dragMoved = true;
        this.userOrbitOffset.az -= dx * 0.007;
        this.userOrbitOffset.pol = Math.max(-0.48, Math.min(0.42, this.userOrbitOffset.pol - dy * 0.005));
        this.lastPtr = { x: e.clientX, y: e.clientY };
        return;
      }
      this._pickHover(e.clientX, e.clientY);
    });

    this.canvas.addEventListener('pointerup', (e) => {
      if (this.dragging && !this.dragMoved && e.button === 0) {
        // Fresh raycast at exact release coordinates
        const rect = this.canvas.getBoundingClientRect();
        this.ptrNdc.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        this.ptrNdc.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
        this.raycaster.setFromCamera(this.ptrNdc, this.camera);

        const btnHits = this.raycaster.intersectObjects(this.interactables, false);
        if (btnHits.length > 0) {
          this.onClickButton(btnHits[0].object.userData.cid);
        } else {
          // Clicked background void or 3D cube floor (or off-control while zoomed in) -> return to full Device view!
          const shellHits = this.raycaster.intersectObjects(this.mouseShellMeshes, false);
          if (shellHits.length === 0 || this.selectedCid != null) {
            this.onClickBackground();
          }
        }
      }
      this.dragging = false;
      try { this.canvas.releasePointerCapture(e.pointerId); } catch {}
    });

    this.canvas.addEventListener('pointerleave', () => {
      this.ptrNdc.set(-9, -9);
      if (this.hoveredCid !== null) {
        this.hoveredCid = null;
        this.canvas.style.cursor = 'grab';
        this.onHoverButton(null, 0, 0);
      }
    });

    this.canvas.addEventListener('dblclick', () => {
      this.onClickBackground();
    });

    // Smooth camera zoom in/out with scroll wheel + smart auto-recenter when zooming out!
    this.canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      if (Math.abs(e.deltaY) < 0.01) return;
      const step = Math.sign(e.deltaY) * Math.min(1.15, Math.max(0.24, Math.abs(e.deltaY) * 0.0075));
      const nextDist = Math.max(1.85, Math.min(11.5, this.camTarget.dist + step));
      this.camTarget.dist = nextDist;

      // When scrolling OUT from a macro close-up, smoothly glide focus back onto the whole mouse!
      if (step > 0) {
        const home = CAMERA_PRESETS.device;
        const pullT = Math.max(0, Math.min(1, (nextDist - 2.4) / 4.2));
        const blend = 0.22 + pullT * 0.45;
        this.camTarget.tx += (home.tx - this.camTarget.tx) * blend;
        this.camTarget.ty += (home.ty - this.camTarget.ty) * blend;
        this.camTarget.tz += (home.tz - this.camTarget.tz) * blend;
        this.camTarget.fov += (home.fov - this.camTarget.fov) * blend;
        if (nextDist >= 5.8) {
          this.camTarget.pol += (home.pol - this.camTarget.pol) * 0.28;
        }
      }
    }, { passive: false });

    window.addEventListener('resize', () => this.resize());
  }

  _pickHover(clientX, clientY) {
    this.raycaster.setFromCamera(this.ptrNdc, this.camera);
    const hits = this.raycaster.intersectObjects(this.interactables, false);
    const cid = hits.length > 0 ? hits[0].object.userData.cid : null;
    if (cid !== this.hoveredCid) {
      this.hoveredCid = cid;
      this.canvas.style.cursor = cid != null ? 'pointer' : 'grab';
    }
    if (cid != null) this.onHoverButton(cid, clientX, clientY);
    else this.onHoverButton(null, 0, 0);
  }

  // ─── Public API ──────────────────────────────────────────────────────

  resize() {
    const parent = this.canvas.parentElement;
    if (!parent) return;
    const w = Math.max(320, parent.clientWidth);
    const h = Math.max(320, parent.clientHeight);
    this.renderer.setSize(w, h, false);
    if (this.camera) {
      this.camera.aspect = w / h;
      if (w >= 980) {
        const shiftX = Math.round(w * 0.205);
        this.camera.setViewOffset(w, h, shiftX, 0, w, h);
      } else {
        this.camera.clearViewOffset();
      }
      this.camera.updateProjectionMatrix();
    }
  }

  setTab(tab, { preserveFocus = false } = {}) {
    this.tab = tab;
    if (!preserveFocus) {
      this.selectedCid = null;
      const preset = CAMERA_PRESETS[tab] || CAMERA_PRESETS.device;
      this.camTarget = { ...preset };
      this.userOrbitOffset = { az: 0, pol: 0 };
    }

    this.modeTargets.cyanPool    = (tab === 'device' || tab === 'buttons') ? 1 : (tab === 'diagnostics' ? 0.65 : 0);
    this.modeTargets.scrollMacro = tab === 'scroll' ? 1 : 0;
    this.modeTargets.hapticGlass = tab === 'haptics' ? 1 : 0;
    this.modeTargets.ringHalo    = tab === 'ring' ? 1 : 0;
    this.modeTargets.xrayLab     = tab === 'diagnostics' ? 1 : 0;
  }

  /**
   * Smoothly zoom camera directly onto ANY clicked physical control on the MX Master 4!
   */
  focusControl(cid) {
    const numCid = Number(cid);
    const camPreset = CONTROL_CAMERAS[numCid];
    this.selectedCid = numCid;
    if (camPreset) {
      this.camTarget = { ...camPreset };
      this.userOrbitOffset = { az: 0, pol: 0 };
    }
    // Keep visual modes clean when focusing a specific button/wheel/pad
    this.modeTargets.scrollMacro = numCid === CID.MIDDLE_CLICK ? 1 : 0;
    this.modeTargets.hapticGlass = 0;
    this.modeTargets.ringHalo = 0;
    this.modeTargets.xrayLab = 0;
    this.modeTargets.cyanPool = 1;

    if (numCid === CID.THUMB_WHEEL) this.pulseThumbWheel(1);
    if (numCid === CID.MIDDLE_CLICK) this.pulseWheel(1);
    this.triggerFloorBurst(1.0, numCid === CID.THUMB_PAD ? 0.65 : 0.0);
  }

  clearFocusedControl() {
    this.selectedCid = null;
    const preset = CAMERA_PRESETS[this.tab] || CAMERA_PRESETS.device;
    this.camTarget = { ...preset };
    this.userOrbitOffset = { az: 0, pol: 0 };
    this.modeTargets.cyanPool    = (this.tab === 'device' || this.tab === 'buttons') ? 1 : (this.tab === 'diagnostics' ? 0.65 : 0);
    this.modeTargets.scrollMacro = this.tab === 'scroll' ? 1 : 0;
    this.modeTargets.hapticGlass = this.tab === 'haptics' ? 1 : 0;
    this.modeTargets.ringHalo    = this.tab === 'ring' ? 1 : 0;
    this.modeTargets.xrayLab     = this.tab === 'diagnostics' ? 1 : 0;
  }

  triggerFloorBurst(strength = 1.0, copperMix = -1.0) {
    // Smoothly swell an active wave instead of hard-resetting into a strobe on rapid clicks/scrolls!
    if (this.floorBurstAge < 0.28) {
      this.floorBurstStrength = Math.min(1.65, Math.max(this.floorBurstStrength, strength));
      if (copperMix >= 0) this.floorBurstColorMix = Math.max(this.floorBurstColorMix, copperMix);
      return;
    }
    this.floorBurstAge = 0.0;
    this.floorBurstStrength = Math.max(0.2, Math.min(1.65, strength));
    this.floorBurstColorMix = copperMix;
  }

  setAmbientPaused(paused) { this.ambientPaused = Boolean(paused); }

  resetCamera() {
    this.selectedCid = null;
    this.userOrbitOffset = { az: 0, pol: 0 };
    this.camTarget = { ...(CAMERA_PRESETS[this.tab] || CAMERA_PRESETS.device) };
  }

  setHardwareState({
    dpi, scrollMode, smartshiftThreshold, torque,
    scrollSpeed, scrollSmoothness, scrollAccel, hiresInvert,
    hapticEnabled, hapticLevel, activeFeelWave, forceNorm,
    ringEnabled, ringCancelRadius, connected,
    battery, charging, thumbwheelMode,
  }) {
    if (typeof dpi === 'number' && dpi >= 100) this.dpi = dpi;
    if (scrollMode) this.scrollMode = scrollMode;
    if (typeof smartshiftThreshold === 'number') this.smartshiftThreshold = smartshiftThreshold;
    if (typeof torque === 'number') this.torque = torque;
    if (typeof scrollSpeed === 'number') this.scrollSpeed = scrollSpeed;
    if (typeof scrollSmoothness === 'number') this.scrollSmoothness = scrollSmoothness;
    if (typeof scrollAccel === 'number') this.scrollAccel = scrollAccel;
    if (typeof hiresInvert === 'boolean') this.hiresInvert = hiresInvert;
    if (typeof hapticEnabled === 'boolean') this.hapticEnabled = hapticEnabled;
    if (typeof hapticLevel === 'number') this.hapticLevel = hapticLevel;
    if (typeof activeFeelWave === 'number') this.activeFeelWave = activeFeelWave;
    if (typeof forceNorm === 'number') this.forceNorm = Math.max(0, Math.min(1, forceNorm));
    if (typeof ringEnabled === 'boolean') this.ringEnabled = ringEnabled;
    if (typeof ringCancelRadius === 'number') this.ringCancelRadius = ringCancelRadius;
    if (typeof connected === 'boolean') this.connected = connected;
    if (typeof battery === 'number') this.batteryPct = battery;
    if (typeof charging === 'boolean') this.charging = charging;
    if (thumbwheelMode) this.thumbwheelMode = thumbwheelMode;
    if (typeof connected === 'boolean' && this.ledDots.length) {
      const hex = connected ? 0x45dbe0 : 0xf87171;
      this.ledDots[0].material.emissive.setHex(hex);
      this.ledDots[0].material.emissiveIntensity = connected ? 0.55 : 0.72;
    }
  }

  _rebuildPressedCids() {
    const prev = this.pressedCids;
    const next = new Set([
      ...this.divertedPressedCids,
      ...this.evdevPressedCids,
      ...this.domPressedCids,
    ]);
    this.pressedCids = next;
    for (const c of next) {
      if (!prev.has(c)) {
        const isPad = c === CID.THUMB_PAD;
        this.triggerFloorBurst(isPad ? 1.15 : 0.72, isPad ? 0.90 : 0.0);
        // Tactile micro-recoil impulse on physical click!
        this.vibeIntensity = Math.max(this.vibeIntensity, isPad ? 0.018 : 0.008);
        this.vibeTime = Math.max(this.vibeTime, isPad ? 0.28 : 0.10);
        this.vibeFreq = isPad ? 42 : 70;
        break;
      }
    }
  }

  setPressedCids(cids) {
    this.divertedPressedCids = new Set(cids);
    this._rebuildPressedCids();
  }

  setDomButtonPressed(cid, isDown) {
    if (isDown) this.domPressedCids.add(cid);
    else this.domPressedCids.delete(cid);
    this._rebuildPressedCids();
  }

  /**
   * Real-time 60 Hz hardware telemetry from physical MX Master 4 (evdev read-only stream):
   *   - dx, dy : live desk movement -> physical 3D hover-glide, bank, pitch, yaw & cube trail!
   *   - wy     : live MagSpeed scroll wheel spin -> 1:1 physical CNC wheel rotation!
   *   - wx     : live Horizontal Thumb Wheel spin -> 1:1 two-band aluminum barrel rotation!
   *   - btns   : live physical button press/release -> real hinged LMB/RMB clicks, wheel click, side pills!
   */
  applyLiveTelemetry({ dx = 0, dy = 0, wy = 0, wx = 0, btns = null } = {}) {
    if (dx || dy) {
      // Silky low-pass weighted velocity target (eliminates raw HID micro-jitter!)
      const dpiScale = 1000 / Math.max(400, this.dpi || 1000);
      const ix = Math.max(-0.32, Math.min(0.32, -dx * 0.0052 * dpiScale));
      const iz = Math.max(-0.32, Math.min(0.32, -dy * 0.0052 * dpiScale));
      this.liveMotion.targetVx = Math.max(-1.8, Math.min(1.8, this.liveMotion.targetVx + ix * 3.2));
      this.liveMotion.targetVz = Math.max(-1.8, Math.min(1.8, this.liveMotion.targetVz + iz * 3.2));
      this.liveMotion.speed = Math.min(1.2, this.liveMotion.speed + Math.hypot(ix, iz) * 1.4);
    }
    if (Math.abs(wy) > 1e-4) {
      this.lastRealScrollAge = 0.0;
      const impulse = -wy * (this.scrollMode === 'free' ? 10.5 : 7.8);
      this.wheelVelocity = Math.max(-32, Math.min(32, this.wheelVelocity + impulse));
      this.triggerFloorBurst(Math.min(0.82, 0.30 + Math.abs(wy) * 0.25), 0.0);
    }
    if (Math.abs(wx) > 1e-4) {
      this.thumbWheelVelocity = Math.max(-24, Math.min(24, this.thumbWheelVelocity + wx * 11.5));
      this.triggerFloorBurst(Math.min(0.75, 0.28 + Math.abs(wx) * 0.25), 0.0);
    }
    if (Array.isArray(btns)) {
      this.evdevPressedCids = new Set(btns.map(Number));
      this._rebuildPressedCids();
    }
  }

  /**
   * Real-time diverted Horizontal Thumb Wheel spin directly from D-Bus ThumbwheelEvent!
   */
  applyThumbwheelDelta(delta = 0, direction = 0) {
    const raw = Math.abs(delta) > 0 ? (delta / 18.0) : (direction * 0.9);
    if (Math.abs(raw) < 1e-4) return;
    this.thumbWheelVelocity = Math.max(-28, Math.min(28, this.thumbWheelVelocity + raw * 11.5));
    this.triggerFloorBurst(0.58, 0.0);
  }

  setRemappedCids(cids) { this.remappedCids = new Set(cids); }

  setSelectedRingSlice(idx) {
    if (idx !== this.selectedRingSlice) {
      this.selectedRingSlice = idx;
      this.ringConfirmPulse = 1.0;
      this.triggerFloorBurst(0.75, 0.42);
    }
  }

  /**
   * Synchronize the 3D WebGL Holographic Actions Ring & Cube Matrix echoes
   * with the active Ring Theme, Size Scale, Deadzone, and Animation toggle!
   */
  setRingAppearance({ theme, sizeScale, enabled, cancelRadius, animate, pulse = false } = {}) {
    if (theme) {
      this.ringTheme.id = theme.id || 'studio';
      if (theme.accent)        this.ringTheme.accent.set(theme.accent);
      if (theme.accent_bright) this.ringTheme.accentBright.set(theme.accent_bright);
      if (theme.secondary)     this.ringTheme.secondary.set(theme.secondary);
      if (theme.seg_idle)      this.ringTheme.segIdle.set(theme.seg_idle);
      if (theme.seg_hover)     this.ringTheme.segHover.set(theme.seg_hover);
    }
    if (typeof sizeScale === 'number' && sizeScale > 0.4) {
      this.ringSizeScale = Math.max(0.72, Math.min(1.28, sizeScale));
    }
    if (typeof enabled === 'boolean') this.ringEnabled = enabled;
    if (typeof cancelRadius === 'number') this.ringCancelRadius = cancelRadius;
    if (typeof animate === 'boolean') this.ringAnimate = animate;
    if (pulse) {
      this.ringConfirmPulse = 1.0;
      this.triggerFloorBurst(0.92, 0.65);
    }
  }

  triggerRingConfirmPulse() {
    this.ringConfirmPulse = 1.0;
    this.triggerFloorBurst(0.95, 0.72);
  }

  pulseWheel(dir = 1) {
    const sign = this.hiresInvert ? -dir : dir;
    const speedScale = Math.max(0.45, Math.min(2.6, this.scrollSpeed || 1.0));
    this.wheelVelocity = sign * (this.scrollMode === 'free' ? 20 : 9.5) * speedScale;
    this.triggerFloorBurst(0.75, 0.0);
  }
  pulseThumbWheel(dir = 1) {
    this.thumbWheelVelocity = dir * 13;
    this.triggerFloorBurst(0.68, 0.0);
  }

  triggerHapticVisual(patternId = 2) {
    this.activeFeelWave = patternId;
    const strength = this.hapticEnabled ? Math.max(0.25, (this.hapticLevel || 65) / 100) : 0.25;
    this.vibeIntensity = 0.024 * (0.45 + strength * 0.80);
    this.vibeTime = 0.46;
    this.vibeFreq = patternId >= 8 ? 64 : (patternId >= 5 ? 50 : 36);
    this.hapticBurstAge = 0.0;
    this.triggerFloorBurst(1.15 + strength * 0.65, 1.0);

    const lraPos = this.lraGroup.position;
    const count = (patternId === 5 || patternId === 6 || patternId === 10) ? 3 : 2;
    for (let i = 0; i < count; i++) {
      const ring = new THREE.Mesh(
        new THREE.RingGeometry(0.18, 0.23, 56),
        new THREE.MeshBasicMaterial({
          color: i % 2 === 0 ? 0xf6b974 : 0xffe4b2,
          transparent: true,
          opacity: 0.85,
          side: THREE.DoubleSide,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
          depthTest: false,
        }),
      );
      ring.position.copy(lraPos);
      ring.rotation.set(0.08, 0.80, 0.0);
      ring.renderOrder = 6;
      this.mouseRoot.add(ring);
      this.shockwaves.push({
        mesh: ring,
        age: -i * 0.085,
        maxAge: 0.78,
        speed: 3.2 + strength * 2.0,
      });
    }
  }

  // ─── Render Loop ─────────────────────────────────────────────────────

  _animate() {
    this._raf = requestAnimationFrame(this._animate);
    const dt = Math.min(0.05, this.clock.getDelta());
    const t = this.clock.elapsedTime;
    const animT = this.ambientPaused ? 1.2 : t;
    const lerpK = 1 - Math.exp(-6.2 * dt);

    for (const k of Object.keys(this.modeWeights)) {
      this.modeWeights[k] += (this.modeTargets[k] - this.modeWeights[k]) * lerpK;
    }

    const isZoomed = this.tab === 'scroll' || this.selectedCid != null;
    const ambientAz = (!this.ambientPaused && !this.dragging)
      ? Math.sin(t * 0.24) * (isZoomed ? 0.018 : 0.062)
      : 0;
    const goalAz = this.camTarget.az + this.userOrbitOffset.az + ambientAz;
    const goalPol = Math.max(0.32, Math.min(1.42, this.camTarget.pol + this.userOrbitOffset.pol));

    this.cam.az += (goalAz - this.cam.az) * lerpK;
    this.cam.pol += (goalPol - this.cam.pol) * lerpK;
    this.cam.dist += (this.camTarget.dist - this.cam.dist) * lerpK;
    this.cam.tx += (this.camTarget.tx - this.cam.tx) * lerpK;
    this.cam.ty += (this.camTarget.ty - this.cam.ty) * lerpK;
    this.cam.tz += (this.camTarget.tz - this.cam.tz) * lerpK;
    this.cam.fov += (this.camTarget.fov - this.cam.fov) * lerpK;

    if (Math.abs(this.camera.fov - this.cam.fov) > 0.02) {
      this.camera.fov = this.cam.fov;
      this.camera.updateProjectionMatrix();
    }

    const r = this.cam.dist;
    const focusY = this.cam.ty + this.hoverBaseY * 0.50;
    this.camera.position.set(
      this.cam.tx + r * Math.sin(this.cam.pol) * Math.sin(this.cam.az),
      focusY + r * Math.cos(this.cam.pol),
      this.cam.tz + r * Math.sin(this.cam.pol) * Math.cos(this.cam.az),
    );
    this.camera.lookAt(this.cam.tx, focusY, this.cam.tz);

    // ─── Real-Time Whole-Mouse Silky Weighted Magnetic Glide, Bank, Pitch & Yaw! ──
    const allowBodyGlide = !this.dragging && this.selectedCid == null && this.tab !== 'scroll';
    const lm = this.liveMotion;
    if (allowBodyGlide) {
      // Smoothly bleed raw target velocity into damped spring motion -> liquid-silk weighted feel!
      const velBlend = 1 - Math.exp(-10.0 * dt);
      lm.vx += (lm.targetVx - lm.vx) * velBlend;
      lm.vz += (lm.targetVz - lm.vz) * velBlend;
      lm.targetVx *= Math.exp(-9.5 * dt);
      lm.targetVz *= Math.exp(-9.5 * dt);

      const stiff = 16.0;
      const damp = 7.8;
      lm.vx += (-stiff * lm.px - damp * lm.vx) * dt;
      lm.vz += (-stiff * lm.pz - damp * lm.vz) * dt;
      lm.px = Math.max(-0.36, Math.min(0.36, lm.px + lm.vx * dt));
      lm.pz = Math.max(-0.36, Math.min(0.36, lm.pz + lm.vz * dt));
      lm.speed *= Math.exp(-3.4 * dt);

      const targetPitch = Math.max(-0.12, Math.min(0.12, -lm.vz * 0.075));
      const targetBank  = Math.max(-0.14, Math.min(0.14,  lm.vx * 0.085));
      const targetYaw   = Math.max(-0.10, Math.min(0.10,  lm.vx * 0.045));
      const tiltK = 1 - Math.exp(-8.5 * dt);
      lm.pitch += (targetPitch - lm.pitch) * tiltK;
      lm.bank  += (targetBank  - lm.bank)  * tiltK;
      lm.yaw   += (targetYaw   - lm.yaw)   * tiltK;
    } else {
      const calmK = 1 - Math.exp(-7.0 * dt);
      lm.px += (0 - lm.px) * calmK;
      lm.pz += (0 - lm.pz) * calmK;
      lm.vx *= Math.exp(-9.0 * dt);
      lm.vz *= Math.exp(-9.0 * dt);
      lm.targetVx *= Math.exp(-10.0 * dt);
      lm.targetVz *= Math.exp(-10.0 * dt);
      lm.pitch += (0 - lm.pitch) * calmK;
      lm.bank  += (0 - lm.bank)  * calmK;
      lm.yaw   += (0 - lm.yaw)   * calmK;
      lm.speed *= Math.exp(-5.0 * dt);
    }

    const floatY = (!this.ambientPaused && !isZoomed)
      ? Math.sin(t * 1.15) * 0.022
      : 0;
    let vx = 0, vy = 0, vz = 0;
    if (this.vibeTime > 0) {
      this.vibeTime = Math.max(0, this.vibeTime - dt);
      const decay = this.vibeTime / 0.46;
      const amp = this.vibeIntensity * decay;
      vx = Math.sin(t * this.vibeFreq * 2.1) * amp;
      vy = Math.cos(t * this.vibeFreq * 1.7) * amp * 0.4;
      vz = Math.sin(t * this.vibeFreq * 1.3) * amp * 0.6;
    }
    this.mouseRoot.position.set(lm.px + vx, this.hoverBaseY + floatY + vy, lm.pz + vz);
    this.mouseRoot.rotation.set(lm.pitch, lm.yaw, lm.bank);

    // ─── Real-Time Physical Mechanical Actuation of EVERY Button, Clicker, Wheel & Pad! ──
    const actuateCids = [
      CID.LEFT_CLICK, CID.RIGHT_CLICK, CID.MIDDLE_CLICK,
      CID.SMART_SHIFT, CID.GESTURE, CID.FORWARD, CID.BACK, CID.THUMB_PAD,
    ];
    for (const cid of actuateCids) {
      const goal = this.pressedCids.has(cid) ? 1.0 : 0.0;
      const prev = this.pressAnim.get(cid) || 0.0;
      // Snappy mechanical switch attack (28/s) & crisp tactile rebound (18/s)!
      const rate = goal > prev ? 28.0 : 18.0;
      const cur = prev + (goal - prev) * (1 - Math.exp(-rate * dt));
      this.pressAnim.set(cid, cur);
    }

    // 1. Left & Right Foggy Glassy Clickers hinge physically downward around the real rear diagonal seam!
    //    0.016 rad (~0.9 deg, ~0.018 nose drop) = authentic micro-switch travel staying 100% above inner chassis!
    if (this.lmbPivot) this.lmbPivot.rotation.x = 0.016 * (this.pressAnim.get(CID.LEFT_CLICK) || 0);
    if (this.rmbPivot) this.rmbPivot.rotation.x = 0.016 * (this.pressAnim.get(CID.RIGHT_CLICK) || 0);

    // 2. MagSpeed CNC Scroll Wheel physically depresses downward on Middle Click!
    if (this.wheelGroup) {
      this.wheelGroup.position.y = -0.024 * (this.pressAnim.get(CID.MIDDLE_CLICK) || 0);
    }

    // 3. Top Mode-Shift Button physically depresses downward into its oval recess!
    if (this.modeShiftCap) {
      this.modeShiftCap.position.y = 0.008 - 0.022 * (this.pressAnim.get(CID.SMART_SHIFT) || 0);
    }

    // 4. All 3 Side Pill Buttons (Gesture, Forward, Back) physically push INWARD into the mouse wall!
    for (const [cid, cap] of this.sideBtnCaps.entries()) {
      const p = this.pressAnim.get(cid) || 0;
      cap.position.x = 0.016 - 0.026 * p;
    }

    // 5. Pentagonal Haptic Sense Thumb Pad physically depresses inward along its normal (-PAD_N)!
    if (this.thumbPadMesh && this.thumbPadBasePos) {
      const p = this.pressAnim.get(CID.THUMB_PAD) || 0;
      this.thumbPadMesh.position.set(
        this.thumbPadBasePos.x - 0.014 * p,
        this.thumbPadBasePos.y - 0.015 * p,
        this.thumbPadBasePos.z - 0.003 * p,
      );
    }

    // ─── Real-Time + Adaptive MagSpeed CNC Wheel Physics ──
    this.lastRealScrollAge = Math.min(99, this.lastRealScrollAge + dt);
    const dirSign = this.hiresInvert ? -1 : 1;
    const speedMult = Math.max(0.35, Math.min(2.6, this.scrollSpeed || 1.0));
    const smoothNorm = Math.max(0, Math.min(1, (this.scrollSmoothness || 0) / 100));
    const thrNorm = Math.max(0, Math.min(1, ((this.smartshiftThreshold || 15) - 1) / 49));
    const tqNorm = Math.max(0.1, Math.min(1, (this.torque || 75) / 100));

    if (!this.ambientPaused) {
      if (this.lastRealScrollAge < 1.6) {
        // Real finger scroll in control — realistic free-spin flywheel coast vs ratchet friction!
        const decay = this.scrollMode === 'free' ? 0.55 : (this.scrollMode === 'smart' ? 2.4 : (5.2 - smoothNorm * 2.5));
        this.wheelVelocity *= Math.exp(-decay * dt);
      } else if (this.tab === 'scroll') {
        // Subtle demo preview on Scroll tab when hand is off the wheel
        if (this.scrollMode === 'free') {
          const goalV = dirSign * (4.2 * speedMult);
          this.wheelVelocity += (goalV - this.wheelVelocity) * dt * (0.95 - smoothNorm * 0.45);
        } else if (this.scrollMode === 'smart') {
          const burstCycle = Math.sin(t * (1.25 - thrNorm * 0.45));
          const freeBurst = Math.max(0, burstCycle - (thrNorm * 0.45 - 0.15)) * 3.4;
          const targetV = dirSign * (1.35 + freeBurst) * speedMult;
          this.wheelVelocity += (targetV - this.wheelVelocity) * dt * (2.4 - smoothNorm * 1.0);
        } else {
          this.wheelVelocity *= Math.exp(-(4.2 - smoothNorm * 2.2) * dt);
        }
      } else {
        // Resting on Device/other tabs: coast smoothly to stop so real scroll pops immediately!
        this.wheelVelocity *= Math.exp(-3.2 * dt);
      }
      this.wheelAngle += this.wheelVelocity * dt;
      if (this.scrollMode === 'ratchet') {
        const step = (Math.PI * 2) / 60;
        const snapped = Math.round(this.wheelAngle / step) * step;
        const snapK = Math.min(1, dt * (12 + tqNorm * 16));
        this.wheelGroup.rotation.x += (snapped - this.wheelGroup.rotation.x) * snapK;
      } else {
        this.wheelGroup.rotation.x = this.wheelAngle;
      }
    }

    // Horizontal Thumb Wheel rotation physics (rolls smoothly around its own Z axis!)
    if (Math.abs(this.thumbWheelVelocity) > 0.008) {
      this.thumbWheelAngle += this.thumbWheelVelocity * dt;
      this.thumbWheelSpinner.rotation.z = this.thumbWheelAngle;
      this.twLedPulse = Math.min(1.0, this.twLedPulse + Math.abs(this.thumbWheelVelocity) * dt * 0.45);
      this.thumbWheelVelocity *= Math.exp(-3.8 * dt);
    } else {
      this.twLedPulse *= Math.exp(-3.2 * dt);
    }

    // Authentic MX Master 4 rear thumb-wheel status light-pipe LED animation
    // (Firmware status: emerald green = healthy, breathing emerald = charging, red = low <=15%)
    if (this.thumbWheelLedMat && this.thumbWheelPipeMat) {
      const isLow = this.connected && this.batteryPct <= 15 && !this.charging;
      let hex = 0x26e88c; // Logitech emerald status green
      let baseGlow = 0.58;
      if (!this.connected) {
        hex = 0xf87171;
        baseGlow = 0.22 + 0.16 * (0.5 + 0.5 * Math.sin(t * 2.4));
      } else if (isLow) {
        hex = 0xff4757;
        baseGlow = 0.45 + 0.55 * (0.5 + 0.5 * Math.sin(t * 4.2));
      } else if (this.charging) {
        hex = 0x26e88c;
        baseGlow = 0.35 + 0.85 * (0.5 + 0.5 * Math.sin(t * 2.1));
      } else {
        // Healthy battery: subtle steady glow with slight shimmer on active thumb-wheel scroll
        baseGlow = 0.46 + 0.12 * Math.sin(t * 1.1) + this.twLedPulse * 0.72;
      }
      this.thumbWheelLedMat.emissive.setHex(hex);
      this.thumbWheelLedMat.emissiveIntensity = baseGlow * 0.88;
      this.thumbWheelPipeMat.emissive.setHex(hex);
      this.thumbWheelPipeMat.emissiveIntensity = baseGlow * 0.26;
    }

    // ─── 1. Live Shooting Pulse Beam + 625-Cube 3D Matrix (adapts to EVERY hardware setting!) ──
    this.hapticBurstAge = Math.min(99, this.hapticBurstAge + dt);
    this.floorBurstAge = Math.min(99, this.floorBurstAge + dt);

    const dpiNorm = Math.max(0, Math.min(1, (this.dpi - 200) / 7800));
    const hapStrength = this.hapticEnabled ? Math.max(0.22, this.hapticLevel / 100) : 0.14;
    const hg = this.modeWeights.hapticGlass;
    const sm = this.modeWeights.scrollMacro;
    const rh = this.modeWeights.ringHalo;
    const xl = this.modeWeights.xrayLab;

    // Waveform profile for Haptics cube waves (Deep Thump = wide heavy swells; Crisp Detent = tight fast pulses)
    const wId = this.activeFeelWave ?? 3;
    const isCrispWave = [0, 2, 6, 8, 11].includes(wId);
    const isDeepWave  = [1, 3, 12].includes(wId);

    // Blend color language & wave physics seamlessly across active modes & settings!
    let targetCopperMix = hg;
    if (this.floorBurstAge < 1.6 && this.floorBurstColorMix >= 0) {
      const burstBlend = Math.exp(-this.floorBurstAge * 2.2);
      targetCopperMix = Math.max(targetCopperMix, this.floorBurstColorMix * burstBlend);
    }
    if (rh > 0.05) targetCopperMix = Math.max(targetCopperMix, rh * 0.25);

    // Adaptive Pulse Rate, Wave Speed, Frequency, and 3D Cube Amplitude (all smoothly low-pass filtered!)
    const dpiPulseRate = 0.85 + dpiNorm * 1.15;
    const dpiWaveSpeed = 1.85 + dpiNorm * 1.95;
    const dpiWaveFreq  = 2.85 + dpiNorm * 1.45;
    const dpiWaveAmp   = 0.064 + dpiNorm * 0.042;

    const scrollWaveSpeed = this.scrollMode === 'free' ? (3.2 * speedMult)
      : (this.scrollMode === 'smart' ? (2.3 * speedMult) : (1.75 * speedMult));
    const scrollWaveFreq  = this.scrollMode === 'ratchet' ? (4.2 + tqNorm * 1.1) : 2.9;
    const scrollWaveAmp   = 0.058 + tqNorm * 0.048;

    const hapWaveSpeed = isCrispWave ? 3.5 : (isDeepWave ? 1.95 : 2.65);
    const hapWaveFreq  = isCrispWave ? 4.6 : (isDeepWave ? 2.45 : 3.4);
    const hapWaveAmp   = (isDeepWave ? 0.125 : 0.082) * (this.hapticEnabled ? (0.45 + hapStrength * 0.80) : 0.18);
    const hapPulseRate = isCrispWave ? 1.65 : (isDeepWave ? 0.95 : 1.25);

    const sa = this.smoothAnim;
    const paramK = 1 - Math.exp(-3.6 * dt);
    const targetMotionBoost = Math.min(0.65, this.liveMotion.speed * 0.45);
    sa.motionBoost += (targetMotionBoost - sa.motionBoost) * (1 - Math.exp(-4.5 * dt));

    const goalPulseRate = (dpiPulseRate * (1 - hg) + hapPulseRate * hg) + sa.motionBoost * 0.45;
    const goalWaveSpeed = (dpiWaveSpeed * (1 - hg - sm) + hapWaveSpeed * hg + scrollWaveSpeed * sm) + sa.motionBoost * 0.85;
    const goalWaveFreq  = dpiWaveFreq  * (1 - hg - sm) + hapWaveFreq  * hg + scrollWaveFreq  * sm;
    const goalWaveAmp   = (dpiWaveAmp   * (1 - hg - sm) + hapWaveAmp   * hg + scrollWaveAmp   * sm) * (1.0 + sa.motionBoost * 0.25);
    const goalEnergy    = Math.max(0.32, (1 - hg) * (0.85 + dpiNorm * 0.28 + sa.motionBoost * 0.18) + hg * (this.hapticEnabled ? (0.45 + hapStrength * 0.80) : 0.28));

    sa.pulseRate += (goalPulseRate - sa.pulseRate) * paramK;
    sa.waveSpeed += (goalWaveSpeed - sa.waveSpeed) * paramK;
    sa.waveFreq  += (goalWaveFreq  - sa.waveFreq)  * paramK;
    sa.waveAmp   += (goalWaveAmp   - sa.waveAmp)   * paramK;
    sa.energy    += (goalEnergy    - sa.energy)    * paramK;
    sa.colorMix  += (targetCopperMix - sa.colorMix) * (1 - Math.exp(-5.0 * dt));

    // Monotonically integrate continuous shader phases -> 100% ZERO STROBE on motion or DPI changes!
    if (!this.ambientPaused) {
      this.phases.beam  += dt * sa.pulseRate;
      this.phases.wave1 += dt * sa.waveSpeed;
      this.phases.wave2 += dt * sa.waveSpeed * 1.16;
    }

    // Silky damped Optical Pulse Beam + 3D Cube Matrix impact tracking!
    const baseBeamCfg = this.alignConfig.parts.opticalBeam || { x: 0.12, y: 0, z: 0.08 };
    const impactK = 1 - Math.exp(-8.5 * dt);
    sa.impactX += ((Number(baseBeamCfg.x) + lm.px) - sa.impactX) * impactK;
    sa.impactZ += ((Number(baseBeamCfg.z) + lm.pz) - sa.impactZ) * impactK;
    this.beamGroup.position.set(sa.impactX, Number(baseBeamCfg.y || 0), sa.impactZ);
    const beamPos = this.beamGroup.position;

    const activeBurstAge = Math.min(this.floorBurstAge, this.hapticBurstAge);
    const activeBurstStr = this.hapticBurstAge < this.floorBurstAge
      ? (1.05 + hapStrength * 0.65)
      : this.floorBurstStrength;

    // Update 625-Cube 3D Matrix uniforms (continuous integrated phases + Ring Theme color sync!)
    const ringColK = 1 - Math.exp(-5.5 * dt);
    this.ringThemeCurrent.accent.lerp(this.ringTheme.accent, ringColK);
    this.ringThemeCurrent.accentBright.lerp(this.ringTheme.accentBright, ringColK);
    this.ringThemeCurrent.secondary.lerp(this.ringTheme.secondary, ringColK);
    this.ringThemeCurrent.segIdle.lerp(this.ringTheme.segIdle, ringColK);

    const floorColA = new THREE.Color(0x28dce8).lerp(this.ringThemeCurrent.secondary, rh);
    const floorColB = new THREE.Color(0xf6aa5c).lerp(this.ringThemeCurrent.accent, rh);

    const cm = this.cubeMatrixMat.uniforms;
    cm.uColorA.value.copy(floorColA);
    cm.uColorB.value.copy(floorColB);
    cm.uBeamPhase.value = this.phases.beam;
    cm.uWavePhase.value = this.phases.wave1;
    cm.uWavePhase2.value = this.phases.wave2;
    cm.uImpact.value.set(beamPos.x, beamPos.z);
    cm.uWaveSpeed.value = sa.waveSpeed;
    cm.uWaveFreq.value = sa.waveFreq;
    cm.uWaveAmp.value = sa.waveAmp;
    cm.uBurstAge.value = activeBurstAge;
    cm.uBurstStrength.value = activeBurstStr;
    cm.uColorMix.value = Math.max(sa.colorMix, rh * 0.62);
    cm.uEnergyScale.value = sa.energy;
    const sliceRad = -Math.PI / 2 + this.selectedRingSlice * ((Math.PI * 2) / 8);
    cm.uSliceAngle.value = sliceRad;
    cm.uSliceWeight.value = rh * (this.ringEnabled ? 1.0 : 0.25);

    // Update Radiant Sub-Floor Gap Glow Bed uniforms (exact continuous phase sync!)
    const fm = this.floorMat.uniforms;
    fm.uColorA.value.copy(floorColA);
    fm.uColorB.value.copy(floorColB);
    fm.uBeamPhase.value = this.phases.beam;
    fm.uWavePhase.value = this.phases.wave1;
    fm.uWavePhase2.value = this.phases.wave2;
    fm.uImpact.value.set(beamPos.x, beamPos.z);
    fm.uWaveSpeed.value = sa.waveSpeed;
    fm.uWaveFreq.value = sa.waveFreq;
    fm.uBurstAge.value = activeBurstAge;
    fm.uBurstStrength.value = activeBurstStr;
    fm.uColorMix.value = Math.max(sa.colorMix, rh * 0.62);
    fm.uEnergyScale.value = sa.energy;

    // Update Live Shooting Pulse Beam + 3 Descending Focus Rings + Silky Breathing Under-Lighting
    const beamVisWeight = Math.max(this.modeWeights.cyanPool, hg * 0.85, rh * 0.65, xl * 0.55);
    const beamOn = this.alignConfig.parts.opticalBeam.visible !== false && beamVisWeight > 0.02;
    this.beamGroup.visible = beamOn;
    if (beamOn) {
      const coneWidth = 1.18 - dpiNorm * 0.42;
      this.beamOuterCone.scale.set(coneWidth, 1.0, coneWidth);

      this.beamMat.uniforms.uBeamPhase.value = this.phases.beam;
      this.beamMat.uniforms.uOpacity.value = beamVisWeight * sa.energy;
      this.beamMat.uniforms.uFocus.value = dpiNorm;
      this.beamMat.uniforms.uColorMix.value = sa.colorMix;

      this.beamCoreMat.uniforms.uBeamPhase.value = this.phases.beam;
      this.beamCoreMat.uniforms.uOpacity.value = beamVisWeight * (0.84 + dpiNorm * 0.30);
      this.beamCoreMat.uniforms.uColorMix.value = sa.colorMix;

      this.beamImpactMat.uniforms.uBeamPhase.value = this.phases.beam;
      this.beamImpactMat.uniforms.uOpacity.value = beamVisWeight * sa.energy;
      this.beamImpactMat.uniforms.uColorMix.value = sa.colorMix;

      // Animate 3 descending focus rings continuously from integrated phases.beam!
      const ringCol = new THREE.Color(0x4cf0ff).lerp(new THREE.Color(0xffbd6e), sa.colorMix);
      for (const br of this.beamRings) {
        const p = (this.phases.beam + br.phaseOffset) % 1.0;
        br.mesh.position.y = 0.64 * (1.0 - p) + 0.015;
        const sc = (0.75 + p * (2.5 - dpiNorm * 0.80));
        br.mesh.scale.setScalar(sc);
        br.mat.color.copy(ringCol);
        br.mat.opacity = Math.sin(p * Math.PI) * 0.64 * beamVisWeight * sa.energy;
      }

      // Silky cinema-grade breathing under-lighting (ZERO harsh sawtooth flash spikes!)
      const smoothBeat = Math.pow(0.5 + 0.5 * Math.sin(this.phases.beam * Math.PI * 2.0), 2.0);
      const burstGlow = Math.exp(-activeBurstAge * 2.8) * Math.min(1.0, activeBurstAge * 9.0) * activeBurstStr;
      const lightCol = floorColA.clone().lerp(floorColB, Math.max(sa.colorMix, rh * 0.62));
      this.sensorBounce.color.copy(lightCol);
      this.sensorBounce.position.set(beamPos.x, 0.28, beamPos.z);
      this.sensorBounce.intensity = (1.85 + smoothBeat * 0.72 + burstGlow * 0.95) * beamVisWeight * sa.energy;

      this.echoLight.color.copy(lightCol);
      this.echoLight.position.set(beamPos.x, 0.08, beamPos.z);
      this.echoLight.intensity = (1.28 + smoothBeat * 0.55 + burstGlow * 0.75) * beamVisWeight * sa.energy;
    } else {
      this.sensorBounce.intensity = 0;
      this.echoLight.intensity = 0;
    }

    // ─── 2. Scroll Macro Electromagnetic Flux Filaments (continuous integrated phase!) ──
    this.fluxGroup.visible = sm > 0.02;
    this.scrollCadMat.opacity = sm * (0.16 + tqNorm * 0.14);
    if (this.fluxGroup.visible) {
      const baseSpeed = this.scrollMode === 'free' ? 5.2 : (this.scrollMode === 'smart' ? 2.6 : 1.3);
      const fluxSpeed = dirSign * baseSpeed * speedMult;
      if (!this.ambientPaused) this.phases.flux += dt * fluxSpeed;
      for (const fluxM of this.fluxMaterials) {
        fluxM.uniforms.uFluxPhase.value = this.phases.flux;
        fluxM.uniforms.uOpacity.value = sm * (0.42 + tqNorm * 0.56);
      }
    }

    // ─── 3. Two-Pass Smoked Obsidian Glass Cutaway (Haptics) & CAD X-Ray (Lab) ──
    const glassBlend = Math.max(hg * 0.56, xl * 0.78);
    const isTranslucent = glassBlend > 0.03;

    for (const mat of this.scanShellMats) {
      const targetOp = 1.0 - glassBlend;
      if (mat.transparent !== isTranslucent) {
        mat.transparent = isTranslucent;
        mat.needsUpdate = true;
      }
      mat.opacity = targetOp;
      mat.depthWrite = !isTranslucent;
    }

    for (const pp of this.depthPrepassMeshes) pp.visible = hg > 0.03;
    for (const ic of (this.innerChassisMeshes || [])) ic.visible = !isTranslucent;
    for (const gr of this.glassRimMeshes) {
      gr.mesh.visible = hg > 0.02 || xl > 0.05;
      gr.mat.uniforms.uOpacity.value = Math.max(hg * 0.95, xl * 0.35);
    }
    for (const xw of this.xrayWireMeshes) {
      xw.mesh.visible = xl > 0.03;
      xw.mat.opacity = xl * 0.22;
    }

    const showLra = this.alignConfig.parts.lraCoil.visible !== false && (hg > 0.04 || xl > 0.14);
    this.lraGroup.visible = showLra;
    this.lraWavesGroup.visible = hg > 0.04;
    this.labInternals.visible = xl > 0.16;

    if (showLra) {
      const burstGlow = Math.exp(-this.hapticBurstAge * 4.0);
      const lraVis = Math.max(hg, xl * 0.85);
      const activeMult = this.hapticEnabled ? 1.0 : 0.25;
      this.lraCoilMat.emissiveIntensity = (0.35 + hapStrength * 0.78 + burstGlow * 1.25) * lraVis * activeMult;

      if (this.lraWavesGroup.visible && this.acousticMat) {
        const waveRate = isCrispWave ? 1.45 : (isDeepWave ? 0.80 : 1.08);
        if (!this.ambientPaused) this.phases.acoustic += dt * waveRate;
        this.acousticMat.uniforms.uTime.value = this.phases.acoustic;
        this.acousticMat.uniforms.uOpacity.value = hg * (this.hapticEnabled ? (0.68 + hapStrength * 0.32) : 0.16);
        this.acousticMat.uniforms.uAmp.value = hapStrength;
        this.acousticMat.uniforms.uBurst.value = burstGlow;
      }

      const worldLra = this.lraGroup.position.clone().applyMatrix4(this.mouseRoot.matrixWorld);
      this.lraLight.position.copy(worldLra);
      this.lraLight.intensity = (2.2 + hapStrength * 2.4 + burstGlow * 3.8) * hg * activeMult;
    } else {
      this.lraLight.intensity = 0;
    }

    // 3D Shockwave rings
    for (let i = this.shockwaves.length - 1; i >= 0; i--) {
      const sw = this.shockwaves[i];
      sw.age += dt;
      if (sw.age < 0) { sw.mesh.visible = false; continue; }
      sw.mesh.visible = true;
      const p = sw.age / sw.maxAge;
      if (p >= 1) {
        this.mouseRoot.remove(sw.mesh);
        sw.mesh.geometry.dispose();
        sw.mesh.material.dispose();
        this.shockwaves.splice(i, 1);
      } else {
        sw.mesh.scale.setScalar(1 + p * sw.speed);
        sw.mesh.material.opacity = (1 - p) * (1 - p) * 0.82;
      }
    }

    // ─── 4. Cinema-Grade 3D Holographic Actions Ring (Theme, Size, Deadzone, Spring Lift & Magnetic Compass!) ──
    this.ringHaloGroup.visible = rh > 0.02;
    if (this.ringHaloGroup.visible) {
      if (!this.ambientPaused && this.ringAnimate) {
        this.phases.ring += dt;
      }
      const ringActive = this.ringEnabled ? 1.0 : 0.28;
      const hoverFloat = (!this.ambientPaused && this.ringAnimate) ? Math.sin(this.phases.ring * 1.65) * 0.032 : 0.0;
      this.ringHaloGroup.position.y = 2.18 + hoverFloat;

      // Smoothly scale whole 3D holographic ring for Compact / Standard / Large!
      const scK = 1 - Math.exp(-8.5 * dt);
      this.ringSizeScaleSmooth += (this.ringSizeScale - this.ringSizeScaleSmooth) * scK;
      const openScale = 0.84 + 0.16 * rh;
      this.ringHaloGroup.scale.setScalar(this.ringSizeScaleSmooth * openScale);

      // Update projection cone, glass backdrop, outer bezel, ticks, & inner deadzone ring
      const rtc = this.ringThemeCurrent;
      if (this.ringBeamMat) {
        this.ringBeamMat.uniforms.uPhase.value = this.phases.ring;
        this.ringBeamMat.uniforms.uOpacity.value = rh * ringActive;
        this.ringBeamMat.uniforms.uColorA.value.copy(rtc.secondary);
        this.ringBeamMat.uniforms.uColorB.value.copy(rtc.accent);
      }
      if (this.ringGlassMat) {
        this.ringGlassMat.opacity = rh * 0.42 * ringActive;
      }
      if (this.ringOuterBezelMat) {
        this.ringOuterBezelMat.color.copy(rtc.secondary);
        this.ringOuterBezelMat.opacity = rh * 0.56 * ringActive;
      }
      if (this.ringInnerOrbitMat) {
        this.ringInnerOrbitMat.color.copy(rtc.accent);
        this.ringInnerOrbitMat.opacity = rh * 0.82 * ringActive;
      }
      if (this.ringInnerOrbit) {
        const dzNorm = Math.max(0.58, Math.min(1.42, (this.ringCancelRadius || 40) / 40));
        this.ringInnerOrbit.scale.setScalar(dzNorm);
      }
      if (this.ringVernierGroup && this.ringTickMat) {
        this.ringVernierGroup.rotation.y = this.phases.ring * 0.12;
        this.ringTickMat.color.copy(rtc.secondary);
        this.ringTickMat.opacity = rh * 0.52 * ringActive;
      }

      // Smooth confirm-pulse shockwave decay (fires on slice/theme/preset switch!)
      if (this.ringConfirmPulse > 0.001) {
        this.ringConfirmPulse = Math.max(0, this.ringConfirmPulse - dt * 2.4);
      }
      if (this.ringPulseMesh && this.ringPulseMat) {
        const p = 1.0 - this.ringConfirmPulse;
        const showPulse = this.ringConfirmPulse > 0.02 && this.ringAnimate;
        this.ringPulseMesh.visible = showPulse;
        if (showPulse) {
          this.ringPulseMesh.scale.setScalar(1.0 + p * 2.15);
          this.ringPulseMat.color.copy(rtc.accentBright);
          this.ringPulseMat.opacity = this.ringConfirmPulse * this.ringConfirmPulse * 0.85 * rh;
        }
      }

      // Smooth spring-interpolated 3D Magnetic Compass Needle aiming directly at selected slice!
      if (this.ringCompassGroup && this.ringCoreMat && this.ringNeedleMat) {
        const segAngle = (Math.PI * 2) / 8;
        const targetYaw = -this.selectedRingSlice * segAngle;
        let diff = targetYaw - this.ringCompassAngle;
        while (diff > Math.PI) diff -= Math.PI * 2;
        while (diff < -Math.PI) diff += Math.PI * 2;
        const compassK = this.ringAnimate ? (1 - Math.exp(-15.0 * dt)) : 1.0;
        this.ringCompassAngle += diff * compassK;
        this.ringCompassGroup.rotation.y = this.ringCompassAngle;
        this.ringCoreMat.color.copy(rtc.accentBright);
        this.ringCoreMat.opacity = rh * 0.88 * ringActive;
        this.ringNeedleMat.color.copy(rtc.accentBright);
        this.ringNeedleMat.opacity = rh * 0.92 * ringActive;
      }

      // Per-slice spring vertical lift + radial pop + GLSL luminous glow!
      const liftK = this.ringAnimate ? (1 - Math.exp(-14.0 * dt)) : 1.0;
      for (let i = 0; i < this.ringSliceMeshes.length; i++) {
        const m = this.ringSliceMeshes[i];
        const sel = i === this.selectedRingSlice;
        const goalLift = sel ? 1.0 : 0.0;
        this.ringSliceLifts[i] += (goalLift - this.ringSliceLifts[i]) * liftK;
        const lift = this.ringSliceLifts[i];

        m.position.y = lift * 0.11;
        const popScale = 1.0 + lift * 0.048;
        m.scale.set(popScale, popScale, 1.0);

        const u = m.material.uniforms;
        u.uPhase.value = this.phases.ring;
        u.uOpacity.value = rh * ringActive;
        u.uLift.value = lift;
        u.uConfirm.value = sel ? (this.ringConfirmPulse * 0.55) : 0.0;
        u.uBaseCol.value.copy(rtc.segIdle);
        u.uAccentCol.value.copy(rtc.accent);
        u.uBrightCol.value.copy(rtc.accentBright);
        u.uSecCol.value.copy(rtc.secondary);
      }
    }

    // ─── 5. Hard Pure White Viewpoint-Aligned Hover Outline & Selection Highlight! ──
    const hlLerp = 1 - Math.exp(-13.0 * dt);
    const viewW = this.canvas.clientWidth || 1360;
    const viewH = this.canvas.clientHeight || 820;

    for (const [cid, overlays] of this.controlHighlights.entries()) {
      const pressed  = this.pressedCids.has(cid);
      const selected = this.selectedCid === cid;
      const hover    = this.hoveredCid === cid;
      const remapped = this.remappedCids.has(cid) && this.tab === 'buttons';
      // On Haptics tab, subtly rim-glow the Thumb Pad proportional to force sensitivity!
      const padForceHint = (cid === CID.THUMB_PAD && hg > 0.2) ? (hg * (0.14 + (1.0 - this.forceNorm) * 0.22)) : 0.0;

      const targetIntensity = pressed ? 1.0
        : hover ? 1.0
        : selected ? 0.86
        : remapped ? 0.26
        : padForceHint;

      const prevLvl = this.controlHighlightLevels.get(cid) || 0.0;
      const nextLvl = prevLvl + (targetIntensity - prevLvl) * hlLerp;
      this.controlHighlightLevels.set(cid, nextLvl);

      // Hover = CRISP PURE STUDIO WHITE (#ffffff) with hard viewpoint silhouette outline!
      // Selected = crisp bright white-gold (#fff6e8), Pressed = warm gold-white (#ffe0a6)
      const targetHex = pressed ? 0xffe0a6
        : hover ? 0xffffff
        : selected ? 0xfff4e2
        : (remapped || padForceHint > 0) ? 0xe6a662
        : 0xffffff;

      const outlinePx = pressed ? 4.6 : (hover ? 4.2 : (selected ? 3.2 : 0.0));

      for (const ov of overlays) {
        ov.mesh.visible = nextLvl > 0.01;
        if (ov.mesh.visible) {
          ov.mat.uniforms.uTime.value = t;
          ov.mat.uniforms.uIntensity.value = nextLvl;
          ov.mat.uniforms.uColor.value.setHex(targetHex);
        }
        if (ov.outlineMesh) {
          const showOutline = nextLvl > 0.05 && outlinePx > 0.1;
          ov.outlineMesh.visible = showOutline;
          if (showOutline) {
            ov.outlineMat.uniforms.uIntensity.value = nextLvl;
            ov.outlineMat.uniforms.uColor.value.setHex(targetHex);
            ov.outlineMat.uniforms.uOutlinePx.value = outlinePx;
            ov.outlineMat.uniforms.uResolution.value.set(viewW, viewH);
          }
        }
        if (ov.edgeLine && ov.edgeMat) {
          const showEdge = nextLvl > 0.05 && (hover || selected || pressed);
          ov.edgeLine.visible = showEdge;
          if (showEdge) {
            ov.edgeMat.color.setHex(targetHex);
            ov.edgeMat.opacity = Math.min(1.0, nextLvl * (hover ? 1.0 : 0.85));
          }
        }
      }
    }

    // Clean subtle emissive highlight on small machined metallic/button parts (wheels/pills)
    for (const [cid, meshes] of this.buttonMeshes.entries()) {
      if (cid === CID.LEFT_CLICK || cid === CID.RIGHT_CLICK || cid === CID.THUMB_PAD) continue;
      const pressed  = this.pressedCids.has(cid);
      const selected = this.selectedCid === cid;
      const hover    = this.hoveredCid === cid;
      const remapped = this.remappedCids.has(cid) && this.tab === 'buttons';
      for (const m of meshes) {
        if (!m.material || !m.material.emissive) continue;
        if (pressed) {
          m.material.emissive.setHex(0xf6c47c);
          m.material.emissiveIntensity = 0.65;
        } else if (hover) {
          m.material.emissive.setHex(0xffffff);
          m.material.emissiveIntensity = 0.24;
        } else if (selected) {
          m.material.emissive.setHex(0xfff0d8);
          m.material.emissiveIntensity = 0.18;
        } else if (remapped) {
          m.material.emissive.setHex(0xd8a26a);
          m.material.emissiveIntensity = 0.14;
        } else {
          m.material.emissive.setHex(0x000000);
          m.material.emissiveIntensity = 0.0;
        }
      }
    }

    // ─── 6. Project 3D Hotspot Pins on Buttons tab ──
    if (this.tab === 'buttons') {
      const rect = this.canvas.getBoundingClientRect();
      const pins = [];
      for (const [cidStr, meta] of Object.entries(BUTTON_META)) {
        const v = new THREE.Vector3(...meta.anchor).applyMatrix4(this.mouseRoot.matrixWorld);
        v.project(this.camera);
        if (v.z < 1) {
          pins.push({
            cid: Number(cidStr),
            name: meta.name,
            x: (v.x * 0.5 + 0.5) * rect.width,
            y: (-v.y * 0.5 + 0.5) * rect.height,
          });
        }
      }
      this.onProjectPins(pins);
    }

    this.renderer.render(this.scene, this.camera);
  }
}
