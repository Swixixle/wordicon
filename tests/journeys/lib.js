// Shared by every journey. The scratch server's address and the minted
// session come from the directory run.sh hands over (JOURNEY_DIR); the
// browser is whatever Playwright installed (or JOURNEY_CHROME, pinned by
// the runner). Every check prints one line; a failing check also saves a
// screenshot into JOURNEY_OUT so CI can hand it back. Any request that
// leaves the scratch origin is a failure: these journeys run with the
// network gone, the gateway poisoned, and no key.
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const DIR = process.env.JOURNEY_DIR || '/tmp/anat';
const OUT = process.env.JOURNEY_OUT || path.join(DIR, 'out');
const BASE = process.env.JOURNEY_BASE || 'http://127.0.0.1:' + (process.env.JOURNEY_PORT || '8499');
const tok = fs.readFileSync(path.join(DIR, 'token'), 'utf8').trim();
const ck = fs.readFileSync(path.join(DIR, 'cookie'), 'utf8').trim();
fs.mkdirSync(OUT, { recursive: true });

const fails = [];
let lastPage = null;
let n = 0;
const ok = (cond, msg) => {
  n += 1;
  console.log((cond ? 'ok   ' : 'FAIL ') + msg);
  if (!cond) {
    fails.push(msg);
    if (lastPage) {
      lastPage.screenshot({ path: path.join(OUT, `fail-${String(n).padStart(3, '0')}.png`), fullPage: true }).catch(() => {});
    }
  }
};

async function launch() {
  // block 106: a fake microphone (a tone) and an auto-granted permission, so
  // the Speak journey can press, record, stop and transcribe with no device
  const opts = { args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] };
  if (process.env.JOURNEY_CHROME) opts.executablePath = process.env.JOURNEY_CHROME;
  return chromium.launch(opts);
}

// A context carrying the minted session, watched for off-origin requests.
async function pairedContext(browser, opts = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, ...opts });
  await ctx.addCookies([{ name: ck, value: tok, domain: '127.0.0.1', path: '/' }]);
  ctx.on('page', p => { lastPage = p; watch(p); });
  return ctx;
}
const offOrigin = [];
function watch(page) {
  page.on('request', r => { const u = r.url(); if (!u.startsWith(BASE) && !u.startsWith('data:') && !u.startsWith('blob:') && !u.startsWith('about:')) offOrigin.push(u); });
}
function finish(name) {
  ok(offOrigin.length === 0, name + ': no request left the scratch origin' + (offOrigin.length ? ': ' + JSON.stringify(offOrigin.slice(0, 5)) : ''));
  console.log(`CHECKS ${n}`);
  console.log(fails.length ? `FAIL ${fails.length}` : `JOURNEY ${name} OK`);
  process.exit(fails.length ? 1 : 0);
}

// Slice 2: a place opens inside the shell now, so what used to be "the page"
// after clicking a door is a frame inside it. This waits for that frame and
// hands it back; everything a journey did to the page it does to this.
async function place(page, path, ms) {
  const until = Date.now() + (ms || 8000);
  while (Date.now() < until) {
    const f = page.frames().find(fr => fr !== page.mainFrame() && fr.url().indexOf(path) !== -1);
    if (f) { try { await f.waitForLoadState('domcontentloaded'); } catch (e) {} return f; }
    await page.waitForTimeout(150);
  }
  return null;
}

module.exports = {
  place, BASE, DIR, OUT, tok, ck, ok, launch, pairedContext, finish, setPage: p => { lastPage = p; } };
