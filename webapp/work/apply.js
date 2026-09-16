// workspace-v2 — the guarded application of a textual suggestion (slice C,
// §7 "Selection, analysis snapshots and application").
//
// A result made from a selection carries its frozen scope: the document,
// the editor session and local sequence at the moment of the press, the
// range in code points and the hash of the exact words. Replace or Insert
// below is permitted only while ALL of that still holds: the same document
// in the same editor session at the same local sequence (so the writer's
// own autosave acknowledgment does not make a capture stale, and any edit
// does), and the words at the range hash to the words the result was made
// for. The repeated-phrase trap — the same word standing at the old offsets
// of a changed draft — fails the sequence check before the hash is even
// looked at. A stale result keeps its snapshot; it is applied only to an
// explicitly reconfirmed target: the current selection, chosen again.
//
// The application is one undo step in the editor and one event in the
// record, linked to the immutable result and the document versions; it is
// "applied (unsaved)" until the save that carries it commits.
import { postJSON, el, toast } from './util.js';
import { sha256Hex } from '/work/document.js';

function cpToUtf16(text, cp) {
  let i = 0, n = 0;
  while (n < cp && i < text.length) { const c = text.codePointAt(i); i += c > 0xffff ? 2 : 1; n += 1; }
  return i;
}

export class Applier {
  constructor(session, editor, hooks = {}) {
    this.session = session; this.editor = editor; this.hooks = hooks;   // onRecorded(event)
    this.applied = [];            // {event_id, depth, undone, result}
    if (editor.structured && editor.structured.onHistory) editor.structured.onHistory(h => this.onHistory(h));
  }

  // Why a scope can or cannot be applied to the draft as it stands now.
  async check(scope) {
    const s = this.session;
    if (!scope || scope.kind !== 'selection' || !scope.range) return { ok: false, why: 'this result was not made from a selection, so it has no place to go', retarget: true };
    if (s.id !== scope.doc_id) return { ok: false, why: 'this result is from another document', retarget: false };
    if (s.editorSession !== scope.editor_session || s.seq !== scope.seq) return { ok: false, why: 'the draft changed since this result was made', retarget: true };
    const text = this.editor.getText();
    const start = cpToUtf16(text, scope.range.start), end = cpToUtf16(text, scope.range.end);
    const expect = text.slice(start, end);
    if (!expect || (await sha256Hex(expect)) !== scope.text_sha256) return { ok: false, why: 'the words at that place are not the words this result was made for', retarget: true };
    return { ok: true, start, end, expect };
  }

  // The current selection, chosen again as the target (an explicit reconfirmation).
  currentTarget() {
    const sel = this.editor.getSelection();
    if (!sel || !sel.text || !sel.text.trim()) return null;
    return { start: sel.start, end: sel.end, expect: sel.text, multiBlock: !!sel.multiBlock };
  }

  async apply({ result, text, mode, target, retargeted }) {
    if (this.editor.isComposing && this.editor.isComposing()) return { ok: false, why: 'finish the character being composed first' };
    if (mode === 'replace' && target.multiBlock) return { ok: false, why: 'the selection crosses paragraphs — Replace works within one paragraph; Insert below is available' };
    const fromSeq = this.session.seq, fromRevision = this.session.revision;
    const r = this.editor.applyText({ start: target.start, end: target.end, expect: target.expect, text, mode });
    if (!r.ok) return r;
    const toSeq = this.session.seq;
    const depth = this.editor.structured && this.editor.structured.undoDepth ? this.editor.structured.undoDepth() : 0;
    const rec = await postJSON('/api/notebook/documents/' + encodeURIComponent(this.session.id) + '/applications', {
      kind: mode === 'replace' ? 'replace' : 'insert', result: result, from_revision: fromRevision, from_seq: fromSeq, to_seq: toSeq,
      range: { start: target.start, end: target.end, units: 'utf16' }, retargeted: !!retargeted,
    });
    if (rec.ok && rec.data.event_id) {
      this.session.noteApplication(rec.data, toSeq);
      this.applied.push({ event_id: rec.data.event_id, depth, undone: false, result });
      if (this.hooks.onRecorded) this.hooks.onRecorded(rec.data);
    } else {
      toast('Applied in the draft; the record could not note it (' + (rec.data && rec.data.error || rec.status) + ').');
    }
    return { ok: true, event: rec.ok ? rec.data : null };
  }

  onHistory(h) {
    for (const a of this.applied) {
      if (!h.redo && !a.undone && h.undoDepth < a.depth) { a.undone = true; this.note('undo', a); }
      else if (h.redo && a.undone && h.undoDepth >= a.depth) { a.undone = false; this.note('redo', a); }
    }
  }
  note(kind, a) {
    postJSON('/api/notebook/documents/' + encodeURIComponent(this.session.id) + '/applications', {
      kind, result: { ...a.result, application_event: a.event_id }, from_revision: this.session.revision, from_seq: this.session.seq, to_seq: this.session.seq, range: {},
    }).catch(() => {});
  }

  // The controls a result card offers for one textual suggestion: the two
  // applications while the target holds; otherwise the reason and, where a
  // selection can be chosen again, the reconfirmation.
  controls(t, text) {
    const scope = t.prepared && t.prepared.disclosure && t.prepared.disclosure.scope;
    const result = { operation_id: t.id, snapshot_id: scope && scope.snapshot_id, trace_id: (t.last && t.last.trace_id) || ((t.last && t.last.groups || []).map(g => g.trace_id).filter(Boolean)[0]) || '', text };
    const host = el('div', { class: 'apply' });
    const render = async () => {
      host.textContent = '';
      const c = await this.check(scope);
      if (c.ok) {
        host.appendChild(el('button', { class: 'btn small', type: 'button', text: 'Insert below the selection', onclick: () => this.run(host, { result, text, mode: 'insert', target: c }) }));
        host.appendChild(el('button', { class: 'btn small', type: 'button', text: 'Replace the selection', onclick: () => this.run(host, { result, text, mode: 'replace', target: c }) }));
      } else {
        host.appendChild(el('span', { class: 'muted small-text', text: c.why + '.' }));
        if (c.retarget) {
          host.appendChild(el('button', { class: 'btn small', type: 'button', text: 'Insert below the current selection', title: 'The target is chosen again: whatever is selected now', onclick: () => {
            const target = this.currentTarget(); if (!target) { toast('Select the words first — the target is chosen again from your selection.'); return; }
            this.run(host, { result, text, mode: 'insert', target, retargeted: true });
          } }));
          host.appendChild(el('button', { class: 'btn small', type: 'button', text: 'Replace the current selection', onclick: () => {
            const target = this.currentTarget(); if (!target) { toast('Select the words first — the target is chosen again from your selection.'); return; }
            this.run(host, { result, text, mode: 'replace', target, retargeted: true });
          } }));
        }
      }
    };
    render();
    host.refresh = render;
    return host;
  }
  async run(host, spec) {
    const r = await this.apply(spec);
    if (!r.ok) { toast('Not applied: ' + r.why + '.'); return; }
    host.textContent = '';
    host.appendChild(el('span', { class: 'ok small-text', text: (spec.mode === 'replace' ? 'Replaced' : 'Inserted') + ' in the draft — one undo step (⌘Z). Applied, unsaved until the next save commits.' }));
    this.editor.focus();
  }
}
