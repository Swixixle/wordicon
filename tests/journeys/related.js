// Find related words (the owner's addition, 2026-09-13). In WebKit, because
// half of this is the room.
//
// The rules under test are his: the search starts from the MEANING — a
// word, a described idea or a selected passage — and needs no accepted
// concept; English synonyms and opposites are English throughout and kept
// apart from the other languages; Latin and Greek are accounted for by name,
// with the period said, in their own script; a language that came back empty
// reads "No close match found in this pass" and one that was never asked
// reads "Not checked", and neither is proof of absence; a comparison from
// before this date says what it lacks instead of looking empty; opening a
// door spends nothing, one press starts it, escape spends nothing; a
// follow-up on a named language is added beneath, replacing nothing; the
// saved comparisons for an idea are shown before anything is spent, by id
// or — labelled — by title; and the room's bar did not grow for any of it.
//
// The job endpoints are routed to the REAL seeded records (fixtures.py ran
// run_refract through the real path): the gateway is poisoned here, and what
// is under test is the client's whole path, not the pipeline behind it.
const { BASE, DIR, ok, finish } = require('./lib');
const { webkit } = require('playwright');
const fs = require('fs');
const path = require('path');

const IDS = JSON.parse(fs.readFileSync(path.join(DIR, 'related.json'), 'utf8'));
const EP = JSON.parse(fs.readFileSync(path.join(DIR, 'epistemic.json'), 'utf8'));
const DRAFT = [
  'The refusenik posture is the stance of one who exits a containing system.',
  '',
  'Escape and belonging remain simultaneously true, and the ledger does not close when you walk out.',
].join('\n');

(async () => {
  const browser = await webkit.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addCookies([{ name: fs.readFileSync(path.join(DIR, 'cookie'), 'utf8').trim(),
                          value: fs.readFileSync(path.join(DIR, 'token'), 'utf8').trim(),
                          domain: '127.0.0.1', path: '/' }]);
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(String(e)));
  const posts = [];
  page.on('request', r => { if (r.method() !== 'GET' && r.url().indexOf('/api/notebook/') === -1) posts.push(r.method() + ' ' + r.url().replace(BASE, '')); });

  // the real seeded records, fetched once, become the job fixtures
  const cookieHeader = fs.readFileSync(path.join(DIR, 'cookie'), 'utf8').trim() + '=' + fs.readFileSync(path.join(DIR, 'token'), 'utf8').trim();
  const rec = async t => { const r = await fetch(BASE + '/api/result/' + t, { headers: { Cookie: cookieHeader } }); return r.json(); };
  const FULL = await rec(IDS.full), FOLLOW = await rec(IDS.followup), SEL = await rec(IDS.selection), LEGACY = await rec(IDS.legacy);
  ok(FULL.mode === 'refract' && Array.isArray(FULL.sections_asked) && FULL.sections_asked.length === 3,
     'the seeded full pass is a real refract record that asked for all three sections: ' + JSON.stringify(FULL.sections_asked));
  ok(LEGACY.sections_asked === undefined && !LEGACY.english_synonyms,
     'the seeded legacy record has no sections_asked and no English sections — the shape written before 2026-09-13');

  const bodies = [];
  let served = null;      // which record the next completed poll returns
  await page.route('**/api/config', r => r.fulfill({ json: { gateway: 'probe-lane', model: 'probe-model-1', ok: true } }));
  await page.route('**/api/jobs', r => {
    if (r.request().method() !== 'POST') return r.continue();
    let b = {}; try { b = JSON.parse(r.request().postData() || '{}'); } catch (e) {}
    bodies.push(b);
    return r.fulfill({ json: { job_id: 'job_rw' + bodies.length, status: 'queued' } });
  });
  let polls = 0;
  await page.route('**/api/jobs/job_rw*', r => {
    polls += 1;
    const id = r.request().url().split('/').pop();
    if (polls % 3 === 1) return r.fulfill({ json: { id, mode: 'refract', status: 'queued', progress: 'Queued…', result: null } });
    return r.fulfill({ json: { id, mode: 'refract', status: 'complete', progress: 'done', input_text: served.input_text, result: served } });
  });

  await page.goto(BASE + '/'); await page.waitForTimeout(1200);
  ok(errs.length === 0, 'no page errors on load: ' + JSON.stringify(errs));

  // ---- 1. the card's door: opens a panel, spends nothing ------------------
  await page.evaluate(t => loadPastResult(t), EP.groupOk);
  await page.waitForTimeout(900);
  const doors = await page.evaluate(() => {
    const d = document.querySelector('#result-area details.explore-idea');
    if (!d) return null;
    d.open = true;
    return [...d.querySelectorAll('button')].map(b => b.textContent.trim());
  });
  ok(doors && /^≈ Find related words/.test(doors[0]), 'Find related words is the first door in Explore this idea: ' + JSON.stringify((doors || []).slice(0, 2)));
  ok(doors && doors.some(t => /^⤷ Explore parallels/.test(t)) && doors.some(t => /^⇄ Explore other languages/.test(t)) && doors.some(t => /^◈ Explore character patterns/.test(t)),
     'and the three other doors are still there');
  const before = posts.length;
  await page.click('#result-area details.explore-idea button:has-text("Find related words")');
  await page.waitForTimeout(1200);
  const panel = await page.evaluate(() => {
    const a = document.querySelector('[id^="refract-area-"]');
    const inp = a ? a.querySelector('input[id^="rw-meaning-"]') : null;
    return { text: a ? a.innerText.replace(/\s+/g, ' ') : '', meaning: inp ? inp.value : null };
  });
  ok(posts.length === before, 'opening the door spent nothing: ' + JSON.stringify(posts.slice(before)));
  ok(panel.meaning === IDS.meaning, 'the meaning line is prefilled from the card and editable: ' + JSON.stringify(panel.meaning));
  ok(/Model calls: 2/.test(panel.text) && /Lane: probe-lane · model probe-model-1/.test(panel.text),
     'the panel says the cost and the lane before anything is pressed: ' + panel.text.slice(0, 200));
  // the seeded full pass and follow-up by id, the same-title pass by title,
  // and the map seed's two refracts — the offline forge names every
  // candidate the same, so they match by title too
  const nSaved = Number((/Saved comparisons for this idea — (\d+)/.exec(panel.text) || [])[1] || 0);
  ok(nSaved >= 3, 'the saved comparisons for this idea are shown before anything is spent: ' + nSaved + ' — ' + panel.text.slice(0, 300));
  ok(/this concept, by id/.test(panel.text) && /same title — a reconstruction/.test(panel.text),
     'a comparison matched by concept id and one matched only by title are labelled apart');
  ok(/matched by concept id; title as a fallback, marked derived/.test(panel.text), 'the panel says how it matched');

  // ---- 2. one press, the edited meaning goes, the title is a handle ------
  await page.fill('[id^="refract-area-"] input[id^="rw-meaning-"]', 'the stance of leaving without claiming the leaving settles anything');
  served = FULL;
  await page.click('[id^="refract-area-"] button:has-text("Find related words — 2 model calls")');
  await page.waitForTimeout(400);
  ok(bodies.length === 1 && posts.filter(x => x === 'POST /api/jobs').length === 1,
     'one press started exactly one run, with no second form: ' + JSON.stringify(posts));
  const b1 = bodies[0] || {};
  ok(b1.mode === 'refract' && b1.entry === 'concept' && (b1.original || {}).title === IDS.title && (b1.original || {}).concept_id === IDS.concept_id,
     'the run is a refract on the card\'s concept, by id: ' + JSON.stringify({ mode: b1.mode, entry: b1.entry, title: (b1.original || {}).title, id: (b1.original || {}).concept_id }));
  ok((b1.original || {}).definition === 'the stance of leaving without claiming the leaving settles anything',
     'the meaning that went is the one he edited, not the card\'s: ' + JSON.stringify((b1.original || {}).definition));
  ok(Array.isArray(b1.only_languages) && b1.only_languages.length === 0 && !b1.passage, 'a full pass names no languages and carries no passage');
  await page.waitForTimeout(8000);   // queued, then complete
  const shown = await page.evaluate(() => {
    const a = document.querySelector('[id^="refract-area-"]');
    return { text: a ? a.innerText : '', html: a ? a.innerHTML : '' };
  });
  const T = shown.text.replace(/\s+/g, ' ');
  // headings are set in capitals by the stylesheet, so they are matched without case
  ok(/Related words — “/i.test(T), 'the word-comparison panel rendered: ' + T.slice(0, 120));
  ok(/English synonyms — words that fit this meaning/i.test(T) && /English antonyms — and what each one opposes/i.test(T),
     'the English sections are there, and apart');
  ok(/anticipatory grief/.test(T) && /liminal dread/.test(T) && /related — adds or drops a part/.test(T) && /\bclose\b/.test(T),
     'a close synonym and a related one are told apart');
  ok(/closure/.test(T) && /homecoming/.test(T) && /a contrast, not an exact opposite/.test(T) && /What it opposes:/.test(T),
     'an exact antonym and a contrast are told apart, and each says what it opposes');
  ok(/Set aside from the English sections, not shown as English: κατήφεια — not written in Latin letters/.test(T),
     'a non-Latin word offered as an English synonym is set aside, visibly, with its reason');
  const synSec = T.split(/English synonyms — words that fit this meaning/i)[1].split(/English antonyms/i)[0];
  ok((synSec.match(/κατήφεια/g) || []).length === 1 && /Set aside/.test(synSec),
     'and it appears in the synonyms section once — in the set-aside line, not as a card');
  ok(/\bLatin\b[\s\S]*limen[\s\S]*Classical Latin/i.test(T), 'Latin has its own section, with the term and its period');
  ok(/Greek — Ancient, Koine or Modern, said which[\s\S]*Ancient Greek[\s\S]*κατήφεια[\s\S]*katēpheia[\s\S]*Ancient Greek, Homeric and Classical/i.test(T),
     'Greek has its own section: the period name, the Greek letters, the romanization, the period');
  ok(/lang="el"/.test(shown.html), 'the Greek term is marked as Greek for a screen reader');
  ok(/Italian[\s\S]*No close match found in this pass — an absence from recall, not proof the language lacks it/.test(T),
     'a language that came back empty reads as no close match in this pass, not as absence');
  ok(/Other languages — what each keeps, drops and adds[\s\S]*Spanish[\s\S]*German/i.test(T), 'the other languages follow, Spanish first');
  ok(/Cultural comparisons — documented uses, with their limits[\s\S]*The liminal phase in rites of passage[\s\S]*Where it stops:/i.test(T),
     'a cultural comparison names its tradition and its limits');
  ok(/Example, written for this pass — not a quotation:/.test(T), 'a generated example is labelled as written, not quoted');
  ok(/Everything here is recall — remembered, not looked up/.test(T) && /naming it is not looking/.test(T),
     'the panel says it is recall and that naming a place to check is not checking');
  ok(/Where one search would settle it \(not yet made\):/.test(T), 'each check location says it is not yet made');
  ok(/Ask another language/i.test(T), 'a follow-up on a named language is offered');
  ok(!/no close word — a gap, and the gap is the finding/.test(T), 'the old gap wording is gone');

  // ---- 3. the follow-up: one language, appended, nothing replaced --------
  served = FOLLOW;
  await page.fill('[id^="refract-area-"] input[id^="rw-lang-"]', 'Japanese');
  await page.click('[id^="refract-area-"] button:has-text("Ask it — 2 model calls")');
  await page.waitForTimeout(400);
  const b2 = bodies[1] || {};
  ok(bodies.length === 2 && b2.mode === 'refract' && JSON.stringify(b2.only_languages) === '["Japanese"]' && (b2.original || {}).concept_id === IDS.concept_id,
     'the follow-up asks for exactly that language, on the same concept: ' + JSON.stringify(b2.only_languages));
  await page.waitForTimeout(8000);
  const after = await page.evaluate(() => document.querySelector('[id^="refract-area-"]').innerText.replace(/\s+/g, ' '));
  ok(/Asked by name — Japanese/i.test(after), 'the follow-up rendered under the language it was asked for');
  ok(/anticipatory grief/.test(after) && /English synonyms — words that fit this meaning/i.test(after) && /\bLatin\b/i.test(after),
     'and the results above it were not replaced');
  ok(!/Asked by name[\s\S]*English synonyms — words that fit/i.test(after), 'the follow-up sits beneath, not above');

  // ---- 4. a record from before this date says what it lacks --------------
  await page.evaluate(t => loadPastResult(t), IDS.legacy);
  await page.waitForTimeout(900);
  const leg = await page.evaluate(() => document.getElementById('result-area').innerText.replace(/\s+/g, ' '));
  ok(/From the record — related words and other languages/i.test(leg), 'the legacy record reopens under the plain name');
  ok(/Not checked — this comparison was made before the English synonyms were part of the tool/.test(leg)
     && /Not checked — this comparison was made before the English opposites were part of the tool/.test(leg),
     'its English sections say they were never part of the tool then — not that nothing was found');
  ok(/Not checked — Latin was not asked for when this comparison was made/.test(leg)
     && /Not checked — Greek was not asked for when this comparison was made/.test(leg),
     'Latin and Greek say they were not asked for, by name');
  ok(/Not checked — this comparison was made before cultural comparisons were part of the tool/.test(leg),
     'and so do the cultural comparisons');
  ok(/Spanish/.test(leg) && /German/.test(leg), 'the languages it did have are still there');
  ok(!/No close match found in this pass — nothing close came back/.test(leg), 'nothing on it is described as searched and empty');

  // ---- 5. the room: the door is behind ⋯, the bar did not grow -------------
  await page.evaluate(() => openWorkspace('write')); await page.waitForTimeout(400);
  await page.evaluate(d => { const ta = document.getElementById('compose-text'); ta.value = d; ta.dispatchEvent(new Event('input')); }, DRAFT);
  await page.waitForTimeout(600);
  // the four static buttons; ↩ Revision notes may be there from earlier journeys' notes, and is counted apart
  const bar = await page.evaluate(() => [...document.querySelectorAll('#ws-bar > button')].filter(b => b.id !== 'carry-ctl').map(b => b.textContent.trim()));
  ok(bar.length === 4 && bar[0] === 'Get feedback' && !bar.some(t => /related/i.test(t)),
     'the bar is still four buttons and none of them is Find related words: ' + JSON.stringify(bar));
  await page.click('#ws-more-btn'); await page.waitForTimeout(300);
  const menu = await page.evaluate(() => document.getElementById('ws-more').innerText.replace(/\s+/g, ' '));
  ok(/Find related words[\s\S]*Your selection, or a meaning you type/i.test(menu), 'the door is in the ⋯ menu: ' + menu.slice(0, 200));
  // a short selection: the word becomes the meaning line
  await page.evaluate(() => { const ta = document.getElementById('compose-text'); ta.focus(); ta.setSelectionRange(4, 13); });   // "refusenik"
  const b3 = posts.length;
  await page.click('#ws-more button:has-text("Your selection, or a meaning you type")');
  await page.waitForTimeout(700);
  const ask = await page.evaluate(() => {
    const el = document.getElementById('related-ask');
    const inp = document.getElementById('related-meaning');
    return { shown: el.style.display !== 'none', text: el.innerText.replace(/\s+/g, ' '), meaning: inp ? inp.value : null,
             sel: RELATED_ASK && RELATED_ASK.selection, more: document.getElementById('ws-more').style.display,
             goDisabled: (document.getElementById('related-go') || {}).disabled };
  });
  ok(ask.shown && ask.more === 'none', 'the door opens the question and closes the menu');
  ok(posts.length === b3, 'and spends nothing: ' + JSON.stringify(posts.slice(b3)));
  ok(ask.sel === 'refusenik' && ask.meaning === 'refusenik', 'a selected word is the meaning line as it stands: ' + JSON.stringify(ask.meaning));
  ok(/from your selection — 1 word/.test(ask.text) && /Model calls: 2/.test(ask.text) && /Lane: probe-lane · model probe-model-1/.test(ask.text),
     'the panel names the scope, the cost and the lane: ' + ask.text.slice(0, 220));
  ok(/A hosted lane sends the meaning line and your selection to the provider/.test(ask.text), 'and says what a hosted lane would receive');
  ok(ask.goDisabled === false, 'Find is live because there is a meaning');
  // escape: closes, spends nothing, gives the caret back
  await page.keyboard.press('Escape'); await page.waitForTimeout(300);
  const esc = await page.evaluate(() => ({ shown: document.getElementById('related-ask').style.display !== 'none',
    open: document.body.classList.contains('ws-open'), focus: document.activeElement ? document.activeElement.id : '',
    s: document.getElementById('compose-text').selectionStart, e: document.getElementById('compose-text').selectionEnd }));
  ok(!esc.shown && esc.open, 'escape closes the question and leaves the room open');
  ok(posts.length === b3, 'cancelling spent nothing');
  ok(esc.focus === 'compose-text' && esc.s === 4 && esc.e === 13, 'and the selection is exactly as it was: ' + JSON.stringify(esc));

  // ---- 6. a long selection is context; the sense is typed; one press ------
  const p2start = DRAFT.indexOf('Escape and belonging');
  await page.evaluate(([a, b]) => { const ta = document.getElementById('compose-text'); ta.focus(); ta.setSelectionRange(a, b); }, [p2start, DRAFT.length]);
  await page.evaluate(() => askRelated()); await page.waitForTimeout(500);
  const ask2 = await page.evaluate(() => ({ meaning: document.getElementById('related-meaning').value,
    text: document.getElementById('related-ask').innerText.replace(/\s+/g, ' '),
    goDisabled: document.getElementById('related-go').disabled, focus: document.activeElement ? document.activeElement.id : '' }));
  ok(ask2.meaning === '' && ask2.goDisabled === true && ask2.focus === 'related-meaning',
     'a passage is context, the meaning line starts empty, Find waits for it, the caret is in the line: ' + JSON.stringify({ m: ask2.meaning, d: ask2.goDisabled, f: ask2.focus }));
  ok(/the passage above is context for which sense you mean/.test(ask2.text), 'and the panel says so');
  const roomBefore = await page.evaluate(() => { const ta = document.getElementById('compose-text'); return { v: ta.value, s: ta.selectionStart, e: ta.selectionEnd }; });
  await page.type('#related-meaning', 'staying true to a place you have left');
  served = SEL;
  await page.keyboard.press('Enter'); await page.waitForTimeout(500);
  const b4 = bodies[2] || {};
  ok(bodies.length === 3, 'Enter in the meaning line is the one press, and it started exactly one run: ' + bodies.length);
  ok(b4.mode === 'refract' && b4.entry === 'selection' && (b4.original || {}).title === '' && (b4.original || {}).concept_id === '',
     'the run needs no title and no accepted concept: ' + JSON.stringify({ entry: b4.entry, title: (b4.original || {}).title }));
  ok((b4.original || {}).definition === 'staying true to a place you have left', 'the meaning that went is the typed sense');
  ok(b4.passage === DRAFT.slice(p2start), 'the selection went as the passage, for context, exactly');
  const line = await page.evaluate(() => { const l = document.getElementById('room-run'); return l.hidden ? '' : l.textContent; });
  ok(/submitted · waiting for a turn/.test(line), 'the room says submitted: ' + JSON.stringify(line));
  await page.waitForTimeout(8500);
  const roomAfter = await page.evaluate(() => { const ta = document.getElementById('compose-text'); return { v: ta.value, s: ta.selectionStart, e: ta.selectionEnd,
    mode: document.body.className, result: document.getElementById('result-area').innerText.replace(/\s+/g, ' '),
    line: (document.getElementById('room-run').hidden ? '' : document.getElementById('room-run').textContent) }; });
  ok(roomAfter.v === roomBefore.v, 'the draft is untouched by the run');
  ok(/ws-split/.test(roomAfter.mode), 'the answer split the room when it arrived: ' + roomAfter.mode);
  ok(/Related words/i.test(roomAfter.result) && /The meaning explored: a skilled throw at a wake/.test(roomAfter.result) && /from a selection in your writing/.test(roomAfter.result),
     'the panel is beside the writing and says the meaning and that it came from a selection: ' + roomAfter.result.slice(0, 200));
  ok(roomAfter.line === '' || /related words/.test(roomAfter.line), 'the line speaks of related words, not of a workup: ' + JSON.stringify(roomAfter.line));
  ok(!/workup/.test(roomAfter.line), 'and never calls it a workup');

  ok(errs.length === 0, 'no page errors through the whole journey: ' + JSON.stringify(errs));
  await browser.close();
  finish('related');
})().catch(e => { console.log('CRASH ' + (e && e.stack || e)); process.exit(1); });
