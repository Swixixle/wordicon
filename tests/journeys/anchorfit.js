// The anchor-fit journey (block 122).
//
// The defect: five materially different anchor-fit results were drawn as one
// row a reader scans as a badge. A census of the owner's real corpus found
// 539 candidate rows carrying a verdict — 54.2% partial, 25.0% topical,
// 11.5% not_run, 6.3% supported, 2.4% contradicted. That is a five-state
// distribution with a large modal class, NOT a check that says the same
// thing every time; the evaluator is untouched here. What failed was the
// drawing of it.
//
// The synthetic fixture carries the same structural failure the owner hit:
// a broad MID-DAY interval, narrowed by the candidate into an
// after-school-to-dinner boundary the anchor never contained.
const { BASE, ok, launch, pairedContext, finish } = require('./lib');

const ANCHOR = 'it happened during one of the midday hours that tend to cradle';
const CLAIM  = 'the interval between school letting out and dinner being called';

function bff(support, extra) {
  return Object.assign({
    title: 'The Midday Interval',
    anchor_integrity: {status: 'exact'},
    claim_support: Object.assign({support: support}, extra || {}),
    friction: {verdict: 'keep'},
    flesh: {}, bone: {},
  });
}

(async () => {
  const browser = await launch();
  const ctx = await pairedContext(browser);
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(String(e)));
  await page.goto(BASE + '/');
  await page.waitForTimeout(700);

  // ---- 1. all five states render distinctly -----------------------------
  const states = await page.evaluate((args) => {
    const mk = (support, extra) => ({
      title: 'The Midday Interval',
      anchor_integrity: {status: 'exact'},
      claim_support: Object.assign({support: support}, extra || {}),
      friction: {verdict: 'keep'}, flesh: {}, bone: {},
    });
    const out = {};
    for (const s of ['supported', 'partial', 'topical', 'contradicted', 'not_run']) {
      const b = mk(s, {deciding_anchor_words: args.a, deciding_claim_words: args.c});
      const row = verdictRows(b, {}).find(r => r[0] === 'Anchor fit');
      const el = document.createElement('div');
      el.innerHTML = anchorFitLine(b);
      document.body.appendChild(el);
      // THE DRAWN MARK, not the state token. Checking the token passed while
      // `contradicted` and `supported` rendered the identical filled circle —
      // a state table can be five-valued and still draw four things.
      out[s] = {state: row[1], glyph: DOT[row[1]], why: row[2], line: el.innerText.trim()};
      el.remove();
    }
    return out;
  }, {a: 'midday, cradle', c: 'school, dinner'});

  const whys = Object.values(states).map(s => s.why);
  ok(new Set(whys).size === 5,
     'all five anchor-fit states say something different :: ' + JSON.stringify(whys));
  const glyphs = Object.values(states).map(s => s.glyph);
  ok(new Set(glyphs).size === 5,
     'all five states are DRAWN differently — five marks, not five names over four marks :: '
     + JSON.stringify(glyphs));
  ok(new Set(Object.values(states).map(s => s.state)).size === 5,
     'and the state table underneath is five-valued :: '
     + JSON.stringify(Object.values(states).map(s => s.state)));
  ok(states.contradicted.glyph !== states.topical.glyph,
     'contradicted no longer shares a mark with topical :: '
     + states.contradicted.glyph + ' vs ' + states.topical.glyph);
  ok(!whys.some(w => /grounded/i.test(w)),
     'the row no longer claims grounding, which it never measured :: ' + JSON.stringify(whys));

  // ---- 2. the deciding difference is ON THE CARD ------------------------
  for (const s of ['partial', 'topical', 'contradicted']) {
    ok(states[s].line.includes('midday') && states[s].line.includes('school'),
       `${s} names the deciding difference without opening anything :: ` + states[s].line);
    ok(/not a mechanical proof|recorded reason/.test(states[s].line),
       `${s} says where its evidence came from :: ` + states[s].line);
  }
  ok(states.supported.line === '' && states.not_run.line === '',
     'a supported or unchecked result adds no deciding line :: '
     + JSON.stringify([states.supported.line, states.not_run.line]));

  // the recorded reason is preferred over the word list when it exists
  const withNote = await page.evaluate(() => {
    const b = {anchor_integrity: {status: 'exact'},
               claim_support: {support: 'partial', note: 'the anchor says midday; the claim adds a school boundary',
                               deciding_anchor_words: 'midday'},
               friction: {verdict: 'keep'}, flesh: {}, bone: {}};
    const el = document.createElement('div');
    el.innerHTML = anchorFitLine(b);
    document.body.appendChild(el);
    const t = el.innerText.trim(); el.remove(); return t;
  });
  ok(/the anchor says midday; the claim adds a school boundary/.test(withNote)
     && /recorded reason/.test(withNote),
     'the reviewer\'s recorded reason is used when it exists :: ' + withNote);

  // ---- 3. the deciding line survives every disclosure being closed ------
  const visible = await page.evaluate((args) => {
    const b = {title: 'The Midday Interval',
               anchor_integrity: {status: 'exact'},
               claim_support: {support: 'partial', deciding_anchor_words: args.a,
                               deciding_claim_words: args.c},
               friction: {verdict: 'keep'},
               flesh: {definition: 'd'}, bone: {}};
    const el = document.createElement('div');
    el.innerHTML = renderCandidateCard({title: 'The Midday Interval', bone_flesh_friction: b,
                                        claims_detail: []}, 'trace_x', {});
    document.body.appendChild(el);
    el.querySelectorAll('details').forEach(d => d.removeAttribute('open'));
    const t = el.innerText; el.remove(); return t;
  }, {a: 'midday, cradle', c: 'school, dinner'});
  ok(/Why partial/.test(visible),
     'the deciding difference is readable with every disclosure closed :: '
     + visible.slice(0, 140));
  ok(/midday/.test(visible) && /school/.test(visible),
     'the narrowing itself is on the face of the card :: ' + visible.slice(0, 160));

  // ---- 4. advisory, said once, and a ruling is still possible ----------
  const notice = await page.evaluate(() => {
    const c = [{title: 'A', bone_flesh_friction: {claim_support: {support: 'partial'},
               anchor_integrity: {status: 'exact'}, friction: {}, flesh: {}, bone: {}}, claims_detail: []},
               {title: 'B', bone_flesh_friction: {claim_support: {support: 'topical'},
               anchor_integrity: {status: 'exact'}, friction: {}, flesh: {}, bone: {}}, claims_detail: []}];
    const el = document.createElement('div');
    el.innerHTML = anchorFitNoticeHtml(c) + c.map(x => renderCandidateCard(x, 't', {})).join('');
    document.body.appendChild(el);
    const t = el.innerText;
    const n = (t.match(/never blocks Keep/g) || []).length;
    const buttons = [...el.querySelectorAll('button')].map(b => b.innerText.trim());
    el.remove();
    return {n, advisory: /Anchor fit is advisory/.test(t),
            keep: buttons.filter(b => /Keep this concept/i.test(b)).length,
            revise: buttons.filter(b => /Revise/i.test(b)).length};
  });
  ok(notice.advisory && notice.n === 1,
     'the non-gating status is stated once for the run, not on every card :: '
     + JSON.stringify(notice));
  ok(notice.keep === 2 && notice.revise === 2,
     'a partial and a topical candidate both still offer Keep and Revise :: '
     + JSON.stringify(notice));

  const denied = await page.evaluate(() => {
    const el = document.createElement('div');
    el.innerHTML = renderCandidateCard({title: 'C', claims_detail: [], bone_flesh_friction: {
      claim_support: {support: 'contradicted', deciding_anchor_words: 'midday'},
      anchor_integrity: {status: 'exact'}, friction: {verdict: 'keep'}, flesh: {}, bone: {}}}, 't', {});
    document.body.appendChild(el);
    const buttons = [...el.querySelectorAll('button')].map(b => b.innerText.trim());
    el.remove();
    return buttons.filter(b => /Keep this concept|Revise|Set it aside/i.test(b)).length;
  });
  ok(denied === 3,
     'even a contradicted candidate keeps all three rulings — the row advises, it does not gate :: '
     + denied);

  ok(errs.length === 0, 'no page errors :: ' + errs.join(' | '));
  await browser.close();
  finish('anchorfit');
})();
