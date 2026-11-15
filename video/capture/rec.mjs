// Real screen recordings of the running PARALLAX app (http://127.0.0.1:8000), for the demo video.
// Chrome's own screencast (CDP Page.startScreencast) gives JPEG frames with timestamps; they are assembled into a
// constant-30fps H.264 clip with the ffmpeg that ships with Remotion.  The page is rendered at 2x and scaled to
// 1920 x 1080, so text stays sharp.  Headless Chrome draws no mouse pointer, so a small dot follows the real
// mouse events (the clicks themselves are real).
import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import { mkdirSync, rmSync, writeFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
export const BASE = 'http://127.0.0.1:8000';
export const OUT = join(HERE, '..', 'public', 'clips');
const TMP = join(HERE, 'frames');

const CURSOR = `
  (() => {
    if (window.__cursor) return;
    const dot = document.createElement('div');
    dot.id = '__cursor';
    Object.assign(dot.style, { position: 'fixed', left: '0px', top: '0px', width: '22px', height: '22px', margin: '-11px 0 0 -11px',
      borderRadius: '50%', background: 'rgba(255,255,255,0.92)', boxShadow: '0 0 0 2px rgba(0,0,0,0.55), 0 2px 10px rgba(0,0,0,0.5)',
      pointerEvents: 'none', zIndex: 2147483647, transition: 'transform 120ms ease', opacity: '0' });
    const add = () => document.body && !dot.isConnected && document.body.appendChild(dot);
    document.addEventListener('mousemove', e => { add(); dot.style.opacity = '1'; dot.style.left = e.clientX + 'px'; dot.style.top = e.clientY + 'px'; }, true);
    document.addEventListener('mousedown', () => { dot.style.transform = 'scale(0.7)'; }, true);
    document.addEventListener('mouseup', () => { dot.style.transform = 'scale(1)'; }, true);
    window.__cursor = dot;
  })();`;

export async function open() {
  const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--hide-scrollbars', '--force-color-profile=srgb'] });
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2, colorScheme: 'dark' });
  await context.addInitScript(CURSOR);
  return { browser, context };
}

/** Record one clip.  `act(page, helpers)` drives the page; returns the clip path and its real duration in seconds. */
export async function record(context, name, act, { start } = {}) {
  const page = await context.newPage();
  if (start) {
    await page.goto(BASE + start, { waitUntil: 'networkidle', timeout: 90000 }).catch(() => {});
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(800);
  }
  const dir = join(TMP, name);
  rmSync(dir, { recursive: true, force: true });
  mkdirSync(dir, { recursive: true });
  const cdp = await context.newCDPSession(page);
  const frames = [];
  cdp.on('Page.screencastFrame', async ({ data, metadata, sessionId }) => {
    const i = frames.length;
    writeFileSync(join(dir, `${String(i).padStart(5, '0')}.jpg`), Buffer.from(data, 'base64'));
    frames.push(metadata.timestamp);
    cdp.send('Page.screencastFrameAck', { sessionId }).catch(() => {});
  });
  await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 94, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1 });
  await page.mouse.move(1500, 900);
  const h = helpers(page);
  await act(page, h);
  await page.waitForTimeout(400);
  await cdp.send('Page.stopScreencast');
  await page.close();
  return encode(name, dir, frames);
}

/** Re-encode a recording from its saved frames (capture/frames/<name>/list.txt), without recording again. */
export function reencode(name) {
  const dir = join(TMP, name);
  const list = join(dir, 'list.txt');
  if (!existsSync(list)) throw new Error(`no saved frames for ${name}`);
  const out = join(OUT, `${name}.mp4`);
  mkdirSync(OUT, { recursive: true });
  execFileSync('npx', ['remotion', 'ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', list,
    '-vf', 'scale=1920:1080:flags=lanczos,format=yuv420p', '-fps_mode', 'cfr', '-r', '30', '-c:v', 'libx264', '-crf', '14', '-preset', 'slow', '-movflags', '+faststart', out],
    { cwd: join(HERE, '..'), stdio: 'inherit' });
  return out;
}

function encode(name, dir, frames) {
  if (frames.length < 2) throw new Error(`${name}: only ${frames.length} frames captured`);
  const lines = [];
  for (let i = 0; i < frames.length; i++) {
    const d = i + 1 < frames.length ? Math.max(frames[i + 1] - frames[i], 1 / 120) : 0.5;
    lines.push(`file '${join(dir, String(i).padStart(5, '0') + '.jpg')}'`, `duration ${d.toFixed(5)}`);
  }
  lines.push(`file '${join(dir, String(frames.length - 1).padStart(5, '0') + '.jpg')}'`);
  writeFileSync(join(dir, 'list.txt'), lines.join('\n'));
  mkdirSync(OUT, { recursive: true });
  const out = join(OUT, `${name}.mp4`);
  execFileSync('npx', ['remotion', 'ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', join(dir, 'list.txt'),
    '-vf', 'scale=1920:1080:flags=lanczos,format=yuv420p', '-fps_mode', 'cfr', '-r', '30', '-c:v', 'libx264', '-crf', '14', '-preset', 'slow', '-movflags', '+faststart', out],
    { cwd: join(HERE, '..'), stdio: 'inherit' });
  const seconds = frames[frames.length - 1] - frames[0] + 0.5;
  console.log(`${name}: ${frames.length} frames over ${seconds.toFixed(1)} s -> ${out}`);
  return { out, seconds };
}

/** Human-speed helpers: smooth mouse moves, clicks on elements, slow typing, smooth scrolling. */
export function helpers(page) {
  let mx = 1500, my = 900;
  const ease = t => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const moveTo = async (x, y, ms = 700) => {
    const steps = Math.max(8, Math.round(ms / 16));
    const x0 = mx, y0 = my;
    for (let i = 1; i <= steps; i++) {
      const t = ease(i / steps);
      await page.mouse.move(x0 + (x - x0) * t, y0 + (y - y0) * t);
      await page.waitForTimeout(ms / steps);
    }
    mx = x; my = y;
  };
  const centre = async (locator) => {
    await locator.first().scrollIntoViewIfNeeded().catch(() => {});
    const b = await locator.first().boundingBox();
    if (!b) throw new Error('element not visible');
    return [b.x + b.width / 2, b.y + b.height / 2];
  };
  return {
    wait: ms => page.waitForTimeout(ms),
    moveTo,
    async click(locator, { ms = 700, pause = 250 } = {}) {
      const [x, y] = await centre(locator);
      await moveTo(x, y, ms);
      await page.waitForTimeout(pause);
      await page.mouse.down(); await page.waitForTimeout(90); await page.mouse.up();
      return [x, y];
    },
    async hover(locator, ms = 700) { const [x, y] = await centre(locator); await moveTo(x, y, ms); return [x, y]; },
    async type(text, delay = 95) { for (const ch of text) { await page.keyboard.type(ch); await page.waitForTimeout(delay + ((ch.charCodeAt(0) * 37) % 40)); } },
    async scrollBy(dy, ms = 1600) {
      const steps = Math.max(10, Math.round(ms / 16));
      let done = 0;
      for (let i = 1; i <= steps; i++) {
        const target = Math.round(dy * ease(i / steps));
        await page.mouse.wheel(0, target - done); done = target;
        await page.waitForTimeout(ms / steps);
      }
    },
    async scrollToEl(locator, offset = 140, ms = 1800) {
      const b = await locator.first().boundingBox();
      if (!b) return;
      await this.scrollBy(b.y - offset, ms);
    },
  };
}

export async function shot(context, name, path, { full = false, wait = 1200, scrollTo } = {}) {
  const page = await context.newPage();
  await page.goto(BASE + path, { waitUntil: 'networkidle', timeout: 90000 }).catch(() => {});
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(wait);
  if (scrollTo) await page.locator(scrollTo).first().scrollIntoViewIfNeeded().catch(() => {});
  const dir = join(OUT, '..', 'shots');
  mkdirSync(dir, { recursive: true });
  const out = join(dir, `${name}.png`);
  await page.screenshot({ path: out, fullPage: full });
  await page.close();
  console.log(`${name}: ${out}`);
  return out;
}

export { existsSync };
