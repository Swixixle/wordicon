// Block 125: the readers, from the room. In WebKit, because this is the room.
//
// The rules under test are the owner's: the readers' control opens a
// question and spends nothing; the panel names each reader, its lane and the
// call count and ONE press starts it; escape spends nothing; the reading
// leaves the draft, the element, the caret and the undo stack alone; the
// room splits when the FIRST reader answers; three readers answer into three
// separate cards and nothing merges them; a quoted span that is not in the
// text is marked, never dropped; a reader that failed is shown failed and not
// as agreement; an observation carries back into the same revision notes;
// a follow-up goes to one reader; the blind reader's discussion is labelled a
// consultation and her first reading stands; an earlier reading reopens
// whole after the draft changes; "remember this" keeps the observation with
// its source.
//
// The server is the real scratch server with the readers' offline stand-ins
// installed (serve.py) — the whole path runs: snapshot, three dispatches,
// quotation check, carry, follow-up, consultation. Nothing reaches a
// provider; any request off the scratch origin fails the journey.
const { BASE, ok, finish } = require('./lib');
const { webkit } = require('playwright');
const fs = require('fs');
const path = require('path');

const DRAFT = [
  'The lantern in the hallway had two settings and the house had learned to read them.',
  '',
  'When it burned low the rooms agreed to be smaller. Nobody had decided this. It was the kind of arrangement that forms between a machine and the people who stop noticing it.',
  '',
  'A third paragraph, kept short.',
].join('\n');
const PARA2 = 'When it burned low the rooms agreed to be smaller. Nobody had decided this. It was the kind of arrangement that forms between a machine and the people who stop noticing it.';

async function waitFor(page, fn, ms) {
  const until = Date.now() + (ms || 8000);
  while (Date.now() < until) {
    if (await page.evaluate(fn)) return true;
    await page.waitForTimeout(150);
  }
  return false;
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
  const posts = [];
  page.on('request', r => { if (r.method() !== 'GET') posts.push(r.method() + ' ' + r.url().replace(BASE, '')); });
  const offOrigin = [];
  page.on('request', r => { const u = r.url(); if (!u.startsWith(BASE) && !u.startsWith('data:') && !u.startsWith('blob:') && !u.startsWith('about:')) offOrigin.push(u); });

  await page.goto(BASE + '/'); await page.waitForTimeout(1200);
  await page.evaluate(() => openWorkspace('write')); await page.waitForTimeout(400);
  await page.evaluate(d => { const ta = document.getElementById('compose-text'); ta.value = d; ta.dispatchEvent(new Event('input')); }, DRAFT);
  await page.waitForTimeout(600);
  ok(errs.length === 0, 'no page errors opening the room: ' + JSON.stringify(errs));

  // ---- the control opens a question, and spends nothing ---------------
  const before = posts.length;
  await page.evaluate(() => { const ta = document.getElementById('compose-text'); ta.focus(); ta.setSelectionRange(120, 120); ta.dataset.moiraProbe = 'live-1'; });
  // the door is in the panel behind Aa, beside Go deep — the bar did not grow
  const bar = await page.evaluate(() => document.querySelectorAll('#ws-bar > button:not(#carry-ctl)').length);
  ok(bar === 7, "the room's bar did not grow a button for the readers: " + bar);
  await page.evaluate(() => toggleWriteStyle()); await page.waitForTimeout(400);
  const door = await page.evaluate(() => { const b = document.getElementById('moira-door'); return { there: !!b, label: b ? b.parentElement.previousElementSibling.textContent : '' }; });
  ok(door.there && /^Readers — three readers/.test(door.label), 'with no Phase 0 ruling recorded the door behind Aa claims no faculty name: ' + door.label);
  await page.click('#moira-door'); await page.waitForTimeout(900);
  const asked = await page.evaluate(() => {
    const el = document.getElementById('moira-ask');
    return { shown: el.style.display !== 'none', text: el.textContent.replace(/\s+/g, ' ') };
  });
  ok(asked.shown, "the readers' control opens a question rather than starting a reading");
  ok(posts.length === before, 'and it has spent nothing: ' + JSON.stringify(posts.slice(before)));
  ok(/Clotho — reads for what is alive/.test(asked.text) && /Lachesis — reads for what can bear weight/.test(asked.text)
     && /Atropos — reads for what reached a stranger/.test(asked.text),
    'the panel names each reader and what it reads for');
  ok(/the mock lane \(no real calls\)/.test(asked.text) && /Model calls: 3, one per reader/.test(asked.text),
    'the panel names the lane and the call count before a press: ' + asked.text.slice(0, 160));
  ok(/same model as the others — a weaker independence test/.test(asked.text),
    "the blind reader's lane says what it means for independence");
  ok(/the blind reader receives nothing else/.test(asked.text), 'the panel says what each reader receives');
  ok(/on this paragraph — \d+ words/.test(asked.text) && asked.text.includes('When it burned low'),
    'the scope is the paragraph the caret is in, and it is shown');

  // ---- escape closes it, spends nothing, gives the caret back -----------
  await page.keyboard.press('Escape'); await page.waitForTimeout(300);
  const cancelled = await page.evaluate(() => ({
    shown: document.getElementById('moira-ask').style.display !== 'none',
    open: document.body.classList.contains('ws-open'),
    focus: document.activeElement ? document.activeElement.id : '',
    caret: document.getElementById('compose-text').selectionStart }));
  ok(!cancelled.shown && cancelled.open && cancelled.focus === 'compose-text' && cancelled.caret === 120,
    "escape closes the readers' panel, leaves the room open and gives the caret back: " + JSON.stringify(cancelled));
  ok(posts.length === before, 'cancelling spent nothing at all');

  // ---- one press starts it; the room is untouched; it splits on the first answer
  const roomBefore = await page.evaluate(() => { const ta = document.getElementById('compose-text'); return { v: ta.value, s: ta.selectionStart, e: ta.selectionEnd }; });
  await page.evaluate(() => askReaders('paragraph')); await page.waitForTimeout(700);
  await page.click('#moira-go'); await page.waitForTimeout(300);
  const started = posts.filter(x => x === 'POST /api/moira/readings');
  ok(started.length === 1, 'one press starts exactly one reading: ' + JSON.stringify(posts.slice(before)));
  const split = await waitFor(page, () => document.body.classList.contains('ws-split') && document.querySelectorAll('#result-area .reader-card').length >= 1, 10000);
  ok(split, 'the room splits when the first reader answers');
  await waitFor(page, () => document.querySelectorAll('#result-area .reader-card .seg').length >= 6, 10000);
  const arrived = await page.evaluate(() => {
    const ta = document.getElementById('compose-text');
    return { probe: ta.dataset.moiraProbe || '', v: ta.value, s: ta.selectionStart, e: ta.selectionEnd,
             focus: document.activeElement ? document.activeElement.id : '',
             who: Array.from(document.querySelectorAll('#result-area .reader-card .who')).map(x => x.textContent),
             quotes: Array.from(document.querySelectorAll('#result-area .quote')).map(x => x.textContent),
             head: (document.querySelector('#result-area .card') || {}).textContent || '',
             verdictWords: /verdict|score|agree/i.test((document.getElementById('result-area') || {}).textContent || '') };
  });
  ok(arrived.probe === 'live-1' && arrived.v === roomBefore.v && arrived.s === roomBefore.s && arrived.e === roomBefore.e,
    'the reading leaves the element, the draft and the caret exactly as they were');
  ok(arrived.focus === 'compose-text', 'and the caret is still in the draft when the answers land');
  ok(arrived.who.length === 3 && /Clotho/.test(arrived.who[0]) && /Lachesis/.test(arrived.who[1]) && /Atropos/.test(arrived.who[2]),
    'three readers answer into three separate cards: ' + JSON.stringify(arrived.who));
  ok(/no verdict or score exists/.test(arrived.head) && /not a finding about your writing/.test(arrived.head),
    'the head says nothing combines them and a silent reader is not a finding');
  ok(arrived.quotes.includes('QUOTED WORDS NOT IN YOUR TEXT') && arrived.quotes.includes('quoted exactly')
     && arrived.quotes.includes('quoted · punctuation normalized'),
    'a quoted span that is not in the text is marked, not dropped — beside spans quoted exactly and with punctuation normalized');
  const blind = await page.evaluate(() => Array.from(document.querySelectorAll('#result-area .reader-card')).map(c => c.textContent).find(t => /Atropos/.test(t)) || '');
  ok(/blind: the instructions and the text, nothing else/.test(blind), "the blind reader's card says what she received");

  // ---- carry back: the same revision notes ------------------------------
  const carriesBefore = posts.filter(x => /^POST \/api\/carry$/.test(x)).length;
  await page.click('#result-area .reader-card .carry-btn'); await page.waitForTimeout(900);
  const ctl = await page.evaluate(() => (document.getElementById('carry-ctl') || {}).textContent || '');
  const carriesAfter = posts.filter(x => /^POST \/api\/carry$/.test(x)).length;
  ok(carriesAfter === carriesBefore + 1 && /Revision notes · \d+/.test(ctl),
    "carrying an observation back lands in the revision notes: " + ctl + ' · carries posted ' + (carriesAfter - carriesBefore));
  await page.evaluate(() => openCarryTray()); await page.waitForTimeout(500);
  const tray = await page.evaluate(() => document.getElementById('carry-tray').textContent.replace(/\s+/g, ' '));
  ok(/observation — advisory, one reader/.test(tray) && /UNVERIFIED/.test(tray),
    "the carried observation keeps its standing — one reader's, advisory, unverified: " + tray.slice(0, 160));
  await page.evaluate(() => toggleCarryTray());

  // ---- a follow-up goes to one reader; the blind reader's is a consultation
  await page.fill('#result-area input[id^="ask-clotho-"]', 'why that line?');
  await page.evaluate(() => { const c = Array.from(document.querySelectorAll('#result-area .reader-card')).find(x => /Clotho/.test(x.textContent)); c.querySelector('.ask button').click(); });
  await waitFor(page, () => document.querySelectorAll('#result-area .thread').length >= 1, 8000);
  const th1 = await page.evaluate(() => Array.from(document.querySelectorAll('#result-area .reader-card')).map(c => ({ who: c.querySelector('.who').textContent, threads: c.querySelectorAll('.thread').length })));
  ok(th1.find(x => /Clotho/.test(x.who)).threads === 1 && th1.filter(x => !/Clotho/.test(x.who)).every(x => x.threads === 0),
    'a follow-up goes to one reader only: ' + JSON.stringify(th1));
  await page.fill('#result-area input[id^="ask-atropos-"]', 'it was about grief');
  await page.evaluate(() => { const c = Array.from(document.querySelectorAll('#result-area .reader-card')).find(x => /Atropos/.test(x.textContent)); c.querySelector('.ask button').click(); });
  await waitFor(page, () => document.querySelectorAll('#result-area .thread').length >= 2, 8000);
  const cons = await page.evaluate(() => { const c = Array.from(document.querySelectorAll('#result-area .reader-card')).find(x => /Atropos/.test(x.textContent)); return { thread: (c.querySelector('.thread .q') || {}).textContent || '', segs: c.querySelectorAll('.seg').length }; });
  ok(/Informed consultation — the blind reading above stands unchanged/.test(cons.thread) && cons.segs >= 3,
    "the blind reader's discussion is labelled a consultation and her first reading stands: " + cons.thread);

  // ---- remember this: kept with its source ------------------------------
  await page.evaluate(() => { const c = Array.from(document.querySelectorAll('#result-area .reader-card')).find(x => /Clotho/.test(x.textContent)); Array.from(c.querySelectorAll('.seg button')).find(b => /remember/.test(b.textContent)).click(); });
  await page.waitForTimeout(700);
  await page.evaluate(() => askReaders('readings')); await page.waitForTimeout(400);
  await page.evaluate(() => moiraTab('notebook')); await page.waitForTimeout(700);
  const nb = await page.evaluate(() => document.getElementById('moira-ask').textContent.replace(/\s+/g, ' '));
  ok(/from Clotho's reading/.test(nb) && /for Clotho and Lachesis/.test(nb) && /The blind reader never receives it/.test(nb),
    '"remember this" keeps the observation with its source, for the two readers that may see it: ' + nb.slice(0, 200));
  await page.keyboard.press('Escape'); await page.waitForTimeout(200);

  // ---- a reader that fails is shown failed, not as agreement ------------
  await page.evaluate(d => { const ta = document.getElementById('compose-text'); ta.value = d + ' FAIL LACHESIS'; ta.dispatchEvent(new Event('input')); ta.focus(); ta.setSelectionRange(ta.value.length - 3, ta.value.length - 3); }, DRAFT);
  await page.waitForTimeout(300);
  await page.evaluate(() => askReaders('draft')); await page.waitForTimeout(500);
  await page.evaluate(() => moiraPickScope('draft')); await page.waitForTimeout(400);
  await page.click('#moira-go');
  await waitFor(page, () => /this one did not answer/.test((document.getElementById('result-area') || {}).textContent || '') && document.querySelectorAll('#result-area .reader-card .seg').length >= 6, 12000);
  const failed = await page.evaluate(() => {
    const cards = Array.from(document.querySelectorAll('#result-area .reader-card')).map(c => c.textContent.replace(/\s+/g, ' '));
    return { lach: cards.find(t => /Lachesis/.test(t)) || '', others: cards.filter(t => !/Lachesis/.test(t)).map(t => (t.match(/quoted exactly/g) || []).length),
             head: (document.querySelector('#result-area .card') || {}).textContent.replace(/\s+/g, ' ') };
  });
  ok(/this one did not answer/.test(failed.lach) && /not agreement with any other reader/.test(failed.lach) && /Retry just this reader/.test(failed.lach),
    'a reader that failed is shown failed, says it is not agreement, and can be retried alone: ' + failed.lach.slice(0, 200));
  ok(failed.others.every(n => n >= 1) && /1 failed/.test(failed.head), 'the other two readers answered and the head counts the failure');

  // ---- an earlier reading reopens whole after the draft changes ---------
  await page.evaluate(d => { const ta = document.getElementById('compose-text'); ta.value = d + '\n\nA new fourth paragraph.'; ta.dispatchEvent(new Event('input')); }, DRAFT);
  await page.waitForTimeout(300);
  await page.evaluate(() => askReaders('readings')); await page.waitForTimeout(400);
  await page.evaluate(() => moiraTab('readings')); await page.waitForTimeout(800);
  const list = await page.evaluate(() => Array.from(document.querySelectorAll('#moira-ask .nb')).map(x => x.textContent.replace(/\s+/g, ' ')));
  ok(list.length >= 2 && /Lachesis ✗/.test(list[0]) && /Lachesis ✓/.test(list[1]) && /1 follow-up|2 follow-ups/.test(list[1]),
    'the readings list shows both readings, newest first, with each reader\'s outcome: ' + JSON.stringify(list.map(x => x.slice(0, 80))));
  // the paragraph reading: its paragraph is still in the room verbatim, so no
  // staleness is claimed; its three cards and both follow-ups come back whole
  await page.evaluate(() => { document.querySelectorAll('#moira-ask .nb a')[1].click(); });
  await waitFor(page, () => document.querySelectorAll('#result-area .thread').length >= 2, 8000);
  const reopened = await page.evaluate(() => ({
    stale: /earlier version of the draft|no longer in the room/.test(document.getElementById('result-area').textContent),
    cards: document.querySelectorAll('#result-area .reader-card').length,
    threads: document.querySelectorAll('#result-area .thread').length,
    v: document.getElementById('compose-text').value }));
  ok(!reopened.stale && reopened.cards === 3 && reopened.threads === 2 && /A new fourth paragraph/.test(reopened.v),
    'an earlier reading reopens whole — its three cards and its follow-ups — without touching the draft: ' + JSON.stringify([reopened.cards, reopened.threads, reopened.stale]));
  // the whole-draft reading: the draft has moved on, and the page says so
  await page.evaluate(() => askReaders('readings')); await page.waitForTimeout(400);
  await page.evaluate(() => moiraTab('readings')); await page.waitForTimeout(700);
  await page.evaluate(() => { document.querySelectorAll('#moira-ask .nb a')[0].click(); });
  await waitFor(page, () => /This reading was of an earlier version of the draft/.test((document.getElementById('result-area') || {}).textContent || ''), 8000);
  const moved = await page.evaluate(() => ({
    stale: /This reading was of an earlier version of the draft/.test(document.getElementById('result-area').textContent),
    offer: /Read the current draft again \(3 model calls\)/.test(document.getElementById('result-area').textContent),
    cards: document.querySelectorAll('#result-area .reader-card').length,
    v: document.getElementById('compose-text').value }));
  ok(moved.stale && moved.offer && moved.cards === 3 && /A new fourth paragraph/.test(moved.v),
    'a whole-draft reading reopened after an edit says the draft has moved on and offers a reread with its price, without touching the draft');

  // ---- undo still reaches back past everything -------------------------
  await page.click('#compose-text');
  await page.evaluate(() => { const ta = document.getElementById('compose-text'); ta.setSelectionRange(ta.value.length, ta.value.length); });
  await page.keyboard.type(' and one more clause', { delay: 0 });
  await page.waitForTimeout(200);
  const typed = await page.evaluate(() => document.getElementById('compose-text').value);
  await page.keyboard.press('ControlOrMeta+z'); await page.waitForTimeout(250);
  const undone = await page.evaluate(() => document.getElementById('compose-text').value);
  ok(undone !== typed && undone.length < typed.length, 'the undo stack survived the whole invocation');

  ok(offOrigin.length === 0, 'no request left the scratch origin: ' + JSON.stringify(offOrigin.slice(0, 3)));
  ok(errs.length === 0, 'no page errors across the readers journey: ' + JSON.stringify(errs));
  await ctx.close();
  await browser.close();
  finish('moira');
})().catch(e => { console.log('FAIL journey crashed: ' + (e && e.stack || e)); process.exit(1); });
