// Real browser + paired scratch server + JSONL persistence. No intercepted
// successful Ledger responses: the forced failure loses a reply AFTER append.
// The lifecycle helper routes named synthetic reads and one explicit write.
const fs = require('fs');
const path = require('path');
const playwright = require('playwright');
const {BASE, DIR, OUT, ok, finish, pairedContext, benignPageError} = require('./lib');
const ENGINE = process.env.JOURNEY_ENGINE === 'webkit' ? 'webkit' : 'chromium';
const NAME = 'ledger-delivery-' + ENGINE;
const state = process.env.JOURNEY_STATE || path.join(DIR, 'state');
function rows() {
  const dir = path.join(state, 'ledger');
  return fs.readdirSync(dir).filter(f => /^events-.*\.jsonl$/.test(f)).flatMap(f => fs.readFileSync(path.join(dir,f),'utf8').trim().split('\n').filter(Boolean).map(JSON.parse));
}
(async () => {
  const browser = await playwright[ENGINE].launch();
  ok(browser.browserType().name() === ENGINE, 'Ledger delivery is measured in ' + ENGINE);
  const ctx = await pairedContext(browser);
  const page = await ctx.newPage(), errors = [];
  page.on('pageerror', e => { if (!benignPageError(e)) errors.push(e.message); });
  const boot = async () => { await page.goto(BASE + '/work'); await page.waitForFunction(() => window.__work?.ledger?.scope); };
  await boot();
  await page.evaluate(() => window.__work.ledger.flush());
  // A normal page activity record, then a landed request whose response is cut.
  const marker = 'ledger_fixture_' + ENGINE + '_' + Date.now();
  const queued = await page.evaluate(marker => {
    const ledger = window.__work.ledger; ledger.note('result_viewed', {id:marker});
    return ledger.pending().find(e => e.subject.id === marker);
  }, marker);
  let sent, response;
  await page.route('**/api/ledger', async route => {
    if (route.request().method() !== 'POST') return route.continue();
    sent = JSON.parse(route.request().postData());
    response = await route.fetch(); await route.abort('failed');
  });
  await page.evaluate(() => window.__work.ledger.flush());
  ok(response?.status() === 200 && rows().filter(e => e.event_id === queued.event_id).length === 1, 'the lost reply followed one successful durable append');
  ok(await page.evaluate(id => window.__work.ledger.pending().some(e => e.event_id === id), queued.event_id), 'without acknowledgement the exact event remains queued');
  await page.unroute('**/api/ledger');
  await page.reload(); await page.waitForFunction(() => window.__work?.ledger?.scope);
  const restored = await page.evaluate(id => window.__work.ledger.pending().find(e => e.event_id === id), queued.event_id);
  ok(restored?.session_id === queued.session_id && restored?.at === queued.at, 'reload preserves original event identity and session clock');
  await page.evaluate(() => window.__work.ledger.flush());
  ok(rows().filter(e => e.event_id === queued.event_id).length === 1 && !await page.evaluate(id => window.__work.ledger.pending().some(e => e.event_id === id), queued.event_id), 'retry acknowledges the same event and leaves exactly one persisted row');
  // Reproduce the threshold reached inside pagehide, with real navigation.
  const boundary = await page.evaluate(() => {
    const l = window.__work.ledger;
    while (l.pending().length < 19) l.note('page_shown', {page:'work'});
    return l.pending().map(e => e.event_id);
  });
  await page.reload(); await page.waitForFunction(() => window.__work?.ledger?.scope); await page.evaluate(() => window.__work.ledger.flush());
  const kept = rows();
  ok(boundary.every(id => kept.filter(e => e.event_id === id).length === 1), 'navigation threshold events all persist once across beacon and acknowledged retry');
  // Valid paired session cannot make an unauthorized cross-origin mutation.
  const rejected = {...queued, event_id:'rejected_' + Date.now()};
  const foreign = await page.request.post(BASE + '/api/ledger', {headers:{Origin:'http://unauthorized.invalid'}, data:{events:[rejected]}});
  ok(foreign.status() === 403 && !(foreign.headers()['access-control-allow-origin']), 'paired cross-origin POST remains refused without an origin allowance');
  const stranger = await browser.newContext();
  const unauth = await stranger.request.post(BASE + '/api/ledger', {data:{events:[rejected]}});
  ok(unauth.status() === 401, 'unpaired Ledger POST remains refused');
  const preflight = await stranger.request.fetch(BASE + '/api/ledger', {method:'OPTIONS', headers:{Origin:'http://unauthorized.invalid','Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type'}});
  ok(preflight.status() === 401 && !preflight.headers()['access-control-allow-origin'], 'unauthorized preflight gets no cross-origin permission');
  const foreignPage = await stranger.newPage();
  await foreignPage.goto('data:text/html,<title>Unpaired opaque origin fixture</title>');
  const browserDenied = await foreignPage.evaluate(async ({base,event}) => {
    try { await fetch(base + '/api/ledger', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({events:[event]})}); return false; }
    catch (_) { return true; }
  }, {base:BASE,event:rejected});
  ok(browserDenied, 'browser fetch from an unauthorized opaque origin is rejected');
  ok(!rows().some(e => e.event_id === rejected.event_id), 'rejected cross-origin and unpaired events never enter the Ledger');
  const lifecycle = await require('./results-lifecycle')(page, {BASE, ENGINE, OUT, ok});
  ok(errors.length === 0, 'navigation and retry raise no Ledger page error: ' + JSON.stringify(errors));
  const ids = kept.filter(e => boundary.includes(e.event_id) || e.event_id === queued.event_id);
  fs.writeFileSync(path.join(OUT,NAME+'.proof.json'),JSON.stringify({engine:ENGINE,browser_version:browser.version(),playwright_version:require('playwright/package.json').version,manual_safari:false,origin:BASE,event_ids:ids.map(e=>e.event_id),session_ids:[...new Set(ids.map(e=>e.session_id))],persisted_rows:ids.length,duplicate_ids:ids.length-new Set(ids.map(e=>e.event_id)).size,lost_reply_status:response.status(),cross_origin_status:foreign.status(),unauthorized_status:unauth.status(),preflight_status:preflight.status(),opaque_origin_browser_rejected:browserDenied,page_errors:errors,operation_lifecycle:lifecycle},null,2)+'\n');
  await stranger.close();await browser.close();finish(NAME);
})().catch(e => { console.error(e); process.exit(1); });
