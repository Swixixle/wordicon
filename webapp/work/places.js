// workspace-v2 — a specialist place opens INSIDE the shell (instructions §6:
// "Existing specialist views may initially open inside the new shell with
// correct return behavior"). The place is the existing page on its own
// route, in a frame in the centre; the writing view is hidden, not
// unmounted, so the editor keeps its element, caret, selection, scroll and
// undo. "Back to writing" restores the writing view and the caret.
import { el } from './util.js';

const PLACES = {
  '/map/focus': { name: 'Map · focus', why: 'one place in focus — where it came from, what it touched, who drew each road' },
  '/map': { name: 'Map · focus', why: 'one place in focus' },
  '/map/trails': { name: 'Map · trails', why: 'your runs, each item a typed door' },
  '/map/world': { name: 'Map · world', why: 'the same record laid out in space' },
  '/bench': { name: 'Bench', why: 'reworking a word you already kept' },
  '/clinic': { name: 'Clinic', why: 'authorities admitted by role, never blended' },
  '/recovery': { name: 'Recovery review', why: 'acceptances that survived without a definition' },
  '/investigation': { name: 'Investigation rooms', why: 'what your other instruments deposited' },
  '/inquiry': { name: 'Inquiry', why: 'a question, kept — with its branches' },
  '/constitution': { name: 'What is Nikodemus', why: 'the law, with its pins' },
  '/': { name: 'The previous interface', why: 'every result and every place, as before' },
};

export class Places {
  constructor(hooks = {}) {
    this.hooks = hooks;          // onOpen(), onClose()
    this.view = document.getElementById('place-view');
    this.frame = document.getElementById('place-frame');
    this.current = '';
    document.getElementById('place-back').addEventListener('click', () => this.close());
  }
  meta(pathname) { return PLACES[pathname] || { name: pathname, why: '' }; }
  open(url) {
    let u;
    try { u = new URL(url, location.href); } catch (e) { return false; }
    if (u.origin !== location.origin) return false;
    const m = this.meta(u.pathname);
    document.getElementById('place-name').textContent = m.name;
    document.getElementById('place-why').textContent = m.why;
    this.frame.title = m.name;
    const want = u.pathname + u.search + u.hash;
    if (this.current !== want) { this.frame.src = want; this.current = want; }
    if (this.hooks.onOpen) this.hooks.onOpen(m);
    this.view.hidden = false;
    return true;
  }
  close() {
    this.view.hidden = true;
    this.frame.src = 'about:blank'; this.current = '';   // a closed place stops running rather than idling behind the page
    if (this.hooks.onClose) this.hooks.onClose();
  }
  isOpen() { return !this.view.hidden; }
}
