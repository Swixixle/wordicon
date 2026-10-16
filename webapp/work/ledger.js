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
    } catch (e) { /* the reporter never blocks the room */ }
    document.addEventListener('visibilitychange', () => this.note(document.hidden ? 'visibility_hidden' : 'visibility_visible', {}));
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
    if (!this.timer) this.timer = setTimeout(() => this.flush(), 15000);
  }

  flush(beacon) {
    clearTimeout(this.timer); this.timer = 0;
    if (!this.queue.length) return;
    const events = this.queue.splice(0, 100);
    const body = JSON.stringify({ events });
    if (beacon && navigator.sendBeacon) {
      try { navigator.sendBeacon('/api/ledger', new Blob([body], { type: 'application/json' })); return; } catch (e) { /* fall through */ }
    }
    fetch('/api/ledger', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body })
      .then(r => { if (r.status === 409) this.enabled = false; })    // the switch is off; stop reporting until it is turned back on
      .catch(() => { this.queue.unshift(...events); });              // kept for the next flush
  }

  setEnabled(on) { this.enabled = !!on; if (!on) { this.queue = []; clearTimeout(this.timer); this.timer = 0; } }
}
