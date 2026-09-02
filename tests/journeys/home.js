// The Home journey — the entrance (blocks 99–101), in a real browser:
// first paint at laptop size, zero provider on load, the wordmark, the
// Continue cards through stable ids (modern, bridged, ambiguous,
// title-only), the ruling band and the Saved-for-later line, the writing
// room's OBJECT IDENTITY across Write / split / swap / full page / close
// with a typed draft and its undo history, the Bench and back, the
// doors, the Clinic deep link, the brand on every page, phone and split
// widths, reduced motion. Prints one line per check; exits 1 on any
// failure. Run by tests/journeys/run.sh (locally or in CI).
const { BASE, ok, launch, pairedContext, finish } = require('./lib');
const healthyVault = { initialized: true, last_seal_at: new Date(Date.now() - 4 * 60000).toISOString(), last_drill_at: new Date(Date.now() - 86400000).toISOString(), cloud: 'iCloud', n_vaults: 31, total_bytes: 125638 * 1024, failure: '', stale_red: false, dirty_seconds: 0 };

(async () => {
  const browser = await launch();
  const paired = (opts = {}) => pairedContext(browser, opts);

  // ---- 2, 12, 19, 20: first paint at laptop size, healthy vault mocked ----
  {
    const ctx = await paired(); const page = await ctx.newPage();
    await page.route('**/api/vault/status', r => r.fulfill({ json: healthyVault }));
    const reqs = []; page.on('request', r => reqs.push(r.url().replace(BASE, '')));
    const errs = []; page.on('pageerror', e => errs.push(String(e)));
    await page.goto(BASE + '/'); await page.waitForTimeout(1500);
    ok(errs.length === 0, 'no page errors on Home: ' + JSON.stringify(errs));
    ok(!reqs.some(u => u.startsWith('/api/config')), 'Home never asks /api/config on load: ' + JSON.stringify(reqs.filter(u => u.startsWith('/api'))));
    const fp = await page.evaluate(() => {
      const r = sel => { const el = document.querySelector(sel); if (!el) return null; const b = el.getBoundingClientRect(); return { top: b.top, bottom: b.bottom, area: b.width * b.height, text: el.textContent.trim().slice(0, 80) }; };
      return { title: document.title, wordmark: document.querySelector('header .wordmark').textContent, header: document.querySelector('header').textContent.replace(/\s+/g, ' '),
               h1: r('#lead h1'), cont: r('#continue-card'), firstCard: r('#continue-area .cont'), cards: document.querySelectorAll('#continue-area .cont').length,
               ta: r('#input-text'), run: r('#go-btn'), ih: innerHeight, strip: document.getElementById('vault-strip').hidden, dot: document.getElementById('quiet-dot').className, quiet: document.getElementById('quiet-text').textContent,
               excluded: document.getElementById('continue-excluded').textContent, rulings: document.querySelectorAll('#ruling-area .rule-row').length, rulingsMore: document.getElementById('ruling-more').textContent,
               rulingText: document.getElementById('ruling-card').textContent.replace(/\s+/g, ' '),
               saved: (() => { const el = document.getElementById('ruling-saved'); if (!el) return { missing: true, hidden: true, display: 'none', text: '', links: 0, top: -1, insideCard: false, title: '' }; const b = el.getBoundingClientRect(); return { hidden: el.hidden, display: getComputedStyle(el).display, text: el.textContent.replace(/\s+/g, ' ').trim(), links: el.querySelectorAll('a, [onclick]').length, top: b.top, insideCard: !!el.closest('#ruling-card'), title: (el.querySelector('span[title]') || {}).title || '' }; })(),
               rulingBottom: document.getElementById('ruling-card').getBoundingClientRect().bottom, intakeTop: document.getElementById('intake-card').getBoundingClientRect().top };
    });
    ok(fp.title === 'Nikodemus' && fp.wordmark === 'Nikodemus', 'the wordmark and title are Nikodemus');
    ok(!/anthropic|gateway|live ·|formerly/i.test(fp.header), 'the header carries no provider and no "formerly": ' + fp.header);
    ok(fp.h1 && fp.h1.text.startsWith('Continue where your thinking left off') && fp.h1.bottom <= fp.ih, 'the lead is the ruled sentence, on screen');
    ok(fp.cards >= 3 && fp.firstCard && fp.firstCard.bottom <= fp.ih, `a real resumable object is on the first paint (${fp.cards} cards; first card bottom ${Math.round(fp.firstCard && fp.firstCard.bottom)} of ${fp.ih})`);
    ok(fp.ta && fp.ta.top > fp.cont.bottom, 'the phrase box sits below Continue');
    ok(fp.ta && fp.ta.area < fp.cont.area, 'the phrase box is smaller than the Continue band');
    ok(fp.run && fp.run.top > fp.ih, 'Run it is below the fold — not the strongest first-paint object (top ' + Math.round(fp.run.top) + ')');
    ok(fp.strip === true && fp.dot === 'dot ok' && fp.quiet === 'all quiet', 'a healthy vault is quiet: strip hidden, green dot, "all quiet"');
    ok(/cannot yet be tied safely to a single concept/.test(fp.excluded) && /“Common Ground” names more than one shelf entry/.test(fp.excluded), 'ambiguous legacy rulings are reported as excluded, not guessed: ' + fp.excluded.slice(0, 90));
    // block 100/103: two rulings due — the claim, and the recovery queue now that it has a door; nothing is saved for later
    ok(fp.rulings === 2 && /^2 · only what the record can count/.test(fp.rulingsMore), 'Needs your ruling shows the claim and the recovery queue, counted as 2: ' + fp.rulingsMore);
    ok(/2 accepted-but-absent concepts, receipt-only — Accept, Reject, or Revise each/.test(fp.rulingText) && /Review them/.test(fp.rulingText) && !/review not built/.test(fp.rulingText), 'the recovery queue is a ruling due with its door: ' + fp.rulingText.slice(0, 160));
    ok(fp.saved.hidden && fp.saved.display === 'none' && fp.saved.text === '', 'nothing is saved for later once the queue has its page — the line is hidden and empty');
    // the mechanism stays: something saved would paint the quiet line; display:flex loses to [hidden] when it empties again
    const shown = await page.evaluate(() => { HOME.pending.saved = [{source: 'x', count: 1, label: '1 thing kept aside', titles: ['t'], why: 'no page yet'}]; renderRulings(); const el = document.getElementById('ruling-saved'); return { hidden: el.hidden, display: getComputedStyle(el).display, text: el.textContent.replace(/\s+/g, ' ').trim(), links: el.querySelectorAll('a, [onclick]').length }; });
    ok(!shown.hidden && shown.display !== 'none' && /^Saved for later 1 thing kept aside — no page yet$/.test(shown.text) && shown.links === 0, 'the Saved for later mechanism still paints, quietly, when something has no door: ' + shown.text);
    const gone = await page.evaluate(() => { HOME.pending.saved = []; renderRulings(); const el = document.getElementById('ruling-saved'); if (!el) return { hidden: false, display: 'missing', rulings: -1 }; return { hidden: el.hidden, display: getComputedStyle(el).display, rulings: document.querySelectorAll('#ruling-area .rule-row').length }; });
    ok(gone.hidden && gone.display === 'none' && gone.rulings === 2, 'with nothing saved the line is gone and the ruling count is unchanged');
    await page.evaluate(() => { HOME = null; }); await page.evaluate(() => loadHome()); await page.waitForTimeout(600);
    // block 103: the door opens the Recovery Review; a case shows only what survived; Accept needs the owner's definition; the ruling is a new event with its clock
    await page.click('#ruling-area .rule-row a[href="/recovery"]'); await page.waitForTimeout(1200);
    const rv = await page.evaluate(() => ({ url: location.pathname, title: document.title, cases: document.querySelectorAll('#cases .card[data-queue-id]').length,
      text: document.getElementById('cases').textContent.replace(/\s+/g, ' '), epoch: document.getElementById('epoch-line').textContent,
      defs: Array.from(document.querySelectorAll('#cases textarea')).map(t => t.value), suggested: /suggestion|proposed|suggested value/i.test(document.getElementById('cases').textContent) }));
    ok(rv.url === '/recovery' && /Recovery Review/.test(rv.title) && rv.cases === 2, 'the door opens the Recovery Review with the two queued cases: ' + JSON.stringify([rv.url, rv.cases]));
    ok(/No definition survives\./.test(rv.text) && /receipt: found/.test(rv.text) && /Sibling A · Sibling B|Contraband Pedagogy · Sibling A/.test(rv.text) && /no clock/.test(rv.text), 'a case shows what survived and says what did not: ' + rv.text.slice(0, 200));
    ok(rv.defs.every(v => v === '') && !rv.suggested, 'no definition is suggested or prefilled — the field is the owner\'s');
    const fourth = await page.$$eval('#cases .card[data-queue-id] .actions button', bs => bs.slice(0, 4).map(b => b.textContent.trim()));
    ok(fourth.join('|') === 'Accept|Revise|Reject|Not enough survives — leave unresolved', 'the four rulings are offered, unresolved among them: ' + fourth.join(' | '));
    ok(/epoch: development_and_calibration/.test(rv.epoch), 'the page names the epoch: ' + rv.epoch);
    await page.click('#cases .card[data-queue-id] .actions button');   // Accept with an empty definition
    await page.waitForTimeout(300);
    const refused = await page.evaluate(() => document.querySelector('#cases .card[data-queue-id] .error').textContent);
    ok(/definition from you is required/.test(refused), 'Accept without a definition is refused on the page: ' + refused);
    await page.fill('#cases .card[data-queue-id] textarea', 'teaching that survives by being forbidden');
    await page.fill('#cases .card[data-queue-id] input[id$="_note"]', 'kept, from the journey');
    await page.click('#cases .card[data-queue-id] .actions button'); await page.waitForTimeout(1200);
    const after = await page.evaluate(() => ({ open: document.querySelectorAll('#cases .card[data-queue-id]').length, ruled: document.querySelectorAll('#ruled .card.ruled').length, ruledText: document.getElementById('ruled').textContent.replace(/\s+/g, ' ') }));
    ok(after.open === 1 && after.ruled === 1 && /accept — kept, from the journey · concept concept_[0-9a-f]{12} · 1 judgment event\(s\) · on the shelf/.test(after.ruledText) && /development_and_calibration/.test(after.ruledText), 'the ruling is recorded with its identity, its clock and its epoch, and the case leaves the open list: ' + after.ruledText.slice(0, 200));
    const apiAfter = await (await page.request.get(BASE + '/api/home')).json();
    const recRow = (apiAfter.pending.items || []).find(i => i.source === 'recovery_review');
    const recovered = (apiAfter.continue || []).find(c => c.kind === 'concept' && c.title === 'Contraband Pedagogy');
    ok(recRow && /^1 accepted-but-absent concept, receipt-only/.test(recRow.label) && recovered && recovered.shelf && recovered.shelf.via === 'concept_id' && /^2026-09/.test(recovered.when || ''), 'Home counts one case left and the recovered concept is a Continue card by its minted id, dated by the ruling: ' + JSON.stringify([recRow && recRow.label, recovered && recovered.shelf, recovered && recovered.when]).slice(0, 200));
    await page.goto(BASE + '/'); await page.waitForTimeout(1200);
    const rulingColors = await page.$$eval('#ruling-area .rule-row', rows => rows.map(r => getComputedStyle(r).borderLeftColor + '|' + getComputedStyle(r).color));
    ok(rulingColors.every(c => !c.includes('224, 138, 138')), 'the rulings band is not failure-red');
    // the two same-titled concepts are two cards, each addressed by id
    const ids = await page.$$eval('#continue-area .cont[data-kind="concept"]', cs => cs.map(c => c.dataset.id));
    ok(ids.includes('concept_fix00000001') && ids.includes('concept_fix00000002') && new Set(ids).size === ids.length, 'two same-titled concepts are two cards by id: ' + ids.join(', '));
    // block 101: how each card reaches the shelf is said as the record has it
    const shelfVia = await page.$$eval('#continue-area .cont[data-kind="concept"]', cs => Object.fromEntries(cs.map(c => [c.dataset.id, c.dataset.shelf + '|' + c.textContent.replace(/\s+/g, ' ')])));
    ok(/^concept_id\|/.test(shelfVia.concept_fix00000001 || '') && /^concept_id\|/.test(shelfVia.concept_fix00000002 || ''), 'modern entries resolve by concept id, the bridge never consulted');
    ok(/^legacy_title\|.*On the shelf through an older title-keyed record\./.test(shelfVia.concept_fix_bridge || '') && /Open it on the shelf/.test(shelfVia.concept_fix_bridge || '') && !/Bench|Map/.test(shelfVia.concept_fix_bridge || ''), 'the pre-wiring entry is bridged, said plainly, with no instruments: ' + (shelfVia.concept_fix_bridge || '').slice(0, 120));
    ok(/^ambiguous\|.*2 shelf entries share this title/.test(shelfVia.concept_fix_sib || '') && !/Open the concept|Open it on the shelf/.test(shelfVia.concept_fix_sib || ''), 'a shared title stays unresolved and says so: ' + (shelfVia.concept_fix_sib || '').slice(0, 140));
    ok(/^title_fallback\|.*On the shelf as a title only/.test(shelfVia.concept_fix_fallback || ''), 'an accepted ruling with no written entry is a title-only row, said as that: ' + (shelfVia.concept_fix_fallback || '').slice(0, 120));
    ok(/cannot yet be tied safely to a single concept/.test(fp.excluded) && /None were guessed into Continue/.test(fp.excluded) && !/stay on the/.test(fp.excluded), 'the excluded line is honest about what the older rulings are: ' + fp.excluded.slice(0, 140));
    // the bridge opens the older entry by ITS id and says so
    await page.click('#continue-area .cont[data-id="concept_fix_bridge"] .resume a');
    await page.waitForTimeout(900);
    const bridged = await page.evaluate(() => ({ hash: location.hash, open: document.getElementById('library-area').style.display !== 'none', search: document.getElementById('library-search').value, note: (document.getElementById('page-note') || {}).textContent || '' }));
    ok(bridged.hash === '#concepts' && bridged.open && bridged.search === 'Lantern Debt' && /opened from an older title-keyed record \(acc_bridgefix\)/.test(bridged.note), 'the bridge opens the shelf on the persisted entry by its acc_ id and says so: ' + JSON.stringify(bridged).slice(0, 200));
    await page.goBack(); await page.waitForTimeout(400);
    // opening a modern Continue concept card lands on the shelf, filtered, by id
    await page.click('#continue-area .cont[data-id="concept_fix00000001"] .resume a');
    await page.waitForTimeout(900);
    const shelf = await page.evaluate(() => ({ hash: location.hash, open: document.getElementById('library-area').style.display !== 'none', search: document.getElementById('library-search').value, rows: document.querySelectorAll('#library-content [id^="wrow_"]').length }));
    ok(shelf.hash === '#concepts' && shelf.open && shelf.search === 'Common Ground', 'a concept card opens the Concepts shelf on that concept: ' + JSON.stringify(shelf));
    // Back returns to Home's top state
    await page.goBack(); await page.waitForTimeout(400);
    ok((await page.evaluate(() => location.hash)) === '' , 'browser Back returns from the place to Home');
    await ctx.close();
  }

  // ---- 13: vault failure stays loud and specific; provider failure visible in About ----
  {
    const ctx = await paired(); const page = await ctx.newPage();
    await page.route('**/api/vault/status', r => r.fulfill({ json: { ...healthyVault, failure: 'seal failed: disk full', stale_red: true, dirty_seconds: 1800 } }));
    await page.route('**/api/config', r => r.abort());
    await page.goto(BASE + '/'); await page.waitForTimeout(1200);
    const v = await page.evaluate(() => ({ strip: document.getElementById('vault-strip').hidden, text: document.getElementById('vault-strip').textContent, color: getComputedStyle(document.getElementById('vault-strip')).color, dot: document.getElementById('quiet-dot').className, quiet: document.getElementById('quiet-text').textContent }));
    ok(v.strip === false && /seal failed: disk full/.test(v.text) && v.dot === 'dot bad' && v.quiet === 'attention', 'a vault failure is visible and specific: ' + v.text.slice(0, 60));
    await page.evaluate(() => openAbout()); await page.waitForTimeout(600);
    const about = await page.evaluate(() => ({ open: document.getElementById('about-panel').open, provider: document.getElementById('about-provider').textContent, formerly: /formerly Wordicon/.test(document.getElementById('about-panel').textContent) }));
    ok(about.open && /offline|unreachable/.test(about.provider) && about.formerly, 'About & proof shows the provider state on demand and keeps "formerly Wordicon": ' + about.provider.slice(0, 50));
    await ctx.close();
  }

  // ---- 10/11: the writing room's object survives the journey with a real typed draft ----
  {
    const ctx = await paired(); const page = await ctx.newPage();
    await page.route('**/api/vault/status', r => r.fulfill({ json: healthyVault }));
    await page.goto(BASE + '/'); await page.waitForTimeout(800);
    await page.evaluate(() => { window.__roomToken = Symbol('room'); document.getElementById('compose-text').__token = window.__roomToken; });
    await page.fill('#input-text', 'the sore has a family tree'); await page.dispatchEvent('#input-text', 'input');
    await page.evaluate(() => openCompose()); await page.waitForTimeout(300);
    await page.keyboard.press('End'); await page.keyboard.type(', and the tree has a debt');
    const V1 = await page.evaluate(() => document.getElementById('compose-text').value);
    await page.keyboard.type(' — undo me');
    let undone = false;
    for (let i = 0; i < 20; i++) { await page.keyboard.press('Control+z'); await page.waitForTimeout(40); if ((await page.evaluate(() => document.getElementById('compose-text').value)) === V1) { undone = true; break; } }
    ok(undone, 'undo works inside the room (typed text undone back to ' + JSON.stringify(V1) + ')');
    await page.evaluate(() => { const ta = document.getElementById('compose-text'); ta.setSelectionRange(9, 9); ta.scrollTop = 0; });
    const same = async (label) => {
      const s = await page.evaluate(() => { const ta = document.getElementById('compose-text'); return { same: ta.__token === window.__roomToken, value: ta.value, sel: ta.selectionStart, mode: document.body.className }; });
      ok(s.same && s.value === V1 && s.sel === 9, `${label}: same room element, draft and caret intact (${s.mode.trim()})`);
    };
    await page.evaluate(() => openWorkspace('split')); await page.waitForTimeout(250); await same('split');
    await page.evaluate(() => swapSides()); await page.waitForTimeout(250); await same('swap');
    await page.evaluate(() => openWorkspace('write')); await page.waitForTimeout(250); await same('full page');
    await page.evaluate(() => closeWorkspace()); await page.waitForTimeout(250); await same('closed back to Home');
    const draftCard = await page.evaluate(() => { renderContinue(); const c = document.querySelector('#continue-area .cont[data-kind="writing"]'); return c ? c.textContent : ''; });
    ok(/left open on this device/.test(draftCard) && /sore has a family tree/.test(draftCard), 'the draft is a Continue card, marked as this device\'s');
    // undo history survives the round trip: more undo removes what was typed before it
    await page.evaluate(() => openCompose()); await page.waitForTimeout(200); await page.focus('#compose-text');
    let shrank = false;
    for (let i = 0; i < 40; i++) { await page.keyboard.press('Control+z'); await page.waitForTimeout(30); const v = await page.evaluate(() => document.getElementById('compose-text').value); if (v.length < V1.length) { shrank = true; break; } }
    ok(shrank, 'undo history survived the split/swap/full-page round trip');
    await page.evaluate(() => { document.getElementById('compose-text').value = ''; }); await page.fill('#compose-text', V1); await page.evaluate(() => closeWorkspace());
    // Bench and back: the draft comes back
    await page.goto(BASE + '/bench'); await page.waitForTimeout(400);
    const benchTitle = await page.title(); ok(/^Nikodemus/.test(benchTitle) && /^Nikodemus — /.test(benchTitle), 'the Bench carries the brand in its title: ' + benchTitle);
    ok(/back to Nikodemus/.test(await page.textContent('body')), 'the Bench\'s back link names Nikodemus');
    await page.goBack(); await page.waitForTimeout(900);
    const back = await page.evaluate(() => ({ path: location.pathname, text: document.getElementById('input-text').value }));
    ok(back.path === '/' && /the sore has a family tree/.test(back.text), 'Bench and back: the draft is where it was: ' + JSON.stringify(back));
    await ctx.close();
  }

  // ---- 8: deep links ----
  {
    const ctx = await paired(); const page = await ctx.newPage();
    await page.route('**/api/vault/status', r => r.fulfill({ json: healthyVault }));
    const ids = await (await page.request.get(BASE + '/api/home')).json();
    const concept = ids.continue.find(c => c.kind === 'concept' && c.id === 'concept_fix00000001'); const room = ids.continue.find(c => c.kind === 'room');
    // block 101: a bridged concept has no lexicon concept_id — the door (a general resolver) must say so rather than bridge
    const bridgedId = (ids.continue.find(c => c.kind === 'concept' && c.shelf && c.shelf.via === 'legacy_title') || {}).id;
    if (bridgedId) { await page.goto(BASE + '/?dest=concept:' + bridgedId); await page.waitForTimeout(1200); const d0 = await page.evaluate(() => ({ open: document.getElementById('library-area').style.display !== 'none', note: (document.getElementById('page-note') || {}).textContent || '' })); ok(!d0.open && /could not be resolved/.test(d0.note), 'the concept door does not bridge: a legacy-only concept id is reported unresolved, nothing opened in its place'); }
    await page.goto(BASE + '/?dest=concept:' + concept.id); await page.waitForTimeout(1200);
    const d1 = await page.evaluate(() => ({ open: document.getElementById('library-area').style.display !== 'none', search: document.getElementById('library-search').value, note: document.getElementById('page-note').textContent }));
    ok(d1.open && d1.search === 'Common Ground', 'a concept door by id opens the shelf on that concept: ' + JSON.stringify(d1));
    await page.goto(BASE + '/?dest=concept:Common%20Ground'); await page.waitForTimeout(1200);
    const d2 = await page.evaluate(() => document.getElementById('page-note').textContent);
    ok(/names 2 concepts/.test(d2), 'a title naming two concepts asks instead of guessing: ' + d2.slice(0, 80));
    await page.goto(BASE + '/?dest=work:nope'); await page.waitForTimeout(1000);
    ok(/could not be resolved/.test(await page.evaluate(() => document.getElementById('page-note').textContent)), 'an unresolvable door still says so');
    await page.goto(BASE + '/clinic?room=' + room.id); await page.waitForTimeout(900);
    ok(/Adult Ventilator Liberation \(fixture\)/.test(await page.textContent('#room-area')), 'the Clinic opens the room named in the deep link');
    ok(/back to Nikodemus/.test(await page.textContent('body')), 'the Clinic\'s back link names Nikodemus');
    await page.goto(BASE + '/bench?concept_id=' + concept.id); await page.waitForTimeout(900);
    ok(/Common Ground/.test(await page.textContent('body')), 'the Bench opens a concept by id');
    await page.goto(BASE + '/anatomy'); await page.waitForTimeout(500);
    const an = await page.evaluate(() => ({ title: document.title, witness: document.querySelector('.organ[data-id="witness"]') ? document.querySelector('.organ[data-id="witness"]').textContent : '', world: NODES.world.does }));
    ok(an.title === 'The Functional Anatomy of Nikodemus' && !/Wordicon/.test(an.world) && /Nikodemus/.test(an.world), 'the anatomy is stamped with the brand from the one source');
    const mf = await (await page.request.get(BASE + '/manifest.json')).json(); ok(mf.name === 'Nikodemus' && mf.short_name === 'Nikodemus', 'the manifest carries the brand');
    await ctx.close();
    const unp = await browser.newContext(); const pp = await unp.newPage(); await pp.goto(BASE + '/pair');
    ok(/Pair this device with Nikodemus/.test(await pp.textContent('body')) && (await pp.title()).startsWith('Nikodemus'), 'the pair page carries the brand');
    await unp.close();
  }

  // ---- 14/15: phone and split widths; reduced motion ----
  for (const [name, w, h] of [['phone', 390, 844], ['split', 700, 900]]) {
    const ctx = await paired({ viewport: { width: w, height: h }, reducedMotion: 'reduce' }); const page = await ctx.newPage();
    await page.route('**/api/vault/status', r => r.fulfill({ json: healthyVault }));
    await page.goto(BASE + '/'); await page.waitForTimeout(1200);
    const m = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: innerWidth, cards: document.querySelectorAll('#continue-area .cont').length, rulings: document.querySelectorAll('#ruling-area .rule-row').length, savedVisible: (() => { const el = document.getElementById('ruling-saved'); if (!el) return false; const b = el.getBoundingClientRect(); return !el.hidden && b.width > 0 && b.right <= innerWidth; })(), intake: !!document.getElementById('input-text'), nav: document.querySelectorAll('header nav.places a').length, caretTransition: getComputedStyle(document.querySelector('.collapse-head .caret')).transitionDuration }));
    ok(m.sw <= m.iw && m.cards >= 3 && m.rulings === 2 && m.intake && m.nav === 6 && !m.savedVisible, `${name} ${w}px: no overflow (${m.sw}/${m.iw}); Continue, two rulings, no saved line, intake, navigation present`);
    ok(m.caretTransition === '0s', `${name}: reduced motion honored (caret transition ${m.caretTransition})`);
    await ctx.close();
  }

  await browser.close();
  finish('home');
})();
