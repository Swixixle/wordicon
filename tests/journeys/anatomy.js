// The anatomy journey — /anatomy (block 98) in a real browser: the gate,
// zero network beyond the document, no motion before a click, the thesis
// on first paint at laptop size, the walk, light and dark, the table
// fallback on a phone. Prints one line per check; exits 1 on any failure.
// Run by tests/journeys/run.sh (locally or in CI).
const { BASE, ok, launch, pairedContext, finish } = require('./lib');

(async () => {
  const browser = await launch();
  const paired = (opts = {}) => pairedContext(browser, { viewport: { width: 1280, height: 900 }, ...opts });

  // 1. the gate still protects the route
  {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    const resp = await page.goto(BASE + '/anatomy');
    ok(page.url().endsWith('/pair'), 'unpaired visit to /anatomy lands on /pair (' + page.url() + ')');
    await ctx.close();
  }

  // 2. zero network beyond the document; no motion before a click
  const ctx = await paired();
  const page = await ctx.newPage();
  const reqs = []; page.on('request', r => reqs.push(r.url()));
  const errs = []; page.on('pageerror', e => errs.push(String(e)));
  await page.goto(BASE + '/anatomy');
  await page.waitForTimeout(2200);
  ok(reqs.length === 1 && reqs[0] === BASE + '/anatomy', 'the only request is the page itself: ' + JSON.stringify(reqs));
  ok(errs.length === 0, 'no page errors: ' + JSON.stringify(errs));
  const rest = await page.evaluate(() => ({ status: document.getElementById('status').textContent, hidden: document.getElementById('token').classList.contains('hidden'), step: state.step, running: state.running, timer: state.timer }));
  ok(rest.status === 'at rest' && rest.hidden && rest.step === -1 && !rest.running && rest.timer === null, 'dormant after 2.2s: ' + JSON.stringify(rest));
  const custody = await page.textContent('#custody');
  ok(/as of \d{4}-\d{2}-\d{2} · commit \S+/.test(custody), 'custody line shows as-of date and commit: ' + custody);

  // 2b. first paint at laptop size: Memory, Owner, and the Witness on screen without scrolling; nothing dimmed; light and dark identical
  for (const scheme of ['dark', 'light']) {
    const cl = await paired({ viewport: { width: 1280, height: 800 }, colorScheme: scheme });
    const pl = await cl.newPage(); await pl.goto(BASE + '/anatomy'); await pl.waitForTimeout(300);
    const fp = await pl.evaluate(() => { const r = id => document.querySelector(`.organ[data-id="${id}"]`).getBoundingClientRect(); const v = b => b.top >= 0 && b.bottom <= innerHeight; return { m: v(r('memory')), o: v(r('owner')), w: v(r('witness')), dim: document.querySelectorAll('.organ.is-dim').length, layout: LAYOUT, bg: getComputedStyle(document.body).backgroundColor, shapes: document.querySelectorAll('.organ').length }; });
    ok(fp.m && fp.o && fp.w && fp.dim === 0 && fp.layout === 'wide' && fp.shapes === 15, `${scheme} scheme, 1280x800 first paint: memory/owner/witness on screen, nothing dimmed, 15 organs (${JSON.stringify(fp)})`);
    if (scheme === 'light') ok(fp.bg === 'rgb(17, 22, 29)', 'the page paints its own ground in light mode (' + fp.bg + ')');
    await cl.close();
  }
  await page.click('.organ[data-id="world"]');
  const wd = await page.textContent('#detail');
  ok(wd.includes('OUTSIDE WORLD') && wd.includes('Outside the membrane') && wd.includes('How it can fail'), 'the Outside World is a clickable node with a detail card');
  await page.click('.organ[data-id="world"]');
  ok((await page.$$eval('#table-view tr[data-id]', rs => rs.map(r => r.dataset.id))).includes('world'), 'the table fallback lists the Outside World');

  // 3. the laws are on the organs; unbuilt tissue is dashed and labeled
  const organ = async (id) => page.evaluate((id) => {
    const g = document.querySelector(`.organ[data-id="${id}"]`);
    const shape = g.querySelector('.organ-shape');
    return { text: g.textContent, cls: g.getAttribute('class'), dash: getComputedStyle(shape).strokeDasharray, opacity: getComputedStyle(g).opacity, display: getComputedStyle(g).display };
  }, id);
  const b = await organ('boundary'); ok(b.text.includes('advises, never decides') && b.text.includes('BOUNDARY & CRITIQUE'), 'Boundary & Critique prints "advises, never decides"');
  const v = await organ('vault'); ok(v.text.includes('VAULT / RESTORATION') && v.text.includes('never regeneration') && !/REGENERATION\b/.test(v.text.replace('never regeneration', '')), 'Vault says restoration, never regeneration');
  const r = await organ('rooms'); ok(r.text.includes('awaiting shadow-mode validation'), 'Clinic visibly awaits shadow-mode validation');
  for (const id of ['archive', 'publication']) { const u = await organ(id); ok(u.cls.includes('unbuilt') && u.text.includes('UNBUILT TISSUE') && u.dash !== 'none', id + ' is dashed and labeled UNBUILT TISSUE (' + u.dash + ')'); }
  const centerPos = await page.evaluate(() => { const out = {}; for (const L of ['wide', 'tall']) { const m = NODES.memory.pos[L], o = NODES.owner.pos[L], mb = DATA.layouts[L].membrane; const cx = mb.kind === 'rect' ? mb.x + mb.w / 2 : DATA.layouts[L].canvas.w / 2; out[L] = { dx: Math.abs(m[0] - cx), sameRow: o[1] === m[1], right: o[0] > m[0] }; } return out; });
  ok(Object.values(centerPos).every(c => c.dx < 75 && c.sameRow && c.right), 'Memory is central and the Owner sits beside it in both layouts: ' + JSON.stringify(centerPos));
  const witnessEdges = await page.evaluate(() => DATA.edges.filter(e => e.from === 'witness').map(e => e.to));
  ok(witnessEdges.length && witnessEdges.every(t => t === 'owner'), 'External Witness reaches only the Owner: ' + JSON.stringify(witnessEdges));
  ok((await page.$$('.edge[data-from="witness"][data-to="memory"]')).length === 0, 'no witness→memory pathway in the DOM');
  const stories = await page.$$eval('#story option', os => os.map(o => ({ v: o.value, d: o.disabled, t: o.textContent })));
  ok(stories.find(s => s.v === 'publication').d && /unbuilt/.test(stories.find(s => s.v === 'publication').t), 'the publication cycle is visibly unavailable: ' + stories.find(s => s.v === 'publication').t);

  // 4. Set it in motion → every step, then finished; nothing loops
  await page.click('#btn-motion');
  const seen = [];
  for (let i = 0; i < 60; i++) {
    await page.waitForTimeout(300);
    const st = await page.evaluate(() => state.step);
    if (seen[seen.length - 1] !== st) seen.push(st);
    const status = await page.textContent('#status');
    if (status.startsWith('finished')) break;
  }
  const steps = await page.evaluate(() => story().steps.length);
  ok(seen.join(',') === Array.from({ length: steps }, (_, i) => i).join(','), 'motion visited every step in order: ' + seen.join(','));
  const fin = await page.evaluate(() => ({ status: document.getElementById('status').textContent, narr: document.getElementById('narration').textContent, step: state.step, running: state.running, timer: state.timer, tr: document.getElementById('token').style.transform }));
  ok(fin.status.startsWith('finished') && fin.step === steps - 1 && !fin.running && fin.timer === null, 'final state: finished, not running, no timer: ' + fin.status);
  ok(fin.narr.includes('11/11') && fin.narr.includes('VAULT') && fin.narr.includes('Forbidden from changing'), 'final narration is the vault step with its forbidden clause');
  const vaultPos = await page.evaluate(() => box(NODES.vault));
  ok(fin.tr.includes(`translate(${vaultPos.x}px`), 'token rests at the Vault: ' + fin.tr);
  ok(fin.narr.includes('seals the resulting record') && fin.narr.includes('not a destination for thinking'), 'the Vault step reads as sealing the record, not where thinking culminates');
  await page.waitForTimeout(2500);
  ok((await page.evaluate(() => state.step)) === steps - 1 && (await page.evaluate(() => state.timer)) === null, 'nothing loops after finishing');
  // Set it in motion again at the end does not restart
  await page.click('#btn-motion'); await page.waitForTimeout(400);
  ok((await page.evaluate(() => state.step)) === steps - 1 && !(await page.evaluate(() => state.running)), 'pressing Set it in motion at the end does not restart the story');

  // 5. Reset, Step ×N: each step renders its sentence and its organ
  await page.click('#btn-reset');
  ok((await page.evaluate(() => state.step)) === -1 && (await page.textContent('#status')) === 'at rest', 'Reset returns to rest');
  const stepStory = await page.evaluate(() => story().steps);
  let stepOk = true;
  for (let i = 0; i < stepStory.length; i++) {
    await page.click('#btn-step');
    const got = await page.evaluate(() => ({ step: state.step, narr: document.getElementById('narration').textContent, tr: document.getElementById('token').style.transform }));
    const n = await page.evaluate((id) => box(NODES[id]), stepStory[i].at);
    if (!(got.step === i && got.narr.includes(stepStory[i].changed.slice(0, 30)) && got.narr.includes(stepStory[i].forbidden.slice(0, 30)) && got.tr.includes(`translate(${n.x}px`))) { stepOk = false; console.log('  step mismatch', i, got.step, got.tr); }
  }
  ok(stepOk, 'Step walked all ' + stepStory.length + ' steps with sentence and organ each time');

  // 6. Pause holds; switching views keeps the step
  await page.click('#btn-reset'); await page.click('#btn-motion'); await page.waitForTimeout(2000); await page.click('#btn-pause');
  const heldAt = await page.evaluate(() => state.step); await page.waitForTimeout(2200);
  ok((await page.evaluate(() => state.step)) === heldAt && (await page.textContent('#status')) === 'paused', 'Pause holds the step (' + heldAt + ')');
  await page.click('#view-table'); const tableStep = await page.evaluate(() => state.step);
  const rowLit = await page.evaluate((at) => document.querySelector(`#table-view tr[data-id="${at}"]`).classList.contains('at'), stepStory[heldAt].at);
  await page.click('#view-diagram');
  ok(tableStep === heldAt && (await page.evaluate(() => state.step)) === heldAt && rowLit, 'switching Table/Diagram keeps the step and marks the row');
  await page.click('.chip[data-cls="preserves"]'); ok((await page.evaluate(() => state.step)) === heldAt, 'a relationship filter keeps the step');

  // 7. filters and selection: only immediate relationships lit; status labels stay visible
  const hid = await page.$$eval('.edge', es => es.filter(e => !e.classList.contains('is-hidden')).map(e => e.dataset.cls));
  ok(hid.length && hid.every(c => c === 'preserves'), 'Preserves filter shows only preserves pathways');
  await page.click('.chip[data-cls="all"]');
  await page.click('.organ[data-id="boundary"]');
  const sel = await page.evaluate(() => {
    const lit = [...document.querySelectorAll('.edge.lit')].map(e => e.dataset.from + '>' + e.dataset.to);
    const bad = lit.filter(x => !x.split('>').includes('boundary'));
    const dim = [...document.querySelectorAll('.organ.is-dim')].map(g => ({ id: g.dataset.id, op: getComputedStyle(g.querySelector('.organ-title')).opacity, disp: getComputedStyle(g).display, status: g.querySelector('.status').textContent, shape: getComputedStyle(g.querySelector('.organ-shape')).opacity }));
    return { lit, bad, dim, detail: document.getElementById('detail').textContent };
  });
  ok(sel.lit.length > 0 && sel.bad.length === 0, 'selecting an organ lights only its immediate pathways');
  ok(sel.dim.length > 0 && sel.dim.every(d => parseFloat(d.op) === 1 && parseFloat(d.shape) < 1 && d.disp !== 'none' && d.status.length > 0), 'focusing an organ dims other silhouettes, never their text');
  ok(['What it does', 'What it contributes', 'What constrains it', 'How it can fail', 'Implementation witness', 'never invents a boundary'].every(t => sel.detail.includes(t)), 'organ detail shows the four fields, the law, and the witness');

  // 8. widths: no horizontal scroll at desktop / split / phone
  for (const [name, w] of [['desktop', 1280], ['split', 700], ['phone', 390]]) {
    await page.setViewportSize({ width: w, height: 900 }); await page.waitForTimeout(250);
    const m = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth, view: state.view, step: state.step }));
    const lay = await page.evaluate(() => LAYOUT);
    ok(m.sw <= m.iw && m.step === heldAt && (w >= 1000 ? lay === 'wide' : lay === 'tall'), `${name} ${w}px: no horizontal overflow (${m.sw}/${m.iw}), layout=${lay}, view=${m.view}, step kept`);
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  await ctx.close();

  // 9. reduced motion: discrete steps, no travel transition
  {
    const c2 = await paired({ reducedMotion: 'reduce' });
    const p2 = await c2.newPage(); await p2.goto(BASE + '/anatomy'); await p2.waitForTimeout(300);
    await p2.click('#btn-step');
    const rm = await p2.evaluate(() => ({ dur: getComputedStyle(document.getElementById('token')).transitionDuration, prop: getComputedStyle(document.getElementById('token')).transitionProperty, step: state.step, reduced: REDUCED }));
    ok(rm.reduced && (rm.dur === '0s' || rm.prop === 'none') && rm.step === 0, 'reduced motion: step changes without travel (' + rm.prop + ' ' + rm.dur + ')');
    await c2.close();
  }

  // 10. back returns to the Wordicon state the visitor left
  {
    const c3 = await paired(); const p3 = await c3.newPage();
    await p3.goto(BASE + '/'); await p3.waitForTimeout(800);
    await p3.fill('#input-text', 'anatomy journey draft'); await p3.dispatchEvent('#input-text', 'input');
    const link = await p3.$('a[href="/anatomy"]'); ok(!!link, 'the What is Wordicon panel carries the See the anatomy link');
    await p3.evaluate(() => { const d = document.querySelector('a[href="/anatomy"]').closest('details'); if (d) d.open = true; });
    await p3.click('a[href="/anatomy"]'); await p3.waitForURL('**/anatomy'); await p3.waitForTimeout(300);
    await p3.click('button.link'); await p3.waitForURL(u => u.pathname === '/'); await p3.waitForTimeout(800);
    const back = await p3.evaluate(() => ({ text: document.getElementById('input-text').value, path: location.pathname }));
    ok(back.path === '/' && back.text === 'anatomy journey draft', 'back returns to / with the draft intact: ' + JSON.stringify(back));
    await c3.close();
  }

  await browser.close();
  finish('anatomy');
})();
