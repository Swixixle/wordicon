// workspace-v2 — the Results side (instructions §6): results, readers,
// notes and sources in separate tabs, no merged verdict. A result card
// names where the result came from, whether the draft has changed since,
// and offers the full view; closing the side hides it and nothing else.
// A finished operation raises the count on the header control and never
// opens a closed side or moves the caret.
import { getJSON, postJSON, el, whenOf, toast, requestKey } from './util.js';

const POLL_MS = 1500;
const STATE_WORDS = { queued: 'Queued', running: 'Running', done: 'Done', complete: 'Done', failed: 'Failed', unknown: 'Outcome unknown' };

export class Results {
  constructor(session, layout, places, hooks = {}) {
    this.session = session; this.layout = layout; this.places = places; this.hooks = hooks;
    this.body = document.getElementById('results-body');
    this.tab = 'results';
    this.tracked = new Map();     // operation_id -> {op, proposal, action, last}
    this.selected = null;         // operation id or trace id whose card is open
    this.unseen = 0;
    this.notice = null;
    this.custom = null;
    this.proposal = null;
    this.bindTabs();
    this.pollTimer = 0;
  }

  bindTabs() {
    for (const t of document.querySelectorAll('#results .tab')) {
      t.addEventListener('click', () => this.showTab(t.dataset.tab));
    }
    document.getElementById('activity-btn').addEventListener('click', () => { this.showTab('results'); this.layout.setResults(true); });
  }
  showTab(name) {
    this.tab = name;
    for (const t of document.querySelectorAll('#results .tab')) { const on = t.dataset.tab === name; t.classList.toggle('on', on); t.setAttribute('aria-selected', String(on)); }
    this.render();
  }

  // ---- what the count means ------------------------------------------------
  bumpUnseen() {
    if (this.layout.state.results && !this.layout.state.focus) return;   // visible: nothing is unseen
    this.unseen += 1; this.renderCount();
  }
  renderCount() {
    const c = document.getElementById('results-count');
    if (this.unseen > 0) { c.textContent = String(this.unseen); c.hidden = false; } else { c.hidden = true; }
  }
  seen() { this.unseen = 0; this.renderCount(); }

  // ---- proposal and notices --------------------------------------------------
  showProposal(prepared, action, handlers) { this.proposal = { prepared, action, handlers }; this.notice = null; this.showTab('results'); }
  clearProposal() { this.proposal = null; this.render(); }
  showNotice(text, choices = []) { this.notice = { text, choices }; this.custom = null; this.showTab('results'); }
  // an element the shell built (Versions, for one) shown at the top of Results until dismissed
  showCustom(element) { this.custom = element; this.notice = null; this.showTab('results'); }
  // a debounced re-render of the results tab, for freshness lines after edits
  refresh() { clearTimeout(this._refresh); this._refresh = setTimeout(() => { if (this.tab === 'results') this.render(); }, 350); }

  // ---- tracking an operation started here ------------------------------------
  track(started, prepared) {
    const id = started.operation_id;
    this.tracked.set(id, { id, kind: started.kind, status: started.status, prepared, startedAt: new Date().toISOString(), last: null });
    this.selected = id;
    this.render();
    this.poll();
    if (this.hooks.onActivity) this.hooks.onActivity();
  }
  // The store's recent operations (slice D): what was running or done
  // before this page opened, or before the server restarted — listed from
  // the record, with their state as the record has it. No proposal is in
  // memory for them, so a card reads from the operation itself.
  async loadRecent(labelOf) {
    const r = await getJSON('/api/operations?limit=30');
    if (!r.ok) return;
    for (const o of (r.data.operations || [])) {
      if (this.tracked.has(o.operation_id)) continue;
      this.tracked.set(o.operation_id, { id: o.operation_id, kind: o.kind, status: o.status, prepared: null, label: labelOf ? labelOf(o.action_id) : o.action_id,
                                         startedAt: o.created_at, last: o, fromStore: true });
    }
    this.dispatcher = r.data.dispatcher || null;
    this.render();
    this.poll();
    if (this.hooks.onActivity) this.hooks.onActivity();
  }
  // open an operation or a reading by id from Your work: tracked from the record, then read once
  open(id, kind) {
    if (!this.tracked.has(id)) this.tracked.set(id, { id, kind, status: 'unknown', prepared: null, label: kind === 'reading' ? 'Readers' : 'Operation', startedAt: '', last: null, fromStore: true });
    this.selected = id;
    this.showTab('results');
    const t = this.tracked.get(id);
    getJSON('/api/operations/' + encodeURIComponent(id)).then(r => {
      if (!r.ok) { t.status = 'unknown'; t.last = { error: r.data.error }; this.render(); return; }
      const d = r.data;
      t.last = d; t.kind = d.kind || kind; t.startedAt = d.created_at || t.startedAt;
      t.status = d.kind === 'reading' ? (d.reading && d.reading.pending === 0 ? 'done' : 'running') : (d.status || 'unknown');
      if (d.action_id && this.hooks.labelOf) t.label = this.hooks.labelOf(d.action_id);
      this.render();
      if (!['done', 'complete', 'failed', 'unknown'].includes(t.status)) this.poll();
    });
  }
  // "Check status / recover result": the record and the result files read again; nothing is sent
  async recover(t) {
    const r = await postJSON('/api/operations/' + encodeURIComponent(t.id) + '/recover', {});
    if (!r.ok) { toast('Not recovered: ' + (r.data.error || r.status)); return; }
    t.status = r.data.status; t.last = { ...(t.last || {}), status: r.data.status, recovery: r.data.recovery };
    toast('Checked from the record — nothing was sent. ' + (r.data.recovery && r.data.recovery.why || ''), 6000);
    this.render(); this.poll();
    if (this.hooks.onActivity) this.hooks.onActivity();
  }
  // "Start another attempt": a NEW operation under a new key, linked to this one; the cost is said
  async anotherAttempt(t) {
    const r = await postJSON('/api/operations/' + encodeURIComponent(t.id) + '/attempts', { request_key: requestKey() });
    if (!r.ok) {
      const d = r.data || {};
      this.showNotice((d.error || ('HTTP ' + r.status)) + (d.nothing_was_sent ? ' — nothing was sent.' : '') + (d.changed ? ' Changed: ' + Object.entries(d.changed).map(([k, v]) => k + ' ' + v.was + ' → ' + v.now).join(', ') : ''),
                      d.changed ? [{ label: 'Start it under the new plan', onClick: async () => { const r2 = await postJSON('/api/operations/' + encodeURIComponent(t.id) + '/attempts', { request_key: requestKey(), accept_changed_plan: true }); if (r2.ok) { this.notice = null; this.track({ operation_id: r2.data.operation_id, kind: r2.data.kind, status: r2.data.status }, t.prepared); } else toast('Not started: ' + (r2.data.error || r2.status)); } }] : []);
      return;
    }
    toast(r.data.cost || 'Another attempt started.', 6000);
    this.track({ operation_id: r.data.operation_id, kind: r.data.kind, status: r.data.status }, t.prepared);
  }
  async poll() {
    clearTimeout(this.pollTimer);
    if (this.polling) { this.pollAgain = true; return; }     // one poll at a time; a second request waits for it
    this.polling = true;
    let busy = false;
    try {
      for (const t of this.tracked.values()) {
        // a finished operation is read once more when it came from the list
        // without its recovery line; otherwise a terminal state is not re-read
        const needsDetail = t.fromStore && t.last && !t.last.recovery;
        if (['done', 'complete', 'failed', 'unknown'].includes(t.status) && !needsDetail) continue;
        let r;
        try { r = await getJSON('/api/operations/' + encodeURIComponent(t.id)); } catch (e) { busy = true; continue; }
        if (r.status === 404) { t.status = 'unknown'; t.last = r.data; continue; }
        if (!r.ok) { busy = true; continue; }
        const d = r.data;
        const before = t.status;
        t.last = d;
        t.status = d.kind === 'reading' ? (d.reading && d.reading.pending === 0 ? 'done' : 'running') : (d.status || 'unknown');
        if (t.status !== before && ['done', 'complete', 'failed'].includes(t.status)) { this.bumpUnseen(); if (this.hooks.onActivity) this.hooks.onActivity(); }
        if (!['done', 'complete', 'failed', 'unknown'].includes(t.status)) busy = true;
      }
      try { this.render(); } catch (e) { console.error('results render failed', e); }
    } finally {
      this.polling = false;
    }
    if (busy || this.pollAgain) { this.pollAgain = false; this.pollTimer = setTimeout(() => this.poll(), POLL_MS); }
  }

  summary() {
    let running = 0, done = 0, attention = 0;
    for (const t of this.tracked.values()) {
      if (['done', 'complete'].includes(t.status)) done += 1;
      else if (['failed', 'unknown'].includes(t.status)) attention += 1;
      else running += 1;
    }
    return { running, done, attention };
  }

  // ---- freshness: the snapshot against the draft now ---------------------------
  // Freshness is the editor session and the local sequence — the content's
  // own generation — never the server revision: the writer's own autosave
  // acknowledgment moves the revision without changing a word, and must
  // not make a capture stale (§7). A reopen is a new editor session.
  freshness(prepared) {
    const s = prepared && prepared.disclosure && prepared.disclosure.scope;
    if (!s || !s.doc_id) return { fresh: null, text: '' };
    const same = this.session.id === s.doc_id;
    if (!same) return { fresh: false, text: 'From another document.' };
    const unchanged = (!s.editor_session || this.session.editorSession === s.editor_session) && this.session.seq === s.seq;
    return unchanged ? { fresh: true, text: 'The draft hasn’t changed since.' }
                     : { fresh: false, text: 'This draft changed. Review the earlier version before applying changes.' };
  }

  // ---- rendering ---------------------------------------------------------------
  render() {
    const b = this.body; b.textContent = '';
    if (this.tab === 'results') this.renderResults(b);
    else if (this.tab === 'feedback') this.renderFeedback(b);
    else if (this.tab === 'notes') this.renderNotes(b);
    else if (this.tab === 'sources') this.renderSources(b);
    if (this.layout.state.results) this.seen();
  }

  renderResults(b) {
    if (this.notice) {
      const n = el('div', { class: 'card' }, [el('div', { class: 'warn', text: this.notice.text })]);
      if (this.notice.choices.length) n.appendChild(el('div', { class: 'row' }, this.notice.choices.map(c => el('button', { class: 'btn', type: 'button', text: c.label, onclick: c.onClick }))));
      n.appendChild(el('button', { class: 'btn small', type: 'button', text: 'Dismiss', onclick: () => { this.notice = null; this.render(); } }));
      b.appendChild(n);
    }
    if (this.custom) { const c = el('div', { class: 'card' }, [this.custom, el('button', { class: 'btn small', type: 'button', text: 'Close', onclick: () => { this.custom = null; this.render(); } })]); b.appendChild(c); }
    if (this.proposal) b.appendChild(this.proposalCard(this.proposal));
    const sel = this.selected && this.tracked.get(this.selected);
    if (sel) b.appendChild(this.resultCard(sel));
    b.appendChild(this.activityList());
  }

  proposalCard({ prepared, action, handlers }) {
    const d = prepared.disclosure, sc = d.scope || {};
    const scopeLine = sc.kind === 'selection' ? `Scope: your selection — ${sc.words} word${sc.words === 1 ? '' : 's'}, ${sc.chars} character${sc.chars === 1 ? '' : 's'}, sent exactly as selected.`
                    : sc.kind === 'document' ? `Scope: the whole draft — ${sc.words} word${sc.words === 1 ? '' : 's'}, ${sc.chars} characters, sent exactly as written.`
                    : `Scope: ${sc.kind}${sc.head ? ' — “' + sc.head + '”' : ''}.`;
    const lane = d.lane || {};
    const card = el('div', { class: 'card', id: 'proposal-card' }, [
      el('div', { class: 'result-title', text: action.label }),
      el('div', { class: 'kv', text: scopeLine }),
      el('div', { class: 'kv', text: `Tool: ${action.label}${action.mode ? ' · ' + action.mode : ''} · calls: ${d.calls}` }),
      el('div', { class: 'kv', text: `Leaves this machine: ${d.leaves_this_machine.fields.join(', ')} — to ${d.leaves_this_machine.recipient === 'model' ? (lane.external ? 'a live model (' + (lane.model || lane.lane) + ')' : 'no one: the mock lane makes no provider request') : d.leaves_this_machine.recipient}.` }),
      el('div', { class: 'kv', text: `Cost: ${d.cost}.` }),
      sc.kind === 'selection' || sc.kind === 'document' ? el('div', { class: 'kv', text: 'Sent as text only: the exact words; headings, emphasis, lists and links are not sent.' }) : null,
      d.available ? null : el('div', { class: 'warn', text: 'Not available now: ' + d.reason }),
    ]);
    const row = el('div', { class: 'row' }, [
      el('button', { class: 'btn primary', type: 'button', text: 'Start', disabled: d.available ? null : true, onclick: handlers.onStart }),
      el('span', { class: 'muted small-text', text: 'Nothing has started · Esc closes this' }),
    ]);
    card.appendChild(row);
    card.appendChild(el('details', {}, [el('summary', { text: 'Details' }), el('div', { class: 'small-text muted', text: `proposal ${prepared.prepared_id} · snapshot ${sc.snapshot_id || '—'} · text sha256 ${(sc.text_sha256 || '').slice(0, 16)}…` })]));
    if (this._esc) document.removeEventListener('keydown', this._esc);     // one listener however often the card is redrawn
    const esc = e => { if (e.key === 'Escape') { document.removeEventListener('keydown', esc); this._esc = null; handlers.onClose(); } };
    this._esc = esc;
    document.addEventListener('keydown', esc);
    setTimeout(() => { const s = card.querySelector('.btn.primary'); if (s && !s.disabled) s.focus(); }, 0);
    return card;
  }

  resultCard(t) {
    const p = t.prepared, a = p ? p.label : (t.label || t.kind);
    const d = t.last || {};
    const state = STATE_WORDS[t.status] || t.status;
    const fresh = this.freshness(p);
    const rec = d.recovery || null;
    const card = el('div', { class: 'card' }, [
      el('div', { class: 'row', style: 'justify-content: space-between' }, [el('div', { class: 'result-title', text: a }), el('span', { class: 'chip', text: whenOf(t.startedAt) })]),
      p && p.disclosure.scope && p.disclosure.scope.doc_id ? el('div', { class: 'kv', text: `From this draft, revision ${p.disclosure.scope.revision}${p.disclosure.scope.kind === 'selection' ? ' · your selection “' + p.disclosure.scope.head + '”' : ''}` }) : null,
      !p && t.fromStore ? el('div', { class: 'kv muted', text: 'From the record' + (d.retry_parent ? ' · another attempt of an earlier operation' : '') + (d.in_process === false ? ' · not running in this process' : '') }) : null,
      fresh.text ? el('div', { class: 'kv ' + (fresh.fresh ? 'ok' : 'warn'), text: fresh.text }) : null,
      el('div', { class: 'kv state ' + (t.status === 'failed' || t.status === 'unknown' ? 'bad' : (t.status === 'done' || t.status === 'complete' ? 'good' : 'running')), text: state + (d.progress && !['done', 'complete', 'failed', 'unknown'].includes(t.status) ? ' · ' + d.progress : '') }),
    ]);
    if (t.status === 'unknown') card.appendChild(el('div', { class: 'warn small-text', text: 'Outcome unknown — ' + (rec && rec.why ? rec.why : 'the server was interrupted; it may still have run. Nothing was sent again.') }));
    if (t.status === 'failed') card.appendChild(el('div', { class: 'warn small-text', text: 'Failed — ' + (d.error || 'no reason was recorded') + '.' }));
    if (t.status === 'queued' && d.progress && /dispatcher/.test(d.progress)) card.appendChild(el('div', { class: 'warn small-text', text: d.progress }));
    if (rec && rec.sent_evidence && ['failed', 'unknown', 'queued'].includes(t.status)) card.appendChild(el('div', { class: 'muted small-text', text: rec.sent_evidence + '.' }));
    if (['failed', 'unknown', 'queued'].includes(t.status) && t.kind === 'job') {
      card.appendChild(el('div', { class: 'row' }, [
        el('button', { class: 'btn small', type: 'button', text: 'Check status / recover result', title: 'Reads the record and the result files again; sends nothing', onclick: () => this.recover(t) }),
        t.status !== 'queued' ? el('button', { class: 'btn small', type: 'button', text: 'Start another attempt', title: 'A new operation under a new key, linked to this one; it sends the frozen text again', onclick: () => this.anotherAttempt(t) }) : null,
      ]));
    }
    if (t.kind === 'reading' && d.reading) {
      const v = d.reading;
      card.appendChild(el('div', { class: 'kv', text: `${v.answered || 0} of ${(v.readers || []).length} readers answered · ${v.no_conference || 'the readers answer separately'}` }));
      for (const r of (v.readers || [])) {
        const segs = (r.response && r.response.segments) || [];
        const det = el('details', { open: r.status === 'complete' ? true : null }, [el('summary', { text: `${cap(r.reader)} — ${r.reads_for} · ${r.status}` })]);
        for (const s of segs.slice(0, 12)) det.appendChild(el('div', { class: 'kv' }, [el('span', { class: 'chip', text: s.class || '' }), ' ', el('span', { text: s.text || '' })]));
        if (r.status !== 'complete' && r.response && r.response.error) det.appendChild(el('div', { class: 'warn small-text', text: r.response.error }));
        card.appendChild(det);
      }
    }
    if (t.kind === 'job' && ['done', 'complete'].includes(t.status)) {
      const titles = d.titles || [];
      if (titles.length) card.appendChild(el('div', { class: 'kv', text: `${titles.length} candidate${titles.length === 1 ? '' : 's'}: ${titles.slice(0, 5).join(' · ')}${titles.length > 5 ? ' …' : ''}` }));
      // a candidate word is a textual suggestion for the words it was made
      // from: Insert below / Replace, guarded (apply.js). Only for a result
      // made from a selection — a whole-draft result has no place to go.
      const candidates = Array.from(new Set([...titles, ...(d.groups || []).flatMap(g => g.titles || [])].filter(Boolean)));
      if (candidates.length && p && p.disclosure.scope && p.disclosure.scope.kind === 'selection' && this.hooks.applyControls) {
        const det = el('details', { class: 'apply-block' }, [el('summary', { text: 'Put a candidate into the draft (' + candidates.length + ' candidate' + (candidates.length === 1 ? '' : 's') + ')' })]);
        for (const title of candidates.slice(0, 8)) det.appendChild(el('div', { class: 'kv apply-row' }, [el('span', { class: 'chip', text: title }), this.hooks.applyControls(t, title)]));
        card.appendChild(det);
      }
      for (const g of (d.groups || [])) {
        card.appendChild(el('div', { class: 'kv' }, [
          el('span', { text: (g.label || 'a concept') + (g.titles && g.titles.length ? ' — ' + g.titles.slice(0, 3).join(' · ') : '') }),
          g.trace_id ? el('button', { class: 'linkish', type: 'button', style: 'margin-left:8px', text: 'open', onclick: () => { this.places.open('/?trace=' + encodeURIComponent(g.trace_id)); if (this.hooks.onPlace) this.hooks.onPlace(); } }) : null,
        ]));
      }
      if (d.partial) card.appendChild(el('div', { class: 'warn small-text', text: 'A partial run: some components did not complete; what came back is kept as partial, not as a reading.' }));
      card.appendChild(el('div', { class: 'row' }, [
        el('span', { class: 'chip', text: 'Kept in Your work' }),
        el('button', { class: 'btn', type: 'button', text: 'Open full result', onclick: () => { this.places.open(d.trace_id ? '/?trace=' + encodeURIComponent(d.trace_id) : '/?job=' + encodeURIComponent(t.id)); if (this.hooks.onPlace) this.hooks.onPlace(); } }),
      ]));
      card.appendChild(el('details', {}, [el('summary', { text: 'Details' }), el('div', { class: 'small-text muted', text: `operation ${t.id} · mode ${d.mode || ''} · run ${d.trace_id || (d.groups || []).map(g => g.trace_id).join(', ') || '—'} · snapshot ${d.snapshot_id || '—'}${rec ? ' · ' + rec.dispatch_intents + ' dispatch intent' + (rec.dispatch_intents === 1 ? '' : 's') + ' recorded, ' + rec.dispatch_ends + ' ended' : ''}` })]));
      card.appendChild(el('div', { class: 'muted small-text', text: 'Nothing is accepted until you rule — rulings are made on the full result.' }));
    }
    return card;
  }

  activityList() {
    const wrap = el('div', {}, [el('div', { class: 'row', style: 'justify-content: space-between' }, [el('span', { class: 'lbl', text: 'Activity' })])]);
    const items = Array.from(this.tracked.values()).sort((a, b) => (b.startedAt || '').localeCompare(a.startedAt || ''));
    if (!items.length) { wrap.appendChild(el('div', { class: 'muted small-text', text: 'Nothing started from here yet. Earlier runs are in Your work.' })); return wrap; }
    for (const t of items) {
      const d = t.last || {};
      const st = STATE_WORDS[t.status] || t.status;
      const cls = t.status === 'failed' || t.status === 'unknown' ? 'bad' : (t.status === 'done' || t.status === 'complete' ? 'good' : 'running');
      const row = el('div', { class: 'card op' }, [
        el('div', {}, [el('span', { text: t.prepared ? t.prepared.label : (t.label || t.kind) }), el('span', { class: 'muted', text: ' · ' + whenOf(t.startedAt) })]),
        el('div', { class: 'state ' + cls, text: st + (cls === 'running' && d.progress ? ' · ' + d.progress : '') }),
        el('div', { class: 'acts' }, [
          el('button', { class: 'linkish', type: 'button', text: 'Open', onclick: () => { this.selected = t.id; this.render(); } }),
          cls === 'running' ? el('button', { class: 'linkish', type: 'button', text: 'Check status', onclick: () => this.poll() }) : null,
        ]),
      ]);
      wrap.appendChild(row);
    }
    return wrap;
  }

  async renderFeedback(b) {
    b.appendChild(el('div', { class: 'lbl', text: 'Readers' }));
    const r = await getJSON('/api/moira/readings?limit=20');
    if (!r.ok) { b.appendChild(el('div', { class: 'warn', text: 'Readings could not be listed.' })); return; }
    const items = r.data.readings || [];
    if (!items.length) { b.appendChild(el('div', { class: 'muted small-text', text: 'No readings yet. Get feedback sends the draft to three readers, one call each.' })); return; }
    for (const it of items) {
      const card = el('div', { class: 'card op' }, [
        el('div', { class: 'result-title', text: (it.faculty_name || 'Readers') + ' · ' + whenOf(it.created_at) }),
        el('div', { class: 'muted small-text', text: `${it.words || 0} words read · ${Object.entries(it.statuses || {}).map(([k, v]) => k + ': ' + v).join(' · ')}` }),
        el('div', { class: 'acts' }, [el('button', { class: 'linkish', type: 'button', text: 'Open', onclick: async () => {
          const v = await getJSON('/api/moira/readings/' + encodeURIComponent(it.reading_id));
          if (!v.ok) return;
          this.tracked.set(it.reading_id, { id: it.reading_id, kind: 'reading', status: v.data.pending === 0 ? 'done' : 'running', prepared: null, startedAt: it.created_at, last: { kind: 'reading', reading: v.data } });
          this.selected = it.reading_id; this.showTab('results');
        } })]),
      ]);
      b.appendChild(card);
    }
  }

  async renderNotes(b) {
    b.appendChild(el('div', { class: 'lbl', text: 'Revision notes' }));
    const r = await getJSON('/api/carries');
    if (!r.ok) { b.appendChild(el('div', { class: 'warn', text: 'Notes could not be listed.' })); return; }
    const items = r.data.carries || [];
    b.appendChild(el('div', { class: 'muted small-text', text: 'A note means “may be useful while revising” and nothing more — not accepted, not supported, not verified.' }));
    if (!items.length) { b.appendChild(el('div', { class: 'muted small-text', text: 'No revision notes yet. Add to revision notes is offered on a result.' })); return; }
    for (const c of items) {
      b.appendChild(el('div', { class: 'card op' }, [
        el('div', { text: c.excerpt || '(no excerpt)' }),
        el('div', { class: 'muted small-text', text: `${c.standing || ''} · from run ${(c.trace_id || '').slice(0, 18)} · ${whenOf(c.recorded_at || c.at)}` }),
        c.note ? el('div', { class: 'kv', text: 'Note: ' + c.note }) : null,
      ]));
    }
  }

  async renderSources(b) {
    b.appendChild(el('div', { class: 'lbl', text: 'Sources' }));
    const r = await getJSON('/api/library');
    if (!r.ok) { b.appendChild(el('div', { class: 'warn', text: 'The Library could not be listed.' })); return; }
    const docs = r.data.documents || [];
    if (!docs.length) { b.appendChild(el('div', { class: 'muted small-text', text: 'No documents in the Library yet. Attach a file or a source admits one; nothing is read by a model on admission.' })); }
    for (const d of docs.slice(0, 30)) {
      b.appendChild(el('div', { class: 'card op' }, [
        el('div', { class: 'result-title', text: d.title || d.filename || d.doc_id || 'document' }),
        el('div', { class: 'muted small-text', text: [d.kind, d.format, d.words ? d.words + ' words' : '', whenOf(d.admitted_at || d.created_at)].filter(Boolean).join(' · ') }),
        el('div', { class: 'acts' }, [el('button', { class: 'linkish', type: 'button', text: 'Open the document', onclick: () => { this.places.open('/#library'); if (this.hooks.onPlace) this.hooks.onPlace(); } })]),
      ]));
    }
    b.appendChild(el('div', { class: 'row' }, [el('button', { class: 'btn', type: 'button', text: 'Open the Library', onclick: () => { this.places.open('/#library'); if (this.hooks.onPlace) this.hooks.onPlace(); } })]));
  }
}

function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : ''; }
