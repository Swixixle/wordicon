// The plain gloss is shown whenever it will be sent, correctable for this
// comparison, and safe across errors (his ruling, 2026-09-14, after an
// independent review of report 77). The panel used to validate one box —
// the meaning — while the concept's gloss rode along unshown; a gloss over
// the limit was refused by the route in the MEANING's name, and the refusal
// replaced the panel and everything typed into it.
//
// Five cases, each through the shipped panel in WebKit with /api/jobs
// mocked so the request that would leave is the thing under test:
//   1. an over-long gloss beside a short meaning — shown, counted, blocking;
//   2. a gloss that supplied the visible meaning because the meaning was
//      empty — shown once, sent once, as the meaning, and recorded as such;
//   3. the gloss shortened for this comparison — recorded as a narrowing;
//   4. the gloss deliberately left out — recorded as an omission;
//   5. a server error, then a retry with every typed field still there.
const { BASE, DIR, ok, finish, pairedContext } = require('./lib');
const { webkit } = require('playwright');
const fs = require('fs');
const path = require('path');
const IDS = JSON.parse(fs.readFileSync(path.join(DIR, 'related.json'), 'utf8'));
const LIMIT = 4000;

(async () => {
  const browser = await webkit.launch();
  const ctx = await pairedContext(browser, { viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(String(e)));
  // Which engine this actually is, asked of the browser rather than of the
  // import line. The first version of this journey said WebKit in its own
  // header and took lib's launcher, which is Chromium; the log now says.
  ok(browser.browserType().name() === 'webkit',
    'the gloss panel is measured in WebKit, the engine the owner writes in: ' + browser.browserType().name());
  const cookieHeader = fs.readFileSync(path.join(DIR, 'cookie'), 'utf8').trim() + '=' + fs.readFileSync(path.join(DIR, 'token'), 'utf8').trim();
  const FULL = await (await fetch(BASE + '/api/result/' + IDS.full, { headers: { Cookie: cookieHeader } })).json();

  const sent = [];
  let answer = () => ({ status: 200, json: { job_id: 'gloss-job', status: 'queued' } });
  await page.route('**/api/jobs', async route => {
    if (route.request().method() !== 'POST') return route.continue();
    let b = {}; try { b = JSON.parse(route.request().postData() || '{}'); } catch (e) {}
    sent.push(b);
    const a = answer(b);
    return route.fulfill({ status: a.status, json: a.json });
  });
  await page.route('**/api/jobs/gloss-job', route => route.fulfill({ json: { id: 'gloss-job', status: 'complete', result: FULL } }));
  await page.goto(BASE + '/'); await page.waitForTimeout(1500);

  const LONG_GLOSS = 'g'.repeat(LIMIT + 1);
  const open = (areaId, original) => page.evaluate(([a, o]) => {
    const area = document.getElementById('result-area');
    area.innerHTML = `<div id="${a}"></div>`;
    openRelatedPanel(a, o);
  }, [areaId, original]);
  const state = (id) => page.evaluate(i => {
    const g = document.getElementById(`rw-gloss-${i}`), m = document.getElementById(`rw-meaning-${i}`), go = document.getElementById(`rw-go-${i}`);
    const gn = document.getElementById(`rw-gloss-note-${i}`), mn = document.getElementById(`rw-meaning-note-${i}`);
    const omit = document.getElementById(`rw-gloss-omit-${i}`);
    return { glossBox: !!g, glossLen: g ? [...g.value].length : null, glossDisabled: !!(g && g.disabled),
             meaning: m ? m.value : null, goDisabled: !!(go && go.disabled), goText: go ? go.textContent : null,
             glossNote: gn && !gn.hidden ? gn.textContent.replace(/\s+/g, ' ') : '', meaningNote: mn && !mn.hidden ? mn.textContent.replace(/\s+/g, ' ') : '',
             omit: omit ? omit.textContent : null, fromGloss: !!document.getElementById(`rw-from-gloss-${i}`),
             panel: !!document.getElementById(`rw-panel-${i}`), status: (document.getElementById(`rw-run-${i}`) || {}).textContent || '' };
  }, id);

  // ---- 1. an over-long gloss beside a short meaning ------------------------
  await open('g1', { title: 'T', definition: 'A short stored meaning.', plain_gloss: LONG_GLOSS, concept_id: 'c1', entry: 'concept' });
  await page.waitForTimeout(500);
  let st = await state('g1');
  ok(st.glossBox && st.glossLen === LIMIT + 1, 'the gloss has its own box and holds the whole value: ' + st.glossLen);
  ok(st.goDisabled && /plain gloss/.test(st.goText || ''), 'the paid action is disabled and names the gloss as the field over: ' + st.goText);
  ok(new RegExp(`${LIMIT + 1}`).test(st.glossNote) && new RegExp(`${LIMIT}`).test(st.glossNote) && /keeps the gloss it has/.test(st.glossNote),
     'the note states the actual count, the limit, and that the idea keeps its gloss: ' + st.glossNote.slice(0, 120));
  ok(st.omit === 'Leave the gloss out of this comparison', 'a deliberate omission control is offered: ' + st.omit);
  ok(!st.meaningNote, 'the meaning, which is short, is not blamed');
  const before1 = sent.length;
  await page.evaluate(() => startRelatedFromPanel('g1')); await page.waitForTimeout(400);
  ok(sent.length === before1, 'nothing is sent while the gloss is over the limit');

  // ---- 2. the gloss supplied the visible meaning ----------------------------
  await open('g2', { title: 'T', definition: '', plain_gloss: LONG_GLOSS, concept_id: 'c2', entry: 'concept' });
  await page.waitForTimeout(500);
  st = await state('g2');
  ok(!st.glossBox && st.fromGloss && st.meaning === LONG_GLOSS, 'with no meaning of its own the gloss stands in as the meaning, shown once, with no second box');
  ok(st.goDisabled && /meaning/.test(st.goText || ''), 'and being over the limit it blocks as the meaning: ' + st.goText);
  await page.evaluate(() => { const m = document.getElementById('rw-meaning-g2'); m.value = 'A shorter visible meaning.'; rwPanelState('g2'); });
  st = await state('g2');
  ok(!st.goDisabled, 'shortening the standing-in gloss unblocks the pass');
  const before2 = sent.length;
  await page.evaluate(() => startRelatedFromPanel('g2')); await page.waitForTimeout(600);
  const r2 = sent[before2] || {};
  ok(sent.length === before2 + 1 && r2.original && r2.original.definition === 'A shorter visible meaning.' && r2.original.plain_gloss === '',
     'the request carries the shortened text once, as the meaning, and no hidden original gloss: ' + JSON.stringify({ d: (r2.original || {}).definition, g: [...String((r2.original || {}).plain_gloss)].length }));
  ok(r2.meaning_from_gloss === true && r2.meaning_narrowed === true && r2.plain_gloss_omitted === false && r2.plain_gloss_narrowed === false,
     'and records that the gloss stood in as the meaning and was narrowed: ' + JSON.stringify({ fg: r2.meaning_from_gloss, mn: r2.meaning_narrowed, go: r2.plain_gloss_omitted, gn: r2.plain_gloss_narrowed }));
  await page.waitForTimeout(1200);
  ok(!(await state('g2')).panel && /related words/i.test(await page.evaluate(() => document.getElementById('g2').innerText)), 'the result takes the area once the pass is in');

  // ---- 3. the gloss shortened for this comparison ---------------------------
  await open('g3', { title: 'T', definition: 'A short stored meaning.', plain_gloss: LONG_GLOSS, concept_id: 'c3', entry: 'concept' });
  await page.waitForTimeout(500);
  await page.evaluate(() => { const g = document.getElementById('rw-gloss-g3'); g.value = 'A shorter gloss, for this comparison.'; rwPanelState('g3'); });
  st = await state('g3');
  ok(!st.goDisabled && !st.glossNote, 'shortening the gloss unblocks the pass and clears the note');
  const before3 = sent.length;
  await page.evaluate(() => startRelatedFromPanel('g3')); await page.waitForTimeout(600);
  const r3 = sent[before3] || {};
  ok(r3.original && r3.original.definition === 'A short stored meaning.' && r3.original.plain_gloss === 'A shorter gloss, for this comparison.',
     'the request carries the meaning untouched and the gloss as shortened: ' + JSON.stringify({ d: (r3.original || {}).definition, g: (r3.original || {}).plain_gloss && [...r3.original.plain_gloss].length > 80 ? [...r3.original.plain_gloss].length + ' chars' : (r3.original || {}).plain_gloss }));
  ok(r3.plain_gloss_narrowed === true && r3.plain_gloss_omitted === false && r3.meaning_narrowed === false && r3.meaning_from_gloss === false,
     'and records the gloss as narrowed for this comparison only: ' + JSON.stringify({ gn: r3.plain_gloss_narrowed, go: r3.plain_gloss_omitted, mn: r3.meaning_narrowed }));

  // ---- 4. the gloss deliberately left out -----------------------------------
  await open('g4', { title: 'T', definition: 'A short stored meaning.', plain_gloss: LONG_GLOSS, concept_id: 'c4', entry: 'concept' });
  await page.waitForTimeout(500);
  await page.click('#rw-gloss-omit-g4'); await page.waitForTimeout(200);
  st = await state('g4');
  ok(st.glossDisabled && /left out of this comparison/.test(st.glossNote) && /keeps its gloss/.test(st.glossNote) && st.omit === 'Put the gloss back',
     'leaving the gloss out is said, reversible, and leaves the idea its gloss: ' + st.glossNote.slice(0, 100));
  ok(!st.goDisabled && st.glossLen === LIMIT + 1, 'the pass is unblocked and the gloss is still there, whole, in its box');
  await page.click('#rw-gloss-omit-g4'); await page.waitForTimeout(200);
  st = await state('g4');
  ok(!st.glossDisabled && st.goDisabled && st.omit === 'Leave the gloss out of this comparison', 'putting it back restores the block');
  await page.click('#rw-gloss-omit-g4'); await page.waitForTimeout(200);
  const before4 = sent.length;
  await page.evaluate(() => startRelatedFromPanel('g4')); await page.waitForTimeout(600);
  const r4 = sent[before4] || {};
  ok(r4.original && r4.original.definition === 'A short stored meaning.' && r4.original.plain_gloss === '',
     'the request carries the meaning and no gloss: ' + JSON.stringify({ d: (r4.original || {}).definition, g: (r4.original || {}).plain_gloss && [...r4.original.plain_gloss].length > 80 ? [...r4.original.plain_gloss].length + ' chars' : (r4.original || {}).plain_gloss }));
  ok(r4.plain_gloss_omitted === true && r4.plain_gloss_narrowed === false, 'and records the omission as a choice: ' + JSON.stringify({ go: r4.plain_gloss_omitted, gn: r4.plain_gloss_narrowed }));

  // ---- 5. a server error, then a retry with everything still there ---------
  await open('g5', { title: 'T', definition: 'A stored meaning to correct.', plain_gloss: 'A stored gloss to correct.', concept_id: 'c5', entry: 'concept' });
  await page.waitForTimeout(500);
  await page.evaluate(() => {
    const m = document.getElementById('rw-meaning-g5'), g = document.getElementById('rw-gloss-g5');
    m.value = 'A corrected meaning.\n\nWith a second paragraph.'; g.value = 'A corrected gloss.'; rwPanelState('g5');
    m.focus(); m.setSelectionRange(2, 11);       // a selection he was in the middle of
  });
  answer = () => ({ status: 500, json: { error: 'the server fell over on purpose' } });
  const before5 = sent.length;
  await page.evaluate(() => startRelatedFromPanel('g5')); await page.waitForTimeout(700);
  st = await state('g5');
  const sel = await page.evaluate(() => { const m = document.getElementById('rw-meaning-g5'); return m ? [m.selectionStart, m.selectionEnd, document.activeElement === m] : null; });
  ok(sent.length === before5 + 1 && st.panel && /fell over on purpose/.test(st.status),
     'the error is written beside the panel, and the panel is still there: ' + st.status.slice(0, 80));
  ok(st.meaning === 'A corrected meaning.\n\nWith a second paragraph.' && (await page.evaluate(() => document.getElementById('rw-gloss-g5').value)) === 'A corrected gloss.',
     'every typed field survived the error, line breaks included');
  ok(!!sel && sel[0] === 2 && sel[1] === 11 && sel[2], 'and so did the selection and the caret: ' + JSON.stringify(sel));
  ok(!st.goDisabled, 'the start button is live again for a retry');
  answer = () => ({ status: 200, json: { job_id: 'gloss-job', status: 'queued' } });
  await page.evaluate(() => startRelatedFromPanel('g5')); await page.waitForTimeout(700);
  const r5 = sent[before5 + 1] || {};
  ok(r5.original && r5.original.definition === 'A corrected meaning.\n\nWith a second paragraph.' && r5.original.plain_gloss === 'A corrected gloss.',
     'the retry sends the corrections exactly, without retyping: ' + JSON.stringify(r5.original));
  ok(r5.meaning_narrowed === false && r5.plain_gloss_narrowed === false, 'an ordinary correction of short fields is not marked as a narrowing');
  await page.waitForTimeout(1200);
  ok(!(await state('g5')).panel, 'and the result takes the area once the retry is in');

  ok(errs.length === 0, 'no page errors through the journey: ' + JSON.stringify(errs.slice(0, 2)));
  await browser.close();
  finish('gloss');
})();
