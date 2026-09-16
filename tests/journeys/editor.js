// The structured editor and the storage contract (workspace-v2 slice C).
// Runs in the engine named by JOURNEY_ENGINE (chromium or webkit) — the
// instructions ask for standard writing to work in both — against the
// workspace scratch server (mock lane; test mode refusing every socket).
//
// What is under test is §7 of the build instructions: the exact text is the
// projection of the structure, and both sides compute it the same (the
// golden vectors, in this engine); a formatting-only change is a versioned
// edit that survives save, reload, crash recovery and restore; an old
// client cannot flatten a structured head; a document the schema cannot
// hold opens plain and is never rewritten in silence; Enter, Shift-Enter,
// lists, the toolbar, find and replace behave; a suggestion is applied only
// to the target it was made for, as one undo step, and the record says so;
// a composition finishes before a save or a capture; a long document stays
// responsive.
const { BASE, DIR, ok, finish, pairedContext } = require('./lib');
const playwright = require('playwright');
const fs = require('fs');
const path = require('path');

const ENGINE = process.env.JOURNEY_ENGINE === 'webkit' ? 'webkit' : 'chromium';
const NAME = 'editor-' + ENGINE;

(async () => {
  const browser = await playwright[ENGINE].launch();
  ok(browser.browserType().name() === ENGINE, 'the editor is measured in ' + ENGINE + ': ' + browser.browserType().name());
  const ctx = await pairedContext(browser, { viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(String(e.message)));
  page.on('dialog', d => d.accept('https://example.org/why'));
  const put = async (id, body) => { const r = await page.request.put(BASE + '/api/notebook/documents/' + id, { data: body }); return { status: r.status(), data: await r.json() }; };
  const getDoc = async id => (await page.request.get(BASE + '/api/notebook/documents/' + id)).json();
  const text = () => page.evaluate(() => window.__work.editor.getText());
  const structure = () => page.evaluate(() => window.__work.editor.getStructure());
  const select = (a, b) => page.evaluate(([a, b]) => { window.__work.editor.focus(); window.__work.editor.setSelection(a, b); }, [a, b]);
  const saved = () => page.waitForFunction(() => /Saved \d/.test(document.getElementById('doc-meta').textContent), null, { timeout: 8000, polling: 200 }).catch(() => {});
  const fresh = async () => { await page.evaluate(() => window.__work.session.newDocument('')); await page.waitForTimeout(150); await page.click('.pm-editor'); };
  const noSave = () => page.evaluate(() => { const s = window.__work.session; if (s.timer) clearTimeout(s.timer); s.timer = null; });   // the crash: the tab dies before autosave

  await page.goto(BASE + '/work');
  await page.waitForSelector('.pm-editor');
  await page.waitForTimeout(500);
  ok(errs.length === 0, 'no page errors on /work: ' + JSON.stringify(errs));

  // 1. the golden vectors, in this engine: projection, canonical form, fingerprint and the position map
  const vectors = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'fixtures', 'projection_vectors.json'), 'utf8'));
  const vec = await page.evaluate(async (vectors) => {
    const m = await import('/work/document.js');
    const bad = [];
    for (const v of vectors.vectors) {
      const doc = m.fromJSON(v.doc);
      const canon = m.canonicalDoc(doc);
      const body = m.project(doc);
      const cs = m.canonicalString(canon);
      const fp = await m.fingerprintV2('', false, body, canon, vectors.schema, vectors.projection);
      const map = m.positionMap(doc);
      const why = [];
      if (body !== v.body) why.push('body');
      if (cs !== v.canonical) why.push('canonical');
      if (fp !== v.fp2) why.push('fp2');
      if (JSON.stringify(map) !== JSON.stringify(v.map)) why.push('map');
      if (m.leafBlocks(doc).length !== v.leaf_count) why.push('leaves');
      if (m.project(m.parsePlain(body)) !== body) why.push('round_trip_plain');
      if (why.length) bad.push(v.name + ': ' + why.join(','));
    }
    return { n: vectors.vectors.length, bad };
  }, vectors);
  ok(vec.bad.length === 0 && vec.n === 18, 'the page reproduces all ' + vec.n + ' golden vectors (projection, canonical JSON, fingerprint v2, position map) in ' + ENGINE + (vec.bad.length ? ': ' + vec.bad.join('; ') : ''));

  // 2. a bold-only change is a versioned edit: it saves, survives a reload, and moves the revision
  await fresh();
  await page.keyboard.type('Bold words here, and plain ones.');
  await saved();
  const id2 = await page.evaluate(() => window.__work.session.id);
  const rev0 = (await getDoc(id2)).revision;
  await select(0, 4); await page.keyboard.press('ControlOrMeta+b');
  await page.waitForTimeout(100);
  ok((await text()) === 'Bold words here, and plain ones.', 'bold changed no character of the text');
  await page.waitForFunction(r => window.__work.session.revision > r, rev0, { timeout: 8000, polling: 200 }).catch(() => {});
  const d2 = await getDoc(id2);
  ok(d2.revision === rev0 + 1 && d2.rich && JSON.stringify(d2.doc_json).includes('"strong"') && d2.body === 'Bold words here, and plain ones.', 'the bold-only save moved the revision (' + rev0 + ' → ' + d2.revision + ') and the structure holds the mark beside the exact text');
  await page.reload(); await page.waitForSelector('.pm-editor'); await page.waitForTimeout(600);
  const s2 = await structure();
  ok((await page.evaluate(() => window.__work.session.id)) === id2 && JSON.stringify(s2.content[0].content[0]) === JSON.stringify({ type: 'text', text: 'Bold', marks: [{ type: 'strong' }] }), 'after a reload the bold is still there, on the same document');
  ok((await page.evaluate(() => window.__work.session.rich)) === true, 'and the session knows the head is structured');

  // 3. an old client cannot flatten a structured head — body only, or an explicit JSON null
  const o1 = await put(id2, { title: '', title_is_manual: false, body: d2.body + ' edited elsewhere', base_revision: d2.revision, base_fingerprint: d2.fingerprint, request_id: 'req_old_client_' + Date.now() });
  const o2 = await put(id2, { title: '', title_is_manual: false, body: d2.body + ' x', base_revision: d2.revision, base_fingerprint: d2.fingerprint, request_id: 'req_old_null_' + Date.now(), doc_json: null });
  const after3 = await getDoc(id2);
  ok(o1.status === 422 && o1.data.error_class === 'structure_would_be_lost' && o2.status === 422 && o2.data.error_class === 'structure_would_be_lost', 'a body-only save against the structured head is refused by name (422 structure_would_be_lost), with an explicit null too');
  ok(after3.revision === d2.revision && after3.fingerprint === d2.fingerprint && after3.rich, 'and the head is untouched');

  // 4. crash recovery keeps the whole structured document — a never-saved document, and an unsent formatting-only edit on a saved one
  await fresh();
  await page.keyboard.type('Recover me whole');
  await select(8, 10); await page.keyboard.press('ControlOrMeta+b');
  await page.waitForTimeout(150);
  const id4 = await page.evaluate(() => window.__work.session.id);
  await noSave();
  await page.reload(); await page.waitForSelector('.pm-editor'); await page.waitForTimeout(1200);
  const r4 = await page.evaluate(() => ({ id: window.__work.session.id, text: window.__work.editor.getText(), st: JSON.stringify(window.__work.editor.getStructure()) }));
  ok(r4.id === id4 && r4.text === 'Recover me whole' && r4.st.includes('"strong"'), 'a document the server never received is reopened from this browser’s recovery, bold and all');
  await saved();
  ok((await getDoc(id4)).rich === true, 'and then saved, structure included');
  await select(0, 7); await page.keyboard.press('ControlOrMeta+i');
  await page.waitForTimeout(150);
  await noSave();
  await page.reload(); await page.waitForSelector('.pm-editor'); await page.waitForTimeout(1200);
  const r4b = await page.evaluate(() => ({ id: window.__work.session.id, st: JSON.stringify(window.__work.editor.getStructure()), recovered: window.__work.session.recovered }));
  ok(r4b.id === id4 && r4b.st.includes('"em"') && r4b.recovered === true, 'an unsent formatting-only edit (no character changed) is recovered from the envelope, not lost to a body comparison');

  // 5. Enter, Shift-Enter, lists: continue, indent, outdent, exit; the projection is exact
  await fresh();
  await page.keyboard.type('A'); await page.keyboard.press('Shift+Enter'); await page.keyboard.type('B');
  await page.keyboard.press('Enter'); await page.keyboard.type('C');
  ok((await text()) === 'A\nB\n\nC', 'Shift-Enter is a hard break (one LF), Enter a paragraph (two LF): ' + JSON.stringify(await text()));
  await page.keyboard.press('Enter'); await page.keyboard.type('one');
  await page.click('.fmt[data-fmt="bullet"]');
  await page.keyboard.press('Enter'); await page.keyboard.type('two');
  await page.keyboard.press('Tab'); await page.keyboard.type('!');
  await page.keyboard.press('Enter'); await page.keyboard.type('three'); await page.keyboard.press('Shift+Tab');
  await page.keyboard.press('Enter'); await page.keyboard.press('Enter'); await page.keyboard.type('after');
  const st5 = await structure();
  const types = st5.content.map(b => b.type).join(',');
  ok(types === 'paragraph,paragraph,bullet_list,paragraph', 'the list continues, nests on Tab, lifts on Shift-Tab and exits on an empty item: ' + types);
  const list = st5.content[2];
  ok(list.content.length === 2 && list.content[0].content[1] && list.content[0].content[1].type === 'bullet_list' && list.content[0].content[1].content[0].content[0].content[0].text === 'two!' && list.content[1].content[0].content[0].text === 'three', 'two! is nested under one; three was lifted back to the outer list');
  ok((await text()) === 'A\nB\n\nC\n\none\n\ntwo!\n\nthree\n\nafter', 'the projection joins every leaf paragraph with two LF and adds no markers: ' + JSON.stringify(await text()));
  ok((await text()).split(/\s+/).length === 7 && /\b7 words\b/.test(await page.textContent('#doc-meta')), 'the header counts the words of this draft: ' + (await page.textContent('#doc-meta')).match(/\d+ words/)[0]);

  // 6. the toolbar acts on the editing selection and keeps it
  await fresh();
  await page.keyboard.type('Keep the selection.');
  await select(5, 8);
  await page.click('.fmt[data-fmt="italic"]');
  const sel6 = await page.evaluate(() => window.__work.editor.getSelection());
  const st6 = await structure();
  ok(sel6.start === 5 && sel6.end === 8 && st6.content[0].content[1].text === 'the' && st6.content[0].content[1].marks[0].type === 'em', 'clicking Italic on the bar italicised exactly the selected word and left the selection where it was');
  ok((await page.getAttribute('.fmt[data-fmt="italic"]', 'aria-pressed')) === 'true', 'and the bar shows the mark as on');
  await page.click('.fmt[data-fmt="h2"]');
  ok((await structure()).content[0].type === 'heading' && (await structure()).content[0].attrs.level === 2, 'H2 makes the paragraph a heading');
  await page.click('.fmt[data-fmt="link"]');
  await page.waitForTimeout(150);
  ok((await structure()).content[0].content[1].marks.some(m => m.type === 'link' && m.attrs.href === 'https://example.org/why'), 'Link puts an http(s) link on the selected words');
  await page.evaluate(() => window.__work.editor.command('link', 'javascript:alert(1)'));
  ok(!(await structure()).content[0].content[1].marks.some(m => m.type === 'link' && /javascript/.test(m.attrs.href)), 'an unsafe link scheme is refused by the editor');
  await saved();
  const id6 = await page.evaluate(() => window.__work.session.id);
  const bad6 = await put(id6, { title: '', title_is_manual: false, body: 'x', base_revision: (await getDoc(id6)).revision, base_fingerprint: (await getDoc(id6)).fingerprint, request_id: 'req_unsafe_' + Date.now(), doc_schema: 1, projection_version: 1,
    doc_json: { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'x', marks: [{ type: 'link', attrs: { href: 'javascript:alert(1)' } }] }] }] } });
  ok(bad6.status === 400 && bad6.data.error_class === 'unsafe_link', 'and the server refuses one too (400 unsafe_link)');
  const bad6b = await put(id6, { title: '', title_is_manual: false, body: 'x', base_revision: (await getDoc(id6)).revision, base_fingerprint: (await getDoc(id6)).fingerprint, request_id: 'req_schema9_' + Date.now(), doc_schema: 9, projection_version: 1, doc_json: { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'x', marks: [] }] }] } });
  ok(bad6b.status === 422 && bad6b.data.error_class === 'schema_unsupported', 'an unknown schema version is refused (422 schema_unsupported)');
  const bad6c = await put(id6, { title: '', title_is_manual: false, body: 'y', base_revision: (await getDoc(id6)).revision, base_fingerprint: (await getDoc(id6)).fingerprint, request_id: 'req_mismatch_' + Date.now(), doc_schema: 1, projection_version: 1, doc_json: { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'x', marks: [] }] }] } });
  ok(bad6c.status === 422 && bad6c.data.error_class === 'projection_mismatch', 'a structure that does not project to the text sent with it is refused (422 projection_mismatch)');

  // 7. find and replace: a count with its population; replace-all is one undo step
  await fresh();
  await page.keyboard.type('the cat and the dog and the end');
  await page.keyboard.press('ControlOrMeta+f');
  await page.waitForSelector('#findbar:not([hidden])');
  await page.fill('#find-input', 'the');
  await page.waitForTimeout(150);
  ok(/1 of 3/.test(await page.textContent('#find-count')), 'find counts the matches in this draft: ' + await page.textContent('#find-count'));
  const sel7 = await page.evaluate(() => window.__work.editor.getSelection());
  ok(sel7.text === 'the' && sel7.start === 0, 'and selects the first');
  await page.click('#find-next');
  ok((await page.evaluate(() => window.__work.editor.getSelection())).start === 12, 'Next moves to the second');
  await page.fill('#replace-input', 'THE');
  await page.click('#find-replace-all');
  await page.waitForTimeout(150);
  ok((await text()) === 'THE cat and THE dog and THE end', 'Replace all replaced every match');
  await page.evaluate(() => window.__work.editor.focus());
  await page.keyboard.press('ControlOrMeta+z');
  await page.waitForTimeout(100);
  ok((await text()) === 'the cat and the dog and the end', 'and one undo takes the whole replace-all back');
  await page.keyboard.press('End'); await page.keyboard.type(' the last');
  ok((await text()) === 'the cat and the dog and the end the last' && /of 4/.test(await page.textContent('#find-count')), 'typing with the bar open recounts (' + await page.textContent('#find-count') + ') and never moves the caret onto a match');
  await page.keyboard.press('Escape');
  ok(await page.isHidden('#findbar'), 'Escape closed the find bar');

  // 8. applying a suggestion: only to the target it was made for; one undo step; recorded; the repeated-phrase trap
  await fresh();
  await page.keyboard.type('The cat sat. The cat sat again, thinking of the throw.');
  await saved();
  const id8 = await page.evaluate(() => window.__work.session.id);
  await select(4, 7);                                                // the FIRST "cat"
  await page.click('button[data-action="analyze.decompose"]');
  await page.waitForSelector('#proposal-card');
  ok(/Sent as text only/.test(await page.textContent('#proposal-card')), 'the proposal says the words go as text only — no formatting is sent');
  await page.click('#proposal-card .btn.primary');
  await page.waitForFunction(() => document.querySelector('#results-body .state.good') !== null, null, { timeout: 60000, polling: 200 });
  await page.waitForTimeout(400);
  ok(/hasn’t changed since/.test(await page.textContent('#results-body')), 'the result is fresh: the writer’s own autosave acknowledgment did not make the capture stale');
  await page.click('.apply-block > summary');
  await page.waitForSelector('.apply-row .btn', { timeout: 5000 });
  const cand = await page.textContent('.apply-row .chip');
  ok(cand.length > 0 && (await page.$$('.apply-row .btn')).length >= 2, 'a candidate word offers Insert below and Replace for the words it was made from: ' + cand);
  const before8 = await text();
  await page.click('.apply-row .btn:has-text("Replace the selection")');
  await page.waitForTimeout(300);
  const after8 = await text();
  ok(after8 === 'The ' + cand + ' sat. The cat sat again, thinking of the throw.', 'Replace put the candidate where the FIRST cat stood and nowhere else: ' + JSON.stringify(after8.slice(0, 40)));
  await page.evaluate(() => window.__work.editor.focus());
  await page.keyboard.press('ControlOrMeta+z');
  await page.waitForTimeout(150);
  ok((await text()) === before8, 'the application was one undo step: one ⌘Z restores the draft exactly');
  await saved();
  await page.waitForTimeout(400);
  const ev8 = (await (await page.request.get(BASE + '/api/notebook/documents/' + id8 + '/events')).json()).events;
  ok(ev8.some(e => e.kind === 'applied' && e.detail.kind === 'replace' && e.detail.result && e.detail.result.operation_id) && ev8.some(e => e.kind === 'applied' && e.detail.kind === 'undo'), 'the record holds the application and its undo, linked to the operation: ' + ev8.map(e => e.detail.kind || e.kind).join(','));
  ok(ev8.filter(e => e.detail.kind === 'replace').every(e => typeof e.detail.committed_revision === 'number'), 'and the application was marked committed by the save that carried it');
  // the trap: the same word at the old offsets of a CHANGED draft
  await page.waitForTimeout(500);
  await page.click('.apply-block > summary');
  await page.waitForTimeout(150);
  const stale8 = await page.textContent('.apply-row');
  ok(/the draft changed since this result was made/.test(stale8) && !/^.*Replace the selection/.test(stale8.replace(/Replace the current selection/g, '')), 'after the draft changed, the old target is refused even though "cat" still stands at the old offsets — the target must be chosen again: ' + stale8.slice(0, 90));
  await page.evaluate(() => window.__work.editor.setSelection(0, 0));
  await page.click('.apply-row .btn:has-text("Replace the current selection")');
  await page.waitForTimeout(150);
  ok((await text()) === before8, 'with nothing selected, choosing the target again applies nothing');
  await select(17, 20);                                              // the SECOND "cat", chosen explicitly
  await page.click('.apply-row .btn:has-text("Replace the current selection")');
  await page.waitForTimeout(300);
  ok((await text()) === 'The cat sat. The ' + cand + ' sat again, thinking of the throw.', 'an explicitly reconfirmed target takes the candidate, and only there');
  await page.evaluate(() => window.__work.editor.focus()); await page.keyboard.press('ControlOrMeta+z');

  // 9. a document the schema cannot hold: carriage returns open read-only and exact; a disclosed conversion makes it structured, keeping the old head as a version
  const crId = 'doc_cr' + Date.now().toString(36);
  await put(crId, { title: '', title_is_manual: false, body: 'line one\r\nline two', base_revision: 0, base_fingerprint: '', request_id: 'req_seed_cr_' + Date.now() });
  await page.evaluate(id => window.__work.session.open(id), crId); await page.waitForTimeout(400);
  ok((await page.evaluate(() => window.__work.editor.mode())) === 'plain' && (await page.evaluate(() => window.__work.editor.isReadOnly())) && (await text()) === 'line one\r\nline two' && (await page.isHidden('#toolbar')), 'a CRLF document opens plain, read-only, exact, with the formatting bar off');
  ok(/carriage returns/.test(await page.textContent('.editor-note')) && /plain text/.test(await page.textContent('#doc-meta')), 'and the surface says why');
  await page.keyboard.press('ControlOrMeta+s'); await page.waitForTimeout(900);
  const cr0 = await getDoc(crId);
  ok(cr0.revision === 1 && cr0.body === 'line one\r\nline two', 'a checkpoint of the read-only document rewrites nothing');
  await page.click('.editor-note .btn');
  await page.waitForFunction(() => window.__work.session.revision === 2, null, { timeout: 8000, polling: 200 }).catch(() => {});
  const cr1 = await getDoc(crId);
  const crCps = (await (await page.request.get(BASE + '/api/notebook/documents/' + crId + '/checkpoints')).json()).checkpoints;
  const crEv = (await (await page.request.get(BASE + '/api/notebook/documents/' + crId + '/events')).json()).events;
  ok(cr1.revision === 2 && cr1.body === 'line one\nline two' && cr1.rich && (await page.evaluate(() => window.__work.editor.mode())) === 'structured', 'the disclosed conversion made revision 2 with LF line endings, structured');
  ok(crCps.some(c => c.reason === 'migration' && c.revision === 1) && crEv.some(e => e.kind === 'format_converted' && e.detail.from === 'plain'), 'the plain head was kept as a migration checkpoint and the conversion is an event');
  const ffId = 'doc_ff' + Date.now().toString(36);
  await put(ffId, { title: '', title_is_manual: false, body: 'page one\fpage two', base_revision: 0, base_fingerprint: '', request_id: 'req_seed_ff_' + Date.now() });
  await page.evaluate(id => window.__work.session.open(id), ffId); await page.waitForTimeout(400);
  await page.click('.plain-editor'); await page.keyboard.press('End'); await page.keyboard.type(' more');
  await saved();
  ok((await getDoc(ffId)).body === 'page one\fpage two more' && !(await getDoc(ffId)).rich, 'a document with a control character stays plain and editable, and the character is kept');

  // 10. versions: restore as a new revision keeps every version; a plain copy is a new document
  await fresh();
  await page.keyboard.type('First version.');
  await page.keyboard.press('ControlOrMeta+s');
  await saved(); await page.waitForTimeout(300);
  const id10 = await page.evaluate(() => window.__work.session.id);
  await page.keyboard.press('End'); await page.keyboard.type(' Then a second.');
  await select(0, 5); await page.keyboard.press('ControlOrMeta+b');
  await saved(); await page.waitForTimeout(300);
  const rev10 = (await getDoc(id10)).revision;
  await page.click('#doc-menu-btn'); await page.click('button[data-doc="versions"]');
  await page.waitForTimeout(800);
  const rows10 = await page.$$eval('#results-body .card.op', els => els.map(e => e.textContent));
  ok(rows10.length >= 2 && rows10.some(r => /Revision 1 · save/.test(r)), 'Versions lists the checkpoints by revision and reason: ' + rows10.map(r => (r.match(/Revision \d+ · \w+/) || ['?'])[0]).join(' | '));
  const idx = rows10.findIndex(r => /Revision 1 · save/.test(r));
  await (await page.$$('#results-body .card.op .linkish'))[idx].click();
  await page.waitForFunction(r => window.__work.session.revision > r, rev10, { timeout: 8000, polling: 200 }).catch(() => {});
  const d10 = await getDoc(id10);
  const cps10 = (await (await page.request.get(BASE + '/api/notebook/documents/' + id10 + '/checkpoints')).json()).checkpoints;
  ok(d10.revision === rev10 + 1 && d10.body === 'First version.' && (await text()) === 'First version.', 'restoring revision 1 made revision ' + d10.revision + ' with the old text; nothing was rewritten');
  ok(cps10.some(c => c.reason === 'restore' && c.revision === rev10) && cps10.some(c => c.revision === 1), 'the head before the restore was kept as a version, and revision 1 is still there');
  await page.click('#doc-menu-btn'); await page.click('button[data-doc="plaincopy"]');
  await page.waitForTimeout(800);
  const pcId = await page.evaluate(() => window.__work.session.id);
  ok(pcId !== id10 && !(await getDoc(pcId)).rich && (await getDoc(pcId)).body === 'First version.' && (await getDoc(id10)).rich, 'a plain copy is a NEW plain document; the original keeps its id and its structure');

  // 11. a composition (IME, dead key) completes before a save or a capture
  await fresh();
  await page.keyboard.type('Compose ');
  await page.evaluate(() => document.querySelector('.pm-editor').dispatchEvent(new CompositionEvent('compositionstart', { bubbles: true })));
  await page.waitForTimeout(50);
  ok(await page.evaluate(() => window.__work.editor.isComposing()), 'the editor reports a composition in progress (synthetic compositionstart — no engine here drives a real IME)');
  await page.evaluate(() => window.__work.session.flush());
  await page.waitForTimeout(200);
  ok(await page.evaluate(() => !window.__work.session.inflight && window.__work.session.status !== 'saving'), 'a save waits for the composition');
  await select(0, 7);
  await page.click('button[data-action="analyze.decompose"]');
  await page.waitForTimeout(300);
  ok((await page.$('#proposal-card')) === null && /composed/.test(await page.textContent('#toast')), 'and so does a capture: no proposal while composing');
  await page.evaluate(() => document.querySelector('.pm-editor').dispatchEvent(new CompositionEvent('compositionend', { bubbles: true })));
  await page.waitForTimeout(600);
  await saved();
  ok(/Saved \d/.test(await page.textContent('#doc-meta')), 'the save goes once the composition ends');

  // 12. exports are visibly plain / structured; pasted text keeps paragraphs and hard breaks the way the plain import reads
  await fresh();
  await page.keyboard.type('Export me.');
  await page.click('#doc-menu-btn'); await page.click('button[data-doc="export-text"]');
  await page.waitForTimeout(150);
  ok(/Exported as plain text/.test(await page.textContent('#toast')) && /not in a \.txt file/.test(await page.textContent('#toast')), 'the text export says it is plain and what a .txt file does not carry');
  const md = await page.evaluate(async () => { const m = await import('/work/document.js'); return m.toMarkdown({ type: 'doc', content: [{ type: 'heading', attrs: { level: 2 }, content: [{ type: 'text', text: 'T', marks: [] }] }, { type: 'bullet_list', content: [{ type: 'list_item', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'one ', marks: [] }, { type: 'text', text: 'two', marks: [{ type: 'strong' }] }] }] }] }, { type: 'blockquote', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'q', marks: [{ type: 'link', attrs: { href: 'https://e.org' } }] }] }] }] }); });
  ok(md === '## T\n\n- one **two**\n\n> [q](https://e.org)\n', 'Markdown keeps heading, list, bold, quote and link: ' + JSON.stringify(md));
  await page.evaluate(() => { const e = window.__work.editor; e.setSelection(e.getText().length, e.getText().length); });
  const pasted = await page.evaluate(() => {
    const dt = new DataTransfer(); dt.setData('text/plain', 'P1 line a\nP1 line b\n\nP2');
    const ev = new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true });
    document.querySelector('.pm-editor').dispatchEvent(ev);
    return window.__work.editor.getText();
  });
  ok(pasted === 'Export me.P1 line a\nP1 line b\n\nP2', 'pasted text keeps a single line break as a hard break and a blank line as a paragraph: ' + JSON.stringify(pasted));

  // 13. a long document stays responsive: a keystroke in a 20,000-word draft
  await fresh();
  const long = Array.from({ length: 400 }, (_, i) => 'Paragraph ' + i + ' ' + 'word '.repeat(49).trim()).join('\n\n');
  await page.evaluate(t => { window.__work.editor.setText(t, {}); window.__work.editor.setSelection(0, 0); window.__work.editor.focus(); }, long);
  await page.waitForTimeout(300);
  const t13 = await page.evaluate(async () => {
    const ed = window.__work.editor;
    const t0 = performance.now(); ed.structured.view.dispatch(ed.structured.view.state.tr.insertText('Z', 1)); const t1 = performance.now();   // the edit, with every handler it fires
    ed.structured._cache.doc = null; const t2 = performance.now(); ed.getText(); const t3 = performance.now();                              // the projection, uncached
    const payload = JSON.stringify(ed.getStructure()); const t4 = performance.now();                                                             // what a save carries
    return { edit: t1 - t0, project: t3 - t2, payload: t4 - t3, bytes: payload.length, words: ed.wordCount() };
  });
  await page.keyboard.type('abc');
  ok(t13.words >= 20000 && t13.edit < 250 && t13.project < 250 && t13.payload < 250, 'a ' + t13.words + '-word draft: an edit with its handlers ' + t13.edit.toFixed(1) + ' ms, the projection ' + t13.project.toFixed(1) + ' ms, the save payload (' + Math.round(t13.bytes / 1024) + ' KB) ' + t13.payload.toFixed(1) + ' ms');
  await noSave();

  // ---- slice G: the races and failures the instructions name (§11, "Races", "Safe application", "Recovery failure") ----
  const sess = () => page.evaluate(() => { const s = window.__work.session; return { id: s.id, seq: s.seq, ackSeq: s.ackSeq, inflight: !!s.inflight, inflightSeq: s.inflight ? s.inflight.seq : null, status: s.status, revision: s.revision, recovered: s.recovered, applications: s.applications.length }; });
  const docUrl = id => BASE + '/api/notebook/documents/' + id;
  const hold = (id, ms) => page.route(docUrl(id), async route => { await new Promise(r => setTimeout(r, ms)); await route.continue(); });
  const settledOn = () => page.waitForFunction(() => { const s = window.__work.session; return !s.inflight && s.seq === s.ackSeq && s.status === 'saved'; }, null, { timeout: 15000, polling: 100 });

  // 14. the editor's own last check: the words at the target must be the words the suggestion was made for, even when it is asked directly
  await fresh();
  await page.keyboard.type('The cat sat.');
  const r14 = await page.evaluate(() => window.__work.editor.applyText({ start: 4, end: 7, expect: 'dog', text: 'ZZ', mode: 'replace' }));
  ok(r14 && r14.ok === false && (await text()) === 'The cat sat.', 'the editor’s own last check refuses a target whose words are not the words the suggestion was made for, and writes nothing: ' + JSON.stringify(r14));

  // 15. a slow save acknowledgment, more typing during it, then a switch to another document: every word lands before the switch, and reopening recovers nothing because there is nothing to recover
  await fresh();
  await page.keyboard.type('Slow words');
  await settledOn();
  const id15 = (await sess()).id;
  await hold(id15, 1500);
  await page.keyboard.type(' one');
  await page.waitForFunction(() => window.__work.session.inflight !== null, null, { timeout: 5000, polling: 50 });
  await page.keyboard.type(' two');
  const mid15 = await sess();
  ok(mid15.inflight && mid15.seq > mid15.inflightSeq, 'more words were typed while the save was in flight (seq ' + mid15.seq + ' > the request’s ' + mid15.inflightSeq + ')');
  const other15 = 'doc_other15' + Date.now().toString(36);
  await put(other15, { title: '', title_is_manual: false, body: 'Other document.', base_revision: 0, base_fingerprint: '', request_id: 'req_seed_o15_' + Date.now() });
  const t15 = Date.now();
  await page.evaluate(id => window.__work.session.open(id), other15);
  const took15 = Date.now() - t15;
  ok((await sess()).id === other15 && (await text()) === 'Other document.', 'the switch happened (' + took15 + ' ms: it waited for the held save and sent the rest)');
  const d15 = await getDoc(id15);
  ok(d15.body === 'Slow words one two', 'every word typed before the switch is on the server — the held save’s and the words typed during it: ' + JSON.stringify(d15.body));
  await page.unroute(docUrl(id15));
  await page.evaluate(id => window.__work.session.open(id), id15);
  await page.waitForTimeout(400);
  const back15 = await sess();
  ok((await text()) === 'Slow words one two' && back15.recovered === false && back15.status === 'saved' && (await getDoc(id15)).revision === d15.revision, 'reopening it recovers nothing and rewrites nothing: the envelope held exactly the head (revision ' + d15.revision + ' stands)');

  // 16. a reply that arrives after the switch stopped waiting still repairs the envelope it belongs to: the words it carried are acknowledged against the head it made, the words typed after it stay unsent and are recovered on reopening
  await fresh();
  await page.keyboard.type('Late reply');
  await settledOn();
  const id16 = (await sess()).id;
  await hold(id16, 6500);
  await page.keyboard.type(' alpha');
  await page.waitForFunction(() => window.__work.session.inflight !== null, null, { timeout: 5000, polling: 50 });
  await page.keyboard.type(' beta');
  await page.waitForTimeout(200);
  const t16 = Date.now();
  await page.evaluate(id => window.__work.session.open(id), other15);
  const took16 = Date.now() - t16;
  ok(took16 >= 3500 && took16 < 6000 && (await sess()).id === other15, 'the switch waited its bound for the held save and then went on rather than holding the room (' + took16 + ' ms)');
  await page.waitForTimeout(7000 - took16 + 800);
  await page.unroute(docUrl(id16));
  const d16 = await getDoc(id16);
  ok(d16.body === 'Late reply alpha', 'the held save landed after the switch: the server holds the words that request carried and not the words typed after it: ' + JSON.stringify(d16.body));
  const env16 = await page.evaluate(async id => { const r = await import('/work/recovery.js'); const envs = await r.forDocument(id); return envs.filter(e => !e.abandoned)[0] || null; }, id16);
  ok(env16 && env16.base_revision === d16.revision && env16.ack_seq < env16.seq && env16.body === 'Late reply alpha beta' && !env16.pending, 'the late reply repaired its envelope: based on the head it made, its own words acknowledged, the words typed after it still unsent, no request pending: ' + JSON.stringify(env16 && { base: env16.base_revision, head: d16.revision, seq: env16.seq, ack: env16.ack_seq }));
  await page.evaluate(id => window.__work.session.open(id), id16);
  await settledOn();
  ok((await text()) === 'Late reply alpha beta' && (await getDoc(id16)).body === 'Late reply alpha beta' && (await sess()).recovered === true, 'reopening it recovers the words typed after the send, from the envelope, and saves them');

  // 17. two tabs on one document: the second tab's save moves the head; the first tab's save is refused (409); both copies are kept and the choice is the owner's
  await fresh();
  await page.keyboard.type('Shared draft');
  await settledOn();
  const id17 = (await sess()).id;
  const page2 = await ctx.newPage();
  page2.on('pageerror', e => errs.push('tab two: ' + String(e.message)));
  await page2.goto(BASE + '/work');
  await page2.waitForSelector('.pm-editor');
  await page2.evaluate(id => window.__work.session.open(id), id17);
  await page2.waitForTimeout(300);
  ok((await page2.evaluate(() => window.__work.session.tab)) !== (await page.evaluate(() => window.__work.session.tab)), 'the second tab has its own tab id, so the two envelopes never overwrite each other');
  await page2.click('.pm-editor');
  await page2.keyboard.press('End');
  await page2.keyboard.type(' from tab two');
  await page2.waitForFunction(() => { const s = window.__work.session; return !s.inflight && s.seq === s.ackSeq && s.status === 'saved'; }, null, { timeout: 15000, polling: 100 });
  ok((await getDoc(id17)).body === 'Shared draft from tab two', 'the second tab saved: the head moved');
  await page.click('.pm-editor');
  await page.keyboard.press('End');
  await page.keyboard.type(' from tab one');
  await page.waitForFunction(() => window.__work.session.status === 'conflict', null, { timeout: 8000, polling: 100 });
  ok(/Saved elsewhere since this copy was opened/.test(await page.textContent('#doc-meta')) && /Nothing was overwritten/.test(await page.textContent('#results-body')), 'the first tab’s save is refused and the room says so, with the choice beside the draft');
  ok((await getDoc(id17)).body === 'Shared draft from tab two' && (await text()) === 'Shared draft from tab one', 'nothing was overwritten: the head is the second tab’s and the first tab still holds its own words');
  await page.click('#results-body button:has-text("Keep mine as a new document")');
  await settledOn();
  const idKept = (await sess()).id;
  ok(idKept !== id17 && (await getDoc(idKept)).body === 'Shared draft from tab one' && (await getDoc(id17)).body === 'Shared draft from tab two', 'Keep mine as a new document: both copies are on the server under their own ids');
  await page2.close();

  // 18. an application while a save is in flight, then its undo: the reply to the older save cannot commit the application; the save that carries it commits it; the undo lands as the next revision
  await fresh();
  await page.keyboard.type('The cat sat here.');
  await settledOn();
  const id18 = (await sess()).id;
  await select(4, 7);
  await page.click('button[data-action="analyze.decompose"]');
  await page.waitForSelector('#proposal-card');
  await page.click('#proposal-card .btn.primary');
  await page.waitForFunction(() => document.querySelector('#results-body .state.good') !== null, null, { timeout: 60000, polling: 200 });
  await page.waitForTimeout(400);
  await page.click('.apply-block > summary');
  await page.waitForSelector('.apply-row .btn', { timeout: 5000 });
  const cand18 = await page.textContent('.apply-row .chip');
  await hold(id18, 1500);
  await page.evaluate(() => { window.__work.session.checkpoint('save'); });          // a save in flight (held) that does not change the words
  await page.waitForFunction(() => window.__work.session.inflight !== null, null, { timeout: 5000, polling: 50 });
  await page.click('.apply-row .btn:has-text("Replace the selection")');
  await page.waitForTimeout(150);
  const mid18 = await sess();
  ok((await text()) === 'The ' + cand18 + ' sat here.' && mid18.inflight && mid18.applications === 1, 'the candidate was applied while the older save was still in flight, and the application is not yet committed');
  await settledOn();
  await page.waitForTimeout(400);
  await page.unroute(docUrl(id18));
  const ev18a = (await (await page.request.get(docUrl(id18) + '/events')).json()).events.filter(e => e.kind === 'applied');
  const rep18 = ev18a.find(e => e.detail.kind === 'replace');
  ok(rep18 && typeof rep18.detail.committed_revision === 'number' && rep18.detail.committed_revision === (await sess()).revision, 'the save that carried the application committed it, at the revision it made: ' + (rep18 && rep18.detail.committed_revision));
  await page.evaluate(() => window.__work.editor.focus());
  await page.keyboard.press('ControlOrMeta+z');
  await page.waitForTimeout(150);
  ok((await text()) === 'The cat sat here.', 'one undo takes the application back');
  await settledOn();
  await page.waitForTimeout(400);
  const ev18b = (await (await page.request.get(docUrl(id18) + '/events')).json()).events.filter(e => e.kind === 'applied');
  const und18 = ev18b.find(e => e.detail.kind === 'undo');
  ok(und18 && und18.detail.committed_revision === rep18.detail.committed_revision + 1 && (await getDoc(id18)).body === 'The cat sat here.', 'the undo is recorded and committed as the next revision, and the head holds the words before the application');

  // 19. a browser whose storage refuses: the room never claims a copy it does not have; the server save still lands; with the server gone it says the words are nowhere but this page
  const ctx19 = await pairedContext(browser, { viewport: { width: 1440, height: 900 } });
  await ctx19.addInitScript(() => { Object.defineProperty(window, 'indexedDB', { get() { throw new Error('storage is unavailable'); } }); });
  const page19 = await ctx19.newPage();
  const errs19 = [];
  page19.on('pageerror', e => errs19.push(String(e.message)));
  await page19.goto(BASE + '/work');
  await page19.waitForSelector('.pm-editor');
  await page19.evaluate(() => window.__work.session.newDocument(''));      // a fresh context reopens the record's latest document otherwise
  await page19.waitForTimeout(150);
  await page19.click('.pm-editor');
  await page19.keyboard.type('Nowhere but here');
  await page19.waitForFunction(() => { const s = window.__work.session; return !s.inflight && s.seq === s.ackSeq && s.status === 'saved'; }, null, { timeout: 15000, polling: 100 });
  const id19 = await page19.evaluate(() => window.__work.session.id);
  const meta19 = await page19.textContent('#doc-meta');
  const d19 = await getDoc(id19);
  ok(/Saved \d/.test(meta19) && /keeps no recovery copy/.test(meta19) && d19.body === 'Nowhere but here', 'with storage refusing, the server save lands and the header says this browser keeps no recovery copy: ' + JSON.stringify(meta19) + ' · server: ' + JSON.stringify(d19.body) + ' id ' + id19);
  await page19.route(docUrl(id19), route => route.abort());
  await page19.keyboard.type(' and gone');
  await page19.waitForFunction(() => window.__work.session.status === 'nolocal', null, { timeout: 8000, polling: 100 });
  const meta19b = await page19.textContent('#doc-meta');
  const d19b = await getDoc(id19);
  ok(/refused to keep a copy/.test(meta19b) && !/Saved locally/.test(meta19b) && d19b.body === 'Nowhere but here', 'with the server gone as well, the room says the words are not on the server and this browser kept no copy — never "saved locally" — and the last complete copy stands on the server: ' + JSON.stringify(meta19b) + ' · server: ' + JSON.stringify(d19b.body));
  ok(errs19.length === 0, 'no page errors with storage unavailable: ' + JSON.stringify(errs19));
  await ctx19.close();

  ok(errs.length === 0, 'no page errors across the editor journey: ' + JSON.stringify(errs));
  await browser.close();
  finish(NAME);
})().catch(async e => { ok(false, 'journey crashed: ' + (e && e.stack || e)); finish(NAME); });
