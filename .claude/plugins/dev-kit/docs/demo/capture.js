// Screenshots of the board of the demo project (build_demo.py), for the documentation.
// usage: node capture.js <board url> <images dir>      (Playwright with Chromium)
const { chromium } = require('playwright');
const path = require('path');
const [url, dir] = process.argv.slice(2);
const SHOTS = [  // file, color scheme, steps before the shot
  ['board-construction', 'light', []],
  ['board-construction-dark', 'dark', []],
  ['board-conception', 'light', [['click', '#ph-conception']]],
  ['board-planning', 'light', [['click', '#ph-planning']]],
  ['board-milestones', 'light', [['click', '#ph-construction']]],
  ['board-releases', 'light', [['click', '#ph-releases']]],
  ['board-stable', 'light', [['click', '#ph-stable']]],
  ['board-pt-br', 'light', [['lang', 'pt-BR']]],
  ['board-needs-you', 'light', [['click', '#needs-btn']]],
  ['board-autopilot', 'light', [['click', '#ap-btn']]],
];
(async () => {
  const b = await chromium.launch();
  for (const [name, scheme, steps] of SHOTS) {
    const p = await b.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 2, colorScheme: scheme, locale: 'en-US' });
    const errors = [];
    p.on('pageerror', (e) => errors.push(String(e)));
    await p.goto(url);
    await p.waitForFunction(() => document.getElementById('main').getAttribute('aria-busy') === 'false', null, { timeout: 20000 });
    for (const [op, arg] of steps) {
      if (op === 'click') await p.click(arg);
      if (op === 'scroll') await p.evaluate((s) => window.scrollTo(0, document.querySelector(s).getBoundingClientRect().top + window.scrollY - 16), arg);
      if (op === 'lang') await p.evaluate((l) => { localStorage.setItem('board-lang', l); location.reload(); }, arg);
      await p.waitForTimeout(500);
    }
    if (steps.some(([op]) => op === 'lang')) await p.waitForFunction(() => document.getElementById('main').getAttribute('aria-busy') === 'false');
    await p.waitForTimeout(600);
    await p.screenshot({ path: path.join(dir, `${name}.png`), fullPage: false });
    if (errors.length) { console.error(name, errors); process.exitCode = 1; }
    await p.close();
  }
  await b.close();
})();
