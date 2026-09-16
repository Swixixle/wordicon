// workspace-v2 — the pair of editors behind one adapter (slice C).
//
// The structured editor (ProseMirror, editor_pm.js) is the ordinary way to
// write. The plain editor (a textarea, editor_plain.js) is the safe path
// for a document the structured schema cannot hold exactly — a carriage
// return or a control character in the text — so nothing is ever rewritten
// in silence (§7 "Import and round-trip"). Both are created once and stay
// mounted; a document switch chooses which one is active and shows it. The
// session talks to this object through the same small interface the
// adapters speak; it never needs to know which one is answering.
import { StructuredEditor } from './editor_pm.js';
import { PlainEditor } from './editor_plain.js';
import { convertible } from '/work/document.js';

export class EditorSwitch {
  constructor(hooks = {}) {
    this.hooks = hooks;                        // onSwitch(mode, why)
    this.structured = new StructuredEditor({ onNotice: t => { if (hooks.onNotice) hooks.onNotice(t); } });
    this.plain = new PlainEditor();
    this.active = this.structured;
    this.why = '';
    this.editHandlers = []; this.selectionHandlers = [];
    for (const ed of [this.structured, this.plain]) {
      ed.onEdit(() => { if (ed === this.active) for (const h of this.editHandlers) h(); });
      ed.onSelection(() => { if (ed === this.active) for (const h of this.selectionHandlers) h(); });
    }
  }
  mount(host) { this.structured.mount(host); this.plain.mount(host); this._show(); }
  _show() {
    this.structured.wrap.hidden = this.active !== this.structured;
    this.plain.wrap.hidden = this.active !== this.plain;
  }
  mode() { return this.active === this.structured ? 'structured' : 'plain'; }

  // the interface the session and the shell use
  get supportsFormatting() { return this.active.supportsFormatting; }
  get docSchema() { return this.active.docSchema; }
  get projectionVersion() { return this.active.projectionVersion; }
  element() { return this.active.element(); }
  onEdit(fn) { this.editHandlers.push(fn); }
  onSelection(fn) { this.selectionHandlers.push(fn); }
  getText() { return this.active.getText(); }
  getStructure() { return this.active.getStructure ? this.active.getStructure() : null; }
  getSelection() { return this.active.getSelection(); }
  setSelection(s, e, dir) { return this.active.setSelection(s, e, dir); }
  focus() { return this.active.focus(); }
  hasFocus() { return this.active.hasFocus ? this.active.hasFocus() : document.activeElement === this.active.element(); }
  isComposing() { return this.active.isComposing ? this.active.isComposing() : false; }
  getScroll() { return this.active.getScroll(); }
  setScroll(v) { return this.active.setScroll(v); }
  selectionRect() { return this.active.selectionRect(); }
  wordCount() { const t = this.getText().trim(); return t ? t.split(/\s+/).length : 0; }
  findAll(q, o) { return this.active.findAll(q, o); }
  replaceRange(s, e, t) { return this.active.replaceRange(s, e, t); }
  replaceRanges(ranges, t) { return this.active.replaceRanges(ranges, t); }
  applyText(target) { return this.active.applyText ? this.active.applyText(target) : { ok: false, why: 'the plain editor applies nothing by itself — copy the words in' }; }
  command(name, arg) { return this.active.command ? this.active.command(name, arg) : false; }
  activeMarks() { return this.active.activeMarks ? this.active.activeMarks() : { block: 'plain' }; }

  // A document switch: structure present → structured; plain text the
  // schema holds exactly → structured (paragraphs from the plain import,
  // persisted only on an actual edit, by the session); anything else →
  // the plain editor, with the reason shown.
  setText(text, opts = {}) {
    let next = this.structured, why = '';
    if (!opts.structure) { const c = convertible(text || ''); if (!c.ok) { next = this.plain; why = c.why; } }
    const switched = next !== this.active;
    this.active = next; this.why = why;
    this._show();
    if (next === this.plain) {
      // carriage returns: a textarea cannot hold them, so the document is
      // shown read-only and kept exactly until a disclosed conversion;
      // other control characters a textarea keeps, so the text is editable
      const cr = /\r/.test(text || '');
      this.plain.setText(text, { readOnly: cr });
      if (cr) this.plain.setNote('Plain text, kept exactly and read-only: this document has carriage returns (CR or CRLF line endings), which neither editor can hold without changing them. Convert them to plain line breaks (LF) to edit here — the document as it stands is kept as a version first.',
                                 { label: 'Convert line endings and edit', onClick: () => { if (this.hooks.onConvert) this.hooks.onConvert(); } });
      else this.plain.setNote('Plain text, kept exactly. The structured editor cannot hold this document (' + why + '), so formatting is off for it.');
    } else {
      this.active.setText(text, opts);
    }
    if (this.hooks.onSwitch) this.hooks.onSwitch(this.mode(), why, switched);
  }
  isReadOnly() { return this.active === this.plain && this.plain.isReadOnly(); }
}
