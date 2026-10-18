// Durable local attention delivery. Bodies and replay gestures stay outside
// this reporter. Event IDs deduplicate delivery; every intentional visit gets
// its own ID. An unacknowledged beacon stays pending across page restarts.
const TYPES = new Set(['session_start', 'session_end', 'page_shown', 'place_opened', 'place_closed',
  'document_opened', 'result_viewed', 'visibility_hidden', 'visibility_visible', 'import_attempted',
  'question_followed', 'material_carried', 'edit_applied', 'search_performed', 'capture_gap',
  'activity_state', 'activity_interval', 'material_selected', 'document_edited', 'document_saved']);
const FIELDS = {id:300, title:120, route:300, page:300, kind:300, revision:300, scope:300};
const ID = /^[A-Za-z0-9_.:-]{1,120}$/;
const ACTIVITY_POLICY = 'visibility_focus_idle.v1', IDLE_MS = 60000, CHECKPOINT_MS = 15000, MAX_INTERVAL_MS = 30000;
const ACTIVITY_STATES = new Set(['foreground_active_estimate', 'foreground_idle_estimate']);
const INTERVAL_REASONS = new Set(['checkpoint', 'idle', 'input', 'focus', 'blur', 'hidden', 'visible', 'pagehide', 'recording_off', 'context']);
function credentialLike(text) {
  if (/\b(?:sk-(?:ant-)?[A-Za-z0-9_-]{8,}|xox[baprs]-[A-Za-z0-9-]{8,}|gh[pousr]_[A-Za-z0-9]{8,}|github_pat_[A-Za-z0-9_]{8,}|AKIA[A-Z0-9]{16})\b/.test(text)
      || /\bBearer\s+[^\s"'<>\\]+/i.test(text)
      || /\b(?:api[_-]?key|x-api-key|access[_-]?token|refresh[_-]?token|password|client[_-]?secret|authorization|cookie)["']?\s*[:=]\s*["']?[^\s"'<>;&,}]+/i.test(text)
      || /https?:\/\/[^\s/@]+@/i.test(text)) return true;
  const secretQuery = new Set(['api_key','apikey','x_api_key','access_token','refresh_token','id_token','auth_token','token','password','passwd','secret','client_secret','credential','credentials','private_key','secret_access_key','session_key','key','auth','signature','sig','session','session_id','x_amz_credential','x_amz_signature','x_amz_security_token']);
  for (const match of text.matchAll(/[?&]([^=&#\s]+)=/g)) {
    let name = match[1]; try { name = decodeURIComponent(name); } catch (_) { /* keep the literal parameter */ }
    if (secretQuery.has(name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, ''))) return true;
  }
  return false;
}
function validInterval(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
      || Object.keys(value).sort().join(',') !== 'duration_ms,end_at,idle_after_ms,policy,reason,start_at,state'
      || value.policy !== ACTIVITY_POLICY || !ACTIVITY_STATES.has(value.state)
      || !INTERVAL_REASONS.has(value.reason) || value.idle_after_ms !== IDLE_MS
      || !Number.isInteger(value.duration_ms) || value.duration_ms <= 0 || value.duration_ms > MAX_INTERVAL_MS
      || typeof value.start_at !== 'string' || typeof value.end_at !== 'string'
      || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?(?:Z|[+-]\d{2}:\d{2})$/.test(value.start_at)
      || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?(?:Z|[+-]\d{2}:\d{2})$/.test(value.end_at)) return false;
  const start = Date.parse(value.start_at), end = Date.parse(value.end_at);
  return Number.isFinite(start) && Number.isFinite(end) && end >= start && Math.abs(end - start - value.duration_ms) <= 2000;
}
export class Ledger {
  constructor() {
    this.queue = []; this.timer = 0; this.enabled = null; this.scope = ''; this.scopeConflict = false;
    this.session = this.id('session'); this.inflight = false; this.initialized = false;
    this.gaps = new Set(); this.lastError = ''; this.maxPending = 2000;
    this.activity = null; this.activityTimer = 0; this.activityContext = {};
    this.focused = false; this.pageEnded = false; this.activityReady = false;
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
      const text = String(value[key]);
      if (credentialLike(text)) { this.gap('metadata_redacted', 'Credential-like activity metadata was omitted before browser storage.'); continue; }
      out[key] = text.slice(0, limit);
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
    if (Object.keys(event).some(k => !['event_id','session_id','scope_id','type','at','subject','interval'].includes(k))) return false;
    if (event.type === 'activity_interval' ? !validInterval(event.interval) : event.interval !== undefined) return false;
    return Object.entries(event.subject).every(([key, value]) => Object.hasOwn(FIELDS, key)
      && typeof value === 'string' && value.length <= FIELDS[key] && !credentialLike(value));
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
      if (this.scope && this.scope !== data.scope_id) {
        this.scopeConflict = true;
        this.activityCheck('context', true);
        this.gap('workspace_scope_changed', 'Workspace identity changed; prior activity stays here. Open a fresh page for the new workspace.');
        for (const event of this.queue) if (event.scope_id === this.scope) this.persist(event);
        clearTimeout(this.timer); this.timer = 0; clearTimeout(this.activityTimer); this.activityTimer = 0;
        return false;
      }
      this.scope = data.scope_id;
      if (data.enabled === false) { this.setEnabled(false); return false; }
      this.enabled = true;
      for (const event of this.queue) {
        if (!event.scope_id) event.scope_id = this.scope;
        if (event.scope_id === this.scope) this.persist(event);
      }
      this.activityCheck('visible');
      return true;
    } catch (_) { this.lastError = 'Capture delivery is waiting for the local server.'; return false; }
  }
  async init() {
    if (this.initialized) return;
    this.initialized = true;
    await this.config();
    document.addEventListener('visibilitychange', () => {
      this.activityCheck(document.hidden ? 'hidden' : 'visible');
      this.note(document.hidden ? 'visibility_hidden' : 'visibility_visible', {});
      if (document.hidden) this.flush(true);
    });
    window.addEventListener('focus', () => { this.focused = true; this.activityCheck('focus'); });
    window.addEventListener('blur', () => { this.focused = false; this.activityCheck('blur'); });
    window.addEventListener('pagehide', () => { this.pageEnded = true; this.activityCheck('pagehide'); this.note('session_end', {}); this.flush(true); });
    window.addEventListener('pageshow', () => { this.pageEnded = false; this.focused = !!document.hasFocus?.(); this.activityCheck('visible'); });
    // Only occurrence is used. Never inspect a key, value, target, coordinate,
    // selection body or clipboard; no individual gesture is stored.
    const pulse = () => this.activityPulse();
    for (const type of ['keydown', 'pointerdown', 'scroll', 'input']) document.addEventListener(type, pulse, {passive:true, capture:true});
    this.note('session_start', {});
    this.focused = !!document.hasFocus?.(); this.activityReady = true; this.activityCheck('visible');
  }
  activityClock() { return {mono:Math.round(globalThis.performance?.now?.() ?? Date.now()), wall:Date.now()}; }
  activityState() {
    if (this.enabled !== true || this.scopeConflict || this.pageEnded || document.hidden || !this.focused) return 'inactive';
    return this.activity && this.activityClock().mono - this.activity.lastInput >= IDLE_MS ? 'foreground_idle_estimate' : 'foreground_active_estimate';
  }
  activitySegment(endMono, endWall, reason) {
    const a = this.activity, duration = endMono - a.mono;
    if (duration > 0 && ACTIVITY_STATES.has(a.state)) this.note('activity_interval', this.activityContext, {
      policy:ACTIVITY_POLICY, state:a.state, start_at:new Date(a.wall).toISOString(), end_at:new Date(endWall).toISOString(),
      duration_ms:duration, idle_after_ms:IDLE_MS, reason});
    a.mono = endMono; a.wall = endWall;
  }
  activityCheck(reason = 'checkpoint', forceInactive = false) {
    if (!this.activityReady) return;
    clearTimeout(this.activityTimer); this.activityTimer = 0;
    const now = this.activityClock();
    if (!this.activity) this.activity = {...now, lastInput:now.mono, state:'inactive'};
    const a = this.activity, elapsed = now.mono - a.mono;
    if (elapsed < 0 || elapsed > MAX_INTERVAL_MS || Math.abs(now.wall - a.wall - elapsed) > 2000) {
      if (ACTIVITY_STATES.has(a.state)) this.gap('activity_time_unobserved', 'Activity timing was interrupted; the unobserved interval was not counted.');
      a.mono = now.mono; a.wall = now.wall;
    } else {
      const idleAt = a.lastInput + IDLE_MS;
      if (a.state === 'foreground_active_estimate' && idleAt > a.mono && idleAt < now.mono) {
        this.activitySegment(idleAt, a.wall + idleAt - a.mono, 'idle');
        a.state = 'foreground_idle_estimate';
        this.note('activity_state', {...this.activityContext, kind:a.state});
      }
      this.activitySegment(now.mono, now.wall, reason);
    }
    const next = forceInactive ? 'inactive' : this.activityState();
    if (a.state !== next) {
      a.state = next;
      this.note('activity_state', {...this.activityContext, kind:next});
    }
    if (this.enabled === true && !this.scopeConflict && !this.pageEnded && !document.hidden && this.focused) {
      this.activityTimer = setTimeout(() => this.activityCheck(), CHECKPOINT_MS);
    }
  }
  activityPulse() {
    if (!this.activityReady || this.enabled !== true || this.scopeConflict || this.pageEnded || document.hidden || !this.focused) return;
    const now = this.activityClock();
    if (!this.activity || this.activity.state !== 'foreground_active_estimate' || now.mono - this.activity.lastInput >= IDLE_MS) this.activityCheck('input');
    this.activity.lastInput = now.mono;
    if (this.activity.state !== 'foreground_active_estimate') this.activityCheck('input');
  }
  context(subject) {
    const next = {};
    const safe = this.subject(subject);
    for (const key of ['id','revision','page','kind','scope']) if (safe[key] != null) next[key] = safe[key];
    if (JSON.stringify(next) === JSON.stringify(this.activityContext)) return;
    this.activityCheck('context'); this.activityContext = next;
  }
  persist(event) {
    if (!this.scope || this.enabled !== true) return;
    try { localStorage.setItem(this.prefix() + event.event_id, JSON.stringify(event)); }
    catch (_) { this.gap('browser_storage_unavailable', 'Browser storage is unavailable; unsent activity may be lost if this page closes.'); }
  }
  pending() {
    const scoped = () => this.queue.filter(e => !this.scope || e.scope_id === this.scope);
    const events = new Map(scoped().map(e => [e.event_id, e]));
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
    for (const event of scoped()) events.set(event.event_id, event);
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
    return {enabled:this.enabled, scope_id:this.scope, scope_confirmed:!!this.scope && !this.scopeConflict, scope_conflict:this.scopeConflict,
      unconfirmed_scope_count:this.scope ? 0 : scopes.size, pending_count:events.size,
      event_ids:[...events.keys()].sort(), durable_count:durable.size,
      memory_only_count:[...events.keys()].filter(id => !durable.has(id)).length,
      invalid_count:invalid, storage_available:storageAvailable,
      last_error:this.lastError, gaps:[...this.gaps].sort()};
  }
  schedule() {
    if (!this.timer && this.enabled !== false && !this.scopeConflict && !document.hidden) this.timer = setTimeout(() => this.flush(), 15000);
  }
  note(type, subject, interval) {
    if (this.enabled === false || this.scopeConflict) return;
    if (type === 'page_shown') this.context({page:subject?.page, id:subject?.id, scope:subject?.scope});
    else if (type === 'document_opened' || type === 'result_viewed') this.context({page:this.activityContext.page, id:subject?.id, revision:subject?.revision, kind:type === 'document_opened' ? 'document' : subject?.kind});
    if (!TYPES.has(type)) {
      this.gap('unsupported_activity', 'An unsupported activity kind was refused; no content from it was captured.'); this.schedule(); return;
    }
    const count = this.pending().length;
    if (count >= this.maxPending || this.queue.length >= 500) {
      this.gap('outbox_full', 'Activity capture paused because its outbox is full; some new events were not retained.');
      this.schedule(); return;
    }
    const event = this.event(type, this.subject(subject));
    if (type === 'activity_interval') {
      if (!validInterval(interval)) { this.gap('invalid_activity_interval', 'An invalid activity estimate was refused.'); return; }
      event.interval = interval;
    }
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
    if (this.scopeConflict) {
      // A retry may make old memory rows durable under their original scope;
      // it must never send them to the replacement workspace.
      for (const event of this.queue) if (event.scope_id === this.scope) this.persist(event);
      return;
    }
    if (this.enabled === false || this.inflight) return;
    // A page that never received its routing scope must wait for reopen,
    // not start a configuration request while it is being discarded.
    if (!this.scope && (this.pageEnded || document.hidden)) return;
    if (!this.scope && !(await this.config())) { this.schedule(); return; }
    // A boundary note can fill the batch during pagehide, before its caller
    // reaches flush(true). WebKit refuses an ordinary fetch from that dying
    // document. Use the lifecycle transport for EVERY flush at that boundary;
    // only a later explicit acknowledgement may remove these durable IDs.
    const departing = this.pageEnded || document.hidden;
    beacon = beacon || departing;
    const events = this.pending().slice(0, 100);
    if (!events.length) return;
    const body = JSON.stringify({ events });
    if (beacon && navigator.sendBeacon) {
      try { if (navigator.sendBeacon('/api/ledger', body)) return; } catch (_) { /* retained on teardown; visible-page fallback below */ }
    }
    if (departing) {
      this.lastError = 'Capture is queued for acknowledgement when this workspace reopens.';
      return;
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
    if (!on && this.enabled === true) this.activityCheck('recording_off', true);
    this.enabled = !!on;
    if (!on) {
      // Keep already captured memory-only rows too. Only speculative events
      // queued before any confirmed scope may be discarded on first config.
      this.queue = this.queue.filter(event => !!event.scope_id);
      clearTimeout(this.timer); this.timer = 0;
      clearTimeout(this.activityTimer); this.activityTimer = 0;
    }
    // Already captured durable pending records are kept, but never transmitted
    // while recording is off. Re-enabling permits acknowledgement and dedup.
    else { this.schedule(); this.activityCheck('visible'); }
  }
}
