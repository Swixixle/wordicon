// workspace-v2 — Your work (slice E): everything the record keeps, found
// through the derived index (scripts/workindex.py) — writing, runs and
// their inputs, readers' readings, revision notes, concepts, saved words,
// questions, sources, recordings, rooms, depositions, inquiries, recovery
// cases, operations. A search is local: the words go to the index as
// bound parameters and never to a model; a hit is a way to reopen the
// authoritative record, never a permission to do anything with it. The
// page says when the index is still updating instead of promising an
// exhaustive "nothing".
import { getJSON, postJSON, el, whenOf, toast } from './util.js';

const KIND_ORDER = ['writing', 'run', 'reading', 'note', 'concept', 'word', 'input', 'operation', 'question', 'source', 'media', 'room', 'deposition', 'inquiry', 'recovery'];

export class YourWork {
  constructor(session, places, hooks = {}) {
    this.session = session; this.places = places; this.hooks = hooks;
    this.view = document.getElementById('yourwork-view');
    this.state = { q: '', kind: '', status: '', archived: 'no', since: '', cursor: null, items: [], health: null, kinds: {}, mode: 'recent', next: null, loading: false };
    this.built = false;
  }

  build() {
    const v = this.view; v.textContent = '';
    v.appendChild(el('h1', { text: 'Your work' }));
    const bar = el('div', { class: 'work-search' });
    this.input = el('input', { type: 'search', id: 'work-q', placeholder: 'Search everything kept: words in your writing, a run’s input, a reader’s answer, a note, a concept…', 'aria-label': 'Search your work' });
    let timer = 0;
    this.input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => { this.state.q = this.input.value; this.state.cursor = null; this.load(); }, 180); });
    this.input.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); clearTimeout(timer); this.state.q = this.input.value; this.state.cursor = null; this.load(); } });
    bar.appendChild(this.input);
    this.healthLine = el('div', { class: 'muted small-text', id: 'work-health' });
    bar.appendChild(this.healthLine);
    v.appendChild(bar);
    this.filters = el('div', { class: 'work-filters', role: 'group', 'aria-label': 'Filters' });
    v.appendChild(this.filters);
    this.list = el('div', { class: 'work-list', id: 'work-list' });
    v.appendChild(this.list);
    this.more = el('div', { class: 'row' });
    v.appendChild(this.more);
    // the index's own account of itself — its population, generation and stores — and the rebuild,
    // in a disclosure at the end: available, never the headline (the review of 6e5b59c)
    this.aboutLine = el('div', { class: 'small-text muted', id: 'work-about' });
    const about = el('details', { class: 'work-about' }, [el('summary', { text: 'About this index' }), this.aboutLine,
      el('div', { class: 'row' }, [el('button', { class: 'btn small', type: 'button', text: 'Rebuild the index', title: 'Reads every store again into a new generation; the current one stays until the new one is complete', onclick: async () => { const r = await postJSON('/api/work/reindex', {}); toast(r.ok ? ((r.data.rebuilt ? 'Rebuilt: ' + (r.data.items || 0) + ' items' : 'Not rebuilt — the last working index stays') + (r.data.failed && r.data.failed.length ? ' — incomplete: ' + r.data.failed.join('; ') : '')) : ('Not rebuilt: ' + (r.data.error || r.status)), 6000); this.state.cursor = null; this.load(); } })])]);
    v.appendChild(about);
    this.built = true;
  }

  async render() {
    if (!this.built) this.build();
    await this.load();
    this.input.focus();
  }

  async load() {
    const s = this.state;
    s.loading = true;
    const params = new URLSearchParams();
    if (s.q) params.set('q', s.q);
    if (s.kind) params.set('kind', s.kind);
    if (s.status) params.set('status', s.status);
    if (s.since) params.set('since', s.since);
    params.set('archived', s.archived);
    if (s.cursor) params.set('cursor', s.cursor);
    params.set('limit', '30');
    const r = await getJSON('/api/work?' + params.toString());
    s.loading = false;
    if (!r.ok) { this.list.textContent = ''; this.list.appendChild(el('div', { class: 'warn', text: 'Your work could not be read: ' + (r.data.error || r.status) })); return; }
    const d = r.data;
    s.items = s.cursor ? s.items.concat(d.items || []) : (d.items || []);
    s.health = d.health; s.kinds = d.kinds || {}; s.mode = d.mode; s.next = d.next_cursor; s.exhaustive = d.exhaustive; s.population = d.population;
    this.renderFilters(); this.renderHealth(); this.renderList();
  }

  renderFilters() {
    const f = this.filters; f.textContent = '';
    const s = this.state;
    const chip = (label, on, onClick, title) => { const b = el('button', { class: 'chip-btn' + (on ? ' on' : ''), type: 'button', text: label, title: title || '', 'aria-pressed': String(!!on) }); b.addEventListener('click', onClick); return b; };
    f.appendChild(chip('Everything', !s.kind, () => { s.kind = ''; s.cursor = null; this.load(); }));
    const kinds = KIND_ORDER.filter(k => s.kinds[k]).concat(Object.keys(s.kinds).filter(k => !KIND_ORDER.includes(k)));
    for (const k of kinds) f.appendChild(chip(kindLabel(k) + ' · ' + s.kinds[k], s.kind === k, () => { s.kind = s.kind === k ? '' : k; s.cursor = null; this.load(); }, 'kind: ' + k));
    f.appendChild(el('span', { class: 'muted small-text', text: ' · ' }));
    const sinceSel = el('select', { 'aria-label': 'Since' });
    for (const [v, t] of [['', 'any time'], [daysAgo(1), 'today'], [daysAgo(7), 'past week'], [daysAgo(30), 'past month']]) { const o = el('option', { value: v, text: t }); if (v === s.since) o.selected = true; sinceSel.appendChild(o); }
    sinceSel.addEventListener('change', () => { s.since = sinceSel.value; s.cursor = null; this.load(); });
    f.appendChild(sinceSel);
    f.appendChild(chip(s.archived === 'only' ? 'Archived only' : 'Show archived', s.archived === 'only', () => { s.archived = s.archived === 'only' ? 'no' : 'only'; s.cursor = null; this.load(); }, 'Archived items leave ordinary listings and keep their history'));
  }

  renderHealth() {
    const h = this.state.health || {};
    const pend = Object.entries(h.pending || {}).filter(([, v]) => v !== null && v > 0);
    // the headline: how many items are searchable and how fresh; the index's internals (stores, generation) in About
    let text = (h.items === undefined ? '' : h.items + ' item' + (h.items === 1 ? '' : 's') + ' searchable') + (h.last_refresh_at ? ' · refreshed ' + whenOf(h.last_refresh_at) : '') + (h.fts ? '' : ' · plain matching (no full-text engine)');
    if (h.updating || h.incomplete) text = 'Search is updating; some recent work may be missing' + (pend.length ? ' (' + pend.map(([k, v]) => v + ' ' + k + (v === 1 ? ' change' : ' changes') + ' pending').join(', ') + ')' : '') + (h.incomplete ? ' — ' + h.incomplete : '') + ' · ' + text;
    this.healthLine.textContent = text;
    this.healthLine.classList.toggle('warn', !!(h.updating || h.incomplete));
    if (this.aboutLine) this.aboutLine.textContent = (h.population || '') + (h.built_at ? ' · built ' + whenOf(h.built_at) : '') + ' — a derived index; every hit reopens the authoritative record';
  }

  renderList() {
    const s = this.state;
    const l = this.list; l.textContent = '';
    const head = el('div', { class: 'muted small-text', text: s.items.length + (s.next ? '+' : '') + ' shown · ' + (s.population || '') + (s.q ? ' · ' + (s.mode === 'fts' ? 'full-text match' : 'literal match') : ' · newest change first') });
    l.appendChild(head);
    if (!s.items.length) {
      l.appendChild(el('div', { class: 'muted', text: s.q ? (s.exhaustive ? 'No matches among the indexed items.' : 'No matches yet — the index is still updating, so this is not an exhaustive no.') : 'Nothing kept yet.' }));
    }
    for (const it of s.items) l.appendChild(this.card(it));
    this.more.textContent = '';
    if (s.next) this.more.appendChild(el('button', { class: 'btn', type: 'button', text: 'More', onclick: () => { s.cursor = s.next; this.load(); } }));
  }

  card(it) {
    const acts = [];
    const open = it.open || {};
    if (open.document) acts.push(el('button', { class: 'linkish', type: 'button', text: 'Open', onclick: async () => { const ok = await this.session.open(open.document); if (!ok) { toast('This document is not in the notebook any more.'); return; } if (this.hooks.onOpenDocument) this.hooks.onOpenDocument(); } }));
    if (open.operation) acts.push(el('button', { class: 'linkish', type: 'button', text: 'Open the operation', onclick: () => { if (this.hooks.onOpenOperation) this.hooks.onOpenOperation(open.operation); } }));
    if (open.reading) acts.push(el('button', { class: 'linkish', type: 'button', text: 'Open the reading', onclick: () => { if (this.hooks.onOpenReading) this.hooks.onOpenReading(open.reading); } }));
    if (open.place) acts.push(el('button', { class: 'linkish', type: 'button', text: it.kind === 'run' ? 'Open full result' : 'Open', onclick: () => { this.places.open(open.place); if (this.hooks.onPlace) this.hooks.onPlace(); } }));
    acts.push(el('button', { class: 'linkish', type: 'button', text: it.archived ? 'Unarchive' : 'Archive', title: 'Archive hides it from ordinary listings and keeps everything', onclick: async () => {
      const r = await postJSON('/api/work/' + encodeURIComponent(it.item_id) + '/archive', { archived: !it.archived });
      if (!r.ok) { toast('Not changed: ' + (r.data.error || r.status)); return; }
      toast(it.archived ? 'Back in the listings.' : 'Archived — kept, hidden from ordinary listings; the Archived filter shows it.');
      this.state.cursor = null; this.load();
    } }));
    const toolWord = it.tool_label || it.tool || '';
    const meta = [it.kind_label || it.kind, toolWord && toolWord !== it.kind ? toolWord : '', it.status, it.changed_at ? 'changed ' + whenOf(it.changed_at) : '', it.created_at && it.created_at !== it.changed_at ? 'created ' + whenOf(it.created_at) : ''].filter(Boolean).join(' · ');
    return el('div', { class: 'card op work-item' + (it.archived ? ' archived' : ''), dataset: { item: it.item_id, kind: it.kind } }, [
      el('div', { class: 'row' }, [el('span', { class: 'chip', text: it.kind_label || it.kind }), el('span', { class: 'result-title', text: it.title || '(untitled)' }), el('span', { class: 'muted small-text', style: 'margin-left:auto', text: whenOf(it.changed_at || it.created_at) })]),
      it.snippet ? el('div', { class: 'kv work-snippet', text: it.snippet }) : null,
      el('div', { class: 'muted small-text', text: meta }),
      el('div', { class: 'acts' }, acts),
      el('details', {}, [el('summary', { text: 'Details' }), el('div', { class: 'small-text muted', text: it.item_id + (it.tool && it.tool !== toolWord ? ' · action ' + it.tool : '') + (it.related && it.related.length ? ' · related: ' + it.related.join(', ') : '') })]),
    ]);
  }
}

function kindLabel(k) {
  return ({ writing: 'Writing', run: 'Runs', reading: 'Readers', note: 'Revision notes', concept: 'Concepts', word: 'Saved words', input: 'Inputs', operation: 'Operations', question: 'Questions', source: 'Sources', media: 'Recordings', room: 'Rooms', deposition: 'Depositions', inquiry: 'Inquiries', recovery: 'Recovery cases' })[k] || k;
}
function daysAgo(n) { const d = new Date(Date.now() - n * 86400000); return d.toISOString(); }
