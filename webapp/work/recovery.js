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
const DB_VERSION = 1;
const STORE = 'envelopes';

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
export async function write(envelope) {
  const db = await open();
  return new Promise((resolve, reject) => {
    let tx;
    try { tx = db.transaction(STORE, 'readwrite'); } catch (e) { reject(e); return; }
    const rec = { ...envelope, key: envelope.doc_id + '|' + envelope.tab_id, at: new Date().toISOString() };
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
