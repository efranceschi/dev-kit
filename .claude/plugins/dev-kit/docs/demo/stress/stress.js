// Stress report of the board: every screen at several window sizes, with what spills out of its box, the page's
// sideways scroll, page errors and the size of /api/state; then the main-thread time of 5 live updates.
// usage: node stress.js <board url> <out dir> <tag> [--full] [--root <project dir>]
//   --full  also 1280x720 dark and a 390x844 phone (default: 1440x1000 and 1024x640)
//   --root  the project the board serves: records 5 events in it and measures the long tasks each update costs
// Writes <tag>-<width>-<scheme>-<screen>.png and <tag>-report.json in <out dir>. Needs Playwright (see docs/maintainers.md).
const { chromium } = require('playwright');
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const args = process.argv.slice(2);
const [url, dir, tag] = args;
const full = args.includes('--full');
const root = args.includes('--root') ? args[args.indexOf('--root') + 1] : null;
if (!url || !dir || !tag) { console.error('usage: node stress.js <board url> <out dir> <tag> [--full] [--root <project dir>]'); process.exit(2); }
const DS = path.resolve(__dirname, '../../../skills/core/scripts/dev_state.py');
fs.mkdirSync(dir, { recursive: true });
const SCREENS = [
  ['construction', []], ['map', ['#ph-map']], ['conception', ['#ph-conception']], ['planning', ['#ph-planning']],
  ['releases', ['#ph-releases']], ['stable', ['#ph-stable']], ['needs', ['#needs-btn']], ['activity', ['#act-btn']],
  ['qa', ['#tab-qa']], ['burndown', ['#metrics-btn']], ['velocity', ['#metrics-btn', '#ins-tab-velocity']],
  ['gates', ['#metrics-btn', '#ins-tab-gates']], ['arch', ['#ph-arch']],
];
const VIEWS = full ? [[1440, 1000, 'light', 'en-US'], [1280, 720, 'dark', 'en-US'], [1024, 640, 'light', 'pt-BR'], [390, 844, 'light', 'pt-BR']]
  : [[1440, 1000, 'light', 'en-US'], [1024, 640, 'light', 'pt-BR']];
// what leaves its box without a scroller or a clip to hold it, and whether the page scrolls sideways
const probe = () => {
  const W = innerWidth, out = { hscroll: document.documentElement.scrollWidth > W + 1, spill: [] };
  const box = 'dialog[open], .tile, .card, .col, .lane-strip, .rel-card, .fnode, .chip, li, button';
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    if (!r.width || !r.height || cs.visibility === 'hidden' || cs.position === 'absolute') continue;  // corner badges sit outside on purpose
    const p = el.parentElement && el.parentElement.closest(box);
    if (!p) continue;
    const q = p.getBoundingClientRect();
    const clip = () => { for (let a = el.parentElement; a && a !== p.parentElement; a = a.parentElement) { if (/(hidden|auto|scroll|clip)/.test(getComputedStyle(a).overflowX)) return true; } return false; };
    if ((r.right > q.right + 3 || r.left < q.left - 3) && !clip()) out.spill.push(`${el.tagName.toLowerCase()}.${[...el.classList].join('.')} in ${p.tagName.toLowerCase()}.${[...p.classList].join('.')}`);
  }
  out.spill = [...new Set(out.spill)].slice(0, 8);
  return out;
};
const ready = (p) => p.waitForFunction(() => document.getElementById('main').getAttribute('aria-busy') === 'false', null, { timeout: 30000 });
(async () => {
  const b = await chromium.launch();
  const report = [];
  for (const [w, hgt, scheme, loc] of VIEWS) {
    for (const [name, clicks] of SCREENS) {
      const p = await b.newPage({ viewport: { width: w, height: hgt }, colorScheme: scheme, locale: loc });
      const errors = [];
      p.on('pageerror', (e) => errors.push(String(e).slice(0, 160)));
      let bytes = 0;
      p.on('response', async (r) => { if (/api\/state/.test(r.url())) { const n = Number(r.headers()['content-length'] || 0); bytes = Math.max(bytes, n); } });
      await p.goto(url);
      if (loc !== 'en-US') await p.evaluate((l) => { localStorage.setItem('board-lang', l); location.reload(); }, loc);
      await ready(p);
      for (const c of clicks) { try { await p.click(c, { timeout: 3000 }); } catch (e) { errors.push('no ' + c); } await p.waitForTimeout(400); }
      await p.waitForTimeout(500);
      const r = await p.evaluate(probe);
      await p.screenshot({ path: `${dir}/${tag}-${w}-${scheme}-${name}.png` });
      report.push({ tag, w, hgt, scheme, loc, name, bytes, ...r, errors });
      await p.close();
    }
  }
  const p = await b.newPage({ viewport: { width: 1440, height: 1000 } });
  await p.goto(url);
  await ready(p);
  const perf = { nodes: await p.evaluate(() => document.querySelectorAll('*').length) };
  if (root) {
    await p.evaluate(() => { window.__lt = []; new PerformanceObserver((l) => l.getEntries().forEach((e) => window.__lt.push(Math.round(e.duration)))).observe({ type: 'longtask' }); });
    for (let i = 0; i < 5; i++) {
      execFileSync('python3', ['-I', DS, '--root', root, 'event', 'tip', '--set', `tip=t${i}`]);
      await p.waitForTimeout(2500);
    }
    perf.long_tasks_ms = await p.evaluate(() => window.__lt);
  }
  report.push({ tag, perf });
  fs.writeFileSync(`${dir}/${tag}-report.json`, JSON.stringify(report, null, 1));
  const bad = report.filter((x) => x.name && (x.hscroll || x.errors.length || x.spill.length));
  console.log(`${report.length - 1} screens · ${bad.length} with sideways scroll, spills or errors · ${JSON.stringify(perf)}`);
  await b.close();
})();
