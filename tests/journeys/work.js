// The workspace (workspace-v2 slice B): /work, the shell over the existing
// core. Runs in WebKit, the engine the owner writes in. What is under test
// is the daily loop and the shell's promises: write → autosave → select →
// propose → Start → a fixture result → reopen; Tools and Results hide and
// return independently and never touch the editor's element, selection or
// undo; Focus restores what was open; at 125% zoom the sides become a
// drawer and a section below the draft; typing starts no model, research or
// producer operation while autosave still happens; Ask proposes and never
// runs. The scratch server for this journey runs with the MOCK lane (a
// canned fixture, no provider, test mode refusing every socket), because the
// loop needs a run to complete through the one job path.
//
// Slice C: the editor is the structured editor (ProseMirror), not a
// textarea. Old check → new check: `.plain-editor` (the element) →
// `.pm-editor`; `t.setSelectionRange(a, b)` → `__work.editor.setSelection(a,
// b)`; `t.value` / `inputValue` → `__work.editor.getText()` (the exact
// projection the server verifies); `t.selectionStart/End` →
// `__work.editor.getSelection()`; `activeElement === t` →
// `__work.editor.hasFocus()`. The behaviours protected are the same.
const { BASE, DIR, ok, finish, pairedContext } = require('./lib');
const { webkit } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const browser = await webkit.launch();
  ok(browser.browserType().name() === 'webkit', 'the workspace is measured in WebKit, the engine the owner writes in: ' + browser.browserType().name());
  const ctx = await pairedContext(browser, { viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const errs = [], posts = [];
  page.on('pageerror', e => errs.push(String(e.message)));
  page.on('request', r => { if (r.method() !== 'GET') posts.push(r.method() + ' ' + new URL(r.url()).pathname); });

  await page.goto(BASE + '/work');
  await page.waitForSelector('.pm-editor');
  await page.waitForTimeout(600);
  ok(errs.length === 0, 'no page errors on /work: ' + JSON.stringify(errs));
  await page.evaluate(() => window.__work.session.newDocument(''));   // a fresh document, whatever the store holds
  await page.waitForTimeout(200);

  // 1. the writing surface is the app's own blue and yellow
  const colours = await page.evaluate(() => { const t = document.querySelector('.pm-editor'); const cs = getComputedStyle(t); const host = getComputedStyle(document.getElementById('editor-host')); return { ink: cs.color, caret: cs.caretColor, bg: host.backgroundColor }; });
  ok(colours.bg === 'rgb(15, 35, 80)', 'the writing surface is #0f2350: ' + colours.bg);
  ok(colours.ink === 'rgb(255, 217, 125)', 'the writing is #ffd97d: ' + colours.ink);

  // 2. write; autosave; the title is the first line; a reload brings it back
  await page.click('.pm-editor');
  const line1 = 'He threw it once, cleanly, and the room laughed.';
  await page.keyboard.type(line1);
  await page.keyboard.press('Enter');                     // a paragraph break (the textarea needed two Enters; the projection is the same two LF)
  await page.keyboard.type('Nobody said so, but the throw was the point.');
  await page.waitForFunction(() => /Saved/.test(document.getElementById('doc-meta').textContent), null, { timeout: 8000, polling: 200 }).catch(() => {});
  const meta = await page.textContent('#doc-meta');
  ok(/Saved/.test(meta), 'autosave: the header says Saved: ' + meta);
  ok((await page.textContent('#doc-title')) === line1, 'the header names the draft by its first line');
  const docId = await page.evaluate(() => window.__work.session.id);
  const stored = await (await page.request.get(BASE + '/api/notebook/documents/' + docId)).json();
  ok(stored.body === line1 + '\n\nNobody said so, but the throw was the point.', 'the notebook holds the exact text, line breaks included');
  ok(stored.rich === true && stored.doc_json && stored.doc_json.content.length === 2 && stored.fingerprint.startsWith('fp2_'), 'and the structure beside it (two paragraphs), under the versioned fingerprint');
  ok(!posts.some(p => /\/api\/(jobs|operations)/.test(p)), 'typing posted nothing to /api/jobs or /api/operations: ' + JSON.stringify(posts));
  ok(posts.some(p => /^PUT \/api\/notebook\/documents\//.test(p)), 'typing did save (a PUT to the notebook)');

  // 3. select words; ⌘. opens the menu below them with three routes and More; a proposal spends nothing
  await page.evaluate(() => { window.__work.editor.focus(); window.__work.editor.setSelection(24, 47); });
  await page.keyboard.press('ControlOrMeta+.');
  await page.waitForSelector('#sel-popover:not([hidden])');
  const routes = await page.$$eval('#sel-popover .route', els => els.map(e => e.textContent.trim()));
  ok(routes.length === 3 && /Get feedback/.test(routes[0]) && /Analyze this passage/.test(routes[1]) && /Find related words/.test(routes[2]), 'the selection menu offers three plain routes: ' + JSON.stringify(routes));
  ok(/More/.test(await page.textContent('#sel-popover .more')), 'and a More line naming the rest');
  const selRectOk = await page.evaluate(() => { const pop = document.getElementById('sel-popover').getBoundingClientRect(); const ta = document.querySelector('.pm-editor').getBoundingClientRect(); return pop.top > ta.top; });
  ok(selRectOk, 'the menu opens below the selected words, not over the top of the draft');
  const before = posts.length;
  await page.click('#sel-popover .route:nth-child(4)');   // Find related words (head + 3 routes)
  await page.waitForSelector('#proposal-card');
  const prop = await page.textContent('#proposal-card');
  const selWords = await page.evaluate(() => window.__work.editor.getText().slice(24, 47).trim().split(/\s+/).length);
  ok(new RegExp('your selection — ' + selWords + ' words').test(prop) && /sent exactly as selected/.test(prop), 'the proposal names the exact scope (' + selWords + ' words): ' + prop.slice(0, 120));
  ok(/mock lane makes no provider request/.test(prop), 'the mock lane says no provider request, no charge — never "local"');
  ok(!/\blocal\b/i.test(prop.replace(/locally/g, '')), 'the proposal never labels model work "local"');
  ok(posts.slice(before).some(p => p === 'POST /api/actions/prepare') && !posts.slice(before).some(p => p === 'POST /api/operations'), 'preparing posted a prepare and no Start');
  await page.keyboard.press('Escape');
  await page.waitForTimeout(200);
  ok((await page.$('#proposal-card')) === null, 'Escape closes the proposal');
  ok(!posts.some(p => p === 'POST /api/operations'), 'and nothing was started');

  // 4. Analyze this passage on the whole draft → Start → a fixture result → the card says where it came from and that the draft has not changed
  await page.evaluate(() => window.__work.editor.setSelection(0, 0));
  await page.click('button[data-action="analyze.decompose"]');
  await page.waitForSelector('#proposal-card');
  ok(/the whole draft/.test(await page.textContent('#proposal-card')), 'with nothing selected the scope is the whole draft');
  const knownOps = await page.evaluate(() => Array.from(window.__work.results.tracked.keys()));
  await page.click('#proposal-card .btn.primary');
  // the operation started HERE is the one the Activity list did not hold before the press (the list also holds the record's earlier operations, slice D)
  await page.waitForFunction(known => Array.from(window.__work.results.tracked.keys()).some(k => !known.includes(k)), knownOps, { timeout: 10000, polling: 100 });
  const opId = await page.evaluate(known => Array.from(window.__work.results.tracked.keys()).find(k => !known.includes(k)), knownOps);
  try {
    await page.waitForFunction(id => { const t = window.__work.results.tracked.get(id); return t && ['complete', 'done', 'failed'].includes(t.status); }, opId, { timeout: 60000, polling: 200 });
  } catch (e) {
    ok(false, 'the run did not reach Done in 60s; errors so far: ' + JSON.stringify(errs) + ' tracked: ' + JSON.stringify(await page.evaluate(() => Array.from(window.__work.results.tracked.values()).map(t => [t.id, t.status, t.last && t.last.status]))));
  }
  await page.waitForTimeout(300);
  const card = await page.textContent('#results-body');
  ok(/From this draft, revision \d+/.test(card), 'the result names its origin: ' + (card.match(/From this draft, revision \d+/) || [''])[0]);
  ok(/hasn’t changed since/.test(card), 'and says the draft has not changed since');
  ok(/Open full result/.test(card), 'and offers the full result');
  const op = await (await page.request.get(BASE + '/api/operations/' + opId)).json();
  ok(op.status === 'complete' && (op.groups || []).length > 0, 'the operation completed through the one job path with groups: ' + (op.groups || []).length);
  ok(typeof op.snapshot_id === 'string' && op.snapshot_id.startsWith('snap_'), 'the operation links to its immutable snapshot');
  const snapFile = path.join(process.env.JOURNEY_STATE || path.join(DIR, 'state'), 'snapshots', op.snapshot_id + '.json');
  ok(fs.existsSync(snapFile), 'the snapshot is on disk: ' + op.snapshot_id);
  // typing after the run: the card says the draft changed
  await page.click('.pm-editor'); await page.keyboard.press('End'); await page.keyboard.type(' More.');
  await page.waitForTimeout(600);   // the results tab re-renders itself after an edit
  ok(/This draft changed\. Review the earlier version before applying changes\./.test(await page.textContent('#results-body')), 'after typing, the card says the draft changed and to review the earlier version');

  // 5. hiding and showing the sides never touches the editor — not its element, its BACKWARD selection, its scroll, or a save still pending
  await page.evaluate(() => { const t = document.querySelector('.pm-editor'); t.__marker = 'same-element'; const e = window.__work.editor; e.focus(); e.setSelection(e.getText().length, e.getText().length); });
  await page.keyboard.type('\n\n' + 'A line to scroll past.\n\n'.repeat(25) + 'Pending words.');    // long enough to scroll; the last words are not yet acknowledged
  await page.evaluate(() => { const e = window.__work.editor; e.setSelection(3, 9, 'backward'); e.setScroll(240); });
  const before5 = await page.evaluate(() => { const s = window.__work.session; const e = window.__work.editor; return { pending: s.seq > s.ackSeq, scroll: e.getScroll(), dir: e.getSelection().direction }; });
  await page.click('#tools-toggle'); await page.click('#results-toggle'); await page.click('#tools-toggle'); await page.click('#results-toggle');
  const same = await page.evaluate(() => { const t = document.querySelector('.pm-editor'); const e = window.__work.editor; const s = e.getSelection(); return { marker: t.__marker, sel: [s.start, s.end], dir: s.direction, scroll: e.getScroll(), n: document.querySelectorAll('.pm-editor').length, text: e.getText() }; });
  ok(same.marker === 'same-element' && same.n === 1, 'the editor element survived four toggles');
  ok(same.sel[0] === 3 && same.sel[1] === 9, 'the selection survived the toggles: ' + JSON.stringify(same.sel));
  ok(before5.dir === 'backward' && same.dir === 'backward', 'and its direction (anchor after head) survived: ' + same.dir);
  ok(before5.scroll > 0 && same.scroll === before5.scroll, 'and the scroll position survived: ' + same.scroll + 'px');
  ok(before5.pending && /Pending words\.$/.test(same.text), 'a save still pending when the sides toggled kept its words');
  await page.waitForFunction(() => { const s = window.__work.session; return !s.inflight && s.seq === s.ackSeq && s.status === 'saved'; }, null, { timeout: 15000, polling: 100 });
  ok(/Pending words\.$/.test((await (await page.request.get(BASE + '/api/notebook/documents/' + (await page.evaluate(() => window.__work.session.id)))).json()).body), 'and that save landed after the toggles');
  await page.evaluate(() => { const e = window.__work.editor; e.setScroll(0); e.focus(); });
  for (let i = 0; i < 6 && /Pending words\.$/.test(await page.evaluate(() => window.__work.editor.getText())); i++) { await page.keyboard.press('ControlOrMeta+z'); await page.waitForTimeout(150); }   // the long typing back out
  await page.evaluate(() => window.__work.editor.focus());
  await page.keyboard.press('ControlOrMeta+z');
  await page.waitForTimeout(200);
  const afterUndo = await page.evaluate(() => window.__work.editor.getText());
  ok(!/ More\.$/.test(afterUndo) && !/Pending words\.$/.test(afterUndo), 'undo still works after the toggles (the last typing came back out)');
  ok((await page.getAttribute('#shell', 'data-tools')) === 'open' && (await page.getAttribute('#shell', 'data-results')) === 'open', 'both sides are open again');

  // 6. Focus hides both sides and the secondary controls; Exit focus restores what was open
  await page.click('#results-hide');
  ok((await page.getAttribute('#shell', 'data-results')) === 'closed', 'Results has its own Hide');
  await page.click('#focus-btn');
  ok((await page.isHidden('#tools')) && (await page.isHidden('#results')) && (await page.isHidden('#activity-foot')), 'Focus hides Tools, Results and the activity strip');
  ok(await page.isVisible('#exit-focus'), 'and shows Exit focus');
  await page.click('#exit-focus');
  ok((await page.getAttribute('#shell', 'data-tools')) === 'open' && (await page.getAttribute('#shell', 'data-results')) === 'closed', 'Exit focus restores exactly the arrangement before: Tools open, Results closed');

  // 7. at 125% zoom the sides do not squeeze the writing: a drawer and a section below
  await page.setViewportSize({ width: 1152, height: 720 });
  await page.waitForTimeout(300);
  ok((await page.getAttribute('#shell', 'data-narrow')) === 'yes', 'at 1152×720 the shell is narrow (both sides would squeeze the writing)');
  const drawerPos = await page.evaluate(() => getComputedStyle(document.getElementById('tools')).position);
  ok(drawerPos === 'absolute', 'Tools is a drawer over the left');
  ok(await page.isVisible('#tools-close'), 'the drawer has a Close');
  await page.keyboard.press('Escape');
  ok((await page.getAttribute('#shell', 'data-tools')) === 'closed', 'Escape closes the drawer');
  await page.click('#results-toggle');
  ok(await page.isVisible('#stacked'), 'Results is a section below the draft');
  ok(await page.isHidden('#results'), 'and not a side');
  ok(await page.isVisible('#stacked #results-tabs') && (await page.$$('#stacked #results-tabs .tab')).length === 4, 'and its four tabs (Results, Feedback, Notes, Sources) came down with it');
  await page.click('#stacked #results-tabs .tab[data-tab="feedback"]');
  ok((await page.getAttribute('#stacked #results-tabs .tab[data-tab="feedback"]', 'aria-selected')) === 'true', 'a tab in the section still switches');
  await page.click('#stacked #results-tabs .tab[data-tab="results"]');
  const hdr = await page.evaluate(() => { const h = document.getElementById('header'); return { sw: h.scrollWidth, cw: h.clientWidth, rows: new Set(Array.from(h.children).filter(e => !e.hidden).map(e => Math.round(e.getBoundingClientRect().top))).size }; });
  ok(hdr.sw <= hdr.cw && hdr.rows >= 2, 'the header wraps its formatting bar onto its own row rather than overlapping (' + hdr.rows + ' rows, no overflow)');
  const editorH = await page.evaluate(() => document.querySelector('.pm-editor').getBoundingClientRect().height);
  ok(editorH >= 300, 'the draft keeps its height (' + Math.round(editorH) + 'px)');
  await page.click('#back-to-writing');
  await page.waitForTimeout(200);
  ok(await page.evaluate(() => window.__work.editor.hasFocus()), 'Back to writing puts the caret back in the draft');
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForTimeout(300);
  ok((await page.getAttribute('#shell', 'data-narrow')) === 'no', 'back at 1440 the sides are sides again');
  ok(await page.isVisible('#results #results-tabs') || (await page.getAttribute('#shell', 'data-results')) === 'closed', 'and the tabs went back to the side');
  // a 1280 px laptop keeps both panels by narrowing them instead of going to a drawer
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.waitForTimeout(300);
  await page.evaluate(() => { window.__work.layout.setTools(true); window.__work.layout.setResults(true); });
  await page.waitForTimeout(200);
  const w1280 = await page.evaluate(() => ({ narrow: document.getElementById('shell').dataset.narrow, tools: document.getElementById('tools').getBoundingClientRect().width, results: document.getElementById('results').getBoundingClientRect().width, writing: document.getElementById('center').getBoundingClientRect().width, hide: !!document.getElementById('results-hide') && document.getElementById('results-hide').getBoundingClientRect().right <= window.innerWidth }));
  ok(w1280.narrow === 'no' && w1280.writing >= 690 && w1280.tools >= 200 && w1280.results >= 280 && w1280.hide, 'at 1280×800 both sides stay open as sides, narrowed, the writing keeps ' + Math.round(w1280.writing) + 'px, and Hide is in reach');
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForTimeout(300);

  // 8. Get feedback: three readers, one call each, through the fixture stand-ins
  if ((await page.getAttribute('#shell', 'data-tools')) !== 'open') await page.click('#tools-toggle');
  await page.click('button[data-action="feedback.readers"]');
  await page.waitForSelector('#proposal-card');
  ok(/3 \(one per reader\)/.test(await page.textContent('#proposal-card')), 'the readers proposal says three calls, one per reader');
  await page.click('#proposal-card .btn.primary');
  // the writer keeps writing while the readers read: the arrival must not take the caret
  await page.click('.pm-editor'); await page.keyboard.press('End'); await page.keyboard.type(' Still typing.');
  await page.waitForFunction(() => /3 of 3 readers answered/.test(document.getElementById('results-body').textContent), null, { timeout: 30000, polling: 200 });
  await page.waitForTimeout(300);
  ok((await page.evaluate(() => window.__work.editor.hasFocus())) && /Still typing\.$/.test(await page.evaluate(() => window.__work.editor.getText())), 'the reading arrived without stealing the caret; the words typed meanwhile are in the draft');
  const reading = await page.textContent('#results-body');
  ok(/3 of 3 readers answered/.test(reading), 'all three readers answered: ' + (reading.match(/\d of \d readers answered/) || [''])[0]);
  ok(/readers answer separately|nothing here combines them/.test(reading), 'and nothing combines them');
  await page.click('#results .tab[data-tab="feedback"]');
  await page.waitForTimeout(500);
  ok(/Readers/.test(await page.textContent('#results-body')), 'the Feedback tab lists the reading');
  await page.click('#results .tab[data-tab="results"]');

  // 9. Ask proposes; it never runs. With nothing selected, a words-only tool says so instead of guessing a subject
  const before9 = posts.filter(p => p === 'POST /api/operations').length;
  await page.evaluate(() => { window.__work.editor.focus(); window.__work.editor.setSelection(0, 0); });
  await page.keyboard.press('ControlOrMeta+k');
  await page.waitForSelector('#ask:not([hidden])');
  await page.fill('#ask-input', 'related words');
  await page.waitForFunction(() => document.querySelectorAll('#ask-matches button').length > 0, null, { timeout: 5000, polling: 100 });
  await page.keyboard.press('Enter');
  await page.waitForTimeout(500);
  ok(/select them first/.test(await page.textContent('#results-body')), 'with nothing selected, Find related words asks for a selection instead of inventing one');
  ok(posts.filter(p => p === 'POST /api/operations').length === before9, 'and started nothing');
  await page.evaluate(() => { window.__work.editor.focus(); window.__work.editor.setSelection(24, 47); });
  await page.keyboard.press('ControlOrMeta+k');
  await page.waitForSelector('#ask:not([hidden])');
  await page.fill('#ask-input', 'related words');
  await page.waitForFunction(() => document.querySelectorAll('#ask-matches button').length > 0, null, { timeout: 5000, polling: 100 });
  await page.keyboard.press('Enter');
  await page.waitForSelector('#proposal-card');
  ok(/Find related words/.test(await page.textContent('#proposal-card')), 'Ask "related words" proposes Find related words');
  ok(posts.filter(p => p === 'POST /api/operations').length === before9, 'and started nothing');
  await page.keyboard.press('Escape');
  await page.keyboard.press('ControlOrMeta+k');
  await page.fill('#ask-input', 'map');
  await page.waitForFunction(() => document.querySelectorAll('#ask-matches button').length > 0, null, { timeout: 5000, polling: 100 });
  await page.keyboard.press('Enter');
  await page.waitForTimeout(400);
  ok(!(await page.isHidden('#place-view')) && /Map/.test(await page.textContent('#place-name')), 'Ask "map" opens the Map as a place inside the shell');
  ok(!posts.some(p => /\/api\/jobs$/.test(p) && posts.indexOf(p) > before9), 'opening the Map started nothing');
  await page.click('#place-back');
  ok(await page.isHidden('#place-view'), 'Back to writing closes the place');
  ok(await page.evaluate(() => document.querySelector('.pm-editor').__marker === 'same-element'), 'the editor element survived the Map round trip');

  // 10. Your work (slice E: the derived index) and Investigate
  const posts10 = posts.length;
  await page.click('a[data-page="yourwork"]');
  await page.waitForSelector('#work-q');
  await page.waitForTimeout(900);
  const yw = await page.textContent('#yourwork-view');
  ok(/writing/.test(yw) && new RegExp(line1.slice(0, 20)).test(yw), 'Your work lists the draft, from the index');
  ok(/Runs · \d+/.test(yw) && /items from \d+ stores, generation \d+/.test(await page.textContent('#work-health')), 'and the runs, with the index’s own population line: ' + (await page.textContent('#work-health')).slice(0, 60));
  await page.fill('#work-q', 'laughed');
  await page.waitForTimeout(700);
  const hits = await page.$$eval('.work-item', els => els.map(e => e.dataset.kind + ':' + e.querySelector('.result-title').textContent.slice(0, 30)));
  ok(hits.some(h => h.startsWith('writing:He threw it once')), 'a word from the draft finds the draft: ' + JSON.stringify(hits.slice(0, 3)));
  ok(hits.some(h => h.startsWith('run:') || h.startsWith('input:') || h.startsWith('operation:')), 'and the run that was made from it');
  ok(!posts.slice(posts10).some(p => /\/api\/(jobs|operations)$/.test(p)) && !posts.slice(posts10).some(p => /\/api\/work/.test(p)), 'searching sent the words to nothing but the local index (a GET): ' + JSON.stringify(posts.slice(posts10)));
  await page.fill('#work-q', '"(unbalanced AND NOT');
  await page.waitForTimeout(700);
  ok(/No matches|shown/.test(await page.textContent('#work-list')) && errs.length === 0, 'a malformed query is answered, not crashed');
  await page.fill('#work-q', '');
  await page.waitForTimeout(700);
  await page.click('.work-filters .chip-btn:has-text("Writing")');
  await page.waitForTimeout(700);
  const firstItem = await page.$('.work-item[data-kind="writing"]');
  const firstId = await firstItem.evaluate(e => e.dataset.item);
  await firstItem.$eval('button:has-text("Archive")', b => b.click());
  await page.waitForTimeout(800);
  ok(!(await page.$$eval('.work-item', els => els.map(e => e.dataset.item))).includes(firstId), 'Archive takes the draft out of the ordinary listing');
  await page.click('.work-filters .chip-btn:has-text("Show archived")');
  await page.waitForTimeout(800);
  ok((await page.$$eval('.work-item', els => els.map(e => e.dataset.item))).includes(firstId) && /archived only/.test(await page.textContent('#work-list')), 'and the archive filter shows it, kept whole');
  const archivedDoc = await (await page.request.get(BASE + '/api/notebook/documents/' + firstId.split(':')[2])).json();
  ok(archivedDoc.doc_id === firstId.split(':')[2] && archivedDoc.body.length > 0, 'the archived document is still in the notebook, untouched');
  await (await page.$('.work-item')).$eval('button:has-text("Unarchive")', b => b.click());
  await page.waitForTimeout(600);
  await page.click('.work-filters .chip-btn:has-text("Archived only")');
  await page.waitForTimeout(600);
  const postsInv = posts.length;
  await page.click('a[data-page="investigate"]');
  await page.waitForSelector('.card[data-producer="ethicalalt"] .facts');
  await page.waitForTimeout(400);
  const inv = await page.textContent('#investigate-view');
  ok(/EthicalAlt/.test(inv) && /Open Case/.test(inv) && /PUBLIC EYE/.test(inv) && /Rabbit Hole/.test(inv), 'Investigate shows the four instruments');
  ok(!posts.slice(postsInv).length, 'opening Investigate contacted no producer and started nothing: ' + JSON.stringify(posts.slice(postsInv)));
  const reg = await (await page.request.get(BASE + '/api/actions')).json();
  const ea = reg.actions.find(a => a.id === 'investigate.ethicalalt.lookup');
  ok(ea && ea.readiness && ea.readiness.producer && ea.readiness.producer.configured === true, 'EthicalAlt readiness is derived from the connector record (configured in the scratch state)');
  const pe = reg.actions.find(a => a.id === 'investigate.publiceye.start');
  ok(pe && pe.readiness && pe.readiness.available === false && /no connector kind/.test(pe.readiness.reason), 'PUBLIC EYE is honestly not available: ' + pe.readiness.reason);
  ok(!/2 of 4 available/.test(inv), 'no fixture constant on the page');
  const eaCard = await page.textContent('.card[data-producer="ethicalalt"]');
  ok(/Deployment verified for starting\s*no/.test(eaCard) && /test mode: a declared development connector on loopback/.test(eaCard) && /POST \/api\/investigate/.test(eaCard), 'the EthicalAlt card says the deployment is not verified, that starting works here only against the fixture producer, and which contract is pinned');
  // slice F: a start is a proposal first, then one POST at the boundary, then the signed export in custody
  await page.fill('.card[data-producer="ethicalalt"] .inv-subject', 'Exemplar Holdings');
  await page.click('.card[data-producer="ethicalalt"] .btn.primary');
  await page.waitForSelector('#proposal-card');
  const invProp = await page.textContent('#proposal-card');
  ok(/what you named — “Exemplar Holdings”/.test(invProp) && /the name, and a session id minted here — to producer:ethicalalt/.test(invProp), 'the proposal names what leaves and to whom: ' + invProp.slice(0, 120));
  ok(!posts.slice(postsInv).some(p => p === 'POST /api/operations'), 'and nothing was started by proposing');
  const knownInv = await page.evaluate(() => Array.from(window.__work.results.tracked.keys()));
  await page.click('#proposal-card .btn.primary');
  await page.waitForFunction(known => Array.from(window.__work.results.tracked.values()).some(t => !known.includes(t.id) && t.kind === 'investigation' && ['complete', 'failed', 'unknown'].includes(t.status)), knownInv, { timeout: 30000, polling: 250 });
  await page.waitForTimeout(400);
  const invCard = await page.textContent('#results-body');
  ok(/Producer: ethicalalt · upstream id nk_/.test(invCard) && /Start: ok/.test(invCard), 'the investigation card names the producer, the upstream id and the start’s outcome');
  ok(/Signed export: imported · receipt: signature verified/.test(invCard) && /in custody: dep_/.test(invCard), 'the signed export is in custody and its signature verified under the pinned key: ' + (invCard.match(/in custody: dep_[a-z0-9]+/) || [''])[0]);
  ok(/a valid signature says the bytes are the producer’s, not that the research is true/.test(invCard), 'and the card says what a signature does and does not mean');
  const invOp = await page.evaluate(known => Array.from(window.__work.results.tracked.values()).find(t => !known.includes(t.id) && t.kind === 'investigation').id, knownInv);
  const invEv = await (await page.request.get(BASE + '/api/operations/' + invOp + '/events')).json();
  const invKinds = invEv.events.filter(e => /^stage_(intent|end)$/.test(e.kind)).map(e => e.kind + ':' + e.stage.slice(0, 4) + (e.outcome ? '=' + e.outcome : ''));
  ok(JSON.stringify(invKinds) === JSON.stringify(['stage_intent:POST', 'stage_end:POST=ok', 'stage_intent:GET ', 'stage_end:GET =ok']), 'the record holds the intent before and the outcome after the POST, then the export’s read: ' + JSON.stringify(invKinds));
  ok(!JSON.stringify(invEv.events.map(e => e.detail)).includes('Exemplar'), 'the name itself is not in the events — the snapshot holds it');
  // Ask: a plain-language request whose rest names what to investigate
  await page.keyboard.press('ControlOrMeta+k');
  await page.waitForSelector('#ask:not([hidden])');
  await page.fill('#ask-input', 'investigate Exemplar Holdings');
  await page.waitForFunction(() => document.querySelectorAll('#ask-matches button').length > 0, null, { timeout: 5000, polling: 100 });
  ok(/“Exemplar Holdings”/.test(await page.textContent('#ask-matches')), 'Ask shows the rest of the request as the subject it would propose');
  await page.keyboard.press('Enter');
  await page.waitForSelector('#proposal-card');
  ok(/Start an investigation \(EthicalAlt\)/.test(await page.textContent('#proposal-card')) && /“Exemplar Holdings”/.test(await page.textContent('#proposal-card')), 'and Enter proposes the investigation with that subject, starting nothing');
  await page.keyboard.press('Escape');
  await page.click('a[data-page="work"]');

  // 11. reload: the same document, the same text, the header says so
  await page.reload();
  await page.waitForSelector('.pm-editor');
  await page.waitForTimeout(800);
  ok(await page.evaluate(() => window.__work.session.id) === docId, 'a reload reopens the same document');
  ok(/^He threw it once/.test(await page.evaluate(() => window.__work.editor.getText())), 'with its text');

  // 12. the record outlives the page (slice D): after the reload the Activity list is read from the
  // store — the run made here, and what a dead process left behind — and restoring a page starts nothing
  const postsBefore12 = posts.length;
  await page.waitForTimeout(600);
  await page.click('#results-toggle');
  if ((await page.getAttribute('#shell', 'data-results')) !== 'open') await page.click('#results-toggle');
  await page.waitForTimeout(400);
  const act = await page.textContent('#results-body');
  ok(/Analyze this passage/.test(act) && /Done/.test(act), 'after the reload the run made here is listed from the record, Done');
  ok(!posts.slice(postsBefore12).some(p => /\/api\/(jobs|operations)$/.test(p)), 'restoring the page started nothing: ' + JSON.stringify(posts.slice(postsBefore12)));
  const seeded = JSON.parse(fs.readFileSync(path.join(DIR, 'operations.json'), 'utf8'));
  const dead = await (await page.request.get(BASE + '/api/operations/' + seeded.dead_after_intent)).json();
  ok(dead.status === 'unknown' && dead.recovery && dead.recovery.case === 'delivery_unknown' && dead.recovery.dispatch_intents === 1, 'an operation a dead process left after its first dispatch intent is unknown, by the record: ' + dead.recovery.case);
  const never = await (await page.request.get(BASE + '/api/operations/' + seeded.never_dispatched)).json();
  ok(never.status === 'failed' && /not resumable/.test(never.error || '') && never.recovery.dispatch_intents === 0, 'one never dispatched and without a proposal is not resumed, and says why: ' + (never.error || '').slice(0, 60));
  const unknownRow = (await page.$$('#results-body .card.op')).length;
  ok(unknownRow >= 2 && /Outcome unknown/.test(act), 'the Activity list shows the unknown operation as unknown, not as running');
  // open it: the card says what the record says, and the two doors are apart
  await page.evaluate(id => { window.__work.results.selected = id; window.__work.results.render(); }, seeded.dead_after_intent);
  await page.waitForTimeout(300);
  const card12 = await page.textContent('#results-body');
  ok(/Outcome unknown — A dispatch was recorded and its outcome was not/.test(card12) && /1 dispatch intent recorded/.test(card12), 'the card says a dispatch was recorded and its outcome was not, with the count from the record');
  const before12 = posts.length;
  await page.click('#results-body button:has-text("Check status / recover result")');
  await page.waitForTimeout(500);
  ok(/nothing was sent/.test(await page.textContent('#toast')) && posts.slice(before12).every(p => /\/recover$/.test(p)), 'Check status reads the record and sends nothing: ' + JSON.stringify(posts.slice(before12)));
  ok((await (await page.request.get(BASE + '/api/operations/' + seeded.dead_after_intent)).json()).status === 'unknown', 'and the operation stays unknown — it is never replayed');
  await page.click('#results-body button:has-text("Start another attempt")');
  await page.waitForTimeout(500);
  ok(/not started from a proposal/.test(await page.textContent('#results-body')) && !posts.slice(before12).some(p => /\/api\/(jobs|operations)$/.test(p)), 'Start another attempt is refused for an operation with no proposal to rebuild, and nothing was sent');
  const opsList = await (await page.request.get(BASE + '/api/operations?limit=10')).json();
  ok(opsList.dispatcher && opsList.dispatcher.held === true && opsList.population, 'the store names its dispatcher and its population');

  // 13. every control is reachable by keyboard (slice G, instructions §11 "all controls keyboard reachable"):
  // a walk of Tab from the first header control reaches the header, the formatting bar, both sides'
  // controls, the editor itself, and the grips; a grip resizes on the arrow keys; Tab leaves the editor
  await page.click('a[data-page="work"]');
  await page.evaluate(() => { window.__work.layout.setTools(true); window.__work.layout.setResults(true); });
  await page.waitForTimeout(200);
  await page.focus('#tools-toggle');
  const reached = new Set();
  const describe = () => page.evaluate(() => { const a = document.activeElement; if (!a || a === document.body) return ''; return a.tagName.toLowerCase() + (a.id ? '#' + a.id : '') + (a.className ? '.' + String(a.className).split(' ').filter(Boolean).join('.') : '') + (a.dataset && a.dataset.page ? '[' + a.dataset.page + ']' : '') + (a.dataset && a.dataset.action ? '[' + a.dataset.action + ']' : ''); });
  reached.add(await describe());
  for (let i = 0; i < 120; i++) {
    await page.keyboard.press('Tab');
    const d = await describe();
    if (!d) break;
    if (d.includes('#tools-toggle') && i > 5) break;
    reached.add(d);
  }
  const need = [['#tools-toggle', 'Tools toggle'], ['#doc-menu-btn', 'Document menu'], ['.fmt', 'a formatting button'], ['#ask-btn', 'Ask'], ['#focus-btn', 'Focus'], ['#results-toggle', 'Results toggle'], ['[yourwork]', 'Your work destination'], ['[feedback.readers]', 'Get feedback'], ['#tools-hide', 'Hide Tools'], ['#tools-grip', 'the Tools grip'], ['.pm-editor', 'the editor'], ['.tab', 'a Results tab'], ['#results-hide', 'Hide Results'], ['#results-grip', 'the Results grip']];
  const missing = need.filter(([sel]) => !Array.from(reached).some(r => r.includes(sel))).map(([, name]) => name);
  ok(missing.length === 0, 'a Tab walk reaches every control of the header, Tools, the editor and Results, including both grips (' + reached.size + ' stops)' + (missing.length ? ' — missing: ' + missing.join(', ') : ''));
  await page.focus('#tools-grip');
  const wBefore = await page.evaluate(() => document.getElementById('tools').getBoundingClientRect().width);
  await page.keyboard.press('ArrowLeft'); await page.keyboard.press('ArrowLeft'); await page.keyboard.press('ArrowLeft');
  await page.waitForTimeout(150);
  const wAfter = await page.evaluate(() => document.getElementById('tools').getBoundingClientRect().width);
  ok(wAfter < wBefore, 'the Tools grip resizes on the arrow keys (' + Math.round(wBefore) + ' → ' + Math.round(wAfter) + 'px)');
  await page.keyboard.press('ArrowRight'); await page.keyboard.press('ArrowRight'); await page.keyboard.press('ArrowRight');
  const text13 = await page.evaluate(() => window.__work.editor.getText());
  await page.evaluate(() => { const e = window.__work.editor; e.focus(); e.setSelection(0, 0); });
  await page.keyboard.press('Tab');
  ok(!(await page.evaluate(() => window.__work.editor.hasFocus())) && (await page.evaluate(() => window.__work.editor.getText())) === text13, 'Tab outside a list leaves the editor (the keyboard is never trapped in the draft) and types nothing');

  ok(errs.length === 0, 'no page errors across the workspace journey: ' + JSON.stringify(errs));
  await browser.close();
  finish('work');
})().catch(async e => { ok(false, 'journey crashed: ' + (e && e.stack || e)); finish('work'); });
