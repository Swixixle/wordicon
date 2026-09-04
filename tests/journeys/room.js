// The writing room, in real WebKit — Safari's own engine, because this is
// where the owner writes and the bug that started this pass was invisible
// to source review and identical in every engine.
//
// The load-bearing check is the first one: click on the letter you can SEE
// and the caret must land on that letter. It used not to. Every glyph the
// ink layer draws was an inline-block — an atomic box — so the picture broke
// lines between CHARACTERS while the textarea broke them between WORDS, and
// the two drifted further apart the deeper into the draft you clicked:
// fifteen characters off by the fourth paragraph, measured.
const { BASE, ok, place, pairedContext, finish } = require('./lib');
const { webkit } = require('playwright');
const fs = require('fs');
const path = require('path');

const DRAFT = [
  'The refusenik posture is the stance of one who exits a containing system without pretending the exit resolves it.', '',
  'Escape and belonging remain simultaneously true, and the ledger does not close when you walk out of the room that opened it.', '',
  'A third paragraph, long enough to wrap several times in a narrow measure, so that arrow keys across wrapped lines have something real to cross and the ink layer has to agree with the textarea about where every line ends.',
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
  // Which engine this actually is, asked of the browser rather than of the
  // import line — a `const { chromium: webkit }` rename walked straight past
  // the first version of the source pin that guards this.
  ok(browser.browserType().name() === 'webkit',
    'the room is measured in WebKit, the engine the owner writes in: ' + browser.browserType().name());
  await page.goto(BASE + '/'); await page.waitForTimeout(1200);
  await page.evaluate(() => openWorkspace('write')); await page.waitForTimeout(400);
  await page.evaluate(d => { const ta = document.getElementById('compose-text'); ta.value = d; ta.dispatchEvent(new Event('input')); }, DRAFT);
  await page.waitForTimeout(900);
  ok(errs.length === 0, 'no page errors opening the room: ' + JSON.stringify(errs));

  // the rectangle the ink layer draws a given character in
  const rectFor = n => page.evaluate(k => {
    const ink = document.getElementById('ink');
    const w = document.createTreeWalker(ink, NodeFilter.SHOW_TEXT); let s = 0, nd;
    while ((nd = w.nextNode())) {
      const L = nd.textContent.length;
      if (s + L > k) { const r = document.createRange(); r.setStart(nd, k - s); r.setEnd(nd, k - s + 1);
        const b = r.getBoundingClientRect(); return { x: b.x + b.width / 2, y: b.y + b.height / 2, w: b.width, ch: nd.textContent[k - s] }; }
      s += L; }
    return null;
  }, n);
  async function clickChar(n) {
    const r = await rectFor(n);
    if (!r || !r.w) return { want: n, got: null };
    await page.mouse.click(r.x, r.y);
    return { want: n, got: await page.evaluate(() => document.getElementById('compose-text').selectionStart), ch: r.ch };
  }

  // ---- 1. the caret lands on the letter you clicked --------------------
  const drift = [];
  for (const n of [0, 5, 40, 90, 118, 200, 300, 420]) {
    const r = await clickChar(n);
    if (r.got !== null) drift.push({ n, off: r.got - r.want });
  }
  const worst = drift.reduce((m, d) => Math.max(m, Math.abs(d.off)), 0);
  ok(drift.length >= 6 && worst <= 1,
    'the caret lands on the letter that is drawn, everywhere in the draft (worst drift ' + worst + ' char): ' + JSON.stringify(drift));

  // and the picture and the box that owns the caret are the same box, by
  // construction — the invariant that makes the above true and keeps it true
  const boxes = await page.evaluate(() => {
    const r = s => { const b = document.querySelector(s).getBoundingClientRect(); return [Math.round(b.x), Math.round(b.width)]; };
    return { wrap: r('.compose .ink-wrap'), ta: r('#compose-text'), ink: r('#ink') };
  });
  ok(JSON.stringify(boxes.wrap) === JSON.stringify(boxes.ta) && JSON.stringify(boxes.ta) === JSON.stringify(boxes.ink),
    'the textarea and the picture behind it are the same box: ' + JSON.stringify(boxes));
  const settled = await page.evaluate(() => {
    const gs = Array.from(document.querySelectorAll('#ink .g'));
    return { total: gs.length, blocks: gs.filter(g => getComputedStyle(g).display === 'inline-block').length,
             landing: gs.filter(g => g.classList.contains('landing')).length };
  });
  ok(settled.blocks === settled.landing,
    'only a letter still animating is an atomic box — settled letters wrap like words: ' + JSON.stringify(settled));

  // ---- 2. arrows across wrapped lines, and back ------------------------
  await page.evaluate(() => { const ta = document.getElementById('compose-text'); ta.focus(); ta.setSelectionRange(40, 40); });
  const down = []; for (let i = 0; i < 4; i++) { await page.keyboard.press('ArrowDown'); down.push(await page.evaluate(() => document.getElementById('compose-text').selectionStart)); }
  const up = []; for (let i = 0; i < 4; i++) { await page.keyboard.press('ArrowUp'); up.push(await page.evaluate(() => document.getElementById('compose-text').selectionStart)); }
  ok(down.every((v, i) => i === 0 || v >= down[i - 1]) && up[up.length - 1] === 40,
    'arrow keys cross wrapped lines and come back to where they started: down ' + JSON.stringify(down) + ' up ' + JSON.stringify(up));

  // ---- 3. select, replace, undo ---------------------------------------
  await page.evaluate(() => { const ta = document.getElementById('compose-text'); ta.focus(); ta.setSelectionRange(4, 13); });
  await page.keyboard.type('REPLACED');
  const replaced = await page.evaluate(() => document.getElementById('compose-text').value.slice(0, 24));
  ok(replaced === 'The REPLACED posture is ', 'selecting and replacing puts the new text exactly where the selection was: ' + JSON.stringify(replaced));
  // ControlOrMeta, because the undo chord belongs to the platform: Cmd on the
  // owner's Mac, Control in the Linux WebKit this runs in. The check is that
  // an undo stack exists and reaches back past the replacement, not which key.
  await page.keyboard.press('ControlOrMeta+z'); await page.waitForTimeout(200);
  const undone = await page.evaluate(() => document.getElementById('compose-text').value.slice(0, 24));
  ok(undone !== replaced && /^The refusenik/.test(undone), 'undo walks the replacement back: ' + JSON.stringify(undone));

  // ---- 4. the two views ------------------------------------------------
  const measure = async () => page.evaluate(() => {
    const b = document.querySelector('.compose .ink-wrap').getBoundingClientRect();
    return { x: Math.round(b.x), w: Math.round(b.width), view: writeView()[0],
             draft: document.getElementById('compose-text').value.length,
             caret: document.getElementById('compose-text').selectionStart };
  });
  await page.evaluate(() => { const ta = document.getElementById('compose-text'); ta.setSelectionRange(97, 97); });
  const f1 = await measure();
  await page.evaluate(() => setWriteView('wide')); await page.waitForTimeout(400);
  const w1 = await measure();
  ok(w1.w > f1.w && w1.view === 'wide', 'Wide uses more of the room than Focused: ' + f1.w + ' -> ' + w1.w);
  ok(w1.draft === f1.draft && w1.caret === f1.caret, 'changing the view touches neither the draft nor the caret: ' + JSON.stringify([f1.draft, f1.caret, w1.draft, w1.caret]));
  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem('wordicon.write.style.v1') || '{}'));
  ok(stored.view === 'wide', 'the view is remembered on this device and nowhere else: ' + JSON.stringify(stored));
  const posts = []; page.on('request', r => { if (r.method() !== 'GET') posts.push(r.method() + ' ' + r.url().replace(BASE, '')); });
  await page.evaluate(() => setWriteView('focused')); await page.waitForTimeout(500);
  ok(posts.length === 0, 'changing the view records nothing: ' + JSON.stringify(posts));
  const f2 = await measure();
  ok(Math.abs(f2.w - f1.w) <= 2, 'Focused comes back to the same measure: ' + f1.w + ' -> ' + f2.w);
  // an unknown view name must not break the room — that is what lets a third be added later
  const unknown = await page.evaluate(() => { writeStyle.view = 'someday'; applyWriteStyle(); return { w: Math.round(document.querySelector('.compose .ink-wrap').getBoundingClientRect().width), view: writeView()[0] }; });
  ok(unknown.view === 'focused' && Math.abs(unknown.w - f1.w) <= 2, 'a view name this build does not know falls back rather than breaking: ' + JSON.stringify(unknown));
  await page.evaluate(() => setWriteView('focused'));

  // ---- 5. the caret survives every mode, at both measures --------------
  await page.evaluate(() => { const ta = document.getElementById('compose-text'); ta.dataset.roomProbe = 'room-1'; ta.focus(); ta.setSelectionRange(97, 104); ta.scrollTop = 0; });
  const before = await page.evaluate(() => { const ta = document.getElementById('compose-text'); return { v: ta.value, s: ta.selectionStart, e: ta.selectionEnd }; });
  for (const step of ['split', 'info', 'write']) { await page.evaluate(m => setWorkspaceMode(m), step); await page.waitForTimeout(220); }
  await page.evaluate(() => swapSides()); await page.waitForTimeout(220);
  await page.evaluate(() => setWriteView('wide')); await page.waitForTimeout(300);
  await page.evaluate(() => setWriteView('focused')); await page.waitForTimeout(300);
  const after = await page.evaluate(() => { const ta = document.getElementById('compose-text'); return { v: ta.value, s: ta.selectionStart, e: ta.selectionEnd, probe: ta.dataset.roomProbe || '' }; });
  ok(after.probe === 'room-1' && after.v === before.v && after.s === before.s && after.e === before.e,
    'every mode, the swap and both views leave the same element, draft and selection: ' + JSON.stringify([before, after]));

  // ...and a walk to a place and back, which is slice 2's promise held at the room's end
  await page.evaluate(() => openPlace('/map')); await page.waitForTimeout(1400);
  ok(!!(await place(page, '/map')), 'a place opens from inside the room');
  await page.evaluate(() => closePlace()); await page.waitForTimeout(600);
  const afterPlace = await page.evaluate(() => { const ta = document.getElementById('compose-text'); return { s: ta.selectionStart, e: ta.selectionEnd, probe: ta.dataset.roomProbe || '' }; });
  ok(afterPlace.probe === 'room-1' && afterPlace.s === before.s && afterPlace.e === before.e,
    'and a walk to a place and back leaves the caret exactly where it was: ' + JSON.stringify(afterPlace));

  // ---- 6. the caret is still right AFTER all of that -------------------
  const drift2 = [];
  for (const n of [40, 200, 420]) { const r = await clickChar(n); if (r.got !== null) drift2.push(r.got - r.want); }
  ok(drift2.every(d => Math.abs(d) <= 1), 'the caret is still on the letter after every mode change and a walk: ' + JSON.stringify(drift2));

  // ---- 7. a long draft scrolls, and the picture scrolls with it --------
  await page.evaluate(() => { const ta = document.getElementById('compose-text'); ta.value = Array(40).fill('A paragraph that exists only to make the draft long enough to scroll.').join('\n\n'); ta.dispatchEvent(new Event('input')); });
  await page.waitForTimeout(700);
  const scrolled = await page.evaluate(() => { const ta = document.getElementById('compose-text'); ta.scrollTop = 600; ta.dispatchEvent(new Event('scroll')); return { ta: ta.scrollTop, ink: document.getElementById('ink').scrollTop, h: ta.scrollHeight }; });
  ok(scrolled.h > 900 && scrolled.ta === scrolled.ink, 'a long draft scrolls and the picture scrolls with it: ' + JSON.stringify(scrolled));

  ok(errs.length === 0, 'no page errors across the room journey: ' + JSON.stringify(errs));
  await ctx.close();
  await browser.close();
  finish('room');
})().catch(e => { console.log('FAIL journey crashed: ' + (e && e.stack || e)); process.exit(1); });
