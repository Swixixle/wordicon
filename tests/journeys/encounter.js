// The encounter journey (block 104), after the ruling journeys: the
// owner turns encounter recording ON from About & proof (a confirmed
// action; the flip is recorded), opens a shelf entry (one owner_opened
// row, ids only), turns it OFF (recorded), and nothing more is written.
// Then the Recovery Review's remaining case is ruled "not enough
// survives": Home carries it as a quiet Unresolved line (not a ruling
// due) with the review's door, the review lists it as reopenable, and a
// later Accept with a definition appends a ruling that cites the
// unresolved one. Prints one line per check; exits 1 on any failure.
const { BASE, ok, launch, pairedContext, finish, place } = require('./lib');
const healthyVault = { initialized: true, last_seal_at: new Date(Date.now() - 4 * 60000).toISOString(), last_drill_at: new Date(Date.now() - 86400000).toISOString(), cloud: 'iCloud', n_vaults: 31, total_bytes: 125638 * 1024, failure: '', stale_red: false, dirty_seconds: 0 };

(async () => {
  const browser = await launch();
  const ctx = await pairedContext(browser); const page = await ctx.newPage();
  await page.route('**/api/vault/status', r => r.fulfill({ json: healthyVault }));
  const posts = []; page.on('request', r => { if (r.method() !== 'GET') posts.push(r.method() + ' ' + r.url().replace(BASE, '')); });
  const errs = []; page.on('pageerror', e => errs.push(String(e)));
  const dialogs = []; page.on('dialog', d => { dialogs.push(d.message()); d.accept(); });
  const api = async (p) => (await page.request.get(BASE + p)).json();

  // ---- the switch: on, by a visible confirmed action; the flip recorded ----
  await page.goto(BASE + '/'); await page.waitForTimeout(1500);
  await page.evaluate(() => openAbout()); await page.waitForTimeout(900);
  const before = await api('/api/encounter/switch');
  ok(before.on === false && before.flips === 0, 'recording is off with no flips before the owner acts');
  await page.click('#encounter-toggle'); await page.waitForTimeout(900);
  ok(dialogs.length === 1 && /Turn encounter recording ON\?/.test(dialogs[0]) && /No text/.test(dialogs[0]) && /flip itself is recorded/.test(dialogs[0]), 'turning on asks a plain question that says what will be kept: ' + (dialogs[0] || '').slice(0, 80));
  const on = await api('/api/encounter/switch');
  ok(on.on === true && on.flips === 1 && !!on.since, 'the switch is on and the flip is the first row: ' + JSON.stringify([on.on, on.flips]));
  const aboutOn = await page.evaluate(() => ({ state: document.getElementById('encounter-state').textContent, btn: document.getElementById('encounter-toggle').textContent, note: document.getElementById('encounter-note').textContent }));
  ok(/^on — since /.test(aboutOn.state) && aboutOn.btn === 'Turn off' && aboutOn.note === 'recorded.', 'About shows on, since when, and offers "Turn off": ' + aboutOn.state);
  // ---- one door, one row: ids only ----
  await page.evaluate(() => { HOME = null; }); await page.evaluate(() => loadHome()); await page.waitForTimeout(800);
  const homeOn = await api('/api/home');
  ok(homeOn.encounter_recording === true, 'Home carries the switch state once on');
  await page.click('#continue-area .cont[data-id="concept_fix_bridge"] .resume a'); await page.waitForTimeout(1000);
  const log1 = await api('/api/encounters');
  ok(log1.total === 1 && log1.encounters[0].type === 'owner_opened' && log1.encounters[0].subject === 'acc_bridgefix' && log1.encounters[0].via === 'home_legacy_bridge'
     && Object.keys(log1.encounters[0]).sort().join(',') === 'at,encounter_id,epoch,object,subject,trace_id,type,via',
     'opening the bridged entry recorded one owner_opened row by id, nothing else: ' + JSON.stringify(log1.encounters[0]));
  ok(!JSON.stringify(log1.encounters).includes('Lantern Debt'), 'the row carries no title, no text');
  ok(posts.filter(p => p === 'POST /api/encounter').length === 1, 'exactly one encounter was posted: ' + JSON.stringify(posts));
  // ---- off again, recorded; then nothing ----
  await page.goBack(); await page.waitForTimeout(400);
  await page.evaluate(() => openAbout()); await page.waitForTimeout(900);
  await page.click('#encounter-toggle'); await page.waitForTimeout(900);
  const off = await api('/api/encounter/switch');
  ok(dialogs.length === 2 && /Turn encounter recording OFF\?/.test(dialogs[1]) && off.on === false && off.flips === 2, 'turning off is a confirmed action and the second recorded flip: ' + JSON.stringify([off.on, off.flips]));
  await page.evaluate(() => { HOME = null; }); await page.evaluate(() => loadHome()); await page.waitForTimeout(800);
  await page.click('#continue-area .cont[data-id="concept_fix00000001"] .resume a'); await page.waitForTimeout(900);
  const log2 = await api('/api/encounters');
  ok(log2.total === 1 && posts.filter(p => p === 'POST /api/encounter').length === 1, 'with recording off again, opening a card wrote nothing and posted nothing');

  // ---- unresolved: not due, findable, reopenable ----
  await page.goto(BASE + '/recovery'); await page.waitForTimeout(1000);
  const open0 = await page.evaluate(() => document.querySelectorAll('#cases .card[data-queue-id]').length);
  ok(open0 === 1, 'one case is still open after the Home journey: ' + open0);
  await page.fill('#cases .card[data-queue-id] input[id$="_note"]', 'not enough survives, from the journey');
  await page.click('#cases .card[data-queue-id] .actions button.unresolved'); await page.waitForTimeout(1200);
  const u1 = await page.evaluate(() => ({ open: document.querySelectorAll('#cases .card[data-queue-id]').length, unresolved: document.querySelectorAll('#unresolved .card[data-queue-id]').length,
    head: (document.querySelector('#unresolved .section-label') || {}).textContent || '', text: document.getElementById('unresolved').textContent.replace(/\s+/g, ' '),
    buttons: Array.from(document.querySelectorAll('#unresolved .card[data-queue-id] .actions button')).map(b => b.textContent.trim()),
    ruled: document.getElementById('ruled').textContent.replace(/\s+/g, ' ') }));
  ok(u1.open === 0 && u1.unresolved === 1 && /^1 unresolved — reopenable$/.test(u1.head.trim()), 'the case leaves the open list and appears as unresolved — reopenable: ' + JSON.stringify([u1.open, u1.unresolved, u1.head]));
  ok(/ruled unresolved/.test(u1.text) && /not enough survives, from the journey/.test(u1.text) && /reopening appends a ruling that cites the unresolved one/.test(u1.text), 'the unresolved card shows its ruling and says what reopening does');
  ok(u1.buttons.join('|') === 'Accept|Revise|Reject', 'reopening offers Accept, Revise, Reject — not unresolved again: ' + u1.buttons.join(' | '));
  ok(/unresolved — not enough survives, from the journey/.test(u1.ruled), 'the unresolved ruling is in the ruled list: ' + u1.ruled.slice(0, 120));
  const homeU = await api('/api/home');
  ok(homeU.pending.unresolved.count === 1 && homeU.pending.unresolved.titles.length === 1 && !(homeU.pending.items || []).some(i => i.source === 'recovery_review') && homeU.pending.saved.length === 0,
     'Home counts the unresolved case, not as a ruling due and not as saved: ' + JSON.stringify(homeU.pending.unresolved));
  await page.goto(BASE + '/'); await page.waitForTimeout(1500);
  const line = await page.evaluate(() => { const el = document.getElementById('ruling-unresolved'); const b = el.getBoundingClientRect(); return { hidden: el.hidden, display: getComputedStyle(el).display, text: el.textContent.replace(/\s+/g, ' ').trim(), links: Array.from(el.querySelectorAll('a')).map(a => a.getAttribute('href')), insideCard: !!el.closest('#ruling-card'), top: b.top, rulingBottom: document.getElementById('ruling-card').getBoundingClientRect().bottom, rows: document.querySelectorAll('#ruling-area .rule-row').length, more: document.getElementById('ruling-more').textContent, title: (el.querySelector('span[title]') || {}).title || '' }; });
  ok(!line.hidden && line.display !== 'none' && /^Unresolved 1 case ruled “not enough survives” — reopenable on the Recovery Review$/.test(line.text) && line.links.join() === '/recovery', 'Home paints the quiet Unresolved line with the review\'s door: ' + line.text);
  ok(!line.insideCard && line.top >= line.rulingBottom - 8 && !/^0 /.test(line.more) && line.rows === 1 && /^1 · only/.test(line.more), 'the line sits under the ruling band and is not counted as a ruling: ' + JSON.stringify([line.rows, line.more]));
  ok(line.title.length > 0 && !/Gutter Loop|Quorum/.test(line.text), 'the title is on hover, not in the line');
  await page.click('#ruling-unresolved a[href="/recovery"]'); await page.waitForTimeout(1000);
  // slice 2: the door opens the review inside the shell
  const rv2 = await place(page, '/recovery');
  ok(!!rv2 && (await page.evaluate(() => location.pathname)) === '/recovery', 'the door opens the review');
  // reopen: Accept without a definition is refused; with one, the ruling cites the unresolved one
  await rv2.click('#unresolved .card[data-queue-id] .actions button'); await page.waitForTimeout(300);
  const refused = await rv2.evaluate(() => document.querySelector('#unresolved .card[data-queue-id] .error').textContent);
  ok(/definition from you is required/.test(refused), 'reopening with Accept and no definition is refused on the page');
  await rv2.fill('#unresolved .card[data-queue-id] textarea', 'a loop that drains what it was meant to carry');
  await rv2.fill('#unresolved .card[data-queue-id] input[id$="_note"]', 'more survived, from the journey');
  await rv2.click('#unresolved .card[data-queue-id] .actions button'); await page.waitForTimeout(1200);
  const u2 = await rv2.evaluate(() => ({ unresolved: document.getElementById('unresolved').textContent.trim(), open: document.querySelectorAll('#cases .card[data-queue-id]').length, ruled: document.querySelectorAll('#ruled .card.ruled').length,
    ruledText: document.getElementById('ruled').textContent.replace(/\s+/g, ' ') }));
  ok(u2.unresolved === '' && u2.open === 0 && u2.ruled === 3 && /accept — more survived, from the journey · concept concept_[0-9a-f]{12} · 1 judgment event\(s\) · on the shelf · reopens rr_[0-9a-f]{12}/.test(u2.ruledText),
     'the reopened ruling is recorded, on the shelf, citing the unresolved ruling; the case leaves the unresolved list: ' + u2.ruledText.slice(0, 220));
  const rec = await api('/api/recovery');
  const last = rec.ruled[rec.ruled.length - 1];
  const prev = rec.ruled.find(r => r.ruling_id === last.reopens);
  ok(rec.unresolved_count === 0 && rec.open_count === 0 && prev && prev.decision === 'unresolved' && last.queue_judgment_id === prev.queue_judgment_id, 'the record holds both rulings, the later citing the earlier, the queue unchanged');
  const homeR = await api('/api/home');
  ok(homeR.pending.unresolved.count === 0, 'Home no longer counts an unresolved case');
  ok(errs.length === 0, 'no page errors across the journey: ' + JSON.stringify(errs));
  await ctx.close();
  await browser.close();
  finish('encounter');
})().catch(e => { console.log('FAIL journey crashed: ' + (e && e.stack || e)); process.exit(1); });
