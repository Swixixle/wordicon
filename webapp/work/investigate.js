// workspace-v2 — Investigate (slice B: the cards, readiness from the
// registry, which derives it from the connector record; slice F adds the
// adapters). Nothing on this page reaches a producer when it opens: the
// readiness shown is what the record says, and a connection check is a
// separate press.
import { el } from './util.js';

const CARDS = [
  { name: 'EthicalAlt', what: 'Company and brand ethical research — profiles, incidents, a signed receipt.', lookup: 'investigate.ethicalalt.lookup', start: 'investigate.ethicalalt.start', leaves: 'a name, when connected', cost: 'unknown until it runs' },
  { name: 'Open Case', what: 'Public-record and case investigation — FEC, votes, lobbying, signed snapshots.', lookup: 'investigate.opencase.list', start: 'investigate.opencase.start', leaves: 'a case and your key, when connected', cost: 'unknown; enrichment calls a provider' },
  { name: 'PUBLIC EYE', what: 'Article and podcast investigation — jobs, receipts, a public verifier.', lookup: null, start: 'investigate.publiceye.start', leaves: 'an article or podcast URL, when connected', cost: 'unknown' },
  { name: 'Rabbit Hole', what: 'Your separate application — not Explore related ideas, not EthicalAlt Deep Research.', lookup: null, start: 'investigate.rabbithole.connect', leaves: '—', cost: '—' },
];

export class Investigate {
  constructor(actions, places, hooks = {}) { this.actions = actions; this.places = places; this.hooks = hooks; this.view = document.getElementById('investigate-view'); }
  render() {
    const v = this.view; v.textContent = '';
    v.appendChild(el('h1', { text: 'Investigate' }));
    const grid = el('div', { style: 'display:grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 12px' });
    for (const c of CARDS) {
      const lookup = c.lookup ? this.actions.byId[c.lookup] : null;
      const start = this.actions.byId[c.start];
      const rd = (start && start.readiness) || {};
      const pr = rd.producer || {};
      const avail = [];
      if (lookup && lookup.readiness && lookup.readiness.available) avail.push(lookup.label.toLowerCase());
      const availableNow = avail.length ? avail.join(', ') + '.' : 'nothing yet.';
      const card = el('div', { class: 'card' }, [
        el('div', { class: 'row', style: 'justify-content: space-between' }, [el('div', { class: 'result-title', text: c.name }), el('span', { class: 'chip', text: 'instrument' })]),
        el('div', { class: 'kv', text: c.what }),
        el('div', { class: 'kv' }, [el('span', { style: 'color: var(--write-panel-ink)', text: 'Available now: ' }), el('span', { text: availableNow + (pr.last_check && pr.configured ? ' Last check: ' + pr.last_check + '.' : '') })]),
        el('div', { class: 'row muted small-text' }, [el('span', { text: 'Leaves this machine: ' + c.leaves }), el('span', { text: 'Cost: ' + c.cost })]),
      ]);
      const row = el('div', { class: 'row' });
      if (lookup) {
        const ok = lookup.readiness && lookup.readiness.available;
        row.appendChild(el('button', { class: 'btn' + (ok ? '' : ' off'), type: 'button', text: lookup.label, disabled: ok ? null : true, title: lookup.readiness ? lookup.readiness.reason : '', onclick: () => this.actions.choose(lookup.id) }));
        if (!ok) row.appendChild(el('span', { class: 'muted small-text', text: lookup.readiness ? lookup.readiness.reason : '' }));
      }
      if (start) {
        const ok = start.readiness && start.readiness.available;
        row.appendChild(el('button', { class: 'btn' + (ok ? '' : ' off'), type: 'button', text: start.kind === 'view' ? start.label : 'Start an investigation', disabled: ok ? null : true, title: start.readiness ? start.readiness.reason : '', onclick: () => this.actions.choose(start.id) }));
        if (!ok) row.appendChild(el('span', { class: 'muted small-text', text: start.readiness ? start.readiness.reason : '' }));
      }
      card.appendChild(row);
      if (pr.configured) card.appendChild(el('details', {}, [el('summary', { text: 'Connector details' }), el('div', { class: 'small-text muted', text: `connector ${pr.connector_id || ''} · enabled ${pr.enabled} · credential ${pr.credential} · contract ${pr.contract}` })]));
      grid.appendChild(card);
    }
    v.appendChild(grid);
    v.appendChild(el('div', { class: 'row' }, [el('button', { class: 'btn', type: 'button', text: 'Open the Investigation rooms', onclick: () => { this.places.open('/investigation'); if (this.hooks.onPlace) this.hooks.onPlace(); } })]));
  }
}
