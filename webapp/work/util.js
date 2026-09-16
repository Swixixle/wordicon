// workspace-v2 — small shared helpers. No framework, no CDN.

export async function getJSON(url) {
  const r = await fetch(url, { credentials: 'same-origin' });
  let d = null;
  try { d = await r.json(); } catch (e) { d = { error: 'not JSON (HTTP ' + r.status + ')' }; }
  return { ok: r.ok, status: r.status, data: d };
}

export async function postJSON(url, body, method = 'POST') {
  const r = await fetch(url, { method, credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
  let d = null;
  try { d = await r.json(); } catch (e) { d = { error: 'not JSON (HTTP ' + r.status + ')' }; }
  return { ok: r.ok, status: r.status, data: d };
}

export function el(tag, attrs = {}, children = []) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') n.className = v;
    else if (k === 'text') n.textContent = v;
    else if (k === 'html') n.innerHTML = v;   // only ever with escaped/literal markup
    else if (k.startsWith('on') && typeof v === 'function') n.addEventListener(k.slice(2), v);
    else if (k === 'dataset') Object.assign(n.dataset, v);
    else n.setAttribute(k, v === true ? '' : String(v));
  }
  for (const c of [].concat(children)) {
    if (c === null || c === undefined || c === false) continue;
    n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  }
  return n;
}

export function esc(s) { return String(s === null || s === undefined ? '' : s); }

export function clockOf(iso) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }); } catch (e) { return ''; }
}

export function whenOf(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso), now = new Date();
    const same = d.toDateString() === now.toDateString();
    const y = new Date(now); y.setDate(now.getDate() - 1);
    const t = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    if (same) return t;
    if (d.toDateString() === y.toDateString()) return 'yesterday ' + t;
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' + t;
  } catch (e) { return ''; }
}

// UTF-16 index -> code point offset in the same string (the range unit the
// new references carry). Splitting a surrogate pair counts the lone half as
// one point; the snapshot carries the slice itself, so nothing is lost.
export function cpOffset(str, utf16Index) {
  return Array.from(str.slice(0, Math.max(0, utf16Index))).length;
}

export function newId(prefix) {
  const rnd = (typeof crypto !== 'undefined' && crypto.getRandomValues)
    ? Array.from(crypto.getRandomValues(new Uint8Array(12)), b => b.toString(16).padStart(2, '0')).join('')
    : Math.random().toString(16).slice(2) + Date.now().toString(16);
  return prefix + rnd;
}

export function requestKey() { return 'rk_' + newId('').slice(0, 20) + '_' + Date.now().toString(36); }

export function autoTitle(body) {
  for (const line of (body || '').split('\n')) { const t = line.replace(/\s+/g, ' ').trim(); if (t) return t.slice(0, 80); }
  return 'Untitled';
}

let toastTimer = 0;
export function toast(msg, ms = 3200) {
  const t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, ms);
}

export const prefs = {
  get(key, fallback) { try { const v = localStorage.getItem('nikodemus.work.' + key); return v === null ? fallback : JSON.parse(v); } catch (e) { return fallback; } },
  set(key, value) { try { localStorage.setItem('nikodemus.work.' + key, JSON.stringify(value)); } catch (e) { /* a preference that cannot be kept is not an error */ } },
};
