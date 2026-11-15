// The demo video's real recordings, one function per scene.  Run: node capture/scenes.mjs [scene ...]
import { open, record, shot } from './rec.mjs';
import { writeFileSync, readFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const LOG = join(HERE, '..', 'public', 'clips', 'clips.json');

const SCENES = {
  // S1: SPHEREx's 102 colours sweeping across a real patch of sky.
  async 'sky-colours'(ctx) {
    return record(ctx, 'sky-colours', async (page, h) => {
      await h.click(page.getByRole('button', { name: /Layers: choose/ }), { ms: 500 });
      await h.click(page.getByRole('button', { name: /Play all 102 colours/ }), { ms: 600 });
      await h.click(page.getByRole('button', { name: /Layers: choose/ }), { ms: 600 });
      await h.moveTo(1880, 1040, 500);
      await h.wait(13500);
    }, { start: '/map?ra=83.8&dec=-3.0&fov=34' });
  },

  // S5: what NASA asked for. Type coordinates, Go, the images play like a video, then blink.
  async 'explore-coords'(ctx) {
    return record(ctx, 'explore-coords', async (page, h) => {
      await h.wait(1200);
      await h.click(page.getByPlaceholder('Star name or sky position'), { ms: 800 });
      await h.type('331.0965 -56.8006');
      await h.wait(400);
      await h.click(page.getByRole('button', { name: '10′', exact: true }), { ms: 600 });   // sky width chip
      await h.wait(300);
      await h.click(page.getByRole('button', { name: 'Go' }), { ms: 600 });
      await h.wait(4500);
      await h.click(page.getByRole('radio', { name: /^Play$/ }).first(), { ms: 800 });   // view mode: play in time order
      await h.wait(400);
      await page.locator('select').first().selectOption({ label: '12 per sec' }).catch(() => {});
      await h.wait(6500);
      await h.click(page.getByRole('radio', { name: /^Blink$/ }).first(), { ms: 800 });
      await h.moveTo(1300, 760, 700);
      await h.wait(5000);
    }, { start: '/explore' });
  },

  // S5b: the other tools NASA listed: subtract, add, colour, click a dot to measure it.
  async 'explore-tools'(ctx) {
    return record(ctx, 'explore-tools', async (page, h) => {
      await h.wait(1500);
      await h.click(page.getByRole('radio', { name: /^Subtract$/ }).first(), { ms: 800 });
      await h.wait(3500);
      await h.click(page.getByRole('radio', { name: /^Add$/ }).first(), { ms: 700 });
      await h.wait(3000);
      await h.click(page.getByRole('radio', { name: /^Colours?$/ }).first(), { ms: 700 });
      await h.wait(3500);
      await h.click(page.getByRole('radio', { name: /^Blink$/ }).first(), { ms: 700 });
      await h.wait(1500);
      const img = await page.locator('canvas').first().boundingBox();
      const x = img ? img.x + img.width / 2 : 787, y = img ? img.y + img.height / 2 : 574;
      await h.moveTo(x, y, 900); await h.wait(300);
      await page.mouse.down(); await h.wait(90); await page.mouse.up();
      await h.wait(7000);
      await h.moveTo(1780, 600, 900);
      await h.scrollBy(520, 2200);
      await h.wait(3500);
    }, { start: '/explore?target=epsilon-indi-b' });
  },

  // S7: Test 1 on the Proof page. Guess, open the sealed images, see where the star landed.
  async 'proof-test'(ctx) {
    return record(ctx, 'proof-test', async (page, h) => {
      await h.wait(800);
      await h.scrollToEl(page.getByText('Predict where a star will be', { exact: false }), 120, 2000);
      await h.wait(1500);
      await h.click(page.getByRole('button', { name: /It keeps moving/ }).first(), { ms: 900 });
      await h.wait(1500);
      await h.click(page.getByRole('button', { name: /Open them/ }).first(), { ms: 900 });
      await h.wait(6500);
      await h.scrollBy(380, 1800);
      await h.wait(4500);
    }, { start: '/proof' });
  },

  // S6: NASA's five test targets, the scorecard.
  async 'proof-scorecard'(ctx) {
    return record(ctx, 'proof-scorecard', async (page, h) => {
      await h.wait(600);
      await h.scrollToEl(page.getByText("NASA's five test targets", { exact: false }), 90, 2400);
      await h.wait(2500);
      await h.scrollBy(520, 4200);
      await h.wait(2500);
      await h.scrollBy(520, 4200);
      await h.wait(2000);
    }, { start: '/proof' });
  },

  // S8: Makemake found blind, and Eris by stacking.
  async 'finds-worlds'(ctx) {
    return record(ctx, 'finds-worlds', async (page, h) => {
      await h.wait(800);
      await h.scrollToEl(page.getByText('Found blind', { exact: false }), 110, 2600);
      await h.wait(5500);
      await h.scrollBy(560, 3000);
      await h.wait(4000);
      await h.scrollToEl(page.getByText('Found blind by stacking', { exact: false }), 110, 3000);
      await h.wait(5500);
    }, { start: '/hunt' });
  },

  // S9: 102 colours read by the model: methane spectra and the other-telescope checks.
  async 'finds-spectra'(ctx) {
    return record(ctx, 'finds-spectra', async (page, h) => {
      await h.wait(800);
      await h.scrollToEl(page.getByText('Reading 102 colours.', { exact: false }), 110, 2600);
      await h.wait(4500);
      await h.scrollToEl(page.locator('.cs-cands').first(), 260, 4200);
      await h.wait(5000);
      await h.scrollBy(620, 3600);
      await h.wait(3500);
    }, { start: '/hunt' });
  },

  // S10: 23 telescopes: the JWST layer at the Pillars of Creation, then Chandra at the Crab.
  async 'map-telescopes'(ctx) {
    return record(ctx, 'map-telescopes', async (page, h) => {
      await h.wait(1500);
      await h.click(page.getByRole('button', { name: /Layers: choose/ }), { ms: 700 });
      await h.wait(900);
      await h.click(page.locator('button[role=radio][title^="JWST"]'), { ms: 900 });
      await h.wait(600);
      await h.click(page.getByRole('button', { name: /Show me the Pillars of Creation/ }), { ms: 800 });
      await h.click(page.getByRole('button', { name: /Layers: choose/ }), { ms: 700 });
      await h.moveTo(1860, 980, 600);
      await h.wait(5500);
      await h.click(page.getByRole('button', { name: /Layers: choose/ }), { ms: 700 });
      await h.wait(600);
      await h.click(page.locator('button[role=radio][title^="Chandra"]'), { ms: 900 });
      await h.wait(500);
      await h.click(page.getByRole('button', { name: /Show me the Crab Nebula/ }), { ms: 800 });
      await h.click(page.getByRole('button', { name: /Layers: choose/ }), { ms: 700 });
      await h.moveTo(1860, 980, 600);
      await h.wait(5000);
    }, { start: '/map?ra=274.7&dec=-13.807&fov=0.4' });
  },

  // S10b: what other telescopes saw at WISE 0855 (Hubble, JWST, ...), with real previews.
  async 'map-scopes'(ctx) {
    return record(ctx, 'map-scopes', async (page, h) => {
      await h.wait(1200);
      await h.click(page.getByRole('button', { name: 'Cold neighbours' }), { ms: 800 });
      await h.wait(900);
      await h.click(page.getByText('WISE 0855', { exact: true }).first(), { ms: 800 });
      await h.wait(2500);
      const ask = page.getByRole('button', { name: /What other telescopes saw here/ });
      await ask.scrollIntoViewIfNeeded();
      await h.wait(600);
      await h.click(ask, { ms: 800 });
      await h.wait(3500);
      await page.locator('.os').first().scrollIntoViewIfNeeded().catch(() => {});
      await h.wait(3000);
      await page.locator('.os-pics').first().scrollIntoViewIfNeeded().catch(() => {});
      await h.wait(4500);
    }, { start: '/map?v=video' });
  },

  // S11: adding photos along a path makes a faint asteroid appear; then what we cannot see yet.
  async 'how-stack'(ctx) {
    return record(ctx, 'how-stack', async (page, h) => {
      await h.wait(1500);
      const slider = page.locator('#how-n');
      await slider.scrollIntoViewIfNeeded();
      await h.wait(800);
      await h.click(slider, { ms: 900 });
      await page.keyboard.press('Home');
      await h.wait(1600);
      for (let i = 0; i < 5; i++) { await page.keyboard.press('ArrowRight'); await h.wait(1500); }
      await h.wait(2500);
    }, { start: '/how#s5' });
  },
  async 'how-limits'(ctx) {
    return record(ctx, 'how-limits', async (page, h) => {
      await h.wait(1500);
      await h.scrollBy(260, 2400);
      await h.wait(5000);
    }, { start: '/how#s8' });
  },

  // S12: anyone can check a real candidate (no vote is cast in the recording).
  async 'check'(ctx) {
    return record(ctx, 'check', async (page, h) => {
      await h.wait(1500);
      await h.hover(page.getByText('Does the light almost vanish', { exact: false }), 900);
      await h.wait(1500);
      await h.hover(page.getByRole('button', { name: /Yes, it goes dark/ }), 900);
      await h.wait(2500);
      await h.moveTo(1500, 860, 900);
      await h.wait(2500);
    }, { start: '/check' });
  },

  // S13: the explainer and the sky chunks.
  async 'how-overview'(ctx) {
    return record(ctx, 'how-overview', async (page, h) => {
      await h.wait(2200);
      await h.scrollBy(900, 3600);
      await h.wait(2500);
      await h.scrollBy(1200, 4200);
      await h.wait(2000);
    }, { start: '/how' });
  },
  async 'map-chunks'(ctx) {
    return record(ctx, 'map-chunks', async (page, h) => {
      await h.wait(2000);
      const b = page.locator('.gm-status__chunk').first();
      await h.click(b, { ms: 900 });
      await h.wait(6500);
    }, { start: '/map?ra=83.8&dec=-5.4&fov=4' });
  },
  async 'home'(ctx) {
    return record(ctx, 'home', async (page, h) => {
      await h.wait(2500);
      await h.scrollBy(700, 3500);
      await h.wait(1500);
    }, { start: '/' });
  },
};

const names = process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(SCENES);
const { browser, context } = await open();
const log = existsSync(LOG) ? JSON.parse(readFileSync(LOG, 'utf8')) : {};
for (const n of names) {
  try {
    const r = await SCENES[n](context);
    log[n] = { file: `clips/${n}.mp4`, seconds: Number(r.seconds.toFixed(2)), recorded_utc: new Date().toISOString() };
    writeFileSync(LOG, JSON.stringify(log, null, 1));
  } catch (e) {
    console.log(`FAILED ${n}: ${String(e.message || e).split('\n')[0]}`);
  }
}
await browser.close();
