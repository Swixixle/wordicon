// The Epistemic Presentation journey (block 113) — in a real browser, on
// two runs written by the real writers against the offline gateway.
//
// Three things are proved here that source review cannot prove:
//
//   1. The state table behind the card header. verdictRows() is pure and
//      lives in the page, so the journey calls it directly with every
//      anchor status the checker can emit — including the two that were
//      crossed, where a REFUTED anchor rendered as an unrun check.
//   2. That the labels are real text. A colour, an icon, a tooltip or CSS
//      ::before content all satisfy a source grep and all vanish the
//      moment the reader selects, copies or listens. innerText is the
//      only witness that distinguishes them.
//   3. That the three unobservable acquisition facts print as words. Never
//      as 0 — a zero is a measurement, and no measurement was taken.
const fs = require('fs');
const path = require('path');
const { BASE, DIR, ok, launch, pairedContext, finish } = require('./lib');
const IDS = JSON.parse(fs.readFileSync(path.join(DIR, 'epistemic.json'), 'utf8'));
const INVENTED = 'INVENTED EXAMPLE — NOT IN YOUR TEXT:';
const SELF_REPORT = 'MODEL SELF-REPORT — UNVERIFIED';

(async () => {
  const browser = await launch();
  const ctx = await pairedContext(browser);
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(String(e)));
  await page.goto(BASE + '/');
  await page.waitForTimeout(800);

  // ---- 1. the grounding state table, called directly ------------------
  const rows = await page.evaluate(() => {
    const g = (ai, cs, fv) => {
      const r = verdictRows({friction: {verdict: fv},
                             anchor_integrity: ai ? {status: ai} : undefined,
                             claim_support: cs ? {support: cs} : undefined,
                             flesh: {}, bone: {}});
      const grounded = r.find(x => x[0] === 'Grounded');
      const made = r.find(x => x[0] === 'Well-made');
      return {g: grounded[1], gWhy: grounded[2], m: made[1], mWhy: made[2]};
    };
    return {
      absent: g('absent', 'not_run', 'keep'),
      notFound: g('not_found', 'not_run', 'keep'),
      near: g('near', 'not_run', 'keep'),
      exactSupported: g('exact', 'supported', 'keep'),
      exactNotRun: g('exact', 'not_run', 'keep'),
      nothing: g('', '', 'keep'),
      contradicted: g('exact', 'contradicted', 'keep'),
    };
  });
  // The defect this journey was written for: an anchor that was CHECKED and
  // NOT FOUND is the strongest negative the mechanical tier can produce, and
  // it was rendering as an empty circle meaning nothing had happened.
  ok(rows.notFound.g === 'no' && /not in your text/.test(rows.notFound.gWhy),
     'a quote checked and not found in the text is a FAILED warrant, not an unrun check: '
     + JSON.stringify(rows.notFound));
  // and its mirror: `absent` means no quote was ever offered, which is not
  // the same as a quote that was offered and missing
  ok(rows.absent.g === 'none' && /no quote was offered/.test(rows.absent.gWhy),
     'no anchor offered reads as nothing checked, not as a refuted quote: ' + JSON.stringify(rows.absent));
  ok(rows.near.g === 'no', 'a near miss is still a failed warrant: ' + JSON.stringify(rows.near));
  ok(rows.exactSupported.g === 'yes', 'quote present and licensing the claim is the only "yes"');
  ok(rows.exactNotRun.g === 'none' && /support check did not run/.test(rows.exactNotRun.gWhy),
     'a present quote with no support check is not a warrant: ' + JSON.stringify(rows.exactNotRun));
  ok(rows.contradicted.g === 'no', 'an anchor that denies the claim is a failed warrant');

  // ---- 2. warrant dominates craft --------------------------------------
  ok(/warrant ABSENT/.test(rows.absent.mWhy) && /warrant ABSENT/.test(rows.exactNotRun.mWhy),
     'a craft pass beside an unestablished claim says the warrant is absent: ' + rows.absent.mWhy);
  ok(/warrant FAILED/.test(rows.notFound.mWhy) && /warrant FAILED/.test(rows.near.mWhy),
     'a craft pass beside a refuted anchor says the warrant failed: ' + rows.notFound.mWhy);
  // and the clause must NOT fire where the warrant holds, or it means nothing
  ok(!/warrant/i.test(rows.exactSupported.mWhy),
     'the warrant clause stays silent where the warrant holds, so it carries information: ' + rows.exactSupported.mWhy);

  // ---- 3. the acquisition read, called directly -------------------------
  const acq = await page.evaluate(() => ({
    both: acquisitionOf({observed: [ACQ_RETURNED, ACQ_CITED]}),
    onlyReturned: acquisitionOf({observed: [ACQ_RETURNED]}),
    onlyCited: acquisitionOf({observed: [ACQ_CITED]}),
    legacySearched: acquisitionOf({used: 'searched'}),
    legacyCited: acquisitionOf({used: 'cited'}),
  }));
  ok(acq.both.returned && acq.both.cited, 'a source both returned and cited carries both');
  ok(acq.onlyReturned.returned && !acq.onlyReturned.cited, 'returned-only carries only returned');
  ok(acq.onlyCited.cited && !acq.onlyCited.returned, 'cited-only carries only cited');
  ok(acq.legacySearched.recorded === false && acq.legacySearched.citedKnown === false,
     'a pre-block-113 "searched" row is not read as proof the prose cited nothing: '
     + JSON.stringify(acq.legacySearched));
  ok(acq.legacyCited.returnedKnown === false,
     'a pre-block-113 "cited" row does not claim the search returned it: ' + JSON.stringify(acq.legacyCited));

  // ---- 4. the sprout panel, rendered from a real snapshot ---------------
  await page.evaluate(t => loadPastResult(t), IDS.sprout);
  await page.waitForTimeout(1200);
  const sp = await page.evaluate(() => {
    const el = document.getElementById('result-area');
    return {text: el.innerText, html: el.innerHTML.length};
  });
  ok(/Returned by provider search/.test(sp.text), 'the panel names what the provider search returned');
  ok(/Cited in generated prose/.test(sp.text), 'the panel names what the prose cited, separately');
  ok(/Fetched by Nikodemus\s*\n?\s*not applicable/.test(sp.text),
     'fetch is not applicable in words, not a zero: ' + (sp.text.match(/Fetched by Nikodemus[^\n]*\n?[^\n]*/) || [''])[0]);
  ok(/Examined\s*\n?\s*unknown/.test(sp.text) && /opaque to this client/.test(sp.text),
     'what the model examined is unknown AND stated to be opaque, not merely unrecorded');
  ok(/Anchored in your Library\s*\n?\s*none/.test(sp.text), 'anchoring is none, in words');
  // THE ZERO TEST. Three facts have no measurement; a digit next to any of
  // them is a measurement being claimed.
  ok(!/(Fetched by Nikodemus|Examined|Anchored in your Library)\s*\n?\s*\d/.test(sp.text),
     'no fact this client cannot observe is printed as a number — fetch, examine and anchor are words');
  ok(sp.text.split(SELF_REPORT).length - 1 >= 1,
     'the reviewer\'s own prose is labelled a model self-report');

  // The label must survive stripping every stylesheet: colour, icons,
  // tooltips and ::before content do not.
  const naked = await page.evaluate(() => {
    document.querySelectorAll('style, link[rel=stylesheet]').forEach(n => n.remove());
    return document.getElementById('result-area').innerText;
  });
  ok(naked.indexOf(SELF_REPORT) !== -1 && /not applicable/.test(naked) && /Returned by provider search/.test(naked),
     'the acquisition labels are real text and survive with every stylesheet removed');

  // ---- 5. the invented example, on a real candidate card ----------------
  await page.reload(); await page.waitForTimeout(600);
  await page.evaluate(t => loadPastResult(t), IDS.groupOk);
  await page.waitForTimeout(1200);
  const cd = await page.evaluate(inv => {
    const el = document.getElementById('result-area');
    const t = el.innerText;
    const hits = t.split(inv).length - 1;
    // the sentence, as rendered, must not be wrapped in the app's quotation
    // convention — punctuation is a claim
    const i = t.indexOf(inv);
    const after = i === -1 ? '' : t.slice(i + inv.length, i + inv.length + 60);
    return {text: t, hits, after};
  }, INVENTED);
  ok(cd.hits >= 1, 'a model-written example sentence carries the invented-example label in real text');
  ok(!/^\s*[“"]/.test(cd.after),
     'the invented sentence is not dressed in the app\'s quotation marks: ' + JSON.stringify(cd.after.slice(0, 30)));
  ok(!/example_sentence/.test(cd.text), 'no raw field name leaked into the card');

  // ---- 6. a group whose anchor was checked and not found ----------------
  await page.evaluate(t => loadPastResult(t), IDS.groupFailed);
  await page.waitForTimeout(1200);
  const bad = await page.evaluate(() => document.getElementById('result-area').innerText);
  ok(/warrant FAILED|warrant ABSENT/.test(bad),
     'a candidate whose anchor was not found says so beside its craft verdict');

  ok(errs.length === 0, 'no page errors across the epistemic journey: ' + JSON.stringify(errs));
  await browser.close();
  finish('epistemic');
})();
