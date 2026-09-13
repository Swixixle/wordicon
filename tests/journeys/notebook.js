// Notebook stage A: the room keeps what you write. In WebKit, because this
// is the room.
//
// The defects this journey was written against, each measured before the
// repair: 125 characters typed in the room → 0 in the browser's session
// store → 0 after a reload (nothing typed in the room ever reached the
// store; only the page box's own input handler did); close and reopen put
// the caret at 0 because the room reassigned an equal value; one Escape from
// inside the writing closed the whole room on the same press that armed the
// Tab exit; the page cancelled every drop, so a phrase dragged inside the
// writing was cancelled, and a paste carrying a file item beside its words
// became an upload; the selection band was a 22% tint over transparent
// glyphs.
//
// What must hold now: every keystroke in the room reaches the store and
// comes back after a reload; the place he left (selection and direction)
// comes back with an unchanged text; the undo stack survives a close and
// reopen; Escape is two presses from inside the writing and one from the
// bar, and closes the innermost panel first; a text drop or a text paste
// into the writing is left to the browser while a file drop anywhere is
// still the page's; a selection makes the real text show itself and the
// picture step aside. Nothing here posts anything, and no request leaves
// the scratch origin.
const { BASE, ok, finish } = require('./lib');
const { webkit } = require('playwright');
const fs = require('fs');
const path = require('path');

// A tag for this run, so the journey can be run again against a kept store —
// the second document's words and the other tab's request id are its own.
const RUN = Date.now().toString(36);
const SECOND = 'Second document, run ' + RUN + '.';
const TEXT = [
  'A first paragraph typed only in the room, never submitted anywhere.',
  '',
  'A second paragraph so that a selection can cross a line.',
].join('\n');

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

  const session = () => page.evaluate(() => JSON.parse(localStorage.getItem('wordicon.session.v1') || '{}'));
  const roomOpen = () => page.evaluate(() => document.body.classList.contains('ws-open'));

  await page.goto(BASE + '/'); await page.waitForTimeout(1200);
  ok(errs.length === 0, 'no page errors on Home: ' + JSON.stringify(errs));
  const s0 = await session();
  ok(!s0.input, 'the store holds no draft before anything is typed');

  // ---- every keystroke reaches the store ---------------------------------
  await page.evaluate(() => openWorkspace('write')); await page.waitForTimeout(400);
  await page.click('#compose-text');
  await page.keyboard.type(TEXT, { delay: 0 }); await page.waitForTimeout(300);
  const s1 = await session();
  ok(s1.input === TEXT, 'what was typed in the room is in the browser\'s store, keystroke by keystroke: ' + (s1.input || '').length + ' of ' + TEXT.length + ' characters');
  ok(posts.every(x => /\/api\/notebook\//.test(x)), 'and typing posted nothing but the document\'s own save: ' + JSON.stringify(posts));

  // ---- an unmistakable selection ----------------------------------------
  const inked = await page.evaluate(() => document.getElementById('compose').classList.contains('inked'));
  await page.evaluate(() => { const ta = document.getElementById('compose-text'); ta.focus(); ta.setSelectionRange(2, 60); });
  await page.waitForTimeout(150);
  const sel = await page.evaluate(() => ({
    marked: document.getElementById('compose').classList.contains('selecting'),
    color: getComputedStyle(document.getElementById('compose-text')).color,
    ink: getComputedStyle(document.getElementById('ink')).visibility }));
  ok(sel.marked && sel.color !== 'rgba(0, 0, 0, 0)' && (!inked || sel.ink === 'hidden'),
    'while a selection exists the real text shows itself and the picture steps aside: ' + JSON.stringify({ inked, ...sel }));
  await page.evaluate(() => { const ta = document.getElementById('compose-text'); ta.setSelectionRange(5, 5); });
  await page.waitForTimeout(150);
  const unsel = await page.evaluate(() => ({
    marked: document.getElementById('compose').classList.contains('selecting'),
    ink: getComputedStyle(document.getElementById('ink')).visibility }));
  ok(!unsel.marked && unsel.ink === 'visible', 'and when the selection collapses the picture paints again: ' + JSON.stringify(unsel));
  const band = await page.evaluate(() => {
    const rules = [];
    for (const sh of document.styleSheets) { try { for (const r of sh.cssRules) if (r.selectorText && /compose.*textarea::selection/.test(r.selectorText)) rules.push(r.cssText); } catch (e) {} }
    return rules; });
  ok(band.length >= 1 && band.every(b => /background(-color)?:\s*var\(--write-ink\)/.test(b) && /[^-]color:\s*var\(--write-bg\)/.test(b)),
    'the selection band is the inverse of the page — ink-coloured band, page-coloured words: ' + JSON.stringify(band));

  // ---- the place he left comes back with an unchanged text ---------------
  await page.evaluate(() => { const ta = document.getElementById('compose-text'); ta.focus(); ta.setSelectionRange(10, 14, 'backward'); });
  await page.waitForTimeout(150);
  await page.evaluate(() => closeWorkspace()); await page.waitForTimeout(250);
  ok(!(await roomOpen()), 'done closes the room');
  await page.evaluate(() => openWorkspace('write')); await page.waitForTimeout(400);
  const back = await page.evaluate(() => { const ta = document.getElementById('compose-text'); return { v: ta.value, s: ta.selectionStart, e: ta.selectionEnd, d: ta.selectionDirection, probe: ta.dataset.probe || '' }; });
  ok(back.v === TEXT && back.s === 10 && back.e === 14 && back.d === 'backward',
    'reopening the room brings back the selection he left, direction included: ' + JSON.stringify([back.s, back.e, back.d]));
  await page.keyboard.press('ControlOrMeta+z'); await page.waitForTimeout(250);
  const undone = await page.evaluate(() => document.getElementById('compose-text').value);
  ok(undone !== TEXT && undone.length < TEXT.length, 'the undo stack survived the close and reopen: ' + JSON.stringify(undone.slice(0, 24)));
  await page.keyboard.press('ControlOrMeta+Shift+z'); await page.waitForTimeout(250);
  const redone = await page.evaluate(() => document.getElementById('compose-text').value);
  ok(redone === TEXT, 'and redo puts the words back exactly');
  // a changed text takes no old place
  await page.evaluate(() => closeWorkspace()); await page.waitForTimeout(200);
  await page.evaluate(() => { const b = document.getElementById('input-text'); b.value = b.value + ' More.'; b.dispatchEvent(new Event('input')); });
  await page.evaluate(() => openWorkspace('write')); await page.waitForTimeout(400);
  const moved = await page.evaluate(() => { const ta = document.getElementById('compose-text'); return { v: ta.value, s: ta.selectionStart }; });
  ok(moved.v === TEXT + ' More.' && moved.s === moved.v.length, 'a draft changed on the page comes into the room whole, and an old place is not applied to it: caret ' + moved.s + ' of ' + moved.v.length);
  await page.evaluate(() => { const ta = document.getElementById('compose-text'); ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); document.execCommand('delete'); for (let i = 0; i < 5; i++) document.execCommand('delete'); });
  await page.waitForTimeout(200);
  const restored = await page.evaluate(() => document.getElementById('compose-text').value);
  ok(restored === TEXT, 'the added words are taken off again through the editor: ' + restored.length + ' characters');

  // ---- reload: the words come back, and so does the place -----------------
  await page.evaluate(() => { const ta = document.getElementById('compose-text'); ta.focus(); ta.setSelectionRange(20, 20); });
  await page.waitForTimeout(200);
  await page.reload(); await page.waitForTimeout(1500);
  const homeBox = await page.evaluate(() => document.getElementById('input-text').value);
  ok(homeBox === TEXT, 'after a reload the words typed in the room are back on the page, exactly: ' + homeBox.length + ' characters');
  const card = await page.evaluate(() => (document.body.innerText.match(/\d+ words? in the room, unsent/) || [''])[0]);
  ok(/in the room, unsent/.test(card), 'Home says so as a Continue card: ' + JSON.stringify(card));
  await page.evaluate(() => openWorkspace('write')); await page.waitForTimeout(400);
  const again = await page.evaluate(() => { const ta = document.getElementById('compose-text'); return { v: ta.value, s: ta.selectionStart, e: ta.selectionEnd }; });
  ok(again.v === TEXT && again.s === 20 && again.e === 20, 'and the room reopens on the same words at the place he was: ' + JSON.stringify([again.s, again.e]));

  // =======================================================================
  // Stage B: saved documents. The draft is a document on this installation:
  // autosaved as he writes, honest about its state, reopenable from My
  // writing, checkpointed on New and on an explicit save, kept apart from
  // any other copy that changed meanwhile.
  // =======================================================================
  const status = () => page.evaluate(() => document.getElementById('nb-status').textContent.trim());
  const nbState = () => page.evaluate(() => ({ id: NB.id, rev: NB.revision, seq: NB.seq, ack: NB.ackSeq, fp: NB.fingerprint }));
  const serverDoc = id => page.evaluate(async i => { const r = await fetch('/api/notebook/documents/' + i); return await r.json(); }, id);
  const settled = async (ms) => { const until = Date.now() + (ms || 6000); while (Date.now() < until) { const t = await status(); if (/^Saved · /.test(t)) return t; await page.waitForTimeout(150); } return await status(); };

  // ---- autosaved while writing, exactly ----------------------------------
  const st1 = await settled();
  const n1 = await nbState();
  ok(/^Saved · \d/.test(st1) && n1.id && n1.rev >= 1 && n1.seq === n1.ack, 'what was typed is saved on this installation without any run, submission or download, and the room says so: ' + JSON.stringify([st1, n1.rev]));
  const saves = posts.filter(x => /^PUT \/api\/notebook\/documents\//.test(x));
  ok(saves.length >= 1 && saves.every(x => x.indexOf(n1.id) !== -1), 'every save went to the one document, by its id: ' + JSON.stringify(saves.length));
  const d1 = await serverDoc(n1.id);
  ok(d1.body === TEXT, 'the store holds the exact text — leading paragraph, blank line and all: ' + d1.body.length + ' characters');
  ok(d1.display_title === 'A first paragraph typed only in the room, never submitted anywhere.' && d1.title === '' && d1.title_is_manual === false,
    'the title is the first line, derived, until he names it: ' + JSON.stringify(d1.display_title));
  const identityKept = await page.evaluate(() => JSON.parse(localStorage.getItem('nikodemus.notebook.doc.v1') || '{}').id);
  ok(identityKept === n1.id, 'the document\'s identity is kept in this browser and survived the reload above');

  // ---- an older reply cannot mark newer typing saved ---------------------
  await page.route('**/api/notebook/documents/*', async route => { await new Promise(r => setTimeout(r, 1500)); await route.continue(); });
  await page.click('#compose-text');
  await page.evaluate(() => { const ta = document.getElementById('compose-text'); ta.setSelectionRange(ta.value.length, ta.value.length); });
  await page.keyboard.type(' More words.', { delay: 0 });
  await page.waitForTimeout(900);
  await page.keyboard.type(' Even more.', { delay: 0 });
  const mid = await status();
  ok(mid === 'Saving…', 'while newer words are behind a save still in flight the room says Saving…, not Saved: ' + JSON.stringify(mid));
  const st2 = await settled(8000);
  await page.unroute('**/api/notebook/documents/*');
  const d2 = await serverDoc(n1.id);
  ok(/^Saved · /.test(st2) && d2.body === TEXT + ' More words. Even more.', 'and Saved is said only when the newest words are in the store: ' + JSON.stringify(st2));

  // ---- offline: honest about where the words are -------------------------
  await page.route('**/api/notebook/documents/*', route => route.abort());
  await page.keyboard.type(' Offline words.', { delay: 0 });
  await page.waitForTimeout(1600);
  const off = await status();
  ok(off === 'Saved on this device · waiting to sync', 'with the server unreachable the room says the words are on this device and waiting, not Saved: ' + JSON.stringify(off));
  const rec = await page.evaluate(() => { for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); if (k.indexOf('nikodemus.notebook.recovery.v1.') === 0) { const r = JSON.parse(localStorage.getItem(k)); if (!r.abandoned) return r; } } return null; });
  ok(rec && rec.doc_id === n1.id && rec.body === TEXT + ' More words. Even more. Offline words.' && rec.pending && rec.pending.request_id,
    'this tab\'s recovery record holds the exact text and the pending request, before the retry: ' + JSON.stringify(rec && rec.pending && rec.pending.request_id));
  await page.unroute('**/api/notebook/documents/*');
  const synced = await settled(12000);
  const d3 = await serverDoc(n1.id);
  ok(/^Saved · /.test(synced) && d3.body.endsWith(' Offline words.'), 'when the server is back the same request is retried and the store catches up: ' + JSON.stringify(synced));

  // ---- a lost reply: the retry carries the same request, the store answers once
  const before3 = d3.revision;
  await page.route('**/api/notebook/documents/*', async route => { await route.fetch(); await route.abort(); });   // the server commits; the reply is lost
  await page.keyboard.type(' Lost reply.', { delay: 0 });
  await page.waitForTimeout(1600);
  await page.unroute('**/api/notebook/documents/*');
  const back2 = await settled(12000);
  const d4 = await serverDoc(n1.id);
  ok(/^Saved · /.test(back2) && d4.body.endsWith(' Lost reply.') && d4.revision === before3 + 1,
    'a save whose reply was lost is retried with the same request id and lands once — one revision, not two: ' + JSON.stringify([before3, d4.revision]));

  // ---- Continue writing, My writing, New, reopen, search -----------------
  await page.reload(); await page.waitForTimeout(1500);
  const card2 = await page.evaluate(() => (document.querySelector('.cont[data-kind="writing"]') || {}).innerText || '');
  ok(/Saved on this Nikodemus/.test(card2) && /Continue writing/.test(card2) && /My writing/.test(card2), 'Home offers Continue writing and says the document is saved on this installation: ' + JSON.stringify(card2.replace(/\s+/g, ' ').slice(0, 120)));
  await page.evaluate(() => openWorkspace('write')); await page.waitForTimeout(300);
  await page.evaluate(() => nbOpenPanel('list')); await page.waitForTimeout(900);
  // The store is this installation's, not this journey's: every journey that
  // typed in the room before this one left a document here. So the claim is
  // not "one document" but "this one first, by its title, and the panel shows
  // exactly what the store lists" — the population is named, not assumed.
  const list1 = await page.evaluate(() => Array.from(document.querySelectorAll('#nb-list .nb-row a b')).map(b => b.textContent));
  const store1 = await page.evaluate(async () => { const r = await fetch('/api/notebook/documents?limit=50'); const j = await r.json(); return { titles: j.documents.map(x => x.display_title || 'Untitled'), total: j.total }; });
  ok(list1.length >= 1 && list1[0] === d1.display_title && JSON.stringify(list1) === JSON.stringify(store1.titles),
    'My writing lists this document first, by its title, and the panel shows exactly the documents the store lists on this installation: ' + JSON.stringify([list1[0], list1.length + ' of ' + store1.total]));
  await page.evaluate(() => nbNew()); await page.waitForTimeout(1500);
  const afterNew = await page.evaluate(() => ({ id: NB.id, room: document.getElementById('compose-text').value, home: document.getElementById('input-text').value }));
  ok(afterNew.id !== n1.id && afterNew.room === '' && afterNew.home === '', 'New opens a separate empty page with its own identity');
  const ck1 = await page.evaluate(async id => { const r = await fetch('/api/notebook/documents/' + id + '/checkpoints'); return (await r.json()).checkpoints.map(c => [c.revision, c.reason]); }, n1.id);
  ok(ck1.some(c => c[1] === 'new'), 'and the document left behind was checkpointed as it stood: ' + JSON.stringify(ck1));
  await page.click('#compose-text'); await page.keyboard.type(SECOND, { delay: 0 });
  const st5 = await settled();
  const n2 = await nbState();
  ok(/^Saved · /.test(st5) && n2.id === afterNew.id, 'the new page saves under its own id: ' + JSON.stringify(st5));
  await page.evaluate(() => nbOpenPanel('list')); await page.waitForTimeout(900);
  const list2 = await page.evaluate(() => Array.from(document.querySelectorAll('#nb-list .nb-row a b')).map(b => b.textContent));
  ok(list2[0] === SECOND && list2[1] === d1.display_title, 'My writing lists both, newest saved first: ' + JSON.stringify(list2));
  await page.evaluate(id => nbOpen(id), n1.id); await page.waitForTimeout(1200);
  const reopened = await page.evaluate(() => ({ id: NB.id, body: document.getElementById('compose-text').value, open: document.body.classList.contains('ws-open') }));
  ok(reopened.id === n1.id && reopened.body === d4.body && reopened.open, 'opening the first again brings back its exact text under its own identity');
  const found = await page.evaluate(async q => { const r = await fetch('/api/notebook/documents?q=' + encodeURIComponent(q)); return (await r.json()).documents.map(x => x.display_title); }, ('document, run ' + RUN).toUpperCase());
  ok(found.length === 1 && found[0] === SECOND, 'search finds a document by words in its body, case aside — this run\'s second document and no other: ' + JSON.stringify(found));

  // ---- a conflict keeps both versions ------------------------------------
  const cur = await nbState();
  const ctx2 = await browser.newContext(); await ctx2.addCookies([{ name: fs.readFileSync(path.join(DIR, 'cookie'), 'utf8').trim(), value: fs.readFileSync(path.join(DIR, 'token'), 'utf8').trim(), domain: '127.0.0.1', path: '/' }]);
  const p2 = await ctx2.newPage(); await p2.goto(BASE + '/'); await p2.waitForTimeout(800);
  // the id is handed in: the page has a global RUN of its own, and a name
  // written inside evaluate() is resolved in the page, not here
  const other = await p2.evaluate(async ({ c, rid }) => { const r = await fetch('/api/notebook/documents/' + c.id, { method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: '', title_is_manual: false, body: 'The other tab wrote this.', base_revision: c.rev, base_fingerprint: c.fp, request_id: rid, origin: 'journey' }) }); const j = await r.json(); return [r.status, j.revision, j.error || null]; }, { c: cur, rid: 'req_othertab_' + RUN });
  ok(other[0] === 200 && other[1] === cur.rev + 1, 'another tab saved the same document from the same base first: ' + JSON.stringify(other));
  await page.click('#compose-text');
  await page.evaluate(() => { const ta = document.getElementById('compose-text'); ta.setSelectionRange(ta.value.length, ta.value.length); });
  await page.keyboard.type(' Mine.', { delay: 0 }); await page.waitForTimeout(1600);
  const conf = await page.evaluate(() => ({ status: document.getElementById('nb-status').textContent.replace(/\s+/g, ' ').trim(), conflict: !!NB.conflict }));
  ok(conf.conflict && /^Another copy has changes/.test(conf.status) && /Review/.test(conf.status), 'this tab\'s save is refused and the room says another copy has changes, with Review: ' + JSON.stringify(conf.status));
  const theirs1 = await serverDoc(cur.id);
  ok(theirs1.body === 'The other tab wrote this.', 'nothing was overwritten');
  await page.evaluate(() => nbOpenPanel('conflict')); await page.waitForTimeout(300);
  const review = await page.evaluate(() => document.getElementById('nb-panel').textContent.replace(/\s+/g, ' '));
  ok(/Mine — in this room now/.test(review) && /The saved version/.test(review) && /Keep mine as a new copy/.test(review) && /Open saved version/.test(review), 'the review shows both versions and the two choices');
  await page.evaluate(() => nbKeepMineAsNew()); await page.waitForTimeout(1600);
  const kept = await page.evaluate(() => ({ id: NB.id, body: document.getElementById('compose-text').value, status: document.getElementById('nb-status').textContent.trim() }));
  const theirs2 = await serverDoc(cur.id);
  const mine2 = await serverDoc(kept.id);
  ok(kept.id !== cur.id && /^Saved · /.test(kept.status) && mine2.body === kept.body && kept.body.endsWith(' Mine.') && theirs2.body === 'The other tab wrote this.',
    'Keep mine as a new copy makes my text a durable document of its own and leaves the other copy intact');
  await ctx2.close();

  // ---- Cmd-S saves the document, not the page ----------------------------
  await page.click('#compose-text');
  await page.evaluate(() => { const ta = document.getElementById('compose-text'); ta.setSelectionRange(ta.value.length, ta.value.length); });
  await page.keyboard.type(' S.', { delay: 0 });
  await page.keyboard.press('ControlOrMeta+s'); await page.waitForTimeout(900);
  const cs = await status();
  const ck2 = await page.evaluate(async id => { const r = await fetch('/api/notebook/documents/' + id + '/checkpoints'); return (await r.json()).checkpoints.map(c => c.reason); }, kept.id);
  ok(/^Saved · /.test(cs) && ck2.includes('save'), 'Cmd-S flushes the save at once and takes an explicit checkpoint: ' + JSON.stringify([cs, ck2]));

  // ---- the header: title, My writing, New, the save state (2026-09-13) --
  // The owner's layout ruling: "Put document title, My writing, New and
  // save status in a compact header. Keep Get feedback visibly outside Aa.
  // Aa owns typography and layout controls. Group less frequent commands
  // into a compact menu … Preserve a quiet focus view with an obvious way
  // to restore controls."
  const head = await page.evaluate(() => {
    const h = document.getElementById('ws-head'), t = document.getElementById('nb-title');
    return { inRoom: !!(h && h.closest('#compose')), items: h ? Array.from(h.querySelectorAll('button')).map(b => b.textContent.trim()) : [],
             statusInHead: !!(h && h.querySelector('#nb-status')), placeholder: t ? t.placeholder : null, value: t ? t.value : null,
             firstLine: document.getElementById('compose-text').value.split('\n').find(l => l.trim()) || '' };
  });
  ok(head.inRoom && head.items.join('|') === 'My writing|New' && head.statusInHead,
    'the header sits in the room with the title, My writing, New and the save state: ' + JSON.stringify(head.items));
  ok(head.value === '' && head.placeholder && head.placeholder === head.firstLine.slice(0, head.placeholder.length) && head.placeholder.length > 8,
    'until he names it the title field shows the first line, greyed, and holds no value of its own: ' + JSON.stringify(head.placeholder));
  const draftBefore = await page.evaluate(() => { const ta = document.getElementById('compose-text'); return { v: ta.value, s: ta.selectionStart, e: ta.selectionEnd }; });
  await page.click('#nb-title'); await page.keyboard.type('Kept title', { delay: 0 });
  const st6 = await settled();
  const titled = await serverDoc(kept.id);
  ok(/^Saved · /.test(st6) && titled.title === 'Kept title' && titled.title_is_manual === true && titled.display_title === 'Kept title',
    'a typed title saves as his, by name, without a run: ' + JSON.stringify([titled.title, titled.title_is_manual, titled.display_title]));
  const draftAfter = await page.evaluate(() => { const ta = document.getElementById('compose-text'); return { v: ta.value, s: ta.selectionStart, e: ta.selectionEnd }; });
  ok(draftAfter.v === draftBefore.v && titled.body === draftBefore.v, 'and naming it did not touch a character of the writing');
  await page.evaluate(() => nbOpenPanel('list')); await page.waitForTimeout(900);
  const list3 = await page.evaluate(() => Array.from(document.querySelectorAll('#nb-list .nb-row a b')).map(b => b.textContent));
  ok(list3[0] === 'Kept title', 'My writing lists it under the name he gave it: ' + JSON.stringify(list3[0]));
  await page.evaluate(() => nbOpenPanel(''));
  await page.click('#nb-title'); await page.keyboard.press('ControlOrMeta+a'); await page.keyboard.press('Backspace');
  const st7 = await settled();
  const untitled = await serverDoc(kept.id);
  ok(/^Saved · /.test(st7) && untitled.title_is_manual === false && untitled.display_title === head.placeholder,
    'clearing the title hands it back to the first line: ' + JSON.stringify([untitled.title_is_manual, untitled.display_title]));
  await page.keyboard.press('Escape'); await page.waitForTimeout(200);
  const escT = await page.evaluate(() => ({ focus: document.activeElement ? document.activeElement.id : '', open: document.body.classList.contains('ws-open') }));
  ok(escT.focus === 'compose-text' && escT.open, 'Escape in the title field goes back to the writing and leaves the room open: ' + JSON.stringify(escT));

  // ---- the bar, Aa and the ⋯ menu ------------------------------------------
  const bar = await page.evaluate(() => Array.from(document.querySelectorAll('#ws-bar > button')).map(b => b.textContent.trim()));
  ok(bar.length === 4 && bar[0] === 'Get feedback' && bar[1] === 'Aa' && bar[2] === '⋯' && bar[3] === 'done',
    'the bar is four static buttons — Get feedback, Aa, ⋯, done: ' + JSON.stringify(bar));
  await page.evaluate(() => toggleWriteStyle()); await page.waitForTimeout(300);
  const aa = await page.evaluate(() => Array.from(document.querySelectorAll('#write-style .lbl')).map(l => l.textContent.trim()));
  ok(aa.join('|') === 'Face|Size|View|Letters', 'Aa owns typography and layout only: ' + JSON.stringify(aa));
  await page.evaluate(() => toggleWriteStyle());
  const postsBeforeMenu = posts.length;
  await page.click('#ws-more-btn'); await page.waitForTimeout(300);
  const menu = await page.evaluate(() => ({ shown: document.getElementById('ws-more').style.display !== 'none',
    labels: Array.from(document.querySelectorAll('#ws-more .lbl')).map(l => l.textContent.trim()),
    buttons: Array.from(document.querySelectorAll('#ws-more button')).map(b => b.textContent.replace(/\s+/g, ' ').trim()),
    expanded: document.getElementById('ws-more-btn').getAttribute('aria-expanded') }));
  ok(menu.shown && menu.expanded === 'true' && menu.labels.join('|') === 'Layout|This document|Full workup|Dictate'
     && ['⇄ sides', '⫞ split', '⤢ write', '☰ page', 'Download', 'Focus', 'On the page'].every(x => menu.buttons.includes(x)) && menu.buttons.some(x => /^This paragraph/.test(x)),
    'the ⋯ menu holds sides, split, write, page, Download, Focus, Full workup and Dictate: ' + JSON.stringify(menu.buttons));
  ok(posts.length === postsBeforeMenu, 'opening the menu spends nothing and posts nothing');
  await page.keyboard.press('Escape'); await page.waitForTimeout(200);
  const menuClosed = await page.evaluate(() => ({ shown: document.getElementById('ws-more').style.display !== 'none', open: document.body.classList.contains('ws-open') }));
  ok(!menuClosed.shown && menuClosed.open, 'Escape closes the menu first and leaves the room');

  // ---- focus: the controls step aside, and one thing stays to bring them back
  await page.click('#ws-more-btn'); await page.waitForTimeout(200);
  await page.evaluate(() => Array.from(document.querySelectorAll('#ws-more button')).find(b => b.textContent.trim() === 'Focus').click());
  await page.waitForTimeout(400);
  const focused = await page.evaluate(() => ({ cls: document.body.classList.contains('ws-focus'),
    head: getComputedStyle(document.getElementById('ws-head')).opacity, bar: getComputedStyle(document.getElementById('ws-bar')).opacity,
    exit: !document.getElementById('ws-focus-exit').hidden, exitText: document.getElementById('ws-focus-exit').textContent.trim(),
    v: document.getElementById('compose-text').value, focus: document.activeElement ? document.activeElement.id : '' }));
  ok(focused.cls && focused.head === '0' && focused.bar === '0' && focused.exit && focused.exitText === '☰ controls' && focused.v === draftBefore.v && focused.focus === 'compose-text',
    'Focus hides the header and the bar, keeps ☰ controls in sight, and touches neither the writing nor the caret: ' + JSON.stringify([focused.head, focused.bar, focused.exitText]));
  await page.click('#ws-focus-exit'); await page.waitForTimeout(400);
  const unfocused = await page.evaluate(() => ({ cls: document.body.classList.contains('ws-focus'), head: getComputedStyle(document.getElementById('ws-head')).opacity, bar: getComputedStyle(document.getElementById('ws-bar')).opacity, exit: !document.getElementById('ws-focus-exit').hidden }));
  ok(!unfocused.cls && unfocused.head === '1' && unfocused.bar === '1' && !unfocused.exit, '☰ controls brings the header and the bar back');

  // ---- the one-time migration of the session draft, once across two tabs ---
  const ctx3 = await browser.newContext(); await ctx3.addCookies([{ name: fs.readFileSync(path.join(DIR, 'cookie'), 'utf8').trim(), value: fs.readFileSync(path.join(DIR, 'token'), 'utf8').trim(), domain: '127.0.0.1', path: '/' }]);
  await ctx3.addInitScript(() => { if (!localStorage.getItem('nikodemus.notebook.migrated.v1') && !localStorage.getItem('nikodemus.notebook.doc.v1') && !localStorage.getItem('wordicon.session.v1'))
    localStorage.setItem('wordicon.session.v1', JSON.stringify({ input: 'Old words from before the notebook existed.', job: '', shown: '', label: '' })); });
  const t1 = await ctx3.newPage(); const t2 = await ctx3.newPage();
  await Promise.all([t1.goto(BASE + '/'), t2.goto(BASE + '/')]); await t1.waitForTimeout(2000);
  const m1 = await t1.evaluate(() => ({ id: NB.id, marker: JSON.parse(localStorage.getItem('nikodemus.notebook.migrated.v1') || 'null'), session: JSON.parse(localStorage.getItem('wordicon.session.v1') || '{}').input }));
  const m2 = await t2.evaluate(() => NB.id);
  const migrated = await t1.evaluate(async () => { const r = await fetch('/api/notebook/documents?q=' + encodeURIComponent('before the notebook existed')); return (await r.json()).documents; });
  ok(m1.id && m1.id === m2 && migrated.length === 1 && migrated[0].doc_id === m1.id && migrated[0].origin === 'migration',
    'the old session draft became one document, once, with the same id from both tabs: ' + JSON.stringify([m1.id, m2, migrated.length]));
  ok(m1.marker && m1.marker.snapshot === 'Old words from before the notebook existed.' && m1.session === 'Old words from before the notebook existed.',
    'the migration marker keeps the original snapshot and the old session key is not deleted');
  const mdoc = await t1.evaluate(async id => { const r = await fetch('/api/notebook/documents/' + id); return await r.json(); }, m1.id);
  ok(mdoc.body === 'Old words from before the notebook existed.', 'and the migrated document holds the exact words');
  await ctx3.close();

  // ---- Escape: two presses from inside the writing, one from the bar ------
  await page.click('#compose-text');
  await page.keyboard.press('Escape'); await page.waitForTimeout(150);
  const line = await page.evaluate(() => document.getElementById('room-run').hidden ? '' : document.getElementById('room-run').textContent);
  ok(await roomOpen(), 'one Escape inside the writing leaves the room open');
  ok(/Escape again, or done, closes the room/.test(line) && /Tab will now leave the writing/.test(line), 'and says what a second one does, and what Tab does now: ' + JSON.stringify(line));
  await page.keyboard.press('Escape'); await page.waitForTimeout(200);
  ok(!(await roomOpen()), 'a second Escape within the window closes it');
  await page.evaluate(() => openWorkspace('write')); await page.waitForTimeout(300);
  await page.click('#compose-text');
  await page.keyboard.press('Escape'); await page.waitForTimeout(1700);
  await page.keyboard.press('Escape'); await page.waitForTimeout(200);
  ok(await roomOpen(), 'an Escape after the window has passed is a first press again — the room stays');
  await page.keyboard.press('Escape'); await page.waitForTimeout(200);
  ok(!(await roomOpen()), 'and the next one, inside the window, closes');
  await page.evaluate(() => openWorkspace('write')); await page.waitForTimeout(300);
  await page.evaluate(() => { document.querySelector('#ws-bar button:last-child').focus(); });
  await page.keyboard.press('Escape'); await page.waitForTimeout(200);
  ok(!(await roomOpen()), 'from the bar one Escape closes the room, as before');
  // the innermost panel closes first
  await page.evaluate(() => openWorkspace('write')); await page.waitForTimeout(300);
  await page.evaluate(() => toggleWriteStyle()); await page.waitForTimeout(200);
  await page.click('#compose-text');
  await page.keyboard.press('Escape'); await page.waitForTimeout(200);
  const panel = await page.evaluate(() => ({ style: document.getElementById('write-style').style.display, open: document.body.classList.contains('ws-open') }));
  ok(panel.style === 'none' && panel.open, 'with the type panel open, Escape closes the panel and leaves the room: ' + JSON.stringify(panel));
  const doneLabel = await page.evaluate(() => document.querySelector('#ws-bar button:last-child').textContent.trim());
  ok(doneLabel === 'done', 'the exit button reads done: ' + JSON.stringify(doneLabel));
  const help = await page.evaluate(() => document.getElementById('room-keys').textContent.replace(/\s+/g, ' ').trim());
  ok(/Escape and then Tab/.test(help) && /Escape twice closes the room/.test(help), 'the writing describes both exits to a screen reader: ' + JSON.stringify(help));

  // ---- text drags and text pastes are the browser's ----------------------
  const postsBefore = posts.length;
  const dec = await page.evaluate(() => {
    const ta = document.getElementById('compose-text'); const out = {};
    const dt = new DataTransfer(); dt.setData('text/plain', 'words');
    dt.items.add(new File(['x'], 'x.png', { type: 'image/png' }));
    const paste = new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true });
    ta.dispatchEvent(paste); out.textAndFilePasteInWriting = paste.defaultPrevented;
    const fileOnly = new DataTransfer(); fileOnly.items.add(new File(['x'], 'y.png', { type: 'image/png' }));
    const paste2 = new ClipboardEvent('paste', { clipboardData: fileOnly, bubbles: true, cancelable: true });
    document.body.dispatchEvent(paste2); out.fileOnlyPasteOnPage = paste2.defaultPrevented;
    const textDrop = new DataTransfer(); textDrop.setData('text/plain', 'dragged words');
    const drop = new DragEvent('drop', { dataTransfer: textDrop, bubbles: true, cancelable: true });
    ta.dispatchEvent(drop); out.textDropInWriting = drop.defaultPrevented;
    const over = new DragEvent('dragover', { dataTransfer: textDrop, bubbles: true, cancelable: true });
    ta.dispatchEvent(over); out.textDragOverWriting = over.defaultPrevented;
    const drop2 = new DragEvent('drop', { dataTransfer: textDrop, bubbles: true, cancelable: true });
    document.body.dispatchEvent(drop2); out.textDropOnPage = drop2.defaultPrevented;
    return out;
  });
  ok(dec.textAndFilePasteInWriting === false, 'a paste that carries words beside a file, into the writing, is left to the browser as words');
  ok(dec.fileOnlyPasteOnPage === true, 'a paste that carries only a file, on the page, is still taken as an upload');
  ok(dec.textDropInWriting === false && dec.textDragOverWriting === false, 'a text drag inside the writing is the browser\'s — neither the drag nor the drop is cancelled');
  ok(dec.textDropOnPage === true, 'a drop outside any field is still the page\'s');
  await page.waitForTimeout(400);
  const uploads = posts.slice(postsBefore).filter(p => /upload/.test(p));
  ok(uploads.length === 1, 'exactly one upload was posted — the file-only paste on the page, not the words pasted into the writing: ' + JSON.stringify(posts.slice(postsBefore)));

  ok(offOrigin.length === 0, 'no request left the scratch origin: ' + JSON.stringify(offOrigin.slice(0, 3)));
  ok(errs.length === 0, 'no page errors across the notebook journey: ' + JSON.stringify(errs));
  await ctx.close();
  await browser.close();
  finish('notebook');
})().catch(e => { console.log('FAIL journey crashed: ' + (e && e.stack || e)); process.exit(1); });
