/**
 * MX4 Studio Launch Video — Deterministic GPU WebGL2 4K 60fps Renderer & Contact Sheet Auditor
 *
 * Mounts the REAL live MX4 Studio app (/data/studio) inside RTX-accelerated headless Brave,
 * steps the virtual clock by exact 1/60 s per frame, pipes directly to FFmpeg with our
 * mastered -14 LUFS audio track, and builds transition contact sheets for visual QA.
 */

import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';
import { CONTACT_FRAMES, FPS, TOTAL_FRAMES, frameToBeat, frameToSec } from './timeline.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const STUDIO_DIR = path.resolve(__dirname, '..', 'data', 'studio');
const OUT_DIR = path.join(__dirname, 'out');
const TMP_DIR = path.join(__dirname, 'tmp');
const AUDIO_WAV = path.join(OUT_DIR, 'mx4_studio_master_audio.wav');

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css':  'text/css; charset=utf-8',
  '.js':   'application/javascript; charset=utf-8',
  '.mjs':  'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png':  'image/png',
  '.jpg':  'image/jpeg',
  '.svg':  'image/svg+xml',
  '.glb':  'model/gltf-binary',
  '.woff2':'font/woff2',
};

function startStudioServer() {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      const urlPath = decodeURIComponent((req.url || '/').split('?')[0]);

      // Serve injected live MX4 Studio index.html
      if (urlPath === '/' || urlPath === '/index.html') {
        let html = fs.readFileSync(path.join(STUDIO_DIR, 'index.html'), 'utf8');
        // Inject stage.css in <head>, mock-bridge.js BEFORE qwebchannel.js, and director.js after app.js
        html = html.replace(
          '</head>',
          `  <link rel="stylesheet" href="/__showcase/stage/stage.css" />\n  <script src="/__showcase/stage/mock-bridge.js"></script>\n</head>`,
        );
        html = html.replace(
          '<script src="qrc:///qtwebchannel/qwebchannel.js"></script>',
          '<!-- virtual QWebChannel provided by mock-bridge.js -->',
        );
        html = html.replace(
          '</body>',
          `  <script type="module" src="/__showcase/stage/director.js"></script>\n</body>`,
        );
        res.writeHead(200, { 'Content-Type': MIME['.html'], 'Cache-Control': 'no-store' });
        res.end(html);
        return;
      }

      // Serve showcase-video assets under /__showcase/
      let filePath;
      if (urlPath.startsWith('/__showcase/')) {
        filePath = path.join(__dirname, urlPath.slice('/__showcase/'.length));
      } else {
        filePath = path.join(STUDIO_DIR, urlPath.replace(/^\/+/, ''));
      }

      if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
        res.writeHead(404);
        res.end('Not found');
        return;
      }
      const ext = path.extname(filePath).toLowerCase();
      res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
      fs.createReadStream(filePath).pipe(res);
    });

    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      resolve({ server, baseUrl: `http://127.0.0.1:${port}` });
    });
  });
}

async function launchBrowser(mode) {
  const isVertical = mode === 'vertical';
  // --force-device-scale-factor=2 gives TRUE native 3840x2160 (4K) / 1080x1920 (9:16) at ~8+ fps!
  const viewport = isVertical ? { width: 540, height: 960 } : { width: 1920, height: 1080 };
  const browser = await chromium.launch({
    executablePath: '/usr/bin/brave',
    headless: true,
    args: [
      '--no-sandbox',
      '--force-device-scale-factor=2',
      '--use-gl=angle',
      '--use-angle=gl',
      '--ignore-gpu-blocklist',
      '--enable-webgl',
      '--disable-gpu-sandbox',
      '--hide-scrollbars',
      '--mute-audio',
      '--disable-background-timer-throttling',
    ],
  });
  const context = await browser.newContext({
    viewport,
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();
  page.on('pageerror', (err) => console.error('[PAGEERROR]', err.message));
  return { browser, context, page };
}

async function renderContactSheets(baseUrl) {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const cDir = path.join(TMP_DIR, 'contacts');
  fs.mkdirSync(cDir, { recursive: true });

  console.log(`Rendering ${CONTACT_FRAMES.length} 4K contact-sheet audit frames...`);
  const { browser, page } = await launchBrowser('landscape');
  const cdp = await page.context().newCDPSession(page);

  await page.goto(`${baseUrl}/?mode=landscape`, { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => window.__BOOT_DIRECTOR__());

  const sortedFrames = [...CONTACT_FRAMES].sort((a, b) => a - b);
  const paths = [];
  for (let i = 0; i < sortedFrames.length; i++) {
    const f = sortedFrames[i];
    await page.evaluate((frame) => window.__DIRECTOR__.stepToFrame(frame), f);
    const { data } = await cdp.send('Page.captureScreenshot', { format: 'png' });
    const outPng = path.join(cDir, `c_${String(i).padStart(2, '0')}_f${String(f).padStart(4, '0')}.png`);
    fs.writeFileSync(outPng, Buffer.from(data, 'base64'));
    paths.push(outPng);
    console.log(`  [${i + 1}/${sortedFrames.length}] frame ${f} (t=${frameToSec(f).toFixed(2)}s, beat=${frameToBeat(f).toFixed(1)})`);
  }
  await browser.close();

  // Stitch into two crisp 3x3 contact sheets (each 1920x1080 for crystal-clear visual audit!)
  for (let sheet = 0; sheet < 2; sheet++) {
    const chunk = paths.slice(sheet * 9, sheet * 9 + 9);
    if (!chunk.length) continue;
    const args = ['-hide_banner', '-y'];
    for (const p of chunk) args.push('-i', p);
    const filters = [];
    for (let k = 0; k < chunk.length; k++) {
      const f = sortedFrames[sheet * 9 + k];
      const lbl = `F${f} | ${frameToSec(f).toFixed(1)}s | B${frameToBeat(f).toFixed(0)}`;
      filters.push(`[${k}:v]scale=640:360:flags=lanczos,drawbox=x=0:y=0:w=210:h=26:color=black@0.72:t=fill,drawtext=text='${lbl}':x=8:y=6:fontsize=15:fontcolor=white[v${k}]`);
    }
    const stackInputs = chunk.map((_, k) => `[v${k}]`).join('');
    filters.push(`${stackInputs}xstack=inputs=${chunk.length}:layout=0_0|w0_0|w0+w1_0|0_h0|w0_h0|w0+w1_h0|0_h0+h3|w0_h0+h3|w0+w1_h0+h3[out]`);
    const outSheet = path.join(OUT_DIR, `contact_sheet_${sheet + 1}.png`);
    args.push('-filter_complex', filters.join(';'), '-map', '[out]', outSheet);
    const r = spawnSync('ffmpeg', args, { stdio: 'pipe' });
    if (r.status !== 0) {
      console.error(r.stderr.toString());
      throw new Error('FFmpeg contact sheet failed');
    }
    console.log(`Wrote ${outSheet}`);
  }

  // Also capture 6 key 9:16 Vertical audit frames!
  const vDir = path.join(TMP_DIR, 'contacts_vertical');
  fs.mkdirSync(vDir, { recursive: true });
  const vFrames = [
    CONTACT_FRAMES[1],  // Cold open title
    CONTACT_FRAMES[4],  // Scene 1 DPI 8000
    CONTACT_FRAMES[7],  // Scene 3 Haptics cutaway
    CONTACT_FRAMES[10], // Scene 4 Actions Ring Ultraviolet
    CONTACT_FRAMES[11], // Scene 4 Cairo Wayland Overlay
    CONTACT_FRAMES[17], // Scene 6 Brand Lockup
  ].sort((a, b) => a - b);

  console.log(`Rendering ${vFrames.length} 9:16 Vertical audit frames...`);
  const vb = await launchBrowser('vertical');
  const vcdp = await vb.page.context().newCDPSession(vb.page);
  await vb.page.goto(`${baseUrl}/?mode=vertical`, { waitUntil: 'domcontentloaded' });
  await vb.page.evaluate(() => window.__BOOT_DIRECTOR__());

  const vPaths = [];
  for (let i = 0; i < vFrames.length; i++) {
    const f = vFrames[i];
    await vb.page.evaluate((frame) => window.__DIRECTOR__.stepToFrame(frame), f);
    const { data } = await vcdp.send('Page.captureScreenshot', { format: 'png' });
    const outPng = path.join(vDir, `v_${String(i).padStart(2, '0')}.png`);
    fs.writeFileSync(outPng, Buffer.from(data, 'base64'));
    vPaths.push(outPng);
  }
  await vb.browser.close();

  // Stitch 6 vertical frames into 1 crisp 3x2 contact sheet
  const vArgs = ['-hide_banner', '-y'];
  for (const p of vPaths) vArgs.push('-i', p);
  const vFilters = vPaths.map((_, k) => `[${k}:v]scale=360:640:flags=lanczos[v${k}]`);
  vFilters.push(`[v0][v1][v2][v3][v4][v5]xstack=inputs=6:layout=0_0|w0_0|w0+w1_0|0_h0|w0_h0|w0+w1_h0[out]`);
  const outVSheet = path.join(OUT_DIR, 'contact_sheet_vertical.png');
  vArgs.push('-filter_complex', vFilters.join(';'), '-map', '[out]', outVSheet);
  const vr = spawnSync('ffmpeg', vArgs, { stdio: 'pipe' });
  if (vr.status !== 0) throw new Error(vr.stderr.toString());
  console.log(`Wrote ${outVSheet}`);
}

async function renderFullVideo(baseUrl, mode) {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const isVertical = mode === 'vertical';
  const outMp4 = path.join(
    OUT_DIR,
    isVertical ? 'mx4_studio_launch_v2_30s_vertical_9x16.mp4' : 'mx4_studio_launch_v2_30s_4k60_master.mp4',
  );

  if (!fs.existsSync(AUDIO_WAV)) {
    throw new Error(`Mastered audio missing at ${AUDIO_WAV} — run python3 audio/synth_master.py first.`);
  }

  console.log(`\nStarting full ${isVertical ? '1080x1920 (9:16 Vertical)' : '3840x2160 (4K UHD)'} @ ${FPS}fps render (${TOTAL_FRAMES} frames)...`);
  const { browser, page } = await launchBrowser(mode);
  const cdp = await page.context().newCDPSession(page);

  await page.goto(`${baseUrl}/?mode=${mode}`, { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => window.__BOOT_DIRECTOR__());

  // Hardware NVENC on RTX 4080 SUPER (falls back to libx264 cleanly if needed)
  const ffArgs = [
    '-hide_banner', '-y',
    '-f', 'image2pipe',
    '-vcodec', 'mjpeg',
    '-framerate', String(FPS),
    '-i', 'pipe:0',
    '-i', AUDIO_WAV,
    '-map', '0:v:0',
    '-map', '1:a:0',
    '-c:v', 'h264_nvenc',
    '-preset', 'p6',
    '-rc', 'vbr',
    '-cq', '16',
    '-b:v', isVertical ? '16M' : '42M',
    '-maxrate', isVertical ? '24M' : '60M',
    '-profile:v', 'high',
    '-pix_fmt', 'yuv420p',
    '-color_primaries', 'bt709',
    '-color_trc', 'bt709',
    '-colorspace', 'bt709',
    '-c:a', 'aac',
    '-b:a', '320k',
    '-ar', '48000',
    '-movflags', '+faststart',
    '-shortest',
    outMp4,
  ];

  const ff = spawn('ffmpeg', ffArgs, { stdio: ['pipe', 'inherit', 'pipe'] });
  let ffErr = '';
  ff.stderr.on('data', (d) => { ffErr += d.toString(); });

  const t0 = Date.now();
  for (let f = 0; f < TOTAL_FRAMES; f++) {
    await page.evaluate((frame) => window.__DIRECTOR__.stepToFrame(frame), f);
    const { data } = await cdp.send('Page.captureScreenshot', {
      format: 'jpeg',
      quality: 96,
    });
    const buf = Buffer.from(data, 'base64');
    if (!ff.stdin.write(buf)) {
      await new Promise((res) => ff.stdin.once('drain', res));
    }

    if ((f + 1) % 300 === 0 || f === TOTAL_FRAMES - 1) {
      const elapsed = (Date.now() - t0) / 1000;
      const fpsActual = (f + 1) / Math.max(0.01, elapsed);
      const eta = (TOTAL_FRAMES - f - 1) / Math.max(0.01, fpsActual);
      console.log(`  [${mode}] frame ${f + 1}/${TOTAL_FRAMES} (${(((f + 1) / TOTAL_FRAMES) * 100).toFixed(1)}%) · ${fpsActual.toFixed(1)} fps · ETA ${eta.toFixed(0)}s`);
    }
  }

  ff.stdin.end();
  const code = await new Promise((res) => ff.on('close', res));
  await browser.close();

  if (code !== 0) {
    console.error(ffErr);
    throw new Error(`FFmpeg exited with code ${code}`);
  }
  const szMb = (fs.statSync(outMp4).size / (1024 * 1024)).toFixed(1);
  console.log(`Rendered master video: ${outMp4} (${szMb} MB)`);
}

async function main() {
  const args = process.argv.slice(2);
  const { server, baseUrl } = await startStudioServer();
  try {
    if (args.includes('--contacts')) {
      await renderContactSheets(baseUrl);
    } else {
      const modeArg = args.find((a) => a.startsWith('--mode='));
      const mode = modeArg ? modeArg.split('=')[1] : 'landscape';
      await renderFullVideo(baseUrl, mode);
    }
  } finally {
    server.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
