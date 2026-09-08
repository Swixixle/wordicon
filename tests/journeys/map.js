// Map · focus — one place in focus, read off the rendered page.
//
// Everything asserted here is read from the page's own text (innerText of
// the rendered rows — the lesson of block 123), against a record the REAL
// road writers produced (fixtures.seed_map): a forge, sprouts, refracts, an
// archetype, a revise, a declared road; a legacy row, a pre-tracking row,
// and two sprouts whose receipts are gone. What only a browser can testify
// to: that nothing is in focus until chosen; that a derived issuer reads
// as derived and never as recorded; that a missing receipt is a named
// state and "run snapshot available" appears only where a snapshot is; that
// the node carries no Friction verdict; that a dispute shows both verdicts
// and chooses neither; that a title-keyed identity is disclosed and never
// welded to a concept-keyed one; that at twelve roads the total stays
// visible and no group opens by itself; that one expansion opens one ring
// and nothing else; that the URL restores the whole view; that a keyboard
// reader hears the same three fields; that no request leaves the page but
// GETs — no model call, no write; and that a door pressed inside the shell
// lands on its run.
const fs = require('fs');
const path = require('path');
const { BASE, DIR, ok, launch, pairedContext, finish, place } = require('./lib');

const ids = JSON.parse(fs.readFileSync(path.join(DIR, 'map.json'), 'utf8'));

// bounded waits that report rather than throw: a sabotage must fail a NAMED
// check, not crash the journey; a navigation in flight is not an answer
async function waitFor(page, fn, arg, ms = 6000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    try { if (await page.evaluate(fn, arg)) return true; } catch (e) { /* the page is navigating */ }
    await page.waitForTimeout(80);
  }
  return false;
}
async function evalSafe(page, fn, arg, fallback) {
  for (let i = 0; i < 20; i++) {
    try { return await page.evaluate(fn, arg); } catch (e) { await page.waitForTimeout(100); }
  }
  return fallback;
}
const stageText = page => page.evaluate(() => (document.getElementById('stage') || {}).innerText || '');
const rendered = () => !!document.querySelector('#stage h2');
const roadRows = () => Array.from(document.querySelectorAll('ol.roads > li[data-edge]')).map(li => ({
  edge: li.getAttribute('data-edge'), text: li.innerText, aria: li.getAttribute('aria-label') || '',
  rings: li.querySelectorAll('.ring2').length }));
function encKey(k) { return encodeURIComponent(k); }

(async () => {
  const browser = await launch();
  const ctx = await pairedContext(browser);
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(String(e)));
  const posts = [], focusCalls = [], paid = [];
  page.on('request', r => {
    const u = r.url().replace(BASE, '');
    if (r.method() !== 'GET') posts.push(r.method() + ' ' + u);
    if (u.startsWith('/api/map/focus')) focusCalls.push(u);
    if (/\/api\/map\/(roads\/suggest|route\/analyze|road|log)/.test(u)) paid.push(u);
  });

  // ---- 1. nothing in focus until chosen -----------------------------------
  await page.goto(BASE + '/map');
  ok(await waitFor(page, () => /Nothing is in focus until you choose it/.test((document.getElementById('stage') || {}).innerText || '')),
     'the Map opens on a picker: nothing is in focus until chosen');
  ok(focusCalls.length === 0, 'no focus was requested before a place was chosen :: ' + JSON.stringify(focusCalls));
  const pick = await page.evaluate(() => (document.getElementById('places') || {}).innerText || '');
  ok(pick.includes(ids.seedTitle) && pick.includes('Lantern Debt'), 'the picker lists the seeded places');
  ok(/legacy title-keyed/.test(pick), 'a title-keyed place is marked as such in the picker');
  ok(/by label, then key/.test(await stageText(page)), 'the picker says its order, and it is not by degree');

  // ---- 2. the focus head ---------------------------------------------------
  await page.goto(BASE + '/map?key=' + encKey(ids.seedKey));
  ok(await waitFor(page, rendered), 'the seeded concept renders in focus');
  const head = await page.evaluate(() => document.querySelector('#stage .card').innerText);
  ok(head.includes(ids.seedTitle), 'the head names the concept under the name it was first boxed under :: ' + head.split('\n')[1]);
  ok(/concept-keyed/.test(head), 'the identity line says concept-keyed');
  ok(!/\b(holds|strained|keep|suspect|contradicted)\b/.test(head), 'the node carries no review verdict — a verdict belongs to a road in a run :: ' + head.replace(/\n/g, ' | ').slice(0, 300));
  ok(/owner standing/.test(head) && /no ruling recorded/.test(head), 'owner standing is stated on the node, and absence is stated as absence');
  ok(/same title, other places/.test(head) && /legacy title-keyed/.test(head), 'the title-keyed twin is disclosed beside the concept-keyed box, never welded');
  ok(/also written as/.test(head), 'the revise variants ride as other written forms, not as the name');
  const burden = await page.evaluate(() => document.querySelectorAll('#stage .card')[1].innerText);
  const total = parseInt((burden.match(/served map — (\d+)/) || [])[1] || '0', 10);
  ok(total >= 12, 'the burden names its population and a total at or past the grouping threshold :: ' + total);
  ok(/evidence support — quoted spans and Library anchors: 0/.test(burden), 'evidence support is stated as zero with its own population, not omitted');
  ok(/none stands in for another/.test(burden), 'the standing rule is on the page');

  // ---- 3. grouped at twelve: the total visible, nothing open ---------------
  const list = await page.evaluate(() => document.querySelectorAll('#stage .card')[2].innerText);
  const m = list.match(/(\d+) direct roads · (\d+) groups/);
  ok(m && parseInt(m[1], 10) === total, 'the grouped list keeps the total visible :: ' + (m && m[0]));
  const groupSum = await page.evaluate(() => Array.from(document.querySelectorAll('ul.groups > li')).reduce((n, li) => n + parseInt((li.innerText.match(/(\d+) road/) || [0, 0])[1], 10), 0));
  ok(groupSum === total, 'the groups sum to the population :: ' + groupSum + ' of ' + total);
  ok((await page.evaluate(() => document.querySelectorAll('ul.groups ol.roads').length)) === 0, 'no group is open until opened');
  ok(/a group opens only when you open it/.test(list) && /oldest first/.test(list), 'the grouping rule and the order rule are stated in words');

  // open the largest parallels group, by the page's own link
  async function openGroup(rel, issuer) {
    const needle = [rel, issuer];
    const done = await evalSafe(page, n => {
      const li = Array.from(document.querySelectorAll('ul.groups > li')).find(x => x.innerText.includes(n[0]) && x.innerText.includes(n[1]));
      const a = li && Array.from(li.querySelectorAll('a')).find(x => x.textContent.trim() === 'open');
      if (!a) return false; a.click(); return true;
    }, needle, false);
    if (!done) return false;
    await page.waitForLoadState('domcontentloaded');
    return waitFor(page, n => Array.from(document.querySelectorAll('ul.groups > li')).some(x => x.innerText.includes(n[0]) && x.innerText.includes(n[1]) && x.querySelector('ol.roads')), needle);
  }
  ok(await openGroup('runs parallel to', 'recorded · model proposal'), 'a group opens on an explicit action');
  ok(/open=/.test(page.url()), 'the open group is in the URL :: ' + page.url().replace(BASE, ''));
  let rows = await evalSafe(page, roadRows, null, []);
  ok(rows.length >= 6, 'the opened group lists its roads :: ' + rows.length);
  const row0 = rows[0];
  ok(/runs parallel to/.test(row0.text) && /issuer/.test(row0.text) && /provenance/.test(row0.text) && /review standing/.test(row0.text)
     && /evidence support/.test(row0.text) && /owner standing/.test(row0.text),
     'a road row states relation, issuer, provenance, review standing, evidence support and owner standing');
  ok(/recorded · model proposal/.test(row0.text) && /by sprout review, this run/.test(row0.text),
     'a recorded model proposal says so, and its review names the stage and the run :: ' + row0.text.split('\n').slice(0, 6).join(' | '));
  ok(/evidence support\s*none/.test(row0.text) && /owner standing\s*none/.test(row0.text), 'absent standings are stated as absent, not left blank');
  ok(/issuer/.test(row0.aria) && /provenance/.test(row0.aria) && /runs parallel to/.test(row0.aria), 'the accessible name carries the same three fields :: ' + row0.aria);

  // ---- 4. the eighteen's state: file not found, snapshot only where it is --
  // a road's own run is on its "recorded" line; the dispute line names other
  // runs too, so the match is on the road's line and not on the row at large
  const ofRun = t => rows.find(r => r.text.includes('run ' + t + ' · road'));
  const missR = ofRun(ids.missingReceipt);
  const missB = ofRun(ids.missingBoth);
  ok(!!missR && /producer receipt cited · file not found/.test(missR.text), 'a road citing a receipt that is not there says so by name');
  ok(!!missR && /run snapshot available/.test(missR.text), 'and says the run snapshot is available when it is');
  ok(!!missB && /producer receipt cited · file not found/.test(missB.text) && !/run snapshot available/.test(missB.text),
     'a road whose receipt AND snapshot are gone claims no snapshot — the eighteen render as this :: ' + (missB ? (missB.text.split('\n')[(missB.text.split('\n').indexOf('provenance') + 1)] || '') : 'row not found'));
  ok(!rows.some(r => /provenance\s*\n\s*(issuer|review standing)/.test(r.text)), 'no provenance cell is blank');

  // ---- 5. the dispute: both verdicts, neither chosen ----------------------
  const disp = rows.find(r => /judged differently across runs/.test(r.text));
  ok(!!disp && /holds ×\d+/.test(disp.text) && /strained ×\d+/.test(disp.text) && /neither verdict is chosen/.test(disp.text),
     'a target judged differently across runs shows both verdicts on the road and chooses neither');
  ok(!!disp && /population: runs whose review reached this target/.test(disp.text), 'the dispute names its population');

  // ---- 6. derived, pre-tracking, declared, resolved, reconstructed ---------
  ok(await openGroup('runs parallel to', 'derived from snapshot · model stage (sprout)'), 'the legacy road\'s group opens');
  rows = await evalSafe(page, roadRows, null, []);
  const legacy = rows.find(r => r.edge === ids.legacyEdge);
  ok(!!legacy && /derived from snapshot · model stage \(sprout\)/.test(legacy.text) && /rule: snapshot · basis: trace_/.test(legacy.text) && /issuer-derivation\/1/.test(legacy.text),
     'a legacy row derives from its snapshot with rule, basis and version on the road');
  ok(!!legacy && !/recorded · /.test(legacy.text.split('\n').find(l => /^issuer/.test(l)) || ''), 'a derived issuer never reads as recorded');
  ok(!!legacy && /no citation recorded/.test(legacy.text) && /run snapshot available/.test(legacy.text), 'a legacy row\'s provenance is "no citation recorded", with its snapshot named');
  ok(await openGroup('runs parallel to', 'issuer not recorded'), 'the pre-tracking road\'s group opens');
  rows = await evalSafe(page, roadRows, null, []);
  const pre = rows.find(r => r.edge === ids.pretrackEdge);
  ok(!!pre && /issuer not recorded/.test(pre.text) && !/derived/.test(pre.text.split('\n').find(l => /^issuer/.test(l)) || ''),
     'a row from before the tracked history with no snapshot says issuer not recorded — nothing is inferred from its relation');
  ok(await openGroup('declared road', 'recorded · owner declaration'), 'the declared road\'s group opens');
  rows = await evalSafe(page, roadRows, null, []);
  const decl = rows.find(r => r.text.includes(ids.declaredId));
  ok(!!decl && /you declared this road/.test(decl.text) && /answers/.test(decl.text) && /recorded · owner declaration/.test(decl.text),
     'a declared road carries owner standing with its verb and declaration id');
  ok(await openGroup('renamed to', 'recorded · pipeline'), 'the revise roads\' group opens');
  rows = await evalSafe(page, roadRows, null, []);
  const res = rows.find(r => /recorded against/.test(r.text));
  ok(!!res && /recorded against\s*word:/.test(res.text) && /resolved onto this box by unambiguous title match/.test(res.text),
     'a road the map resolved onto this box discloses the key it was recorded against');
  ok(await openGroup('produced', 'derived from snapshot · pipeline'), 'the reconstructed road\'s group opens');
  rows = await evalSafe(page, roadRows, null, []);
  const recon = rows.find(r => /reconstructed from snapshot/.test(r.text));
  ok(!!recon && /recorded time unavailable/.test(recon.text) && !/\d{4}-\d{2}-\d{2}\s*· run/.test(recon.text),
     'a reconstruction with no recorded time says so — no time is synthesized');
  ok(!!recon && /derived from snapshot · pipeline/.test(recon.text) && /rule: reconstruction/.test(recon.text), 'a reconstruction names the snapshot it was drawn from as its basis');

  // ---- 7. one expansion, one ring -----------------------------------------
  const target = rows.find(r => /runs parallel to/.test(r.text) && /Cassandra/.test(r.text)) || rows[0];
  await evalSafe(page, e => { const li = document.querySelector(`ol.roads > li[data-edge="${e}"]`); const a = li && Array.from(li.querySelectorAll('a')).find(x => /show next ring/.test(x.textContent)); a && a.click(); }, target.edge, null);
  await page.waitForLoadState('domcontentloaded');
  ok(await waitFor(page, () => document.querySelectorAll('.ring2').length === 1), 'expanding one road opens exactly one further ring');
  ok(/expand=/.test(page.url()), 'the expansion is in the URL');
  const ring = await evalSafe(page, () => ({ text: document.querySelector('.ring2').innerText, nested: document.querySelectorAll('.ring2 .ring2').length,
                                            openGroups: document.querySelectorAll('.ring2 ol.roads').length, groups: document.querySelectorAll('.ring2 ul.groups li').length }), null, {text: '', nested: -1, openGroups: -1, groups: -1});
  ok(/one ring only/.test(ring.text) && ring.nested === 0, 'the further ring says it is one ring only and opens nothing beyond itself');
  ok(ring.groups === 0 || ring.openGroups === 0, 'a bounded further ring shows its groups closed');
  ok((await evalSafe(page, roadRows, null, [])).filter(r => r.rings > 0).length === 1, 'no other road expanded');
  // the URL holds the open groups and the expansion: reload, and they are back
  const openBefore = await evalSafe(page, () => document.querySelectorAll('ul.groups ol.roads').length, null, -1);
  await page.reload();
  ok(await waitFor(page, rendered), 'the grouped view reloads');
  const back = await evalSafe(page, () => ({ open: document.querySelectorAll('ul.groups ol.roads').length, ring: document.querySelectorAll('.ring2').length }), null, {});
  ok(openBefore >= 1 && back.open === openBefore && back.ring === 1, 'reload restores the open groups and the one expansion from the URL :: ' + JSON.stringify(back) + ' (open before: ' + openBefore + ')');

  // ---- 8. a filter narrows and says so; the facets stay whole -------------
  const beforeOpts = await evalSafe(page, () => Array.from(document.querySelectorAll('select')[0].options).map(o => o.textContent), null, []);
  await evalSafe(page, () => { const s = document.querySelectorAll('select')[0]; const o = Array.from(s.options).find(x => /runs parallel to/.test(x.textContent)); s.value = o.value; s.dispatchEvent(new Event('change')); }, null, null);
  await page.waitForLoadState('domcontentloaded');
  ok(await waitFor(page, () => /filtered — \d+ of \d+ direct roads shown/.test((document.getElementById('stage') || {}).innerText || '')), 'a filter says how many of how many it shows');
  ok(/rel=parallels/.test(page.url()), 'the filter is in the URL');
  const afterOpts = await evalSafe(page, () => Array.from(document.querySelectorAll('select')[0].options).map(o => o.textContent), null, []);
  ok(JSON.stringify(afterOpts) === JSON.stringify(beforeOpts) && beforeOpts.length > 2, 'the facets are counted over the whole ring, so the filter can be undone from what is shown');
  const filteredRows = await evalSafe(page, roadRows, null, []);
  ok(filteredRows.length >= 6 && filteredRows.every(r => /runs parallel to/.test(r.text.split('\n')[0])), 'only the chosen relation remains :: ' + filteredRows.length);
  ok(await evalSafe(page, () => { const c = document.querySelectorAll('#stage .card')[2]; return !!c && !c.querySelector(':scope > ul.groups') && !!c.querySelector(':scope > ol.roads'); }, null, false),
     'below the threshold the filtered ring is listed flat, not grouped');
  ok(filteredRows.filter(r => r.rings > 0).length === 1, 'the expansion survives a filter its road survives');

  // ---- 9. the URL restores the whole view ----------------------------------
  const urlBefore = page.url();
  await page.reload();
  ok(await waitFor(page, rendered), 'the view reloads');
  const restored = await evalSafe(page, () => ({ h2: document.querySelector('#stage h2').textContent, ring: document.querySelectorAll('.ring2').length,
    sel: document.querySelectorAll('select')[0].selectedOptions[0].textContent }), null, {});
  ok(page.url() === urlBefore && String(restored.h2).includes(ids.seedTitle) && restored.ring === 1 && /runs parallel to/.test(restored.sel),
     'reload restores focus, expansion and filter from the URL :: ' + JSON.stringify(restored));
  // back walks to the previous state, because a filter is a navigation
  await page.goBack(); await page.waitForLoadState('domcontentloaded');
  ok(await waitFor(page, () => !/rel=parallels/.test(location.search) && !!document.querySelector('#stage h2')), 'Back removes the filter, because the filter was a navigation');

  // ---- 10. the keyboard reader hears the same fields ------------------------
  await page.goto(BASE + '/map?key=' + encKey(ids.legacyKey));
  ok(await waitFor(page, rendered), 'the title-keyed place renders');
  const lhead = await page.evaluate(() => document.querySelector('#stage .card').innerText);
  ok(/legacy title-keyed/.test(lhead) && /never welds them/.test(lhead), 'a title-keyed place is disclosed as such, with the rule');
  const lrows = await evalSafe(page, roadRows, null, []);
  ok(lrows.length === 2 && !/direct roads · \d+ groups/.test(await stageText(page)), 'below the threshold the roads are listed, not grouped');
  let heard = '';
  for (let i = 0; i < 40 && !heard; i++) {
    await page.keyboard.press('Tab');
    heard = await page.evaluate(() => { const a = document.activeElement; return a && a.matches('ol.roads > li') ? (a.getAttribute('aria-label') || '') : ''; });
  }
  ok(/runs parallel to/.test(heard) && /issuer recorded · model proposal/.test(heard) && /provenance receipt_/.test(heard),
     'tabbing reaches a road and its accessible name carries relation, issuer and provenance :: ' + heard);

  // ---- 11. no model call, no write, from any of it --------------------------
  ok(paid.length === 0, 'no paid or writing map route was touched :: ' + JSON.stringify(paid));
  ok(posts.length === 0, 'no request but GET left the page :: ' + JSON.stringify(posts));

  // ---- 12. inside the shell: the door opens Focus, and a run door lands ----
  await page.goto(BASE + '/');
  await page.waitForTimeout(1200);
  await page.evaluate(() => document.querySelector('header nav.places a[href="/map"]').click());
  const frame = await place(page, '/map');
  ok(!!frame, 'the header\'s Map door opens the Map inside the shell');
  ok(await waitFor(page, () => { const f = document.getElementById('place-frame'); const d = f && f.contentDocument; return !!(d && /Nothing is in focus until you choose it/.test((d.getElementById('stage') || {}).innerText || '')); }),
     'and what opens is the picker — Focus is the Map\'s door');
  // the title-keyed place: two roads, listed flat, each with its run door
  await page.evaluate(t => { const d = document.getElementById('place-frame').contentDocument; const a = Array.from(d.querySelectorAll('#places a')).find(x => x.textContent.trim() === t); a && a.click(); }, 'Lantern Debt');
  ok(await waitFor(page, () => /^\/map\?key=/.test(location.pathname + location.search)), 'choosing a place inside the pane moves the address with it :: ' + page.url().replace(BASE, ''));
  ok(await waitFor(page, () => { const d = document.getElementById('place-frame').contentDocument; return !!(d && d.querySelector('#stage h2') && d.querySelector('ol.roads a[href^="/?trace="]')); }), 'the focus renders inside the pane, with its run doors');
  const doorTrace = await evalSafe(page, () => { const d = document.getElementById('place-frame').contentDocument; const a = d.querySelector('ol.roads a[href^="/?trace="]'); if (!a) return ''; const t = decodeURIComponent(a.getAttribute('href').slice('/?trace='.length)); a.click(); return t; }, null, '');
  ok(doorTrace === ids.legacySprout, 'the run door names the run that drew the road :: ' + doorTrace);
  ok(await waitFor(page, () => document.getElementById('place').hidden && location.pathname === '/', null, 8000), 'a run door pressed inside the pane closes the pane');
  // Home marks the run it has on screen (ON_SCREEN, the warp clock's own
  // record): the door landed when that mark carries the door's trace
  ok(await waitFor(page, t => typeof ON_SCREEN !== 'undefined' && !!ON_SCREEN && ON_SCREEN.trace === t, doorTrace, 8000),
     'and lands on that run in Home — a door that goes somewhere');

  ok(errs.length === 0, 'no page errors :: ' + errs.join(' | '));
  await browser.close();
  finish('map');
})().catch(e => { console.log('FAIL journey crashed: ' + (e && e.stack || e)); process.exit(1); });
