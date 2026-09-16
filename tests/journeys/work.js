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
  await page.click('#proposal-card .btn.primary');
  try {
    await page.waitForFunction(() => /(^|[^A-Za-z])Done([^A-Za-z]|$)/.test(document.getElementById('results-body').textContent) || document.querySelector('#results-body .state.good') !== null, null, { timeout: 60000, polling: 200 });
  } catch (e) {
    ok(false, 'the run did not reach Done in 60s; errors so far: ' + JSON.stringify(errs) + ' tracked: ' + JSON.stringify(await page.evaluate(() => Array.from(window.__work.results.tracked.values()).map(t => [t.id, t.status, t.last && t.last.status]))));
  }
  const card = await page.textContent('#results-body');
  ok(/From this draft, revision \d+/.test(card), 'the result names its origin: ' + (card.match(/From this draft, revision \d+/) || [''])[0]);
  ok(/hasn’t changed since/.test(card), 'and says the draft has not changed since');
  ok(/Open full result/.test(card), 'and offers the full result');
  const opId = await page.evaluate(() => Array.from(window.__work.results.tracked.keys())[0]);
  const op = await (await page.request.get(BASE + '/api/operations/' + opId)).json();
  ok(op.status === 'complete' && (op.groups || []).length > 0, 'the operation completed through the one job path with groups: ' + (op.groups || []).length);
  ok(typeof op.snapshot_id === 'string' && op.snapshot_id.startsWith('snap_'), 'the operation links to its immutable snapshot');
  const snapFile = path.join(process.env.JOURNEY_STATE || path.join(DIR, 'state'), 'snapshots', op.snapshot_id + '.json');
  ok(fs.existsSync(snapFile), 'the snapshot is on disk: ' + op.snapshot_id);
  // typing after the run: the card says the draft changed
  await page.click('.pm-editor'); await page.keyboard.press('End'); await page.keyboard.type(' More.');
  await page.waitForTimeout(600);   // the results tab re-renders itself after an edit
  ok(/This draft changed\. Review the earlier version before applying changes\./.test(await page.textContent('#results-body')), 'after typing, the card says the draft changed and to review the earlier version');

  // 5. hiding and showing the sides never touches the editor
  await page.evaluate(() => { const t = document.querySelector('.pm-editor'); t.__marker = 'same-element'; window.__work.editor.focus(); window.__work.editor.setSelection(3, 9); });
  await page.click('#tools-toggle'); await page.click('#results-toggle'); await page.click('#tools-toggle'); await page.click('#results-toggle');
  const same = await page.evaluate(() => { const t = document.querySelector('.pm-editor'); const s = window.__work.editor.getSelection(); return { marker: t.__marker, sel: [s.start, s.end], n: document.querySelectorAll('.pm-editor').length }; });
  ok(same.marker === 'same-element' && same.n === 1, 'the editor element survived four toggles');
  ok(same.sel[0] === 3 && same.sel[1] === 9, 'the selection survived the toggles: ' + JSON.stringify(same.sel));
  await page.evaluate(() => window.__work.editor.focus());
  await page.keyboard.press('ControlOrMeta+z');
  await page.waitForTimeout(200);
  const afterUndo = await page.evaluate(() => window.__work.editor.getText());
  ok(!/ More\.$/.test(afterUndo), 'undo still works after the toggles (the last typing came back out)');
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
  const editorH = await page.evaluate(() => document.querySelector('.pm-editor').getBoundingClientRect().height);
  ok(editorH >= 300, 'the draft keeps its height (' + Math.round(editorH) + 'px)');
  await page.click('#back-to-writing');
  await page.waitForTimeout(200);
  ok(await page.evaluate(() => window.__work.editor.hasFocus()), 'Back to writing puts the caret back in the draft');
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForTimeout(300);
  ok((await page.getAttribute('#shell', 'data-narrow')) === 'no', 'back at 1440 the sides are sides again');

  // 8. Get feedback: three readers, one call each, through the fixture stand-ins
  if ((await page.getAttribute('#shell', 'data-tools')) !== 'open') await page.click('#tools-toggle');
  await page.click('button[data-action="feedback.readers"]');
  await page.waitForSelector('#proposal-card');
  ok(/3 \(one per reader\)/.test(await page.textContent('#proposal-card')), 'the readers proposal says three calls, one per reader');
  await page.click('#proposal-card .btn.primary');
  await page.waitForFunction(() => /readers answered/.test(document.getElementById('results-body').textContent), null, { timeout: 30000, polling: 200 });
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

  // 10. Your work and Investigate
  await page.click('a[data-page="yourwork"]');
  await page.waitForTimeout(800);
  const yw = await page.textContent('#yourwork-view');
  ok(/writing/.test(yw) && new RegExp(line1.slice(0, 20)).test(yw), 'Your work lists the draft');
  ok(/decompose|run|Analyze/.test(yw), 'and the run');
  await page.click('a[data-page="investigate"]');
  await page.waitForTimeout(400);
  const inv = await page.textContent('#investigate-view');
  ok(/EthicalAlt/.test(inv) && /Open Case/.test(inv) && /PUBLIC EYE/.test(inv) && /Rabbit Hole/.test(inv), 'Investigate shows the four instruments');
  const reg = await (await page.request.get(BASE + '/api/actions')).json();
  const ea = reg.actions.find(a => a.id === 'investigate.ethicalalt.lookup');
  ok(ea && ea.readiness && ea.readiness.producer && ea.readiness.producer.configured === true, 'EthicalAlt readiness is derived from the connector record (configured in the scratch state)');
  const pe = reg.actions.find(a => a.id === 'investigate.publiceye.start');
  ok(pe && pe.readiness && pe.readiness.available === false && /no connector kind/.test(pe.readiness.reason), 'PUBLIC EYE is honestly not available: ' + pe.readiness.reason);
  ok(!/2 of 4 available/.test(inv), 'no fixture constant on the page');
  await page.click('a[data-page="work"]');

  // 11. reload: the same document, the same text, the header says so
  await page.reload();
  await page.waitForSelector('.pm-editor');
  await page.waitForTimeout(800);
  ok(await page.evaluate(() => window.__work.session.id) === docId, 'a reload reopens the same document');
  ok(/^He threw it once/.test(await page.evaluate(() => window.__work.editor.getText())), 'with its text');

  ok(errs.length === 0, 'no page errors across the workspace journey: ' + JSON.stringify(errs));
  await browser.close();
  finish('work');
})().catch(async e => { ok(false, 'journey crashed: ' + (e && e.stack || e)); finish('work'); });
