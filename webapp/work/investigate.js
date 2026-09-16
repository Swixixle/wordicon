// workspace-v2 — Investigate (slice B: the cards; slice F: the adapters;
// corrected after the review of 6e5b59c, finding 3).
// Nothing on this page reaches a producer when it opens: readiness is what
// the record says, derived per capability — configured, contract (pinned
// from the producer's source at a named revision), the credential's
// presence, the last explicit check, whether the owner ruled that the
// deployment runs that revision — and a connection check is a separate
// press. A start is a proposal first (what leaves, to whom, what it costs),
// and nothing runs until Start on that proposal. The main card says what
// can be done and why; the contract's routes and sources sit in a details
// disclosure.
import { getJSON, postJSON, el, toast, whenOf } from './util.js';

const CARDS = [
  { producer: 'ethicalalt', name: 'EthicalAlt', what: 'Company and brand ethical research — profiles, incidents, a signed receipt.', lookup: 'investigate.ethicalalt.lookup', start: 'investigate.ethicalalt.start', placeholder: 'a company or brand name' },
  { producer: 'open_case', name: 'Open Case', what: 'Public-record and case investigation — FEC, votes, lobbying; a signed snapshot on request.', lookup: 'investigate.opencase.list', start: 'investigate.opencase.start', snapshot: 'investigate.opencase.snapshot', placeholder: 'a case id (36 characters), your handle, then the subject’s name' },
  { producer: 'public_eye', name: 'PUBLIC EYE', what: 'Article and podcast investigation — jobs, receipts, a public verifier.', lookup: null, start: 'investigate.publiceye.start', placeholder: 'an article or podcast URL' },
  { producer: 'rabbit_hole', name: 'Rabbit Hole', what: 'Your separate application — not Explore related ideas, not EthicalAlt’s deep mode.', lookup: null, start: 'investigate.rabbithole.connect', placeholder: '' },
];

export class Investigate {
  constructor(actions, places, hooks = {}) { this.actions = actions; this.places = places; this.hooks = hooks; this.view = document.getElementById('investigate-view'); this.producers = null; this.packageContract = null; }

  async render() {
    const v = this.view; v.textContent = '';
    v.appendChild(el('h1', { text: 'Investigate' }));
    v.appendChild(el('div', { class: 'muted small-text', text: 'Four instruments. What each can do from here is derived from the record at this moment — no producer is contacted by opening this page.' }));
    const [, prod] = await Promise.all([this.actions.load(), getJSON('/api/producers')]);
    this.producers = prod.ok ? prod.data.producers : {};
    this.packageContract = prod.ok ? prod.data.package_contract : null;
    const grid = el('div', { style: 'display:grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 12px' });
    for (const c of CARDS) grid.appendChild(this.card(c));
    v.appendChild(grid);
    v.appendChild(el('div', { class: 'row' }, [el('button', { class: 'btn', type: 'button', text: 'Open the Investigation rooms', onclick: () => { this.places.open('/investigation'); if (this.hooks.onPlace) this.hooks.onPlace(); } })]));
    if (this.packageContract && this.packageContract.served_by_main === false) {
      v.appendChild(el('div', { class: 'muted small-text', id: 'package-contract-note', text: 'The rooms import signed packages (' + (this.packageContract.what || '').split(' — ')[0] + '). At the pinned revisions that package route is not served by either producer’s main branch — it exists on unpushed branches only — so an import from a deployment of main lands as a named failure (404), never as a record.' }));
    }
  }

  card(c) {
    const p = (this.producers || {})[c.producer] || {};
    const lookup = c.lookup ? this.actions.byId[c.lookup] : null;
    const start = this.actions.byId[c.start];
    const snapshot = c.snapshot ? this.actions.byId[c.snapshot] : null;
    const rdS = (p.readiness && p.readiness.start) || (start && start.readiness && start.readiness.producer) || {};
    const rdL = (p.readiness && p.readiness.lookup) || {};
    const ct = p.contract || null;
    const avail = [];
    if (lookup && lookup.readiness && lookup.readiness.available) avail.push(lookup.label.toLowerCase());
    if (start && start.readiness && start.readiness.available && start.kind !== 'view') avail.push('start an investigation' + (rdS.fixture_only ? ' (fixture producer)' : ''));
    if (snapshot && snapshot.readiness && snapshot.readiness.available) avail.push('take a signed snapshot (a mutation on the producer)');
    const card = el('div', { class: 'card', dataset: { producer: c.producer } }, [
      el('div', { class: 'row', style: 'justify-content: space-between' }, [el('div', { class: 'result-title', text: c.name }), el('span', { class: 'chip', text: 'instrument' })]),
      el('div', { class: 'kv', text: c.what }),
      el('div', { class: 'kv' }, [el('span', { style: 'color: var(--write-panel-ink)', text: 'Available now: ' }), el('span', { class: 'avail', text: avail.length ? avail.join(', ') + '.' : 'nothing yet.' })]),
    ]);
    // the readiness, per capability, from the record — what decides, on the card; the contract's text in details
    const facts = [];
    facts.push(['Connector', rdS.configured ? (rdS.connector_id + (rdS.enabled ? ' · enabled' : ' · disabled')) : (p.connector_kind ? 'none registered' : 'none can be declared yet')]);
    if (p.connector_kind) {
      facts.push(['Contract', ct ? ('read from the producer’s own source (' + (ct.revision_date || '') + ') — what it serves is known from its code, not from a deployment; the routes and the revision are in “The contract, as pinned” below') : (rdS.contract || '—')]);
      facts.push(['Credential', rdS.credential || 'not required']);
      facts.push(['Last check', (rdS.last_check || 'never tried') + (rdS.last_success_at ? ' · last success ' + whenOf(rdS.last_success_at) : '')]);
      facts.push(['Look up', rdL.available ? 'available' : (rdL.reason || 'not available')]);
      facts.push(['Start', rdS.start_available ? ('available' + (rdS.fixture_only ? ' — ' + rdS.reason : '')) : (rdS.reason || 'not available')]);
      facts.push(['Cost', 'unknown here — the producer’s own calls are billed on its side; nothing is priced by this workspace']);
      facts.push(['Live use', rdS.deployment_verified ? ('enabled by your authorization' + (rdS.live_start_ruling && rdS.live_start_ruling.note ? ' — ' + rdS.live_start_ruling.note : '')) : 'not enabled — a real investigation through this connector waits for your authorization below; until then only the fixture producer can be started']);
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
      row.appendChild(el('button', { class: 'btn', type: 'button', text: 'Check the connection', title: 'One read of the producer’s listing (the route its main serves), recorded as an attempt; nothing imported', onclick: async () => {
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
      if (snapshot) {
        const okS = snapshot.readiness && snapshot.readiness.available;
        card.appendChild(el('div', { class: 'row' }, [el('button', { class: 'btn small' + (okS ? '' : ' off'), type: 'button', text: 'Take a signed snapshot…', disabled: okS ? null : true,
          title: 'A separate act: one POST that creates a snapshot row on the producer, re-signs the case file and credits your handle. Proposed first; nothing runs until Start.',
          onclick: () => { const text = input.value.trim(); if (!text) { toast('Name the case id and your handle first (a label may follow).'); input.focus(); return; } this.actions.prepare(snapshot.id, { kind: 'description', text, title: c.name + ' snapshot' }); } }),
          el('span', { class: 'muted small-text', text: 'a mutation on the producer, never part of a start' })]));
      }
      if (!ok) card.appendChild(el('div', { class: 'muted small-text', text: 'Start: ' + (start.readiness ? start.readiness.reason : 'not available') }));
      if (rdS.configured && !rdS.deployment_verified) {
        // the owner authorizes use; the technical check that the deployment runs the revision the contract was
        // read from is the implementer's work, named in the note — the owner is never asked to certify a revision
        const det = el('details', {}, [el('summary', { text: 'Enable live investigations through this connector (owner)' })]);
        const note = el('input', { type: 'text', placeholder: 'who checked this deployment against the pinned contract, and when (kept in the record)', class: 'inv-subject' });
        det.appendChild(el('div', { class: 'muted small-text', text: 'This records your authorization to use this connector for real investigations, and nothing else: it verifies nothing by itself. The technical check — that the deployment serves the contract the adapter was read from — belongs to whoever set the connector up; name them in the note. If the contract is re-read from a later revision, this authorization is asked for again.' }));
        det.appendChild(el('div', { class: 'row' }, [note, el('button', { class: 'btn small', type: 'button', text: 'Authorize live use', onclick: async () => {
          if (!note.value.trim()) { toast('Name who checked the deployment and when — the authorization carries the note.'); return; }
          const r = await postJSON('/api/connectors/' + encodeURIComponent(rdS.connector_id) + '/live-start', { enabled: true, note: note.value.trim() });
          toast(r.ok ? 'Recorded. Live investigations through this connector are enabled by your authorization.' : ('Not recorded: ' + (r.data.error || r.status)));
          this.render();
        } })]));
        card.appendChild(det);
      } else if (rdS.deployment_verified) {
        card.appendChild(el('div', { class: 'row' }, [el('button', { class: 'btn small', type: 'button', text: 'Withdraw the authorization', onclick: async () => { const r = await postJSON('/api/connectors/' + encodeURIComponent(rdS.connector_id) + '/live-start', { enabled: false, note: 'withdrawn' }); toast(r.ok ? 'Withdrawn; live use is disabled again.' : 'Not changed'); this.render(); } })]));
      }
    } else if (start && start.kind === 'view') {
      card.appendChild(el('div', { class: 'muted small-text', text: start.readiness ? start.readiness.reason : '' }));
    }
    if (p.start) {
      const det = el('details', { class: 'contract' }, [el('summary', { text: 'The contract, as pinned' })]);
      if (ct) {
        det.appendChild(el('div', { class: 'small-text muted', text: `${ct.repo} · revision ${ct.revision} (${ct.branch}, ${ct.revision_date}) · read ${ct.read_on}` + (ct.branch_note ? ' · ' + ct.branch_note : '') }));
        for (const [name, r] of Object.entries(ct.routes || {})) {
          det.appendChild(el('div', { class: 'small-text muted', text: `${name}: ${r.method} ${r.path} · auth ${r.auth} · ${r.source}` + (r.request ? ` · request ${r.request}` : '') + ` · reply ${r.reply} · side effects: ${r.side_effects}` + (r.implemented ? '' : ` · not used here: ${r.why_not || ''}`) + (r.separate_action ? ` · ${r.separate_action}` : '') }));
        }
        const ns = (ct.not_served || {}).package_export;
        if (ns) det.appendChild(el('div', { class: 'small-text warn', text: `NOT served by main: ${ns.path} (${ns.what}) — ${ns.served_by}` }));
      } else {
        det.appendChild(el('div', { class: 'small-text muted', text: `${p.start.method} ${p.start.path} · payload ${(p.start.payload || []).join(', ')} · auth ${p.start.auth} · ${p.start.synchronous ? 'synchronous' : 'asynchronous (' + (p.start.status || 'no status route') + ')'} · cancel ${p.start.cancel || 'not supported'} · side effects: ${p.start.side_effects || '—'} · limits: ${p.start.limits || 'unknown'} · source: ${p.contract_source || '—'} · adapter ${p.adapter_version}` }));
      }
      det.appendChild(el('div', { class: 'small-text muted', text: `adapter ${p.adapter_version} · ${p.contract_source || ''}` }));
      card.appendChild(det);
    }
    return card;
  }
}
