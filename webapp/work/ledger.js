// Durable local attention delivery. Bodies and replay gestures stay outside
// this reporter. Event IDs deduplicate delivery; every intentional visit gets
// its own ID. An unacknowledged beacon stays pending across page restarts.
const TYPES = new Set(['session_start', 'session_end', 'page_shown', 'place_opened', 'place_closed',
  'document_opened', 'result_viewed', 'visibility_hidden', 'visibility_visible', 'import_attempted',
  'question_followed', 'material_carried', 'edit_applied', 'search_performed', 'capture_gap']);
const FIELDS = {id:300, title:120, route:300, page:300, kind:300, revision:300, scope:300};
const ID = /^[A-Za-z0-9_.:-]{1,120}$/;
export class Ledger {
  constructor() {
    this.queue = []; this.timer = 0; this.enabled = null; this.scope = '';
    this.session = this.id('session'); this.inflight = false; this.initialized = false;
    this.gaps = new Set(); this.lastError = ''; this.maxPending = 2000;
  }
  id(prefix) {
    return prefix + '_' + (globalThis.crypto && crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + '_' + Math.random().toString(36).slice(2));
  }
  localISO() {
    const d = new Date(), off = -d.getTimezoneOffset();
    const pad = n => String(Math.abs(n)).padStart(2, '0');
    return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, -1)
      + (off >= 0 ? '+' : '-') + pad(Math.trunc(off / 60)) + ':' + pad(off % 60);
  }
  prefix() { return 'nikodemus.attention.v2.' + this.scope + '.'; }
  event(type, subject) {
    return { event_id: this.id('event'), session_id: this.session, scope_id: this.scope,
      type, at: this.localISO(), subject: subject || {} };
  }
  subject(value) {
    const out = {};
    if (!value || typeof value !== 'object' || Array.isArray(value)) return out;
    for (const [key, limit] of Object.entries(FIELDS)) {
      if (value[key] == null) continue;
      if (!['string', 'number', 'boolean'].includes(typeof value[key])) {
        this.gap('invalid_metadata', 'An activity metadata field had an unsupported shape and was omitted.'); continue;
      }
      const text = String(value[key]); out[key] = text.slice(0, limit);
      if (text.length > limit) this.gap('metadata_shortened', 'An activity label exceeded its metadata limit and was shortened; document content was not changed.');
    }
    // Unknown fields, bodies and authorization values never reach the outbox.
    return out;
  }
  valid(event, scope = this.scope) {
    if (!event || typeof event !== 'object' || Array.isArray(event) || !TYPES.has(event.type)
        || typeof event.event_id !== 'string' || !ID.test(event.event_id)
        || typeof event.session_id !== 'string' || !ID.test(event.session_id) || event.scope_id !== scope
        || typeof event.at !== 'string' || event.at.length > 40
        || !event.subject || typeof event.subject !== 'object' || Array.isArray(event.subject)) return false;
    if (Object.keys(event).some(k => !['event_id','session_id','scope_id','type','at','subject'].includes(k))) return false;
    return Object.entries(event.subject).every(([key, value]) => Object.hasOwn(FIELDS, key)
      && typeof value === 'string' && value.length <= FIELDS[key]);
  }
  gap(kind, title) {
    if (this.gaps.has(kind) || this.enabled === false) return;
    this.gaps.add(kind); this.lastError = title;
    const event = this.event('capture_gap', { kind:kind.slice(0,300), title:title.slice(0,120) });
    this.queue.push(event);
    if (this.scope) {
      try { localStorage.setItem(this.prefix() + event.event_id, JSON.stringify(event)); }
      catch (_) { /* the memory record explicitly says durable storage failed */ }
    }
  }
  async config() {
    try {
      const response = await fetch('/api/ledger/config', { credentials: 'same-origin' });
      if (!response.ok) return false;
      const data = await response.json();
      if (!/^ledger_[a-f0-9]{24}$/.test(data.scope_id || '')) {
        if (data.enabled === false) this.setEnabled(false);
        this.lastError = 'The server has no compatible capture scope; queued activity has not been sent.'; return false;
      }
      this.scope = data.scope_id;
      if (data.enabled === false) { this.setEnabled(false); return false; }
      this.enabled = true;
      for (const event of this.queue) { event.scope_id = this.scope; this.persist(event); }
      return true;
    } catch (_) { this.lastError = 'Capture delivery is waiting for the local server.'; return false; }
  }
  async init() {
    if (this.initialized) return;
    this.initialized = true;
    await this.config();
    document.addEventListener('visibilitychange', () => {
      this.note(document.hidden ? 'visibility_hidden' : 'visibility_visible', {});
      if (document.hidden) this.flush(true);
    });
    window.addEventListener('pagehide', () => { this.note('session_end', {}); this.flush(true); });
    this.note('session_start', {});
  }
  persist(event) {
    if (!this.scope || this.enabled !== true) return;
    try { localStorage.setItem(this.prefix() + event.event_id, JSON.stringify(event)); }
    catch (_) { this.gap('browser_storage_unavailable', 'Browser storage is unavailable; unsent activity may be lost if this page closes.'); }
  }
  pending() {
    const events = new Map(this.queue.map(e => [e.event_id, e]));
    if (this.scope) {
      try {
        for (let i = 0; i < localStorage.length; i++) {
          const key = localStorage.key(i);
          if (!key || !key.startsWith(this.prefix())) continue;
          try {
            const event = JSON.parse(localStorage.getItem(key));
            if (!this.valid(event) || key !== this.prefix() + event.event_id) throw new Error('bad outbox record');
            events.set(event.event_id, event);
          } catch (_) { this.gap('malformed_outbox', 'A queued activity record cannot be read; its original browser record is preserved.'); }
        }
      } catch (_) { this.gap('browser_storage_unavailable', 'Browser storage is unavailable; unsent activity may be lost if this page closes.'); }
    }
    for (const event of this.queue) events.set(event.event_id, event);
    return [...events.values()].sort((a, b) => String(a.at).localeCompare(String(b.at)) || a.event_id.localeCompare(b.event_id));
  }
  status() {
    // Inspection never confirms a scope, emits gaps, sends, or deletes rows.
    // If the server is unavailable, show prior browser queues as unconfirmed.
    const events = new Map(this.queue.filter(e => this.valid(e, e.scope_id)).map(e => [e.event_id, e]));
    const durable = new Set(), scopes = new Set(); let invalid = 0, storageAvailable = true;
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        const match = /^nikodemus\.attention\.v2\.(ledger_[a-f0-9]{24})\.(.+)$/.exec(key || '');
        if (!match || (this.scope && match[1] !== this.scope)) continue;
        scopes.add(match[1]);
        try {
          const event = JSON.parse(localStorage.getItem(key));
          if (!this.valid(event, match[1]) || match[2] !== event.event_id) throw new Error('bad outbox record');
          events.set(event.event_id, event); durable.add(event.event_id);
        } catch (_) { invalid++; }
      }
    } catch (_) { storageAvailable = false; }
    return {enabled:this.enabled, scope_id:this.scope, scope_confirmed:!!this.scope,
      unconfirmed_scope_count:this.scope ? 0 : scopes.size, pending_count:events.size,
      event_ids:[...events.keys()].sort(), durable_count:durable.size,
      memory_only_count:[...events.keys()].filter(id => !durable.has(id)).length,
      invalid_count:invalid, storage_available:storageAvailable,
      last_error:this.lastError, gaps:[...this.gaps].sort()};
  }
  schedule() {
    if (!this.timer && this.enabled !== false && !document.hidden) this.timer = setTimeout(() => this.flush(), 15000);
  }
  note(type, subject) {
    if (this.enabled === false) return;
    if (!TYPES.has(type)) {
      this.gap('unsupported_activity', 'An unsupported activity kind was refused; no content from it was captured.'); this.schedule(); return;
    }
    const count = this.pending().length;
    if (count >= this.maxPending || this.queue.length >= 500) {
      this.gap('outbox_full', 'Activity capture paused because its outbox is full; some new events were not retained.');
      this.schedule(); return;
    }
    const event = this.event(type, this.subject(subject));
    this.queue.push(event); this.persist(event);
    // Memory holds unsaved events; durable rows are re-read by ID when needed.
    if (this.scope) {
      try { if (localStorage.getItem(this.prefix() + event.event_id)) this.queue = this.queue.filter(e => e.event_id !== event.event_id); }
      catch (_) { /* keep the in-memory copy */ }
    }
    if (count + 1 >= 20) { this.flush(); return; }
    this.schedule();
  }
  acknowledge(ids, sent) {
    const allowed = new Set(sent.map(e => e.event_id));
    for (const id of Array.isArray(ids) ? ids : []) {
      if (!allowed.has(id)) continue;
      try { localStorage.removeItem(this.prefix() + id); } catch (_) { /* retry is safe: server deduplicates */ }
      this.queue = this.queue.filter(e => e.event_id !== id);
    }
  }
  async flush(beacon = false) {
    clearTimeout(this.timer); this.timer = 0;
    if (this.enabled === false || this.inflight) return;
    if (!this.scope && !(await this.config())) { this.schedule(); return; }
    const events = this.pending().slice(0, 100);
    if (!events.length) return;
    const body = JSON.stringify({ events });
    if (beacon && navigator.sendBeacon) {
      try { if (navigator.sendBeacon('/api/ledger', body)) return; } catch (_) { /* normal request below */ }
    }
    this.inflight = true;
    try {
      const response = await fetch('/api/ledger', { method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' }, body, keepalive: !!beacon });
      let data = {};
      try { data = await response.json(); } catch (_) { /* no acknowledgement */ }
      if (response.status === 409 && data.code === 'recording_off') { this.setEnabled(false); return; }
      if (!response.ok) { this.lastError = data.error || 'Activity delivery failed; unsent records remain queued.'; return; }
      this.acknowledge(data.acknowledged, events);
      this.lastError = '';
      if (this.pending().length < this.maxPending) this.gaps.delete('outbox_full');
    } catch (_) { this.lastError = 'The local server did not acknowledge activity; its outbox is retained.'; }
    finally { this.inflight = false; if (this.enabled !== false && this.pending().length) this.schedule(); }
  }
  setEnabled(on) {
    this.enabled = !!on;
    if (!on) {
      // Keep already captured memory-only rows too. Only speculative events
      // queued before any confirmed scope may be discarded on first config.
      this.queue = this.queue.filter(event => !!event.scope_id);
      clearTimeout(this.timer); this.timer = 0;
    }
    // Already captured durable pending records are kept, but never transmitted
    // while recording is off. Re-enabling permits acknowledgement and dedup.
    else this.schedule();
  }
}
