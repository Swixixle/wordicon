// The connected-instruments journey (block 107): the Investigation page
// against two mock producers on loopback — the registry with its pinned
// keys and a credential named by reference; Check and Locate importing
// nothing; an import by id and one by a pasted address of the configured
// origin; a foreign address refused; the exact-bytes door; re-verification;
// a package with one changed byte kept UNVERIFIED and seating nothing; a
// producer that answers 500 or an HTML page landing as a named failure and
// never as "nothing found"; a room whose seats stay apart under each
// instrument's own labels; three name-match proposals granting nothing;
// Reject and Leave unresolved converging nothing; Declare producing the
// two-instrument timeline; the chooser reading an Open Case address as its
// import and landing here with nothing fetched; About & proof naming the
// instruments. The browser never contacts a producer — the server does,
// on a press — so every browser request stays on the scratch origin.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { BASE, DIR, ok, launch, pairedContext, finish, place } = require('./lib');
const healthyVault = { initialized: true, last_seal_at: new Date(Date.now() - 4 * 60000).toISOString(), last_drill_at: new Date(Date.now() - 86400000).toISOString(), cloud: 'iCloud', n_vaults: 31, total_bytes: 125638 * 1024, failure: '', stale_red: false, dirty_seconds: 0 };
const PPORT = fs.readFileSync(path.join(DIR, 'producer_port'), 'utf8').trim();
const PBASE = 'http://127.0.0.1:' + PPORT;
const FX = path.resolve(__dirname, '..', 'fixtures', 'federation');
const OC = JSON.parse(fs.readFileSync(path.join(FX, 'open_case.exemplar.deposition.json'), 'utf8'));
const EA = JSON.parse(fs.readFileSync(path.join(FX, 'ethicalalt.exemplar.deposition.json'), 'utf8'));
const OC_ID = OC.object.id, EA_ID = EA.object.id;

(async () => {
  const browser = await launch();
  const ctx = await pairedContext(browser); const page = await ctx.newPage();
  await page.route('**/api/vault/status', r => r.fulfill({ json: healthyVault }));
  const posts = []; page.on('request', r => { if (r.method() !== 'GET') posts.push(r.method() + ' ' + r.url().replace(BASE, '')); });
  const errs = []; page.on('pageerror', e => errs.push(String(e)));
  page.on('dialog', d => d.type() === 'prompt' ? d.accept('the owner declares — journey') : d.accept());
  const api = async (p) => (await page.request.get(BASE + p)).json();
  const text = (sel) => page.evaluate((s) => (document.querySelector(s) || { textContent: '' }).textContent.replace(/\s+/g, ' ').trim(), sel);
  const attempts = async () => (await api('/api/connectors')).connectors.map(c => [c.connector_id, c.status, c.depositions]);

  // ---- the page, the registry, nothing on load
  await page.goto(BASE + '/investigation'); await page.waitForTimeout(1200);
  const reg = await text('#connectors');
  ok(/Open Case \(scratch\)/.test(reg) && /EthicalAlt \(scratch\)/.test(reg) && /env:JOURNEY_OPEN_CASE_KEY/.test(reg) && !/jjjjjj/.test(reg) && (reg.match(/ed25519:sha256:/g) || []).length >= 2,
    'the registry lists both instruments with a pinned key fingerprint and a credential named by reference, no value: ' + reg.slice(0, 160));
  ok(/read-only \(locate, import, verify\)/.test(reg) && /never tried/.test(reg), 'each instrument says what it can do (read-only) and that nothing has been tried: ' + (reg.match(/never tried/g) || []).length);
  ok(posts.length === 0, 'opening the page posted nothing — no fetch on load: ' + JSON.stringify(posts));
  ok((await api('/api/depositions')).count === 0, 'custody is empty before any press');

  // ---- Check and Locate: the producer is reached; nothing is imported
  await page.click('button:has-text("Check reachability")'); await page.waitForTimeout(900);
  const chk = await text('[data-checknote="open-case-dev"]');
  ok(/reachable — the producer lists 1 object/.test(chk) && /nothing was imported/.test(chk), 'Check reaches Open Case through the credential and imports nothing: ' + chk);
  ok((await api('/api/depositions')).count === 0, 'custody is still empty after Check');
  await page.selectOption('#imp-connector', 'ethicalalt-dev');
  await page.fill('#loc-query', 'exemplar'); await page.click('button:has-text("Locate")'); await page.waitForTimeout(900);
  const loc = await text('#loc-note'), locr = await text('#loc-results');
  ok(/2 object\(s\) in the producer's own list/.test(loc) && /nothing imported/.test(loc) && /Exemplar Holdings/.test(locr) && /exemplar-legacy-co/.test(locr), 'Locate lists the producer\'s own objects and imports nothing: ' + loc);

  // ---- import by id (EthicalAlt), by address (Open Case), a foreign address refused
  await page.fill('#imp-object', EA_ID); await page.click('button:has-text("Fetch and import the signed record")'); await page.waitForTimeout(1200);
  const n1 = await text('#imp-note');
  ok(/imported and VERIFIED against the pinned key/.test(n1) && /dep_/.test(n1), 'importing by id verifies the EthicalAlt package under the pinned key: ' + n1);
  await page.selectOption('#imp-connector', 'open-case-dev');
  await page.fill('#imp-object', PBASE + '/cases/' + OC_ID + '?tab=evidence'); await page.click('button:has-text("Fetch and import the signed record")'); await page.waitForTimeout(1200);
  const n2 = await text('#imp-note');
  ok(/imported and VERIFIED/.test(n2), 'importing by a pasted address of the configured origin verifies the Open Case package: ' + n2);
  const deps = (await api('/api/depositions')).depositions;
  const dOC = deps.find(d => d.producer === 'open_case'), dEA = deps.find(d => d.producer === 'ethicalalt');
  ok(deps.length === 2 && dOC && dEA && dOC.status === 'current' && dEA.status === 'current' && dOC.signature_ok && dEA.signature_ok, 'two depositions in custody, both current and verified');
  await page.fill('#imp-object', 'https://evil.example/cases/' + OC_ID); await page.click('button:has-text("Fetch and import the signed record")'); await page.waitForTimeout(800);
  const n3 = await text('#imp-note');
  ok(/does not belong to this connector's configured origin/.test(n3) && /nothing was fetched/.test(n3) && (await api('/api/depositions')).count === 2, 'a foreign address is refused and nothing is fetched: ' + n3);
  const tbl = await text('#depositions');
  ok(/verified/.test(tbl) && /current/.test(tbl) && /exact bytes/.test(tbl) && /re-verify/.test(tbl) && /record/.test(tbl), 'the custody table shows verification, status and the doors');

  // ---- the doors: exact bytes, re-verify, the record
  const raw = await (await page.request.get(BASE + '/api/depositions/' + dOC.deposition_id + '/bytes')).body();
  const sha = crypto.createHash('sha256').update(raw).digest('hex');
  ok(sha === dOC.sha256 && raw.equals(fs.readFileSync(path.join(FX, 'open_case.exemplar.deposition.json'))), 'the exact-bytes door returns the bytes received, byte-identical to the producer\'s package, with their hash');
  await page.click(`tr[data-dep="${dOC.deposition_id}"] a:has-text("re-verify")`); await page.waitForTimeout(700);
  const rv = await text(`[data-vnote="${dOC.deposition_id}"]`);
  ok(/re-verified under the current pinned keys/.test(rv) && /bytes identical to import/.test(rv), 're-verify checks the stored bytes against the current keys and writes nothing: ' + rv);
  await page.click(`tr[data-dep="${dEA.deposition_id}"] a:has-text("record")`); await page.waitForTimeout(700);
  const rec = await text('#dep-detail');
  ok(/producer ethicalalt/.test(rec) && /research depth deep_research/.test(rec) && /concern level moderate \(EthicalAlt's assessment\)/.test(rec) && /source_stated/.test(rec) && /PARTIAL — 1 of 4 incidents without a direct source URL/.test(rec) && /never completeness/.test(rec),
    'the record door shows the producer\'s own labels attributed to it, its stated times, and its partial provenance as its own counts: ' + rec.slice(0, 200));

  // ---- a package with one changed byte: kept, UNVERIFIED, seating nothing
  const tampered = JSON.parse(JSON.stringify(EA)); tampered.payload.profile.overall_concern_level = 'clean';
  await page.selectOption('#imp-connector', 'ethicalalt-dev');
  await page.evaluate(() => { document.querySelectorAll('details').forEach(d => { d.open = true; }); });
  await page.fill('#pkg-body', JSON.stringify(tampered)); await page.click('button:has-text("Import these bytes")'); await page.waitForTimeout(1000);
  const pk = await text('#pkg-note');
  ok(/kept UNVERIFIED/.test(pk) && /payload_sha256 does not match/.test(pk), 'a package with one changed byte is kept UNVERIFIED with the reason named: ' + pk);
  const deps2 = (await api('/api/depositions')).depositions; const dBad = deps2.find(d => !d.signature_ok);
  ok(deps2.length === 3 && dBad && dBad.status === 'unverified' && !dBad.prior_version_of && dEA.status === 'current' && (await api('/api/depositions/' + dBad.deposition_id)).representation === null,
    'the unverified package has no representation, no version link, and casts nothing over the verified deposition');

  // ---- a producer that fails: a named failure, never "nothing found"; custody untouched
  await page.selectOption('#imp-connector', 'ethicalalt-dev');
  for (const [oid, want] of [['server-boom', 'http_5xx'], ['gateway-502', 'html_error_page'], ['not-json', 'not_json'], ['redirect-me', 'redirect_refused'], ['missing-one', 'http_404']]) {
    await page.selectOption('#imp-connector', 'ethicalalt-dev');   // the registry re-renders after each attempt (its standing changed), so re-choose the instrument
    await page.fill('#imp-object', oid); await page.click('button:has-text("Fetch and import the signed record")'); await page.waitForTimeout(900);
    const n = await text('#imp-note');
    ok(new RegExp('not imported — ' + want).test(n) && !/nothing found/i.test(n), `${oid} lands as ${want}, not as nothing found: ` + n.slice(0, 120));
  }
  ok((await api('/api/depositions')).count === 3, 'the failures imported nothing');
  const st = await attempts();
  ok(st.some(x => x[0] === 'ethicalalt-dev' && /last attempt failed: http_404/.test(x[1])) && st.some(x => x[0] === 'open-case-dev' && /reachable at last attempt/.test(x[1])),
    'each instrument keeps its own standing — one failing does not mark the other: ' + JSON.stringify(st));
  await page.waitForTimeout(600);
  const reg2 = await text('#connectors');
  ok(/last attempt failed: http_404/.test(reg2), 'the registry shows the failure on the instrument');

  // ---- the room: seats apart, the producer's own labels, the gaps distinct
  await page.fill('#room-title', 'Exemplar Holdings — instruments side by side'); await page.click('button:has-text("Create an Investigation Room")'); await page.waitForTimeout(1000);
  ok(!(await page.evaluate(() => document.getElementById('room-card').hidden)), 'the room opens');
  for (const id of [dOC.deposition_id, dEA.deposition_id, dBad.deposition_id]) {
    await page.selectOption('#room-add-dep', id); await page.click('button:has-text("Add this deposition to the room")'); await page.waitForTimeout(800);
  }
  const rid = new URL(page.url()).searchParams.get('room');
  const room = await api('/api/investigations/' + rid);
  const seats = Object.fromEntries(room.seats.map(s => [s.kind, s.items.length]));
  ok(seats.evidence === 3 && seats.signal === 1 && seats.incident === 4 && seats.allegation_response === 1 && seats.gap === 9 && seats.dispute === 0 && seats.ruling === 0 && room.unverified.length === 1,
    'the seats are filled apart by instrument and kind, the unverified package listed apart: ' + JSON.stringify(seats));
  const seatText = await text('#room-seats');
  ok(/CONTEXTUAL \(Open Case's classifier\)/.test(seatText) && /ALLEGED \(Open Case's classifier\)/.test(seatText) && /confidence high \(EthicalAlt\)/.test(seatText) && /Open Case's pattern engine — a signal, not a Nikodemus finding/.test(seatText),
    'each seat item carries its instrument\'s own label, attributed to that instrument');
  ok(/documented absence/.test(seatText) && /gap_documented/.test(seatText) && /search_failed/.test(seatText) && /source_unavailable/.test(seatText) && /missing_source_url/.test(seatText) && /researcher_gap/.test(seatText),
    'the documented absence, the failed search and the producer\'s own gaps stay distinct');
  ok(/Type 3/.test(seatText), 'the allegation stays paired with its documented response type');
  const unv = await text('#room-unverified');
  ok(/unverified — nothing from these is seated/.test(unv) && /payload_sha256 does not match/.test(unv), 'the unverified package is named apart with its reason, and seats nothing');
  ok(/No relationship proposed/.test(await text('#room-relationships')) && /nothing converges until the owner declares/.test(await text('#room-convergence')), 'before the owner acts there is no relationship and no convergence');

  // ---- proposals grant nothing; Reject and Leave unresolved converge nothing; Declare converges
  await page.click('button:has-text("Propose relationships")'); await page.waitForTimeout(1000);
  const rels = (await api('/api/investigations/' + rid)).relationships;
  ok(rels.length === 3 && rels.every(r => r.state === 'proposed_same_entity' && r.origin === 'mechanical' && /names are not identities/.test(r.basis)), 'three exact name matches are proposed, each saying names are not identities');
  ok(/nothing converges until the owner declares/.test(await text('#room-convergence')) && (await api('/api/investigations/' + rid + '/convergence')).timeline.length === 0, 'a proposal alone converges nothing');
  const subjectProp = rels.find(r => /open_case:case:/.test(r.b) || /open_case:case:/.test(r.a));
  const others = rels.filter(r => r !== subjectProp);
  await page.click(`[data-proposal="${others[0].proposal_id}"] button.reject`); await page.waitForTimeout(900);
  await page.click(`[data-proposal="${others[1].proposal_id}"] button.unresolved`); await page.waitForTimeout(900);
  const cv0 = await api('/api/investigations/' + rid + '/convergence');
  ok(cv0.timeline.length === 0 && cv0.links.length === 0 && /nothing converges/.test(cv0.note), 'Reject and Leave unresolved converge nothing');
  const relText = await text('#room-relationships');
  ok(/rejected_match/.test(relText) && /unresolved/.test(relText) && (relText.match(/ruled by the owner/g) || []).length === 2, 'the two rulings are shown as the owner\'s, apart from a declaration');
  await page.click(`[data-proposal="${subjectProp.proposal_id}"] button:has-text("Declare")`); await page.waitForTimeout(1200);
  const cv = await api('/api/investigations/' + rid + '/convergence');
  ok(cv.links.length === 1 && cv.links[0].state === 'declared_same_entity' && cv.timeline.length === 7 && cv.overlaps.length === 2 && cv.interpretation.built === false,
    'Declare produces the two instruments\' dated records and the in-window pairs, with interpretation not built: ' + cv.timeline.length + ' rows, ' + cv.overlaps.length + ' overlaps');
  const cvText = await text('#room-convergence');
  ok(/declared_same_entity/.test(cvText) && /within the 90-day window/.test(cvText) && /not a claim of relation/.test(cvText) && /not built/.test(cvText) && /Open Case's classifier/.test(cvText),
    'the convergence panel shows the timeline with each row\'s label owner and the mechanical sentences');
  const rulingSeat = (await api('/api/investigations/' + rid)).seats.find(s => s.kind === 'ruling');
  ok(rulingSeat.items.length === 3 && rulingSeat.items.every(i => i.producer === 'nikodemus'), 'the owner\'s three rulings sit in their own seat');
  const rulings = await api('/api/identity/proposals');
  ok((rulings.rulings || []).every(r => r.by === 'owner'), 'every ruling is recorded as the owner\'s');

  // ---- the chooser: an Open Case address reads as its import and lands here with nothing fetched
  const attBefore = JSON.stringify(await attempts());
  await page.goto(BASE + '/'); await page.waitForTimeout(1200);
  await page.fill('#input-text', PBASE + '/cases/' + OC_ID); await page.dispatchEvent('#input-text', 'input'); await page.waitForTimeout(900);
  const c = await page.evaluate(() => ({ reading: document.getElementById('destination-reading').textContent.replace(/\s+/g, ' '),
    chips: Array.from(document.querySelectorAll('#destination-chips .dest')).map(b => ({ id: b.dataset.dest, suggested: b.classList.contains('suggested'), disabled: b.disabled, text: b.textContent.replace(/\s+/g, ' ').trim() })) }));
  const imp = c.chips.find(x => x.id === 'import_open_case');
  ok(/Reads as a web address/.test(c.reading) && imp && imp.suggested && !imp.disabled && !c.chips.some(x => x.id === 'import_ethicalalt'), 'the address of the configured Open Case reads as its import, highlighted, the other producer\'s import not offered: ' + c.chips.map(x => x.id).join(','));
  await page.click('#destination-chips .dest[data-dest="import_open_case"]'); await page.waitForTimeout(1500);
  const u = new URL(page.url());
  ok(u.pathname === '/investigation' && u.searchParams.get('object') === OC_ID && u.searchParams.get('connector') === 'open-case-dev', 'choosing the import lands on the Investigation page with the address and the recognized object carried: ' + u.search.slice(0, 120));
  // slice 2: the destination opens the Investigation Room inside the shell,
  // so the words that sent you there are still in the box behind it
  const inv = await place(page, '/investigation');
  ok(!!inv, 'the import destination opened the Investigation Room inside the shell');
  const pre = await inv.evaluate(() => ({ obj: document.getElementById('imp-object').value, note: document.getElementById('imp-note').textContent, conn: document.getElementById('imp-connector').value }));
  ok(pre.obj.includes(OC_ID) && /nothing has been fetched/.test(pre.note) && pre.conn === 'open-case-dev' && JSON.stringify(await attempts()) === attBefore, 'the form is pre-filled and nothing was fetched: ' + pre.note);
  await page.goto(BASE + '/'); await page.waitForTimeout(1000);
  await page.fill('#input-text', 'Exemplar Holdings'); await page.dispatchEvent('#input-text', 'input'); await page.waitForTimeout(900);
  const chips2 = await page.evaluate(() => Array.from(document.querySelectorAll('#destination-chips .dest')).map(b => ({ id: b.dataset.dest, disabled: b.disabled, unbuilt: b.classList.contains('unbuilt') })));
  ok(['look_ethicalalt', 'search_open_case', 'investigation_room'].every(id => chips2.some(x => x.id === id && !x.disabled)), 'a name offers the instrument doors as available: ' + chips2.map(x => x.id).join(','));

  // ---- About & proof names the instruments; the Rooms place has the door
  await page.evaluate(() => { document.getElementById('about-panel').open = true; }); await page.waitForTimeout(1200);
  const about = await text('#about-instruments');
  ok(/Open Case \(scratch\) \(open_case, 1 key pinned, credential env:JOURNEY_OPEN_CASE_KEY\)/.test(about) && /3 deposition\(s\)/.test(about) && /1 room\(s\)/.test(about) && /identity ruling\(s\)/.test(about) && /manual pull only/.test(about) && !/jjjj/.test(about),
    'About & proof states the registry, custody and rulings, the credential by reference: ' + about.slice(0, 200));
  ok(/Nikodemus can hold what your other instruments produce/.test(await text('#about-panel')), 'the constitution carries the instruments paragraph');
  ok(await page.evaluate(() => !!document.querySelector('#rooms-area a[href="/investigation"]')), 'the Rooms place has the door to the instruments');
  ok(errs.length === 0, 'no page errors: ' + JSON.stringify(errs.slice(0, 3)));
  await browser.close();
  finish('federation');
})().catch(e => { console.log('FAIL journey crashed: ' + (e && e.stack || e)); process.exit(1); });
