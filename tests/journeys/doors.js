// The three doors ruling (2026-10-16, the owner: "I see no simple button to
// analyze. no simple way to upload files, photos, documents... we probably
// need to collapse a lot of the options"). What is under test, in WebKit, in
// the running shell: the bar on the draft offers the three acts and each is
// the registry action it names (a press proposes; nothing runs without
// Start); the rail is the short pinned set and a folded tool still answers
// to its name in Ask; the workspace's own intake queues on arrival, stores
// only on Admit, and the admission posts exactly one /api/upload; the
// about-pages kept doors in the footer; Focus clears the bar with the rest
// of the chrome. The server runs the MOCK lane: a Start completes as a
// canned fixture and no socket leaves the process.
const { BASE, DIR, ok, finish, pairedContext } = require('./lib');
const { webkit } = require('playwright');

(async () => {
  const browser = await webkit.launch();
  ok(browser.browserType().name() === 'webkit', 'the doors are measured in WebKit, the engine the owner writes in: ' + browser.browserType().name());
  const ctx = await pairedContext(browser, { viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const errs = [], posts = [];
  page.on('pageerror', e => errs.push(String(e.message)));
  page.on('request', r => { if (r.method() !== 'GET') posts.push(r.method() + ' ' + new URL(r.url()).pathname); });

  await page.goto(BASE + '/work');
  await page.waitForSelector('.pm-editor');
  await page.waitForTimeout(600);
  ok(errs.length === 0, 'no page errors on /work: ' + JSON.stringify(errs));
  await page.evaluate(() => window.__work.session.newDocument(''));
  await page.waitForTimeout(200);

  // 1. the bar: the three acts on the draft itself, in ruled order
  const bar = await page.$$eval('#draft-actions .big .big-label', els => els.map(e => e.textContent));
  ok(JSON.stringify(bar) === JSON.stringify(['Get feedback', 'Analyze', 'Add a file']),
     'the bar offers the three acts: ' + JSON.stringify(bar));

  // 2. the rail is the short set; nothing folded is drawn, no group renders empty
  const railIds = await page.$$eval('#tool-groups button.item', els => els.map(e => e.dataset.action));
  ok(railIds.length === 13, 'the rail lists 13 doors (was 36): ' + railIds.length + ' ' + JSON.stringify(railIds));
  ok(!railIds.some(id => id.startsWith('investigate.')), 'the rail shows no second copy of Investigate (it lives on the Investigate page)');
  ok(!railIds.includes('explore.crack') && !railIds.includes('explore.deep') && !railIds.includes('more.legacy'),
     'the folded verbs and about-pages are not drawn in the rail');
  const groups = await page.$$eval('#tool-groups details.group > summary', els => els.map(e => e.textContent.replace(/[▸▾]/g, '').trim()));
  ok(groups.length === 3 && /Places/.test(groups[2]), 'three groups, the third named Places: ' + JSON.stringify(groups));

  // 3. a folded tool still answers to its name in Ask, and proposes without running
  const before3 = posts.filter(p => p === 'POST /api/operations').length;
  await page.click('.pm-editor');
  await page.keyboard.type('He threw it once, cleanly, and the room laughed. Nobody said so.');
  await page.waitForTimeout(400);
  await page.keyboard.press('ControlOrMeta+k');
  await page.waitForSelector('#ask:not([hidden])');
  await page.fill('#ask-input', 'take this apart');
  await page.waitForFunction(() => document.querySelectorAll('#ask-matches button').length > 0, null, { timeout: 5000, polling: 100 });
  await page.keyboard.press('Enter');
  await page.waitForSelector('#proposal-card');
  ok(/Take this apart/.test(await page.textContent('#proposal-card')), 'Ask still reaches the folded "Take this apart" by name');
  ok(posts.filter(p => p === 'POST /api/operations').length === before3, 'and started nothing');
  await page.keyboard.press('Escape');

  // 4. Analyze from the bar: a proposal that names the routed run; Start completes it (mock lane)
  await page.evaluate(() => { window.__work.editor.focus(); window.__work.editor.setSelection(0, 0); });
  await page.click('button[data-bar="explore.auto"]');
  await page.waitForSelector('#proposal-card');
  const prop = await page.textContent('#proposal-card');
  ok(/the whole draft/.test(prop), 'Analyze with nothing selected takes the whole draft: ' + prop.slice(0, 120));
  const knownOps = await page.evaluate(() => Array.from(window.__work.results.tracked.keys()));
  await page.click('#proposal-card .btn.primary');
  await page.waitForFunction(known => Array.from(window.__work.results.tracked.keys()).some(k => !known.includes(k)), knownOps, { timeout: 10000, polling: 100 });
  const opId = await page.evaluate(known => Array.from(window.__work.results.tracked.keys()).find(k => !known.includes(k)), knownOps);
  await page.waitForFunction(id => { const t = window.__work.results.tracked.get(id); return t && ['complete', 'done', 'failed'].includes(t.status); }, opId, { timeout: 60000, polling: 200 });
  const op = await (await page.request.get(BASE + '/api/operations/' + opId)).json();
  ok(op.status === 'complete', 'the bar’s Analyze completed through the one job path: ' + op.status);
  ok(typeof op.snapshot_id === 'string' && op.snapshot_id.startsWith('snap_'), 'the routed run links to its immutable snapshot');

  // 5. Get feedback from the bar proposes the three readers; Close starts nothing
  const before5 = posts.filter(p => p === 'POST /api/operations').length;
  await page.click('button[data-bar="feedback.readers"]');
  await page.waitForSelector('#proposal-card');
  ok(/Get feedback|readers/i.test(await page.textContent('#proposal-card')), 'the bar’s Get feedback proposes the readers');
  await page.keyboard.press('Escape');
  ok(posts.filter(p => p === 'POST /api/operations').length === before5, 'closing the proposal started nothing');

  // 6. Add a file: queued on arrival, stored only on Admit, one POST /api/upload
  await page.click('button[data-bar="attach.source"]');
  await page.waitForSelector('#work-intake');
  const beforeUp = posts.filter(p => p === 'POST /api/upload').length;
  await page.setInputFiles('#work-intake input[type="file"]', {
    name: 'passage.txt', mimeType: 'text/plain',
    buffer: Buffer.from('A passage he kept, brought in through the workspace door.'),
  });
  await page.waitForSelector('#work-intake .intake-row');
  ok(/queued — nothing stored yet/.test(await page.textContent('#work-intake')), 'an arrived file is queued, not stored');
  ok(posts.filter(p => p === 'POST /api/upload').length === beforeUp, 'arrival posted nothing');
  await page.click('#work-intake .btn.primary');
  await page.waitForFunction(() => /stored in the Library as the source/.test(document.getElementById('work-intake').textContent), null, { timeout: 8000, polling: 100 });
  ok(posts.filter(p => p === 'POST /api/upload').length === beforeUp + 1, 'Admit posted exactly one /api/upload');
  ok(/text derived from the file itself/.test(await page.textContent('#work-intake')), 'and the text derived locally, no model call');
  await page.keyboard.press('Escape');
  await page.waitForTimeout(200);
  ok(await page.isHidden('#work-intake-overlay'), 'Escape closes the intake dialog');

  // 7. the about-pages kept doors — in the footer now
  for (const id of ['foot-constitution', 'foot-anatomy', 'foot-legacy']) {
    ok(await page.isVisible('#' + id), 'the footer door ' + id + ' is there');
  }

  // 8. Focus clears the bar with the chrome; Exit focus restores it
  await page.click('#focus-btn');
  ok(await page.isHidden('#draft-actions'), 'Focus clears the bar');
  await page.click('#exit-focus');
  ok(await page.isVisible('#draft-actions'), 'Exit focus restores the bar');

  ok(errs.length === 0, 'no page errors through the doors: ' + JSON.stringify(errs));
  await browser.close();
  finish('doors');
})();
