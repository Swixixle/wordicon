// workspace-v2 — the document session (slice B; slice C adds structure).
//
// One object owns one open document: what the server committed (revision,
// fingerprint), what this tab has typed since (seq), the one save in
// flight and its request id bound to its exact payload, the local recovery
// envelope, and the conflict state. The editor is an ADAPTER the session
// talks to through a small interface (getText, setText, onEdit,
// getSelection, focus, getScroll/setScroll, getStructure,
// supportsFormatting); the session never reaches into the editor's DOM,
// and the editor never talks to the server.
//
// The semantics are the notebook client's (webapp/index.html, stage B),
// carried over whole: one write in flight per document and newer content
// waits and coalesces; a retry reuses the same request id and payload so a
// lost reply is recognised by the store; a reply for a superseded request
// cannot speak for newer text; 409 keeps both copies and stops automatic
// saving until the owner chooses; a checkpoint reason rides the next save.
//
// Structure (slice C): the exact text and the structure are ONE versioned
// document. A save carries doc_json/doc_schema/projection_version when the
// editor holds structure and either the document is already structured or
// an edit has been made since it was opened — opening a plain document
// never rewrites it (§7). The server validates the structure and computes
// the projection itself; a mismatch is refused, and the refusal is shown.
import { getJSON, postJSON, newId, autoTitle } from './util.js';
import * as recovery from './recovery.js';
import { canonicalString, parsePlain } from '/work/document.js';

const IDLE_MS = 750, MAX_WAIT_MS = 2000, RETRY_MS = [2000, 5000, 15000, 30000];
const SWITCH_WAIT_MS = 4000;     // how long a document switch waits for the save in flight before the envelope carries the rest
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
    this.hooks = hooks;              // onStatus(session), onOpened(session), onConflict(session), onApplicationCommitted(event)
    this.tab = tabId();
    this.blank();
    this.localState = { ok: true, why: '' };
    adapter.onEdit(() => this.noteEdit());
  }

  blank() {
    this.id = ''; this.title = ''; this.title_is_manual = false; this.revision = 0; this.fingerprint = ''; this.origin = '';
    this.seq = 0; this.sentSeq = 0; this.ackSeq = 0; this.savedAt = ''; this.inflight = null; this.timer = null; this.firstEditAt = 0;
    this.status = 'idle'; this.serverError = ''; this.errorClass = ''; this.conflict = null; this.retryTimer = null; this.retries = 0;
    this.lastCheckpointAt = 0; this.pendingReason = ''; this.createdAt = '';
    this.rich = false;               // the committed head carries structure
    this.applications = [];          // {event_id, to_seq}: applied suggestions not yet in a committed revision
    this.editorSession = newId('es_');   // one per opening: a frozen scope names it, so a reopen is never mistaken for the same generation
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

  // The structure a save carries, or null: the editor's structure once the
  // document is structured on the server or an edit has been made here.
  structureToSend() {
    if (!this.adapter.getStructure) return null;
    const s = this.adapter.getStructure();
    if (!s) return null;
    return (this.rich || this.seq > 0) ? s : null;
  }

  // The reference an action freezes: document, committed revision, local
  // generation, and the selection in UTF-16 (the adapter's unit) — the
  // caller converts to code points for the snapshot.
  ref() {
    if (!this.id) return null;
    const sel = this.adapter.getSelection();
    return { id: this.id, seq: this.seq, revision: this.revision, fingerprint: this.fingerprint, editorSession: this.editorSession, selection: sel };
  }

  // ---- the recovery envelope ------------------------------------------------
  async record() {
    if (!this.id) return;
    const env = {
      doc_id: this.id, tab_id: this.tab, editor_session: this.editorSession, seq: this.seq, ack_seq: this.ackSeq, body: this.body(), title: this.title, title_is_manual: this.title_is_manual,
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
    if (this.adapter.isComposing && this.adapter.isComposing()) {   // a composition (IME, dead key) completes first
      if (this.timer) clearTimeout(this.timer);
      this.timer = setTimeout(() => { this.timer = null; this.flush(); }, 300);
      return;
    }
    const seq = this.seq;
    if (seq === this.ackSeq && !this.pendingReason) return;
    this.firstEditAt = 0;
    const payload = { title: this.sentTitle(), title_is_manual: this.title_is_manual, body: this.body(),
                      base_revision: this.revision, base_fingerprint: this.fingerprint, request_id: requestId(),
                      origin: this.origin || 'work' };
    const structure = this.structureToSend();
    if (structure) {
      payload.doc_json = structure;
      payload.doc_schema = this.adapter.docSchema; payload.projection_version = this.adapter.projectionVersion;
    }
    if (this.pendingReason) payload.checkpoint_reason = this.pendingReason;
    else if (this.lastCheckpointAt && Date.now() - this.lastCheckpointAt > INTERVAL_CHECKPOINT_MS) payload.checkpoint_reason = 'interval';
    this.inflight = { request_id: payload.request_id, seq, payload, doc_id: this.id, editor_session: this.editorSession, ctl: (typeof AbortController === 'function') ? new AbortController() : null };
    this.sentSeq = seq;
    await this.record();                                   // the pending request is on disk BEFORE it is sent
    this.status = 'saving'; this.renderStatus();
    await this.send();
  }

  // waits for the save in flight (if any), then flushes what is pending,
  // each wait bounded: a server that does not answer cannot hold the room
  async settle(reason, maxWaitMs = 10000) {
    const until = Date.now() + maxWaitMs;
    while (this.inflight && Date.now() < until) await new Promise(r => setTimeout(r, 50));
    await this.flush(reason);
    while (this.inflight && Date.now() < until) await new Promise(r => setTimeout(r, 50));
    return !this.inflight && this.seq === this.ackSeq;
  }

  // A reply that arrives after this session moved to another document (or
  // was reopened) cannot speak for the editor — but it can still repair the
  // envelope of the document it belongs to: the words that request carried
  // are acknowledged, the head it made is the new base, and anything typed
  // after the send stays unsent against that base. Only the envelope of the
  // same editor session is touched; a reopening has its own.
  async lateAck(inf, d) {
    try {
      const env = await recovery.read(inf.doc_id, this.tab);
      if (!env || env.editor_session !== inf.editor_session || env.base_revision !== inf.payload.base_revision) return;
      const fixed = { ...env, ack_seq: Math.max(env.ack_seq | 0, inf.seq), base_revision: d.revision | 0, base_fingerprint: d.fingerprint || '' };
      if (env.pending && env.pending.request_id === inf.request_id) fixed.pending = null;
      await recovery.write(fixed);
    } catch (e) { /* the envelope stays as it was: unsent words remain unsent */ }
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
    if (this.inflight !== inf) {                            // an older reply cannot speak for newer text
      if (r.ok && d && !d.error && r.status === 200) this.lateAck(inf, d);
      return;
    }
    if (r.status === 409) {
      this.inflight = null; this.retries = 0;
      this.conflict = { head: d.head || null, mine: inf.payload.body, mineStructure: inf.payload.doc_json || null, at: new Date().toISOString() };
      this.status = 'conflict'; this.record(); this.renderStatus();
      if (this.hooks.onConflict) this.hooks.onConflict(this);
      return;
    }
    if (!r.ok || d.error) {
      if (r.status >= 500) { this.retryLater(d.error || ('HTTP ' + r.status)); return; }
      this.inflight = null; this.retries = 0; this.serverError = d.error || ('HTTP ' + r.status); this.errorClass = d.error_class || '';
      this.status = 'failed'; this.record(); this.renderStatus();
      return;
    }
    this.inflight = null; this.retries = 0; this.serverError = ''; this.errorClass = '';
    this.revision = d.revision | 0; this.fingerprint = d.fingerprint || ''; this.savedAt = d.saved_at || '';
    if (d.rich) this.rich = true;
    this.ackSeq = inf.seq;
    if (inf.payload.checkpoint_reason) { this.lastCheckpointAt = Date.now(); if (this.pendingReason === inf.payload.checkpoint_reason) this.pendingReason = ''; }
    if (!this.lastCheckpointAt) this.lastCheckpointAt = Date.now();
    this.saveIdentity(); this.record();
    this.commitApplications(inf.seq, this.revision);
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

  // ---- applied suggestions: local until the save that carries them commits ------
  noteApplication(event, toSeq) {
    if (!(event && event.event_id)) return;
    const to = typeof toSeq === 'number' ? toSeq : this.seq;
    this.applications.push({ event_id: event.event_id, to_seq: to });
    // noted after the save that carried it was already acknowledged (the
    // record's reply came second): that acknowledgment's revision commits it
    if (to <= this.ackSeq) this.commitApplications(this.ackSeq, this.revision);
  }
  commitApplications(ackedSeq, revision) {
    const due = this.applications.filter(a => a.to_seq <= ackedSeq);
    this.applications = this.applications.filter(a => a.to_seq > ackedSeq);
    for (const a of due) {
      postJSON('/api/notebook/documents/' + encodeURIComponent(this.id) + '/applications/' + encodeURIComponent(a.event_id) + '/committed', { committed_revision: revision })
        .then(r => { if (r.ok && this.hooks.onApplicationCommitted) this.hooks.onApplicationCommitted({ event_id: a.event_id, revision }); })
        .catch(() => {});
    }
  }

  // ---- what the header says ----------------------------------------------------
  statusText() {
    const clock = this.savedAt ? new Date(this.savedAt).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : '';
    // a browser that refused the recovery write keeps no copy: the room says
    // so beside every state, never claiming a copy it does not have
    const local = this.localState && this.localState.ok === false ? ' · this browser keeps no recovery copy' : '';
    switch (this.status) {
      case 'idle': return (this.id ? (clock ? 'Saved ' + clock : 'Not saved yet') : 'New') + local;
      case 'pending': return 'Unsaved changes' + local;
      case 'saving': return 'Saving…' + local;
      case 'saved': return (clock ? 'Saved ' + clock : 'Saved') + local;
      case 'local': return 'Saved locally · waiting for the server' + (this.serverError ? ' (' + this.serverError + ')' : '');
      case 'nolocal': return 'Couldn’t save — not on the server, and this browser refused to keep a copy' + (this.localState.why ? ' (' + this.localState.why + ')' : '');
      case 'failed': return 'Couldn’t save: ' + (this.serverError || 'refused');
      case 'conflict': return 'Saved elsewhere since this copy was opened — choose which to keep';
      default: return '';
    }
  }
  renderStatus() { if (this.hooks.onStatus) this.hooks.onStatus(this); }

  // ---- open / new / conflict ways out ------------------------------------------
  async open(id, opts = {}) {
    if (!id) return false;
    if (id === this.id && !opts.reload) return true;
    if (this.id) await this.settle(undefined, SWITCH_WAIT_MS);   // the save in flight lands and the pending words go before the switch
    const r = await getJSON('/api/notebook/documents/' + encodeURIComponent(id));
    if (r.status === 404) return this.openUnsaved(id);
    if (!r.ok || r.data.error) return false;
    const d = r.data;
    let newer = null;
    if (!opts.reload) {
      try {
        const envs = await recovery.forDocument(id);
        // an envelope with edits this tab never got acknowledged, based on the
        // head as it stands; older envelopes (no ack_seq) are judged by their text
        const unsent = e => (e.ack_seq === undefined ? e.body !== d.body : e.seq > e.ack_seq);
        newer = envs.filter(e => e.base_revision === d.revision && !e.abandoned && unsent(e)).sort((a, b) => (b.at || '').localeCompare(a.at || ''))[0] || null;
        // an envelope that holds exactly the head — the same words and the same
        // structure (for a plain head, the structure its words parse to) — has
        // nothing to recover: reopening it must not become a rewrite
        if (newer && newer.body === d.body) {
          const headStructure = d.doc_json ? canonicalString(d.doc_json) : (newer.structure ? canonicalString(parsePlain(d.body)) : null);
          const envStructure = newer.structure ? canonicalString(newer.structure) : null;
          if (headStructure === envStructure) newer = null;
        }
      } catch (e) { /* no recovery store: nothing to recover from */ }
    }
    const localState = this.localState;
    this.blank();
    Object.assign(this, { id: d.doc_id, title: d.title || '', title_is_manual: !!d.title_is_manual, revision: d.revision | 0,
      fingerprint: d.fingerprint || '', savedAt: d.saved_at || '', origin: d.origin || '', status: 'saved', localState,
      lastCheckpointAt: Date.now(), createdAt: d.created_at || '', rich: !!d.doc_json });
    this.saveIdentity();
    if (newer) {
      this.adapter.setText(newer.body, { structure: newer.structure || null });
      this.title = newer.title || this.title; this.title_is_manual = !!newer.title_is_manual;
      try { if (newer.selection) this.adapter.setSelection(newer.selection.start, newer.selection.end, newer.selection.direction); if (newer.scroll && this.adapter.setScroll) this.adapter.setScroll(newer.scroll); } catch (e) {}
      this.seq = 1; this.status = 'pending'; this.record(); this.flush(); this.recovered = true;
    } else {
      this.adapter.setText(d.body, { structure: d.doc_json || null });
      this.recovered = false; this.record();
    }
    this.renderStatus();
    if (this.hooks.onOpened) this.hooks.onOpened(this);
    return true;
  }

  // A document the server never received (the tab closed before its first
  // save landed) lives only in this browser's recovery store: it is reopened
  // from there, whole, and saved.
  async openUnsaved(id) {
    let env = null;
    try {
      const envs = await recovery.forDocument(id);
      env = envs.filter(e => (e.base_revision | 0) === 0 && !e.abandoned && (e.body || (e.structure && e.seq > 0))).sort((a, b) => (b.at || '').localeCompare(a.at || ''))[0] || null;
    } catch (e) { env = null; }
    if (!env) return false;
    const localState = this.localState;
    this.blank();
    Object.assign(this, { id, title: env.title || '', title_is_manual: !!env.title_is_manual, origin: 'work', localState, createdAt: env.at || '' });
    this.saveIdentity();
    this.adapter.setText(env.body || '', { structure: env.structure || null });
    try { if (env.selection) this.adapter.setSelection(env.selection.start, env.selection.end, env.selection.direction); } catch (e) {}
    this.seq = 1; this.status = 'pending'; this.recovered = true; this.record(); this.flush();
    this.renderStatus();
    if (this.hooks.onOpened) this.hooks.onOpened(this);
    return true;
  }

  async newDocument(text = '', origin = 'new') {
    if (this.id && (this.body().trim() || this.revision)) await this.settle('new', SWITCH_WAIT_MS);
    this.adopt(newId('doc_'), origin);
    this.adapter.setText(text || '', { structure: null });
    if (text) { this.seq = 1; this.status = 'pending'; this.record(); await this.flush('open'); }
    else { this.status = 'idle'; this.record(); }
    this.renderStatus();
    if (this.hooks.onOpened) this.hooks.onOpened(this);
    this.adapter.focus();
  }

  // a copy of this document as a new one, structure and all
  async duplicate() {
    const text = this.body(), structure = this.adapter.getStructure ? this.adapter.getStructure() : null;
    if (this.id && (text.trim() || this.revision)) await this.settle('new', SWITCH_WAIT_MS);
    this.adopt(newId('doc_'), 'duplicate');
    this.adapter.setText(text, { structure });
    this.seq = 1; this.status = 'pending'; this.record(); await this.flush('open');
    this.renderStatus();
    if (this.hooks.onOpened) this.hooks.onOpened(this);
  }

  async keepMineAsNew() {
    // the editor already holds mine — text, structure and undo history stay where they are
    const title = this.title, manual = this.title_is_manual;
    this.conflict = null;
    this.adopt(newId('doc_'), 'conflict-copy');
    this.title = title; this.title_is_manual = manual;
    this.seq = 1; this.status = 'pending'; this.record();
    await this.flush('save');
    if (this.hooks.onOpened) this.hooks.onOpened(this);
  }

  async openSaved() {
    const head = this.conflict && this.conflict.head;
    if (!head) return;
    try { await recovery.write({ doc_id: this.id, tab_id: this.tab + '.abandoned.' + Date.now().toString(36), seq: this.seq, ack_seq: this.ackSeq, body: this.body(), title: this.title, title_is_manual: this.title_is_manual, base_revision: this.revision, base_fingerprint: this.fingerprint, structure: this.adapter.getStructure ? this.adapter.getStructure() : null, abandoned: true }); } catch (e) {}
    this.conflict = null;
    this.revision = head.revision | 0; this.fingerprint = head.fingerprint || ''; this.savedAt = head.saved_at || '';
    this.title = head.title || ''; this.title_is_manual = !!head.title_is_manual; this.rich = !!head.doc_json;
    this.adapter.setText(head.body || '', { structure: head.doc_json || null });
    this.seq = 0; this.ackSeq = 0; this.status = 'saved'; this.saveIdentity(); this.record(); this.renderStatus();
  }

  async rename(title) {
    this.title = String(title || '').slice(0, 200); this.title_is_manual = !!this.title.trim();
    this.seq += 1; this.record(); this.renderStatus(); await this.flush('save');
  }

  async checkpoint(reason = 'save') { await this.flush(reason); }

  // A disclosed conversion: CR and CRLF become LF, the document becomes one
  // the structured editor holds, and the save that carries it makes the
  // server keep the plain head as it stood (a 'migration' checkpoint) and
  // record the conversion as an event.
  async convertLineEndings() {
    if (!this.id) return false;
    const text = this.body().replace(/\r\n?/g, '\n');
    this.adapter.setText(text, { structure: null });
    this.seq += 1; this.record(); this.renderStatus();
    await this.flush();
    return true;
  }

  // ---- versions: restore as a new revision; a deliberate plain copy ---------------
  async restoreCheckpoint(checkpointId) {
    if (!this.id) return { ok: false, error: 'no document' };
    const settled = await this.settle();
    if (!settled) return { ok: false, error: 'the draft is not saved yet — nothing was restored' };
    const r = await postJSON('/api/notebook/documents/' + encodeURIComponent(this.id) + '/restore',
      { checkpoint_id: checkpointId, base_revision: this.revision, base_fingerprint: this.fingerprint, request_id: requestId() });
    if (!r.ok) return { ok: false, error: r.data.error || ('HTTP ' + r.status), error_class: r.data.error_class || '' };
    await this.open(this.id, { reload: true });
    return { ok: true, ack: r.data };
  }
  async plainCopy() {
    if (!this.id) return { ok: false, error: 'no document' };
    await this.settle();
    const r = await postJSON('/api/notebook/documents/' + encodeURIComponent(this.id) + '/plain-copy', { request_id: requestId() });
    if (!r.ok) return { ok: false, error: r.data.error || ('HTTP ' + r.status) };
    await this.open(r.data.doc_id);
    return { ok: true, ack: r.data };
  }
}
