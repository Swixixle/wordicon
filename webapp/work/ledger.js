// workspace-v2 — the Ledger's reporter (2026-10-16, his ruling: "all
// routes, saved info time stamped and documented in a retrievable way" —
// events first, no keystrokes). This module only REPORTS: it queues
// attention events (doors, pages, documents, results, visibility) and
// posts them in batches to the owner's own store. It reads nothing, sends
// nothing anywhere else, and stops the moment the Settings switch says so
// (a 409 from the store is the switch speaking; reporting stops at once).
// Events carry ids and short titles, never bodies.

export class Ledger {
  constructor() { this.queue = []; this.timer = 0; this.enabled = true; }

  async init() {
    try {
      const r = await fetch('/api/ledger/config', { credentials: 'same-origin' });
      const d = await r.json();
      this.enabled = d.enabled !== false;
      // off means nothing is SENT, not merely nothing new queued: the
      // session_start noted below before a slow answer, or queued by an
      // earlier page, is dropped too — a switched-off shell makes no
      // /api/ledger request at all (W2; the desk's inline reporter agrees)
      if (!this.enabled) { this.queue = []; clearTimeout(this.timer); this.timer = 0; }
    } catch (e) { /* the reporter never blocks the room */ }
    document.addEventListener('visibilitychange', () => {
      this.note(document.hidden ? 'visibility_hidden' : 'visibility_visible', {});
      // hand the queue over ONLY when hiding (a plain-string beacon —
      // teardown-safe). Returning to a tab does no work at all: a reporter
      // that acts on arrival perturbs the very attention it records.
      if (document.hidden) this.flush(true);
    });
    window.addEventListener('pagehide', () => { this.note('session_end', {}); this.flush(true); });
    this.note('session_start', {});
  }

  // the page's clock, kept in the owner's own time with its offset named —
  // the store adds its own UTC receive clock beside it: two clocks, labeled
  localISO() {
    const d = new Date(), off = -d.getTimezoneOffset();
    const pad = n => String(Math.abs(n)).padStart(2, '0');
    return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, -1)
      + (off >= 0 ? '+' : '-') + pad(Math.trunc(off / 60)) + ':' + pad(off % 60);
  }

  note(type, subject) {
    if (!this.enabled) return;
    this.queue.push({ type, at: this.localISO(), subject: subject || {} });
    if (this.queue.length > 500) this.queue.splice(0, this.queue.length - 500);   // attention data, not a debt: cap, never balloon
    if (this.queue.length >= 20) { this.flush(); return; }
    // no timer while the tab is hidden: a reporter that wakes a background
    // tab changes how the rest of the page behaves while away (polls run
    // that throttling would have held) — attention data must not create
    // attention; the queue hands over at the visibility boundary instead
    if (!this.timer && !document.hidden) this.timer = setTimeout(() => this.flush(), 15000);
  }

  flush(beacon) {
    clearTimeout(this.timer); this.timer = 0;
    if (!this.queue.length) return;
    const events = this.queue.splice(0, 100);
    const body = JSON.stringify({ events });
    if (beacon && navigator.sendBeacon) {
      // a PLAIN-STRING beacon: text/plain is a simple request, so WebKit's
      // teardown never flags it (a json-typed Blob at pagehide surfaced as
      // "access control checks" page errors); the store force-parses the
      // body whatever the type says
      try { navigator.sendBeacon('/api/ledger', body); return; } catch (e) { /* fall through */ }
    }
    fetch('/api/ledger', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body })
      .then(r => { if (r.status === 409) this.enabled = false; })    // the switch is off; stop reporting until it is turned back on
      .catch(() => { this.queue.unshift(...events); });              // kept for the next flush
  }

  setEnabled(on) { this.enabled = !!on; if (!on) { this.queue = []; clearTimeout(this.timer); this.timer = 0; } }
}
