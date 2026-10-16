// workspace-v2 — the intake (2026-10-16): a door for files in the workspace
// itself, because the only way in was a framed trip to the previous
// interface. Dropping or choosing a file QUEUES it; nothing is stored until
// the press that says so, and nothing is read by a model on admission —
// block 117 holds here exactly as in the previous interface: text and PDF
// derive their text locally, and an image's text is a vision call made only
// on the button that names it. The artifact is the source; the text is a
// derivative and says which it is.
import { el, toast } from './util.js';

const KINDS = 'plain text, Markdown, PDF, and JPEG/PNG/GIF/WebP images';
const ACCEPT = '.txt,.md,.markdown,text/plain,text/markdown,application/pdf,image/png,image/jpeg,image/gif,image/webp';

function fmtBytes(n) {
  if (n >= 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + ' MB';
  if (n >= 1024) return Math.round(n / 1024) + ' KB';
  return n + ' B';
}

export class Intake {
  constructor(results, layout, places) {
    this.results = results; this.layout = layout; this.places = places;   // kept for the shell's shape; the intake is its own dialog
    this.queue = [];     // { file, status: queued|admitting|stored|refused, artifact, rep, needs_model, error }
  }

  open(files) {
    if (files && files.length) for (const f of files) this.queue.push({ file: f, status: 'queued' });
    this.render();
  }

  close() {
    const ov = document.getElementById('work-intake-overlay');
    if (ov) ov.hidden = true;
  }

  // Its own dialog, like Ask — not a card in the side panel, which renders
  // as a short strip below the draft on a narrow desk and buried the
  // controls (the owner, 2026-10-16: "the upload button is not functional").
  overlay() {
    let ov = document.getElementById('work-intake-overlay');
    if (!ov) {
      ov = el('div', { id: 'work-intake-overlay', class: 'intake', hidden: true });
      ov.addEventListener('click', e => { if (e.target === ov) this.close(); });
      document.addEventListener('keydown', e => { if (e.key === 'Escape' && !ov.hidden) this.close(); });
      document.getElementById('shell').appendChild(ov);
    }
    return ov;
  }

  render() {
    const ov = this.overlay();
    ov.hidden = false;
    ov.textContent = '';
    const host = el('div', { id: 'work-intake', class: 'intake-box', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Add a file' }, [
      el('div', { class: 'row', style: 'justify-content: space-between; align-items: baseline' }, [
        el('div', { class: 'result-title', text: 'Add a file' }),
        el('button', { class: 'btn small', type: 'button', text: 'Close ✕', 'aria-label': 'Close the intake', onclick: () => this.close() }),
      ]),
      el('div', { class: 'kv muted small-text', text: 'This version takes ' + KINDS + '. Admitting stores the file unchanged in the Library and derives one text representation beside it — locally for text and PDF. Nothing is read by a model on admission; an image’s text is a separate vision call you press for by name.' }),
    ]);
    const input = el('input', { type: 'file', multiple: true, accept: ACCEPT, style: 'display:none', 'aria-label': 'Choose files to add' });
    input.addEventListener('change', () => { if (input.files.length) this.open(Array.from(input.files)); input.value = ''; });
    const row = el('div', { class: 'row' }, [
      el('button', { class: 'btn', type: 'button', text: 'Choose files…', onclick: () => input.click() }),
      el('span', { class: 'muted small-text', text: 'or drop them anywhere on this page' }),
      input,
    ]);
    host.appendChild(row);

    if (this.queue.length) {
      const list = el('div', { class: 'intake-list' });
      this.queue.forEach((q, i) => list.appendChild(this.rowFor(q, i)));
      host.appendChild(list);
      const pending = this.queue.filter(q => q.status === 'queued').length;
      if (pending) {
        host.appendChild(el('div', { class: 'row' }, [
          el('button', { class: 'btn primary', type: 'button', text: 'Admit to the Library' + (pending === 1 ? '' : ' (' + pending + ' files)'),
            onclick: () => this.admitQueued() }),
          el('button', { class: 'btn small', type: 'button', text: 'Clear the queue', onclick: () => { this.queue = this.queue.filter(x => x.status !== 'queued'); this.render(); } }),
        ]));
      }
    }
    host.appendChild(el('div', { class: 'kv muted small-text' }, [
      el('span', { text: 'An authority (a dictionary, a reference) is admitted by role in the Clinic, never blended — ' }),
      el('button', { class: 'linkish', type: 'button', text: 'open the Clinic', onclick: () => this.places.open('/clinic') }),
      el('span', { text: '. Audio and EPUB keep their own intake for now — ' }),
      el('button', { class: 'linkish', type: 'button', text: 'open the full intake (previous interface)', onclick: () => this.places.open('/#bring') }),
      el('span', { text: '.' }),
    ]));
    ov.appendChild(host);
  }

  rowFor(q, i) {
    const r = el('div', { class: 'card intake-row', dataset: { intake: String(i) } });
    r.appendChild(el('div', { class: 'row', style: 'justify-content: space-between' }, [
      el('span', { class: 'result-title small-text', text: q.file.name || '(unnamed)' }),
      el('span', { class: 'muted small-text', text: fmtBytes(q.file.size) }),
    ]));
    if (q.status === 'queued') r.appendChild(el('div', { class: 'muted small-text', text: 'queued — nothing stored yet' }));
    if (q.status === 'admitting') r.appendChild(el('div', { class: 'muted small-text', text: 'admitting…' }));
    if (q.status === 'refused') r.appendChild(el('div', { class: 'small-text warn', text: q.error }));
    if (q.status === 'stored') {
      const a = q.artifact || {}, rep = q.rep || {};
      r.appendChild(el('div', { class: 'small-text', text: 'stored in the Library as the source · ' + (a.kind || '') + (a.sha256 ? ' · sha256 ' + String(a.sha256).slice(0, 12) + '…' : '') }));
      if (q.needs_model) {
        r.appendChild(el('div', { class: 'muted small-text', text: 'Reading the text off an image is a model call. The file is stored; nothing has been sent.' }));
        r.appendChild(el('button', { class: 'btn small', type: 'button', text: 'Read the text off this image (one vision call)',
          onclick: () => this.represent(i) }));
      } else if (rep.method) {
        r.appendChild(el('div', { class: 'muted small-text', text: 'text derived ' + (rep.method === 'original_text' ? 'from the file itself' : (rep.method === 'pdf_text_layer' ? 'from the PDF’s own text layer' : 'by ' + rep.method)) + ' · ' + (rep.chars || 0) + ' characters · no model call' }));
      }
    }
    return r;
  }

  async admitQueued() {
    for (let i = 0; i < this.queue.length; i++) {
      const q = this.queue[i];
      if (q.status !== 'queued') continue;
      q.status = 'admitting'; this.render();
      try {
        const fd = new FormData();
        fd.append('file', q.file, q.file.name);
        const r = await fetch('/api/upload', { method: 'POST', body: fd, credentials: 'same-origin' });
        let d = {};
        try { d = await r.json(); } catch (e) { d = { error: 'HTTP ' + r.status }; }
        if (!r.ok) { q.status = 'refused'; q.error = d.error || ('HTTP ' + r.status); }
        else { q.status = 'stored'; q.artifact = d.artifact; q.rep = d.representation || {}; q.needs_model = !!d.needs_model; }
      } catch (e) {
        q.status = 'refused'; q.error = 'The admission did not reach the server: ' + e;
      }
      this.render();
    }
    const stored = this.queue.filter(x => x.status === 'stored').length;
    if (stored) toast(stored + (stored === 1 ? ' file' : ' files') + ' admitted — stored in the Library, nothing read by a model.');
  }

  async represent(i) {
    const q = this.queue[i];
    if (!q || !q.artifact || !q.artifact.artifact_id) return;
    try {
      const r = await fetch('/api/artifact/' + encodeURIComponent(q.artifact.artifact_id) + '/represent', { method: 'POST', credentials: 'same-origin' });
      let d = {};
      try { d = await r.json(); } catch (e) { d = { error: 'HTTP ' + r.status }; }
      if (!r.ok) { toast('The reading failed: ' + (d.error || r.status), 6000); return; }
      q.rep = d.representation || {}; q.needs_model = false;
      q.rep.method = q.rep.method || 'model_transcription';
      this.render();
      toast('The image’s text was read by the model and stored as a derivative beside the source.');
    } catch (e) { toast('The reading did not reach the server: ' + e, 6000); }
  }
}
