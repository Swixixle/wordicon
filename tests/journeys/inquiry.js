// Block 111 phase 1: the Inquiry — a question, kept.
//
// What this journey has to prove is small and load-bearing. The question
// survives verbatim through every act the room offers. Identity is minted,
// so the same words twice are two inquiries. Navigation is history, so
// reopening puts him back where he stood. An abandoned branch keeps why it
// was abandoned AND what the failure revealed. Nothing here is a ruling.
// The room names what it cannot do yet on its own face. And reaching it
// through the chooser never disturbs the writing room.
//
// No model is mocked because none is reachable: this phase calls none.
const { BASE, ok, place, finish } = require('./lib');
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const Q = 'Are there pre-Christian figures with descriptions resembling Jesus, and does that even mean borrowing?';

(async () => {
  const opts = {};
  if (process.env.JOURNEY_CHROME) opts.executablePath = process.env.JOURNEY_CHROME;
  const browser = await chromium.launch(opts);
  const DIR = process.env.JOURNEY_DIR || '/tmp/anat';
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addCookies([{ name: fs.readFileSync(path.join(DIR, 'cookie'), 'utf8').trim(),
                          value: fs.readFileSync(path.join(DIR, 'token'), 'utf8').trim(),
                          domain: '127.0.0.1', path: '/' }]);
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(String(e)));
  const off = []; page.on('request', r => { if (!r.url().startsWith(BASE)) off.push(r.url()); });

  await page.goto(BASE + '/inquiry'); await page.waitForTimeout(900);

  // ---- open one, on a messy question -----------------------------------
  await page.fill('#q', Q);
  await page.click('#open-btn'); await page.waitForTimeout(700);
  const asked = await page.evaluate(() => document.getElementById('asked').textContent);
  ok(asked === Q, 'the question is kept exactly as it was asked: ' + JSON.stringify(asked.slice(0, 50)));

  const first = await page.evaluate(() => ONE.inquiry_id);
  // ---- the same words again are a different inquiry ---------------------
  await page.evaluate(() => closeOne()); await page.waitForTimeout(200);
  await page.fill('#q', Q);
  await page.click('#open-btn'); await page.waitForTimeout(700);
  const second = await page.evaluate(() => ONE.inquiry_id);
  ok(first !== second && /^inq_/.test(first) && /^inq_/.test(second),
    'the same words opened twice are two inquiries — identity is minted, not read off the question: '
    + JSON.stringify([first, second]));

  // ---- the doors this phase did not build say so ------------------------
  const unbuilt = await page.evaluate(() => {
    const bs = Array.from(document.querySelectorAll('#unbuilt button'));
    const cs = bs.map(b => getComputedStyle(b));
    return { n: bs.length, text: bs.map(b => b.textContent.replace(/\s+/g, ' ')).join(' | '),
             allDisabled: bs.every(b => b.disabled),
             border: cs.map(c => c.borderTopStyle), cursor: cs.map(c => c.cursor) };
  });
  // five now: phase 2 built readings and meta-questions, and the room stopped
  // claiming them as unbuilt in the same commit that built them
  ok(unbuilt.n === 5 && unbuilt.allDisabled
     && unbuilt.border.every(b => b === 'dashed') && unbuilt.cursor.every(c => c === 'not-allowed'),
    'every phase this room has not built renders as an unbuilt door — dashed, inert, naming its own '
    + 'reason: ' + JSON.stringify([unbuilt.n, unbuilt.border[0], unbuilt.cursor[0]]));
  ok(/research outside/.test(unbuilt.text) && /trial/.test(unbuilt.text) && /ask my record/.test(unbuilt.text),
    'and it names outside research, trial and record search among them');

  // ---- branch it, abandon one, and keep what the failure revealed -------
  const branched = await page.evaluate(async (iid) => {
    const post = (u, b) => fetch(u, {method: 'POST', headers: {'Content-Type': 'application/json'},
                                    body: JSON.stringify(b)}).then(r => r.json());
    const root = ONE.root_node_id;
    const a = await post('/api/inquiry/' + iid + '/node', {parent_id: root, node_type: 'reading', text: 'shared descriptive motifs'});
    const b = await post('/api/inquiry/' + iid + '/node', {parent_id: root, node_type: 'meta', text: 'am I assuming resemblance implies borrowing?'});
    await post('/api/inquiry/' + iid + '/disposition', {node_id: a.node.node_id, disposition: 'abandoned',
      reason: 'the comparison class was never defined', revealed: 'that "similar" was doing all the work'});
    await post('/api/inquiry/' + iid + '/active', {node_id: b.node.node_id});
    return {a: a.node.node_id, b: b.node.node_id};
  }, second);
  await page.evaluate(iid => openOne(iid), second); await page.waitForTimeout(500);
  const state = await page.evaluate(() => ({
    asked: document.getElementById('asked').textContent,
    active: ONE.active_node_id,
    nodes: ONE.nodes.map(n => [n.node_type, n.disposition.disposition, n.disposition.revealed || '']),
    rail: document.querySelectorAll('#rail .node').length,
  }));
  ok(state.asked === Q, 'branching, abandoning and navigating left the question untouched');
  ok(state.rail === 3, 'the rail shows the root and both branches: ' + state.rail);
  const gone = state.nodes.find(n => n[1] === 'abandoned');
  ok(gone && /doing all the work/.test(gone[2]),
    'an abandoned branch keeps what the failure revealed, not just that it failed: ' + JSON.stringify(gone));

  // ---- reopening puts him back where he stood ---------------------------
  await page.reload(); await page.waitForTimeout(900);
  await page.evaluate(iid => openOne(iid), second); await page.waitForTimeout(500);
  const back = await page.evaluate(() => ({ active: ONE.active_node_id,
    asked: document.getElementById('asked').textContent }));
  ok(back.active === branched.b && back.asked === Q,
    'after a full reload it reopens on the question as asked, standing where he left it');

  // ---- nothing here was a ruling ---------------------------------------
  const home = await page.evaluate(() => fetch('/api/home').then(r => r.json()));
  const due = (home.pending && home.pending.items || []).filter(i => i.source === 'recovery_review' || i.source === 'claim');
  ok(!(home.pending && home.pending.items || []).some(i => /inquiry/i.test(i.source || '')),
    'exploring created no ruling due — a branch is where thinking happened, not a judgment: '
    + JSON.stringify(due.map(d => d.source)));

  // ---- and the writing room is untouched by the walk --------------------
  await page.goto(BASE + '/'); await page.waitForTimeout(900);
  await page.evaluate(() => openWorkspace('write')); await page.waitForTimeout(300);
  await page.evaluate(() => { const ta = document.getElementById('compose-text');
    ta.value = 'a draft that must survive the walk'; ta.dispatchEvent(new Event('input')); ta.setSelectionRange(2, 8); });
  const el0 = await page.evaluate(() => { const ta = document.getElementById('compose-text');
    ta.dataset.probe = 'live-inq'; return {v: ta.value, s: ta.selectionStart, e: ta.selectionEnd}; });
  await place(page, '/inquiry'); await page.waitForTimeout(700);
  await page.evaluate(() => closePlace()); await page.waitForTimeout(400);
  const el1 = await page.evaluate(() => { const ta = document.getElementById('compose-text');
    return {probe: ta.dataset.probe || '', v: ta.value, s: ta.selectionStart, e: ta.selectionEnd,
            open: document.body.classList.contains('ws-open')}; });
  ok(el1.probe === 'live-inq' && el1.v === el0.v && el1.s === el0.s && el1.e === el0.e && el1.open,
    'walking to the Inquiry and back leaves the same room element, draft and caret: ' + JSON.stringify(el1));

  // ---- phase 2: the Question Reader ------------------------------------
  //
  // The model is routed, not run: the journeys keep the gateway poisoned, and
  // what is under test is the client's whole path — cost shown before spend,
  // proposals rendered as proposals, all-makes-siblings, an edit that
  // descends rather than overwrites, and a meta-question that is marked as
  // being about the question.
  // Nothing is mocked here. The journey server installs the Reader's
  // deterministic offline stand-in (server.READER_GATEWAY = cli.MockReader),
  // so every endpoint below is the real one: the real mechanical check, the
  // real recorded run, the real adoption into siblings. The stand-in returns
  // one span that IS in the question and one that is not, so the drop is
  // exercised rather than described.
  let readPosts = 0;
  page.on('request', r => { if (/\/read$/.test(r.url()) && r.method() === 'POST') readPosts += 1; });

  await page.goto(BASE + '/inquiry'); await page.waitForTimeout(800);
  await page.evaluate(iid => openOne(iid), second); await page.waitForTimeout(600);
  const cost = await page.evaluate(() => ({
    line: document.getElementById('read-cost').textContent,
    why: document.getElementById('read-why').textContent.replace(/\s+/g, ' '),
    spent: document.getElementById('readings-card').style.display }));
  ok(/one model call · lane /.test(cost.line) && readPosts === 0,
    'the page says what a reading costs before it spends it, and has spent nothing: '
    + JSON.stringify([cost.line, readPosts]));
  ok(/does not answer it, look anything up/.test(cost.why),
    'and says plainly that the Reader answers nothing');

  await page.click('#read-btn'); await page.waitForTimeout(700);
  const props = await page.evaluate(() => ({
    n: document.querySelectorAll('#readings .pick').length,
    note: document.getElementById('readings-note').textContent,
    text: document.getElementById('readings').textContent.replace(/\s+/g, ' '),
    drop: document.getElementById('assumptions').textContent.replace(/\s+/g, ' ') }));
  ok(props.n === 3 && /would need/.test(props.text),
    'three readings come back, each saying what evidence it would need: ' + props.n);
  ok(/Nothing here was looked up/.test(props.note),
    'and the card says on its face that nothing was looked up');
  ok(/Council of Nicaea/.test(props.drop) && /not in your/.test(props.drop),
    'a span the Reader invented is dropped and shown as dropped, in his own words: '
    + JSON.stringify(props.drop.slice(-120)));

  await page.evaluate(() => tickAll());
  await page.click('#adopt-btn'); await page.waitForTimeout(700);
  const sibs = await page.evaluate(() => {
    // the three the Reader proposed, not the one this journey wrote by hand
    // in the phase-1 section — which is the point of the standing axis
    const rs = ONE.nodes.filter(n => n.node_type === 'reading' && n.standing === 'model_proposal');
    const mine = ONE.nodes.filter(n => n.node_type === 'reading' && n.standing === 'owner_stated');
    return { n: rs.length, uniq: new Set(rs.map(r => r.node_id)).size,
             parents: new Set(rs.map(r => r.parent_id)).size,
             onRoot: rs.every(r => r.parent_id === ONE.root_node_id),
             routes: Array.from(new Set(rs.map(r => r.route))), mine: mine.length };
  });
  ok(sibs.n === 3 && sibs.uniq === 3 && sibs.parents === 1 && sibs.onRoot,
    'taking every reading makes separate sibling branches, never one blended prompt: '
    + JSON.stringify([sibs.n, sibs.uniq, sibs.parents]));
  ok(JSON.stringify(sibs.routes) === '["develop"]' && sibs.mine >= 1,
    'each proposed reading stands as a proposal, and his own reading beside it does not: '
    + JSON.stringify([sibs.routes, sibs.mine]));

  // his wording descends from the model's; the proposal is untouched
  const target = await page.evaluate(() => ONE.nodes.find(n => n.node_type === 'reading').node_id);
  await page.evaluate(nid => goNode(nid), target); await page.waitForTimeout(400);
  await page.fill('#edit-text', 'motifs, but only in the earliest texts');
  await page.click('text=Keep my wording'); await page.waitForTimeout(700);
  const edited = await page.evaluate(t => {
    const kid = ONE.nodes.find(n => n.parent_id === t && n.node_type === 'reading');
    const orig = ONE.nodes.find(n => n.node_id === t);
    return { kid: kid && {text: kid.text, standing: kid.standing, route: kid.route},
             orig: orig && orig.text,
             proposal: (ONE.reading_runs[0] || {}).readings.map(r => r.label) };
  }, target);
  ok(edited.kid && edited.kid.standing === 'owner_stated' && edited.kid.route === 'owner',
    'an edit descends from the proposal as his own words, not the model\'s: ' + JSON.stringify(edited.kid));
  ok(edited.orig === 'shared descriptive motifs' && edited.proposal[0] === 'shared descriptive motifs',
    'and neither the adopted reading nor the proposal behind it was rewritten: '
    + JSON.stringify([edited.orig, edited.proposal[0]]));

  await page.fill('#meta-text', 'am I assuming resemblance implies borrowing?');
  await page.click('text=Ask about the question'); await page.waitForTimeout(700);
  const meta = await page.evaluate(() => {
    const m = ONE.nodes.find(n => n.node_type === 'meta');
    return { has: !!m, world: m && m.world_directed,
             said: document.getElementById('here').textContent.replace(/\s+/g, ' ') };
  });
  ok(meta.has && meta.world === false,
    'a meta-question is marked as being about the question, not about the world: ' + JSON.stringify(meta.world));

  ok(readPosts === 1, 'the whole of that spent exactly one model call: ' + readPosts);

  ok(errs.length === 0, 'no page errors: ' + JSON.stringify(errs.slice(0, 3)));
  ok(off.length === 0, 'inquiry: no request left the scratch origin');
  await browser.close();
  finish('inquiry');
})().catch(e => { console.log('FAIL journey crashed: ' + (e && e.stack || e)); process.exit(1); });
