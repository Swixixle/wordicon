// workspace-v2 — the structured document on the page (slice C). The same
// contract as scripts/document_schema.py, in the browser: schema v1 for
// ProseMirror, projection v1 (leaf textblocks joined by two LF, a hard
// break one LF, nothing appended), the canonical JSON, the versioned
// fingerprint, the plain import, and the position map between ProseMirror
// positions, UTF-16 offsets and code points. tests/fixtures/
// projection_vectors.json is the shared proof that both sides agree.
import { Schema } from '/work/vendor/prosemirror.js';

export const SCHEMA_VERSION = 1;
export const PROJECTION_VERSION = 1;
const SAFE_HREF = /^(https?:\/\/|mailto:)[^\s\x00-\x1f]+$/i;
const MARK_ORDER = { link: 0, strong: 1, em: 2 };

export const schema = new Schema({
  nodes: {
    doc: { content: 'block+' },
    paragraph: { group: 'block', content: 'inline*', parseDOM: [{ tag: 'p' }], toDOM() { return ['p', 0]; } },
    heading: { group: 'block', content: 'inline*', attrs: { level: { default: 1 } }, defining: true,
      parseDOM: [{ tag: 'h1', attrs: { level: 1 } }, { tag: 'h2', attrs: { level: 2 } }, { tag: 'h3', attrs: { level: 3 } }],
      toDOM(n) { return ['h' + n.attrs.level, 0]; } },
    blockquote: { group: 'block', content: 'block+', defining: true, parseDOM: [{ tag: 'blockquote' }], toDOM() { return ['blockquote', 0]; } },
    bullet_list: { group: 'block', content: 'list_item+', parseDOM: [{ tag: 'ul' }], toDOM() { return ['ul', 0]; } },
    ordered_list: { group: 'block', content: 'list_item+', attrs: { order: { default: 1 } },
      parseDOM: [{ tag: 'ol', getAttrs(dom) { return { order: dom.hasAttribute('start') ? +dom.getAttribute('start') : 1 }; } }],
      toDOM(n) { return n.attrs.order === 1 ? ['ol', 0] : ['ol', { start: n.attrs.order }, 0]; } },
    list_item: { content: 'paragraph (paragraph | bullet_list | ordered_list)*', defining: true, parseDOM: [{ tag: 'li' }], toDOM() { return ['li', 0]; } },
    text: { group: 'inline' },
    hard_break: { inline: true, group: 'inline', selectable: false, parseDOM: [{ tag: 'br' }], toDOM() { return ['br']; } },
  },
  marks: {
    link: { attrs: { href: {} }, inclusive: false, parseDOM: [{ tag: 'a[href]', getAttrs(dom) { const h = dom.getAttribute('href') || ''; return SAFE_HREF.test(h) ? { href: h } : false; } }],
      toDOM(m) { return ['a', { href: m.attrs.href, rel: 'noopener noreferrer', target: '_blank' }, 0]; } },
    strong: { parseDOM: [{ tag: 'strong' }, { tag: 'b' }, { style: 'font-weight', getAttrs: v => /^(bold|[5-9]\d\d)$/.test(v) && null }], toDOM() { return ['strong', 0]; } },
    em: { parseDOM: [{ tag: 'i' }, { tag: 'em' }, { style: 'font-style=italic' }], toDOM() { return ['em', 0]; } },
  },
});

// ---- canonical node form (what the server validates and hashes) ----------------
export function canonicalDoc(pmDoc) {
  const marks = ms => ms.map(m => (m.type.name === 'link' ? { type: 'link', attrs: { href: m.attrs.href } } : { type: m.type.name }))
    .sort((a, b) => MARK_ORDER[a.type] - MARK_ORDER[b.type]);
  const inline = node => { const out = []; node.forEach(ch => { if (ch.isText) out.push({ type: 'text', text: ch.text, marks: marks(ch.marks) }); else if (ch.type.name === 'hard_break') out.push({ type: 'hard_break' }); }); return out; };
  const block = node => {
    const t = node.type.name;
    if (t === 'paragraph') return { type: 'paragraph', content: inline(node) };
    if (t === 'heading') return { type: 'heading', attrs: { level: node.attrs.level }, content: inline(node) };
    if (t === 'blockquote') { const c = []; node.forEach(ch => c.push(block(ch))); return { type: 'blockquote', content: c }; }
    if (t === 'bullet_list' || t === 'ordered_list') {
      const items = []; node.forEach(li => { const c = []; li.forEach(ch => c.push(block(ch))); items.push({ type: 'list_item', content: c }); });
      return t === 'ordered_list' ? { type: t, attrs: { order: node.attrs.order }, content: items } : { type: t, content: items };
    }
    throw new Error('not a v1 block: ' + t);
  };
  const content = []; pmDoc.forEach(b => content.push(block(b)));
  return { type: 'doc', content };
}

// JSON with sorted keys and no whitespace — byte-identical to Python's
export function canonicalString(obj) {
  const walk = v => {
    if (Array.isArray(v)) return '[' + v.map(walk).join(',') + ']';
    if (v && typeof v === 'object') return '{' + Object.keys(v).sort().map(k => JSON.stringify(k) + ':' + walk(v[k])).join(',') + '}';
    if (typeof v === 'string') return jsonString(v);
    return JSON.stringify(v);
  };
  return walk(obj);
}
// Python's json.dumps(ensure_ascii=False) escapes only ", \ and control characters below 0x20
function jsonString(s) {
  let out = '"';
  for (const ch of s) {
    const c = ch.codePointAt(0);
    if (ch === '"') out += '\\"'; else if (ch === '\\') out += '\\\\';
    else if (c === 0x0a) out += '\\n'; else if (c === 0x0d) out += '\\r'; else if (c === 0x09) out += '\\t';
    else if (c === 0x08) out += '\\b'; else if (c === 0x0c) out += '\\f';
    else if (c < 0x20) out += '\\u' + c.toString(16).padStart(4, '0');
    else out += ch;
  }
  return out + '"';
}

// ---- projection v1 ------------------------------------------------------------------
export function leafBlocks(doc) {
  const out = [];
  const walk = n => { const t = n.type ? n.type.name : n.type; if (t === 'paragraph' || t === 'heading') { out.push(n); return; } (n.forEach ? n.forEach(walk) : (n.content || []).forEach(walk)); };
  (doc.forEach ? doc.forEach(walk) : (doc.content || []).forEach(walk));
  return out;
}
export function blockText(block) {
  let s = '';
  const each = fn => (block.forEach ? block.forEach(fn) : (block.content || []).forEach(fn));
  each(n => { const t = n.type ? (n.type.name || n.type) : n.type; if (t === 'text' || n.isText) s += n.text; else if (t === 'hard_break') s += '\n'; });
  return s;
}
export function project(doc) { return leafBlocks(doc).map(blockText).join('\n\n'); }

// ---- plain import ----------------------------------------------------------------------
export function convertible(body) {
  if (typeof body !== 'string') return { ok: false, why: 'not text' };
  if (body.includes('\r')) return { ok: false, why: 'carriage return (CR) in the text — the structured schema keeps LF only; the plain path keeps the text exactly' };
  if (/[\x00-\x08\x0b-\x1f\x7f]/.test(body)) return { ok: false, why: 'a control character in the text — the plain path keeps it exactly' };
  return { ok: true, why: '' };
}
export function parsePlain(body) {
  const c = convertible(body); if (!c.ok) throw new Error(c.why);
  const blocks = body.split('\n\n').map(piece => {
    const content = [];
    piece.split('\n').forEach((line, i) => { if (i) content.push(schema.nodes.hard_break.create()); if (line) content.push(schema.text(line)); });
    return schema.nodes.paragraph.create(null, content);
  });
  return schema.nodes.doc.create(null, blocks);
}
export function fromJSON(json) { return schema.nodeFromJSON(json); }

// ---- the position map ---------------------------------------------------------------------
export function positionMap(pmDoc) {
  const out = []; let pm = 0, u16 = 0, cp = 0, first = true;
  const cpLen = s => Array.from(s).length;
  const walk = node => {
    const t = node.type.name;
    if (t === 'paragraph' || t === 'heading') {
      if (!first) { out.push({ kind: 'separator', pm, utf16: u16, cp, len_pm: 0, len_utf16: 2, len_cp: 2 }); u16 += 2; cp += 2; }
      first = false; pm += 1;
      node.forEach(n => {
        if (n.isText) { const lu = n.text.length, lc = cpLen(n.text); out.push({ kind: 'text', pm, utf16: u16, cp, len_pm: lu, len_utf16: lu, len_cp: lc }); pm += lu; u16 += lu; cp += lc; }
        else if (n.type.name === 'hard_break') { out.push({ kind: 'hard_break', pm, utf16: u16, cp, len_pm: 1, len_utf16: 1, len_cp: 1 }); pm += 1; u16 += 1; cp += 1; }
      });
      pm += 1; return;
    }
    pm += 1; node.forEach(walk); pm += 1;
  };
  pmDoc.forEach(walk);
  return out;
}
// ProseMirror position → UTF-16 offset in the projected text (bias: a
// position between blocks maps to the end of the preceding block's text;
// inside a text run it maps unit for unit).
export function pmToText(map, pos) {
  let best = 0;
  for (const e of map) {
    if (e.kind === 'separator') continue;
    if (pos >= e.pm && pos <= e.pm + e.len_pm) return e.utf16 + (pos - e.pm);
    if (e.pm + e.len_pm <= pos) best = e.utf16 + e.len_utf16;
  }
  return best;
}
// UTF-16 offset in the projected text → ProseMirror position (an offset
// inside a synthetic separator maps just after the preceding block's text).
export function textToPm(map, off) {
  let best = 0;
  for (const e of map) {
    if (e.kind === 'separator') { if (off >= e.utf16 && off < e.utf16 + e.len_utf16) return best; continue; }
    if (off >= e.utf16 && off <= e.utf16 + e.len_utf16) return e.pm + (off - e.utf16);
    best = e.pm + e.len_pm;
  }
  return best;
}
export function cpOffset(str, utf16Index) { return Array.from(str.slice(0, Math.max(0, utf16Index))).length; }

// ---- fingerprint v2 ------------------------------------------------------------------------
export async function sha256Hex(text) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf), b => b.toString(16).padStart(2, '0')).join('');
}
export async function fingerprintV2(title, titleIsManual, body, canonDoc, docSchema, projectionVersion) {
  const canon = canonicalString({ b: body, m: !!titleIsManual, t: title, d: canonDoc ? canonicalString(canonDoc) : null, s: docSchema, p: projectionVersion });
  return 'fp2_' + (await sha256Hex(canon)).slice(0, 32);
}

// ---- exports from the structure (slice C) ------------------------------------------
// Markdown keeps what the format holds: headings, lists (nested, multi-
// paragraph items), quotes, bold, italic, links; a hard break is a line
// ending in two spaces. Plain text is the projection and nothing else — the
// .txt export is visibly plain.
function mdInline(content) {
  let s = '';
  for (const n of content || []) {
    if (n.type === 'hard_break') { s += '  \n'; continue; }
    let t = n.text || '';
    const marks = (n.marks || []).map(m => m.type);
    if (marks.includes('strong')) t = '**' + t + '**';
    if (marks.includes('em')) t = '*' + t + '*';
    const link = (n.marks || []).find(m => m.type === 'link');
    if (link) t = '[' + t + '](' + link.attrs.href + ')';
    s += t;
  }
  return s;
}
function mdBlocks(blocks, indent = '') {
  const out = [];
  for (const b of blocks || []) {
    if (b.type === 'paragraph') out.push(indent + mdInline(b.content).split('\n').join('\n' + indent));
    else if (b.type === 'heading') out.push(indent + '#'.repeat(b.attrs.level) + ' ' + mdInline(b.content));
    else if (b.type === 'blockquote') out.push(mdBlocks(b.content, indent).split('\n').map(l => indent + '> ' + l.slice(indent.length)).join('\n'));
    else if (b.type === 'bullet_list' || b.type === 'ordered_list') {
      let n = b.type === 'ordered_list' ? (b.attrs && b.attrs.order !== undefined ? b.attrs.order : 1) : 0;
      const items = [];
      for (const li of b.content || []) {
        const marker = b.type === 'ordered_list' ? (n++ + '. ') : '- ';
        const inner = mdBlocks(li.content, indent + ' '.repeat(marker.length));
        items.push(indent + marker + inner.slice(indent.length + marker.length));
      }
      out.push(items.join('\n'));
    }
  }
  return out.join('\n\n');
}
export function toMarkdown(canonDoc) { return mdBlocks(canonDoc.content) + '\n'; }

function escapeHtml(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function htmlInline(content) {
  let s = '';
  for (const n of content || []) {
    if (n.type === 'hard_break') { s += '<br>'; continue; }
    let t = escapeHtml(n.text || '');
    for (const m of (n.marks || [])) {
      if (m.type === 'strong') t = '<strong>' + t + '</strong>';
      else if (m.type === 'em') t = '<em>' + t + '</em>';
      else if (m.type === 'link') t = '<a href="' + escapeHtml(m.attrs.href) + '">' + t + '</a>';
    }
    s += t;
  }
  return s;
}
function htmlBlocks(blocks) {
  return (blocks || []).map(b => {
    if (b.type === 'paragraph') return '<p>' + htmlInline(b.content) + '</p>';
    if (b.type === 'heading') return '<h' + b.attrs.level + '>' + htmlInline(b.content) + '</h' + b.attrs.level + '>';
    if (b.type === 'blockquote') return '<blockquote>' + htmlBlocks(b.content) + '</blockquote>';
    if (b.type === 'bullet_list') return '<ul>' + (b.content || []).map(li => '<li>' + htmlBlocks(li.content) + '</li>').join('') + '</ul>';
    if (b.type === 'ordered_list') return '<ol' + (b.attrs && b.attrs.order !== 1 ? ' start="' + b.attrs.order + '"' : '') + '>' + (b.content || []).map(li => '<li>' + htmlBlocks(li.content) + '</li>').join('') + '</ol>';
    return '';
  }).join('\n');
}
export function toHTML(canonDoc) { return htmlBlocks(canonDoc.content); }
