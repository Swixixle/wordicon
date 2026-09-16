// Screenshots of the Slice I surfaces the standing shot list predates: the
// "unsaved copies from other tabs" bar (a second tab's distinct unsent words
// listed beside this tab's draft), and the Investigate authorization control.
// Runs against the scratch dev server like tests/slice_g/shots.js:
//   JOURNEY_DIR=<dir> JOURNEY_PORT=8499 ENGINE=chromium|webkit OUT=<dir> node tests/slice_g/shots_drafts.js
process.chdir(require('path').join(__dirname, '..', 'journeys'));
const { BASE, pairedContext } = require('../journeys/lib');
const playwright = require('playwright');
const path = require('path');
const ENGINE = process.env.ENGINE === 'webkit' ? 'webkit' : 'chromium';
const OUT = process.env.OUT;
(async () => {
  const browser = await playwright[ENGINE].launch();
  const ctx = await pairedContext(browser, { viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const docUrl = id => BASE + '/api/notebook/documents/' + id;
  const boot = async p => { await p.goto(BASE + '/work'); await p.waitForSelector('.pm-editor'); await p.waitForFunction(() => !!(window.__work && window.__work.session && window.__work.session.id), null, { timeout: 10000, polling: 100 }); };
  const blockSaves = (p, id) => p.route(docUrl(id), route => route.request().method() === 'PUT' ? route.abort('failed') : route.continue());
  const stopRetryOn = p => p.evaluate(() => { const s = window.__work.session; if (s.retryTimer) clearTimeout(s.retryTimer); s.retryTimer = null; if (s.timer) clearTimeout(s.timer); s.timer = null; });
  await boot(page);
  await page.evaluate(() => window.__work.session.newDocument(''));
  await page.waitForTimeout(200); await page.click('.pm-editor');
  await page.keyboard.type('Disposable words, saved in tab A.');
  await page.waitForFunction(() => /Saved \d/.test(document.getElementById('doc-meta').textContent), null, { timeout: 8000, polling: 200 });
  const id = await page.evaluate(() => window.__work.session.id);
  await blockSaves(page, id);
  await page.keyboard.type(' Then more words typed in tab A that did not reach the server.');
  await page.waitForFunction(() => window.__work.session.status === 'local', null, { timeout: 8000, polling: 50 });
  await stopRetryOn(page);
  const tabB = await ctx.newPage();
  await boot(tabB);
  await tabB.evaluate(id => window.__work.session.open(id), id);
  await tabB.waitForTimeout(800);
  await tabB.screenshot({ path: path.join(OUT, '40-drafts-bar-other-tab-live.png') });
  await blockSaves(tabB, id);
  await tabB.click('.pm-editor'); await tabB.keyboard.press('End'); await tabB.keyboard.type(' And different words typed in tab B, also unsent.');
  await tabB.waitForFunction(() => window.__work.session.status === 'local', null, { timeout: 8000, polling: 50 });
  await stopRetryOn(tabB);
  await tabB.waitForTimeout(300);
  await page.unroute(docUrl(id));
  await page.reload(); await page.waitForSelector('.pm-editor'); await page.waitForTimeout(1200);
  await page.screenshot({ path: path.join(OUT, '41-drafts-bar-after-reload-own-words-kept.png') });
  await tabB.close();
  await page.waitForTimeout(900);
  await page.evaluate(() => window.__work.session.open(window.__work.session.id));
  await page.waitForTimeout(900);
  await page.screenshot({ path: path.join(OUT, '42-drafts-bar-other-tab-gone.png') });
  // the Investigate authorization control
  await page.click('text=Investigate');
  await page.waitForSelector('text=Live use');
  const btn = page.locator('button:has-text("Authorize live use")').first();
  if (await btn.count()) await btn.scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(OUT, '43-investigate-live-use.png') });
  const txt = await page.textContent('body');
  console.log(JSON.stringify({ engine: ENGINE, drafts_bar_seen: /unsaved cop/.test(await page.textContent('#drafts-bar').catch(() => '')), authorize_control: /Authorize live use/.test(txt), verifies_nothing: /verifies nothing by itself/.test(txt) }));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
