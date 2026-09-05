// The chooser journey (block 105): words in the box bring up the
// destination row; the cats sentence reads as a question with Research
// highlighted and unbuilt; nothing runs by typing (no job is posted);
// Save as an open question keeps it verbatim and Home counts it quietly;
// Develop the idea is the only way to reach Run it; an invented name with
// a date and a place reads as identity with the studies unbuilt; the
// empty box shows nothing. Runs after home.js on the same scratch store.
const { BASE, ok, launch, pairedContext, finish } = require('./lib');
const healthyVault = { initialized: true, last_seal_at: new Date(Date.now() - 4 * 60000).toISOString(), last_drill_at: new Date(Date.now() - 86400000).toISOString(), cloud: 'iCloud', n_vaults: 31, total_bytes: 125638 * 1024, failure: '', stale_red: false, dirty_seconds: 0 };
const CATS = 'I would like to know about the historical superstitions involving cats.';
const IDENT = 'Rowan Ashby Pell, born 1985-04-11 at 3 p.m. in Duluth, Minnesota';

(async () => {
  const browser = await launch();
  const ctx = await pairedContext(browser); const page = await ctx.newPage();
  await page.route('**/api/vault/status', r => r.fulfill({ json: healthyVault }));
  const posts = []; page.on('request', r => { if (r.method() !== 'GET') posts.push(r.method() + ' ' + r.url().replace(BASE, '')); });
  const errs = []; page.on('pageerror', e => errs.push(String(e)));
  page.on('dialog', d => d.dismiss());
  const api = async (p) => (await page.request.get(BASE + p)).json();
  await page.goto(BASE + '/'); await page.waitForTimeout(1500);
  const before = await page.evaluate(() => ({ rows: document.querySelectorAll('#ruling-area .rule-row').length, more: document.getElementById('ruling-more').textContent }));
  const empty = await page.evaluate(() => ({ row: document.getElementById('destination-row').hidden, dev: document.getElementById('develop-controls').hidden, runVisible: document.getElementById('go-btn').getBoundingClientRect().width > 0 }));
  ok(empty.row && empty.dev && !empty.runVisible, 'an empty box shows no destinations and no Run it');
  // the cats sentence: typed, read, nothing runs
  await page.fill('#input-text', CATS); await page.dispatchEvent('#input-text', 'input'); await page.waitForTimeout(900);
  const c = await page.evaluate(() => {
    const chips = Array.from(document.querySelectorAll('#destination-chips .dest'));
    return { row: document.getElementById('destination-row').hidden, dev: document.getElementById('develop-controls').hidden,
      reading: document.getElementById('destination-reading').textContent.replace(/\s+/g, ' '),
      chips: chips.map(b => ({ id: b.dataset.dest, suggested: b.classList.contains('suggested'), unbuilt: b.classList.contains('unbuilt'), disabled: b.disabled, text: b.textContent.replace(/\s+/g, ' ').trim() })),
      note: document.getElementById('destination-note').textContent };
  });
  ok(!c.row && c.dev, 'typing the cats sentence shows the destination row and keeps Develop\'s controls hidden');
  ok(/Reads as a question/.test(c.reading) && /arrived typed/.test(c.reading) && /Nothing runs until you choose/.test(c.reading), 'the reading names the shape, the arrival, and the law: ' + c.reading.slice(0, 120));
  const ids = c.chips.map(x => x.id).join(',');
  ok(ids === 'research,search,develop,inquiry,room,write,question', 'the question shape offers Research, Search, Develop, Inquiry, Room, Write, Save as an open question: ' + ids);
  const research = c.chips.find(x => x.id === 'research'), develop = c.chips.find(x => x.id === 'develop');
  ok(research && research.suggested && research.unbuilt && research.disabled && /not built/.test(research.text), 'Research is highlighted and unbuilt — a label, not a door: ' + (research && research.text.slice(0, 80)));
  ok(develop && !develop.suggested && !develop.disabled, 'Develop the idea is offered but not highlighted for a question');
  ok(/highlighted destination is not built yet/.test(c.note), 'the note says the highlight is not built: ' + c.note);
  ok(!posts.some(p => /\/api\/jobs/.test(p)), 'nothing was posted to /api/jobs by typing: ' + JSON.stringify(posts));
  // clicking the unbuilt destination does nothing
  await page.click('#destination-chips .dest[data-dest="research"]', { force: true }); await page.waitForTimeout(400);
  ok(!posts.some(p => /\/api\/jobs|\/api\/questions|\/api\/clinic/.test(p)) && await page.evaluate(() => document.getElementById('develop-controls').hidden), 'an unbuilt destination is inert');
  // Save as an open question: kept verbatim, nothing runs, Home counts it, the Library lists it
  await page.click('#destination-chips .dest[data-dest="question"]'); await page.waitForTimeout(1200);
  const qs = await api('/api/questions');
  ok(qs.open.length === 1 && qs.open[0].text === CATS && qs.open[0].provenance === 'typed' && qs.open[0].shape === 'question', 'the question is kept verbatim with its arrival: ' + JSON.stringify(qs.open[0] || {}).slice(0, 160));
  ok(!posts.some(p => /\/api\/jobs/.test(p)) && posts.filter(p => p === 'POST /api/questions').length === 1, 'saving the question ran nothing');
  const note = await page.evaluate(() => (document.getElementById('page-note') || {}).textContent || '');
  ok(/kept as an open question, verbatim/.test(note) && /Nothing ran/.test(note), 'the page says what happened: ' + note.slice(0, 100));
  await page.waitForTimeout(900);
  const line = await page.evaluate(() => { const el = document.getElementById('ruling-questions'); return { hidden: el.hidden, text: el.textContent.replace(/\s+/g, ' ').trim(), rows: document.querySelectorAll('#ruling-area .rule-row').length, more: document.getElementById('ruling-more').textContent, title: (el.querySelector('span[title]') || {}).title || '' }; });
  ok(!line.hidden && /^Open questions 1 kept verbatim — in the Library$/.test(line.text) && line.title === CATS.slice(0, 80) && line.rows === before.rows && line.more === before.more, 'Home carries the open question as a quiet count, not a ruling: ' + line.text + ' | ' + line.more + ' (was ' + before.more + ')');
  await page.click('#ruling-questions a'); await page.waitForTimeout(900);
  const lib = await page.evaluate(() => ({ hash: location.hash, open: document.getElementById('questions-body').style.display !== 'none', text: document.getElementById('questions-list').textContent.replace(/\s+/g, ' '), pill: document.getElementById('questions-count').textContent }));
  ok(lib.hash === '#library' && lib.open && lib.text.includes(CATS) && lib.pill === '1', 'the door opens the Library on the open question: ' + JSON.stringify([lib.hash, lib.open, lib.pill]));
  // Develop the idea is the only way to Run it; the routing chips still follow
  await page.evaluate(() => { document.getElementById('input-text').scrollIntoView(); });
  await page.click('#destination-chips .dest[data-dest="develop"]'); await page.waitForTimeout(400);
  const dev = await page.evaluate(() => ({ dev: document.getElementById('develop-controls').hidden, run: document.getElementById('go-btn').getBoundingClientRect().width > 0, chosen: (document.querySelector('#destination-chips .dest.chosen') || {}).dataset && document.querySelector('#destination-chips .dest.chosen').dataset.dest, gesture: document.getElementById('gesture-chooser').style.display }));
  ok(!dev.dev && dev.run && dev.chosen === 'develop' && dev.gesture === 'none', 'choosing Develop reveals Run it (a sentence, so the gesture chooser stays hidden)');
  ok(!posts.some(p => /\/api\/jobs/.test(p)), 'choosing Develop itself runs nothing');
  // the invented identity: the studies unbuilt, Develop deliberate
  await page.fill('#input-text', IDENT); await page.dispatchEvent('#input-text', 'input'); await page.waitForTimeout(900);
  const i = await page.evaluate(() => ({ dev: document.getElementById('develop-controls').hidden, reading: document.getElementById('destination-reading').textContent.replace(/\s+/g, ' '),
    chips: Array.from(document.querySelectorAll('#destination-chips .dest')).map(b => b.dataset.dest + (b.classList.contains('suggested') ? '*' : '') + (b.disabled ? '!' : '')) }));
  ok(i.dev && /Reads as a name with a date and a place/.test(i.reading) && i.chips.join(',') === 'name_study*!,portrait!,owner_facts!,write,search,develop', 'a name with a date and a place reads as identity; the studies are unbuilt; Develop is a deliberate door: ' + i.chips.join(','));
  ok(!posts.some(p => /\/api\/jobs/.test(p)), 'still nothing ran');
  // a built, highlighted destination is still not a choice: a lone word highlights Develop, and Run it stays hidden until the click
  await page.fill('#input-text', 'television'); await page.dispatchEvent('#input-text', 'input'); await page.waitForTimeout(900);
  const w = await page.evaluate(() => ({ dev: document.getElementById('develop-controls').hidden, chosen: !!document.querySelector('#destination-chips .dest.chosen'),
    chips: Array.from(document.querySelectorAll('#destination-chips .dest')).map(b => b.dataset.dest + (b.classList.contains('suggested') ? '*' : '')) }));
  ok(w.dev && !w.chosen && w.chips.join(',') === 'develop*,search,write,question,look_ethicalalt,search_open_case,investigation_room', 'a lone word highlights Develop without choosing it — Run it stays hidden: ' + w.chips.join(','));   // ledger (block 107): a word also offers the instrument doors
  ok(!posts.some(p => /\/api\/jobs/.test(p)), 'the highlighted built destination did not run');
  // clearing the box clears the row
  await page.fill('#input-text', ''); await page.dispatchEvent('#input-text', 'input'); await page.waitForTimeout(600);
  const cleared = await page.evaluate(() => ({ row: document.getElementById('destination-row').hidden, dev: document.getElementById('develop-controls').hidden }));
  ok(cleared.row && cleared.dev, 'an emptied box hides the row and the controls again');
  ok(errs.length === 0, 'no page errors across the journey: ' + JSON.stringify(errs));
  await ctx.close();
  await browser.close();
  finish('chooser');
})().catch(e => { console.log('FAIL journey crashed: ' + (e && e.stack || e)); process.exit(1); });
