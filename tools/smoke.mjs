// CI smoke test: open the page in a real browser and fail on any script error, an empty city, or details
// that do not open — on a desktop and a phone screen. `validate.py` only proves the script parses; a runtime
// error (e.g. a variable read before it is declared) still blanks the whole map, and only a browser sees it.
// Usage: node tools/smoke.mjs [path/to/index.html]   (CHROME=/path/to/chrome overrides the browser)
import { chromium } from 'playwright-core';
import { resolve } from 'node:path';

const page = resolve(process.argv[2] || 'index.html');
const browser = await chromium.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome', headless: true });
const fail = [];
for (const [name, opts] of [['desktop', { viewport: { width: 1400, height: 860 } }],
                            ['phone', { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }]]) {
  const ctx = await browser.newContext(opts);
  const p = await ctx.newPage();
  p.on('pageerror', e => fail.push(`${name}: script error: ${e.message}`));
  await p.goto('file://' + page);
  await p.waitForTimeout(1500);
  for (const city of ['hcmc', 'dalat', 'nhatrang', 'mytho']) {
    const opened = await p.evaluate(c => { const t = document.querySelector(`#tabs button[data-city="${c}"]`); if (t) t.click(); return !!t; }, city);
    if (!opened) { fail.push(`${name}: the ${city} tab is missing — the page did not render`); continue; }
    await p.waitForTimeout(200);
    if (!(await p.locator('.card').count())) fail.push(`${name}: ${city} shows no places`);
  }
  try {
    if (name === 'phone') await p.locator('#viewtoggle button[data-v="list"]').click({ timeout: 5000 });
    await p.locator('.card').first().click({ timeout: 5000 });
    await p.waitForTimeout(300);
    if (!(await p.locator('#detail h2').isVisible())) fail.push(`${name}: a place's details did not open`);
  } catch (e) { fail.push(`${name}: could not open a place: ${e.message.split('\n')[0]}`); }
  await ctx.close();
}
await browser.close();
if (fail.length) { console.error(fail.join('\n')); process.exit(1); }
console.log('smoke OK: no script errors; all four cities list places; details open on desktop and phone');
