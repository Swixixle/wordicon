// Defect 4: a workup that finishes while you are not looking at it.
//
// The owner's report was exact and it is the whole specification: "It didn't
// automatically pull up the search I looked for earlier. I had to wait for it
// to load and then click back out and in." An answer that needs you to leave
// the room and come back before the page notices it is an answer the page
// lost and then found by accident.
//
// So the route is recorded when the run starts — job id, which surface asked,
// what scope, where the answer belongs, whether it has been shown — and every
// origin is walked here rather than one guessed path: the room open, the room
// closed, a place, a full reload, a run started from the page instead of the
// room, a failure, and a server that no longer has the job at all.
//
// WebKit, because this is the room. The job endpoints are routed rather than
// run: what is under test is the client's whole path.
const { BASE, ok, finish } = require('./lib');
const { webkit } = require('playwright');
const fs = require('fs');
const path = require('path');

const DRAFT = [
  'The refusenik posture is the stance of one who exits a containing system.',
  '',
  'Escape and belonging remain simultaneously true.',
].join('\n');

function deepResult() {
  const group = (label, title) => ({
    label, gist: label + ' gist', neighbors: '', constraints: '', grounding: 'explicit',
    anchor: '', source_check: {}, background: '',
    result: { trace_id: 'trace_resume', summary: '', candidates: [
      { bff: { title, definition: 'a probe definition', bone: [], flesh: {} }, friction: {} } ] },
  });
  return { trace_id: 'trace_resume', mode: 'deep', gesture: 'trial',
           attack: { verdict: 'keep', notes: [] },
           groups: [group('One', 'Resume Alpha'), group('Two', 'Resume Beta')] };
}

// One browser context per scenario, so a reload is a real reload and the
// stored route is the only thing that crosses.
async function fresh(browser, DIR) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addCookies([{ name: fs.readFileSync(path.join(DIR, 'cookie'), 'utf8').trim(),
                          value: fs.readFileSync(path.join(DIR, 'token'), 'utf8').trim(),
                          domain: '127.0.0.1', path: '/' }]);
  return ctx;
}

// state: 'slow' keeps it running for as long as the scenario needs;
// 'done' answers complete; 'fail' answers failed; 'gone' 404s the way a
// restarted server does.
async function wire(page, state, posts) {
  page.on('request', r => { if (r.method() !== 'GET') posts.push(r.method() + ' ' + r.url().replace(BASE, '')); });
  await page.route('**/api/config', r => r.fulfill({ json: { gateway: 'probe-lane', model: 'probe-model-1', ok: true } }));
  await page.route('**/api/inflight', r => r.fulfill({ json: { running: [] } }));
  await page.route('**/api/jobs', r => r.request().method() === 'POST'
    ? r.fulfill({ json: { job_id: 'job_resume', status: 'queued' } }) : r.continue());
  await page.route('**/api/jobs/job_resume', r => {
    const s = state();
    if (s === 'gone') return r.fulfill({ status: 404, json: { error: 'no job with that id' } });
    if (s === 'fail') return r.fulfill({ json: { id: 'job_resume', mode: 'deep', status: 'failed',
                                                error: 'RateLimitError: 429 too many requests' } });
    if (s === 'done') return r.fulfill({ json: { id: 'job_resume', mode: 'deep', status: 'complete',
                                                progress: 'done', input_text: DRAFT, result: deepResult() } });
    return r.fulfill({ json: { id: 'job_resume', mode: 'deep', status: 'running',
                               progress: '[1/2] One — forging…', result: null } });
  });
}

async function startFromRoom(page) {
  await page.goto(BASE + '/'); await page.waitForTimeout(1000);
  await page.evaluate(() => openWorkspace('write')); await page.waitForTimeout(300);
  await page.evaluate(d => { const ta = document.getElementById('compose-text'); ta.value = d; ta.dispatchEvent(new Event('input')); }, DRAFT);
  await page.waitForTimeout(400);
  await page.keyboard.press('ControlOrMeta+Shift+p'); await page.waitForTimeout(400);
  await page.click('#deep-ask-go'); await page.waitForTimeout(700);
}

(async () => {
  const browser = await webkit.launch();
  const DIR = process.env.JOURNEY_DIR || '/tmp/anat';
  const errs = [];

  // ---- 1. the route is identity, and it is written before the first poll --
  {
    const ctx = await fresh(browser, DIR); const page = await ctx.newPage();
    page.on('pageerror', e => errs.push(String(e)));
    let st = 'slow'; const posts = [];
    await wire(page, () => st, posts);
    await startFromRoom(page);
    const route = await page.evaluate(() => {
      const raw = localStorage.getItem('nikodemus.run.route.v1');
      return { raw, run: JSON.parse(JSON.stringify(RUN)) };
    });
    ok(route.run.job === 'job_resume' && route.run.surface === 'room' && route.run.scope === 'draft'
       && route.run.dest === 'beside' && route.run.revealed === false,
      'the run records which surface asked, for what, and where the answer belongs: ' + JSON.stringify(route.run));
    ok(route.raw && !/refusenik|containing system|Escape and belonging/.test(route.raw),
      'and the stored route carries no word of the draft — identity only: ' + JSON.stringify(route.raw));

    // ---- 2. a full reload finds the running job again --------------------
    await page.reload(); await page.waitForTimeout(1600);
    const after = await page.evaluate(() => ({
      job: RUN.job, watching: WATCHING,
      line: document.getElementById('room-run').hidden ? '' : document.getElementById('room-run').textContent }));
    ok(after.job === 'job_resume' && after.watching === 'job_resume',
      'a full reload picks the running job back up from the stored route: ' + JSON.stringify(after));
    ok(/working ·/.test(after.line),
      'and the room says it is working rather than sitting on a frozen line: ' + JSON.stringify(after.line));

    // ---- 3. it completes while he is NOT in the room ---------------------
    st = 'done';
    await page.waitForTimeout(3200);
    const away = await page.evaluate(() => ({
      open: document.body.classList.contains('ws-open'),
      line: document.getElementById('room-run').hidden ? '' : document.getElementById('room-run').textContent,
      btn: !!document.querySelector('#room-run button') }));
    ok(!away.open, 'after the reload he is on the page, not in the room: ' + JSON.stringify(away.open));
    ok(/your workup is ready/.test(away.line) && away.btn,
      'a workup that lands while he is away waits and offers itself: ' + JSON.stringify(away.line));

    // ---- 4. entering the room shows it — without leaving and re-entering -
    await page.evaluate(() => document.querySelector('#room-run button').click());
    await page.waitForTimeout(700);
    const opened = await page.evaluate(() => ({
      mode: document.body.className,
      titles: Array.from(document.querySelectorAll('#result-area .result-title')).map(x => x.textContent),
      line: document.getElementById('room-run').hidden,
      left: localStorage.getItem('nikodemus.run.route.v1') }));
    ok(/ws-split/.test(opened.mode) && opened.titles.length >= 2,
      'opening it puts the workup beside the writing: ' + JSON.stringify([opened.mode, opened.titles]));
    ok(opened.line && !opened.left,
      'and the route is spent once it has been shown, so it is never offered twice');
    await ctx.close();
  }

  // ---- 5. a run started from the page never takes the draft -------------
  {
    const ctx = await fresh(browser, DIR); const page = await ctx.newPage();
    page.on('pageerror', e => errs.push(String(e)));
    let st = 'slow'; const posts = [];
    await wire(page, () => st, posts);
    await page.goto(BASE + '/'); await page.waitForTimeout(1000);
    await page.evaluate(() => { submitRun('deep', 'a passage typed on the page', null, 'trial'); });
    await page.waitForTimeout(600);
    const home = await page.evaluate(() => JSON.parse(JSON.stringify(RUN)));
    ok(home.surface === 'home' && home.dest === 'work',
      'a run submitted from the page belongs to the page: ' + JSON.stringify(home));
    // now open the room, with a draft in it, and let the page's run finish
    await page.evaluate(() => openWorkspace('write')); await page.waitForTimeout(300);
    await page.evaluate(d => { const ta = document.getElementById('compose-text'); ta.value = d; ta.dispatchEvent(new Event('input')); ta.setSelectionRange(4, 9); }, DRAFT);
    const before = await page.evaluate(() => { const ta = document.getElementById('compose-text'); return { v: ta.value, s: ta.selectionStart, e: ta.selectionEnd, mode: document.body.className }; });
    st = 'done';
    await page.waitForTimeout(3400);
    const land = await page.evaluate(() => { const ta = document.getElementById('compose-text');
      return { v: ta.value, s: ta.selectionStart, e: ta.selectionEnd, mode: document.body.className,
               line: document.getElementById('room-run').hidden ? '' : document.getElementById('room-run').textContent,
               btn: !!document.querySelector('#room-run button') }; });
    ok(land.v === before.v && land.s === before.s && land.e === before.e,
      'a page run landing while the room is open leaves the draft and the caret alone');
    ok(!/ws-split/.test(land.mode),
      'it does not hijack the writing room into a split: ' + land.mode);
    ok(/started on the page has finished/.test(land.line) && land.btn,
      'it says so and offers to open beside the writing: ' + JSON.stringify(land.line));
    await ctx.close();
  }

  // ---- 6. a failure names its class, in the room ------------------------
  {
    const ctx = await fresh(browser, DIR); const page = await ctx.newPage();
    page.on('pageerror', e => errs.push(String(e)));
    let st = 'slow'; const posts = [];
    await wire(page, () => st, posts);
    await startFromRoom(page);
    st = 'fail';
    await page.waitForTimeout(3200);
    const failed = await page.evaluate(() => ({
      line: document.getElementById('room-run').hidden ? '' : document.getElementById('room-run').textContent,
      job: RUN.job, left: localStorage.getItem('nikodemus.run.route.v1') }));
    ok(/the workup failed — the provider rate-limited the run/.test(failed.line),
      'a failure names its real class rather than pointing at a page he may not be reading: '
      + JSON.stringify(failed.line));
    ok(!failed.job && !failed.left, 'and the route is cleared, so nothing waits on a dead run');
    await ctx.close();
  }

  // ---- 7. a job the server no longer has says so -----------------------
  {
    const ctx = await fresh(browser, DIR); const page = await ctx.newPage();
    page.on('pageerror', e => errs.push(String(e)));
    let st = 'slow'; const posts = [];
    await wire(page, () => st, posts);
    await startFromRoom(page);
    st = 'gone';
    await page.reload(); await page.waitForTimeout(1800);
    const gone = await page.evaluate(() => ({
      line: document.getElementById('room-run').hidden ? '' : document.getElementById('room-run').textContent,
      job: RUN.job }));
    ok(/cannot be resumed — the server no longer has it/.test(gone.line),
      'a job the server has lost is stated, not left as a frozen line: ' + JSON.stringify(gone.line));
    ok(!gone.job, 'and its route is dropped rather than retried forever');
    await ctx.close();
  }

  // ---- 8. completion while he is typing does not touch what he types ----
  {
    const ctx = await fresh(browser, DIR); const page = await ctx.newPage();
    page.on('pageerror', e => errs.push(String(e)));
    let st = 'slow'; const posts = [];
    await wire(page, () => st, posts);
    await startFromRoom(page);
    await page.click('#compose-text');
    await page.evaluate(() => { const ta = document.getElementById('compose-text'); ta.setSelectionRange(ta.value.length, ta.value.length); });
    st = 'done';
    await page.keyboard.type(' still typing while it lands', { delay: 12 });
    await page.waitForTimeout(3400);
    const typed = await page.evaluate(() => { const ta = document.getElementById('compose-text');
      return { v: ta.value, at: ta.selectionStart, focus: document.activeElement ? document.activeElement.id : '',
               mode: document.body.className }; });
    ok(/ still typing while it lands$/.test(typed.v),
      'every character typed while the answer was arriving is in the draft: ' + JSON.stringify(typed.v.slice(-40)));
    ok(typed.focus === 'compose-text' && typed.at === typed.v.length,
      'the caret is still his, at the end of what he typed: ' + JSON.stringify([typed.focus, typed.at, typed.v.length]));
    ok(/ws-split/.test(typed.mode), 'and the answer came to sit beside him: ' + typed.mode);
    await ctx.close();
  }

  ok(errs.length === 0, 'no page errors across every origin: ' + JSON.stringify(errs.slice(0, 3)));
  await browser.close();
  finish('resume');
})();
