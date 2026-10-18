// Optional scratch-only request evidence. Never logs bodies, cookies, auth,
// arbitrary headers or query strings. Initiator stacks identify app functions;
// the fixed diagnostic filename stays in JOURNEY_OUT, outside source control.
const fs = require('fs');
const path = require('path');
async function attachLedgerTrace(context, out, label) {
  const filename = path.join(out, label + '.ledger-trace.jsonl');
  const safeURL = value => { try { const u = new URL(value); u.search = ''; u.hash = ''; return u.href; } catch { return String(value).split(/[?#]/)[0]; } };
  const headers = h => Object.fromEntries(Object.entries(h).filter(([k]) => /^(origin|referer|host|content-type|content-length|sec-fetch-.*|access-control-.*|vary|location)$/i.test(k)).map(([k,v]) => [k, /referer|location/i.test(k) ? safeURL(v) : v]));
  const emit = value => fs.appendFileSync(filename, JSON.stringify({at:new Date().toISOString(), ...value}) + '\n');
  const relevant = value => { try { return new URL(value).pathname.startsWith('/api/ledger'); } catch { return false; } };
  await context.exposeBinding('__ledgerTrace', (_source, value) => emit(value));
  await context.addInitScript(() => {
    const note = (kind, value, options = {}) => {
      try {
        const u = new URL(value, location.href); if (!u.pathname.startsWith('/api/ledger')) return;
        u.search = ''; u.hash = '';
        window.__ledgerTrace({kind, page_origin:location.origin, page_path:location.pathname,
          raw_path:String(value).split(/[?#]/)[0], url:u.href, method:options.method || (kind === 'beacon_initiator' ? 'POST' : 'GET'),
          content_type:new Headers(options.headers || {}).get('Content-Type'),
          initiator:(new Error()).stack}).catch(() => {});
      } catch (_) { /* diagnostics never change request behavior */ }
    };
    const original = window.fetch;
    window.fetch = function(input, options) { note('fetch_initiator', typeof input === 'string' ? input : input.url, options); return original.call(this, input, options); };
    const beacon = navigator.sendBeacon.bind(navigator);
    navigator.sendBeacon = function(url, body) { note('beacon_initiator', url); return beacon(url, body); };
  });
  context.on('request', r => { if (relevant(r.url())) emit({kind:'request', url:safeURL(r.url()), method:r.method(), resource_type:r.resourceType(), headers:headers(r.headers())}); });
  context.on('response', r => { if (relevant(r.url())) emit({kind:'response', url:safeURL(r.url()), method:r.request().method(), status:r.status(), headers:headers(r.headers())}); });
  context.on('requestfailed', r => { if (relevant(r.url())) emit({kind:'requestfailed', url:safeURL(r.url()), method:r.method(), failure:r.failure()}); });
  context.on('page', p => {
    p.on('console', m => { if (/ledger|access.control|cors/i.test(m.text())) emit({kind:'console', type:m.type(), message:m.text(), location:m.location()}); });
    p.on('pageerror', e => emit({kind:'pageerror', message:e.message}));
  });
  return filename;
}
module.exports = {attachLedgerTrace};
