// The Carry Back journey (block 123) — the bridge from a workup to the room.
//
// What only a browser can testify to: that carrying disturbs nothing in the
// live textarea; that the standing labels are TEXT and survive a copy; that
// a draft which differs from the analysed one cannot pass silently; that a
// contradicted item cannot render as supported; and that nothing here ever
// inserts prose into the draft or produces a ruling.
//
// Block 123b — SERVER AUTHORITY and EXACT IDENTITY. Every carry below names
// an object; the server resolves it against the run's own record and takes
// the excerpt and the standing from there. The client's claims are sent and
// must LOSE. And every carry is posted with the trace a card actually
// carries — the COMPONENT'S, whose record holds the dissection's gist as its
// input_text — and must come back bound to the draft the Go Deep run
// examined, with the recorded road written into it.
//
// The fixture is a real partial Go Deep run through the real path, with the
// offline gateway answering anchor-support by title so the RECORD holds a
// partial fit and a contradicted proposal, plus a rabbithole opened from the
// completed component's card the way the page opens one. The owner's
// passage is not here.
const fs = require('fs');
const path = require('path');
const { BASE, DIR, ok, launch, pairedContext, finish } = require('./lib');
const IDS = JSON.parse(fs.readFileSync(path.join(DIR, 'partial.json'), 'utf8'));
const TRACE = IDS.deepPartial;
const COMPONENT = IDS.component;             // what a candidate card sends
const SPROUT = IDS.sproutFromComponent;      // what a thread/door card sends

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

  // ---- 2. five carries through the real route, each LYING about itself --
  // The page sends what a card sends — the component's trace, a name for
  // the object — plus an excerpt and a standing that are WRONG on purpose.
  // What comes back must be the record's text and the record's standing.
  const carried = await page.evaluate(async ([comp, sprout]) => {
    const mk = (tid, kind, ref, excerpt, standing) => fetch('/api/carry', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({trace_id: tid, source_kind: kind, source_ref: ref, excerpt, standing})}).then(r => r.json());
    const out = [];
    // a partial candidate, claimed as supported with a rewritten definition
    out.push(await mk(comp, 'candidate', {title: 'The Refusenik Posture', field: 'definition'},
      'The Refusenik Posture: a definition the page made up.',
      {anchor_fit: 'supported', friction_verdict: 'keep', route: 'candidate concept'}));
    // its anchor-fit difference, claimed as supported
    out.push(await mk(comp, 'anchor_fit', {title: 'The Refusenik Posture', field: 'claim_support'},
      'Anchor fit (supported): the page says so',
      {anchor_fit: 'supported', route: 'anchor-fit difference — reviewer-selected words, not a proof'}));
    // the CONTRADICTED candidate, claimed as supported and kept
    out.push(await mk(comp, 'candidate', {title: 'Threshold Grief', field: 'definition'},
      'Threshold Grief: the page says this one is fine.',
      {anchor_fit: 'supported', friction_verdict: 'keep', contradicted: false, route: 'candidate concept'}));
    // the model's example sentence, claimed as the owner's own words
    out.push(await mk(comp, 'candidate', {title: 'The Refusenik Posture', field: 'example_sentence'},
      'a sentence the owner never wrote, claimed as his',
      {invented: false, route: 'owner-authored'}));
    // a lateral thread from the rabbithole opened off that card, claimed verified
    out.push(await mk(sprout, 'thread', {index: 0, title: 'Cassandra'},
      'Cassandra — verified, says the page',
      {route: 'lateral thread · verified', recall_only: false, unverified: false}));
    return out;
  }, [COMPONENT, SPROUT]);
  ok(carried.every(c => c && c.ok && c.carry && c.carry.carry_id),
     'five carries recorded through the real route :: ' + carried.map(c => c && (c.error || c.carry.carry_id)).join(','));
  ok(carried.every(c => c.carry.means === 'may be useful while revising' && (c.carry.is_not || []).includes('accepted')),
     'each carry records what it means and what it is not :: ' + JSON.stringify(carried[0].carry.is_not));
  ok(carried.every(c => c.carry.analyzed && /^src:[0-9a-f]{12}$/.test(c.carry.analyzed.source_key)),
     'each carry is bound to the hash of the text the workup examined, not to a card position :: '
     + carried[0].carry.analyzed.source_key);
  ok(carried.every(c => !('candidates' in c.carry) && !('groups' in c.carry)),
     'a carry holds an excerpt and a reference, not a copy of the result');
  // server authority: the record's text and standing, never the client's
  const [cDef, cFit, cBad, cEx, cThr] = carried.map(c => c.carry);
  ok(/^The Refusenik Posture: The stance of one who exits a containing system/.test(cDef.excerpt),
     'the excerpt is the record\'s own definition, not the one the page sent :: ' + JSON.stringify(cDef.excerpt.slice(0, 80)));
  ok(cDef.standing.anchor_fit === 'partial' && cDef.standing.friction_verdict === 'keep',
     'a partial candidate claimed as supported comes back partial :: ' + JSON.stringify(cDef.standing));
  ok(cFit.standing.anchor_fit === 'partial' && /The description is licensed; the causal claim is not/.test(cFit.excerpt),
     'the anchor-fit difference is the reviewer\'s recorded words :: ' + JSON.stringify(cFit.excerpt));
  ok(cBad.standing.contradicted === true && cBad.standing.anchor_fit === 'contradicted'
     && cBad.standing.friction_verdict === 'contradicted' && /^Threshold Grief: Generic liminal-space/.test(cBad.excerpt),
     'a contradicted candidate claimed as supported and kept comes back contradicted, with the record\'s text :: '
     + JSON.stringify(cBad.standing));
  ok(cEx.standing.invented === true && cEx.standing.route === 'model-written example'
     && /^He quit the job but kept the refusenik posture/.test(cEx.excerpt) && !('anchor_fit' in cEx.standing),
     'the example sentence claimed as the owner\'s comes back INVENTED, in the model\'s words, with no anchor fit it was never given :: '
     + JSON.stringify(cEx.standing));
  ok(cThr.standing.unverified === true && cThr.standing.route === 'lateral thread · holds'
     && /^Cassandra — Greek myth/.test(cThr.excerpt) && !/verified, says the page/.test(cThr.excerpt),
     'a thread claimed verified comes back unverified, with the record\'s route :: ' + JSON.stringify(cThr.standing));
  ok(cDef.source.ref.concept_id && /^concept_/.test(cDef.source.ref.concept_id) && cDef.source.ref.field === 'definition',
     'the stored ref is the identity the server settled (concept_id + field), not the bare title the page sent :: '
     + JSON.stringify(cDef.source.ref));
  // exact identity: posted with the component's trace, bound to the draft
  ok(carried.every(c => c.carry.analyzed.trace_id === TRACE),
     'every carry is bound to the Go Deep run that held the draft, though none was posted with its trace :: '
     + carried.map(c => c.carry.analyzed.trace_id).join(','));
  ok(new Set(carried.map(c => c.carry.analyzed.source_key)).size === 1,
     'all five carries share one source key — the draft\'s, not the component gist\'s or the sprout\'s :: '
     + [...new Set(carried.map(c => c.carry.analyzed.source_key))].join(','));
  ok(/^A passage about pretending while poor/.test(cDef.analyzed.head),
     'the analysed head is the owner\'s draft, not the dissection\'s gist :: ' + JSON.stringify(cDef.analyzed.head));
  ok(cDef.analyzed.chain.map(h => h.link).join('>') === 'component_of>root'
     && cThr.analyzed.chain.map(h => h.link).join('>') === 'parent_trace_id>component_of>root',
     'the road from the card\'s run to the draft is written into the carry, hop by hop :: '
     + JSON.stringify([cDef.analyzed.chain, cThr.analyzed.chain]));
  // a name that does not resolve is refused, never guessed
  const refused = await page.evaluate(async (comp) => {
    const post = body => fetch('/api/carry', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(Object.assign({trace_id: comp, excerpt: 'x', standing: {}}, body))}).then(async r => ({status: r.status, body: await r.json()}));
    return {
      missing: await post({source_kind: 'candidate', source_ref: {title: 'The Afterschool Slot', field: 'definition'}}),
      fitOnPartialOnly: await post({source_kind: 'anchor_fit', source_ref: {title: 'Nobody'}}),
      field: await post({source_kind: 'candidate', source_ref: {title: 'The Refusenik Posture', field: 'plot'}}),
    };
  }, COMPONENT);
  ok(Object.values(refused).every(r => r.status === 400 && r.body.error && !r.body.ok),
     'a ref that names nothing in the record is refused with a reason, not guessed :: ' + JSON.stringify(refused));

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
  // the thread's standing is what ITS record holds: the rabbithole's review
  // saw provider results, so it is unverified but not recall-only — and the
  // tray may not say otherwise in either direction
  const sproutCited = await page.evaluate(async (sp) => {
    const d = await (await fetch('/api/result/' + sp)).json(); return (d.citations || []).length;
  }, SPROUT);
  ok(/UNVERIFIED/.test(tray.text) && (/RECALL ONLY/.test(tray.text) === (sproutCited === 0)),
     'the lateral thread reads UNVERIFIED, and RECALL ONLY exactly when its run saw no provider results :: '
     + sproutCited + ' citation row(s); ' + tray.text.match(/UNVERIFIED|RECALL ONLY[^\n]*/g));
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
  // 123b: the analysed version is the DRAFT the Go Deep run examined, not
  // the dissection's gist that the component's own record holds
  ok(/^A passage about pretending while poor/.test(shown.pre) && !/The part of the mechanism/.test(shown.pre),
     'the analysed version opened is the owner\'s draft, not the component\'s forge text :: ' + JSON.stringify(shown.pre.slice(0, 60)));
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
