// workspace-v2 — the shell's arrangement (instructions §6).
//
// Tools and Results open and close independently; each open side carries
// its own Hide; the header always carries the reopen controls, lit while a
// side is open. Focus hides both sides and the secondary controls together
// and restores exactly the arrangement that was open before. The sides
// are resizable by pointer and keyboard within clamps that keep the writing
// usable. The arrangement is remembered per screen-size bucket.
//
// When two sides would squeeze the writing (the available writing width
// measured in CSS px — zoom counts — falls under the minimum), the shell
// goes NARROW: Tools becomes a dismissible drawer over the left (focus
// trapped inside, the rest inert, focus returned to its opener on close)
// and Results becomes a collapsible section below the draft, reached by
// "↓ Results" and left by "↑ Back to writing", which restores the caret.
import { prefs } from './util.js';

const MIN_WRITING_PX = 700;         // roughly 60ch of 19px prose plus its padding
const TOOLS_MIN = 200, TOOLS_MAX = 420, RESULTS_MIN = 280, RESULTS_MAX = 560;

export class Layout {
  constructor(shell, hooks = {}) {
    this.shell = shell;
    this.hooks = hooks;             // onChange(state), focusEditor(), editorHasFocus()
    this.tools = document.getElementById('tools');
    this.results = document.getElementById('results');
    this.center = document.getElementById('center');
    this.state = { tools: true, results: false, focus: false, narrow: false, toolsW: 280, resultsW: 380, before: null };
    this.opener = null;
    this.scrim = document.createElement('div'); this.scrim.className = 'scrim'; this.scrim.hidden = true;
    document.getElementById('body').appendChild(this.scrim);
    this.scrim.addEventListener('click', () => this.setTools(false));
    this.bind();
    this.load();
    this.measure();
    window.addEventListener('resize', () => { this.measure(); });
  }

  bucket() { const w = window.innerWidth; return w >= 1600 ? 'wide' : (w >= 1100 ? 'laptop' : 'small'); }

  load() {
    const p = prefs.get('layout.' + this.bucket(), null);
    if (p) Object.assign(this.state, { tools: !!p.tools, results: !!p.results, toolsW: p.toolsW || 280, resultsW: p.resultsW || 380 });
    else if (this.bucket() === 'wide') this.state.results = true;
  }
  save() {
    const s = this.state;
    prefs.set('layout.' + this.bucket(), { tools: s.tools, results: s.results, toolsW: s.toolsW, resultsW: s.resultsW });
  }

  // narrow = both sides open, even at their thinnest, would leave the writing
  // under the minimum; before that point the sides give way, not the writing
  // (slice G: a 1280 px laptop keeps both panels by narrowing them)
  measure() {
    const s = this.state;
    const wouldBe = window.innerWidth - TOOLS_MIN - RESULTS_MIN;
    const narrow = wouldBe < MIN_WRITING_PX;
    if (narrow !== s.narrow) { s.narrow = narrow; }
    // clamp widths so an open side never squeezes the writing below the minimum
    if (!narrow) {
      const spare = window.innerWidth - MIN_WRITING_PX;
      if (s.toolsW + s.resultsW > spare) {
        const share = Math.max(0, spare) / 2;
        s.toolsW = Math.max(TOOLS_MIN, Math.min(s.toolsW, Math.floor(share)));
        s.resultsW = Math.max(RESULTS_MIN, Math.min(s.resultsW, Math.floor(share)));
      }
    }
    this.apply();
  }

  apply() {
    const s = this.state, sh = this.shell;
    sh.style.setProperty('--tools-w', s.toolsW + 'px');
    sh.style.setProperty('--results-w', s.resultsW + 'px');
    sh.dataset.tools = s.tools ? 'open' : 'closed';
    sh.dataset.results = s.results ? 'open' : 'closed';
    sh.dataset.focus = s.focus ? 'on' : 'off';
    sh.dataset.narrow = s.narrow ? 'yes' : 'no';
    this.tools.hidden = !(s.tools && !s.focus);
    this.results.hidden = !(s.results && !s.focus) || s.narrow;
    const stacked = document.getElementById('stacked');
    const stackedOn = s.narrow && s.results && !s.focus;
    stacked.hidden = !stackedOn;
    // the results body — and its tabs (Results, Feedback, Notes, Sources) — live
    // in ONE place: the side when beside, the stacked section when below
    const body = document.getElementById('results-body');
    const stackedBody = document.getElementById('stacked-body');
    if (stackedOn && body.parentElement !== stackedBody) stackedBody.appendChild(body);
    if (!stackedOn && body.parentElement !== this.results) this.results.appendChild(body);
    const tabs = document.getElementById('results-tabs');
    const stackedHead = document.getElementById('stacked-head'), sideHead = this.results.querySelector('.panel-head');
    if (tabs && stackedOn && tabs.parentElement !== stackedHead) stackedHead.insertBefore(tabs, document.getElementById('back-to-writing'));
    if (tabs && !stackedOn && tabs.parentElement !== sideHead) sideHead.insertBefore(tabs, document.getElementById('results-hide'));
    // the drawer: scrim + inert centre while open at narrow widths
    const drawer = s.narrow && s.tools && !s.focus;
    this.scrim.hidden = !drawer;
    if (drawer) { this.center.setAttribute('inert', ''); if (!this.results.hidden) this.results.setAttribute('inert', ''); }
    else { this.center.removeAttribute('inert'); this.results.removeAttribute('inert'); }
    // header controls
    const tt = document.getElementById('tools-toggle'), rt = document.getElementById('results-toggle');
    tt.setAttribute('aria-pressed', String(s.tools)); tt.classList.toggle('on', s.tools);
    tt.firstChild.textContent = s.tools ? '◂ Tools' : 'Tools ▸';
    rt.setAttribute('aria-pressed', String(s.results)); rt.classList.toggle('on', s.results);
    rt.firstChild.textContent = s.narrow ? (s.results ? '↓ Results ' : '↓ Results ') : (s.results ? 'Results ▸ ' : '◂ Results ');
    document.getElementById('focus-btn').setAttribute('aria-pressed', String(s.focus));
    document.getElementById('exit-focus').hidden = !s.focus;
    if (this.hooks.onChange) this.hooks.onChange(s);
  }

  setTools(open, opener) {
    const s = this.state;
    if (open && s.narrow) this.opener = opener || document.activeElement;
    s.tools = !!open; this.save(); this.apply();
    if (open && s.narrow) { const first = this.tools.querySelector('.dest'); if (first) first.focus(); }
    if (!open && s.narrow && this.opener && this.opener.focus) { try { this.opener.focus(); } catch (e) {} }
  }
  setResults(open) {
    const s = this.state;
    s.results = !!open; this.save(); this.apply();
    if (s.narrow && open) { const st = document.getElementById('stacked'); st.scrollIntoView({ block: 'start', behavior: 'smooth' }); }
  }
  toggleTools(opener) { this.setTools(!this.state.tools, opener); }
  toggleResults() { this.setResults(!this.state.results); }

  setFocus(on) {
    const s = this.state;
    if (on && !s.focus) { s.before = { tools: s.tools, results: s.results }; s.focus = true; }
    else if (!on && s.focus) { s.focus = false; if (s.before) { s.tools = s.before.tools; s.results = s.before.results; } s.before = null; }
    this.apply();
    if (this.hooks.focusEditor) this.hooks.focusEditor();
  }

  backToWriting() {
    const wv = document.getElementById('work-view');
    wv.scrollTo({ top: 0, behavior: 'smooth' });
    if (this.hooks.focusEditor) this.hooks.focusEditor();
  }

  bind() {
    document.getElementById('tools-toggle').addEventListener('click', e => this.toggleTools(e.currentTarget));
    document.getElementById('tools-hide').addEventListener('click', () => this.setTools(false));
    document.getElementById('tools-close').addEventListener('click', () => this.setTools(false));
    document.getElementById('results-toggle').addEventListener('click', () => this.toggleResults());
    document.getElementById('results-hide').addEventListener('click', () => this.setResults(false));
    document.getElementById('focus-btn').addEventListener('click', () => this.setFocus(true));
    document.getElementById('exit-focus').addEventListener('click', () => this.setFocus(false));
    document.getElementById('back-to-writing').addEventListener('click', () => this.backToWriting());
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        if (this.state.focus) { this.setFocus(false); e.preventDefault(); return; }
        if (this.state.narrow && this.state.tools) { this.setTools(false); e.preventDefault(); }
      }
      // focus trap inside the drawer
      if (e.key === 'Tab' && this.state.narrow && this.state.tools && !this.state.focus) {
        const f = Array.from(this.tools.querySelectorAll('button, a, [tabindex]:not([tabindex="-1"])')).filter(x => !x.hidden && x.offsetParent !== null);
        if (!f.length) return;
        const first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { last.focus(); e.preventDefault(); }
        else if (!e.shiftKey && document.activeElement === last) { first.focus(); e.preventDefault(); }
        else if (!this.tools.contains(document.activeElement)) { first.focus(); e.preventDefault(); }
      }
    });
    this.grip(document.getElementById('tools-grip'), 'toolsW', TOOLS_MIN, TOOLS_MAX, +1);
    this.grip(document.getElementById('results-grip'), 'resultsW', RESULTS_MIN, RESULTS_MAX, -1);
  }

  grip(node, key, min, max, sign) {
    const clamp = v => {
      const s = this.state;
      const other = key === 'toolsW' ? (s.results ? s.resultsW : 0) : (s.tools ? s.toolsW : 0);
      const roomMax = Math.max(min, window.innerWidth - other - MIN_WRITING_PX);
      return Math.max(min, Math.min(max, Math.min(roomMax, Math.round(v))));
    };
    let startX = 0, startW = 0, dragging = false;
    node.addEventListener('pointerdown', e => { dragging = true; startX = e.clientX; startW = this.state[key]; node.setPointerCapture(e.pointerId); e.preventDefault(); });
    node.addEventListener('pointermove', e => { if (!dragging) return; this.state[key] = clamp(startW + sign * (e.clientX - startX)); this.apply(); });
    const end = () => { if (!dragging) return; dragging = false; this.save(); };
    node.addEventListener('pointerup', end); node.addEventListener('pointercancel', end);
    node.addEventListener('keydown', e => {
      const step = e.shiftKey ? 40 : 16;
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        const dir = (e.key === 'ArrowRight' ? 1 : -1) * sign;
        this.state[key] = clamp(this.state[key] + dir * step); this.save(); this.apply(); e.preventDefault();
      }
      if (e.key === 'Home') { this.state[key] = clamp(min); this.save(); this.apply(); e.preventDefault(); }
      if (e.key === 'End') { this.state[key] = clamp(max); this.save(); this.apply(); e.preventDefault(); }
    });
    node.setAttribute('aria-valuemin', String(min)); node.setAttribute('aria-valuemax', String(max));
  }
}
