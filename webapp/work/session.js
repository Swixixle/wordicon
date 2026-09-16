// workspace-v2 — the document session (slice B; slice C adds structure).
//
// One object owns one open document: what the server committed (revision,
// fingerprint), what this tab has typed since (seq), the one save in
// flight and its request id bound to its exact payload, the local recovery
// envelope, and the conflict state. The editor is an ADAPTER the session
// talks to through a small interface (getText, setText, onEdit,
// getSelection, focus, getScroll/setScroll, supportsFormatting); the
// session never reaches into the editor's DOM, and the editor never talks
// to the server.
//
// The semantics are the notebook client's (webapp/index.html, stage B),
// carried over whole: one write in flight per document and newer content
// waits and coalesces; a retry reuses the same request id and payload so a
// lost reply is recognised by the store; a reply for a superseded request
// cannot speak for newer text; 409 keeps both copies and stops automatic
// saving until the owner chooses; a checkpoint reason rides the next save.
import { getJSON, postJSON, newId, autoTitle } from './util.js';
import * as recovery from './recovery.js';

const IDLE_MS = 750, MAX_WAIT_MS = 2000, RETRY_MS = [2000, 5000, 15000, 30000];
const INTERVAL_CHECKPOINT_MS = 5 * 60 * 1000;
const DOC_KEY = 'nikodemus.work.doc.v1';
const TAB_KEY = 'nikodemus.work.tab.v1';

export function tabId() {
  try {
    let t = sessionStorage.getItem(TAB_KEY);
    if (!t) { t = 'tab_' + Math.random().toString(16).slice(2, 12) + Date.now().toString(16); sessionStorage.setItem(TAB_KEY, t); }
    return t;
  } catch (e) { return 'tab_volatile'; }
}

function requestId() { return 'req_' + newId('').slice(0, 24) + '_' + Date.now().toString(36); }

export class DocumentSession {
  constructor(adapter, hooks = {}) {
    this.adapter = adapter;
    this.hooks = hooks;              // onStatus(session), onOpened(session), onConflict(session)
    this.tab = tabId();
    this.blank();
    this.localState = { ok: true, why: '' };
    adapter.onEdit(() => this.noteEdit());
  }

  blank() {
    this.id = ''; this.title = ''; this.title_is_manual = false; this.revision = 0; this.fingerprint = ''; this.origin = '';
    this.seq = 0; this.sentSeq = 0; this.ackSeq = 0; this.savedAt = ''; this.inflight = null; this.timer = null; this.firstEditAt = 0;
    this.status = 'idle'; this.serverError = ''; this.conflict = null; this.retryTimer = null; this.retries = 0;
    this.lastCheckpointAt = 0; this.pendingReason = ''; this.createdAt = '';
  }

  // ---- identity in this browser -------------------------------------------
  loadIdentity() {
    try { const d = JSON.parse(localStorage.getItem(DOC_KEY) || 'null'); return d && d.id ? d : null; } catch (e) { return null; }
  }
  saveIdentity() {
    try { localStorage.setItem(DOC_KEY, JSON.stringify({ id: this.id, title: this.title, title_is_manual: this.title_is_manual, revision: this.revision, fingerprint: this.fingerprint, savedAt: this.savedAt, origin: this.origin })); } catch (e) {}
  }

  body() { return this.adapter.getText(); }
  displayTitle() { return this.title_is_manual && this.title.trim() ? this.title : autoTitle(this.body()); }
  sentTitle() { return this.title_is_manual ? this.title : ''; }

  // The reference an action freezes: document, committed revision, local
  // generation, and the selection in UTF-16 (the adapter's unit) — the
  // caller converts to code points for the snapshot.
  ref() {
    if (!this.id) return null;
    const sel = this.adapter.getSelection();
    return { id: this.id, seq: this.seq, revision: this.revision, fingerprint: this.fingerprint, selection: sel };
  }

  // ---- the recovery envelope ------------------------------------------------
  async record() {
    if (!this.id) return;
    const env = {
      doc_id: this.id, tab_id: this.tab, seq: this.seq, body: this.body(), title: this.title, title_is_manual: this.title_is_manual,
      base_revision: this.revision, base_fingerprint: this.fingerprint,
      structure: this.adapter.getStructure ? this.adapter.getStructure() : null,
      doc_schema: this.adapter.docSchema || null, projection_version: this.adapter.projectionVersion || null,
      selection: this.adapter.getSelection(), scroll: this.adapter.getScroll ? this.adapter.getScroll() : 0,
      pending: this.inflight ? { request_id: this.inflight.request_id, seq: this.inflight.seq, payload: this.inflight.payload } : null,
      pending_reason: this.pendingReason || '',
    };
    try {
      await recovery.write(env);
      if (!this.localState.ok) { this.localState = { ok: true, why: '' }; this.renderStatus(); }
    } catch (e) {
      // the last complete envelope stays; this one did not land, and the room says so
      if (this.localState.ok) { this.localState = { ok: false, why: String(e && e.message || e) }; this.renderStatus(); }
    }
  }

  // ---- edits ----------------------------------------------------------------
  noteEdit() {
    if (!this.id) this.adopt(newId('doc_'), 'work');
    this.seq += 1;
    if (!this._raf) this._raf = requestAnimationFrame(() => { this._raf = 0; this.record(); this.renderStatus(); });
    if (this.conflict) { this.renderStatus(); return; }
    const now = Date.now();
    if (!this.firstEditAt) this.firstEditAt = now;
    if (this.timer) clearTimeout(this.timer);
    if (now - this.firstEditAt >= MAX_WAIT_MS) { this.timer = null; this.flush(); return; }
    this.timer = setTimeout(() => { this.timer = null; this.flush(); }, IDLE_MS);
    if (this.status !== 'saving' && this.status !== 'local' && this.status !== 'nolocal') { this.status = 'pending'; this.renderStatus(); }
  }

  adopt(id, origin) {
    const localState = this.localState;
    this.blank();
    this.id = id; this.origin = origin || ''; this.localState = localState; this.createdAt = new Date().toISOString();
    this.saveIdentity();
  }

  // ---- saving -----------------------------------------------------------------
  async flush(reason) {
    if (!this.id) return;
    if (reason) this.pendingReason = reason;
    if (this.inflight) return;
    if (this.conflict) return;
    const seq = this.seq;
    if (seq === this.ackSeq && !this.pendingReason) return;
    this.firstEditAt = 0;
    const payload = { title: this.sentTitle(), title_is_manual: this.title_is_manual, body: this.body(),
                      base_revision: this.revision, base_fingerprint: this.fingerprint, request_id: requestId(),
                      origin: this.origin || 'work' };
    if (this.adapter.getStructure && this.adapter.getStructure()) {
      payload.doc_json = this.adapter.getStructure();
      payload.doc_schema = this.adapter.docSchema; payload.projection_version = this.adapter.projectionVersion;
    }
    if (this.pendingReason) payload.checkpoint_reason = this.pendingReason;
    else if (this.lastCheckpointAt && Date.now() - this.lastCheckpointAt > INTERVAL_CHECKPOINT_MS) payload.checkpoint_reason = 'interval';
    this.inflight = { request_id: payload.request_id, seq, payload, ctl: (typeof AbortController === 'function') ? new AbortController() : null };
    this.sentSeq = seq;
    await this.record();                                   // the pending request is on disk BEFORE it is sent
    this.status = 'saving'; this.renderStatus();
    await this.send();
  }

  async send() {
    const inf = this.inflight;
    if (!inf) return;
    let r, d;
    try {
      r = await fetch('/api/notebook/documents/' + encodeURIComponent(this.id), { method: 'PUT', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(inf.payload), signal: inf.ctl ? inf.ctl.signal : undefined });
      d = await r.json();
    } catch (e) {
      if (this.inflight !== inf) return;
      this.retryLater('the server could not be reached');
      return;
    }
    if (this.inflight !== inf) return;                      // an older reply cannot speak for newer text
    if (r.status === 409) {
      this.inflight = null; this.retries = 0;
      this.conflict = { head: d.head || null, mine: inf.payload.body, at: new Date().toISOString() };
      this.status = 'conflict'; this.record(); this.renderStatus();
      if (this.hooks.onConflict) this.hooks.onConflict(this);
      return;
    }
    if (!r.ok || d.error) {
      if (r.status >= 500) { this.retryLater(d.error || ('HTTP ' + r.status)); return; }
      this.inflight = null; this.retries = 0; this.serverError = d.error || ('HTTP ' + r.status);
      this.status = 'failed'; this.record(); this.renderStatus();
      return;
    }
    this.inflight = null; this.retries = 0; this.serverError = '';
    this.revision = d.revision | 0; this.fingerprint = d.fingerprint || ''; this.savedAt = d.saved_at || '';
    this.ackSeq = inf.seq;
    if (inf.payload.checkpoint_reason) { this.lastCheckpointAt = Date.now(); if (this.pendingReason === inf.payload.checkpoint_reason) this.pendingReason = ''; }
    if (!this.lastCheckpointAt) this.lastCheckpointAt = Date.now();
    this.saveIdentity(); this.record();
    if (this.seq !== this.ackSeq || this.pendingReason) { this.status = 'pending'; this.renderStatus(); this.flush(); }
    else { this.status = 'saved'; this.renderStatus(); }
  }

  retryLater(why) {
    this.serverError = why;
    this.status = this.localState.ok ? 'local' : 'nolocal';
    this.renderStatus();
    const wait = RETRY_MS[Math.min(this.retries, RETRY_MS.length - 1)];
    this.retries += 1;
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.retryTimer = setTimeout(() => { this.retryTimer = null; if (this.inflight) this.send(); }, wait);
  }
  retryNow() {
    if (this.retryTimer) { clearTimeout(this.retryTimer); this.retryTimer = null; }
    if (this.inflight) { this.status = 'saving'; this.renderStatus(); this.send(); }
    else { this.status = 'pending'; this.flush('save'); }
  }

  // ---- what the header says ----------------------------------------------------
  statusText() {
    const clock = this.savedAt ? new Date(this.savedAt).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : '';
    switch (this.status) {
      case 'idle': return this.id ? (clock ? 'Saved ' + clock : 'Not saved yet') : 'New';
      case 'pending': return 'Unsaved changes';
      case 'saving': return 'Saving…';
      case 'saved': return clock ? 'Saved ' + clock : 'Saved';
      case 'local': return 'Saved locally · waiting for the server' + (this.serverError ? ' (' + this.serverError + ')' : '');
      case 'nolocal': return 'Couldn’t save — not on the server, and this browser refused to keep a copy' + (this.localState.why ? ' (' + this.localState.why + ')' : '');
      case 'failed': return 'Couldn’t save: ' + (this.serverError || 'refused');
      case 'conflict': return 'Saved elsewhere since this copy was opened — choose which to keep';
      default: return '';
    }
  }
  renderStatus() { if (this.hooks.onStatus) this.hooks.onStatus(this); }

  // ---- open / new / conflict ways out ------------------------------------------
  async open(id) {
    if (!id) return false;
    if (id === this.id) return true;
    await this.flush();
    const r = await getJSON('/api/notebook/documents/' + encodeURIComponent(id));
    if (!r.ok || r.data.error) return false;
    const d = r.data;
    let newer = null;
    try {
      const envs = await recovery.forDocument(id);
      newer = envs.filter(e => e.base_revision === d.revision && e.body !== d.body).sort((a, b) => (b.at || '').localeCompare(a.at || ''))[0] || null;
    } catch (e) { /* no recovery store: nothing to recover from */ }
    const localState = this.localState;
    this.blank();
    Object.assign(this, { id: d.doc_id, title: d.title || '', title_is_manual: !!d.title_is_manual, revision: d.revision | 0,
      fingerprint: d.fingerprint || '', savedAt: d.saved_at || '', origin: d.origin || '', status: 'saved', localState,
      lastCheckpointAt: Date.now(), createdAt: d.created_at || '' });
    this.saveIdentity();
    this.adapter.setText(newer ? newer.body : d.body, { structure: d.doc_json || null });
    if (newer) { this.seq = 1; this.status = 'pending'; this.record(); this.flush(); this.recovered = true; }
    else { this.recovered = false; this.record(); }
    this.renderStatus();
    if (this.hooks.onOpened) this.hooks.onOpened(this);
    return true;
  }

  async newDocument(text = '', origin = 'new') {
    if (this.id && (this.body().trim() || this.revision)) await this.flush('new');
    this.adopt(newId('doc_'), origin);
    this.adapter.setText(text || '', { structure: null });
    if (text) { this.seq = 1; this.status = 'pending'; this.record(); await this.flush('open'); }
    else { this.status = 'idle'; this.record(); }
    this.renderStatus();
    if (this.hooks.onOpened) this.hooks.onOpened(this);
    this.adapter.focus();
  }

  async keepMineAsNew() {
    const mine = this.conflict ? this.conflict.mine : this.body();
    const current = this.body();
    const text = current !== mine && this.seq > this.sentSeq ? current : mine;
    this.conflict = null;
    this.adopt(newId('doc_'), 'conflict-copy');
    this.adapter.setText(text, { structure: null });
    this.seq = 1; this.status = 'pending'; this.record();
    await this.flush('save');
    if (this.hooks.onOpened) this.hooks.onOpened(this);
  }

  async openSaved() {
    const head = this.conflict && this.conflict.head;
    if (!head) return;
    try { await recovery.write({ doc_id: this.id, tab_id: this.tab + '.abandoned.' + Date.now().toString(36), seq: this.seq, body: this.body(), title: this.title, title_is_manual: this.title_is_manual, base_revision: this.revision, base_fingerprint: this.fingerprint, abandoned: true }); } catch (e) {}
    this.conflict = null;
    this.revision = head.revision | 0; this.fingerprint = head.fingerprint || ''; this.savedAt = head.saved_at || '';
    this.title = head.title || ''; this.title_is_manual = !!head.title_is_manual;
    this.adapter.setText(head.body || '', { structure: head.doc_json || null });
    this.seq = 0; this.ackSeq = 0; this.status = 'saved'; this.saveIdentity(); this.record(); this.renderStatus();
  }

  async rename(title) {
    this.title = String(title || '').slice(0, 200); this.title_is_manual = !!this.title.trim();
    this.seq += 1; this.record(); this.renderStatus(); await this.flush('save');
  }

  async checkpoint(reason = 'save') { await this.flush(reason); }
}
