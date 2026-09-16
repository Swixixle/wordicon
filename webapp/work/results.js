// workspace-v2 — the Results side (instructions §6): results, readers,
// notes and sources in separate tabs, no merged verdict. A result card
// names where the result came from, whether the draft has changed since,
// and offers the full view; closing the side hides it and nothing else.
// A finished operation raises the count on the header control and never
// opens a closed side or moves the caret.
import { getJSON, el, whenOf, toast } from './util.js';

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
  showNotice(text, choices = []) { this.notice = { text, choices }; this.showTab('results'); }

  // ---- tracking an operation started here ------------------------------------
  track(started, prepared) {
    const id = started.operation_id;
    this.tracked.set(id, { id, kind: started.kind, status: started.status, prepared, startedAt: new Date().toISOString(), last: null });
    this.selected = id;
    this.render();
    this.poll();
    if (this.hooks.onActivity) this.hooks.onActivity();
  }
  async poll() {
    clearTimeout(this.pollTimer);
    if (this.polling) { this.pollAgain = true; return; }     // one poll at a time; a second request waits for it
    this.polling = true;
    let busy = false;
    try {
      for (const t of this.tracked.values()) {
        if (['done', 'complete', 'failed'].includes(t.status)) continue;
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
  freshness(prepared) {
    const s = prepared && prepared.disclosure && prepared.disclosure.scope;
    if (!s || !s.doc_id) return { fresh: null, text: '' };
    const same = this.session.id === s.doc_id;
    if (!same) return { fresh: false, text: 'From another document.' };
    const unchanged = this.session.revision === s.revision && this.session.seq === s.seq;
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
      d.available ? null : el('div', { class: 'warn', text: 'Not available now: ' + d.reason }),
    ]);
    const row = el('div', { class: 'row' }, [
      el('button', { class: 'btn primary', type: 'button', text: 'Start', disabled: d.available ? null : true, onclick: handlers.onStart }),
      el('span', { class: 'muted small-text', text: 'Nothing has started · Esc closes this' }),
    ]);
    card.appendChild(row);
    card.appendChild(el('details', {}, [el('summary', { text: 'Details' }), el('div', { class: 'small-text muted', text: `proposal ${prepared.prepared_id} · snapshot ${sc.snapshot_id || '—'} · text sha256 ${(sc.text_sha256 || '').slice(0, 16)}…` })]));
    const esc = e => { if (e.key === 'Escape') { document.removeEventListener('keydown', esc); handlers.onClose(); } };
    document.addEventListener('keydown', esc);
    setTimeout(() => { const s = card.querySelector('.btn.primary'); if (s && !s.disabled) s.focus(); }, 0);
    return card;
  }

  resultCard(t) {
    const p = t.prepared, a = p ? p.label : t.kind;
    const d = t.last || {};
    const state = STATE_WORDS[t.status] || t.status;
    const fresh = this.freshness(p);
    const card = el('div', { class: 'card' }, [
      el('div', { class: 'row', style: 'justify-content: space-between' }, [el('div', { class: 'result-title', text: a }), el('span', { class: 'chip', text: whenOf(t.startedAt) })]),
      p && p.disclosure.scope && p.disclosure.scope.doc_id ? el('div', { class: 'kv', text: `From this draft, revision ${p.disclosure.scope.revision}${p.disclosure.scope.kind === 'selection' ? ' · your selection “' + p.disclosure.scope.head + '”' : ''}` }) : null,
      fresh.text ? el('div', { class: 'kv ' + (fresh.fresh ? 'ok' : 'warn'), text: fresh.text }) : null,
      el('div', { class: 'kv state ' + (t.status === 'failed' || t.status === 'unknown' ? 'bad' : (t.status === 'done' ? 'good' : 'running')), text: state + (d.progress && !['done', 'complete', 'failed'].includes(t.status) ? ' · ' + d.progress : '') }),
    ]);
    if (t.status === 'unknown') card.appendChild(el('div', { class: 'warn small-text', text: 'The server does not hold this operation any more (it may have restarted). Outcome unknown — nothing was sent again.' }));
    if (t.status === 'failed') card.appendChild(el('div', { class: 'warn small-text', text: 'Failed — ' + (d.error || 'no reason was recorded') + '.' }));
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
      card.appendChild(el('details', {}, [el('summary', { text: 'Details' }), el('div', { class: 'small-text muted', text: `operation ${t.id} · mode ${d.mode || ''} · run ${d.trace_id || (d.groups || []).map(g => g.trace_id).join(', ') || '—'} · snapshot ${d.snapshot_id || '—'}` })]));
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
        el('div', {}, [el('span', { text: t.prepared ? t.prepared.label : t.kind }), el('span', { class: 'muted', text: ' · ' + whenOf(t.startedAt) })]),
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
