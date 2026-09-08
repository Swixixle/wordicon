// The Wayfinder's paid actions (Map Focus, repair) — disclosure before spend.
//
// Three buttons on the world map call a model: Resonance roads, Friction
// roads, and reading a plotted journey. The writing room's law is that a
// keystroke may not spend money and neither may a click that did not say it
// would; these predated it. What only a browser can testify to: that NO
// request leaves the page before the owner confirms, that Escape cancels
// with nothing sent, and that after confirmation EXACTLY ONE request leaves.
// The prompts and outputs behind the actions are unchanged.
const { BASE, ok, launch, pairedContext, finish } = require('./lib');

// bounded waits that report rather than throw: a sabotage must fail a NAMED
// check, not crash the journey on a timeout
async function waitFor(page, fn, ms = 4000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    if (await page.evaluate(fn)) return true;
    await page.waitForTimeout(80);
  }
  return false;
}
const panelOpen = () => document.getElementById('spend-ask').classList.contains('open');
const panelClosed = () => !document.getElementById('spend-ask').classList.contains('open');

(async () => {
  const browser = await launch();
  const ctx = await pairedContext(browser);
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(String(e)));
  const spend = [];   // every request to a paid route, as it leaves the page
  page.on('request', r => {
    const u = r.url();
    if (u.includes('/api/map/roads/suggest') || u.includes('/api/map/route/analyze')) spend.push(u.replace(BASE, ''));
  });
  await page.goto(BASE + '/map/world');
  // DATA is a script-level `let`, not a window property
  await page.waitForFunction(() => typeof DATA !== 'undefined' && DATA && Array.isArray(DATA.runs) && DATA.runs.length > 0, null, { timeout: 15000 });

  // two real places from the seeded record: the sprout seed and one of its parallels
  const places = await page.evaluate(() => {
    const seedRun = DATA.runs.find(r => r.mode === 'sprout');
    const seed = seedRun && seedRun.items.find(it => it.seed);
    const ext = seedRun && seedRun.items.find(it => it.kind === 'external');
    return { from: seed ? seed.label : '', to: ext ? ext.label.replace(/\s*\(.*\)$/, '') : '', fromKey: seed ? seed.key : '' };
  });
  ok(places.from && places.to, 'the seeded record offers a journey with a real road on it :: ' + JSON.stringify(places));

  // ---- 1. Resonance roads: the panel opens, nothing has left ---------------
  await page.evaluate(p => {
    document.getElementById('wf-from').value = p.from;
    document.getElementById('wf-to').value = p.to;
    // if the title is shared by several boxes, choose the seed's own box — the owner's act, not a coin flip
    const k = keyForLabel(p.from); if (k && k.ambiguous) wfPick[p.from.toLowerCase().trim()] = p.fromKey;
    window.__propose = proposeRoads('resonance');   // resolves only after the panel is answered
  }, places);
  const opened = await waitFor(page, panelOpen);
  ok(opened, 'a disclosure panel opened before anything was sent');
  const panel = await page.evaluate(() => document.getElementById('spend-ask').innerText);
  ok(spend.length === 0, 'no request left the page before the owner answered :: ' + JSON.stringify(spend));
  ok(/Model calls:\s*1/.test(panel), 'the panel says exactly one call :: ' + panel.slice(0, 200));
  ok(/Lane:/.test(panel) && /mock gateway|model/.test(panel), 'the panel names the lane and model :: ' + panel.slice(0, 200));
  ok(/POST \/api\/map\/roads\/suggest/.test(panel), 'the panel names the route :: ' + panel.slice(0, 200));
  ok(/Enters the record/.test(panel) && /no road/.test(panel), 'the panel says what enters the record, and that no road does until declared');
  ok(/Cost:/.test(panel) && /cannot price/.test(panel), 'the cost line states its own limit rather than a number it does not have');

  // ---- 2. Escape cancels; still nothing left -------------------------------
  await page.keyboard.press('Escape');
  const escClosed = await waitFor(page, panelClosed, 2000);
  ok(escClosed, 'Escape closed the panel');
  if (!escClosed) await page.evaluate(() => document.getElementById('spend-ask-cancel') && document.getElementById('spend-ask-cancel').click());
  await page.evaluate(() => window.__propose);
  ok(spend.length === 0, 'cancelling sent nothing :: ' + JSON.stringify(spend));

  // ---- 3. Proceed: exactly one request -------------------------------------
  await page.evaluate(() => { window.__propose = proposeRoads('resonance'); });
  if (await waitFor(page, panelOpen)) await page.click('#spend-ask-go');
  await page.evaluate(() => window.__propose);
  await page.waitForTimeout(300);
  ok(spend.filter(u => u.includes('roads/suggest')).length === 1,
     'after confirmation exactly one proposal request left :: ' + JSON.stringify(spend));

  // ---- 4. Friction roads, same door --------------------------------------
  await page.evaluate(() => { window.__propose = proposeRoads('friction'); });
  const opened2 = await waitFor(page, panelOpen);
  ok(opened2 && spend.filter(u => u.includes('roads/suggest')).length === 1, 'the second button also waits :: ' + JSON.stringify(spend));
  if (opened2) await page.click('#spend-ask-cancel');
  await page.evaluate(() => window.__propose);
  ok(spend.filter(u => u.includes('roads/suggest')).length === 1, 'cancelling the second sent nothing more');

  // ---- 5. Reading a journey: plot, choose, and the same discipline --------
  const plotted = await page.evaluate(() => {
    findRoutes();
    const w = wfState;
    if (!w || !w.alts.length) return { alts: 0 };
    selectAlt(0);
    window.__analyze = analyzeRoute();
    return { alts: w.alts.length, chosen: w.chosen };
  });
  ok(plotted.alts > 0 && plotted.chosen === 0, 'a real route was plotted and chosen :: ' + JSON.stringify(plotted));
  const opened3 = await waitFor(page, panelOpen);
  const panel2 = await page.evaluate(() => document.getElementById('spend-ask').innerText);
  ok(opened3 && spend.filter(u => u.includes('route/analyze')).length === 0, 'no analysis request left before the answer :: ' + JSON.stringify(spend));
  ok(/POST \/api\/map\/route\/analyze/.test(panel2) && /Model calls:\s*1/.test(panel2) && /route_analysis/.test(panel2),
     'the analysis panel names its route, one call, and the snapshot it writes :: ' + panel2.slice(0, 200));
  if (opened3) await page.click('#spend-ask-go');
  await page.evaluate(() => window.__analyze);
  await page.waitForTimeout(300);
  ok(spend.filter(u => u.includes('route/analyze')).length === 1, 'exactly one analysis request left after confirmation :: ' + JSON.stringify(spend));

  ok(errs.length === 0, 'no page errors :: ' + errs.join(' | '));
  await browser.close();
  finish('wayfinder');
})();
