// The narrowing history survives a follow-up (his ruling, 2026-09-14, after
// an independent review of report 77 found it dropped). A comparison made
// on a SHORTER meaning given for that pass is recorded as a narrowing; when
// that record is reopened and another language is asked about the same
// meaning, the outgoing request and the job the server queues must both
// still say it is a narrowing — true stays true — and an ordinary
// comparison's false stays false. The flag is carried as recorded, never
// recomputed from the length of the text on screen.
//
// Runs in WebKit, like the rest of the related-words journeys. The scratch
// server's model gateway is poisoned, so the follow-up job is queued and
// then fails at the model — which is exactly enough: the queued job row is
// the server's record of what it received.
const { BASE, DIR, ok, finish, pairedContext } = require('./lib');
const { webkit } = require('playwright');
const fs = require('fs');
const path = require('path');
const IDS = JSON.parse(fs.readFileSync(path.join(DIR, 'related.json'), 'utf8'));

(async () => {
  const browser = await webkit.launch();
  const ctx = await pairedContext(browser, { viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(String(e)));
  // Which engine this actually is, asked of the browser rather than of the
  // import line. The first version of this journey said WebKit in its own
  // header and took lib's launcher, which is Chromium; the log now says.
  ok(browser.browserType().name() === 'webkit',
    'the narrowing is measured in WebKit, the engine the owner writes in: ' + browser.browserType().name());
  const cookieHeader = fs.readFileSync(path.join(DIR, 'cookie'), 'utf8').trim() + '=' + fs.readFileSync(path.join(DIR, 'token'), 'utf8').trim();
  const getJson = async u => { const r = await fetch(BASE + u, { headers: { Cookie: cookieHeader } }); return r.json(); };

  const sent = [];
  await page.route('**/api/jobs', async route => {
    if (route.request().method() !== 'POST') return route.continue();
    let b = {}; try { b = JSON.parse(route.request().postData() || '{}'); } catch (e) {}
    sent.push(b);
    return route.continue();     // the real route queues it; the record of what it received is the job row
  });
  await page.goto(BASE + '/'); await page.waitForTimeout(1500);

  for (const [name, id, want] of [['a narrowed comparison', IDS.narrowed, true], ['an ordinary comparison', IDS.full, false]]) {
    const rec = await getJson('/api/result/' + id);
    ok((rec.source || {}).meaning_narrowed === want, `${name} is recorded as meaning_narrowed: ${want}: ` + JSON.stringify((rec.source || {}).meaning_narrowed));
    await page.evaluate(t => loadPastResult(t), id); await page.waitForTimeout(1500);
    const shown = await page.evaluate(u => ({
      projected: (RELATED_SRC[u] || {}).meaning_narrowed,
      said: !!document.getElementById('rw-narrowed-' + u),
      text: (document.getElementById('result-area') || {}).innerText || '',
    }), id);
    ok(shown.projected === want, `reopening projects the recorded value, ${want}, into what a follow-up will send: ` + JSON.stringify(shown.projected));
    ok(shown.said === want, want ? 'the reopened card says it is a shorter meaning given for this comparison' : 'an ordinary card does not claim a narrowing');
    if (want) ok(/a shorter meaning given for this comparison/.test(shown.text) && /was not changed/.test(shown.text), 'and says the concept’s own meaning was not changed');
    const before = sent.length;
    await page.fill(`#rw-lang-${id}`, 'Japanese');
    await page.click('button:has-text("Ask it — 2 model calls")');
    await page.waitForTimeout(1200);
    const req = sent[before] || null;
    ok(!!req && (req.only_languages || []).join(',') === 'Japanese', `asking another language sent one request: ` + JSON.stringify(req && req.only_languages));
    ok(!!req && req.meaning_narrowed === want, `the outgoing request carries meaning_narrowed: ${want}: ` + JSON.stringify(req && req.meaning_narrowed));
    ok(!!req && req.original && req.original.definition === rec.source.definition, 'and the same meaning, as recorded');
    // what the server queued from that request
    const jobs = await getJson('/api/jobs');
    const job = (jobs.jobs || jobs || []).find(j => j.mode === 'refract' && (j.related_entry || {}).only_languages && j.related_entry.only_languages[0] === 'Japanese' && (j.original || {}).definition === rec.source.definition);
    ok(!!job, 'the server queued a follow-up job for it');
    ok(!!job && (job.related_entry || {}).meaning_narrowed === want, `and the queued job records meaning_narrowed: ${want}, as received: ` + JSON.stringify(job && job.related_entry && job.related_entry.meaning_narrowed));
  }

  ok(errs.length === 0, 'no page errors through the journey: ' + JSON.stringify(errs.slice(0, 2)));
  await browser.close();
  finish('narrowing');
})();
