/**
 * Deterministic Virtual QWebChannel Bridge for MX4 Studio Launch Video.
 *
 * Loaded before app.js so the REAL, unmodified MX4 Studio frontend mounts with
 * rich live hardware state, all 6 real Ring Themes, all 8 real Ring Presets,
 * 45 HID++ 2.0 features, and instant frame-synced telemetry hooks.
 */

(function initVirtualBridge() {
  // ── 1. Deterministic Virtual Clock (60.000 fps exact lock!) ──────────────
  let virtualMs = 0;
  let rafSeq = 0;
  let rafQueue = new Map();

  const origNow = performance.now.bind(performance);
  const nativeRaf = window.requestAnimationFrame.bind(window);
  const baseEpoch = Date.now();

  performance.now = () => virtualMs;
  Date.now = () => Math.floor(baseEpoch + virtualMs);

  // Force preserveDrawingBuffer: true so WebGL2 never clears between GPU render and CDP screenshot
  const origGetContext = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function patchedGetContext(type, attrs) {
    if (type === 'webgl2' || type === 'webgl' || type === 'experimental-webgl') {
      return origGetContext.call(this, type, { ...(attrs || {}), preserveDrawingBuffer: true });
    }
    return origGetContext.call(this, type, attrs);
  };

  // Disable Chromium's wall-clock ViewTransition crossfade during deterministic
  // frame-by-frame capture so every tab switch lands cleanly on the exact beat frame!
  try {
    Object.defineProperty(document, 'startViewTransition', {
      configurable: true,
      writable: true,
      value: undefined,
    });
  } catch {
    document.startViewTransition = undefined;
  }

  window.requestAnimationFrame = (cb) => {
    const id = ++rafSeq;
    rafQueue.set(id, cb);
    return id;
  };
  window.cancelAnimationFrame = (id) => {
    rafQueue.delete(id);
  };

  window.__MX4_CLOCK__ = {
    now: () => virtualMs,
    origNow,
    nativeRaf,
    reset() {
      virtualMs = 0;
    },
    advance(dtMs) {
      virtualMs += dtMs;
      const batch = Array.from(rafQueue.entries());
      rafQueue.clear();
      for (const [, cb] of batch) {
        try { cb(virtualMs); } catch (e) { console.error('[RAF]', e); }
      }
    },
    flushPending() {
      const batch = Array.from(rafQueue.entries());
      rafQueue.clear();
      for (const [, cb] of batch) {
        try { cb(virtualMs); } catch (e) { console.error('[RAF]', e); }
      }
    },
  };

  // ── 2. Live Mock MX Master 4 Hardware State ──────────────────────────────
  const RING_THEMES = [
    { id: 'studio',   name: 'Studio Copper',    tagline: 'Smoked obsidian · brushed copper · Darkfield cyan', accent: '#e8a864', accent_bright: '#ffe0b2', secondary: '#3ce0e8', bg_outer: '#0a0d14', bg_ring: '#121722', bg_core: '#0c1018', seg_idle: '#18202e', seg_hover: '#2e2318', border: '#334057', text: '#f5f7fc', text_sub: '#95a3ba', cancel: '#f06e6e' },
    { id: 'cyber',    name: 'Darkfield Cyber',  tagline: 'Deep midnight · electric cyan · cryo-white',        accent: '#2ae4f0', accent_bright: '#b0fbff', secondary: '#4c8dff', bg_outer: '#050a14', bg_ring: '#091324', bg_core: '#060d18', seg_idle: '#0e1e33', seg_hover: '#0c3448', border: '#1e4260', text: '#effbff', text_sub: '#7eaac4', cancel: '#ff6b84' },
    { id: 'obsidian', name: 'Monochrome Pro',   tagline: 'Stealth matte graphite · pure white · tungsten',    accent: '#f2f5fa', accent_bright: '#ffffff', secondary: '#9ca8ba', bg_outer: '#08090c', bg_ring: '#12141a', bg_core: '#0b0d11', seg_idle: '#1a1d24', seg_hover: '#303642', border: '#373e4c', text: '#ffffff', text_sub: '#949ca8', cancel: '#f87171' },
    { id: 'solar',    name: 'Amber Forge',      tagline: 'Warm basalt · molten gold-amber · ember glow',      accent: '#ff9d3b', accent_bright: '#ffe099', secondary: '#ff5d42', bg_outer: '#120b07', bg_ring: '#1d120c', bg_core: '#140c08', seg_idle: '#291a12', seg_hover: '#452512', border: '#543522', text: '#fff7ee', text_sub: '#bf9c80', cancel: '#ff5959' },
    { id: 'emerald',  name: 'Nordic Emerald',   tagline: 'Carbon slate · luminous mint · glacier teal',       accent: '#34e6a4', accent_bright: '#b2ffe0', secondary: '#28c7d9', bg_outer: '#06110e', bg_ring: '#0c1c17', bg_core: '#081410', seg_idle: '#132a22', seg_hover: '#104230', border: '#214c3d', text: '#effdf7', text_sub: '#80b8a4', cancel: '#f87171' },
    { id: 'violet',   name: 'Ultraviolet Pulse',tagline: 'Cosmos indigo · electric violet · neon magenta',    accent: '#b87dff', accent_bright: '#e7ccff', secondary: '#f464c2', bg_outer: '#0c0716', bg_ring: '#150e28', bg_core: '#0e091c', seg_idle: '#1f1538', seg_hover: '#392061', border: '#412d6b', text: '#f8f2ff', text_sub: '#a490c9', cancel: '#ff6685' },
  ];

  const RING_SIZES = [
    { id: 'compact',  label: 'Compact',  canvas: 416, outer_r: 148, inner_r: 50, scale_3d: 0.86 },
    { id: 'standard', label: 'Standard', canvas: 480, outer_r: 174, inner_r: 58, scale_3d: 1.00 },
    { id: 'large',    label: 'Large',    canvas: 552, outer_r: 202, inner_r: 66, scale_3d: 1.15 },
  ];

  const RING_PRESETS = [
    {
      id: 'default', name: 'Productivity', badge: 'CORE',
      tagline: 'Universal daily workflow · edit, clipboard, capture & tabs',
      slices: [
        { label: 'Undo', icon: 'edit-undo', action_type: 'keystroke', action_data: 'ctrl+z' },
        { label: 'Redo', icon: 'edit-redo', action_type: 'keystroke', action_data: 'ctrl+shift+z' },
        { label: 'Copy', icon: 'edit-copy', action_type: 'keystroke', action_data: 'ctrl+c' },
        { label: 'Paste', icon: 'edit-paste', action_type: 'keystroke', action_data: 'ctrl+v' },
        { label: 'Screenshot', icon: 'camera-photo', action_type: 'command', action_data: 'grim -g "$(slurp)" - | wl-copy' },
        { label: 'Save', icon: 'document-save', action_type: 'keystroke', action_data: 'ctrl+s' },
        { label: 'Find', icon: 'edit-find', action_type: 'keystroke', action_data: 'ctrl+f' },
        { label: 'Close Tab', icon: 'window-close', action_type: 'keystroke', action_data: 'ctrl+w' },
      ],
    },
    {
      id: 'hyprland', name: 'Hyprland WM', badge: 'WAYLAND',
      tagline: 'Workspaces, tiling float, fullscreen & Wayland capture',
      slices: [
        { label: 'Fullscreen', icon: 'view-fullscreen', action_type: 'command', action_data: 'hyprctl dispatch fullscreen 0' },
        { label: 'Next WS', icon: 'go-next', action_type: 'command', action_data: 'hyprctl dispatch workspace +1' },
        { label: 'Move Next', icon: 'go-jump', action_type: 'command', action_data: 'hyprctl dispatch movetoworkspace +1' },
        { label: 'Float', icon: 'window-new', action_type: 'command', action_data: 'hyprctl dispatch togglefloating' },
        { label: 'Close Win', icon: 'window-close', action_type: 'command', action_data: 'hyprctl dispatch killactive' },
        { label: 'Screenshot', icon: 'camera-photo', action_type: 'command', action_data: 'grim -g "$(slurp)" - | wl-copy' },
        { label: 'Move Prev', icon: 'go-jump', action_type: 'command', action_data: 'hyprctl dispatch movetoworkspace -1' },
        { label: 'Prev WS', icon: 'go-previous', action_type: 'command', action_data: 'hyprctl dispatch workspace -1' },
      ],
    },
    {
      id: 'browser', name: 'Web Browser', badge: 'WEB',
      tagline: 'Fast tab surfing, reopen closed, history & page search',
      slices: [
        { label: 'New Tab', icon: 'tab-new', action_type: 'keystroke', action_data: 'ctrl+t' },
        { label: 'Close Tab', icon: 'window-close', action_type: 'keystroke', action_data: 'ctrl+w' },
        { label: 'Reload', icon: 'view-refresh', action_type: 'keystroke', action_data: 'ctrl+r' },
        { label: 'Forward', icon: 'go-next', action_type: 'keystroke', action_data: 'alt+Right' },
        { label: 'Reopen', icon: 'edit-undo', action_type: 'keystroke', action_data: 'ctrl+shift+t' },
        { label: 'Find', icon: 'edit-find', action_type: 'keystroke', action_data: 'ctrl+f' },
        { label: 'Back', icon: 'go-previous', action_type: 'keystroke', action_data: 'alt+Left' },
        { label: 'Bookmark', icon: 'bookmark-new', action_type: 'keystroke', action_data: 'ctrl+d' },
      ],
    },
    {
      id: 'editor', name: 'Code / IDE', badge: 'DEV',
      tagline: 'Command palette, quick open, format, terminal & refactor',
      slices: [
        { label: 'Palette', icon: 'system-search', action_type: 'keystroke', action_data: 'ctrl+shift+p' },
        { label: 'Quick Open', icon: 'document-open', action_type: 'keystroke', action_data: 'ctrl+p' },
        { label: 'Find All', icon: 'edit-find', action_type: 'keystroke', action_data: 'ctrl+shift+f' },
        { label: 'Format', icon: 'format-justify-left', action_type: 'keystroke', action_data: 'ctrl+shift+i' },
        { label: 'Terminal', icon: 'utilities-terminal', action_type: 'keystroke', action_data: 'ctrl+grave' },
        { label: 'Comment', icon: 'format-indent-more', action_type: 'keystroke', action_data: 'ctrl+/' },
        { label: 'Undo', icon: 'edit-undo', action_type: 'keystroke', action_data: 'ctrl+z' },
        { label: 'Save', icon: 'document-save', action_type: 'keystroke', action_data: 'ctrl+s' },
      ],
    },
    {
      id: 'terminal', name: 'Terminal / Shell', badge: 'CLI',
      tagline: 'Split panes, clipboard, history search & screen clear',
      slices: [
        { label: 'New Tab', icon: 'tab-new', action_type: 'keystroke', action_data: 'ctrl+shift+t' },
        { label: 'Copy', icon: 'edit-copy', action_type: 'keystroke', action_data: 'ctrl+shift+c' },
        { label: 'Paste', icon: 'edit-paste', action_type: 'keystroke', action_data: 'ctrl+shift+v' },
        { label: 'Find', icon: 'edit-find', action_type: 'keystroke', action_data: 'ctrl+shift+f' },
        { label: 'Close Tab', icon: 'window-close', action_type: 'keystroke', action_data: 'ctrl+shift+w' },
        { label: 'Clear', icon: 'edit-clear', action_type: 'keystroke', action_data: 'ctrl+l' },
        { label: 'Zoom In', icon: 'zoom-in', action_type: 'keystroke', action_data: 'ctrl+plus' },
        { label: 'Zoom Out', icon: 'zoom-out', action_type: 'keystroke', action_data: 'ctrl+minus' },
      ],
    },
    {
      id: 'media', name: 'Media & Audio', badge: 'AUDIO',
      tagline: 'Native PipeWire volume, MPRIS playback & mic mute',
      slices: [
        { label: 'Play/Pause', icon: 'media-playback-start', action_type: 'command', action_data: 'playerctl play-pause' },
        { label: 'Vol +5%', icon: 'audio-volume-high', action_type: 'command', action_data: 'wpctl set-volume -l 1.5 @DEFAULT_AUDIO_SINK@ 5%+' },
        { label: 'Next', icon: 'media-skip-forward', action_type: 'command', action_data: 'playerctl next' },
        { label: 'Vol -5%', icon: 'audio-volume-low', action_type: 'command', action_data: 'wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-' },
        { label: 'Mute Audio', icon: 'audio-volume-muted', action_type: 'command', action_data: 'wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle' },
        { label: 'Mute Mic', icon: 'microphone-muted', action_type: 'command', action_data: 'wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle' },
        { label: 'Previous', icon: 'media-skip-backward', action_type: 'command', action_data: 'playerctl previous' },
        { label: 'Fullscreen', icon: 'view-fullscreen', action_type: 'keystroke', action_data: 'f' },
      ],
    },
    {
      id: 'creative', name: 'Creative & 3D', badge: '3D / ART',
      tagline: 'Blender, Figma, GIMP & Krita precision studio tools',
      slices: [
        { label: 'Save', icon: 'document-save', action_type: 'keystroke', action_data: 'ctrl+s' },
        { label: 'Redo', icon: 'edit-redo', action_type: 'keystroke', action_data: 'ctrl+shift+z' },
        { label: 'Duplicate', icon: 'edit-copy', action_type: 'keystroke', action_data: 'shift+d' },
        { label: 'Export', icon: 'document-export', action_type: 'keystroke', action_data: 'ctrl+shift+e' },
        { label: 'Screenshot', icon: 'camera-photo', action_type: 'command', action_data: 'grim -g "$(slurp)" - | wl-copy' },
        { label: 'Zoom Fit', icon: 'zoom-in', action_type: 'keystroke', action_data: 'Home' },
        { label: 'Hide/Show', icon: 'view-refresh', action_type: 'keystroke', action_data: 'h' },
        { label: 'Undo', icon: 'edit-undo', action_type: 'keystroke', action_data: 'ctrl+z' },
      ],
    },
    {
      id: 'hardware', name: 'MX4 Hardware Deck', badge: 'MX4',
      tagline: 'Cycle DPI, SmartShift toggle, Easy-Switch & audio',
      slices: [
        { label: 'Cycle DPI', icon: 'input-mouse', action_type: 'dpi_cycle', action_data: '' },
        { label: 'SmartShift', icon: 'view-refresh', action_type: 'smartshift_toggle', action_data: '' },
        { label: 'Next Host', icon: 'network-wireless', action_type: 'host_next', action_data: '' },
        { label: 'Vol +5%', icon: 'audio-volume-high', action_type: 'command', action_data: 'wpctl set-volume -l 1.5 @DEFAULT_AUDIO_SINK@ 5%+' },
        { label: 'Mute Audio', icon: 'audio-volume-muted', action_type: 'command', action_data: 'wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle' },
        { label: 'Vol -5%', icon: 'audio-volume-low', action_type: 'command', action_data: 'wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-' },
        { label: 'Screenshot', icon: 'camera-photo', action_type: 'command', action_data: 'grim -g "$(slurp)" - | wl-copy' },
        { label: 'Haptic Ping', icon: 'emblem-favorite', action_type: 'haptic', action_data: '2' },
      ],
    },
  ];

  const mock = {
    sysd: { running: true, version: 2 },
    agent: { running: true, version: 2, gesture_active: true, trigger_cid: 416, active_profile: 'hyprland' },
    environment: { compositor: 'Hyprland', wtype: true, xdotool: true, layer_shell: true },
    device: {
      connected: true,
      name: 'MX Master 4',
      friendly_name: 'MX Master 4',
      connection: 'bolt',
      firmware: '39.0.0015',
      battery: 92,
      charging: false,
      dpi: 1000,
      dpi_min: 200,
      dpi_max: 8000,
      dpi_step: 50,
      wheel_mode: 'smart',
      smartshift: true,
      smartshift_threshold: 18,
      ratchet_torque: 75,
      tunable_torque: true,
      hires_enabled: true,
      hires_invert: false,
      hires_diverted: true,
      scroll_speed: 1.0,
      scroll_smoothness: 35,
      scroll_accel: 20,
      thumbwheel_diverted: true,
      thumbwheel_invert: false,
      haptic_enabled: true,
      haptic_level: 72,
      force_supported: true,
      force_min: 4156,
      force_max: 6909,
      force_default: 5195,
      force_value: 5195,
      current_host: 0,
      num_hosts: 3,
    },
    hosts: [
      { index: 0, name: 'Workstation', bus_label: 'BOLT', paired: true, current: true, can_rename: true },
      { index: 1, name: 'Studio Book', bus_label: 'BLE',  paired: true, current: false, can_rename: true },
      { index: 2, name: 'Dev Lab',     bus_label: 'BLE',  paired: true, current: false, can_rename: true },
    ],
    buttons: [
      { cid: 80,  name: 'Left Click',   divertable: false, remappable: false },
      { cid: 81,  name: 'Right Click',  divertable: false, remappable: false },
      { cid: 82,  name: 'Middle Click', divertable: true,  remappable: true  },
      { cid: 83,  name: 'Back',         divertable: true,  remappable: true  },
      { cid: 86,  name: 'Forward',      divertable: true,  remappable: true  },
      { cid: 195, name: 'Gesture',      divertable: true,  remappable: true  },
      { cid: 196, name: 'Mode Shift',   divertable: true,  remappable: true  },
      { cid: 416, name: 'Thumb Pad',    divertable: true,  remappable: false },
    ],
    config: {
      pointer: { dpi_presets: [800, 1200, 2400, 4000, 8000] },
      scroll: { scroll_speed: 1.0, scroll_smoothness: 35, scroll_accel: 20 },
      haptics: {
        enabled: true,
        ring_boundary_pattern: 1,
        ring_confirm_pattern: 3,
        ring_cancel_pattern: 0,
        notification_enabled: true,
        notification_pattern: 5,
      },
      thumbwheel: {
        diverted: true, invert: false, preset: 'volume', step: 35, haptic_tick: true,
        positive_type: 'command', positive_data: 'wpctl set-volume -l 1.5 @DEFAULT_AUDIO_SINK@ 5%+',
        negative_type: 'command', negative_data: 'wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-',
      },
      daemon: {
        autostart_gesture: true,
        trigger_cid: 416,
        cancel_radius: 40,
        ring_theme: 'studio',
        ring_size: 'standard',
        ring_show_hints: true,
        ring_animate: true,
      },
      button_bindings: [
        { cid: 195, action_type: 'dpi_cycle', action_data: '' },
      ],
      ring_profiles: {
        default: {
          app_id: 'default',
          app_name: 'Default',
          slices: JSON.parse(JSON.stringify(RING_PRESETS[0].slices)),
          button_overrides: [],
        },
        hyprland: {
          app_id: 'hyprland',
          app_name: 'Hyprland',
          slices: JSON.parse(JSON.stringify(RING_PRESETS[1].slices)),
          button_overrides: [],
        },
      },
    },
    ring_themes: RING_THEMES,
    ring_sizes: RING_SIZES,
    ring_presets: RING_PRESETS,
    thumbwheel_presets: {
      volume: { label: 'Volume (PipeWire)', positive_type: 'command', positive_data: 'wpctl set-volume +5%', negative_type: 'command', negative_data: 'wpctl set-volume -5%' },
      tabs:   { label: 'Browser Tabs',      positive_type: 'keystroke', positive_data: 'ctrl+Tab', negative_type: 'keystroke', negative_data: 'ctrl+shift+Tab' },
      zoom:   { label: 'Canvas Zoom',       positive_type: 'keystroke', positive_data: 'ctrl+plus', negative_type: 'keystroke', negative_data: 'ctrl+minus' },
    },
  };

  const PROBED_FEATURES = [
    { index: 1,  feature_hex: '0x0000', name: 'IRoot',                 description: 'HID++ 2.0 root protocol index',    response_hex: '04 05 00 00', locked: false },
    { index: 2,  feature_hex: '0x0001', name: 'IFeatureSet',           description: '45 hardware feature descriptors',  response_hex: '2D 00 00 00', locked: false },
    { index: 3,  feature_hex: '0x0007', name: 'DeviceFriendlyName',    description: 'MX Master 4 stored name',          response_hex: '4D 58 20 34', locked: false },
    { index: 4,  feature_hex: '0x1004', name: 'UnifiedBattery',        description: '92% live charge telemetry',        response_hex: '5C 04 00 00', locked: false },
    { index: 5,  feature_hex: '0x1814', name: 'ChangeHost',            description: 'Easy-Switch 3-slot wireless bus',  response_hex: '03 00 01 00', locked: false },
    { index: 6,  feature_hex: '0x1815', name: 'HostsInfo',             description: 'Bolt / BLE host descriptors',      response_hex: '03 01 00 00', locked: false },
    { index: 7,  feature_hex: '0x19B0', name: 'HapticMotorLRA',        description: '15 hardware LRA waveforms',        response_hex: '01 48 0F 00', locked: false },
    { index: 8,  feature_hex: '0x19C0', name: 'ForceSensingThumbPad',  description: 'Actuation force 4156–6909',        response_hex: '14 4B 10 3C', locked: false },
    { index: 9,  feature_hex: '0x1B04', name: 'SpecialKeysMSEButtons', description: 'Divertable & remappable CIDs',     response_hex: '08 01 A0 00', locked: false },
    { index: 10, feature_hex: '0x2111', name: 'SmartShiftEnhanced',    description: 'MagSpeed ratchet torque 1–100%',   response_hex: '02 12 4B 00', locked: false },
    { index: 11, feature_hex: '0x2121', name: 'HiResWheel',            description: '144 Hz high-resolution wheel',     response_hex: '08 02 01 00', locked: false },
    { index: 12, feature_hex: '0x2150', name: 'ThumbWheel',            description: 'CNC side wheel diversion',         response_hex: '01 01 00 00', locked: false },
    { index: 13, feature_hex: '0x2201', name: 'AdjustableDPI',         description: 'Darkfield 200–8000 DPI sensor',    response_hex: '03 E8 1F 40', locked: false },
  ];

  // Signal dispatcher
  const respListeners = [];
  const liveListeners = [];

  window.__MX4_MOCK_STATE__ = mock;
  window.__MX4_MOCK_EMIT__ = (eventName, payload) => {
    const str = JSON.stringify(payload);
    for (const fn of liveListeners) {
      try { fn(eventName, str); } catch {}
    }
  };

  function dispatchRpc(method, a) {
    if (method === 'getSnapshot') return JSON.parse(JSON.stringify(mock));
    if (method === 'setDpi') { mock.device.dpi = Number(a.dpi); return { ok: true, dpi: mock.device.dpi }; }
    if (method === 'setScrollMode') {
      mock.device.wheel_mode = a.mode;
      mock.device.smartshift = a.mode === 'smart';
      mock.device.smartshift_threshold = Number(a.threshold ?? 18);
      mock.device.ratchet_torque = Number(a.torque ?? 75);
      return { ok: true };
    }
    if (method === 'setScrollTuning') {
      mock.device.scroll_speed = Number(a.speed ?? 1.0);
      mock.device.scroll_smoothness = Number(a.smoothness ?? 0);
      mock.device.scroll_accel = Number(a.accel ?? 0);
      mock.config.scroll = {
        scroll_speed: mock.device.scroll_speed,
        scroll_smoothness: mock.device.scroll_smoothness,
        scroll_accel: mock.device.scroll_accel,
      };
      return { ok: true };
    }
    if (method === 'setHaptic') {
      mock.device.haptic_enabled = Boolean(a.enabled);
      mock.device.haptic_level = Number(a.level ?? 72);
      return { ok: true };
    }
    if (method === 'triggerHaptic') return { ok: true, auto_enabled: false };
    if (method === 'saveHapticConfig') { Object.assign(mock.config.haptics, a); return { ok: true }; }
    if (method === 'saveRingSettings') { Object.assign(mock.config.daemon, a); return { ok: true }; }
    if (method === 'applyRingPreset') {
      const p = RING_PRESETS.find((x) => x.id === a.preset_id) || RING_PRESETS[0];
      const prof = mock.config.ring_profiles[a.profile_id || 'default'];
      if (prof) prof.slices = JSON.parse(JSON.stringify(p.slices));
      return { ok: true };
    }
    if (method === 'probeFeatures') return { features: PROBED_FEATURES };
    return { ok: true };
  }

  // Expose QWebChannel shim identical to QtWebEngine
  window.qt = { webChannelTransport: {} };
  window.QWebChannel = function MockQWebChannel(_transport, cb) {
    const channel = {
      objects: {
        mx4Bridge: {
          responseReady: { connect: (fn) => respListeners.push(fn) },
          liveEvent:     { connect: (fn) => liveListeners.push(fn) },
          invoke(reqId, method, argsJson) {
            let args = {};
            try { args = JSON.parse(argsJson || '{}'); } catch {}
            const data = dispatchRpc(method, args);
            const payload = JSON.stringify({ ok: true, data });
            for (const fn of respListeners) fn(reqId, payload);
          },
        },
      },
    };
    Promise.resolve().then(() => cb(channel));
  };
})();
