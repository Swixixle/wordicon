// Screenshots of the RUNNING workspace (instructions §11: "inspect screenshots
// of the running application, not just the design canvas"): every panel
// arrangement, narrow and zoomed, selected text with its menu, a proposal,
// result / partial / error / unknown states, a reader's feedback, a source
// reading opened as a place, Your work and Investigate, Versions, Help.
// Each shot records page errors and whether the page overflowed sideways.
// Fixtures only (the dev scratch server on the mock lane).
const fs = require('fs'), path = require('path');
const playwright = require('playwright');
const DIR = process.env.JOURNEY_DIR;
const BASE = 'http://127.0.0.1:' + (process.env.JOURNEY_PORT || '8499');
const ENGINE = process.env.ENGINE === 'webkit' ? 'webkit' : 'chromium';
const OUT = process.env.OUT || path.join(DIR, 'shots', ENGINE);   // usage: JOURNEY_DIR=<dev dir> JOURNEY_PORT=<port> ENGINE=chromium|webkit node tests/slice_g/shots.js
fs.mkdirSync(OUT, { recursive: true });
const tok = fs.readFileSync(path.join(DIR, 'token'), 'utf8').trim();
const ck = fs.readFileSync(path.join(DIR, 'cookie'), 'utf8').trim();

// the seeded record's ids, from the seeder's own report (never a stale constant)
const seeded = (() => { try { const lines = fs.readFileSync(path.join(DIR, 'out', 'fixtures.log'), 'utf8').trim().split('\n'); return JSON.parse(lines[lines.length - 1]); } catch (e) { return {}; } })();
const PARTIAL_TRACE = (seeded.partial && seeded.partial.deepPartial) || '';
const DRAFT = 'The house had two doors and we only ever used one.\n\nWhen the second one opened, in the winter my father died, the cold came through it like a guest who had been waiting on the step for years. Nobody said so. We stood in the hall with our coats on.\n\nI have been trying to name what that door was for.';

(async () => {
  const browser = await playwright[ENGINE].launch();
  const report = { engine: ENGINE, shots: [] };
  const mk = async (viewport, extra = {}) => {
    const ctx = await browser.newContext({ viewport, ...extra });
    await ctx.addCookies([{ name: ck, value: tok, domain: '127.0.0.1', path: '/' }]);
    const page = await ctx.newPage();
    const errs = [];
    page.on('pageerror', e => errs.push('pageerror: ' + e.message));
    page.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
    return { ctx, page, errs };
  };
  const shot = async (page, errs, name, note) => {
    const m = await page.evaluate(() => ({
      sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,
      bodySw: document.body.scrollWidth, page: document.getElementById('shell') && document.getElementById('shell').dataset.page,
      tools: document.getElementById('shell') && document.getElementById('shell').dataset.tools, results: document.getElementById('shell') && document.getElementById('shell').dataset.results,
      focus: document.getElementById('shell') && document.getElementById('shell').dataset.focus, narrow: document.getElementById('shell') && document.getElementById('shell').dataset.narrow,
      meta: (document.getElementById('doc-meta') || {}).textContent,
    }));
    const file = path.join(OUT, name + '.png');
    await page.screenshot({ path: file });
    const overflow = m.sw > m.cw + 1 || m.bodySw > m.cw + 1;
    report.shots.push({ name, note, file, viewport: page.viewportSize(), overflow, scrollWidth: m.sw, clientWidth: m.cw, state: { page: m.page, tools: m.tools, results: m.results, focus: m.focus, narrow: m.narrow }, meta: m.meta, errors: errs.slice() });
    console.log((overflow ? 'OVERFLOW ' : 'ok       ') + name + ' ' + JSON.stringify(page.viewportSize()) + (errs.length ? ' errors=' + errs.length : ''));
    errs.length = 0;
  };
  const select = (page, a, b) => page.evaluate(([a, b]) => { window.__work.editor.focus(); window.__work.editor.setSelection(a, b); }, [a, b]);
  const settled = page => page.waitForFunction(() => { const s = window.__work.session; return !s.inflight && s.seq === s.ackSeq && s.status === 'saved'; }, null, { timeout: 15000, polling: 100 }).catch(() => {});
  const draft = async page => {
    await page.evaluate(t => window.__work.session.newDocument(t), DRAFT);
    await page.waitForTimeout(200);
    await settled(page);
    await page.evaluate(() => window.__work.session.rename('Two doors'));
    await settled(page);
    await page.evaluate(() => { const e = window.__work.editor; e.setSelection(0, 0); e.focus(); });
  };

  // ---- 1440×900: the arrangements, with a completed result on the right ----
  let { ctx, page, errs } = await mk({ width: 1440, height: 900 });
  await page.goto(BASE + '/work'); await page.waitForSelector('.pm-editor'); await page.waitForTimeout(600);
  await draft(page);
  await shot(page, errs, '01-tools-open-results-closed', 'the default arrangement: Tools open, Results closed, the draft on the blue surface');
  // a result: analyze the selected sentence on the mock lane
  await select(page, 49, 168);
  await page.keyboard.press('ControlOrMeta+.');
  await page.waitForTimeout(400);
  await shot(page, errs, '02-selection-menu', 'selected words and the selection menu (⌘.) — nothing has run');
  await page.click('#sel-popover button.route:has-text("Decompose")');
  await page.waitForSelector('#proposal-card');
  await page.waitForTimeout(300);
  await shot(page, errs, '03-proposal', 'the proposal: what leaves, to whom, the lane, the cost — nothing runs until Start');
  await page.click('#proposal-card .btn.primary');
  await page.waitForFunction(() => document.querySelector('#results-body .state.good') !== null, null, { timeout: 60000, polling: 200 });
  await page.waitForTimeout(500);
  await shot(page, errs, '04-both-open-result', 'both sides open with a complete result (mock lane)');
  await page.click('.apply-block > summary'); await page.waitForTimeout(300);
  await shot(page, errs, '05-apply-controls', 'the result’s application controls: Insert below / Replace, offered only while the target holds');
  await page.click('#tools-hide'); await page.waitForTimeout(300);
  await shot(page, errs, '06-results-only', 'Tools hidden, Results open (the header keeps its reopen control)');
  await page.click('#results-hide'); await page.waitForTimeout(300);
  await shot(page, errs, '07-both-hidden', 'both sides hidden; the header controls bring them back');
  await page.click('#tools-toggle'); await page.waitForTimeout(300);
  await shot(page, errs, '08-tools-only', 'Tools open, Results hidden');
  await page.click('#focus-btn'); await page.waitForTimeout(300);
  await shot(page, errs, '09-focus', 'Focus: sides and secondary controls out of sight; Exit focus restores the arrangement');
  await page.click('#exit-focus'); await page.waitForTimeout(300);
  await page.click('#results-toggle'); await page.waitForTimeout(300);
  // readers' feedback
  await select(page, 0, 49);
  await page.click('button[data-action="feedback.readers"]');
  await page.waitForSelector('#proposal-card');
  await page.click('#proposal-card .btn.primary');
  await page.waitForFunction(() => /3 of 3 readers/.test(document.getElementById('results-body').textContent), null, { timeout: 60000, polling: 300 }).catch(() => {});
  await page.waitForTimeout(400);
  await page.click('#results button[data-tab="feedback"]').catch(() => {});
  await page.waitForTimeout(400);
  await shot(page, errs, '10-readers-feedback', 'the three readers’ feedback, each on its own, no verdict');
  // the record's interrupted operations (unknown) and a failed investigation
  await page.click('#results button[data-tab="results"]').catch(() => {});
  await page.waitForTimeout(300);
  await page.evaluate(() => window.__work.results.open('job_seed_dead01', 'job'));
  await page.waitForTimeout(800);
  await shot(page, errs, '11-result-unknown', 'an operation a dead process left after its first dispatch intent: outcome unknown, by the record; Check status sends nothing');
  await page.click('a[data-page="investigate"]'); await page.waitForTimeout(800);
  await shot(page, errs, '12-investigate', 'Investigate: four instruments, readiness from the record, nothing contacted by opening');
  await page.fill('.card[data-producer="ethicalalt"] input.inv-subject', 'Boom Industries');
  await page.click('.card[data-producer="ethicalalt"] button:has-text("Start an investigation")');
  await page.waitForSelector('#proposal-card'); await page.waitForTimeout(300);
  await shot(page, errs, '13-investigation-proposal', 'an investigation proposed from the fixture producer: what leaves and to whom, before Start');
  await page.click('#proposal-card .btn.primary');
  await page.waitForFunction(() => /Sending to EthicalAlt/.test(document.getElementById('results-body').textContent), null, { timeout: 20000, polling: 100 }).catch(() => {});
  await page.click('a[data-page="work"]'); await page.waitForTimeout(200);
  await shot(page, errs, '14a-result-running', 'an investigation in flight: Running · Sending to EthicalAlt');
  await page.waitForFunction(() => /Failed/.test(document.getElementById('results-body').textContent) && !/Sending to EthicalAlt/.test(document.getElementById('results-body').textContent), null, { timeout: 60000, polling: 300 }).catch(() => {});
  await page.waitForTimeout(600);
  await shot(page, errs, '14-result-error', 'a failed investigation (the fixture producer answered 500): a known failure, named');
  // a partial run from the record
  await page.evaluate(t => window.__work.places.open('/?trace=' + t), PARTIAL_TRACE);
  await page.waitForTimeout(4000);
  await shot(page, errs, '15-result-partial', 'a partial workup from the record opened as a place (its own page: 2 components proposed, 1 analysed, partiality stated before any verdict)');
  // a source reading as a place inside the shell
  await page.click('a[data-page="work"]').catch(() => {});
  await page.evaluate(() => window.__work.places.open('/'));
  await page.waitForTimeout(2500);
  const frame = page.frameLocator('#place-frame');
  await frame.getByText('Read it', { exact: true }).first().click().catch(() => {});
  await page.waitForTimeout(2500);
  await shot(page, errs, '16-place-source-reading', 'a source (the fixture document) read on the previous interface, opened as a place inside the shell; the draft keeps its element');
  await page.evaluate(() => window.__work.places.open('/constitution#the-workspace-two-sides-that-act-only-on-a-press'));
  await page.waitForTimeout(1500);
  await shot(page, errs, '17-place-constitution-clause', 'the constitution opened at the workspace clause');
  await page.click('#place-back'); await page.waitForTimeout(300);
  await page.click('a[data-page="yourwork"]'); await page.waitForTimeout(900);
  await shot(page, errs, '18-yourwork', 'Your work: everything kept, from the index, with its population');
  await page.fill('#work-q', 'door'); await page.waitForTimeout(900);
  await shot(page, errs, '19-yourwork-search', 'a search of the record (local; the words go to the index only)');
  await page.click('a[data-page="help"]'); await page.waitForTimeout(400);
  await shot(page, errs, '20-help', 'Help, with the workspace’s rule and its door');
  await page.click('a[data-page="work"]'); await page.waitForTimeout(300);
  await page.click('#doc-menu-btn'); await page.waitForTimeout(200);
  await shot(page, errs, '21-doc-menu', 'the document menu: New, Rename, Duplicate, Open another, Versions, plain copy, exports, Archive');
  await page.keyboard.press('Escape');
  await page.click('#doc-menu-btn'); await page.click('button[data-doc="versions"]'); await page.waitForTimeout(600);
  await shot(page, errs, '22-versions', 'Versions: checkpoints and events; restore makes a new revision');
  await page.keyboard.press('ControlOrMeta+f'); await page.waitForTimeout(200);
  await page.keyboard.type('door'); await page.waitForTimeout(300);
  await shot(page, errs, '23-find', 'find and replace, with its count and population');
  await page.keyboard.press('Escape');
  await page.keyboard.press('ControlOrMeta+k'); await page.waitForTimeout(200);
  await page.keyboard.type('investigate Exemplar Holdings'); await page.waitForTimeout(400);
  await shot(page, errs, '24-ask', 'Ask: a plain request; the rest of it becomes the subject; Enter proposes, never runs');
  await page.keyboard.press('Escape');
  await ctx.close();

  // ---- other sizes and zooms ----
  for (const [name, vp, extra, note] of [
    ['30-1920x1080', { width: 1920, height: 1080 }, {}, '1920×1080, both sides open'],
    ['31-1280x800', { width: 1280, height: 800 }, {}, 'a smaller laptop, both sides open'],
    ['32-zoom125', { width: 1152, height: 720 }, { deviceScaleFactor: 1.25 }, '125% zoom (1440 px window)'],
    ['33-zoom150', { width: 960, height: 600 }, { deviceScaleFactor: 1.5 }, '150% zoom (1440 px window): measured narrow — Tools is a drawer, Results a section below'],
    ['34-zoom200', { width: 720, height: 450 }, { deviceScaleFactor: 2 }, '200% zoom (1440 px window)'],
    ['35-phone', { width: 390, height: 844 }, { deviceScaleFactor: 3, isMobile: ENGINE === 'chromium', hasTouch: true }, 'phone width'],
  ]) {
    const c = await mk(vp, extra);
    await c.page.goto(BASE + '/work'); await c.page.waitForSelector('.pm-editor'); await c.page.waitForTimeout(600);
    await draft(c.page);
    await c.page.evaluate(() => { window.__work.layout.setTools(true); window.__work.layout.setResults(true); });
    await c.page.waitForTimeout(400);
    await shot(c.page, c.errs, name, note);
    const narrow = await c.page.evaluate(() => document.getElementById('shell').dataset.narrow);
    if (narrow === 'yes') {
      await c.page.evaluate(() => window.__work.layout.setTools(false));
      await c.page.waitForTimeout(300);
      await shot(c.page, c.errs, name + '-results-below', 'narrow: Results as a section below the writing, with Back to writing');
      await c.page.evaluate(() => window.__work.layout.setTools(true));
      await c.page.waitForTimeout(300);
      await shot(c.page, c.errs, name + '-drawer', 'narrow: Tools as a drawer over the writing, with its own close');
    }
    await c.ctx.close();
  }
  await browser.close();
  fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(report, null, 1));
  console.log('written ' + OUT + '/report.json; overflow: ' + report.shots.filter(s => s.overflow).map(s => s.name).join(', ') + '; errors: ' + report.shots.filter(s => s.errors.length).map(s => s.name + ' ' + JSON.stringify(s.errors)).join(' | '));
})().catch(e => { console.error('CRASH', e); process.exit(1); });
