// workspace-v2 slice J — the owner's own notes beside the work, and his
// annotations on carried text.
//
// What is under test is the promise that words typed in the panel are as safe
// as words typed in the draft: they are in this browser before any server
// acknowledgment, a refused save keeps them and retries under the same request
// id (so a retry cannot become a duplicate), another tab cannot overwrite
// them, and undo inside a note box is the box's own and never reaches the
// draft. Also the two display repairs: a standing rendered from its fields
// rather than as "[object Object]", and a run named only when the record
// holds one.
const { BASE, ok, finish, pairedContext } = require('./lib');
const playwright = require('playwright');

const ENGINE = process.env.JOURNEY_ENGINE === 'webkit' ? 'webkit' : 'chromium';
const NAME = 'notes-' + ENGINE;

(async () => {
  const browser = await playwright[ENGINE].launch();
  const ctx = await pairedContext(browser, { viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => { if (!require('./lib').benignPageError(e)) errs.push(String(e.message)); });

  const boot = async p => {
    await p.goto(BASE + '/work');
    await p.waitForSelector('.pm-editor');
    await p.waitForFunction(() => !!(window.__work && window.__work.session && window.__work.session.id), null, { timeout: 10000, polling: 100 });
    await p.evaluate(() => window.__work.layout.setResults(true));
  };
  const openNotes = async p => { await p.click('#results-tabs .tab[data-tab="notes"]'); await p.waitForSelector('#note-compose', { timeout: 6000 }); };
  const status = p => p.textContent('.notes-mine .note-status');
  const waitStatus = (p, re, ms = 9000) => p.waitForFunction(r => new RegExp(r).test((document.querySelector('.notes-mine .note-status') || {}).textContent || ''), re.source, { timeout: ms, polling: 150 });
  const notesOf = async (p, docId) => (await (await p.request.get(BASE + '/api/notes?doc_id=' + docId)).json()).notes;
  const fresh = async p => { await p.evaluate(() => window.__work.session.newDocument('')); await p.waitForTimeout(200); await p.click('.pm-editor'); };
  const saved = p => p.waitForFunction(() => /Saved \d/.test(document.getElementById('doc-meta').textContent), null, { timeout: 8000, polling: 200 });

  // Leaves the box at an exact text using real keystrokes, so the undo stack
  // stays real. How much ONE undo takes back is the engine's own business
  // (Chromium takes a word, WebKit the whole burst) and is not what this
  // journey pins — only that undo acts inside the box and nowhere else.
  const setBox = async (p, text) => {
    await p.click('#note-compose');
    await p.locator('#note-compose').selectText();
    await p.keyboard.type(text);
    await waitStatus(p, /Saved to the record/, 12000);
  };
  const notesState = p => p.evaluate(() => { const m = window.__work.results.mine; return { docId: m.docId, sid: window.__work.session.id, loaded: m.loaded, items: m.items.length, chips: document.querySelectorAll('.note-chip-head').length, composeNote: (m.editors.get(m.composeScope()) || {}).noteId || '' }; });
  const waitChips = async (p, n, who) => {
    try { await p.waitForFunction(k => document.querySelectorAll('.note-chip-head').length >= k, n, { timeout: 12000, polling: 150 }); }
    catch (e) { ok(false, who + ': the earlier notes never appeared as chips — state was ' + JSON.stringify(await notesState(p))); }
  };
  await boot(page);
  ok(errs.length === 0, 'no page errors on /work: ' + JSON.stringify(errs));

  // 1. a note is written beside the document it was typed on, and the record says it is HIS
  await fresh(page);
  await page.keyboard.type('A disposable draft for the note journey.');
  await saved(page);
  const docA = await page.evaluate(() => window.__work.session.id);
  await openNotes(page);
  await page.click('#note-compose');
  await page.keyboard.type('My own note, typed while reading.');
  await waitStatus(page, /Saved to the record/);
  let mine = await notesOf(page, docA);
  ok(mine.length === 1 && mine[0].body === 'My own note, typed while reading.', 'the note reached the record: ' + JSON.stringify(mine.map(n => n.body)));
  ok(mine[0].owner_authored === true && /own words/.test(mine[0].means) && mine[0].is_not.includes('a carry'),
     'the record says these are his own words and not a carry: ' + JSON.stringify({ o: mine[0].owner_authored, m: mine[0].means }));
  ok(/Notes · 1/.test(await page.textContent('#results-tabs .tab[data-tab="notes"]')), 'the tab carries the count so the surface is visibly there while reading');

  // 2. undo inside the note box is the box's own: the draft is untouched, and
  //    undo in the draft does not reach the note
  const draftText = await page.evaluate(() => window.__work.editor.getText());
  await page.keyboard.type(' Words to undo.');
  const boxFull = await page.inputValue('#note-compose');
  await page.keyboard.press('ControlOrMeta+z');
  const boxUndone = await page.inputValue('#note-compose');
  ok(boxUndone.length < boxFull.length && boxFull.endsWith('Words to undo.'), 'undo in the note box took back words from the note: ' + JSON.stringify([boxFull.slice(-18), boxUndone.slice(-18)]));
  ok(await page.evaluate(() => window.__work.editor.getText()) === draftText, 'undo in the note box left the draft exactly as it was');
  await page.keyboard.press('ControlOrMeta+Shift+z');
  ok(await page.inputValue('#note-compose') === boxFull && await page.evaluate(() => window.__work.editor.getText()) === draftText, 'redo in the note box restores only its own words and leaves the draft unchanged');
  await page.click('.pm-editor'); await page.keyboard.type(' appended');
  const boxBeforeDraftUndo = await page.inputValue('#note-compose');
  await page.keyboard.press('ControlOrMeta+z');
  ok(await page.inputValue('#note-compose') === boxBeforeDraftUndo, 'undo in the draft left the note box alone');
  // 3. the panel closing and reopening keeps the words, the caret and the undo stack
  await setBox(page, 'My own note, typed while reading. Still here.');
  await page.evaluate(() => window.__work.session.id && window.__work.layout.setResults(false));
  await page.waitForTimeout(200);
  await page.evaluate(() => window.__work.layout.setResults(true));
  await page.click('#results-tabs .tab[data-tab="results"]');
  await openNotes(page);
  const afterToggle = await page.inputValue('#note-compose');
  ok(afterToggle.startsWith('My own note') && /Still here\./.test(afterToggle), 'the note box came back with its words after the panel closed and reopened: ' + JSON.stringify(afterToggle));
  const beforeToggleUndo = await page.inputValue('#note-compose');
  await page.click('#note-compose');
  await page.keyboard.press('ControlOrMeta+z');
  // Undo of a replacement can restore a longer previous value. Check that
  // the retained stack changes this box, not which value is shorter.
  ok(await page.inputValue('#note-compose') !== beforeToggleUndo, 'the box kept its own undo stack across the panel toggle — the element was re-attached, not rebuilt');
  await setBox(page, 'My own note, typed while reading. Still here.');

  // 4. a second document has its own notes; the first document's are not shown
  //    and not carried across
  await fresh(page);
  await page.keyboard.type('A second disposable draft.');
  await saved(page);
  const docB = await page.evaluate(() => window.__work.session.id);
  await openNotes(page);
  ok(docB !== docA, 'the journey is on a second document');
  ok(await page.inputValue('#note-compose') === '', 'the note box is empty on the second document');
  ok(!/Still here/.test(await page.textContent('.notes-mine')), 'the first document’s notes are not shown beside the second');
  await setBox(page, 'A note that belongs to the second document.');
  ok((await notesOf(page, docB)).length === 1 && (await notesOf(page, docA)).length === 1, 'each document keeps its own note: ' + JSON.stringify([(await notesOf(page, docA)).length, (await notesOf(page, docB)).length]));

  // 5. a refused save keeps the words, says so, and the retry sends the SAME
  //    request id — so a save that actually landed cannot become two notes
  await page.click('.notes-mine button:has-text("Start another note")');
  await page.waitForTimeout(250);
  ok(await page.inputValue('#note-compose') === '', 'Start another note leaves an empty box and the finished one below');
  // The sabotage pass found the first shape of this check could not fail:
  // aborting outright means the server never saw the save, so no retry could
  // duplicate anything. The real hazard is a save that LANDS and whose reply
  // is lost — so the request is let through and only then failed.
  await page.route('**/api/notes**', async r => {
    if (r.request().method() === 'POST') { try { await r.fetch(); } catch (e) { /* the server still saw it */ } }
    await r.abort('failed');
  });
  await page.click('#note-compose'); await page.keyboard.type('Words written while the server was unreachable.');
  await waitStatus(page, /Not saved/);
  ok(/press Retry/.test(await status(page)), 'a refused save says so and says the words are still here: ' + JSON.stringify((await status(page)).slice(0, 90)));
  const landed = (await notesOf(page, docB)).filter(n => /server was unreachable/.test(n.body)).length;
  ok(landed === 1, 'the save reached the record even though the page was told it failed — the duplicate hazard is live: ' + landed);
  ok(await page.inputValue('#note-compose') === 'Words written while the server was unreachable.', 'the refused save left every word in the box');
  const keptId = await page.evaluate(() => window.__work.results.mine.editors.get(window.__work.results.mine.composeScope()).requestId);
  ok(!!keptId, 'the request id is held for the retry');

  // and the words are in this browser before any acknowledgment: a reload
  // during the failed save brings them back
  await page.reload(); await page.waitForSelector('.pm-editor'); await page.waitForTimeout(900);
  await page.evaluate(() => window.__work.layout.setResults(true));
  await openNotes(page);
  ok(await page.inputValue('#note-compose') === 'Words written while the server was unreachable.', 'the unsent words came back from this browser after a reload: ' + JSON.stringify(await page.inputValue('#note-compose')));
  ok(/not saved to the record yet|Not saved/.test(await status(page)), 'and the page says they are not on the record yet: ' + JSON.stringify((await status(page)).slice(0, 80)));
  const sameId = await page.evaluate(() => window.__work.results.mine.editors.get(window.__work.results.mine.composeScope()).requestId);
  ok(!!sameId && sameId === keptId, 'the recovered words came back with the request id they were last sent under (the mechanism; the guarantee it exists for is the next check): ' + JSON.stringify([keptId, sameId]));
  await page.unroute('**/api/notes**');
  await page.evaluate(() => window.__work.results.mine.flush(window.__work.results.mine.composeScope()));
  await waitStatus(page, /Saved to the record/);
  const afterRetry = await notesOf(page, docB);
  ok(afterRetry.filter(n => /server was unreachable/.test(n.body)).length === 1, 'the retry made exactly one note, not two: ' + JSON.stringify(afterRetry.map(n => n.body)));
  await page.waitForFunction(() => window.__work.results.mine.items.length >= 2, null, { timeout: 9000, polling: 150 });
  ok(true, 'the list the offline page could not read came back by itself once the server answered');

  // 6. a second tab of this browser cannot overwrite words this tab has not sent.
  //    Tab A is still holding that note in its compose box (it wrote it); tab B
  //    opens the same note from the list and saves first.
  const target = afterRetry.find(n => /server was unreachable/.test(n.body));
  const tabB = await ctx.newPage();
  tabB.on('pageerror', e => { if (!require('./lib').benignPageError(e)) errs.push('tab B: ' + String(e.message)); });
  await boot(tabB);
  await tabB.evaluate(id => window.__work.session.open(id), docB);
  await tabB.waitForTimeout(500);
  await openNotes(tabB);
  await waitChips(tabB, 1, 'tab B');
  await tabB.click('.note-chip-head:has-text("server was unreachable")');
  await tabB.waitForSelector('.note-chip.open textarea', { timeout: 8000 });
  const tabBBox = tabB.locator('.note-chip.open textarea').first();
  const replyB = tabB.waitForResponse(r => r.url() === BASE + '/api/notes/' + target.note_id && r.request().method() === 'PUT');
  await tabBBox.click(); await tabBBox.press('ControlOrMeta+End'); await tabB.keyboard.type(' — edited in tab B.');
  const committedB = await replyB;
  const committedBodyB = await committedB.json();
  await tabB.waitForFunction(() => /Saved to the record/.test((document.querySelector('.note-chip.open .note-status') || {}).textContent || ''), null, { timeout: 9000, polling: 150 });
  ok(committedB.status() === 200 && /edited in tab B/.test(committedBodyB.note?.body || ''), 'tab B saved its edit to the same note first');

  // A stale Saved label can survive until the asynchronous recovery write
  // paints. Await each actual save response before asserting its outcome.
  const replyA = page.waitForResponse(r => r.url() === BASE + '/api/notes/' + target.note_id && r.request().method() === 'PUT');
  await page.click('#note-compose');
  await page.keyboard.press('ControlOrMeta+End'); await page.keyboard.type(' — and edited in tab A.');
  await replyA;
  // settle on ANY outcome first: a check that hangs instead of failing by name
  // is not a check, and the sabotage pass proved this one used to hang
  await waitStatus(page, /changed somewhere else|Saved to the record|Not saved/, 12000);
  const settled = await status(page);
  ok(/changed somewhere else/.test(settled) && /Nothing was overwritten/.test(settled),
     'tab A is told the note moved and that nothing was overwritten: ' + JSON.stringify(settled.slice(0, 80)));
  ok(/edited in tab A/.test(await page.inputValue('#note-compose')), 'tab A still holds every word it typed: ' + JSON.stringify((await page.inputValue('#note-compose')).slice(-30)));
  ok(/The other version reads/.test(await page.textContent('.notes-mine .note-acts')), 'and it is shown what the other version says rather than having it applied');
  const serverNow = (await notesOf(page, docB)).find(n => n.note_id === target.note_id);
  ok(/edited in tab B/.test(serverNow.body) && !/edited in tab A/.test(serverNow.body), 'tab B’s save stands on the record, unharmed by tab A’s refused one');
  const keepMine = page.locator('.notes-mine button:has-text("Keep mine as a new note")');
  if (await keepMine.count()) { await keepMine.click(); await waitStatus(page, /Saved to the record/, 12000); }
  else ok(false, 'no way to keep his own version was offered after the conflict');
  const both = await notesOf(page, docB);
  ok(both.some(n => /edited in tab A/.test(n.body)) && both.some(n => /edited in tab B/.test(n.body)),
     'both versions are on the record under their own ids — nothing combined, nothing lost: ' + JSON.stringify(both.map(n => n.body.slice(-22))));
  await tabB.close();

  // 7. after a restart of the page the notes are still there, from the record
  await page.reload(); await page.waitForSelector('.pm-editor'); await page.waitForTimeout(900);
  await page.evaluate(() => window.__work.layout.setResults(true));
  await openNotes(page);
  const listed = await page.textContent('.notes-mine');
  ok(/edited in tab A/.test(listed) && /second document/.test(listed), 'the notes came back from the record after a reload: ' + JSON.stringify(listed.slice(0, 60)));

  // 8. the two display repairs, tested on the rules themselves
  const st = await page.evaluate(() => window.__work.results.standingWords({ route: 'candidate concept', anchor_fit: 'supported', friction_verdict: 'weak', invented: true, contradicted: false }));
  ok(Array.isArray(st) && st.join(' · ').includes('route: candidate concept') && st.join(' · ').includes('anchor fit: supported') && st.join(' · ').includes('written by the model'),
     'a standing is rendered from its own fields, in words: ' + JSON.stringify(st));
  ok(!st.join(' ').includes('[object Object]'), 'no standing renders as [object Object]');
  ok(!st.join(' ').includes('contradicted'), 'a flag the record does not assert is silence, not "false": ' + JSON.stringify(st));
  ok((await page.evaluate(() => window.__work.results.standingWords(undefined))).length === 0, 'a carry with no standing renders nothing rather than guessing');
  const withRun = await page.evaluate(() => window.__work.results.runLine({ source: { trace_id: 'trace_abc123' } }));
  const noRun = await page.evaluate(() => window.__work.results.runLine({ source: {}, title: 'a title that must never become a run' }));
  ok(withRun === 'from run trace_abc123', 'a run is named from the record’s own path: ' + JSON.stringify(withRun));
  ok(/not recorded/.test(noRun) && !/title/.test(noRun), 'with no run in the record the page says so and never infers one from a title: ' + JSON.stringify(noRun));

  // 9. his annotation on carried text sits BESIDE it and never replaces it.
  //    The card is built from a synthetic carry so this journey adds nothing
  //    to the shared store that a later journey would find; the record-level
  //    proof that a note cannot overwrite an excerpt is in the Python suite.
  const annot = await page.evaluate(() => {
    const c = { carry_id: 'carry_test', excerpt: 'The carried sentence, exactly as the run produced it.',
                standing: { route: 'candidate concept', anchor_fit: 'partial' },
                source: { trace_id: 'trace_zzz' }, at: new Date().toISOString(),
                means: 'may be useful while revising', is_not: ['accepted', 'owner_authored'] };
    const card = window.__work.results.carryCard(c);
    document.body.appendChild(card);
    const opener = card.querySelector('.note-annotate button');
    const before = card.textContent;
    opener.click();
    const out = { opener: opener.textContent, hasBox: !!card.querySelector('textarea'),
                  save: !!Array.from(card.querySelectorAll('button')).find(b => /Save my note/.test(b.textContent)),
                  excerptStillThere: card.textContent.includes('The carried sentence, exactly as the run produced it.'),
                  beforeHadExcerpt: before.includes('The carried sentence, exactly as the run produced it.'),
                  standingShown: card.textContent.includes('route: candidate concept'),
                  runShown: card.textContent.includes('from run trace_zzz') };
    card.remove();
    return out;
  });
  ok(annot.opener === 'Add my own note', 'a carried card offers him a note of his own: ' + JSON.stringify(annot.opener));
  ok(annot.hasBox && annot.save, 'opening it gives a box and a save control');
  ok(annot.beforeHadExcerpt && annot.excerptStillThere, 'the carried sentence is still on the card with the box open — the note goes beside it, never over it');
  ok(annot.standingShown && annot.runShown, 'the card states the standing in words and names the run the record holds');

  ok(errs.length === 0, 'no page errors across the whole journey: ' + JSON.stringify(errs.slice(0, 4)));
  await browser.close();
  finish(NAME);
})().catch(e => { console.error(e); process.exit(1); });
