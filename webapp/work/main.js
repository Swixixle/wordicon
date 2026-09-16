// workspace-v2 — the shell's bootstrap (slice B; slice C wires the two
// editors, the formatting bar, find and replace, versions and the guarded
// application of a suggestion). Wires the modules; holds no business logic
// of its own.
import { el, toast, getJSON, whenOf } from './util.js';
import { DocumentSession } from './session.js';
import { EditorSwitch } from './editors.js';
import { Layout } from './layout.js';
import { Places } from './places.js';
import { Results } from './results.js';
import { Actions } from './actions.js';
import { YourWork } from './yourwork.js';
import { Investigate } from './investigate.js';
import { Applier } from './apply.js';
import { toMarkdown, toHTML } from '/work/document.js';

const shell = document.getElementById('shell');
const editor = new EditorSwitch({ onNotice: t => toast(t, 6000), onSwitch: () => { renderToolbar(); },
  onConvert: async () => { if (await session.convertLineEndings()) toast('Line endings converted to LF; the document as it stood is kept as a version. You can edit and format it now.', 6000); } });
editor.mount(document.getElementById('editor-host'));

const session = new DocumentSession(editor, {
  onStatus: s => renderHeader(s),
  onOpened: s => { renderHeader(s); showPage('work'); renderToolbar(); if (s.recovered) toast('Opened with unsent changes recovered from this browser (newer than the saved copy).'); },
  onConflict: s => renderConflict(s),
  onApplicationCommitted: () => { results.render(); },
});

const layout = new Layout(shell, { focusEditor: () => editor.focus() });
const places = new Places({ onOpen: () => { hideViews(); document.getElementById('place-view').hidden = false; }, onClose: () => showPage(currentPage) });
const applier = new Applier(session, editor, { onRecorded: () => {} });
const results = new Results(session, layout, places, { onPlace: () => {}, onActivity: () => renderActivity(), applyControls: (t, text) => applier.controls(t, text) });
const actions = new Actions(session, layout, places, results, { onPlace: () => {} });
const yourwork = new YourWork(session, places, { onOpenDocument: () => showPage('work'), onPlace: () => {} });
const investigate = new Investigate(actions, places, {});

let currentPage = 'work';
const PAGES = { work: 'work-view', yourwork: 'yourwork-view', investigate: 'investigate-view', settings: 'settings-view', help: 'help-view' };

function hideViews() { for (const id of Object.values(PAGES)) document.getElementById(id).hidden = true; document.getElementById('place-view').hidden = true; }

function showPage(name) {
  if (!PAGES[name]) name = 'work';
  currentPage = name;
  if (places.isOpen()) places.close();
  hideViews();
  document.getElementById(PAGES[name]).hidden = false;
  shell.dataset.page = name;
  for (const a of document.querySelectorAll('.dest')) a.classList.toggle('on', a.dataset.page === name);
  renderToolbar();
  if (name === 'yourwork') yourwork.render();
  if (name === 'investigate') investigate.render();
  if (name === 'settings') renderSettings();
  if (name === 'help') renderHelp();
  if (name === 'work') editor.focus();
  if (location.hash !== '#' + name && name !== 'work') history.replaceState(null, '', '#' + name);
  if (name === 'work' && location.hash && location.hash !== '#work') history.replaceState(null, '', location.pathname);
  renderHeader(session);
}

function renderHeader(s) {
  const t = document.getElementById('doc-title'), m = document.getElementById('doc-meta');
  if (currentPage === 'work' || places.isOpen()) {
    t.textContent = s.displayTitle();
    const n = editor.wordCount();
    m.textContent = (s.title_is_manual ? '' : 'untitled · ') + s.statusText() + ' · ' + n + (n === 1 ? ' word' : ' words') + (editor.mode() === 'plain' ? ' · plain text' : '');
    m.classList.toggle('warn', ['failed', 'conflict', 'nolocal'].includes(s.status));
  } else {
    t.textContent = currentPage === 'yourwork' ? 'Your work' : (currentPage === 'investigate' ? 'Investigate' : (currentPage === 'settings' ? 'Settings' : 'Help'));
    m.textContent = '· the draft stays open in Work';
    m.classList.remove('warn');
  }
  document.title = (window.BRAND && window.BRAND.name || 'Nikodemus') + ' — ' + (currentPage === 'work' ? s.displayTitle() : t.textContent);
}

function renderConflict(s) {
  const head = s.conflict && s.conflict.head;
  results.showNotice('This document was saved elsewhere since this copy was opened (revision ' + (head ? head.revision : '?') + '). Nothing was overwritten. Keep both: yours becomes a new document, or open the saved copy and keep yours in this browser’s recovery.', [
    { label: 'Keep mine as a new document', onClick: () => session.keepMineAsNew().then(() => { results.notice = null; results.render(); }) },
    { label: 'Open the saved copy', onClick: () => session.openSaved().then(() => { results.notice = null; results.render(); }) },
  ]);
  layout.setResults(true);
}

function renderActivity() {
  const s = results.summary();
  const parts = [];
  if (s.running) parts.push(s.running + ' running');
  if (s.done) parts.push(s.done + ' done');
  if (s.attention) parts.push(s.attention + (s.attention === 1 ? ' needs' : ' need') + ' your attention');
  document.getElementById('activity-summary').textContent = parts.join(' · ') || 'nothing running';
}

// ---- the formatting bar (slice C) ------------------------------------------------
// Shown only while the structured editor is active on the Work page. Every
// control takes the pointer on mousedown WITHOUT taking focus, so the
// editing selection is exactly what the command acts on.
const TOOLBAR = [
  ['bold', 'B', 'Bold (⌘B)', 'strong'], ['italic', 'I', 'Italic (⌘I)', 'em'],
  ['h1', 'H1', 'Heading 1'], ['h2', 'H2', 'Heading 2'], ['h3', 'H3', 'Heading 3'], ['paragraph', '¶', 'Paragraph'],
  ['bullet', '• List', 'Bulleted list (⇧⌘8)'], ['ordered', '1. List', 'Numbered list (⇧⌘9)'], ['quote', '❝ Quote', 'Quote'],
  ['link', 'Link', 'Link (http, https or mailto)'], ['find', 'Find', 'Find and replace (⌘F)'], ['undo', '↶', 'Undo (⌘Z)'], ['redo', '↷', 'Redo (⇧⌘Z)'],
];
let toolbarBuilt = false;
function buildToolbar() {
  const tb = document.getElementById('toolbar');
  tb.textContent = '';
  for (const [name, label, title, mark] of TOOLBAR) {
    const b = el('button', { class: 'btn small fmt', type: 'button', text: label, title, dataset: { fmt: name }, 'aria-label': title });
    if (name === 'bold') b.style.fontWeight = '700';
    if (name === 'italic') b.style.fontStyle = 'italic';
    b.addEventListener('mousedown', e => e.preventDefault());            // the selection stays where it is
    b.addEventListener('click', () => runFormat(name));
    tb.appendChild(b);
  }
  toolbarBuilt = true;
}
function runFormat(name) {
  if (name === 'find') { openFind(); return; }
  if (name === 'link') {
    const marks = editor.activeMarks();
    const sel = editor.getSelection();
    if (!sel.text) { toast('Select the words to link first.'); editor.focus(); return; }
    const href = prompt(marks.link ? 'Change the link (empty removes it):' : 'Link to (http, https or mailto):', '');
    if (href === null) { editor.focus(); return; }
    if (!editor.command('link', href)) toast(href.trim() ? 'Not a link this editor holds: http, https or mailto only.' : 'Link removed.');
    editor.focus(); return;
  }
  editor.command(name);
  editor.focus();
  renderToolbarState();
}
function renderToolbar() {
  const tb = document.getElementById('toolbar');
  if (!toolbarBuilt) buildToolbar();
  tb.hidden = !(currentPage === 'work' && editor.supportsFormatting);
  renderToolbarState();
}
function renderToolbarState() {
  const tb = document.getElementById('toolbar');
  if (tb.hidden) return;
  const m = editor.activeMarks();
  for (const b of tb.querySelectorAll('.fmt')) {
    const n = b.dataset.fmt;
    const on = (n === 'bold' && m.strong) || (n === 'italic' && m.em) || (n === 'link' && m.link) || (n === 'paragraph' && m.block === 'paragraph') || (['h1', 'h2', 'h3'].includes(n) && m.block === n);
    b.classList.toggle('on', !!on); b.setAttribute('aria-pressed', String(!!on));
  }
}

// ---- find and replace (slice C) --------------------------------------------------
const find = { open: false, hits: [], at: -1 };
function openFind() {
  const bar = document.getElementById('findbar');
  bar.hidden = false; find.open = true;
  const sel = editor.getSelection();
  const input = document.getElementById('find-input');
  if (sel.text && !sel.text.includes('\n') && sel.text.length < 80) input.value = sel.text;
  input.focus(); input.select();
  runFind(true);
}
function closeFind() { document.getElementById('findbar').hidden = true; find.open = false; find.hits = []; find.at = -1; editor.focus(); }
// `select` moves the editor's selection onto the current match — only for an
// explicit find action (typing in the find box, Next, Previous, Replace);
// a recount after an edit in the draft must never move the caret, or the
// next keystroke would replace a match the writer did not select.
function runFind(fromStart, select = true) {
  const q = document.getElementById('find-input').value;
  const cs = document.getElementById('find-case').checked;
  find.hits = editor.findAll(q, { caseSensitive: cs });
  const sel = editor.getSelection();
  if (fromStart || find.at < 0 || find.at >= find.hits.length) find.at = find.hits.findIndex(h => h.start >= sel.start);
  if (find.at < 0 && find.hits.length) find.at = 0;
  renderFind(select);
}
function renderFind(select = true) {
  const c = document.getElementById('find-count');
  c.textContent = !document.getElementById('find-input').value ? '' : (find.hits.length ? (find.at + 1) + ' of ' + find.hits.length : 'no matches in this draft');
  if (select && find.hits.length && find.at >= 0) { const h = find.hits[find.at]; editor.setSelection(h.start, h.end); }
}
function findStep(delta) {
  if (!find.hits.length) { runFind(true); if (!find.hits.length) return; }
  find.at = (find.at + delta + find.hits.length) % find.hits.length;
  renderFind();
}
function replaceOne() {
  if (!find.hits.length || find.at < 0) { runFind(true); return; }
  const h = find.hits[find.at], rep = document.getElementById('replace-input').value;
  editor.replaceRange(h.start, h.end, rep);
  runFind(false);
}
function replaceAll() {
  runFind(true);
  const rep = document.getElementById('replace-input').value;
  const hits = find.hits.slice();
  if (hits.length) editor.replaceRanges(hits, rep);          // one transaction: one undo step
  toast(hits.length + (hits.length === 1 ? ' occurrence' : ' occurrences') + ' replaced in this draft' + (editor.mode() === 'plain' ? ' (plain text: the browser’s own undo may not reach a replace-all)' : ' — one undo step') + '.');
  runFind(true);
}
function bindFind() {
  document.getElementById('find-input').addEventListener('input', () => runFind(true));
  document.getElementById('find-input').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); findStep(e.shiftKey ? -1 : 1); } if (e.key === 'Escape') { e.preventDefault(); closeFind(); } });
  document.getElementById('replace-input').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); replaceOne(); } if (e.key === 'Escape') { e.preventDefault(); closeFind(); } });
  document.getElementById('find-case').addEventListener('change', () => runFind(true));
  document.getElementById('find-next').addEventListener('click', () => findStep(1));
  document.getElementById('find-prev').addEventListener('click', () => findStep(-1));
  document.getElementById('find-replace').addEventListener('click', replaceOne);
  document.getElementById('find-replace-all').addEventListener('click', replaceAll);
  document.getElementById('find-close').addEventListener('click', closeFind);
  document.getElementById('findbar').addEventListener('keydown', e => { if (e.key === 'Escape') { e.preventDefault(); closeFind(); } });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && find.open && editor.hasFocus()) { closeFind(); return; }
    // ⌘F finds in the draft only while the draft (or the find bar) has the focus; elsewhere it is the browser's own
    if ((e.metaKey || e.ctrlKey) && !e.shiftKey && e.key.toLowerCase() === 'f' && currentPage === 'work' && (editor.hasFocus() || document.getElementById('findbar').contains(document.activeElement))) { e.preventDefault(); openFind(); }
  });
}

function renderSettings() {
  const v = document.getElementById('settings-view'); v.textContent = '';
  v.appendChild(el('h1', { text: 'Settings' }));
  v.appendChild(el('div', { class: 'kv', text: 'Appearance, pairing, the Vault, notifications and the record’s own settings live in the previous interface for now; they are not lost.' }));
  v.appendChild(el('div', { class: 'row' }, [el('button', { class: 'btn', type: 'button', text: 'Open the previous interface (new tab)', onclick: () => window.open('/', '_blank', 'noopener') }), el('button', { class: 'btn', type: 'button', text: 'Devices and pairing', onclick: () => window.open('/pair', '_blank', 'noopener') })]));
  v.appendChild(el('div', { class: 'kv' }, ['Arrangement: Tools and Results remember whether they are open and how wide, per screen size. ', el('button', { class: 'btn small', type: 'button', text: 'Forget the arrangement', onclick: () => { try { Object.keys(localStorage).filter(k => k.startsWith('nikodemus.work.layout.')).forEach(k => localStorage.removeItem(k)); } catch (e) {} toast('Forgotten. Reload to see the defaults.'); } })]));
}

function renderHelp() {
  const v = document.getElementById('help-view'); v.textContent = '';
  v.appendChild(el('h1', { text: 'Help' }));
  const lines = [
    'Write in the blue surface. It saves by itself; the header says when, and counts the words of this draft.',
    'Formatting: bold ⌘B, italic ⌘I, headings, bulleted and numbered lists (⇧⌘8, ⇧⌘9; Tab and ⇧Tab indent and outdent inside a list; Enter on an empty item leaves the list), quotes and links, from the bar or the keys. Enter starts a paragraph; ⇧Enter breaks a line inside one. ⌘F finds and replaces in the draft.',
    'Your words are kept exactly. The plain text that tools read and that exports carry is the text you see; headings, emphasis, lists and links are kept beside it and never sent to a model. A document with characters this editor cannot hold (a carriage return, a control character) opens in plain text, kept exactly, with formatting off.',
    'Pasting keeps paragraphs, headings, lists, quotes, bold, italic and links; anything else arrives as text and the paste says so. ⇧⌘V pastes as plain text.',
    'Tools (left) holds the destinations and every feature in plain words, grouped. Results (right) holds results, readers’ feedback, revision notes and sources. Each side has its own Hide; the header brings them back.',
    'Select words and press ⌘. (or use the selection menu) to act on exactly those words. Nothing runs until you press Start on the proposal, which says what leaves this machine and what it costs.',
    'A result made from a selection can be put into the draft — Insert below the selection, or Replace the selection — only while the draft is as it was when the result was made; otherwise you choose the target again. An application is one undo step (⌘Z).',
    'Ask ⌘K finds a tool by name — related words, feedback, analyze, map. It proposes; it never runs by itself.',
    'Focus hides the sides and the secondary controls; Exit focus brings back what was open.',
    'Document ▾: New, Rename, Duplicate, Open another, Versions (⌘S makes a checkpoint; a version can be restored as a new revision — nothing is rewritten), Make a plain copy, Export (text is visibly plain; Markdown keeps the structure; Print for PDF).',
    'Undo is the editor’s own for this sitting. Checkpoints and the recovery copy in this browser are what persist; they are not continuous undo.',
    'Your work lists what is kept. Investigate shows the instruments and whether each can be started from here.',
    'The previous interface is still there under More tools; nothing was removed.',
  ];
  for (const l of lines) v.appendChild(el('div', { class: 'kv', text: l }));
}

// ---- document menu ------------------------------------------------------------
function fileName(ext) {
  const stamp = new Date().toISOString().slice(0, 10);
  const slug = String(session.displayTitle() || '').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '-').replace(/^-+|-+$/g, '').slice(0, 60);
  return (slug || 'writing') + '-' + stamp + ext;
}
function saveBlob(blob, name) { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000); }

async function showVersions() {
  await session.checkpoint('save');
  const r = await getJSON('/api/notebook/documents/' + encodeURIComponent(session.id) + '/checkpoints');
  if (!r.ok) { results.showNotice('Versions could not be listed: ' + (r.data.error || r.status)); layout.setResults(true); return; }
  const cps = r.data.checkpoints || [];
  const ev = await getJSON('/api/notebook/documents/' + encodeURIComponent(session.id) + '/events');
  const events = ev.ok ? (ev.data.events || []) : [];
  const card = el('div', {}, [el('div', { class: 'lbl', text: 'Versions of this document' })]);
  if (!cps.length) card.appendChild(el('div', { class: 'muted small-text', text: 'No checkpoints yet; ⌘S makes one, and the first structured save keeps the plain text as it stood.' }));
  for (const c of cps) {
    const row = el('div', { class: 'card op' }, [
      el('div', {}, [el('span', { text: 'Revision ' + c.revision + ' · ' + c.reason }), el('span', { class: 'muted', text: ' · ' + whenOf(c.created_at) + ' · ' + c.chars + ' characters' + (c.rich ? ' · with formatting' : ' · plain') })]),
      el('div', { class: 'acts' }, [el('button', { class: 'linkish', type: 'button', text: 'Restore as a new revision', onclick: async () => {
        const out = await session.restoreCheckpoint(c.checkpoint_id);
        if (!out.ok) { toast('Not restored: ' + out.error); return; }
        toast('Restored revision ' + c.revision + ' as revision ' + out.ack.revision + '. The versions in between are kept.');
        results.notice = null; results.render();
      } })]),
    ]);
    card.appendChild(row);
  }
  if (events.length) {
    const det = el('details', {}, [el('summary', { text: events.length + ' recorded event' + (events.length === 1 ? '' : 's') })]);
    for (const e of events.slice(0, 40)) det.appendChild(el('div', { class: 'small-text muted', text: whenOf(e.created_at) + ' · ' + e.kind + (e.revision !== null && e.revision !== undefined ? ' · revision ' + e.revision : '') + (e.detail && e.detail.kind ? ' · ' + e.detail.kind : '') + (e.detail && e.detail.from ? ' · from ' + e.detail.from : '') }));
    card.appendChild(det);
  }
  results.showCustom(card);
  layout.setResults(true);
}

function bindDocMenu() {
  const btn = document.getElementById('doc-menu-btn'), menu = document.getElementById('doc-menu');
  const close = () => { menu.hidden = true; btn.setAttribute('aria-expanded', 'false'); };
  btn.addEventListener('click', () => { menu.hidden = !menu.hidden; btn.setAttribute('aria-expanded', String(!menu.hidden)); if (!menu.hidden) menu.querySelector('button').focus(); });
  document.addEventListener('click', e => { if (!menu.hidden && !menu.contains(e.target) && e.target !== btn) close(); });
  menu.addEventListener('keydown', e => { if (e.key === 'Escape') { close(); btn.focus(); } });
  menu.addEventListener('click', async e => {
    const b = e.target.closest('button[data-doc]'); if (!b) return;
    close();
    const what = b.dataset.doc;
    if (what === 'new') await session.newDocument('');
    else if (what === 'rename') { const t = prompt('Title for this document (leave empty to use the first line):', session.title_is_manual ? session.title : ''); if (t !== null) await session.rename(t); }
    else if (what === 'duplicate') { await session.duplicate(); toast('Duplicated as a new document, formatting and all; the original is unchanged.'); }
    else if (what === 'open') { showPage('yourwork'); }
    else if (what === 'versions') { await showVersions(); }
    else if (what === 'plaincopy') {
      const out = await session.plainCopy();
      if (!out.ok) { toast('No plain copy was made: ' + out.error); return; }
      toast('A plain-text copy is open as a new document. The original keeps its formatting.');
    }
    else if (what === 'export-text') {
      saveBlob(new Blob([session.body()], { type: 'text/plain;charset=utf-8' }), fileName('.txt'));
      toast(editor.mode() === 'plain' ? 'Exported as text, exactly as it stands.' : 'Exported as plain text: headings, emphasis, lists and links are not in a .txt file. The document here keeps them.', 6000);
    }
    else if (what === 'export-md') {
      const s = editor.getStructure();
      const md = s ? toMarkdown(s) : session.body();
      saveBlob(new Blob([md], { type: 'text/markdown;charset=utf-8' }), fileName('.md'));
      toast(s ? 'Exported as Markdown with its headings, lists, quotes, emphasis and links.' : 'Exported as Markdown: the text as it stands (this document has no structure).');
    }
    else if (what === 'print') {
      const s = editor.getStructure();
      const html = s ? toHTML(s) : '<pre style="white-space:pre-wrap;font:inherit">' + session.body().replace(/&/g, '&amp;').replace(/</g, '&lt;') + '</pre>';
      const w = window.open('', '_blank');
      if (!w) { toast('The print window was blocked by the browser.'); return; }
      w.document.write('<!doctype html><html><head><meta charset="utf-8"><title>' + session.displayTitle().replace(/</g, '&lt;') + '</title><style>body{font:16px/1.5 Georgia,serif;max-width:68ch;margin:40px auto;color:#111}blockquote{border-left:3px solid #999;margin-left:0;padding-left:14px}</style></head><body>' + html + '</body></html>');
      w.document.close(); w.focus(); setTimeout(() => w.print(), 250);
    }
    else if (what === 'archive') toast('Archive arrives with the index (slice E); nothing is ever deleted.');
  });
  document.addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') { e.preventDefault(); session.checkpoint('save'); toast('Checkpoint requested.'); }
  });
}

// ---- selection menu -------------------------------------------------------------
function bindSelection() {
  const host = document.getElementById('editor-host');
  let timer = 0;
  const maybe = () => { clearTimeout(timer); timer = setTimeout(() => { const sel = editor.getSelection(); if (sel.text && sel.text.trim() && editor.hasFocus()) actions.showPopover(); else actions.hidePopover(); }, 220); };
  host.addEventListener('mouseup', maybe);
  host.addEventListener('keyup', e => { if (e.shiftKey || e.key === 'Shift') maybe(); });
  editor.onEdit(() => { actions.hidePopover(); if (find.open) runFind(false, false); renderHeader(session); results.refresh(); });
  editor.onSelection(() => renderToolbarState());
  document.addEventListener('mousedown', e => { const pop = document.getElementById('sel-popover'); if (!pop.hidden && !pop.contains(e.target) && !host.contains(e.target)) actions.hidePopover(); });
  document.getElementById('sel-popover').addEventListener('keydown', e => { if (e.key === 'Escape') { actions.hidePopover(); editor.focus(); } });
}

// ---- destinations ---------------------------------------------------------------
function bindDestinations() {
  // the destinations only — the shell's own data-page attribute is state, not a control
  document.querySelectorAll('a[data-page]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); showPage(a.dataset.page); if (layout.state.narrow) layout.setTools(false); }));
  window.addEventListener('hashchange', () => { const p = location.hash.slice(1); if (PAGES[p]) showPage(p); });
}

async function boot() {
  bindDocMenu(); bindSelection(); bindDestinations(); bindFind(); actions.bindAsk();
  layout.hooks.onChange = () => { if (layout.state.results) results.seen(); };
  await actions.load();
  results.loadRecent(id => (actions.byId[id] && actions.byId[id].label) || (id || '').replace(/^legacy:\/api\/jobs:/, 'a run: '));
  const known = session.loadIdentity();
  let opened = false;
  if (known && known.id) opened = await session.open(known.id);
  if (!opened) {
    // the most recently saved document, else a fresh one
    const r = await getJSON('/api/notebook/documents?limit=1');
    const first = r.ok ? ((r.data.documents || r.data.items || [])[0]) : null;
    if (first && first.doc_id) opened = await session.open(first.doc_id);
  }
  if (!opened) await session.newDocument('');
  const p = location.hash.slice(1);
  showPage(PAGES[p] ? p : 'work');
  renderActivity();
  results.render();
  layout.apply();
  window.__work = { session, layout, results, actions, places, editor, applier };   // for the journeys: state, not a control surface
}
boot();
