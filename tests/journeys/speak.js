// The Speak journey, quiet half (block 106): with a fake microphone, the
// instrument is pressed, listens, is stopped, transcribes with the mock
// engine, shows what it heard in the box with provenance spoken, offers
// the same destinations as the typed sentence, is discarded, and a reload
// mid-listen leaves it Ready with nothing recording. run.sh hashes the
// scratch store before and after this journey: none of it writes.
const { BASE, ok, launch, pairedContext, finish } = require('./lib');
const healthyVault = { initialized: true, last_seal_at: new Date(Date.now() - 4 * 60000).toISOString(), last_drill_at: new Date(Date.now() - 86400000).toISOString(), cloud: 'iCloud', n_vaults: 31, total_bytes: 125638 * 1024, failure: '', stale_red: false, dirty_seconds: 0 };
const CATS = 'I would like to know about the historical superstitions involving cats.';

(async () => {
  const browser = await launch();
  const ctx = await pairedContext(browser); const page = await ctx.newPage();
  await page.route('**/api/vault/status', r => r.fulfill({ json: healthyVault }));
  const posts = []; page.on('request', r => { if (r.method() !== 'GET') posts.push(r.method() + ' ' + r.url().replace(BASE, '')); });
  const errs = []; page.on('pageerror', e => errs.push(String(e)));
  page.on('dialog', d => d.dismiss());
  const state = () => page.evaluate(() => ({ st: document.getElementById('speak-state').dataset.state, text: document.getElementById('speak-state').textContent, btn: document.getElementById('speak-btn').textContent.trim(), disabled: document.getElementById('speak-btn').disabled,
    recording: !!(typeof SPEAK !== 'undefined' && SPEAK.rec && SPEAK.rec.state === 'recording'), tracks: (typeof SPEAK !== 'undefined' && SPEAK.stream) ? SPEAK.stream.getTracks().filter(t => t.readyState === 'live').length : 0,
    box: document.getElementById('input-text').value, review: document.getElementById('speak-review').hidden, heard: document.getElementById('speak-heard').textContent, engine: document.getElementById('speak-engine').textContent,
    audio: document.getElementById('speak-audio').getAttribute('src') || '' }));
  await page.goto(BASE + '/'); await page.waitForTimeout(1500);
  const s0 = await state();
  ok(s0.st === 'ready' && s0.text === 'Ready' && !s0.disabled && !s0.recording && s0.tracks === 0, 'on load the instrument is Ready, enabled on a secure page, and nothing is recording');
  ok(posts.length === 0, 'loading posted nothing');
  // press: listening begins only now
  await page.click('#speak-btn'); await page.waitForTimeout(800);
  const s1 = await state();
  ok(s1.st === 'listening' && s1.btn === '⏹ Stop' && s1.recording && s1.tracks >= 1, 'the press opens the microphone and Listening is visible with a Stop control: ' + JSON.stringify([s1.st, s1.btn, s1.recording]));
  ok(posts.length === 0, 'listening posts nothing');
  await page.waitForTimeout(1200);
  // stop: transcribing, then review; the transcript in the box, editable, spoken
  await page.click('#speak-btn'); await page.waitForTimeout(1500);
  const s2 = await state();
  ok(s2.st === 'review' && !s2.recording && s2.tracks === 0 && !s2.review, 'stopping closes the microphone and reaches Review what Nikodemus heard: ' + JSON.stringify([s2.st, s2.recording, s2.tracks]));
  ok(s2.box === CATS && s2.heard.includes(CATS), 'what the engine heard is in the box, editable, and shown for review');
  ok(/heard by mock mock-1/.test(s2.engine) && /audio never left this machine/.test(s2.engine) && /vocabulary hint/.test(s2.engine), 'the engine names itself and its settings: ' + s2.engine.slice(0, 100));
  ok(s2.audio.startsWith('blob:'), 'replay comes from the page\'s own memory (a blob URL), not a stored file');
  ok(posts.filter(p => p !== 'POST /api/speak/transcribe' && p !== 'POST /api/destinations').length === 0 && posts.filter(p => p === 'POST /api/speak/transcribe').length === 1, 'one transcription was posted and nothing else: ' + JSON.stringify(posts));
  await page.waitForTimeout(600);
  const dest = await page.evaluate(() => ({ reading: document.getElementById('destination-reading').textContent.replace(/\s+/g, ' '), chips: Array.from(document.querySelectorAll('#destination-chips .dest')).map(b => b.dataset.dest + (b.classList.contains('suggested') ? '*' : '') + (b.disabled ? '!' : '')).join(','), dev: document.getElementById('develop-controls').hidden }));
  ok(/arrived spoken/.test(dest.reading) && dest.chips === 'research*!,search,develop,room,write,question' && dest.dev, 'the spoken sentence receives the typed sentence\'s destinations, arrived spoken, nothing run: ' + dest.chips);
  // editing keeps it spoken
  await page.fill('#input-text', CATS + ' Correct the transcript.'); await page.dispatchEvent('#input-text', 'input'); await page.waitForTimeout(700);
  const edited = await page.evaluate(() => ({ reading: document.getElementById('destination-reading').textContent.replace(/\s+/g, ' '), block: (typeof speechBlock === 'function') ? speechBlock() : null }));
  ok(/arrived spoken/.test(edited.reading) && edited.block && edited.block.edited === true && edited.block.machine_text === CATS && edited.block.external === false, 'an edited transcript stays spoken and records that it was edited beside what the machine heard');
  // discard leaves nothing
  await page.click('#speak-discard'); await page.waitForTimeout(400);
  const s3 = await state();
  ok(s3.st === 'discarded' && s3.box === '' && s3.review && s3.audio === '' && !s3.recording, 'Discard clears the box, the review and the audio: ' + JSON.stringify([s3.st, s3.box, s3.review]));
  await page.waitForTimeout(2800);
  ok((await state()).st === 'ready', 'and the instrument returns to Ready');
  // a reload mid-listen: nothing restarts
  await page.click('#speak-btn'); await page.waitForTimeout(800);
  ok((await state()).st === 'listening', 'listening again, deliberately');
  await page.reload(); await page.waitForTimeout(1500);
  const s4 = await state();
  ok(s4.st === 'ready' && !s4.recording && s4.tracks === 0 && s4.review, 'after a reload the instrument is Ready and nothing is recording: ' + JSON.stringify([s4.st, s4.recording, s4.tracks]));
  ok(posts.filter(p => p !== 'POST /api/speak/transcribe' && p !== 'POST /api/destinations').length === 0, 'the whole quiet half posted only readings and the one transcription: ' + JSON.stringify(posts));
  ok(errs.length === 0, 'no page errors: ' + JSON.stringify(errs));
  await ctx.close();
  await browser.close();
  finish('speak');
})().catch(e => { console.log('FAIL journey crashed: ' + (e && e.stack || e)); process.exit(1); });
