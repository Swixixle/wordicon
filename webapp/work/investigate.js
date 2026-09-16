// workspace-v2 — Investigate (slice B: the cards; slice F: the adapters).
// Nothing on this page reaches a producer when it opens: readiness is what
// the record says, derived per capability — configured, contract, the
// credential's presence, the last explicit check, whether the deployment
// was verified for starting — and a connection check is a separate press.
// A start is a proposal first (what leaves, to whom, what it costs), and
// nothing runs until Start on that proposal.
import { getJSON, postJSON, el, toast, whenOf } from './util.js';

const CARDS = [
  { producer: 'ethicalalt', name: 'EthicalAlt', what: 'Company and brand ethical research — profiles, incidents, a signed export.', lookup: 'investigate.ethicalalt.lookup', start: 'investigate.ethicalalt.start', placeholder: 'a company or brand name' },
  { producer: 'open_case', name: 'Open Case', what: 'Public-record and case investigation — FEC, votes, lobbying, signed snapshots.', lookup: 'investigate.opencase.list', start: 'investigate.opencase.start', placeholder: 'a case id (36 characters), then the handle' },
  { producer: 'public_eye', name: 'PUBLIC EYE', what: 'Article and podcast investigation — jobs, receipts, a public verifier.', lookup: null, start: 'investigate.publiceye.start', placeholder: 'an article or podcast URL' },
  { producer: 'rabbit_hole', name: 'Rabbit Hole', what: 'Your separate application — not Explore related ideas, not EthicalAlt’s deep mode.', lookup: null, start: 'investigate.rabbithole.connect', placeholder: '' },
];

export class Investigate {
  constructor(actions, places, hooks = {}) { this.actions = actions; this.places = places; this.hooks = hooks; this.view = document.getElementById('investigate-view'); this.producers = null; }

  async render() {
    const v = this.view; v.textContent = '';
    v.appendChild(el('h1', { text: 'Investigate' }));
    v.appendChild(el('div', { class: 'muted small-text', text: 'Four instruments. What each can do from here is derived from the record at this moment — no producer is contacted by opening this page.' }));
    const [, prod] = await Promise.all([this.actions.load(), getJSON('/api/producers')]);
    this.producers = prod.ok ? prod.data.producers : {};
    const grid = el('div', { style: 'display:grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 12px' });
    for (const c of CARDS) grid.appendChild(this.card(c));
    v.appendChild(grid);
    v.appendChild(el('div', { class: 'row' }, [el('button', { class: 'btn', type: 'button', text: 'Open the Investigation rooms', onclick: () => { this.places.open('/investigation'); if (this.hooks.onPlace) this.hooks.onPlace(); } })]));
  }

  card(c) {
    const p = (this.producers || {})[c.producer] || {};
    const lookup = c.lookup ? this.actions.byId[c.lookup] : null;
    const start = this.actions.byId[c.start];
    const rdS = (p.readiness && p.readiness.start) || (start && start.readiness && start.readiness.producer) || {};
    const rdL = (p.readiness && p.readiness.lookup) || {};
    const avail = [];
    if (lookup && lookup.readiness && lookup.readiness.available) avail.push(lookup.label.toLowerCase());
    if (start && start.readiness && start.readiness.available && start.kind !== 'view') avail.push('start an investigation' + (rdS.fixture_only ? ' (fixture producer)' : ''));
    const card = el('div', { class: 'card', dataset: { producer: c.producer } }, [
      el('div', { class: 'row', style: 'justify-content: space-between' }, [el('div', { class: 'result-title', text: c.name }), el('span', { class: 'chip', text: 'instrument' })]),
      el('div', { class: 'kv', text: c.what }),
      el('div', { class: 'kv' }, [el('span', { style: 'color: var(--write-panel-ink)', text: 'Available now: ' }), el('span', { class: 'avail', text: avail.length ? avail.join(', ') + '.' : 'nothing yet.' })]),
    ]);
    // the readiness, per capability, from the record
    const facts = [];
    facts.push(['Connector', rdS.configured ? (rdS.connector_id + (rdS.enabled ? ' · enabled' : ' · disabled')) : (p.connector_kind ? 'none registered' : 'none can be declared yet')]);
    if (p.connector_kind) {
      facts.push(['Contract', rdS.contract || '—']);
      facts.push(['Credential', rdS.credential || 'not required']);
      facts.push(['Last check', (rdS.last_check || 'never tried') + (rdS.last_success_at ? ' · last success ' + whenOf(rdS.last_success_at) : '')]);
      facts.push(['Look up', rdL.available ? 'available' : (rdL.reason || 'not available')]);
      facts.push(['Start', rdS.start_available ? ('available' + (rdS.fixture_only ? ' — ' + rdS.reason : '')) : (rdS.reason || 'not available')]);
      facts.push(['Deployment verified for starting', rdS.deployment_verified ? ('yes — ruled by ' + ((rdS.live_start_ruling || {}).by || 'owner') + (rdS.live_start_ruling && rdS.live_start_ruling.note ? ': ' + rdS.live_start_ruling.note : '')) : 'no — the adapter’s contract is pinned from source; the deployment has not been verified from here']);
    } else {
      facts.push(['Why', rdS.reason || p.why_unavailable || '—']);
    }
    const dl = el('dl', { class: 'facts' });
    for (const [k, v] of facts) { dl.appendChild(el('dt', { text: k })); dl.appendChild(el('dd', { text: v })); }
    card.appendChild(dl);
    const row = el('div', { class: 'row' });
    if (lookup) {
      const ok = lookup.readiness && lookup.readiness.available;
      row.appendChild(el('button', { class: 'btn' + (ok ? '' : ' off'), type: 'button', text: lookup.label, disabled: ok ? null : true, title: lookup.readiness ? lookup.readiness.reason : '', onclick: () => this.actions.choose(lookup.id) }));
    }
    if (rdS.configured && rdS.connector_id) {
      row.appendChild(el('button', { class: 'btn', type: 'button', text: 'Check the connection', title: 'One read of the producer’s origin, recorded as an attempt; nothing imported', onclick: async () => {
        const r = await postJSON('/api/connectors/' + encodeURIComponent(rdS.connector_id) + '/check', {});
        toast(r.ok ? ('Checked: ' + (r.data.status || r.data.outcome || 'answered') + (r.data.detail ? ' — ' + r.data.detail : '')) : ('Check failed: ' + (r.data.error || r.status)), 6000);
        this.render();
      } }));
    }
    card.appendChild(row);
    if (start && start.kind !== 'view' && p.connector_kind) {
      const input = el('input', { type: 'text', placeholder: c.placeholder, 'aria-label': 'What to investigate with ' + c.name, class: 'inv-subject' });
      const ok = start.readiness && start.readiness.available;
      const go = el('button', { class: 'btn' + (ok ? ' primary' : ' off'), type: 'button', text: 'Start an investigation…', disabled: ok ? null : true, title: ok ? 'Proposes first: what leaves, to whom, what it costs. Nothing runs until Start.' : (start.readiness ? start.readiness.reason : '') });
      go.addEventListener('click', () => {
        const text = input.value.trim();
        if (!text) { toast('Name ' + c.placeholder + ' first.'); input.focus(); return; }
        this.actions.prepare(start.id, { kind: 'description', text, title: c.name });
      });
      card.appendChild(el('div', { class: 'row' }, [input, go]));
      if (!ok) card.appendChild(el('div', { class: 'muted small-text', text: 'Start: ' + (start.readiness ? start.readiness.reason : 'not available') }));
      if (rdS.configured && !rdS.deployment_verified) {
        const det = el('details', {}, [el('summary', { text: 'Record a verification ruling (owner)' })]);
        const note = el('input', { type: 'text', placeholder: 'how the deployment was verified (kept in the record)', class: 'inv-subject' });
        det.appendChild(el('div', { class: 'muted small-text', text: 'Starting live is enabled only by your ruling that this connector’s deployment was verified against the pinned contract. This records the ruling; it verifies nothing by itself.' }));
        det.appendChild(el('div', { class: 'row' }, [note, el('button', { class: 'btn small', type: 'button', text: 'Record: verified for starting', onclick: async () => {
          if (!note.value.trim()) { toast('Say how it was verified — the ruling carries the note.'); return; }
          const r = await postJSON('/api/connectors/' + encodeURIComponent(rdS.connector_id) + '/live-start', { enabled: true, note: note.value.trim() });
          toast(r.ok ? 'Recorded. Starting is enabled for this connector by your ruling.' : ('Not recorded: ' + (r.data.error || r.status)));
          this.render();
        } })]));
        card.appendChild(det);
      } else if (rdS.deployment_verified) {
        card.appendChild(el('div', { class: 'row' }, [el('button', { class: 'btn small', type: 'button', text: 'Withdraw the verification ruling', onclick: async () => { const r = await postJSON('/api/connectors/' + encodeURIComponent(rdS.connector_id) + '/live-start', { enabled: false, note: 'withdrawn' }); toast(r.ok ? 'Withdrawn; starting is disabled again.' : 'Not changed'); this.render(); } })]));
      }
    } else if (start && start.kind === 'view') {
      card.appendChild(el('div', { class: 'muted small-text', text: start.readiness ? start.readiness.reason : '' }));
    }
    if (p.start) {
      card.appendChild(el('details', {}, [el('summary', { text: 'The contract, as pinned' }), el('div', { class: 'small-text muted', text: `${p.start.method} ${p.start.path} · payload ${(p.start.payload || []).join(', ')} · auth ${p.start.auth} · ${p.start.synchronous ? 'synchronous' : 'asynchronous (' + (p.start.status || 'no status route') + ')'} · cancel ${p.start.cancel || 'not supported'} · side effects: ${p.start.side_effects || '—'} · limits: ${p.start.limits || 'unknown'} · source: ${p.contract_source || '—'} · adapter ${p.adapter_version}` })]));
    }
    return card;
  }
}
