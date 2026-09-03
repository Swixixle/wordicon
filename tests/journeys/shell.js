// The shell journey (slice 2): a place opens without unloading the document,
// so the writing room's ELEMENT survives — and with it the caret, the undo
// stack, the scroll and the workspace layout that an element carries and a
// localStorage draft cannot.
//
// The load-bearing checks are the three a source pin cannot make: the main
// frame never navigates, a property stamped on the live textarea is still
// there afterwards, and a keyboard undo still walks back through edits made
// before the trip. If any of those fails, the shell rebuilt something.
const { BASE, ok, launch, pairedContext, finish } = require('./lib');

(async () => {
  const browser = await launch();
  const ctx = await pairedContext(browser); const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(String(e)));
  page.on('dialog', d => d.dismiss());
  await page.goto(BASE + '/'); await page.waitForTimeout(1200);
  ok(errs.length === 0, 'no page errors on Home: ' + JSON.stringify(errs));
  // The proof that the document was never replaced. A pushState is a
  // "navigation" to the browser and to Playwright's framenavigated, so the
  // honest test is whether THIS window survived: a stamped global and a
  // property on the live textarea are both gone the moment a document is.
  const LOAD_ID = await page.evaluate(() => (window.__shellLoadId = 'load-' + Math.random()));
  const stillHere = async () => await page.evaluate(() => window.__shellLoadId || '');

  // ---- a real draft, in the room, beside the page ----------------------
  await page.evaluate(() => openWorkspace('split')); await page.waitForTimeout(500);
  await page.click('#compose-text');
  await page.keyboard.type('The first sentence stands.');
  await page.waitForTimeout(120);
  await page.keyboard.type(' And a second one after it.');
  await page.waitForTimeout(120);
  const before = await page.evaluate(() => {
    const ta = document.getElementById('compose-text');
    ta.dataset.shellProbe = 'live-element-1';       // survives only if nothing is rebuilt
    ta.setSelectionRange(4, 9);                     // a caret AND a selection
    ta.scrollTop = 0;
    window.scrollTo(0, 0);
    const pg = document.getElementById('page'); if (pg) pg.scrollTop = 140;
    return { value: ta.value, start: ta.selectionStart, end: ta.selectionEnd,
             cls: document.body.className, pageScroll: pg ? pg.scrollTop : -1 };
  });
  ok(before.value === 'The first sentence stands. And a second one after it.',
    'the draft is in the room: ' + JSON.stringify(before.value));
  ok(/ws-open/.test(before.cls) && /ws-split/.test(before.cls), 'the workspace is open and split: ' + before.cls);

  // ---- walk to a place -------------------------------------------------
  // clicked in the page rather than by Playwright, which scrolls a target
  // into view first and would move the very scroll position under test
  await page.evaluate(() => document.querySelector('header nav.places a[href="/map"]').click());
  await page.waitForTimeout(1500);
  const at = await page.evaluate(() => {
    const ta = document.getElementById('compose-text');
    const f = document.getElementById('place-frame');
    const pg = document.getElementById('page');
    return { url: location.pathname, paneHidden: document.getElementById('place').hidden,
             homeHidden: document.getElementById('home-main').hidden,
             name: document.getElementById('place-name').textContent,
             frameSrc: (f.contentWindow.location.pathname || ''), frameH: parseInt(f.style.height || '0', 10),
             probe: ta.dataset.shellProbe || '', value: ta.value,
             start: ta.selectionStart, end: ta.selectionEnd,
             cls: document.body.className, pageScroll: pg ? pg.scrollTop : -1,
             here: Array.from(document.querySelectorAll('header nav.places a.here')).map(a => a.getAttribute('href')).join(',') };
  });
  ok(at.url === '/map', 'the address says /map: ' + at.url);
  ok(await stillHere() === LOAD_ID, 'the document was never replaced — this is the same window');
  ok(!at.paneHidden && at.homeHidden, 'the place pane replaced Home inside the shell');
  ok(at.name === 'Map' && at.frameSrc === '/map', 'the pane names the place and holds its document: ' + at.name + ' ' + at.frameSrc);
  ok(at.frameH > 320, 'the place was given the height that is left: ' + at.frameH);
  ok(at.here === '/map', 'the header marks where you are: ' + JSON.stringify(at.here));
  ok(at.probe === 'live-element-1', 'the writing room is the SAME element — nothing was rebuilt');
  ok(at.value === before.value, 'the draft is untouched');
  ok(at.start === 4 && at.end === 9, 'the caret AND the selection survived the walk: ' + at.start + '-' + at.end);
  ok(/ws-open/.test(at.cls) && /ws-split/.test(at.cls), 'the layout survived the walk: ' + at.cls);
  const mapReal = await page.evaluate(() => {
    const d = document.getElementById('place-frame').contentDocument;
    return d ? { title: d.title, stage: !!d.getElementById('stage'), path: d.location.pathname,
                 toWorld: !!d.querySelector('a[href="/map/world"]') } : null;
  });
  ok(mapReal && mapReal.path === '/map' && mapReal.stage && /Nikodemus/.test(mapReal.title),
    'the Map itself is in the pane — its own document, its own stage: ' + JSON.stringify(mapReal));

  // a place that walks to another place moves the shell with it, without a reload
  ok(mapReal.toWorld, 'the Map carries its door to the spatial map');
  await page.evaluate(() => document.getElementById('place-frame').contentDocument.querySelector('a[href="/map/world"]').click());
  await page.waitForTimeout(1600);
  const world = await page.evaluate(() => ({ url: location.pathname, name: document.getElementById('place-name').textContent,
    wayfinder: !!document.getElementById('place-frame').contentDocument.getElementById('wayfinder'),
    probe: document.getElementById('compose-text').dataset.shellProbe || '' }));
  ok(world.url === '/map/world' && world.wayfinder && /world/.test(world.name),
    'a place walking to another place carries the shell with it: ' + JSON.stringify(world));
  ok(world.probe === 'live-element-1' && await stillHere() === LOAD_ID, 'and still the same window and the same room');
  await page.goBack(); await page.waitForTimeout(1200);

  // the place's own way back is hidden inside the shell — it would say you
  // left something you never left — and the bar is the one way home
  const dupes = await page.evaluate(() => {
    const d = document.getElementById('place-frame').contentDocument;
    const links = Array.from(d.querySelectorAll('a[href="/"]'));
    return { n: links.length, shown: links.filter(a => a.style.display !== 'none').length,
             bar: !!document.querySelector('#place-bar button') };
  });
  ok(dupes.n > 0 && dupes.shown === 0 && dupes.bar,
    'the place\'s own back link is hidden inside the shell and the bar is the way home: ' + JSON.stringify(dupes));

  // ---- and back, by the browser's own Back ------------------------------
  await page.goBack(); await page.waitForTimeout(900);
  const home = await page.evaluate(() => {
    const ta = document.getElementById('compose-text');
    const pg = document.getElementById('page');
    return { url: location.pathname, paneHidden: document.getElementById('place').hidden,
             homeHidden: document.getElementById('home-main').hidden,
             frameSrc: document.getElementById('place-frame').contentWindow.location.href,
             probe: ta.dataset.shellProbe || '', value: ta.value,
             start: ta.selectionStart, end: ta.selectionEnd, cls: document.body.className,
             pageScroll: pg ? pg.scrollTop : -1 };
  });
  ok(home.url === '/' && home.paneHidden && !home.homeHidden, 'Back returns to Home inside the same document');
  ok(await stillHere() === LOAD_ID, 'Back did not replace the document either');
  ok(/^about:blank$/.test(home.frameSrc), 'a closed place stops running rather than idling behind the page: ' + home.frameSrc);
  ok(home.probe === 'live-element-1' && home.value === before.value, 'the room came back as the same element with the same draft');
  ok(home.start === 4 && home.end === 9, 'the caret and selection are still where they were: ' + home.start + '-' + home.end);
  ok(home.pageScroll === before.pageScroll, 'Home came back to where it was scrolled: ' + home.pageScroll + ' (was ' + before.pageScroll + ')');

  // ---- the proof no stored draft can give: the undo stack ---------------
  await page.click('#compose-text');
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+z' : 'Control+z');
  await page.waitForTimeout(200);
  const undone = await page.evaluate(() => document.getElementById('compose-text').value);
  ok(undone !== before.value && undone.length < before.value.length && /The first sentence stands\./.test(undone),
    'undo walked back through an edit made BEFORE the walk — the stack survived: ' + JSON.stringify(undone));

  // ---- a place may walk to another place, and home again ----------------
  await page.evaluate(() => openPlace('/clinic')); await page.waitForTimeout(1200);
  const clinic = await page.evaluate(() => ({ url: location.pathname, name: document.getElementById('place-name').textContent,
    src: document.getElementById('place-frame').contentWindow.location.pathname }));
  ok(clinic.url === '/clinic' && clinic.name === 'Clinic' && clinic.src === '/clinic', 'the Clinic opens as a place: ' + JSON.stringify(clinic));
  await page.evaluate(() => { document.getElementById('place-frame').contentDocument.querySelector('a[href="/"]').click(); });
  await page.waitForTimeout(1200);
  const backHome = await page.evaluate(() => ({ url: location.pathname, paneHidden: document.getElementById('place').hidden,
    probe: document.getElementById('compose-text').dataset.shellProbe || '' }));
  ok(backHome.url === '/' && backHome.paneHidden, 'a place\'s own "back" closes the pane instead of loading Home inside it');
  ok(backHome.probe === 'live-element-1', 'and the room is still the same element after that too');
  ok(await stillHere() === LOAD_ID, 'none of it replaced the document');

  // ---- the ruled standalone documents are NOT places --------------------
  const standalone = await page.evaluate(() => ({ anat: !!PLACES['/anatomy'], pair: !!PLACES['/pair'], list: STANDALONE.join(',') }));
  ok(!standalone.anat && !standalone.pair && standalone.list === '/anatomy,/pair',
    'the anatomy and pairing are ruled standalone, never panes: ' + JSON.stringify(standalone));
  await page.click('header .quiet a[href="/anatomy"]'); await page.waitForTimeout(1200);
  ok(page.url().replace(BASE, '') === '/anatomy', 'the anatomy takes the whole window, as ruled: ' + page.url().replace(BASE, ''));

  // ---- old URLs are still entry points ---------------------------------
  for (const [path, needle] of [['/map', 'overworld'], ['/clinic', 'clinic'], ['/bench', 'bench'],
                                ['/trails', 'trails'], ['/recovery', 'recovery'], ['/investigation', 'investigation']]) {
    const r = await page.request.get(BASE + path);
    ok(r.status() === 200, 'the old URL ' + path + ' still answers on its own: ' + r.status());
  }
  ok(errs.length === 0, 'no page errors across the shell journey: ' + JSON.stringify(errs));
  await ctx.close();
  await browser.close();
  finish('shell');
})().catch(e => { console.log('FAIL journey crashed: ' + (e && e.stack || e)); process.exit(1); });
