// workspace-v2 — the shell's bootstrap (slice B). Wires the modules; holds
// no business logic of its own.
import { el, toast, getJSON } from './util.js';
import { DocumentSession } from './session.js';
import { PlainEditor } from './editor_plain.js';
import { Layout } from './layout.js';
import { Places } from './places.js';
import { Results } from './results.js';
import { Actions } from './actions.js';
import { YourWork } from './yourwork.js';
import { Investigate } from './investigate.js';

const shell = document.getElementById('shell');
const editor = new PlainEditor();
editor.mount(document.getElementById('editor-host'));

const session = new DocumentSession(editor, {
  onStatus: s => renderHeader(s),
  onOpened: s => { renderHeader(s); showPage('work'); if (s.recovered) toast('Opened with unsent changes recovered from this browser (newer than the saved copy).'); },
  onConflict: s => renderConflict(s),
});

const layout = new Layout(shell, { focusEditor: () => editor.focus() });
const places = new Places({ onOpen: () => { hideViews(); document.getElementById('place-view').hidden = false; }, onClose: () => showPage(currentPage) });
const results = new Results(session, layout, places, { onPlace: () => {}, onActivity: () => renderActivity() });
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
  const toolbar = document.getElementById('toolbar');
  toolbar.hidden = !(name === 'work' && editor.supportsFormatting);
  document.getElementById('title-block').style.visibility = name === 'work' ? 'visible' : 'visible';
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
    m.textContent = (s.title_is_manual ? '' : 'untitled · ') + s.statusText();
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
    'Write in the blue surface. It saves by itself; the header says when.',
    'Tools (left) holds the destinations and every feature in plain words, grouped. Results (right) holds results, readers’ feedback, revision notes and sources. Each side has its own Hide; the header brings them back.',
    'Select words and press ⌘. (or use the selection menu) to act on exactly those words. Nothing runs until you press Start on the proposal, which says what leaves this machine and what it costs.',
    'Ask ⌘K finds a tool by name — related words, feedback, analyze, map. It proposes; it never runs by itself.',
    'Focus hides the sides and the secondary controls; Exit focus brings back what was open.',
    'Your work lists what is kept. Investigate shows the instruments and whether each can be started from here.',
    'The previous interface is still there under More tools; nothing was removed.',
  ];
  for (const l of lines) v.appendChild(el('div', { class: 'kv', text: l }));
}

// ---- document menu ------------------------------------------------------------
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
    else if (what === 'duplicate') { const text = session.body(); await session.newDocument(text, 'duplicate'); toast('Duplicated as a new document; the original is unchanged.'); }
    else if (what === 'open') { showPage('yourwork'); }
    else if (what === 'versions') { await session.checkpoint('save'); const r = await getJSON('/api/notebook/documents/' + encodeURIComponent(session.id) + '/checkpoints'); if (r.ok) { const cps = r.data.checkpoints || []; results.showNotice(cps.length ? 'Versions: ' + cps.map(c => 'revision ' + c.revision + ' (' + c.reason + ')').join(' · ') + ' — restore-as-new arrives with the structured editor (slice C).' : 'No checkpoints yet; ⌘S makes one.'); layout.setResults(true); } }
    else if (what === 'export') { const blob = new Blob([session.body()], { type: 'text/plain;charset=utf-8' }); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = (session.displayTitle() || 'draft').replace(/[^\w\- ]+/g, '').slice(0, 60) + '.txt'; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000); }
    else if (what === 'archive') toast('Archive arrives with the index (slice E); nothing is ever deleted.');
  });
  document.addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') { e.preventDefault(); session.checkpoint('save'); toast('Checkpoint requested.'); }
  });
}

// ---- selection menu -------------------------------------------------------------
function bindSelection() {
  const ta = editor.element();
  let timer = 0;
  const maybe = () => { clearTimeout(timer); timer = setTimeout(() => { const sel = editor.getSelection(); if (sel.text && sel.text.trim() && document.activeElement === ta) actions.showPopover(); else actions.hidePopover(); }, 220); };
  ta.addEventListener('mouseup', maybe);
  ta.addEventListener('keyup', e => { if (e.shiftKey || e.key === 'Shift') maybe(); });
  ta.addEventListener('input', () => actions.hidePopover());
  document.addEventListener('mousedown', e => { const pop = document.getElementById('sel-popover'); if (!pop.hidden && !pop.contains(e.target) && e.target !== ta) actions.hidePopover(); });
  document.getElementById('sel-popover').addEventListener('keydown', e => { if (e.key === 'Escape') { actions.hidePopover(); editor.focus(); } });
}

// ---- destinations ---------------------------------------------------------------
function bindDestinations() {
  document.querySelectorAll('[data-page]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); showPage(a.dataset.page); if (layout.state.narrow) layout.setTools(false); }));
  window.addEventListener('hashchange', () => { const p = location.hash.slice(1); if (PAGES[p]) showPage(p); });
}

async function boot() {
  bindDocMenu(); bindSelection(); bindDestinations(); actions.bindAsk();
  layout.hooks.onChange = () => { if (layout.state.results) results.seen(); };
  await actions.load();
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
  window.__work = { session, layout, results, actions, places, editor };   // for the journeys: state, not a control surface
}
boot();
