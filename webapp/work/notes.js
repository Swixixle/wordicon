// workspace-v2 slice J — the owner's own notes, beside the work.
//
// What this surface is: a place to write HIS prose while reading something
// else, one scratchpad per document. It is not the revision-notes list: that
// holds carries, which are the model's words travelling under "may be useful
// while revising". The two are rendered in separate sections with separate
// wording because the record keeps them separate.
//
// Three promises the code has to keep, in this order:
//   1. Words typed here are in this browser BEFORE any server acknowledgment
//      (a note envelope per note per tab — recovery.js), so a crash, a
//      reload or a refused save never costs a sentence.
//   2. A failed save leaves the text where it is, says so plainly, and
//      retries under the SAME request id, so a retry cannot become a
//      duplicate note.
//   3. Another tab writing the same note cannot overwrite these words: the
//      envelope key carries the tab id, and the server refuses an edit made
//      against a revision that has moved, handing back both bodies.
//
// The compose textarea is created ONCE and never recreated. Re-rendering the
// panel re-attaches the same element, so the caret, the selection and the
// browser's own undo stack (⌘Z inside the box, scoped to the box) survive
// every tab switch, panel toggle and list refresh.
import { getJSON, postJSON, el, whenOf, requestKey } from './util.js';
import * as recovery from './recovery.js';

const SAVE_MS = 900;            // quiet enough to be a save, short enough to be a habit
const PREVIEW_CHARS = 140;
const COMPOSE = 'new:';

function previewOf(body) {
  const one = String(body || '').replace(/\s+/g, ' ').trim();
  return one.length > PREVIEW_CHARS ? one.slice(0, PREVIEW_CHARS) + '…' : one;
}

export class Notes {
  constructor(session, hooks = {}) {
    this.session = session;
    this.hooks = hooks;                 // onCount(n)
    this.docId = '';
    this.items = [];                    // the server's notes for this document, newest first
    this.listError = '';
    this.editors = new Map();           // scope -> editor state
    this.expanded = new Set();          // note ids open for editing
    this.host = null;
    this.composeEl = null;
    this.loaded = false;
  }

  tabId() { return this.session.tab; }
  composeScope() { return COMPOSE + (this.docId || ''); }

  editor(scope, seed = {}) {
    let e = this.editors.get(scope);
    if (!e) {
      e = { scope, noteId: '', body: '', baseRevision: 0, status: 'idle', error: '',
            conflict: null, requestId: '', timer: 0, inflight: false, sel: null, ...seed };
      this.editors.set(scope, e);
    }
    return e;
  }

  count() { return this.items.length; }

  // ---- the document this surface belongs beside -------------------------------
  // Switching documents flushes what is unsent FIRST. If that save fails the
  // words stay in this browser under the old document's key and come back
  // when he returns to it — they are never carried into the new document.
  async setDocument(docId) {
    const next = String(docId || '');
    if (next === this.docId) return;
    if (this.docId) await this.flushAll({ quiet: true });
    this.docId = next;
    this.items = [];
    this.listError = '';
    this.expanded.clear();
    this._actsKey = null; this._listKey = null;
    this.loaded = false;
    const c = this.editor(this.composeScope());
    if (this.composeEl) this.composeEl.value = c.body || '';
    await this.load();
  }

  async load() {
    if (!this.docId) { this.loaded = true; this.paint(); return; }
    let r;
    try { r = await getJSON('/api/notes?doc_id=' + encodeURIComponent(this.docId)); }
    catch (err) { r = { ok: false, status: 0, data: { error: String(err && err.message || err) } }; }
    if (!r.ok) {
      this.listError = 'Your notes for this document could not be listed. Nothing was lost; this is a read.';
      this.items = [];
    } else {
      this.listError = '';
      this.items = (r.data.notes || []);
    }
    await this.restoreUnsent();
    this.loaded = true;
    if (this.hooks.onCount) this.hooks.onCount(this.count());
    this.paint();
  }

  // Words this tab typed and the server never acknowledged, put back exactly
  // where they were typed. An envelope whose body the server already holds is
  // not a recovery and is ignored rather than re-announced.
  async restoreUnsent() {
    if (!recovery.available()) return;
    let envs = [];
    try { envs = await recovery.notesForDocument(this.docId); } catch (e) { return; }
    for (const env of envs) {
      if (env.tab_id !== this.tabId()) continue;          // another tab's copy is its own; never touched here
      if (env.acked) continue;
      const onServer = env.note_id ? (this.items.find(n => n.note_id === env.note_id) || null) : null;
      if (onServer && onServer.body === env.body) continue;
      const e = this.editor(env.scope);
      e.body = env.body || '';
      e.noteId = env.note_id || '';
      e.baseRevision = env.base_revision || 0;
      e.requestId = env.request_id || '';
      e.status = 'local';
      e.error = '';
      if (e.noteId) this.expanded.add(e.noteId);
      if (env.scope === this.composeScope() && this.composeEl) this.composeEl.value = e.body;
    }
  }

  // ---- typing ------------------------------------------------------------------
  async onInput(scope, value, selStart, selEnd) {
    const e = this.editor(scope);
    if (e.body !== value) e.requestId = '';              // new words are a new write, never a retry of the old one
    e.body = value;
    e.sel = (selStart === undefined) ? e.sel : { start: selStart, end: selEnd };
    e.conflict = null;
    e.status = 'local';
    e.error = '';
    let kept = true;
    try { await this.keep(e); } catch (err) { kept = false; }
    if (!kept) { e.status = 'nolocal'; }
    this.paintStatus(e);
    clearTimeout(e.timer);
    e.timer = setTimeout(() => { this.flush(scope); }, SAVE_MS);
  }

  async keep(e) {
    if (!recovery.available()) throw new Error('no local store');
    await recovery.writeNote({ scope: e.scope, tab_id: this.tabId(), doc_id: this.docId,
                               note_id: e.noteId || '', body: e.body,
                               base_revision: e.baseRevision || 0,
                               request_id: e.requestId || '', acked: false });
  }

  async markKept(e) {
    if (!recovery.available()) return;
    try {
      await recovery.writeNote({ scope: e.scope, tab_id: this.tabId(), doc_id: this.docId,
                                 note_id: e.noteId || '', body: e.body,
                                 base_revision: e.baseRevision || 0, request_id: '', acked: true });
    } catch (err) { /* the server has it; a local bookkeeping failure costs nothing */ }
  }

  // ---- saving ------------------------------------------------------------------
  async flushAll(opts = {}) {
    for (const scope of Array.from(this.editors.keys())) {
      const e = this.editors.get(scope);
      if (!e) continue;
      clearTimeout(e.timer);
      if (e.status === 'local' || e.status === 'failed' || e.status === 'nolocal') await this.flush(scope, opts);
    }
  }

  async flush(scope, opts = {}) {
    const e = this.editors.get(scope);
    if (!e || e.inflight) return;
    clearTimeout(e.timer);
    const body = e.body;
    if (!body.trim() && !e.noteId) { e.status = 'idle'; this.paintStatus(e); return; }
    if (e.noteId && e.lastSaved === body) { e.status = 'saved'; this.paintStatus(e); return; }
    if (!e.requestId) { e.requestId = requestKey(); await this.keep(e).catch(() => {}); }
    e.inflight = true; e.status = 'saving'; e.error = ''; this.paintStatus(e);
    let r;
    try {
      if (e.noteId) {
        r = await postJSON('/api/notes/' + encodeURIComponent(e.noteId),
                           { body, base_revision: e.baseRevision, request_id: e.requestId }, 'PUT');
      } else {
        r = await postJSON('/api/notes', { doc_id: this.docId, body, request_id: e.requestId, tab_id: this.tabId() });
      }
    } catch (err) {
      // the request never completed: the words stay, the request id stays, and
      // Retry re-sends the SAME id, so a save that actually landed cannot
      // become a second note
      r = { ok: false, status: 0, data: { error: 'the request did not complete (' + String(err && err.message || err) + ').' } };
    }
    e.inflight = false;
    if (r.ok && r.data && r.data.note) {
      const n = r.data.note;
      const wasNew = !e.noteId;
      e.noteId = n.note_id; e.baseRevision = n.revision; e.lastSaved = n.body;
      e.status = 'saved'; e.error = ''; e.conflict = null; e.requestId = '';
      await this.markKept(e);
      this.mergeItem(n, wasNew);
      if (this.listError) { this.listError = ''; await this.load(); return; }   // the server is answering again
      if (!opts.quiet) this.paint(); else this.paintStatus(e);
      if (this.hooks.onCount) this.hooks.onCount(this.count());
      return;
    }
    const d = (r && r.data) || {};
    if (r && r.status === 409 && d.code === 'conflict') {
      e.status = 'conflict';
      e.conflict = { body_here: d.body_here || '', revision_here: d.revision_here || 0 };
      e.error = 'This note changed somewhere else while you were writing. Nothing was overwritten.';
    } else {
      e.status = 'failed';
      e.error = (d.error || (r && r.error) || 'the save did not reach the server') + '';
    }
    await this.keep(e).catch(() => {});   // the words AND the id this retry must reuse
    if (!opts.quiet) this.paint(); else this.paintStatus(e);
  }

  mergeItem(n, wasNew) {
    const i = this.items.findIndex(x => x.note_id === n.note_id);
    if (i >= 0) this.items[i] = n; else this.items.unshift(n);
    this.items.sort((a, b) => String(b.updated_at || b.at).localeCompare(String(a.updated_at || a.at)));
    if (wasNew) this.rebuild = true;
  }

  // The conflict choices. Neither one loses words: keeping his makes a NEW
  // note, so the other tab's version stays exactly where it is.
  async keepMineAsNew(scope) {
    const e = this.editor(scope);
    const body = e.body;
    e.noteId = ''; e.baseRevision = 0; e.requestId = requestKey(); e.conflict = null;
    e.body = body;
    await this.flush(scope);
  }

  async takeTheirs(scope) {
    const e = this.editor(scope);
    if (!e.conflict) return;
    e.body = e.conflict.body_here;
    e.baseRevision = e.conflict.revision_here;
    e.lastSaved = e.conflict.body_here;
    e.status = 'saved'; e.conflict = null; e.error = ''; e.requestId = '';
    await this.markKept(e);
    if (e.scope === this.composeScope() && this.composeEl) this.composeEl.value = e.body;
    this.paint();
  }

  async newNote() {
    const scope = this.composeScope();
    await this.flush(scope);
    const e = this.editor(scope);
    if (e.status === 'failed' || e.status === 'conflict') return;   // never clear a box whose words are not safe
    await recovery.removeNote(scope, this.tabId()).catch(() => {});
    this.editors.delete(scope);
    this._actsKey = null; this._listKey = null;
    if (this.composeEl) { this.composeEl.value = ''; this.composeEl.focus(); }
    this.paint();
  }

  async remove(noteId) {
    let r;
    try { r = await postJSON('/api/notes/' + encodeURIComponent(noteId), {}, 'DELETE'); }
    catch (err) { r = { ok: false, status: 0, data: { error: String(err && err.message || err) } }; }
    if (!r.ok) { this.listError = 'That note could not be taken out of the list. It is unchanged.'; this.paint(); return; }
    this.items = this.items.filter(n => n.note_id !== noteId);
    this.expanded.delete(noteId);
    const c = this.editor(this.composeScope());
    if (c.noteId === noteId) { this.editors.delete(this.composeScope()); if (this.composeEl) this.composeEl.value = ''; }
    this.editors.delete(noteId);
    await recovery.removeNote(noteId, this.tabId()).catch(() => {});
    this.rebuild = true;
    if (this.hooks.onCount) this.hooks.onCount(this.count());
    this.paint();
  }

  // ---- rendering ----------------------------------------------------------------
  // The host element is built once and re-attached. Nothing here recreates the
  // compose textarea, so its caret and its undo stack outlive every re-render.
  render(parent) {
    if (!this.host) this.build();
    parent.appendChild(this.host);
    if (!this.loaded) this.load();
    else if (this.rebuild) this.paint();
  }

  build() {
    this.host = el('div', { class: 'notes-mine' });
    this.composeEl = el('textarea', {
      class: 'note-box', id: 'note-compose', rows: '4',
      placeholder: 'Write a note beside what you are reading. Your words, not the model’s.',
      'aria-label': 'Write a note',
    });
    this.composeEl.addEventListener('input', () => {
      this.onInput(this.composeScope(), this.composeEl.value, this.composeEl.selectionStart, this.composeEl.selectionEnd);
    });
    this.composeEl.addEventListener('blur', () => {
      const e = this.editor(this.composeScope());
      if (e.status === 'local') this.flush(this.composeScope());
      else if (this.rebuild) setTimeout(() => { if (!this.typing()) this.paint(); }, 0);
    });
    this.composeStatus = el('div', { class: 'note-status muted small-text' });
    this.composeActs = el('div', { class: 'row note-acts' });
    this.list = el('div', { class: 'note-list' });
    this.head = el('div', {});
    this.host.append(this.head, this.composeEl, this.composeStatus, this.composeActs, this.list);
    this.paint();
  }

  statusLine(e) {
    if (e.status === 'saving') return 'Saving…';
    if (e.status === 'saved') return 'Saved to the record.';
    if (e.status === 'local') return 'In this browser — not saved to the record yet.';
    if (e.status === 'nolocal') return 'This browser refused to keep a copy. Your words are on this screen only until they save.';
    if (e.status === 'failed') return 'Not saved: ' + e.error + ' Your words are here — press Retry.';
    if (e.status === 'conflict') return e.error;
    return '';
  }

  statusClass(e) {
    return (e.status === 'failed' || e.status === 'conflict' || e.status === 'nolocal') ? 'note-status warn' : 'note-status muted small-text';
  }

  paintStatus(e) {
    if (e.scope === this.composeScope() && this.composeStatus) {
      this.composeStatus.textContent = this.statusLine(e);
      this.composeStatus.className = this.statusClass(e);
      this.paintActs(e);
      return;
    }
    const node = this.list && this.list.querySelector('[data-status-for="' + e.scope + '"]');
    if (node) { node.textContent = this.statusLine(e); node.className = this.statusClass(e); }
  }

  // A control is only rebuilt when what it should say has changed. Rebuilding
  // it unconditionally replaced the button under a click that was already in
  // flight (WebKit ordered the blur repaint before the click dispatch, so
  // “Start another note” silently did nothing there).
  actsKey(e) {
    return [e.status, e.body.trim() ? '1' : '0', e.conflict ? e.conflict.revision_here : ''].join('|');
  }

  paintActs(e) {
    if (!this.composeActs) return;
    const key = this.actsKey(e);
    if (this._actsKey === key) return;
    this._actsKey = key;
    this.composeActs.textContent = '';
    if (e.status === 'failed') this.composeActs.appendChild(el('button', { class: 'btn small', type: 'button', text: 'Retry', onclick: () => this.flush(e.scope) }));
    if (e.status === 'conflict') {
      this.composeActs.appendChild(el('button', { class: 'btn small', type: 'button', text: 'Keep mine as a new note', onclick: () => this.keepMineAsNew(e.scope) }));
      this.composeActs.appendChild(el('button', { class: 'btn small', type: 'button', text: 'Take the other version', onclick: () => this.takeTheirs(e.scope) }));
      this.composeActs.appendChild(el('div', { class: 'kv', text: 'The other version reads: “' + previewOf(e.conflict ? e.conflict.body_here : '') + '”' }));
    }
    if (e.body.trim() && (e.status === 'saved' || e.status === 'local')) {
      this.composeActs.appendChild(el('button', { class: 'btn small', type: 'button', text: 'Start another note', onclick: () => this.newNote() }));
    }
  }

  // True while the person is typing in any note box on this surface. A
  // rebuild then would destroy the live element under their hands.
  typing() {
    const a = document.activeElement;
    return !!(a && a.tagName === 'TEXTAREA' && this.host && this.host.contains(a));
  }

  paint() {
    if (!this.host) return;
    if (this.typing()) {                       // defer: repaint the statuses, keep every live box
      this.rebuild = true;
      for (const e of this.editors.values()) this.paintStatus(e);
      return;
    }
    this.rebuild = false;
    const c = this.editor(this.composeScope());
    this.head.textContent = '';
    this.head.appendChild(el('div', { class: 'lbl', text: 'Your notes' }));
    this.head.appendChild(el('div', { class: 'muted small-text', text: this.docId
      ? 'Your own words, kept beside this document. Nothing here is sent to a model, and nothing here is a result.'
      : 'Open or start a document and your notes live beside it.' }));
    if (this.listError) this.head.appendChild(el('div', { class: 'warn', text: this.listError }));
    this.composeEl.disabled = !this.docId;
    if (this.composeEl.value !== c.body && document.activeElement !== this.composeEl) this.composeEl.value = c.body;
    this.composeStatus.textContent = this.statusLine(c);
    this.composeStatus.className = this.statusClass(c);
    this.paintActs(c);

    const others = this.items.filter(n => n.note_id !== c.noteId);
    const listKey = JSON.stringify([others.map(n => [n.note_id, n.revision, n.updated_at]), Array.from(this.expanded),
                                    others.map(n => (this.editors.get(n.note_id) || {}).status || 'saved')]);
    if (this._listKey === listKey) return;
    this._listKey = listKey;
    this.list.textContent = '';
    if (!others.length) {
      this.list.appendChild(el('div', { class: 'muted small-text', text: this.items.length ? '' : 'No notes on this document yet.' }));
      return;
    }
    this.list.appendChild(el('div', { class: 'lbl small-text', text: 'Earlier notes · ' + others.length }));
    for (const n of others) {
      const open = this.expanded.has(n.note_id);
      const e = this.editor(n.note_id, { noteId: n.note_id, body: n.body, baseRevision: n.revision, lastSaved: n.body, status: 'saved' });
      if ((e.status === 'saved' || e.status === 'idle') && e.body !== n.body) {
        e.noteId = n.note_id; e.body = n.body; e.baseRevision = n.revision; e.lastSaved = n.body; e.status = 'saved';
      }
      const chip = el('div', { class: 'card note-chip' + (open ? ' open' : '') });
      chip.appendChild(el('button', {
        class: 'linkish note-chip-head', type: 'button',
        'aria-expanded': String(open),
        text: (open ? '▾ ' : '▸ ') + (previewOf(e.body) || '(empty)'),
        onclick: () => { if (open) this.expanded.delete(n.note_id); else this.expanded.add(n.note_id); this.paint(); },
      }));
      chip.appendChild(el('div', { class: 'muted small-text', text: 'yours · ' + whenOf(n.updated_at || n.at) + (n.revision > 1 ? ' · ' + n.revision + ' writes' : '') }));
      if (open) {
        const ta = el('textarea', { class: 'note-box', rows: '4', 'aria-label': 'Edit this note' });
        ta.value = e.body;
        ta.addEventListener('input', () => this.onInput(n.note_id, ta.value, ta.selectionStart, ta.selectionEnd));
        ta.addEventListener('blur', () => {
          if (this.editor(n.note_id).status === 'local') this.flush(n.note_id);
          else if (this.rebuild) setTimeout(() => { if (!this.typing()) this.paint(); }, 0);
        });
        chip.appendChild(ta);
        chip.appendChild(el('div', { class: this.statusClass(e), 'data-status-for': n.note_id, text: this.statusLine(e) }));
        const acts = el('div', { class: 'row note-acts' });
        if (e.status === 'failed') acts.appendChild(el('button', { class: 'btn small', type: 'button', text: 'Retry', onclick: () => this.flush(n.note_id) }));
        if (e.status === 'conflict') {
          acts.appendChild(el('button', { class: 'btn small', type: 'button', text: 'Keep mine as a new note', onclick: () => this.keepMineAsNew(n.note_id) }));
          acts.appendChild(el('button', { class: 'btn small', type: 'button', text: 'Take the other version', onclick: () => this.takeTheirs(n.note_id) }));
        }
        acts.appendChild(el('button', { class: 'btn small', type: 'button', text: 'Take out of the list', onclick: () => this.remove(n.note_id) }));
        chip.appendChild(acts);
        if (e.status === 'conflict' && e.conflict) chip.appendChild(el('div', { class: 'kv', text: 'The other version reads: “' + previewOf(e.conflict.body_here) + '”' }));
      }
      this.list.appendChild(chip);
    }
  }
}
