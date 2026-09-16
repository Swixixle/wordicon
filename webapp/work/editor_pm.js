// workspace-v2 — the structured editor adapter (slice C). ProseMirror on
// the blue surface, from the pinned local bundle. It speaks the same small
// interface the plain adapter speaks (getText/setText/onEdit/getSelection/
// focus/getScroll/getStructure) plus formatting commands, find/replace and
// the guarded application of a textual suggestion.
//
// The exact text of the document is the projection of the structure
// (document.js — the same function the server computes); the structure
// itself is what the session saves beside it. The view is created once and
// never replaced; a document switch replaces the STATE, not the view, so
// hiding the writing behind a panel or a place leaves the element where it
// was. Undo history is per document session: switching documents starts a
// new history, and a browser restart loses the in-memory stack — the
// checkpoints and the recovery envelope are what persist, and they are not
// called continuous undo.
import { EditorState, EditorView, TextSelection, Slice, Plugin, Decoration, DecorationSet, history, undo, redo, closeHistory, undoDepth, redoDepth,
         keymap, baseKeymap, toggleMark, setBlockType, wrapIn, lift, chainCommands, splitBlock, exitCode, newlineInCode, createParagraphNear, liftEmptyBlock,
         wrapInList, splitListItem, liftListItem, sinkListItem } from '/work/vendor/prosemirror.js';
import { schema, project, canonicalDoc, parsePlain, fromJSON, convertible, positionMap, pmToText, textToPm, cpOffset, SCHEMA_VERSION, PROJECTION_VERSION } from '/work/document.js';
import { el } from './util.js';

// tags the schema holds; anything else in pasted HTML arrives as text, and the paste says so
const HELD_TAGS = new Set(['P', 'H1', 'H2', 'H3', 'UL', 'OL', 'LI', 'BLOCKQUOTE', 'BR', 'STRONG', 'B', 'EM', 'I', 'A', 'SPAN', 'DIV', 'BODY', 'HTML', 'HEAD', 'META', 'STYLE', 'FONT', 'U', 'S', 'SUB', 'SUP', 'SMALL', 'MARK', 'CITE', 'Q', 'ABBR', 'TIME', 'LABEL']);

export class StructuredEditor {
  constructor(hooks = {}) {
    this.hooks = hooks;                       // onNotice(text): a disclosed conversion on paste
    this.supportsFormatting = true;
    this.docSchema = SCHEMA_VERSION;
    this.projectionVersion = PROJECTION_VERSION;
    this.editHandlers = [];
    this.selectionHandlers = [];
    this.historyHandlers = [];
    this.holder = el('div', { class: 'pm-holder' });
    this.wrap = el('div', { class: 'editor-measure' }, [this.holder]);
    this._cache = { doc: null, text: '', map: null };
    const insertHardBreak = (state, dispatch) => { if (dispatch) dispatch(state.tr.replaceSelectionWith(schema.nodes.hard_break.create()).scrollIntoView()); return true; };
    // Tab and Shift-Tab act only inside a list (indent, outdent); anywhere
    // else they are the platform's own — focus moves on, as it must for a
    // keyboard user. No browser tab/history command is taken.
    const keys = keymap({
      'Mod-z': undo, 'Shift-Mod-z': redo, 'Mod-y': redo,
      'Mod-b': toggleMark(schema.marks.strong), 'Mod-i': toggleMark(schema.marks.em),
      // Enter: a new list item; on an empty item, out of the list; otherwise a new paragraph
      'Enter': chainCommands(splitListItem(schema.nodes.list_item), newlineInCode, createParagraphNear, liftEmptyBlock, splitBlock),
      'Shift-Enter': chainCommands(exitCode, insertHardBreak),
      'Tab': sinkListItem(schema.nodes.list_item), 'Shift-Tab': liftListItem(schema.nodes.list_item),
      'Mod-Shift-8': wrapInList(schema.nodes.bullet_list), 'Mod-Shift-9': wrapInList(schema.nodes.ordered_list),
    });
    // the placeholder: a decoration on the one empty paragraph of an empty document, never a node
    const placeholder = new Plugin({ props: { decorations(state) {
      const d = state.doc;
      if (d.childCount === 1 && d.firstChild.type.name === 'paragraph' && d.firstChild.content.size === 0)
        return DecorationSet.create(d, [Decoration.node(0, d.firstChild.nodeSize, { class: 'is-empty', 'data-placeholder': 'Write here.' })]);
      return null;
    } } });
    this.state = EditorState.create({ schema, doc: parsePlain(''), plugins: [history(), keys, keymap(baseKeymap), placeholder] });
    this.view = new EditorView(this.holder, {
      state: this.state,
      attributes: { class: 'pm-editor', spellcheck: 'true', autocorrect: 'off', autocapitalize: 'off', 'aria-label': 'Your draft', role: 'textbox', 'aria-multiline': 'true' },
      dispatchTransaction: tr => {
        const st = this.view.state.apply(tr);
        this.view.updateState(st);
        this.state = st;
        if (tr.docChanged) { this._cache.doc = null; for (const h of this.editHandlers) h(); }
        if (tr.selectionSet || tr.docChanged) for (const h of this.selectionHandlers) h();
        const hist = tr.getMeta('history$');
        if (hist) for (const h of this.historyHandlers) h({ redo: !!hist.redo, undoDepth: undoDepth(st), redoDepth: redoDepth(st) });
      },
      // plain text pastes the way the plain import reads: a blank line is a
      // paragraph break, a single line break a hard break — not one
      // paragraph per line, which is ProseMirror's default
      clipboardTextParser: (text) => { const doc = parsePlain(this.normalizeText(text)); return new Slice(doc.content, 1, 1); },
      transformPastedText: (text) => this.normalizeText(text),
      handlePaste: (view, e) => this.disclosePaste(e),
    });
  }
  mount(host) { if (!this.wrap.isConnected) host.appendChild(this.wrap); }
  element() { return this.view.dom; }
  isComposing() { return this.view.composing; }
  // CRLF and lone CR become LF and other C0 controls (tab excepted) are
  // dropped — a DISCLOSED conversion of pasted text, never of a document
  notice(text) { if (this.hooks.onNotice) this.hooks.onNotice(text); }
  normalizeText(text) {
    const out = String(text || '').replace(/\r\n?/g, '\n').replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, '');
    if (out !== text) this.notice('Pasted text was converted: line endings became line breaks and control characters were dropped. The text you see is the text that is kept.');
    return out;
  }
  disclosePaste(e) {
    const html = e.clipboardData && e.clipboardData.getData('text/html');
    if (!html || e.shiftKey) return false;
    let unheld = [];
    try {
      const dom = new DOMParser().parseFromString(html, 'text/html');
      for (const n of dom.body.querySelectorAll('*')) if (!HELD_TAGS.has(n.tagName)) unheld.push(n.tagName.toLowerCase());
    } catch (err) { unheld = []; }
    if (unheld.length) this.notice('Pasted with the structure this editor holds: ' + Array.from(new Set(unheld)).slice(0, 6).join(', ') + ' arrived as text (paragraphs, headings, lists, quotes, bold, italic and links are kept). ⇧⌘V pastes as plain text.');
    return false;                              // ProseMirror parses it through the schema
  }

  // ---- text and structure --------------------------------------------------
  _ensure() {
    if (this._cache.doc !== this.view.state.doc) { this._cache = { doc: this.view.state.doc, text: project(this.view.state.doc), map: positionMap(this.view.state.doc) }; }
    return this._cache;
  }
  getText() { return this._ensure().text; }
  getStructure() { return canonicalDoc(this.view.state.doc); }
  positionMap() { return this._ensure().map; }
  wordCount() { const t = this.getText().trim(); return t ? t.split(/\s+/).length : 0; }
  setText(text, opts = {}) {
    // a document switch: a new state (and a new history), the same view
    let doc = null;
    if (opts.structure) { try { doc = fromJSON(opts.structure); doc.check(); if (project(doc) !== (text || '')) doc = null; } catch (e) { doc = null; } }
    if (!doc) doc = parsePlain(text || '');
    const st = EditorState.create({ schema, doc, plugins: this.view.state.plugins });
    this.view.updateState(st); this.state = st; this._cache.doc = null;
    for (const h of this.selectionHandlers) h();
  }
  static convertible(text) { return convertible(text); }

  // ---- selection, in the projected text's units ---------------------------------
  onEdit(fn) { this.editHandlers.push(fn); }
  onSelection(fn) { this.selectionHandlers.push(fn); }
  onHistory(fn) { this.historyHandlers.push(fn); }
  getSelection() {
    const { map, text } = this._ensure();
    const sel = this.view.state.selection;
    const a = pmToText(map, sel.anchor), h = pmToText(map, sel.head);
    const start = Math.min(a, h), end = Math.max(a, h);
    return { start, end, direction: h < a ? 'backward' : (h > a ? 'forward' : 'none'), text: text.slice(start, end),
             cp: { start: cpOffset(text, start), end: cpOffset(text, end) }, units: 'utf16', pm: { anchor: sel.anchor, head: sel.head },
             multiBlock: sel.$from.sameParent(sel.$to) === false };
  }
  setSelection(start, end, dir) {
    const { map } = this._ensure();
    const from = textToPm(map, start), to = textToPm(map, end);
    const tr = this.view.state.tr.setSelection(dir === 'backward' ? TextSelection.create(this.view.state.doc, to, from) : TextSelection.create(this.view.state.doc, from, to));
    this.view.dispatch(tr.scrollIntoView());
  }
  focus() { try { this.view.focus(); } catch (e) {} }
  getScroll() { const sc = this.wrap.closest('.work-view'); return sc ? sc.scrollTop : 0; }
  setScroll(v) { const sc = this.wrap.closest('.work-view'); if (sc) sc.scrollTop = v | 0; }
  selectionRect() {
    const sel = this.view.state.selection;
    const c = this.view.coordsAtPos(sel.to);
    return { left: c.left, top: c.top, height: (c.bottom - c.top) || 24 };
  }
  hasFocus() { return this.view.hasFocus(); }

  // ---- formatting commands (the toolbar and the keys share them) -------------------
  command(name, arg) {
    const st = this.view.state, d = this.view.dispatch;
    const run = cmd => cmd(st, d, this.view);
    switch (name) {
      case 'bold': return run(toggleMark(schema.marks.strong));
      case 'italic': return run(toggleMark(schema.marks.em));
      case 'paragraph': return run(setBlockType(schema.nodes.paragraph));
      case 'h1': case 'h2': case 'h3': return run(setBlockType(schema.nodes.heading, { level: +name[1] }));
      case 'bullet': return run(wrapInList(schema.nodes.bullet_list)) || run(liftListItem(schema.nodes.list_item));
      case 'ordered': return run(wrapInList(schema.nodes.ordered_list)) || run(liftListItem(schema.nodes.list_item));
      case 'quote': return run(wrapIn(schema.nodes.blockquote)) || run(lift);
      case 'lift': return run(lift);
      case 'indent': return run(sinkListItem(schema.nodes.list_item));
      case 'outdent': return run(liftListItem(schema.nodes.list_item));
      case 'undo': return run(undo);
      case 'redo': return run(redo);
      case 'link': {
        const href = (arg || '').trim();
        const { from, to, empty } = st.selection;
        if (empty) return false;
        if (!href) { d(st.tr.removeMark(from, to, schema.marks.link)); return true; }
        if (!/^(https?:\/\/|mailto:)[^\s]+$/i.test(href)) return false;
        d(st.tr.addMark(from, to, schema.marks.link.create({ href }))); return true;
      }
      default: return false;
    }
  }
  activeMarks() {
    const st = this.view.state, out = {};
    for (const m of ['strong', 'em', 'link']) {
      const { from, $from, to, empty } = st.selection;
      out[m] = empty ? !!schema.marks[m].isInSet(st.storedMarks || $from.marks()) : st.doc.rangeHasMark(from, to, schema.marks[m]);
    }
    const p = st.selection.$from.parent;
    out.block = p.type.name === 'heading' ? 'h' + p.attrs.level : p.type.name;
    return out;
  }
  undoDepth() { return undoDepth(this.view.state); }
  redoDepth() { return redoDepth(this.view.state); }

  // ---- find and replace over the projected text ---------------------------------------
  findAll(query, opts = {}) {
    if (!query) return [];
    const text = this.getText();
    const hay = opts.caseSensitive ? text : text.toLowerCase(), needle = opts.caseSensitive ? query : query.toLowerCase();
    const out = []; let i = 0;
    while ((i = hay.indexOf(needle, i)) !== -1) { out.push({ start: i, end: i + query.length }); i += Math.max(1, query.length); }
    return out;
  }
  // replace a range of the projected text with plain text, as one history step
  replaceRange(start, end, text) { return this.replaceRanges([{ start, end }], text); }
  // several ranges (in the same projected text) in ONE transaction — one undo step
  replaceRanges(ranges, text) {
    const { map } = this._ensure();
    const inlineOf = () => { const nodes = []; text.split('\n').forEach((line, i) => { if (i) nodes.push(schema.nodes.hard_break.create()); if (line) nodes.push(schema.text(line)); }); return nodes; };
    let tr = closeHistory(this.view.state.tr);
    for (const r of ranges.slice().sort((a, b) => b.start - a.start)) {   // from the end, so earlier positions stay valid
      const from = textToPm(map, r.start), to = textToPm(map, r.end);
      const nodes = inlineOf();
      tr = nodes.length ? tr.replaceWith(from, to, nodes) : tr.delete(from, to);
    }
    this.view.dispatch(tr.scrollIntoView());
    this.view.dispatch(closeHistory(this.view.state.tr));
    return true;
  }

  // ---- the guarded application of a textual suggestion ----------------------------------
  // `target` names the exact range and the exact text expected there; if the
  // text at the range is not what the caller expects, nothing happens. The
  // application is ONE undo step: history is closed before and after.
  applyText({ start, end, expect, text, mode }) {
    const current = this.getText();
    if (current.slice(start, end) !== expect) return { ok: false, why: 'the words at that place are not the words this suggestion was made for' };
    const { map } = this._ensure();
    const from = textToPm(map, start), to = textToPm(map, end);
    let tr = closeHistory(this.view.state.tr);
    if (mode === 'replace') {
      const nodes = []; text.split('\n').forEach((line, i) => { if (i) nodes.push(schema.nodes.hard_break.create()); if (line) nodes.push(schema.text(line)); });
      tr = nodes.length ? tr.replaceWith(from, to, nodes) : tr.delete(from, to);
    } else {
      // insert below: a new paragraph after the block that holds the end of the range
      const $to = this.view.state.doc.resolve(to);
      const after = $to.after($to.depth);
      const doc = parsePlain(text);
      const blocks = []; doc.forEach(b => blocks.push(b));
      tr = tr.insert(after, blocks);
    }
    tr = tr.setMeta('application', true);
    this.view.dispatch(tr);
    this.view.dispatch(closeHistory(this.view.state.tr));
    return { ok: true };
  }
}
