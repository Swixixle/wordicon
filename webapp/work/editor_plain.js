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
    this.noteText = el('span', { text: 'Plain text, kept exactly.' });
    this.noteAction = el('button', { class: 'btn small', type: 'button', text: '', style: 'margin-left:10px' });
    this.noteAction.hidden = true;
    this.note = el('div', { class: 'editor-note' }, [this.noteText, this.noteAction]);
    this.wrap = el('div', { class: 'editor-measure' }, [this.ta, this.note]);
    this.exact = null;                        // the exact body while read-only (a textarea normalizes CR/CRLF to LF)
    this.editHandlers = []; this.selectionHandlers = [];
    this.composing = false;
    this.ta.addEventListener('input', () => { for (const h of this.editHandlers) h(); });
    this.ta.addEventListener('compositionstart', () => { this.composing = true; });
    this.ta.addEventListener('compositionend', () => { this.composing = false; });
    for (const ev of ['select', 'keyup', 'mouseup', 'input']) this.ta.addEventListener(ev, () => { for (const h of this.selectionHandlers) h(); });
  }
  mount(host) { if (!this.wrap.isConnected) host.appendChild(this.wrap); }
  element() { return this.ta; }
  setNote(text, action) {
    this.noteText.textContent = text;
    if (action) { this.noteAction.textContent = action.label; this.noteAction.onclick = action.onClick; this.noteAction.hidden = false; }
    else { this.noteAction.hidden = true; this.noteAction.onclick = null; }
  }
  // Read-only keeps the exact body: a textarea's value normalizes CR and
  // CRLF to LF, so a document with carriage returns is shown, not edited,
  // until its line endings are converted by a disclosed choice.
  setReadOnly(on) { this.ta.readOnly = !!on; this.ta.classList.toggle('readonly', !!on); }
  isReadOnly() { return this.ta.readOnly; }
  isComposing() { return this.composing; }
  hasFocus() { return document.activeElement === this.ta; }
  getText() { return this.exact !== null ? this.exact : this.ta.value; }
  setText(text, opts = {}) {
    // the one moment the value is assigned from outside: a document switch
    this.ta.value = text || '';
    this.exact = (opts.readOnly && this.ta.value !== (text || '')) ? (text || '') : null;
    this.setReadOnly(!!opts.readOnly);
    try { this.ta.setSelectionRange(0, 0); } catch (e) {}
    this.ta.scrollTop = 0;
  }
  getStructure() { return null; }
  onEdit(fn) { this.editHandlers.push(fn); }
  onSelection(fn) { this.selectionHandlers.push(fn); }
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
  wordCount() { const t = this.ta.value.trim(); return t ? t.split(/\s+/).length : 0; }
  findAll(query, opts = {}) {
    if (!query) return [];
    const text = this.ta.value;
    const hay = opts.caseSensitive ? text : text.toLowerCase(), needle = opts.caseSensitive ? query : query.toLowerCase();
    const out = []; let i = 0;
    while ((i = hay.indexOf(needle, i)) !== -1) { out.push({ start: i, end: i + query.length }); i += Math.max(1, query.length); }
    return out;
  }
  replaceRange(start, end, text) {
    // setRangeText keeps the platform's undo stack where the browser supports it
    try { this.ta.setSelectionRange(start, end); this.ta.setRangeText(text, start, end, 'end'); }
    catch (e) { this.ta.value = this.ta.value.slice(0, start) + text + this.ta.value.slice(end); }
    this.ta.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  }
  replaceRanges(ranges, text) {
    let v = this.ta.value;
    for (const r of ranges.slice().sort((a, b) => b.start - a.start)) v = v.slice(0, r.start) + text + v.slice(r.end);
    this.ta.value = v;                        // one assignment: the platform's undo may not reach it, and the note says so
    this.ta.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  }
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
