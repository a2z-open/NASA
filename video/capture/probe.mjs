import { open, BASE } from './rec.mjs';
const { browser, context } = await open();
const page = await context.newPage();
await page.goto(BASE + '/explore?target=epsilon-indi-b', { waitUntil: 'networkidle' });
await page.waitForTimeout(2000);
for (const [label, loc] of [['placeholder', page.getByPlaceholder('A name or coordinates')], ['subtract', page.getByRole('button', { name: /^Subtract$/ })], ['subtract-text', page.getByText('Subtract', { exact: true })], ['play', page.getByRole('button', { name: /^Play$/ })], ['blink', page.getByRole('radio', { name: /Blink/ })], ['go', page.getByRole('button', { name: 'Go' })]]) {
  const n = await loc.count();
  const vis = [];
  for (let i = 0; i < n; i++) vis.push(await loc.nth(i).isVisible());
  console.log(label, n, vis.join(','));
}
const html = await page.evaluate(() => [...document.querySelectorAll('*')].filter(e => /^(Play|Blink|Subtract|Add|Colour)$/.test((e.textContent||'').trim()) && e.children.length <= 1).map(e => `${e.tagName}.${e.className}[role=${e.getAttribute('role')}]`).slice(0, 12).join('\n'));
console.log(html);
await browser.close();
