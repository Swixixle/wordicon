// Pass 2: Go deep from the room. In WebKit, because this is the room.
//
// The rules under test are all the owner's: a keystroke must not spend money;
// the panel says the scope, the lane and the cost and ONE press starts it;
// escape spends nothing; the run leaves the draft, the element, the caret,
// the undo stack and the scroll alone and keeps going if he leaves; the room
// splits only when the answer ARRIVES; and the expansion onto every
// component never starts by itself.
//
// The job endpoints are routed here rather than run: the journeys keep the
// model gateway poisoned, and what is under test is the client's whole path
// — confirm, submit, poll, arrive, split — not the pipeline behind it.
const { BASE, ok, finish } = require('./lib');
const { webkit } = require('playwright');
const fs = require('fs');
const path = require('path');

const DRAFT = [
  'The refusenik posture is the stance of one who exits a containing system.',
  '',
  'Escape and belonging remain simultaneously true, and the ledger does not close when you walk out.',
  '',
  'A third paragraph, kept short.',
].join('\n');
const PARA2 = 'Escape and belonging remain simultaneously true, and the ledger does not close when you walk out.';

function deepResult() {
  const group = (label, title) => ({
    label, gist: label + ' gist', neighbors: '', constraints: '', grounding: 'explicit',
    anchor: '', source_check: {}, background: '',
    result: { trace_id: 'trace_probe', summary: '', candidates: [
      { bff: { title, definition: 'a probe definition', bone: [], flesh: {}, }, friction: {} } ] },
  });
  return { trace_id: 'trace_probe', mode: 'deep', gesture: 'trial',
           attack: { verdict: 'keep', notes: [] },
           groups: [group('One', 'Probe Alpha'), group('Two', 'Probe Beta'), group('Three', 'Probe Gamma')] };
}

(async () => {
  const browser = await webkit.launch();
  const DIR = process.env.JOURNEY_DIR || '/tmp/anat';
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addCookies([{ name: fs.readFileSync(path.join(DIR, 'cookie'), 'utf8').trim(),
                          value: fs.readFileSync(path.join(DIR, 'token'), 'utf8').trim(),
                          domain: '127.0.0.1', path: '/' }]);
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(String(e)));

  // every non-GET the page makes, so "spends nothing" can be measured rather
  // than asserted
  const posts = [];
  page.on('request', r => { if (r.method() !== 'GET') posts.push(r.method() + ' ' + r.url().replace(BASE, '')); });

  await page.route('**/api/config', r => r.fulfill({ json: { gateway: 'probe-lane', model: 'probe-model-1', ok: true } }));
  let polls = 0;
  await page.route('**/api/jobs', r => r.request().method() === 'POST'
    ? r.fulfill({ json: { job_id: 'job_probe', status: 'queued' } }) : r.continue());
  await page.route('**/api/jobs/job_probe', r => {
    polls += 1;
    if (polls < 3) return r.fulfill({ json: { job_id: 'job_probe', mode: 'deep', status: 'running', progress: '[2/3] Two — forging…', result: null } });
    return r.fulfill({ json: { job_id: 'job_probe', mode: 'deep', status: 'complete', progress: 'done', input_text: PARA2, result: deepResult() } });
  });

  await page.goto(BASE + '/'); await page.waitForTimeout(1200);
  await page.evaluate(() => openWorkspace('write')); await page.waitForTimeout(400);
  await page.evaluate(d => { const ta = document.getElementById('compose-text'); ta.value = d; ta.dispatchEvent(new Event('input')); }, DRAFT);
  await page.waitForTimeout(700);
  ok(errs.length === 0, 'no page errors opening the room: ' + JSON.stringify(errs));

  // ---- the chords ------------------------------------------------------
  const chords = await page.evaluate(() => ({ draft: DEEP_CHORDS.draft.key, para: DEEP_CHORDS.paragraph.key }));
  ok(chords.draft === 'p' && chords.para === 'enter',
    'the chords are the ruled ones — and NOT Cmd+Shift+T, which is Reopen Last Closed Tab: ' + JSON.stringify(chords));

  // ---- a keystroke opens a question, and spends nothing -----------------
  const before = posts.length;
  await page.evaluate(() => { const ta = document.getElementById('compose-text'); ta.focus(); ta.setSelectionRange(90, 90); });
  await page.keyboard.press('ControlOrMeta+Shift+p');
  await page.waitForTimeout(500);
  const asked = await page.evaluate(() => {
    const el = document.getElementById('deep-ask');
    return { shown: el.style.display !== 'none', text: el.textContent.replace(/\s+/g, ' '),
             focused: document.activeElement ? document.activeElement.id : '' };
  });
  ok(asked.shown, 'the chord opens the question rather than starting the run');
  ok(posts.length === before, 'and it has spent nothing: ' + JSON.stringify(posts.slice(before)));
  ok(/Lane: probe-lane · model probe-model-1/.test(asked.text),
    'the panel names the lane and the model it would spend on: ' + asked.text.slice(0, 140));
  ok(/Model calls: 2 \+ about 4 for each idea it finds\./.test(asked.text)
     && /cannot be exact yet: counting the ideas in your text is what the first call is for/.test(asked.text),
    'the panel prices the run honestly, and says why it cannot be exact');
  ok(/keeps running if you close the room/.test(asked.text), 'the panel says the run outlives the room');
  ok(/on the whole draft/.test(asked.text), 'the whole-draft scope is named');

  // ---- escape cancels, spends nothing, and gives the caret back ---------
  await page.keyboard.press('Escape'); await page.waitForTimeout(300);
  const cancelled = await page.evaluate(() => ({
    shown: document.getElementById('deep-ask').style.display !== 'none',
    open: document.body.classList.contains('ws-open'),
    focus: document.activeElement ? document.activeElement.id : '',
    caret: document.getElementById('compose-text').selectionStart }));
  ok(!cancelled.shown && cancelled.open, 'escape closes the question and leaves the room open');
  ok(posts.length === before, 'cancelling spent nothing at all: ' + JSON.stringify(posts.slice(before)));
  ok(cancelled.focus === 'compose-text' && cancelled.caret === 90,
    'and the caret goes back exactly where it was: ' + JSON.stringify(cancelled));

  // ---- the paragraph is what lies between blank lines -------------------
  await page.keyboard.press('ControlOrMeta+Shift+Enter'); await page.waitForTimeout(400);
  const para = await page.evaluate(() => ({ what: DEEP_ASK.what, text: DEEP_ASK.text, kind: DEEP_ASK.kind }));
  ok(para.kind === 'paragraph' && para.text === 'Escape and belonging remain simultaneously true, and the ledger does not close when you walk out.',
    'the paragraph is exactly the text between the blank lines around the caret: ' + JSON.stringify(para.text));
  await page.keyboard.press('Escape'); await page.waitForTimeout(200);

  // ---- a selection is OFFERED, never silently widened -------------------
  await page.evaluate(() => { const ta = document.getElementById('compose-text'); ta.focus(); ta.setSelectionRange(75, 96); });
  await page.keyboard.press('ControlOrMeta+Shift+Enter'); await page.waitForTimeout(400);
  const sel = await page.evaluate(() => ({ kind: DEEP_ASK.kind, text: DEEP_ASK.text,
    panel: document.getElementById('deep-ask').textContent.replace(/\s+/g, ' ') }));
  ok(sel.kind === 'selection' && sel.text.length <= 21 && /the text you have selected/.test(sel.panel),
    'with a selection the paragraph command offers the selection, and says so: ' + JSON.stringify(sel.text));
  await page.keyboard.press('Escape'); await page.waitForTimeout(200);

  // ---- one press starts it; the room is untouched while it runs ---------
  await page.evaluate(() => { const ta = document.getElementById('compose-text'); ta.focus(); ta.setSelectionRange(120, 128); ta.dataset.deepProbe = 'live-1'; ta.scrollTop = 0; });
  const roomBefore = await page.evaluate(() => { const ta = document.getElementById('compose-text'); return { v: ta.value, s: ta.selectionStart, e: ta.selectionEnd, mode: document.body.className }; });
  await page.keyboard.press('ControlOrMeta+Shift+p'); await page.waitForTimeout(400);
  await page.click('#deep-ask-go'); await page.waitForTimeout(900);
  const started = posts.filter(x => x === 'POST /api/jobs');
  ok(started.length === 1, 'one press starts exactly one run, with no second form: ' + JSON.stringify(posts.slice(before)));
  const running = await page.evaluate(() => {
    const ta = document.getElementById('compose-text'), line = document.getElementById('room-run');
    return { probe: ta.dataset.deepProbe || '', v: ta.value, s: ta.selectionStart, e: ta.selectionEnd,
             focus: document.activeElement ? document.activeElement.id : '',
             line: line.hidden ? '' : line.textContent, mode: document.body.className,
             pointer: getComputedStyle(line).pointerEvents };
  });
  ok(running.probe === 'live-1' && running.v === roomBefore.v && running.s === roomBefore.s && running.e === roomBefore.e,
    'the run leaves the element, the draft and the caret exactly as they were: ' + JSON.stringify([roomBefore.s, roomBefore.e, running.s, running.e]));
  ok(running.focus === 'compose-text', 'and it does not take the focus: ' + running.focus);
  ok(/3 ideas found, about 14 model calls/.test(running.line),
    'the estimate becomes an exact count the moment the split comes back: ' + JSON.stringify(running.line));
  ok(running.pointer === 'none', 'the running line cannot be clicked and is never in the way');
  ok(/ws-write/.test(running.mode) && !/ws-split/.test(running.mode),
    'the room has NOT split while the run is still going: ' + running.mode);

  // ---- it splits when the answer arrives, not before --------------------
  await page.waitForTimeout(6000);
  const arrived = await page.evaluate(() => {
    const ta = document.getElementById('compose-text');
    return { mode: document.body.className, probe: ta.dataset.deepProbe || '', v: ta.value,
             s: ta.selectionStart, e: ta.selectionEnd,
             focus: document.activeElement ? document.activeElement.id : '',
             line: document.getElementById('room-run').hidden,
             titles: Array.from(document.querySelectorAll('#result-area .result-title')).map(x => x.textContent) };
  });
  ok(/ws-split/.test(arrived.mode), 'the room splits when the answer arrives: ' + arrived.mode);
  ok(arrived.titles.length >= 3, 'and the workup is beside the writing: ' + JSON.stringify(arrived.titles));
  ok(arrived.probe === 'live-1' && arrived.v === roomBefore.v && arrived.s === roomBefore.s && arrived.e === roomBefore.e,
    'through all of which the room is the same element with the same draft and caret');
  ok(arrived.focus === 'compose-text', 'the caret is still in the draft when the answer lands');
  ok(arrived.line, 'the running line goes quiet once the answer is here');

  // ---- the expansion is priced from what came back, and runs nothing ----
  const exp = await page.evaluate(() => {
    const c = document.getElementById('deep-expansion');
    if (!c) return null;
    const b = c.querySelector('button');
    return { text: c.textContent.replace(/\s+/g, ' '), disabled: b.disabled, aria: b.getAttribute('aria-disabled') };
  });
  ok(exp && /3 components × 3 instruments = up to 9 more model calls/.test(exp.text),
    'the expansion is counted from the components that actually came back: ' + (exp ? exp.text.slice(0, 120) : 'missing'));
  const doorLook = await page.evaluate(() => {
    const b = document.getElementById('deep-expansion-door');
    if (!b) return null;
    const cs = getComputedStyle(b);
    return { cls: b.className, border: cs.borderTopStyle, cursor: cs.cursor,
             status: (b.querySelector('.dest-status') || {}).textContent || '' };
  });
  ok(exp.disabled && exp.aria === 'true' && /not built —/.test(exp.text),
    'and it is a door with its price on it, not a button that fires nine calls');
  ok(doorLook && /\bunbuilt\b/.test(doorLook.cls) && doorLook.border === 'dashed'
     && doorLook.cursor === 'not-allowed' && /sprout/.test(doorLook.status),
    'it renders as this page\'s unbuilt door — dashed, inert, naming its own reason — not as a '
    + 'greyed-out button that reads as broken: ' + JSON.stringify(doorLook));
  const afterExp = posts.length;
  await page.evaluate(() => { const b = document.querySelector('#deep-expansion button'); b.click(); });
  await page.waitForTimeout(400);
  ok(posts.length === afterExp, 'clicking it runs nothing: ' + JSON.stringify(posts.slice(afterExp)));

  // ---- undo still reaches back past everything -------------------------
  await page.click('#compose-text');
  await page.evaluate(() => { const ta = document.getElementById('compose-text'); ta.setSelectionRange(ta.value.length, ta.value.length); });
  await page.keyboard.type(' and one more clause', { delay: 0 });
  await page.waitForTimeout(200);
  const typed = await page.evaluate(() => document.getElementById('compose-text').value);
  await page.keyboard.press('ControlOrMeta+z'); await page.waitForTimeout(250);
  const undone = await page.evaluate(() => document.getElementById('compose-text').value);
  ok(undone !== typed && undone.length < typed.length,
    'the undo stack survived the whole invocation: ' + JSON.stringify(undone.slice(-40)));

  ok(errs.length === 0, 'no page errors across the deep journey: ' + JSON.stringify(errs));
  await ctx.close();
  await browser.close();
  finish('deep');
})().catch(e => { console.log('FAIL journey crashed: ' + (e && e.stack || e)); process.exit(1); });
