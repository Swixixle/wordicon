// workspace-v2 — the local recovery store (instructions §7, "Save, recovery
// and migration"). IndexedDB, one envelope per (document, editing tab): the
// whole document (exact body and, from slice C, the structure and its
// versions), what it was based on (revision, fingerprint), the local edit
// sequence, selection and scroll, and any pending exact save request.
//
// Truthfulness rules: "saved locally" is said only after the write's own
// transaction completes; a failed write (quota, private mode, a blocked
// database) leaves the last complete envelope intact and is reported as a
// failure, never as a save. Distinct tabs never overwrite each other's only
// copy: the key includes the tab id.

const DB_NAME = 'nikodemus.work.recovery';
const DB_VERSION = 2;
const STORE = 'envelopes';
// Slice J: the owner's own notes get the same protection as the draft — the
// words are in this browser before any server acknowledgment, and a note's
// key carries the tab that typed it, so two tabs writing the same note can
// never overwrite each other's only copy. A separate store, because a note
// is not a draft and the two are never folded together.
const NOTES = 'note_envelopes';

let dbPromise = null;

function open() {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    let req;
    try { req = indexedDB.open(DB_NAME, DB_VERSION); } catch (e) { reject(e); return; }
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const st = db.createObjectStore(STORE, { keyPath: 'key' });
        st.createIndex('doc_id', 'doc_id', { unique: false });
      }
      if (!db.objectStoreNames.contains(NOTES)) {         // added at version 2; the v1 store is untouched
        const nt = db.createObjectStore(NOTES, { keyPath: 'key' });
        nt.createIndex('doc_id', 'doc_id', { unique: false });
        nt.createIndex('scope', 'scope', { unique: false });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error || new Error('IndexedDB refused to open'));
    req.onblocked = () => reject(new Error('IndexedDB is blocked by another tab'));
  });
  dbPromise.catch(() => { dbPromise = null; });
  return dbPromise;
}

export function available() {
  try { return typeof indexedDB !== 'undefined' && indexedDB !== null; } catch (e) { return false; }
}

// Writes the envelope; resolves only when the transaction has completed.
// `at` is the moment the WORDS were written; a note added to an envelope by
// another tab (carried, discarded) passes keepAt so the envelope keeps its
// own time and its place in any ordering by time.
export async function write(envelope, opts = {}) {
  const db = await open();
  return new Promise((resolve, reject) => {
    let tx;
    try { tx = db.transaction(STORE, 'readwrite'); } catch (e) { reject(e); return; }
    const rec = { ...envelope, key: envelope.doc_id + '|' + envelope.tab_id, at: (opts.keepAt && envelope.at) ? envelope.at : new Date().toISOString() };
    tx.objectStore(STORE).put(rec);
    tx.oncomplete = () => resolve(rec);
    tx.onerror = () => reject(tx.error || new Error('the recovery write failed'));
    tx.onabort = () => reject(tx.error || new Error('the recovery write was aborted'));
  });
}

export async function read(doc_id, tab_id) {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readonly');
    const req = tx.objectStore(STORE).get(doc_id + '|' + tab_id);
    req.onsuccess = () => resolve(req.result || null);
    req.onerror = () => reject(req.error);
  });
}

export async function forDocument(doc_id) {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readonly');
    const req = tx.objectStore(STORE).index('doc_id').getAll(doc_id);
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => reject(req.error);
  });
}

export async function remove(doc_id, tab_id) {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).delete(doc_id + '|' + tab_id);
    tx.oncomplete = () => resolve(true);
    tx.onerror = () => reject(tx.error);
  });
}

export async function all() {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readonly');
    const req = tx.objectStore(STORE).getAll();
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => reject(req.error);
  });
}


// ---- the owner's notes ------------------------------------------------------
// `scope` is the note's identity while it is being written: a note id once
// the server has one, or 'new:<doc_id>' for words in the compose box that
// have not become a note yet. The key carries the tab, so another tab's
// unsent words are a separate row that this tab never writes over.

export function noteKey(scope, tab_id) { return scope + '|' + tab_id; }

export async function writeNote(envelope) {
  const db = await open();
  return new Promise((resolve, reject) => {
    let tx;
    try { tx = db.transaction(NOTES, 'readwrite'); } catch (e) { reject(e); return; }
    const rec = { ...envelope, key: noteKey(envelope.scope, envelope.tab_id), at: new Date().toISOString() };
    tx.objectStore(NOTES).put(rec);
    tx.oncomplete = () => resolve(rec);
    tx.onerror = () => reject(tx.error || new Error('the note recovery write failed'));
    tx.onabort = () => reject(tx.error || new Error('the note recovery write was aborted'));
  });
}

export async function readNote(scope, tab_id) {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(NOTES, 'readonly');
    const req = tx.objectStore(NOTES).get(noteKey(scope, tab_id));
    req.onsuccess = () => resolve(req.result || null);
    req.onerror = () => reject(req.error);
  });
}

export async function notesForDocument(doc_id) {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(NOTES, 'readonly');
    const req = tx.objectStore(NOTES).index('doc_id').getAll(doc_id);
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => reject(req.error);
  });
}

export async function removeNote(scope, tab_id) {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(NOTES, 'readwrite');
    tx.objectStore(NOTES).delete(noteKey(scope, tab_id));
    tx.oncomplete = () => resolve(true);
    tx.onerror = () => reject(tx.error);
  });
}

export async function allNotes() {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(NOTES, 'readonly');
    const req = tx.objectStore(NOTES).getAll();
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => reject(req.error);
  });
}
