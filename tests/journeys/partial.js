// The partial-workup journey (block 119).
//
// The defect: a deep run completed ONE component of six and the page
// showed a "full coverage" line at the top, a per-component summary on
// the card that finished, and a reassurance BELOW both saying five had
// failed but nothing was lost. Each statement was true. Together they
// read as a whole reading of the passage, and the owner argued with the
// surviving sixth as though it were Nikodemus's verdict on his writing.
//
// Source review cannot catch this. Every string was already in the file;
// what was wrong was the ORDER they appeared in and the fact that a
// custody statement stood where a completion statement belonged. Only a
// rendered page can testify to order, and only innerText can testify
// that the words are words — a colour, an icon, a tooltip or a CSS
// ::before all satisfy a grep and all vanish when the reader selects,
// copies, or listens.
const fs = require('fs');
const path = require('path');
const { BASE, DIR, ok, launch, pairedContext, finish } = require('./lib');
const IDS = JSON.parse(fs.readFileSync(path.join(DIR, 'partial.json'), 'utf8'));
const REQUIRED = 'PARTIAL WORKUP — 1 of 6 components completed. No overall reading exists.';

(async () => {
  const browser = await launch();
  const ctx = await pairedContext(browser);
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(String(e)));
  await page.goto(BASE + '/');
  await page.waitForTimeout(800);

  // ---- 1. the banner's own wording, at the shape the ruling names ------
  const one = await page.evaluate(() => {
    const d = {n_components: 6, n_failed: 5, n_completed: 1,
               groups: [{label: 'conditional self-description'},
                        {label: 'component 2', failed: true},
                        {label: 'slow descent metaphor', failed: true},
                        {label: 'reinterpreted hell', failed: true},
                        {label: 'critique of moral performance', failed: true},
                        {label: 'labor, fortune, and complicity in desolation', failed: true}]};
    const el = document.createElement('div');
    el.innerHTML = partialWorkupBanner(d);
    document.body.appendChild(el);
    const t = el.innerText;
    el.remove();
    return t;
  });
  ok(one.includes(REQUIRED), 'partial banner states the ruling\'s sentence verbatim' + ' :: ' + JSON.stringify(one.slice(0, 120)));
  ok(one.includes('reinterpreted hell') && one.includes('critique of moral performance'), 'partial banner names the components that did not run' + ' :: ' + one.slice(0, 120));
  ok(/not a finding about your writing/i.test(one), 'partial banner denies that a failure to run is a finding' + ' :: ' + one.slice(0, 120));

  // A run where everything completed must say NOTHING. A banner that
  // always fires is a banner nobody reads.
  const none = await page.evaluate(() =>
    partialWorkupBanner({n_components: 3, n_failed: 0, n_completed: 3, groups: [{}, {}, {}]}));
  ok(none === '', 'a complete run renders no partial banner at all' + ' :: ' + JSON.stringify(none));

  // ---- 2. extraction coverage may not speak for the analysis ----------
  const cov = await page.evaluate(() => ({
    partial: coverageLine({n_components: 6, n_failed: 5, groups: []}),
    whole: coverageLine({n_components: 6, n_failed: 0, groups: []}),
  }));
  ok(!/full coverage/i.test(cov.partial) && !/full coverage/i.test(cov.whole), 'coverage line no longer claims "full coverage"' + ' :: ' + JSON.stringify(cov));
  ok(/6 components were proposed/.test(cov.partial) && /1 completed analysis/.test(cov.partial), 'coverage line names components PROPOSED and components ANALYSED separately' + ' :: ' + JSON.stringify(cov.partial));
  ok(/not the reading/i.test(cov.partial), 'coverage line says coverage describes the split, not the reading' + ' :: ' + JSON.stringify(cov.partial));

  // ---- 3. the REAL partial run, reopened, in DOM order ----------------
  await page.evaluate(async (tid) => {
    const r = await fetch('/api/result/' + tid);
    window.__d = await r.json();
  }, IDS.deepPartial);
  const real = await page.evaluate(() => {
    const el = document.createElement('div');
    el.innerHTML = buildDeepHtml(window.__d);
    document.body.appendChild(el);
    const t = el.innerText;
    el.remove();
    return {text: t, n: window.__d.n_components, done: window.__d.n_completed};
  });
  ok(/PARTIAL WORKUP — \d+ of \d+ components completed\. No overall reading exists\./.test(real.text), 'a real partial run renders the PARTIAL WORKUP line' + ' :: ' + real.text.slice(0, 120));
  ok(real.text.includes(`${real.done} of ${real.n} components completed`), 'the real run\'s banner counts match its own record' + ' :: ' + `${real.done}/${real.n} :: ` + real.text.slice(0, 120));

  // ORDER is the whole defect. The partiality must precede the trial's
  // verdict on the input, because a reader who meets the verdict first has
  // already been told the page is a reading.
  // Case-INSENSITIVE, because .section-label is text-transform:uppercase and
  // innerText applies it: the trial's heading reaches the reader as
  // "YOUR INPUT ON TRIAL". A case-sensitive search for it found nothing and
  // the ordering check passed on trial@-1 — a check that cannot see the
  // thing it is ordering against is not ordering anything.
  const flat = real.text.toUpperCase();
  const iPartial = flat.indexOf('PARTIAL WORKUP');
  const iTrial = flat.indexOf('YOUR INPUT ON TRIAL');
  ok(iTrial >= 0, 'the trial verdict is on the page at all (the ordering check has something to order against)' + ' :: ' + `trial@${iTrial}`);
  ok(iPartial >= 0 && iTrial > iPartial, 'partiality is rendered BEFORE the trial verdict, not after it' + ' :: ' + `partial@${iPartial} trial@${iTrial}`);
  ok(/not a verdict on the workup/i.test(real.text), 'the trial verdict is scoped to the input, not to the workup' + ' :: ' + real.text.slice(0, 120));

  // The banner is a FACT, not an explanation, so block 116's disclosure
  // rule does not apply to it: it must be readable without opening
  // anything. innerText of a closed <details> excludes its body, so this
  // distinguishes the two.
  const visible = await page.evaluate(() => {
    const el = document.createElement('div');
    el.innerHTML = buildDeepHtml(window.__d);
    document.body.appendChild(el);
    el.querySelectorAll('details').forEach(x => x.removeAttribute('open'));
    const t = el.innerText;
    el.remove();
    return t;
  });
  ok(visible.includes('PARTIAL WORKUP'), 'the partial line is readable with every disclosure closed' + ' :: ' + visible.slice(0, 120));

  // ---- 4. failed components stay, completed components stay -----------
  const kept = await page.evaluate(() => {
    const el = document.createElement('div');
    el.innerHTML = buildDeepHtml(window.__d);
    document.body.appendChild(el);
    const out = {
      retryButtons: el.querySelectorAll('button[onclick^="retryConcept"]').length,
      failedCards: [...el.querySelectorAll('.section-label')]
        .filter(x => /this one failed/i.test(x.innerText)).length,
      text: el.innerText,
    };
    el.remove();
    return out;
  });
  const nFailed = await page.evaluate(() => window.__d.n_failed);
  ok(kept.retryButtons === nFailed && nFailed > 0, 'every failed component keeps its own retry door' + ' :: ' + `${kept.retryButtons} button(s) for ${nFailed} failed component(s)`);
  ok(kept.failedCards === nFailed, 'failed components remain visible rather than collapsing away' + ' :: ' + `${kept.failedCards} failed card(s)`);
  const completedLabel = await page.evaluate(() =>
    (window.__d.groups.find(g => !g.failed) || {}).label || '');
  ok(completedLabel && kept.text.includes(completedLabel), 'the component that DID complete is still on the page' + ' :: ' + completedLabel);

  // ---- 5. no aggregate count may float free of its population ---------
  const counts = await page.evaluate(() => ({
    partial: componentCountLine({n_components: 6, n_failed: 5, groups: []}),
    whole: componentCountLine({n_components: 6, n_failed: 0, groups: []}),
  }));
  ok(/1 of 6 component\(s\) analysed/.test(counts.partial), 'a partial run\'s component count says how many were ANALYSED' + ' :: ' + JSON.stringify(counts));

  ok(errs.length === 0, 'no page errors' + ' :: ' + errs.join(' | '));
  await browser.close();
  finish('partial');
})();
