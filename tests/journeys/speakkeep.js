// The Speak journey, writing half (block 106): Keep recording stores the
// recording byte-intact in Media with the machine transcript as a version
// naming the engine; an edited transcript sent as an open question carries
// provenance spoken and the transcription's identity, with the machine's
// text beside the owner's edit; the instrument reads Sent.
const { BASE, ok, launch, pairedContext, finish } = require('./lib');
const healthyVault = { initialized: true, last_seal_at: new Date(Date.now() - 4 * 60000).toISOString(), last_drill_at: new Date(Date.now() - 86400000).toISOString(), cloud: 'iCloud', n_vaults: 31, total_bytes: 125638 * 1024, failure: '', stale_red: false, dirty_seconds: 0 };
const CATS = 'I would like to know about the historical superstitions involving cats.';

(async () => {
  const browser = await launch();
  const ctx = await pairedContext(browser); const page = await ctx.newPage();
  await page.route('**/api/vault/status', r => r.fulfill({ json: healthyVault }));
  const posts = []; page.on('request', r => { if (r.method() !== 'GET') posts.push(r.method() + ' ' + r.url().replace(BASE, '')); });
  const errs = []; page.on('pageerror', e => errs.push(String(e)));
  page.on('dialog', d => d.accept());
  const api = async (p) => (await page.request.get(BASE + p)).json();
  await page.goto(BASE + '/'); await page.waitForTimeout(1500);
  const mediaBefore = (await api('/api/media')).media.length;
  await page.click('#speak-btn'); await page.waitForTimeout(1500);
  await page.click('#speak-btn'); await page.waitForTimeout(1500);
  const st = await page.evaluate(() => document.getElementById('speak-state').dataset.state);
  ok(st === 'review', 'recorded and transcribed: ' + st);
  // keep the recording
  await page.click('#speak-keep'); await page.waitForTimeout(1500);
  const note = await page.evaluate(() => document.getElementById('speak-note').textContent);
  ok(/kept as media_/.test(note) && /machine transcript as a version/.test(note), 'Keep recording stores it and says so: ' + note.slice(0, 120));
  const media = (await api('/api/media')).media;
  const mine = media.find(m => (m.acquisitions || []).some(a => a.source === 'Speak to Nikodemus'));
  ok(media.length === mediaBefore + 1 && mine && mine.kind === 'audio', 'one audio item joined Media, sourced Speak to Nikodemus');
  const tv = (mine && mine.transcripts) || [];
  ok(tv.length === 1 && tv[0].origin === 'locally generated' && tv[0].engine && tv[0].engine.name === 'mock' && tv[0].engine.external === false && tv[0].n_segments >= 1, 'the machine transcript is a time-anchored version naming the engine: ' + JSON.stringify(tv[0] && tv[0].engine));
  ok(posts.filter(p => p === 'POST /api/speak/keep').length === 1 && posts.filter(p => p === 'POST /api/speak/keep/transcript').length === 1, 'keeping was two posts: the bytes, then the transcript');
  // edit, then send as an open question
  await page.fill('#input-text', CATS + ' And correct the transcript.'); await page.dispatchEvent('#input-text', 'input'); await page.waitForTimeout(700);
  await page.click('#destination-chips .dest[data-dest="question"]'); await page.waitForTimeout(1200);
  const q = (await api('/api/questions')).open.find(x => x.text === CATS + ' And correct the transcript.');
  ok(q && q.provenance === 'spoken' && q.speech && q.speech.edited === true && q.speech.machine_text === CATS && q.speech.name === 'mock' && q.speech.external === false, 'the open question arrived spoken, edited, with the machine\'s text and the engine beside it: ' + JSON.stringify(q && q.speech));
  const sent = await page.evaluate(() => document.getElementById('speak-state').dataset.state);
  ok(sent === 'sent', 'the instrument reads Sent: ' + sent);
  ok(!posts.some(p => /\/api\/jobs/.test(p)), 'nothing ran');
  ok(errs.length === 0, 'no page errors: ' + JSON.stringify(errs));
  await ctx.close();
  await browser.close();
  finish('speakkeep');
})().catch(e => { console.log('FAIL journey crashed: ' + (e && e.stack || e)); process.exit(1); });
