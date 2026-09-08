// The Carry Back journey (block 123) — the bridge from a workup to the room.
//
// What only a browser can testify to: that carrying disturbs nothing in the
// live textarea; that the standing labels are TEXT and survive a copy; that
// a draft which differs from the analysed one cannot pass silently; that a
// contradicted item cannot render as supported; and that nothing here ever
// inserts prose into the draft or produces a ruling.
//
// The synthetic fixture carries the same structural trap as the run that
// prompted this block: a broad MIDDAY interval, a list mixing childhood and
// adult examples, a candidate that narrows it to school-to-dinner, an
// anchor-fit reviewer naming the added boundary, an unverified cultural
// comparison, one invented example, one contradicted proposal. The owner's
// passage is not here.
const fs = require('fs');
const path = require('path');
const { BASE, DIR, ok, launch, pairedContext, finish } = require('./lib');
const IDS = JSON.parse(fs.readFileSync(path.join(DIR, 'partial.json'), 'utf8'));
const TRACE = IDS.deepPartial;

(async () => {
  const browser = await launch();
  const ctx = await pairedContext(browser);
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(String(e)));
  await page.goto(BASE + '/');
  await page.waitForTimeout(700);

  // ---- 0. an empty tray creates no furniture ----------------------------
  const before = await page.evaluate(() => ({
    ctl: !!document.getElementById('carry-ctl'),
    n: (await_ => 0)(),
  }));
  ok(!before.ctl, 'no revision-notes control exists while nothing has been carried :: ' + JSON.stringify(before));

  // ---- 1. the real cards carry the action ---------------------------------
  await page.evaluate(async (tid) => {
    const r = await fetch('/api/result/' + tid); window.__d = await r.json();
    const area = document.getElementById('result-area');
    area.innerHTML = buildDeepHtml(window.__d);
  }, TRACE);
  const btns = await page.evaluate(() => document.querySelectorAll('button.carry-btn').length);
  ok(btns >= 2, 'the completed component\'s cards offer a quiet carry action :: ' + btns);

  // ---- 2. carry the fixture's five standings through the real route -----
  const carried = await page.evaluate(async (tid) => {
    const mk = (kind, ref, excerpt, standing) => fetch('/api/carry', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({trace_id: tid, source_kind: kind, source_ref: ref, excerpt, standing})}).then(r => r.json());
    const out = [];
    out.push(await mk('candidate', {concept_id: 'concept_fx1', title: 'The Afterschool Slot', field: 'definition'},
      'The Afterschool Slot: the interval between school letting out and dinner being called.',
      {anchor_fit: 'partial', friction_verdict: 'keep', route: 'candidate concept'}));
    out.push(await mk('anchor_fit', {concept_id: 'concept_fx1', title: 'The Afterschool Slot', field: 'claim_support'},
      'Anchor fit (partial): anchor: midday, cradle · claim: school, dinner',
      {anchor_fit: 'partial', route: 'anchor-fit difference — reviewer-selected words, not a proof'}));
    out.push(await mk('candidate', {concept_id: 'concept_fx2', title: 'The Consecrated Porch', field: 'definition'},
      'The Consecrated Porch: sacred ground read as supervision, so the transgression borrows the institution’s calm.',
      {anchor_fit: 'contradicted', friction_verdict: 'reject', contradicted: true, route: 'candidate concept'}));
    out.push(await mk('candidate', {concept_id: 'concept_fx1', title: 'The Afterschool Slot', field: 'example_sentence'},
      'The afterschool slot ran from three to six, and it held both my glove and my brother’s lighter equally.',
      {invented: true, route: 'model-written example'}));
    out.push(await mk('thread', {index: 3, title: 'Latchkey children', work: 'American social history'},
      'Latchkey children — American social history — a documented interval between institutional endpoints.',
      {route: 'lateral thread · holds', recall_only: true, unverified: true}));
    return out;
  }, TRACE);
  ok(carried.every(c => c && c.ok && c.carry && c.carry.carry_id),
     'five carries recorded through the real route :: ' + carried.map(c => c && (c.error || c.carry.carry_id)).join(','));
  ok(carried.every(c => c.carry.means === 'may be useful while revising' && (c.carry.is_not || []).includes('accepted')),
     'each carry records what it means and what it is not :: ' + JSON.stringify(carried[0].carry.is_not));
  ok(carried.every(c => c.carry.analyzed && /^src:[0-9a-f]{12}$/.test(c.carry.analyzed.source_key)),
     'each carry is bound to the hash of the text the workup examined, not to a card position :: '
     + carried[0].carry.analyzed.source_key);
  ok(carried.every(c => !('candidates' in c.carry) && !('groups' in c.carry)),
     'a carry holds an excerpt and a reference, not a copy of the result');

  // ---- 3. carrying produced no ruling and changed no candidate -----------
  const untouched = await page.evaluate(async (tid) => {
    const r = await fetch('/api/result/' + tid); const d = await r.json();
    const g = d.groups.find(x => !x.failed);
    const c = g.candidates[0];
    const b = c.bone_flesh_friction || c.bff;
    return {verdict: b.friction.verdict, decided: !!(b.decision || c.decision)};
  }, TRACE);
  ok(untouched.verdict === 'keep' && !untouched.decided,
     'carrying created no judgment and moved no verdict :: ' + JSON.stringify(untouched));

  // ---- 4. the control appears after a RELOAD, from the record -------------
  await page.reload(); await page.waitForTimeout(900);
  const ctl = await page.evaluate(() => {
    const b = document.getElementById('carry-ctl'); return b ? b.innerText.trim() : '';
  });
  ok(/Revision notes · 5/.test(ctl), 'the carries reopen after a page reload, counted from the record :: ' + ctl);

  // ---- 5. the tray beside an untouched room ------------------------------
  await page.evaluate(() => { openCompose(); });
  await page.waitForTimeout(300);
  const roomBefore = await page.evaluate(() => {
    const box = document.getElementById('compose-text');
    box.value = 'A midday sentence the owner is writing now.\nSecond line.';
    box.setSelectionRange(9, 17);
    box.scrollTop = 0;
    box.focus();
    return {value: box.value, s: box.selectionStart, e: box.selectionEnd, scroll: box.scrollTop,
            focused: document.activeElement === box, id: box};
  });
  await page.keyboard.type('X');            // put something on the undo stack
  await page.evaluate(() => openCarryTray());
  await page.waitForTimeout(400);
  const roomAfter = await page.evaluate(() => {
    const box = document.getElementById('compose-text');
    return {value: box.value, s: box.selectionStart, e: box.selectionEnd, scroll: box.scrollTop,
            trayOpen: document.getElementById('carry-tray').style.display === 'block',
            same: box === window.__boxRef};
  });
  ok(roomAfter.trayOpen, 'the tray opened :: ' + roomAfter.trayOpen);
  // Typing X over the selected word replaced it — that is the browser doing
  // exactly what the owner did, and it is the value the tray must leave alone.
  ok(roomAfter.value === 'A midday X the owner is writing now.\nSecond line.',
     'the draft text is exactly what the owner typed — nothing inserted :: ' + JSON.stringify(roomAfter.value));
  ok(roomAfter.s === roomAfter.e && roomAfter.s === 10,
     'the caret is where typing left it :: ' + roomAfter.s + '/' + roomAfter.e);
  // undo still works after the tray opened: native history was not destroyed
  await page.evaluate(() => document.getElementById('compose-text').focus());
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+Z' : 'Control+Z');
  await page.waitForTimeout(150);
  const undone = await page.evaluate(() => document.getElementById('compose-text').value);
  ok(undone === 'A midday sentence the owner is writing now.\nSecond line.',
     'native undo still reaches the keystroke made before the tray opened :: ' + JSON.stringify(undone));

  // ---- 6. standings are TEXT on the tray and in copied output -------------
  const tray = await page.evaluate(() => {
    const t = document.getElementById('carry-tray');
    const items = [...t.querySelectorAll('.carry-item')];
    return {
      n: items.length,
      text: t.innerText,
      labels: [...t.querySelectorAll('.carry-label')].map(x => x.innerText),
      visibleLabels: [...t.querySelectorAll('.carry-label')].filter(x => {
        const cs = getComputedStyle(x); const r = x.getBoundingClientRect();
        return cs.display !== 'none' && cs.visibility !== 'hidden' && cs.opacity !== '0' && r.width > 0 && r.height > 0;
      }).length,
      copied: CARRIES.map(c => carryCopyText(c)),
    };
  });
  ok(tray.n === 5, 'all five carries are on the tray :: ' + tray.n);
  // THE RENDERED TRAY, not the label elements. innerText of a display:none
  // element still returns its text, so reading labels one by one passed
  // while a stylesheet hid every one of them — the exact sabotage this
  // block was told to survive. The parent's innerText excludes hidden
  // children; that is the witness a reader actually has.
  ok(/INVENTED EXAMPLE/.test(tray.text), 'the invented example is labelled INVENTED on the rendered tray :: ' + tray.text.slice(0, 160));
  ok(/CONTRADICTED/.test(tray.text), 'the contradicted proposal is labelled CONTRADICTED on the rendered tray');
  ok(/RECALL ONLY/.test(tray.text), 'the recall-only comparison stays recall-only on the rendered tray');
  ok(/anchor fit: partial/i.test(tray.text), 'the partial anchor-fit stays partial on the rendered tray');
  ok(!/\bsupported\b/i.test(tray.text), 'nothing on the rendered tray reads as supported');
  ok(tray.labels.length >= 8 && tray.visibleLabels === tray.labels.length,
     'every standing label is actually displayed, not merely present in the DOM :: '
     + tray.visibleLabels + '/' + tray.labels.length);
  ok(tray.copied.some(c => /^\[.*INVENTED EXAMPLE.*\]/.test(c)),
     'the invented label travels INSIDE copied text, not only in a stylesheet');
  ok(tray.copied.some(c => /CONTRADICTED/.test(c)), 'the contradicted label travels in copied text');
  ok(!/Keep this concept/.test(tray.text), 'the tray offers no ruling — carry is not keep');

  // ---- 7. draft mismatch cannot pass silently ------------------------------
  ok(/This workup examined an earlier version of this draft/.test(tray.text),
     'a draft that differs from the analysed text is said so, plainly');
  const choices = await page.evaluate(() => [...document.querySelectorAll('.carry-stale button')].map(b => b.innerText.trim()));
  ok(choices.includes('Open the analyzed version') && choices.some(c => /Carry these notes to the current version anyway/.test(c)) && choices.includes('Cancel'),
     'the mismatch offers the three explicit choices :: ' + JSON.stringify(choices));
  // "Open the analyzed version" shows it BESIDE the room, never in the box
  await page.evaluate(() => document.querySelector('.carry-stale button').click());
  await page.waitForTimeout(400);
  const shown = await page.evaluate(() => ({
    pre: (document.querySelector('.carry-stale pre.analyzed') || {}).textContent || '',
    box: document.getElementById('compose-text').value,
  }));
  ok(shown.pre.length > 40 && shown.box === 'A midday sentence the owner is writing now.\nSecond line.',
     'opening the analysed version shows it read-only and leaves the draft alone :: ' + shown.pre.slice(0, 50));
  // the owner's explicit choice is recorded as his
  const first = carried[0].carry.carry_id;
  await page.evaluate(async (id) => {
    const btn = [...document.querySelectorAll('.carry-stale button')].find(b => /anyway/.test(b.innerText));
    await retargetCarry(id, btn);
  }, first);
  await page.waitForTimeout(400);
  const retargeted = await page.evaluate(async (id) => {
    const d = await (await fetch('/api/carries')).json();
    const c = d.carries.find(x => x.carry_id === id);
    return c && c.target;
  }, first);
  ok(retargeted && retargeted.retargeted_by_owner === 'carry_to_current_anyway',
     'carrying to a different draft is recorded as the owner\'s choice :: ' + JSON.stringify(retargeted));

  // ---- 8. the draft in the room after all of that -------------------------
  const finalBox = await page.evaluate(() => document.getElementById('compose-text').value);
  ok(finalBox === 'A midday sentence the owner is writing now.\nSecond line.',
     'the original draft was never changed by anything carried :: ' + JSON.stringify(finalBox));

  // ---- 9. dismissed and used are history, not deletion --------------------
  await page.evaluate(async (ids) => { await carryUsed(ids[1]); await carryDismiss(ids[4]); },
                      carried.map(c => c.carry.carry_id));
  const after = await page.evaluate(async () => {
    const d = await (await fetch('/api/carries')).json();
    return {active: d.carries.length, summary: d.summary};
  });
  ok(after.active === 3 && after.summary.used === 1 && after.summary.dismissed === 1 && after.summary.total === 5,
     'used and dismissed leave the tray but stay in the record :: ' + JSON.stringify(after));

  ok(errs.length === 0, 'no page errors :: ' + errs.join(' | '));
  await browser.close();
  finish('carry');
})();
