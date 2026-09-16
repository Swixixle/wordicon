// workspace-v2 — Your work (slice B: what the existing record lists; slice E
// replaces the sources with the derived index and its search). Everything
// here is a read of local records; nothing is fetched from a producer and
// no model is asked.
import { getJSON, el, whenOf } from './util.js';

export class YourWork {
  constructor(session, places, hooks = {}) {
    this.session = session; this.places = places; this.hooks = hooks;
    this.view = document.getElementById('yourwork-view');
  }
  async render() {
    const v = this.view; v.textContent = '';
    v.appendChild(el('h1', { text: 'Your work' }));
    v.appendChild(el('div', { class: 'muted small-text', text: 'Writing and runs, from the record. Search across everything arrives with the index (slice E); until then this lists the notebook and the last thirty runs.' }));
    const [docs, hist, live] = await Promise.all([getJSON('/api/notebook/documents?limit=50'), getJSON('/api/history'), getJSON('/api/inflight')]);
    const list = el('div', { style: 'display:flex; flex-direction:column; gap:8px' });
    if (docs.ok) {
      for (const d of (docs.data.documents || docs.data.items || [])) {
        list.appendChild(el('div', { class: 'card op' }, [
          el('div', { class: 'row' }, [el('span', { class: 'chip', text: 'writing' }), el('span', { class: 'result-title', text: d.display_title || d.title || 'Untitled' }), el('span', { class: 'muted small-text', style: 'margin-left:auto', text: whenOf(d.saved_at) })]),
          el('div', { class: 'muted small-text', text: `notebook · revision ${d.revision} · created ${whenOf(d.created_at)}` }),
          el('div', { class: 'acts' }, [el('button', { class: 'linkish', type: 'button', text: 'Open', onclick: async () => { await this.session.open(d.doc_id); if (this.hooks.onOpenDocument) this.hooks.onOpenDocument(); } })]),
        ]));
      }
    }
    const running = live.ok ? (live.data.running || []) : [];
    for (const j of running) {
      list.appendChild(el('div', { class: 'card op' }, [
        el('div', { class: 'row' }, [el('span', { class: 'chip', text: 'run' }), el('span', { class: 'result-title', text: j.mode + ' · ' + (j.input_text || '').slice(0, 60) }), el('span', { class: 'muted small-text', style: 'margin-left:auto', text: whenOf(j.created_at) })]),
        el('div', { class: 'state running', text: (j.status || 'running') + (j.progress ? ' · ' + j.progress : '') }),
      ]));
    }
    if (hist.ok) {
      const seen = new Set();
      for (const it of (hist.data.items || [])) {
        if (seen.has(it.trace_id)) continue; seen.add(it.trace_id);
        const titles = (hist.data.items || []).filter(x => x.trace_id === it.trace_id).map(x => x.title).filter(Boolean);
        list.appendChild(el('div', { class: 'card op' }, [
          el('div', { class: 'row' }, [el('span', { class: 'chip', text: it.operation || 'run' }), el('span', { class: 'result-title', text: titles.slice(0, 3).join(' · ') || it.trace_id }), el('span', { class: 'muted small-text', style: 'margin-left:auto', text: whenOf(it.created_at) })]),
          el('div', { class: 'muted small-text', text: 'run ' + it.trace_id + (it.decision ? ' · ruled: ' + it.decision : '') }),
          el('div', { class: 'acts' }, [el('button', { class: 'linkish', type: 'button', text: 'Open full result', onclick: () => { this.places.open('/?trace=' + encodeURIComponent(it.trace_id)); if (this.hooks.onPlace) this.hooks.onPlace(); } })]),
        ]));
      }
    }
    if (!list.children.length) list.appendChild(el('div', { class: 'muted', text: 'Nothing recorded yet.' }));
    v.appendChild(list);
  }
}
