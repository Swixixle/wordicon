// The quiet journey (block 104): browse the record with encounter
// recording OFF — Home, About & proof (the switch reads off, by default,
// never turned on), the Concepts shelf, a bridged shelf entry and a
// concept card (the two doors that would emit an encounter when on), the
// anatomy, the Recovery Review — and leave the store byte-identical.
// run.sh hashes the scratch store before and after this journey; this
// file proves the pages and the switch, run.sh proves the bytes. Runs
// FIRST, on the freshly seeded store, before any journey that rules.
const { BASE, ok, launch, pairedContext, finish } = require('./lib');
const healthyVault = { initialized: true, last_seal_at: new Date(Date.now() - 4 * 60000).toISOString(), last_drill_at: new Date(Date.now() - 86400000).toISOString(), cloud: 'iCloud', n_vaults: 31, total_bytes: 125638 * 1024, failure: '', stale_red: false, dirty_seconds: 0 };

(async () => {
  const browser = await launch();
  const ctx = await pairedContext(browser); const page = await ctx.newPage();
  await page.route('**/api/vault/status', r => r.fulfill({ json: healthyVault }));
  const posts = []; page.on('request', r => { if (r.method() !== 'GET') posts.push(r.method() + ' ' + r.url().replace(BASE, '')); });
  const errs = []; page.on('pageerror', e => errs.push(String(e)));
  page.on('dialog', d => d.dismiss());
  await page.goto(BASE + '/'); await page.waitForTimeout(1500);
  ok(errs.length === 0, 'no page errors on Home: ' + JSON.stringify(errs));
  const home = await (await page.request.get(BASE + '/api/home')).json();
  ok(home.encounter_recording === false, 'Home carries the switch state: off');
  ok(home.pending && home.pending.unresolved && home.pending.unresolved.count === 0, 'no case is unresolved on a fresh store');
  const unres = await page.evaluate(() => { const el = document.getElementById('ruling-unresolved'); return el ? { hidden: el.hidden, display: getComputedStyle(el).display, text: el.textContent } : null; });
  ok(unres && unres.hidden && unres.display === 'none' && unres.text === '', 'the Unresolved line exists and is hidden when nothing is unresolved');
  // About & proof: the switch, visibly off, never turned on, with what it would record
  await page.evaluate(() => openAbout()); await page.waitForTimeout(900);
  const about = await page.evaluate(() => ({ state: document.getElementById('encounter-state').textContent, btn: document.getElementById('encounter-toggle').textContent, hidden: document.getElementById('encounter-toggle').hidden,
    explain: document.getElementById('encounter-explain').textContent.replace(/\s+/g, ' '), epoch: document.getElementById('about-epoch-name').textContent }));
  ok(/^off \(default — never turned on\)/.test(about.state), 'About says recording is off by default and was never turned on: ' + about.state);
  ok(!about.hidden && about.btn === 'Turn on', 'the visible owner action is "Turn on"');
  ok(/ids and event types only/.test(about.explain) && /never any text/.test(about.explain) && /Turning it on or off is itself recorded/.test(about.explain), 'About says exactly what would be recorded and that the flip is recorded');
  // the doors that would emit an encounter when on
  await page.click('#continue-area .cont[data-id="concept_fix_bridge"] .resume a'); await page.waitForTimeout(900);
  await page.goBack(); await page.waitForTimeout(400);
  await page.click('#continue-area .cont[data-id="concept_fix00000001"] .resume a'); await page.waitForTimeout(900);
  await page.goBack(); await page.waitForTimeout(400);
  // block 105b: words typed and destinations displayed — an identity-shaped input especially — write nothing (run.sh hashes the store around this whole journey)
  await page.fill('#input-text', 'Rowan Ashby Pell, born 1985-04-11 at 3 p.m. in Duluth, Minnesota'); await page.dispatchEvent('#input-text', 'input'); await page.waitForTimeout(900);
  const ident = await page.evaluate(() => ({ row: document.getElementById('destination-row').hidden, reading: document.getElementById('destination-reading').textContent.replace(/\s+/g, ' '), chips: Array.from(document.querySelectorAll('#destination-chips .dest')).map(b => b.dataset.dest + (b.disabled ? '!' : '')) }));
  ok(!ident.row && /Reads as a name with a date and a place/.test(ident.reading) && ident.chips.join(',') === 'name_study!,portrait!,owner_facts!,write,search,develop', 'an identity-shaped input is read and shown with the studies unbuilt: ' + ident.chips.join(','));
  await page.fill('#input-text', 'I would like to know about the historical superstitions involving cats.'); await page.dispatchEvent('#input-text', 'input'); await page.waitForTimeout(900);
  const catsRow = await page.evaluate(() => Array.from(document.querySelectorAll('#destination-chips .dest')).map(b => b.dataset.dest + (b.classList.contains('suggested') ? '*' : '') + (b.disabled ? '!' : '')).join(','));
  ok(catsRow === 'research*!,search,develop,room,write,question', 'the cats sentence is read with Research outside Nikodemus highlighted and unbuilt: ' + catsRow);
  await page.fill('#input-text', ''); await page.dispatchEvent('#input-text', 'input'); await page.waitForTimeout(500);
  const readsOnly = posts.filter(p => p !== 'POST /api/destinations');
  ok(readsOnly.length === 0, 'browsing with recording off posted nothing: ' + JSON.stringify(readsOnly) + ' (reads of the words\' shape: ' + posts.length + ')');
  // the other pages
  await page.goto(BASE + '/anatomy'); await page.waitForTimeout(800);
  await page.goto(BASE + '/recovery'); await page.waitForTimeout(1000);
  const rec = await page.evaluate(() => ({ cases: document.querySelectorAll('#cases .card[data-queue-id]').length, unresolved: document.getElementById('unresolved').textContent.trim() }));
  ok(rec.cases === 2 && rec.unresolved === '', 'the review lists the two open cases and no unresolved section');
  const enc = await (await page.request.get(BASE + '/api/encounters')).json();
  ok(enc.total === 0 && enc.switch && enc.switch.on === false && enc.switch.flips === 0, 'the raw log is empty and the switch has never flipped');
  ok(posts.filter(p => p !== 'POST /api/destinations').length === 0, 'nothing but shape readings was posted by the whole quiet journey: ' + JSON.stringify(posts.filter(p => p !== 'POST /api/destinations')));
  await ctx.close();
  await browser.close();
  finish('quiet');
})().catch(e => { console.log('FAIL journey crashed: ' + (e && e.stack || e)); process.exit(1); });
