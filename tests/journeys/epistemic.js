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
const VAULT = JSON.parse(fs.readFileSync(path.join(DIR, 'vault_states.json'), 'utf8'));
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

  // ---- 7. block 114: the result comes first ----------------------------
  // Opened on the PARENT decompose run, which is where component headers
  // live — and which is also the record that was dropping them. A closed
  // <details> contributes nothing to innerText, which is what makes the
  // rule testable at all, and is why it has to be tested here: source
  // review cannot tell a collapsed line from a deleted one.
  await page.evaluate(t => loadPastResult(t), IDS.decompose);
  await page.waitForTimeout(1500);
  const hdrs = await page.evaluate(() => {
    const cards = [...document.querySelectorAll('#result-area .card')];
    return cards.filter(c => /^(Concept|Component)/.test(
        (c.querySelector('.section-label') || {}).textContent || ''))
      .map(c => ({
        label: (c.querySelector('.result-title') || {}).textContent.trim(),
        text: c.innerText,
        summary: (c.querySelector('details.case > summary') || {}).textContent || '',
        open: (c.querySelector('details.case') || {}).open,
        h: c.getBoundingClientRect().height,
      }));
  });
  ok(hdrs.length >= 2, 'both components rendered a header: ' + JSON.stringify(hdrs.map(h => h.label)));
  const found = hdrs.find(h => !/not found in your text/.test(h.text));
  const missing = hdrs.find(h => /not found in your text/.test(h.text));

  ok(!!missing, 'a component whose anchor was NOT found says so on the page, outside any disclosure');
  ok(!!found && !/Anchored to:/.test(found.text) && !/Bound by the source:/.test(found.text)
     && !/Common context/.test(found.text) && !/The text\'s own stance:/.test(found.text),
     'a component whose anchor WAS found keeps the machinery out of the reader\'s way: '
     + JSON.stringify(found && found.text.slice(0, 120)));
  ok(!!found && /how this was pulled out of your text/.test(found.summary),
     'and names what it put away, rather than simply dropping it: ' + JSON.stringify(found && found.summary));
  ok(!!found && found.open === false, 'the machinery disclosure starts closed');

  // NOTHING WAS DELETED. Opening it has to bring it all back, or this block
  // traded a confusing page for a dishonest one.
  const reopened = await page.evaluate(() => {
    [...document.querySelectorAll('#result-area details.case')].forEach(d => { d.open = true; });
    return document.getElementById('result-area').innerText;
  });
  ok(/Anchored to:/.test(reopened) && /Bound by the source:/.test(reopened)
     && /Common context/.test(reopened),
     'opening the disclosure brings the anchor and the constraint back — collapsed, not dropped');

  // 114b: and the record has to still hold them a day later. This is the
  // same page, reached the way Recent reaches it: from the stored snapshot,
  // not from the run. It used to arrive with six fields out of thirteen.
  ok(/shown in the text|a reading — one interpretation among others/.test(reopened),
     'the reopened run still knows whether a component was shown in the text or read into it');

  // ---- 9. block 116: the mark, and the live door -----------------------
  // Every older pin for these sentences greps index.html, and moving a
  // sentence into a whyHtml('...') argument leaves it in index.html. So the
  // suite can no longer tell the face from the mark and this is the only
  // place that can.
  await page.evaluate(t => loadPastResult(t), IDS.groupFailed);
  await page.waitForTimeout(1400);
  const mk = await page.evaluate(() => {
    const el = document.getElementById('result-area');
    const marks = [...el.querySelectorAll('.why-mark')];
    return {text: el.innerText, n: marks.length,
            expanded: marks.map(m => m.getAttribute('aria-expanded')),
            isButton: marks.every(m => m.tagName === 'BUTTON'),
            controls: marks.every(m => !!document.getElementById(m.getAttribute('aria-controls')))};
  });
  ok(mk.n > 0, 'the card carries marks: ' + mk.n);
  ok(mk.isButton && mk.controls && mk.expanded.every(x => x === 'false'),
     'each mark is a real control, announced closed, pointing at an element that exists');
  // NAMED ON A LESSON THAT IS GENUINELY ON THE CARD. The first version of
  // this listed three lessons that all live inside a closed `show the case`
  // disclosure, so innerText excluded them whether the mark worked or not —
  // a check that could not fail. This one is the live door's own
  // explanation, which sits directly in the card with nothing above it.
  ok(!/the check that placed it runs once/.test(mk.text),
     'the live door explains itself only when asked, not on every card forever');

  // THE FINDING IS STILL THERE. This is block 114's rule with a sharper
  // edge: a mark is quieter than a disclosure, and a finding may not be quiet.
  // These are the findings THIS page actually carries — the verdict rows.
  // (The first version of this check looked for findings the fixture does not
  // produce, which would have passed the day the rows were emptied.)
  ok(/the quote is not in your text/.test(mk.text) && /source warrant FAILED/.test(mk.text),
     'the findings themselves are still on the face: '
     + JSON.stringify(mk.text.slice(0, 100)));

  // AND NOTHING WAS DELETED — pressing a mark brings its sentence back.
  const pressed = await page.evaluate(() => {
    // A mark that is NOT inside a closed disclosure — unhiding a body whose
    // ancestor <details> is shut changes innerText by nothing, and the first
    // version of this measured exactly that and concluded the mark was broken.
    const m = document.querySelector('#result-area .door-head .why-mark');
    m.click();
    return {text: document.getElementById('result-area').innerText,
            expanded: m.getAttribute('aria-expanded'), label: m.textContent};
  });
  ok(pressed.expanded === 'true' && pressed.label === '\u00d7',
     'pressing a mark announces itself open and says so in its own label');
  ok(pressed.text.length > mk.text.length,
     'pressing a mark brings text back onto the page — the lesson is hidden, not dropped');

  // ---- the live door, called directly ----------------------------------
  // The suite can only see that a branch EXISTS. A mutation that makes the
  // branch unreachable leaves its text in the file and passes every source
  // pin — which is the failure this project has already shipped three times.
  // Calling the function is the only thing that can tell reachable from
  // present.
  const doors = await page.evaluate(() => {
    const D = (ai, cs, verdict, note) => liveDoor({
      friction: {verdict, hostile_read: note ? 'x' : ''},
      anchor_integrity: ai ? {status: ai} : undefined,
      claim_support: cs ? {support: cs} : undefined});
    return {
      bothBroken: D('not_found', 'not_run', 'reject', true).key,
      anchorOnly: D('not_found', 'not_run', 'keep', false).key,
      objectionOnly: D('exact', 'supported', 'existing', true).key,
      clean: D('exact', 'supported', 'keep', false).key,
      // an objection with nothing recorded to test is not a Verify case
      objectionNoClaims: D('exact', 'supported', 'reject', false).key,
    };
  });
  ok(doors.bothBroken === 'verify-not-anchor',
     'a card with BOTH a failed warrant and a craft objection names the door that moves the '
     + 'objection instead of burying it: ' + doors.bothBroken);
  ok(doors.anchorOnly === 'none',
     'a failed warrant with no objection is told plainly that nothing here repairs it: ' + doors.anchorOnly);
  ok(doors.objectionOnly === 'verify', 'an objection on a sound warrant routes to Verify: ' + doors.objectionOnly);
  ok(doors.clean === 'travel', 'an uncontested card is told the doors travel: ' + doors.clean);
  ok(doors.objectionNoClaims === 'travel',
     'an objection with no recorded claims does not offer Verify, which would have nothing to '
     + 'test: ' + doors.objectionNoClaims);

  // ---- the live door ---------------------------------------------------
  const door = await page.evaluate(() => {
    const el = document.getElementById('result-area');
    const sums = [...el.querySelectorAll('details.case > summary')].map(x => x.textContent.trim());
    return {text: el.innerText, sums,
            heads: [...el.querySelectorAll('.door-head')].map(x => x.textContent.trim())};
  });
  // These candidates were built on an anchor that is not in the source, and
  // nothing on a card re-runs the anchor check — so the honest answer is that
  // there is no door, and the app says it rather than offering five that
  // cannot do the job.
  ok(door.heads.some(h => /Nothing on this card repairs the warrant/.test(h)),
     'a candidate with a broken warrant is told plainly that no door here repairs it: '
     + JSON.stringify(door.heads.slice(0, 2)));
  ok(!/Sprout — travel laterally/.test(door.text),
     'the doors that cannot change this card are not competing with the one that can');
  const opened = await page.evaluate(() => {
    [...document.querySelectorAll('#result-area details.case')].forEach(d => { d.open = true; });
    return document.getElementById('result-area').innerText;
  });
  ok(/Sprout — travel laterally/.test(opened) && /Refract/.test(opened) && /Archetype/.test(opened),
     'and they are one press away, not removed');

  // ---- 8. block 115: what the record counted ---------------------------
  // The panel is arithmetic over rows already on the shelf, so the only
  // things worth proving in a browser are that it reaches the page at all
  // and that it does not quietly become advice.
  await page.goto(BASE + '/#concepts');
  await page.waitForTimeout(2000);
  const lib = await page.evaluate(() => {
    const el = document.getElementById('library-content');
    return {text: el ? el.innerText : '', has: !!(el && /What the record counted/.test(el.innerText))};
  });
  ok(lib.has, 'the counted panel reaches the shelf: ' + JSON.stringify(lib.text.slice(0, 160)));
  ok(/Counting only/.test(lib.text),
     'and says on the page that it is counting, not ruling');
  ok(!/\bshould\b|\bconsider\b|\brecommend/i.test(lib.text.split('Counting only')[1].slice(0, 900)),
     'the counted panel does not recommend anything');

  // ---- 10. block 117: the Vault strip, against the REAL producer -------
  // These five status objects were captured from vault.status() itself in a
  // throwaway directory. Every journey used to mock this endpoint with one
  // healthy literal, so the red path had never rendered and a renamed field
  // would have left the strip green forever — on the guarantee that is
  // supposed to be the floor.
  const strip = await page.evaluate(states => {
    const out = {};
    for (const [name, v] of Object.entries(states)) out[name] = vaultStripState(v);
    return out;
  }, VAULT);
  ok(strip.healthy.hidden === true && strip.healthy.quiet === true && strip.healthy.red === false,
     'a healthy Vault goes quiet and gets out of the way');
  ok(strip.uninitialised.red === true && /No vault/.test(strip.uninitialised.text),
     'no Vault at all is red and says the corpus is on this disk only: '
     + JSON.stringify(strip.uninitialised.text.slice(0, 40)));
  ok(strip.dirty.hidden === true,
     'unsealed changes under the ceiling are not yet an alarm');
  ok(strip.stale.red === true && /unsealed changes for/.test(strip.stale.text),
     'unsealed past the ceiling turns red by itself: ' + JSON.stringify(strip.stale.text.slice(-40)));
  ok(strip.failed.red === true && /did not complete/.test(strip.failed.text),
     'a recorded failure is shown in the failure\'s own words, not a generic red');
  // AND THE STATES THAT SHOULD DIFFER, DO. Not all five: `dirty` renders
  // exactly like `healthy` ON PURPOSE — under the staleness ceiling the
  // debounce says this is not yet an alarm, and the strip stays out of the
  // way. The first version of this check demanded five distinct sentences and
  // failed on that deliberate equality, which would have been a real defect
  // introduced by a test.
  ok(strip.dirty.text === strip.healthy.text && strip.dirty.hidden === strip.healthy.hidden,
     'unsealed-but-under-the-ceiling is deliberately indistinguishable from healthy');
  const loud = ['uninitialised', 'healthy', 'stale', 'failed'].map(k => strip[k].text);
  ok(new Set(loud).size === 4,
     'the four states that must differ render four different strips: '
     + JSON.stringify(loud.map(t => t.slice(0, 24))));

  ok(errs.length === 0, 'no page errors across the epistemic journey: ' + JSON.stringify(errs));
  await browser.close();
  finish('epistemic');
})();
