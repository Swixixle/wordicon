// The constitution journey (block 121).
//
// The law moved out of the home page's What-is panel onto /constitution.
// Three things need a real browser to testify to, and source review cannot:
//
//   1. That the disclosure controls open BY KEYBOARD. A <details> is
//      keyboard-operable natively, but only if the control is a real
//      <summary> — a div styled to look like one satisfies every grep and
//      is unreachable without a mouse.
//   2. That the compact panel's promises reach the clauses they claim. A
//      dead anchor is a paraphrase with a link painted on it.
//   3. That nothing which reports RUNTIME STATE went to the inert page.
//      Hide explanation when necessary; never hide state.
const { BASE, ok, launch, pairedContext, finish } = require('./lib');

(async () => {
  const browser = await launch();
  const ctx = await pairedContext(browser);
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(String(e)));

  // ---- the canonical page ---------------------------------------------
  const resp = await page.goto(BASE + '/constitution');
  ok(resp && resp.status() === 200, 'the constitution is served :: ' + (resp && resp.status()));
  await page.waitForTimeout(300);

  const shape = await page.evaluate(() => ({
    movements: [...document.querySelectorAll('.about-movement')].map(e => e.innerText.split('\n')[0].trim()),
    sections: document.querySelectorAll('details.canon').length,
    summaries: document.querySelectorAll('details.canon > summary').length,
    toc: [...document.querySelectorAll('.toc a')].map(a => a.getAttribute('href')),
    openAtLoad: document.querySelectorAll('details.canon[open]').length,
  }));
  ok(shape.movements.length === 5, 'all five movements are on the page :: ' + shape.movements.length);
  ok(shape.summaries === shape.sections,
     'every disclosure has a real <summary>, so every one has a keyboard :: '
     + shape.summaries + '/' + shape.sections);
  ok(shape.toc.length >= shape.sections + 5, 'the contents lists every part :: ' + shape.toc.length);

  // every contents entry lands on something that exists
  const deadAnchors = await page.evaluate(() =>
    [...document.querySelectorAll('.toc a')]
      .map(a => a.getAttribute('href').slice(1))
      .filter(id => !document.getElementById(id)));
  ok(deadAnchors.length === 0, 'no contents entry points at nothing :: ' + JSON.stringify(deadAnchors));

  // ---- KEYBOARD, not pointer -------------------------------------------
  // Tab to the first summary and press Enter. If the control were a styled
  // div this is exactly where it would fail, silently, for anyone who does
  // not use a mouse.
  const kb = await page.evaluate(() => {
    const s = document.querySelector('details.canon > summary');
    s.focus();
    return { focused: document.activeElement === s, openBefore: s.parentElement.open };
  });
  ok(kb.focused, 'the first disclosure control can take keyboard focus :: ' + JSON.stringify(kb));
  await page.keyboard.press('Enter');
  await page.waitForTimeout(120);
  const afterEnter = await page.evaluate(() =>
    document.querySelector('details.canon').open);
  ok(afterEnter && !kb.openBefore,
     'Enter on the focused control opens the explanation :: ' + afterEnter);
  const textWhenOpen = await page.evaluate(() =>
    document.querySelector('details.canon .canon-body').innerText.trim().length);
  ok(textWhenOpen > 200, 'the opened disclosure reveals real text, not a stub :: ' + textWhenOpen);

  // expand-all is a real button and reveals the whole law
  const expanded = await page.evaluate(async () => {
    const b = document.getElementById('expand-all');
    b.focus();
    const focused = document.activeElement === b;
    b.click();
    return { focused, tag: b.tagName,
             open: document.querySelectorAll('details.canon[open]').length,
             total: document.querySelectorAll('details.canon').length,
             words: document.body.innerText.split(/\s+/).length };
  });
  ok(expanded.tag === 'BUTTON' && expanded.focused,
     'expand-everything is a real, focusable button :: ' + JSON.stringify(expanded));
  ok(expanded.open === expanded.total,
     'expand-everything opens every section :: ' + expanded.open + '/' + expanded.total);
  ok(expanded.words > 6000,
     'the whole law is readable in one pass when expanded :: ' + expanded.words + ' words');

  // ---- the inert page carries no runtime state -------------------------
  const stateOnCanon = await page.evaluate(() =>
    ['about-provider','about-system','about-epoch','about-encounter','about-speak',
     'about-instruments','epoch-begin','encounter-toggle']
      .filter(id => document.getElementById(id)));
  ok(stateOnCanon.length === 0,
     'no runtime state was moved onto the inert page :: ' + JSON.stringify(stateOnCanon));

  // ---- the home panel: an orientation that points at the law -----------
  await page.goto(BASE + '/');
  await page.waitForTimeout(700);
  const panel = await page.evaluate(() => {
    const p = document.getElementById('about-panel');
    p.open = true;
    const links = [...p.querySelectorAll('a.canon-link')].map(a => ({
      canon: a.getAttribute('data-canon'), href: a.getAttribute('href') }));
    return {
      words: p.innerText.split(/\s+/).length,
      links,
      toConstitution: !!p.querySelector('a[href="/constitution"]'),
      toAnatomy: !!p.querySelector('a[href="/anatomy"]'),
      movements: p.querySelectorAll('.about-movement').length,
      state: ['about-provider','about-epoch','about-encounter','about-speak','about-instruments']
             .filter(id => p.querySelector('#' + id)).length,
    };
  });
  ok(panel.toConstitution, 'the panel opens the constitution :: ' + panel.toConstitution);
  ok(panel.toAnatomy, 'the panel still opens the anatomy :: ' + panel.toAnatomy);
  ok(panel.movements === 0,
     'the panel carries no movement heading — one constitution, not two :: ' + panel.movements);
  ok(panel.words < 1200, 'the panel is an orientation, not the law :: ' + panel.words + ' words');
  ok(panel.state === 5,
     'the machine-state readouts stayed in the panel where they mean something :: ' + panel.state);
  ok(panel.links.length >= 4, 'the refusals are foregrounded :: ' + panel.links.length);

  // every promise in the panel reaches the clause it names
  const ids = await page.evaluate(async (hrefs) => {
    const r = await fetch('/constitution');
    const html = await r.text();
    const doc = new DOMParser().parseFromString(html, 'text/html');
    return hrefs.map(h => ({ h, found: !!doc.getElementById(h) }));
  }, panel.links.map(l => l.canon));
  const broken = ids.filter(x => !x.found).map(x => x.h);
  ok(broken.length === 0,
     'every panel promise reaches the clause that binds it :: ' + JSON.stringify(broken));

  // ---- /anatomy is still its own inert document ------------------------
  const an = await page.goto(BASE + '/anatomy');
  ok(an && an.status() === 200, 'the anatomy is still served separately :: ' + (an && an.status()));
  const anShape = await page.evaluate(() => ({
    isConstitution: !!document.querySelector('details.canon'),
    hasOwnTitle: /anatomy/i.test(document.title),
  }));
  ok(!anShape.isConstitution && anShape.hasOwnTitle,
     'the anatomy was not folded into the constitution :: ' + JSON.stringify(anShape));

  ok(errs.length === 0, 'no page errors :: ' + errs.join(' | '));
  await browser.close();
  finish('constitution');
})();
