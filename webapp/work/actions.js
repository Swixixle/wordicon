// workspace-v2 — the registry on the page (instructions §5). Tools, the
// selection menu, Ask and the proposal card are all generated from
// GET /api/actions; the page never invents a control. Selecting an action
// PREPARES it (a frozen proposal, nothing sent); the proposal's Start
// dispatches once under a request key. Opening a view starts nothing.
import { getJSON, postJSON, el, requestKey, toast } from './util.js';

const MODE_DOT = { decompose: 'var(--mode-source)', crack: 'var(--mode-source)', deep: 'var(--mode-source)', sprout: 'var(--mode-sprout)', refract: 'var(--mode-refract)', forge: 'var(--mode-forge)' };
const GROUP_TITLES = { on_draft: 'On this draft', explore: 'Explore', investigate: 'Investigate', more: 'More tools' };
const POPOVER_ROUTES = ['feedback.readers', 'analyze.decompose', 'explore.refract'];
const POPOVER_MORE = ['explore.sprout', 'explore.forge', 'explore.crack', 'explore.deep', 'explore.map'];

export class Actions {
  constructor(session, layout, places, results, hooks = {}) {
    this.session = session; this.layout = layout; this.places = places; this.results = results; this.hooks = hooks;
    this.registry = null; this.byId = {};
    this.proposal = null;
    this.openGroups = new Set(['on_draft']);
  }

  async load() {
    const r = await getJSON('/api/actions');
    if (!r.ok) { toast('The action registry could not be read: ' + (r.data && r.data.error || r.status)); return; }
    this.registry = r.data;
    this.byId = Object.fromEntries(r.data.actions.map(a => [a.id, a]));
    this.renderTools();
  }

  subjectNow() {
    // a non-empty selection is the subject; otherwise the whole draft
    const ref = this.session.ref();
    const sel = this.session.adapter.getSelection();
    const text = this.session.body();
    if (sel && sel.text && sel.text.trim()) {
      return { kind: 'selection', text: sel.text, doc_id: ref ? ref.id : '', revision: ref ? ref.revision : null, seq: ref ? ref.seq : null,
               editor_session: ref ? ref.editorSession : '', range: { start: sel.cp.start, end: sel.cp.end }, units: 'codepoint', title: this.session.displayTitle() };
    }
    return { kind: 'document', text, doc_id: ref ? ref.id : '', revision: ref ? ref.revision : null, seq: ref ? ref.seq : null,
             editor_session: ref ? ref.editorSession : '', title: this.session.displayTitle() };
  }

  // ---- Tools ---------------------------------------------------------------
  renderTools() {
    const host = document.getElementById('tool-groups');
    host.textContent = '';
    for (const g of ['on_draft', 'explore', 'investigate', 'more']) {
      const items = this.registry.actions.filter(a => a.group === g);
      const avail = items.filter(a => a.readiness && a.readiness.available).length;
      const count = g === 'investigate' ? `${avail} of ${items.length} available` : (g === 'on_draft' ? '' : String(items.length));
      const det = el('details', { class: 'group', open: this.openGroups.has(g) ? true : null, dataset: { group: g } });
      det.addEventListener('toggle', () => { if (det.open) this.openGroups.add(g); else this.openGroups.delete(g); });
      const sum = el('summary', {}, [el('span', { class: 'arrow', 'aria-hidden': 'true', text: '▸' }), el('span', { text: GROUP_TITLES[g] }), count ? el('span', { class: 'count', text: count }) : null]);
      det.appendChild(sum);
      const upd = () => { sum.firstChild.textContent = det.open ? '▾' : '▸'; };
      det.addEventListener('toggle', upd); upd();
      for (const a of items) det.appendChild(this.itemButton(a));
      host.appendChild(det);
    }
  }

  itemButton(a) {
    const off = !(a.readiness && a.readiness.available);
    const b = el('button', { class: 'item' + (off ? ' off' : ''), type: 'button', dataset: { action: a.id }, title: a.readiness ? a.readiness.reason : '' });
    if (a.mode && MODE_DOT[a.mode]) b.appendChild(el('span', { class: 'dot', style: 'background:' + MODE_DOT[a.mode] }));
    b.appendChild(el('span', { text: a.label }));
    const sub = a.mode && a.mode !== a.label.toLowerCase() && a.group === 'explore' ? capital(a.mode) : (off ? shortReason(a) : '');
    if (sub) b.appendChild(el('span', { class: 'sub', text: '— ' + sub }));
    b.addEventListener('click', () => this.choose(a.id, b));
    return b;
  }

  // ---- choosing an action ----------------------------------------------------
  async choose(actionId, opener) {
    const a = this.byId[actionId];
    if (!a) return;
    if (a.kind === 'view') {
      if (a.handler === 'unavailable') { toast(a.readiness && a.readiness.reason || 'not available'); return; }
      if (a.handler === 'standalone') { window.open(a.route, '_blank', 'noopener'); return; }
      if (a.route && a.route.startsWith('/#')) { this.places.open('/' + a.route.slice(1)); if (this.hooks.onPlace) this.hooks.onPlace(); return; }
      this.places.open(a.route); if (this.hooks.onPlace) this.hooks.onPlace();
      return;
    }
    if (a.kind === 'note' || a.kind === 'ruling' || a.kind === 'apply') { toast(a.label + ' is offered on a result, a word or a candidate — not from here.'); return; }
    await this.prepare(actionId);
  }

  async prepare(actionId, subjectOverride) {
    const a = this.byId[actionId];
    if (this.session.adapter.isComposing && this.session.adapter.isComposing()) { toast('Finish the character being composed first — the capture waits for it.'); return; }
    const subject = subjectOverride || this.subjectNow();
    if (!subject.text || !subject.text.trim()) { toast('Nothing is written or selected yet.'); return; }
    const r = await postJSON('/api/actions/prepare', { action_id: actionId, subject, inputs: {} });
    if (!r.ok) {
      this.results.showNotice(r.data.error || ('HTTP ' + r.status), r.data.choices ? r.data.choices.map(c => ({ label: c.label, onClick: () => this.prepare(c.id, subject) })) : []);
      this.layout.setResults(true);
      return;
    }
    this.proposal = r.data;
    this.results.showProposal(r.data, a, {
      onStart: () => this.start(),
      onClose: () => { this.proposal = null; this.results.clearProposal(); },
    });
    this.layout.setResults(true);
  }

  async start() {
    const p = this.proposal;
    if (!p) return;
    const key = requestKey();
    const r = await postJSON('/api/operations', { prepared_id: p.prepared_id, request_key: key });
    if (!r.ok) {
      const d = r.data || {};
      this.results.showNotice((d.error || ('HTTP ' + r.status)) + (d.nothing_was_sent ? ' — nothing was sent.' : ''));
      return;
    }
    this.proposal = null;
    this.results.clearProposal();
    this.results.track(r.data, p);
  }

  // ---- the selection menu ------------------------------------------------------
  showPopover() {
    const pop = document.getElementById('sel-popover');
    const sel = this.session.adapter.getSelection();
    if (!sel || !sel.text || !sel.text.trim()) { pop.hidden = true; return; }
    pop.textContent = '';
    const words = sel.text.trim().split(/\s+/).filter(Boolean).length;
    pop.appendChild(el('div', { class: 'head' }, [el('span', { class: 'lbl', text: `On your selection · ${words} word${words === 1 ? '' : 's'}` }), el('span', { class: 'muted small-text', text: '⌘.' })]));
    for (const id of POPOVER_ROUTES) {
      const a = this.byId[id]; if (!a) continue;
      const b = el('button', { class: 'route', type: 'button', text: a.label + (a.mode && a.group !== 'on_draft' ? ' — ' + capital(a.mode) : (id === 'analyze.decompose' ? ' — Decompose' : '')) });
      b.addEventListener('click', () => { pop.hidden = true; this.prepare(id); });
      pop.appendChild(b);
    }
    const more = el('div', { class: 'more' }, ['More ▾ — ']);
    POPOVER_MORE.forEach((id, i) => {
      const a = this.byId[id]; if (!a) return;
      const b = el('button', { class: 'linkish', type: 'button', text: a.label });
      b.addEventListener('click', () => { pop.hidden = true; this.choose(id); });
      if (i) more.appendChild(document.createTextNode(' · '));
      more.appendChild(b);
    });
    pop.appendChild(more);
    // below the selection's last line, never over it; inside the writing view
    const host = document.getElementById('work-view');
    const hr = host.getBoundingClientRect();
    let top = 0, left = 0;
    try { const r = this.session.adapter.selectionRect(); top = r.top - hr.top + host.scrollTop + r.height + 8; left = Math.max(16, Math.min(r.left - hr.left, host.clientWidth - 336)); } catch (e) { top = 120; left = 40; }
    pop.style.top = top + 'px'; pop.style.left = left + 'px';
    pop.hidden = false;
    const first = pop.querySelector('.route'); if (first) first.focus();
  }
  hidePopover() { document.getElementById('sel-popover').hidden = true; }

  // ---- Ask ---------------------------------------------------------------------
  bindAsk() {
    const ask = document.getElementById('ask'), input = document.getElementById('ask-input'), list = document.getElementById('ask-matches');
    let matches = [], active = 0, timer = 0;
    const render = () => {
      list.textContent = '';
      matches.forEach((m, i) => {
        const b = el('button', { type: 'button', class: i === active ? 'on' : '', role: 'option', 'aria-selected': String(i === active) },
          [el('span', { text: m.label }), el('span', { class: 'g', text: GROUP_TITLES[m.group] || m.group }), m.remainder ? el('span', { class: 'g', text: '· “' + m.remainder + '”' }) : null, m.accepts_subject ? null : el('span', { class: 'g', text: '· not for this selection' })]);
        b.addEventListener('click', () => { pick(i); });
        list.appendChild(b);
      });
    };
    const pick = (i) => {
      const m = matches[i]; if (!m) return; this.closeAsk();
      // a plain-language request whose rest names what to investigate: that rest is the subject, verbatim
      if (m.remainder) { this.prepare(m.id, { kind: 'description', text: m.remainder, title: m.label }); return; }
      this.choose(m.id);
    };
    const query = async () => {
      const q = input.value.trim();
      if (!q) { matches = []; render(); return; }
      const subject = this.subjectNow().kind;
      const r = await postJSON('/api/actions/match', { query: q, subject });
      if (!r.ok) return;
      matches = r.data.matches || []; active = 0; render();
    };
    input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(query, 120); });
    input.addEventListener('keydown', e => {
      if (e.key === 'ArrowDown') { active = Math.min(matches.length - 1, active + 1); render(); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { active = Math.max(0, active - 1); render(); e.preventDefault(); }
      else if (e.key === 'Enter') {
        e.preventDefault();
        if (!matches.length) { toast('No tool matches that. Try a plain name: related words, feedback, analyze, map.'); return; }
        if (matches.length > 1 && !e.altKey) { list.firstChild && list.firstChild.focus(); toast('Several tools match — choose one.'); return; }
        pick(active);
      }
      else if (e.key === 'Escape') { this.closeAsk(); e.preventDefault(); }
    });
    list.addEventListener('keydown', e => {
      const items = Array.from(list.children); const i = items.indexOf(document.activeElement);
      if (e.key === 'ArrowDown') { (items[i + 1] || items[0]).focus(); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { (items[i - 1] || input).focus(); e.preventDefault(); }
      else if (e.key === 'Escape') { this.closeAsk(); e.preventDefault(); }
    });
    ask.addEventListener('click', e => { if (e.target === ask) this.closeAsk(); });
    document.getElementById('ask-btn').addEventListener('click', () => this.openAsk());
    document.addEventListener('keydown', e => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); this.openAsk(); }
      if ((e.metaKey || e.ctrlKey) && e.key === '.') { e.preventDefault(); this.showPopover(); }
    });
  }
  openAsk() {
    this.askOpener = document.activeElement;
    const ask = document.getElementById('ask'), input = document.getElementById('ask-input');
    ask.hidden = false; input.value = ''; document.getElementById('ask-matches').textContent = ''; input.focus();
  }
  closeAsk() {
    document.getElementById('ask').hidden = true;
    if (this.askOpener && this.askOpener.focus) { try { this.askOpener.focus(); } catch (e) {} }
  }
}

function capital(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : ''; }
function shortReason(a) {
  const r = (a.readiness && a.readiness.reason) || '';
  if (r.length <= 34) return r;
  return r.slice(0, 32) + '…';
}
