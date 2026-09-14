// Screenshots of the application actually running, at two desk sizes, with
// the geometry printed beside each one: how wide the work actually is, how
// many band tracks it actually got, whether any card is clipped, and — in a
// split — whether the room's head clears the bar. A measurement, not an
// eyeball. Synthetic fixtures: the seeded store, never the owner's corpus.
//
// Not a journey and not run by run.sh. It needs a server already up against
// a seeded JOURNEY_DIR:
//   JOURNEY_DIR=<dir> JOURNEY_OUT=<dir>/out SHOT_OUT=<dir> node _shot.js
const { BASE, launch, pairedContext, DIR } = require('./lib');
const fs = require('fs');
const OUT = process.env.SHOT_OUT;
const IDS = JSON.parse(fs.readFileSync(`${DIR}/related.json`, 'utf8'));
const SIZES = [[1440, 900, 'laptop'], [2560, 1400, 'wide']];

// A measurement, not an eyeball: how wide the work actually is, how many
// tracks the bands actually got, and whether anything is clipped.
const geom = () => {
  const bg = document.querySelector('#home-main .band-grid');
  const wide = document.getElementById('work').getBoundingClientRect().width;
  let clipped = 0;
  document.querySelectorAll('#work .card').forEach(c => {
    if (c.scrollWidth > c.clientWidth + 1) clipped++;
  });
  return {work: Math.round(wide),
    rail: Math.round(document.getElementById('rail').getBoundingClientRect().width),
    side: (() => { const s = document.getElementById('side');
      return s && getComputedStyle(s).display !== 'none' ? Math.round(s.getBoundingClientRect().width) : 0; })(),
    bands: bg ? getComputedStyle(bg).gridTemplateColumns : null,
    clippedCards: clipped};
};

(async () => {
  const browser = await launch();
  for (const [w, h, name] of SIZES) {
    const ctx = await pairedContext(browser, {viewport: {width: w, height: h}});
    const page = await ctx.newPage();
    const errs = []; page.on('pageerror', e => errs.push(String(e)));
    await page.goto(BASE + '/'); await page.waitForTimeout(2500);
    await page.screenshot({path: `${OUT}/home-${name}.png`});
    console.log(name, 'home', JSON.stringify(await page.evaluate(geom)));

    // Library — the shelf open, its rows in columns
    await page.evaluate(() => { location.hash = 'library'; });
    await page.waitForTimeout(500);
    await page.evaluate(() => { const b = document.getElementById('library-btn'); if (b) b.click(); });
    await page.waitForTimeout(1500);
    await page.evaluate(() => { const el = document.getElementById('library'); if (el) el.scrollIntoView(); });
    await page.waitForTimeout(500);
    await page.screenshot({path: `${OUT}/library-${name}.png`});

    // A specialized workspace, embedded in the shell
    await page.evaluate(() => { location.hash = ''; window.scrollTo(0, 0); openPlace('/bench', true); });
    await page.waitForTimeout(2500);
    await page.screenshot({path: `${OUT}/workspace-${name}.png`});
    const foot = await page.evaluate(() => {
      const f = document.getElementById('place-frame');
      const r = f.getBoundingClientRect();
      return {frameBottom: Math.round(r.bottom), viewport: window.innerHeight,
              gap: Math.round(window.innerHeight - r.bottom),
              docH: Math.round(document.documentElement.scrollHeight)};
    });
    console.log(name, 'embedded frame', JSON.stringify(foot));
    await page.evaluate(() => closePlace());
    await page.waitForTimeout(600);

    // Writing beside a reading
    await page.evaluate(() => {
      openWorkspace('split');
      const ta = document.getElementById('compose-text');
      ta.value = 'He threw it once, cleanly, and the room laughed.\n\nNobody said so, but the throw was the point — the part of it he could not have explained if asked, and would not have wanted to.';
      ta.dispatchEvent(new Event('input', {bubbles: true}));
    });
    await page.waitForTimeout(600);
    await page.evaluate(t => loadPastResult(t), IDS.full);
    await page.waitForTimeout(2000);
    await page.screenshot({path: `${OUT}/writing-${name}.png`});
    console.log(name, 'writing', JSON.stringify(await page.evaluate(() => {
      const g = (id) => { const e = document.getElementById(id);
        if (!e || !e.offsetParent && getComputedStyle(e).position !== 'fixed') return null;
        const r = e.getBoundingClientRect();
        return {l: Math.round(r.left), r: Math.round(r.right), w: Math.round(r.width)}; };
      const head = g('ws-head'), bar = g('ws-bar');
      const bg = document.querySelector('#home-main .band-grid');
      const rail = document.getElementById('rail');
      const side = document.getElementById('side');
      return {head, bar, overlap: head && bar ? Math.round(head.r - bar.l) : null,
        page: Math.round(document.getElementById('page').getBoundingClientRect().width),
        work: Math.round(document.getElementById('work').getBoundingClientRect().width),
        railH: Math.round(rail.getBoundingClientRect().height),
        railCols: getComputedStyle(rail).flexDirection,
        sideShown: side ? getComputedStyle(side).display !== 'none' : null,
        bands: bg ? getComputedStyle(bg).gridTemplateColumns : null};
    })));
    console.log(name, 'errors:', JSON.stringify(errs.slice(0, 3)));
    await ctx.close();
  }
  await browser.close();
})();
