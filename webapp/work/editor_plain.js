// workspace-v2 — the plain editor adapter (slice B; kept in slice C as the
// safe plain-text path for a document that cannot round-trip through the
// structured schema, §7 "Import and round-trip").
//
// A textarea on the blue surface: exact text, the platform's own caret,
// selection, clipboard and undo. It creates its element ONCE and never
// replaces it; hiding the view around it (a panel, a place, the Map) leaves
// the element, its selection and its undo history where they were.
import { el, cpOffset } from './util.js';

export class PlainEditor {
  constructor() {
    this.supportsFormatting = false;
    this.docSchema = null;
    this.projectionVersion = null;
    this.ta = el('textarea', { class: 'plain-editor', spellcheck: 'true', autocorrect: 'off', autocapitalize: 'off',
      placeholder: 'Write here.', 'aria-label': 'Your draft' });
    this.note = el('div', { class: 'editor-note', text: 'Plain text. Formatting arrives with the structured editor; your words are kept exactly.' });
    this.wrap = el('div', { class: 'editor-measure' }, [this.ta, this.note]);
    this.editHandlers = [];
    this.ta.addEventListener('input', () => { for (const h of this.editHandlers) h(); });
  }
  mount(host) { if (!this.wrap.isConnected) host.appendChild(this.wrap); }
  element() { return this.ta; }
  getText() { return this.ta.value; }
  setText(text, opts = {}) {
    // the one moment the value is assigned from outside: a document switch
    this.ta.value = text || '';
    try { this.ta.setSelectionRange(0, 0); } catch (e) {}
    this.ta.scrollTop = 0;
  }
  getStructure() { return null; }
  onEdit(fn) { this.editHandlers.push(fn); }
  getSelection() {
    const s = this.ta.selectionStart, e = this.ta.selectionEnd;
    const text = this.ta.value.slice(s, e);
    return { start: s, end: e, direction: this.ta.selectionDirection || 'none', text,
             cp: { start: cpOffset(this.ta.value, s), end: cpOffset(this.ta.value, e) }, units: 'utf16' };
  }
  setSelection(s, e, dir) { try { this.ta.setSelectionRange(s, e, dir === 'backward' ? 'backward' : 'forward'); } catch (err) {} }
  focus() { try { this.ta.focus({ preventScroll: true }); } catch (e) {} }
  getScroll() { return this.ta.scrollTop; }
  setScroll(v) { this.ta.scrollTop = v | 0; }
  // Where the selection sits, for the popover: the caret rectangle is not
  // available from a textarea, so the popover anchors below the element's
  // visible selection line by a mirror measurement.
  selectionRect() {
    const r = this.ta.getBoundingClientRect();
    const mirror = document.createElement('div');
    const cs = getComputedStyle(this.ta);
    for (const p of ['fontFamily', 'fontSize', 'lineHeight', 'padding', 'border', 'letterSpacing', 'whiteSpace', 'wordWrap', 'boxSizing']) mirror.style[p] = cs[p];
    mirror.style.position = 'absolute'; mirror.style.visibility = 'hidden'; mirror.style.whiteSpace = 'pre-wrap'; mirror.style.wordWrap = 'break-word';
    mirror.style.width = r.width + 'px'; mirror.style.left = '-9999px'; mirror.style.top = '0';
    const before = document.createTextNode(this.ta.value.slice(0, this.ta.selectionEnd));
    const marker = document.createElement('span'); marker.textContent = '​';
    mirror.appendChild(before); mirror.appendChild(marker);
    document.body.appendChild(mirror);
    const mr = marker.getBoundingClientRect(), mm = mirror.getBoundingClientRect();
    document.body.removeChild(mirror);
    return { left: r.left + (mr.left - mm.left), top: r.top + (mr.top - mm.top) - this.ta.scrollTop, height: mr.height || 24 };
  }
}
