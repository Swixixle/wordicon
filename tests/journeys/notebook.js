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
  ok(posts.length === 0, 'and typing posted nothing: ' + JSON.stringify(posts));

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
