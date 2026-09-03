"""The Library wing — Wordicon's document spine, Phase 0.

Generalized from the theo-wing (the spine's tested v0: canonical text kept
intact, deterministic segmentation, mechanical anchors, manifests with
checksums). Constitution, enforced by construction and pinned by tests:

- ZERO model calls. Nothing in this module imports or touches a gateway.
  A book lands, is hashed, segmented, indexed, and readable without a
  single API request. The model enters only when the owner selects, asks,
  or runs a lane — and none of those lanes live in this file.
- Originals are sacred: the blob on disk is byte-identical to what arrived,
  forever. Everything else is a labeled derivative pointing back at it.
- Four identity layers, never collapsed (per the 2026-08-29 planning
  ruling): blob_id says WHICH BYTES; document_id says WHICH WORK;
  ingest_id says WHERE AND WHEN this copy arrived; representation_id says
  HOW it was read (extractor + segmenter revisions). Identical bytes from
  two sources share a blob and keep two acquisition records. A revised
  segmenter mints a NEW immutable representation — it never reuses old
  anchor identities.
- Determinism, precisely: identical bytes processed with identical
  extractor and segmenter revisions produce identical representation and
  anchor IDs. This holds by construction (the IDs are content hashes over
  exactly those inputs) and is asserted by the suite, not hoped.
- Failed or suspect extraction is VISIBLE: findings on the representation,
  never silent normalization.
- FTS5 search is the local lexical lane only — exact text in your library.
  It is labeled as such; it is not semantic search and not the web.
"""

import hashlib
import html
import html.parser
import json
import os
import pathlib
import re
import sqlite3
import zipfile

import wordicon_cli as cli

EXTRACTOR_REV = 1
SEGMENTER_REV = 1

_now = cli._now


# ---------------------------------------------------------------------------
# storage layout — everything under local_state/library/, paths derived at
# call time so the test suite's state redirect and the serve-real harness
# both catch this wing automatically.

def lib_dir() -> pathlib.Path:
    return pathlib.Path(cli.LOCAL_STATE) / "library"


def blobs_dir() -> pathlib.Path:
    return lib_dir() / "blobs"


def reps_dir() -> pathlib.Path:
    return lib_dir() / "representations"


def ingests_log() -> pathlib.Path:
    return lib_dir() / "ingests.jsonl"


def docs_path() -> pathlib.Path:
    return lib_dir() / "documents.json"


def search_db_path() -> pathlib.Path:
    return lib_dir() / "search.db"


def load_documents() -> dict:
    p = docs_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def load_ingests() -> "list[dict]":
    p = ingests_log()
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("ingest_id"):
            out.append(row)
    return out


# ---------------------------------------------------------------------------
# extraction — stdlib only, so the extractor's behavior is pinned by THIS
# file's revision number and nothing else's release notes.

_BLOCK_TAGS = {"p", "li", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6",
               "figcaption", "dt", "dd", "pre", "td", "th"}
_SKIP_TAGS = {"script", "style", "nav", "noscript", "template", "svg"}


class _BlockExtractor(html.parser.HTMLParser):
    """Text per block element, in document order. Skipped-tag content is
    counted, not silently vanished — the count lands in findings."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []          # [{"tag": str, "text": str}]
        self._buf = []
        self._block_tag = None
        self._skip_depth = 0
        self.skipped_chars = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
        if tag in _BLOCK_TAGS and self._skip_depth == 0:
            self._flush()
            self._block_tag = tag
        if tag == "br" and self._buf:
            self._buf.append(" ")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if tag == "title":
            self._in_title = False
        if tag in _BLOCK_TAGS:
            self._flush()

    def handle_data(self, data):
        if self._skip_depth:
            self.skipped_chars += len(data)
            return
        if self._in_title:
            # Title text is the title, not a phantom first paragraph.
            self.title += data
            return
        self._buf.append(data)

    def _flush(self):
        text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        if text:
            self.blocks.append({"tag": self._block_tag or "p", "text": text})
        self._buf = []
        self._block_tag = None

    def close(self):
        self._flush()
        super().close()


def _decode(data: bytes) -> "tuple[str, list]":
    findings = []
    try:
        return data.decode("utf-8"), findings
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
        n = text.count("�")
        findings.append(f"Decoding: {n} byte sequence(s) were not valid UTF-8 and "
                        "were replaced — the blob is intact, this representation "
                        "is lossy there.")
        return text, findings


def _extract_html(data: bytes) -> "tuple[str, list, list]":
    """→ (title, blocks, findings)"""
    text, findings = _decode(data)
    p = _BlockExtractor()
    p.feed(text)
    p.close()
    if p.skipped_chars:
        findings.append(f"Extraction: {p.skipped_chars} character(s) inside "
                        "script/style/nav-class tags were not treated as text.")
    if not p.blocks:
        findings.append("Extraction: no block-level text was found — this file "
                        "may not be an article, or its markup defeats the "
                        f"extractor (rev {EXTRACTOR_REV}). Nothing was invented "
                        "to fill the gap.")
    return re.sub(r"\s+", " ", p.title).strip(), p.blocks, findings


def _extract_epub(data: bytes) -> "tuple[str, list, list]":
    """→ (title, sections, findings); sections = [{heading, blocks}] in
    spine order, one per spine item — the chapter is the natural unit."""
    findings = []
    sections = []
    title = ""
    import io
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return "", [], ["Extraction: not a readable EPUB (bad zip container)."]
    names = set(zf.namelist())
    opf_path = None
    if "META-INF/container.xml" in names:
        cx, _ = _decode(zf.read("META-INF/container.xml"))
        m = re.search(r'full-path="([^"]+)"', cx)
        if m:
            opf_path = m.group(1)
    if not opf_path:
        opf_path = next((n for n in sorted(names) if n.endswith(".opf")), None)
        if opf_path:
            findings.append("Extraction: container.xml missing or unreadable; "
                            "the OPF was located by filename instead.")
    if not opf_path or opf_path not in names:
        return "", [], findings + ["Extraction: no OPF package document — the "
                                    "spine order cannot be established."]
    opf, _ = _decode(zf.read(opf_path))
    tm = re.search(r"<dc:title[^>]*>([^<]*)</dc:title>", opf)
    if tm:
        title = html.unescape(tm.group(1)).strip()
    base = opf_path.rsplit("/", 1)[0] + "/" if "/" in opf_path else ""
    manifest = dict(re.findall(
        r'<item[^>]*\bid="([^"]+)"[^>]*\bhref="([^"]+)"', opf))
    manifest.update({i: h for h, i in re.findall(
        r'<item[^>]*\bhref="([^"]+)"[^>]*\bid="([^"]+)"', opf)})
    spine_ids = re.findall(r'<itemref[^>]*\bidref="([^"]+)"', opf)
    if not spine_ids:
        return title, [], findings + ["Extraction: the OPF has an empty spine."]
    for sid in spine_ids:
        href = manifest.get(sid)
        if not href:
            findings.append(f"Extraction: spine item {sid!r} is not in the "
                            "manifest — skipped, and saying so.")
            continue
        path = base + href.split("#")[0]
        if path not in names:
            findings.append(f"Extraction: spine file {path!r} is missing from "
                            "the archive — skipped, and saying so.")
            continue
        sec_title, blocks, f2 = _extract_html(zf.read(path))
        findings.extend(f"[{path}] {x}" for x in f2)
        heading = sec_title or (blocks[0]["text"][:80] if blocks and
                                 blocks[0]["tag"].startswith("h") else path)
        sections.append({"heading": heading, "blocks": blocks, "src": path})
    return title, sections, findings


def _extract_txt(data: bytes) -> "tuple[str, list, list]":
    text, findings = _decode(data)
    blocks = [{"tag": "p", "text": re.sub(r"\s+", " ", b).strip()}
              for b in re.split(r"\n\s*\n", text) if b.strip()]
    if not blocks:
        findings.append("Extraction: the file contains no text.")
    return "", blocks, findings


# ---------------------------------------------------------------------------
# The medical wing's two custody adapters (docs/adr-medical-wing.md).
# Two EXPLICIT extractors, separately versioned — never one imaginary
# universal revision. docx_text_v1 is stdlib (zipfile + ElementTree).
# pdf_text_v1 rides pdfminer.six, pinned in requirements.txt; the
# installed pdfminer version is folded into the extractor identity, so a
# changed library mints NEW representations instead of silently changing
# what an old representation id claims to contain.

DOCX_EXTRACTOR = "docx_text_v1"
_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _pdf_extractor_tag() -> str:
    import pdfminer  # pinned dependency; ImportError is honest, not caught
    return f"pdf_text_v1+pdfminer.six-{pdfminer.__version__}"


def _extract_docx(data: bytes) -> "tuple[str, list, list]":
    import io
    import xml.etree.ElementTree as _ET
    findings = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        doc_xml = zf.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError, OSError) as e:
        raise ValueError("This DOCX cannot be opened as one (encrypted, "
                         "truncated, or not really a DOCX) — refused "
                         f"plainly rather than mangled: {e}")
    try:
        root = _ET.fromstring(doc_xml)
    except _ET.ParseError as e:
        raise ValueError(f"This DOCX's document.xml does not parse — "
                         f"refused plainly: {e}")
    blocks = []
    for p in root.iter(_W_NS + "p"):
        text = "".join(t.text or "" for t in p.iter(_W_NS + "t"))
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            blocks.append({"tag": "p", "text": text})
    if not blocks:
        findings.append("Extraction: the DOCX contains no text.")
    return "", blocks, findings


def _extract_pdf(data: bytes) -> "tuple[str, list, list]":
    """Per-page sections so every anchor names its page. Scanned PDFs —
    no extractable text layer — are REFUSED with a visible finding; OCR
    is a later, separately versioned adapter (the ruling), because
    silently returning nothing would let a scan pose as an empty
    document."""
    import io
    from pdfminer.high_level import extract_text
    from pdfminer.pdfpage import PDFPage
    from pdfminer.pdfparser import PDFSyntaxError
    findings = []
    try:
        n_pages = len(list(PDFPage.get_pages(io.BytesIO(data))))
    except (PDFSyntaxError, Exception) as e:  # noqa: BLE001 — refuse plainly
        raise ValueError(f"This file cannot be read as a PDF — refused "
                         f"plainly rather than mangled: {e}")
    if not n_pages:
        raise ValueError("This PDF has no pages — refused plainly.")
    sections, total_chars = [], 0
    for i in range(n_pages):
        try:
            page_text = extract_text(io.BytesIO(data), page_numbers=[i]) or ""
        except Exception as e:  # noqa: BLE001 — one bad page is disclosed
            findings.append(f"Extraction: page {i + 1} failed to extract "
                            f"({e}) — recorded, not invented.")
            page_text = ""
        total_chars += len(page_text.strip())
        blocks = [{"tag": "p", "text": re.sub(r"\s+", " ", b).strip()}
                  for b in re.split(r"\n\s*\n", page_text) if b.strip()]
        sections.append({"heading": f"page {i + 1}", "blocks": blocks,
                         "src": f"page:{i + 1}"})
    if total_chars < max(40, 15 * n_pages):
        raise ValueError(
            "This PDF carries no usable text layer — most likely a scanned "
            "document. Refused with this finding rather than mangled; OCR "
            "is a later, separately versioned adapter.")
    return "", sections, findings


# ---------------------------------------------------------------------------
# segmentation — the theo-wing's lessons, generalized. Deterministic; a
# changed rule here MUST bump SEGMENTER_REV or the suite goes red.

_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=[\"'“”‘’]?[A-Z0-9])")


def split_sentences(text: str) -> "list[str]":
    """Strip symmetric wrapping quotes BEFORE splitting (the theo-wing's
    quote-wrapped-sentence lesson), then split on terminal punctuation
    followed by a capital. Deterministic, no dictionary, no model."""
    t = text.strip()
    if len(t) > 1 and t[0] in "\"'“‘" and t[-1] in "\"'”’":
        t = t[1:-1].strip()
    if not t:
        return []
    parts = [s.strip() for s in _SENT_SPLIT.split(t) if s.strip()]
    return parts or [t]


def build_representation(blob_id: str, kind: str, data: bytes,
                          fallback_title: str = "") -> dict:
    """One deterministic reading of one blob. The representation_id is a
    content hash over (blob, extractor identity, segmenter rev) —
    determinism and revision-isolation by construction, not by promise.

    The medical wing's adapters (docs/adr-medical-wing.md) are two
    EXPLICIT extractors — pdf_text_v1 and docx_text_v1 — never a shared
    universal revision: each carries its own versioned name into the
    representation id, so a future v2 of one mints NEW representations
    for its own kind and touches nothing else. The pre-existing kinds
    keep the numeric stdlib revision bit-for-bit."""
    if kind == "epub":
        title, raw_sections, findings = _extract_epub(data)
    elif kind == "html":
        t, blocks, findings = _extract_html(data)
        title, raw_sections = t, [{"heading": t or fallback_title or "article",
                                    "blocks": blocks, "src": ""}]
    elif kind == "pdf":
        t, raw_sections, findings = _extract_pdf(data)
        title = t
    elif kind == "docx":
        t, blocks, findings = _extract_docx(data)
        title, raw_sections = t, [{"heading": t or fallback_title or "document",
                                    "blocks": blocks, "src": ""}]
    else:
        t, blocks, findings = _extract_txt(data)
        title, raw_sections = t, [{"heading": fallback_title or "text",
                                    "blocks": blocks, "src": ""}]
    extractor_tag = (_pdf_extractor_tag() if kind == "pdf"
                     else DOCX_EXTRACTOR if kind == "docx"
                     else f"{EXTRACTOR_REV}")
    rep_id = "rep_" + hashlib.sha256(
        f"{blob_id}|{kind}|extractor:{extractor_tag}|segmenter:{SEGMENTER_REV}"
        .encode()).hexdigest()[:16]
    sections = []
    n_sents = 0
    for si, sec in enumerate(raw_sections):
        paragraphs = []
        cursor = 0
        sec_text_parts = []
        for pi, block in enumerate(sec["blocks"]):
            sents = []
            for zi, s in enumerate(split_sentences(block["text"])):
                sents.append({"path": f"{si}.{pi}.{zi}", "text": s})
                n_sents += 1
            if not sents and block["text"]:
                findings.append(f"Segmentation: section {si} paragraph {pi} "
                                "yielded no sentences from non-empty text — "
                                "that is a segmenter gap, not empty content.")
            paragraphs.append({"path": f"{si}.{pi}", "tag": block["tag"],
                                "sentences": sents})
            sec_text_parts.append(block["text"])
        section_text = "\n".join(sec_text_parts)
        # exact offsets of every sentence into this section's canonical
        # extracted text — "resolves mechanically" means slicing works
        pos = 0
        for para in paragraphs:
            for s in para["sentences"]:
                idx = section_text.find(s["text"], pos)
                if idx < 0:
                    idx = section_text.find(s["text"])
                if idx < 0:
                    findings.append(f"Anchoring: sentence {s['path']} could not "
                                    "be located in its own section text — "
                                    "recorded as unanchored, not guessed.")
                    s["start"], s["end"] = -1, -1
                else:
                    s["start"], s["end"] = idx, idx + len(s["text"])
                    pos = idx
        sections.append({"path": str(si), "heading": sec["heading"],
                          "src": sec.get("src", ""),
                          "paragraphs": paragraphs, "text": section_text})
    return {"representation_id": rep_id, "blob_id": blob_id, "kind": kind,
            "extractor": ({"name": extractor_tag} if kind in ("pdf", "docx")
                          else {"name": "wordicon-library-stdlib",
                                "rev": EXTRACTOR_REV}),
            "segmenter_rev": SEGMENTER_REV, "created_at": _now(),
            "title": title or fallback_title,
            "n_sections": len(sections), "n_sentences": n_sents,
            "sections": sections, "findings": findings}


# ---------------------------------------------------------------------------
# ingestion — acquisition and reading are separate records.

def detect_kind(filename: str, data: bytes) -> str:
    name = (filename or "").lower()
    # Magic bytes BEFORE extensions for the binary kinds (the medical
    # wing's adapters, docs/adr-medical-wing.md): a PDF named .txt must
    # reach the PDF extractor, not be mangled into "text" — the
    # extension is a claim, the bytes are the fact.
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:2] == b"PK" and b"mimetype" in data[:200] \
            and b"epub" in data[:200]:
        return "epub"
    if data[:2] == b"PK" and b"word/document.xml" in data[:4000]:
        return "docx"
    if name.endswith(".epub"):
        return "epub"
    if name.endswith(".pdf"):
        return "pdf"
    if name.endswith(".docx"):
        return "docx"
    if name.endswith((".html", ".htm", ".xhtml")):
        return "html"
    if name.endswith((".txt", ".md")):
        return "txt"
    head = data[:512].lstrip().lower()
    if head.startswith((b"<!doctype html", b"<html")):
        return "html"
    return "unsupported"


def ingest(data: bytes, filename: str = "", source: str = "",
            title: str = "") -> dict:
    """Store the bytes intact, record the acquisition, derive (or reuse)
    the deterministic representation, index it. No model anywhere."""
    kind = detect_kind(filename, data)
    if kind == "unsupported":
        raise ValueError("The library reads EPUB, HTML, plain text, PDF, and "
                         "DOCX. This file is none of those — refused plainly "
                         "rather than mangled into text.")
    blob_id = hashlib.sha256(data).hexdigest()
    lib_dir().mkdir(parents=True, exist_ok=True)
    blobs_dir().mkdir(exist_ok=True)
    reps_dir().mkdir(exist_ok=True)
    blob_path = blobs_dir() / blob_id
    if not blob_path.exists():
        blob_path.write_bytes(data)

    docs = load_documents()
    document_id = next((did for did, d in docs.items()
                        if blob_id in d.get("blob_ids", [])), None)
    new_document = document_id is None
    if new_document:
        document_id = "doc_" + hashlib.sha256(
            (blob_id + _now()).encode()).hexdigest()[:12]

    rep = build_representation(blob_id, kind, data, fallback_title=title or filename)
    rep_path = reps_dir() / f"{rep['representation_id']}.json"
    reused_rep = rep_path.exists()
    if not reused_rep:
        rep_path.write_text(json.dumps(rep, indent=1))
        index_representation(rep, document_id)

    ingest_id = "ing_" + hashlib.sha256(
        (blob_id + source + _now()).encode()).hexdigest()[:12]
    with open(ingests_log(), "a") as f:
        f.write(json.dumps({
            "ingest_id": ingest_id, "blob_id": blob_id,
            "document_id": document_id,
            "representation_id": rep["representation_id"],
            "source": source or filename or "(unstated)",
            "filename": filename, "retrieved_at": _now(),
            "bytes": len(data), "kind": kind,
            "extractor_rev": EXTRACTOR_REV, "segmenter_rev": SEGMENTER_REV,
        }) + "\n")

    d = docs.get(document_id) or {"title": "", "kind": kind, "created_at": _now(),
                                    "blob_ids": [], "representation_ids": []}
    d["title"] = title or d.get("title") or rep["title"] or filename or document_id
    if blob_id not in d["blob_ids"]:
        d["blob_ids"].append(blob_id)
    if rep["representation_id"] not in d["representation_ids"]:
        d["representation_ids"].append(rep["representation_id"])
    d["current_representation_id"] = rep["representation_id"]
    docs[document_id] = d
    docs_path().write_text(json.dumps(docs, indent=1))

    return {"document_id": document_id, "new_document": new_document,
            "blob_id": blob_id, "ingest_id": ingest_id,
            "representation_id": rep["representation_id"],
            "representation_reused": reused_rep,
            "title": d["title"], "kind": kind,
            "n_sections": rep["n_sections"], "n_sentences": rep["n_sentences"],
            "findings": rep["findings"]}


def load_representation(rep_id: str) -> dict:
    p = reps_dir() / f"{rep_id}.json"
    if not re.fullmatch(r"rep_[0-9a-f]{16}", rep_id or "") or not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def resolve_anchor(anchor_id: str) -> dict:
    """The mechanical resolution check: an anchor is (representation,
    path), and resolving it means SLICING the sentence out of its
    section's canonical text — string equality, no lookup table trusted."""
    m = re.fullmatch(r"(rep_[0-9a-f]{16}):(\d+)\.(\d+)\.(\d+)", anchor_id or "")
    if not m:
        return {"ok": False, "why": "not an anchor id"}
    rep = load_representation(m.group(1))
    if not rep:
        return {"ok": False, "why": "no such representation"}
    try:
        sec = rep["sections"][int(m.group(2))]
        para = sec["paragraphs"][int(m.group(3))]
        sent = para["sentences"][int(m.group(4))]
    except (IndexError, KeyError):
        return {"ok": False, "why": "no such path in the representation"}
    if sent["start"] < 0:
        return {"ok": False, "why": "recorded as unanchored at ingest",
                "text": sent["text"]}
    sliced = sec["text"][sent["start"]:sent["end"]]
    return {"ok": sliced == sent["text"], "text": sent["text"],
            "heading": sec["heading"], "start": sent["start"],
            "end": sent["end"],
            "why": "" if sliced == sent["text"] else "slice mismatch — the "
                   "representation is internally inconsistent"}


# ---------------------------------------------------------------------------
# search — the local lexical lane. Exact text in your library; not
# semantic, not the web, and labeled as such wherever it renders.

def _search_db() -> sqlite3.Connection:
    lib_dir().mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(search_db_path())
    db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS sentences USING fts5("
               "anchor_id UNINDEXED, document_id UNINDEXED, heading, text)")
    return db


def index_representation(rep: dict, document_id: str) -> int:
    db = _search_db()
    db.execute("DELETE FROM sentences WHERE anchor_id LIKE ?",
               (rep["representation_id"] + ":%",))
    n = 0
    for sec in rep["sections"]:
        for para in sec["paragraphs"]:
            for s in para["sentences"]:
                db.execute("INSERT INTO sentences VALUES (?, ?, ?, ?)",
                           (f"{rep['representation_id']}:{s['path']}",
                            document_id, sec["heading"], s["text"]))
                n += 1
    db.commit()
    db.close()
    return n


def search_terms(query: str, limit: int = 40) -> "list[dict]":
    """The QUESTION lane: a question is not a phrase from the document,
    so this matches any of the question's content words (FTS5 OR over
    quoted terms). Still purely lexical and local — recall here means
    'these words appear', never 'this answers you'."""
    words = re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", (query or ""))
    stop = {"the", "and", "for", "are", "was", "were", "what", "which",
            "does", "this", "that", "with", "from", "have", "has", "how",
            "when", "where", "who", "why", "can", "could", "should",
            "would", "say", "says", "about", "before", "after", "into",
            "each", "every", "their", "there", "than", "then", "them"}
    terms = []
    for w in words:
        lw = w.lower()
        if lw not in stop and lw not in terms:
            terms.append(lw)
    if not terms:
        return []
    match = " OR ".join('"' + t.replace('"', '""') + '"' for t in terms[:12])
    db = _search_db()
    try:
        rows = db.execute(
            "SELECT anchor_id, document_id, heading, "
            "snippet(sentences, 3, '«', '»', '…', 18) "
            "FROM sentences WHERE sentences MATCH ? LIMIT ?",
            (match, limit)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        db.close()
    return [{"anchor_id": a, "document_id": d, "heading": h, "snippet": s}
            for a, d, h, s in rows]


def search(query: str, limit: int = 40) -> "list[dict]":
    q = (query or "").strip()
    if not q:
        return []
    db = _search_db()
    try:
        rows = db.execute(
            "SELECT anchor_id, document_id, heading, "
            "snippet(sentences, 3, '«', '»', '…', 18) "
            "FROM sentences WHERE sentences MATCH ? LIMIT ?",
            ('"' + q.replace('"', '""') + '"', limit)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        db.close()
    return [{"anchor_id": a, "document_id": d, "heading": h, "snippet": s}
            for a, d, h, s in rows]


# ---------------------------------------------------------------------------
# Phase 1A — the crossing. A reader selection becomes an immutable SpanRef
# and one of four objects: note, claim, citation, Bench ingredient. All of
# it mechanical; the model is not consulted and cannot be from this module.
#
# The one rule that matters most is structural: creating a Claim from a
# passage records ONLY that the claim was created while viewing that span.
# It does not mean the span supports the claim. support is "unruled" at
# birth and stays unruled until the owner separately asks the support
# question and rules on the answer. Presence is not support.

CROSSING_KINDS = ("note", "claim", "citation", "ingredient")


def crossings_log() -> pathlib.Path:
    return lib_dir() / "crossings.jsonl"


def retrieve_span(rep: dict, start_path: str, start_offset: int,
                   end_path: str, end_offset: int) -> dict:
    """Mechanical retrieval: the span is a pure slice of the section's
    canonical extracted text, located via the two sentences' recorded
    offsets. Same-section only (the reader shows one section at a time, so
    a legal selection cannot cross one). The snapshot a crossing stores is
    for mismatch detection; THIS function is the authority, always."""
    def find(path):
        try:
            si, pi, zi = (int(x) for x in path.split("."))
            sec = rep["sections"][si]
            return si, sec, sec["paragraphs"][pi]["sentences"][zi]
        except (ValueError, IndexError, KeyError, AttributeError):
            return None, None, None
    s_si, s_sec, s_sent = find(start_path)
    e_si, e_sec, e_sent = find(end_path)
    if s_sent is None or e_sent is None:
        return {"ok": False, "why": "no such sentence in this representation"}
    if s_si != e_si:
        return {"ok": False, "why": "a selection cannot cross a section boundary"}
    if s_sent["start"] < 0 or e_sent["start"] < 0:
        return {"ok": False, "why": "an endpoint sentence was recorded as "
                                     "unanchored at ingest"}
    start_offset = max(0, min(int(start_offset), len(s_sent["text"])))
    end_offset = max(0, min(int(end_offset), len(e_sent["text"])))
    a = s_sent["start"] + start_offset
    b = e_sent["start"] + end_offset
    if b < a:
        a, b = e_sent["start"] + end_offset, s_sent["start"] + start_offset
    if b <= a:
        return {"ok": False, "why": "an empty selection is not a span"}
    text = s_sec["text"][a:b]
    return {"ok": True, "text": text, "section_index": s_si,
            "heading": s_sec["heading"], "abs_start": a, "abs_end": b}


def make_crossing(kind: str, representation_id: str, start_path: str,
                   start_offset: int, end_path: str, end_offset: int,
                   owner_text: str = "") -> dict:
    """Append one crossing. Idempotent by construction: the crossing_id is
    a content hash of (kind, span, owner text), so a double-click yields
    the same id and the second write is refused as a duplicate rather than
    silently stacking. Source wording and owner wording live in separate
    fields and no code path writes one from the other."""
    if kind not in CROSSING_KINDS:
        raise ValueError("a crossing is a note, claim, citation, or ingredient")
    rep = load_representation(representation_id)
    if not rep:
        raise ValueError("no such representation")
    got = retrieve_span(rep, start_path, start_offset, end_path, end_offset)
    if not got["ok"]:
        raise ValueError(got["why"])
    owner_text = (owner_text or "").strip()[:2000]
    if kind == "claim" and not owner_text:
        raise ValueError("a claim needs your own wording — the source span is "
                         "the view, not the claim")
    span_ref = {"representation_id": representation_id,
                "start_anchor": start_path, "start_offset": int(start_offset),
                "end_anchor": end_path, "end_offset": int(end_offset),
                "selected_text_hash": hashlib.sha256(got["text"].encode()).hexdigest(),
                "created_at": _now()}
    crossing_id = "cross_" + hashlib.sha256(
        f"{kind}|{representation_id}|{start_path}:{start_offset}|"
        f"{end_path}:{end_offset}|{owner_text}".encode()).hexdigest()[:12]
    existing = {r.get("crossing_id") for r in _read_crossing_rows()
                if r.get("type") == "crossing"}
    if crossing_id in existing:
        return {"crossing_id": crossing_id, "duplicate": True}
    docs = load_documents()
    document_id = next((did for did, d in docs.items()
                        if representation_id in d.get("representation_ids", [])), "")
    row = {"type": "crossing", "crossing_id": crossing_id, "kind": kind,
           "span_ref": span_ref, "document_id": document_id,
           "blob_id": rep.get("blob_id", ""),
           "snapshot_text": got["text"][:4000],   # mismatch detection ONLY
           "owner_text": owner_text, "created_at": _now()}
    if kind == "claim":
        # created while viewing this span — and that is ALL it means
        row["support"] = "unruled"
    with open(crossings_log(), "a") as f:
        f.write(json.dumps(row) + "\n")
    return {**row, "duplicate": False, "retrieved_text": got["text"],
            "heading": got["heading"]}


def _read_crossing_rows() -> "list[dict]":
    p = crossings_log()
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("type"):
            out.append(row)
    return out


def retract_crossing(crossing_id: str, undo: bool = False) -> dict:
    """Append-only and recoverable: a retraction is a new row, never a
    deletion, and an un-retraction is another row. The record keeps every
    change of mind in order."""
    if not any(r.get("crossing_id") == crossing_id and r.get("type") == "crossing"
               for r in _read_crossing_rows()):
        raise ValueError("no such crossing")
    row = {"type": "unretract" if undo else "retract",
           "crossing_id": crossing_id, "at": _now()}
    with open(crossings_log(), "a") as f:
        f.write(json.dumps(row) + "\n")
    return row


SUPPORT_RULING_BEARINGS = ("supports", "contradicts", "contextualizes",
                            "unrelated", "insufficient_span", "rejected")
SUPPORT_RULING_MODES = ("direct", "inference", "interpretation", "speculation")


def record_support_ruling(crossing_id: str, bearing: str, mode: str = None,
                           origin: str = "owner", basis: list = None,
                           reason: str = "", proposal_trace_id: str = "") -> dict:
    """The OWNER's half of the support question — mechanical append, no
    model, and now fully sovereign: adopting a proposal is one origin
    (adopted_model, carrying the proposal run's trace), ruling it yourself
    is another (owner, with optional basis and reason), and 'rejected'
    declines a proposal while leaving the claim unruled — the rejection
    stays as reversal data. A new ruling on an already-ruled claim
    AUTO-LINKS to the ruling it supersedes; history is never overwritten,
    only extended. The evidence boundary binds the owner too: a basis
    sentence outside the crossing's span is refused with reselection
    guidance — sovereignty is authority over judgment, not permission to
    create an untraceable citation."""
    if bearing not in SUPPORT_RULING_BEARINGS:
        raise ValueError("a support ruling is one of the five bearings, "
                         "or rejected")
    if bearing in ("supports", "contradicts", "contextualizes"):
        if mode not in SUPPORT_RULING_MODES:
            raise ValueError(f"an operative bearing ({bearing}) needs a mode — "
                             "direct, inference, interpretation, or speculation")
    elif mode:
        raise ValueError(f"{bearing} has no way of operating — no mode")
    if origin not in ("owner", "adopted_model"):
        raise ValueError("a ruling's origin is owner or adopted_model")
    base = [r for r in _read_crossing_rows()
            if r.get("crossing_id") == crossing_id and r.get("type") == "crossing"]
    if not base:
        raise ValueError("no such crossing")
    if base[0].get("kind") != "claim":
        raise ValueError("support is a question about claims")
    # the evidence boundary, applied to the owner's own basis
    clean_basis = []
    if basis:
        sr = base[0]["span_ref"]
        rep = load_representation(sr["representation_id"])
        known = {s2["path"] for sec in rep.get("sections", [])
                 for par in sec["paragraphs"] for s2 in par["sentences"]}
        k0 = tuple(int(x) for x in sr["start_anchor"].split("."))
        k1 = tuple(int(x) for x in sr["end_anchor"].split("."))
        if k1 < k0:
            k0, k1 = k1, k0
        outside = []
        for b in basis:
            b = str(b).strip().strip("[]")
            if not b:
                continue
            if b not in known:
                raise ValueError(f"basis [{b}] is not a sentence of this "
                                 "document — a ruling cannot rest on a "
                                 "citation that does not exist")
            bk = tuple(int(x) for x in b.split("."))
            (clean_basis if k0 <= bk <= k1 else outside).append(b)
        if outside:
            lo = min([k0] + [tuple(int(x) for x in b.split(".")) for b in outside])
            hi = max([k1] + [tuple(int(x) for x in b.split(".")) for b in outside])
            raise ValueError(
                "your basis runs beyond this crossing's span ("
                + ", ".join(f"[{b}]" for b in outside[:4])
                + ") — reselect through [" + ".".join(str(x) for x in lo)
                + "] to [" + ".".join(str(x) for x in hi)
                + "] and make the claim there. A ruling's citation must be "
                  "traceable to the span it rules on.")
    # auto-link: a ruling over an existing active ruling supersedes it
    active = ""
    for r in _read_crossing_rows():
        if r.get("type") == "support_ruling" and r.get("crossing_id") == crossing_id:
            if r.get("bearing") == "rejected":
                continue
            active = r.get("ruling_id", "")
    ruling_id = "rul_" + hashlib.sha256(
        f"{crossing_id}|{bearing}|{mode}|{_now()}".encode()).hexdigest()[:12]
    row = {"type": "support_ruling", "crossing_id": crossing_id,
           "ruling_id": ruling_id, "bearing": bearing, "mode": mode,
           "origin": origin, "basis": clean_basis,
           "reason": (reason or "").strip()[:500],
           "proposal_trace_id": (proposal_trace_id or "")[:60],
           "supersedes_ruling_id": active if bearing != "rejected" else "",
           "at": _now()}
    with open(crossings_log(), "a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def record_support_proposal(crossing_id: str, proposal: dict) -> None:
    """Persist a model proposal beside the claim it answers. A proposal
    NEVER changes the support state — only a ruling row does."""
    row = {"type": "support_proposal", "crossing_id": crossing_id,
           "at": _now(), **{k: proposal.get(k) for k in
                             ("bearing", "mode", "basis", "suggested_span",
                              "why", "findings", "trace_id", "model")}}
    with open(crossings_log(), "a") as f:
        f.write(json.dumps(row) + "\n")


def load_crossings(representation_id: str = "") -> "list[dict]":
    """Folded state: retractions, proposals, and rulings applied in log
    order; every displayed quotation freshly retrieved (the stored
    snapshot is compared, never trusted)."""
    rows = _read_crossing_rows()
    by_id = {}
    for r in rows:
        if r["type"] == "crossing":
            if representation_id and \
                    r["span_ref"]["representation_id"] != representation_id:
                continue
            by_id[r["crossing_id"]] = {**r, "retracted": False,
                                        "proposals": []}
        elif r["crossing_id"] in by_id:
            c = by_id[r["crossing_id"]]
            if r["type"] == "retract":
                c["retracted"] = True
            elif r["type"] == "unretract":
                c["retracted"] = False
            elif r["type"] == "support_proposal":
                c["proposals"].append({k: r.get(k) for k in
                                        ("bearing", "mode", "basis",
                                         "suggested_span", "why", "at",
                                         "trace_id")})
            elif r["type"] == "support_ruling":
                if r.get("bearing") == "rejected":
                    # a declined proposal leaves the claim unruled; the
                    # decline itself stays in the record as reversal data
                    c["support"] = "unruled"
                    c["support_mode"] = None
                    c["rejections"] = c.get("rejections", 0) + 1
                else:
                    c["support"] = r.get("bearing")
                    c["support_mode"] = r.get("mode")
                    c["support_origin"] = r.get("origin", "")
                    c["support_ruling_id"] = r.get("ruling_id", "")
                    c["support_reason"] = r.get("reason", "")
                    c["ruling_history"] = c.get("ruling_history", 0) + 1
                c["support_ruled_at"] = r["at"]
    out = []
    for c in by_id.values():
        rep = load_representation(c["span_ref"]["representation_id"])
        sr = c["span_ref"]
        got = retrieve_span(rep, sr["start_anchor"], sr["start_offset"],
                             sr["end_anchor"], sr["end_offset"]) if rep else \
            {"ok": False, "why": "representation missing"}
        if got.get("ok"):
            fresh_hash = hashlib.sha256(got["text"].encode()).hexdigest()
            c["retrieved_text"] = got["text"]
            c["heading"] = got.get("heading", "")
            c["mismatch"] = fresh_hash != sr["selected_text_hash"]
        else:
            c["retrieved_text"] = ""
            c["mismatch"] = True
            c["mismatch_why"] = got.get("why", "")
        out.append(c)
    out.sort(key=lambda c: c["created_at"], reverse=True)
    return out


# ---------------------------------------------------------------------------
# The Work Room — the works registry (backlog items 21/21b, owner's go
# 2026-08-29). One canonical place for a work, linking identities that
# already exist (source-index entries, Map external keys, imported
# documents, owner-declared Wikipedia/Wikidata/external references)
# WITHOUT replacing any of them. Constitution, enforced here:
# - Work identity is never inferred from a normalized title: work_id is a
#   content-and-time hash, so Camus's The Fall and the Genesis fall keep
#   different ids however their titles normalize.
# - Every link is an OWNER ruling: append-only, origin kept, supersession
#   and retraction as lineage, never a string match.
# - Zero model calls, zero network: this module still may not mention a
#   gateway, and nothing here fetches anything.

WORK_KINDS = ("novel", "poem", "play", "paper", "essay", "scripture",
               "program", "film", "speech", "song", "other")
LINK_SUBJECT_KINDS = ("source_entry", "map_key", "document", "wikipedia",
                       "wikidata", "external_ref")
DOORWAY_ROLES = ("whole work", "character or figure", "section or chapter",
                  "episode or scene", "question or argument", "other")
DOCUMENT_ROLES = ("edition", "translation", "adaptation", "excerpt")
SOURCE_FUNCTIONS = ("primary", "reference", "scholarship",
                     "edition or catalog", "owner record")
ACCESS_STATUSES = ("found - not opened", "metadata only", "abstract read",
                    "paywalled", "full text available", "passage imported")
_QID_RX = re.compile(r"^Q[1-9]\d{0,15}$")


def works_log() -> pathlib.Path:
    return lib_dir() / "works.jsonl"


def _read_work_rows() -> "list[dict]":
    p = works_log()
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("type"):
            out.append(row)
    return out


def _append_work_row(row: dict) -> None:
    lib_dir().mkdir(parents=True, exist_ok=True)
    with open(works_log(), "a") as f:
        f.write(json.dumps(row) + "\n")


def safe_external_url(url: str) -> str:
    """http(s) only, structurally. javascript:, data:, file:, and
    malformed URLs are refused — and because v1 never fetches any of
    these, there is deliberately no endpoint capable of SSRF."""
    u = (url or "").strip()
    if len(u) > 2000:
        raise ValueError("that URL is implausibly long")
    low = u.lower()
    if not (low.startswith("http://") or low.startswith("https://")):
        raise ValueError("only http and https URLs are kept — anything else "
                         "is refused, not sanitized")
    if any(c in u for c in ("<", ">", '"', " ")):
        raise ValueError("that is not a well-formed URL")
    if len(u.split("://", 1)[1].split("/")[0]) < 3:
        raise ValueError("that URL has no plausible host")
    return u


def create_work(canonical_title: str, creator_display: str = "",
                 work_kind: str = "other", original_date: str = "") -> dict:
    """No model call anywhere near this. The id is hashed from title AND
    creation instant, so two works with byte-identical titles are two
    works — identity is the owner's declaration, never the spelling."""
    title = (canonical_title or "").strip()[:200]
    if not title:
        raise ValueError("a work needs its canonical title")
    kind = work_kind if work_kind in WORK_KINDS else "other"
    row = {"type": "work",
           # the salt keeps two same-second creations two works; identity is
           # the owner's act, so nothing about it may depend on the title
           # alone — or on the clock being coarse enough to disambiguate
           "work_id": "work_" + hashlib.sha256(
               (title + "|" + _now() + "|" + creator_display + "|"
                + os.urandom(6).hex()).encode()).hexdigest()[:12],
           "canonical_title": title,
           "creator_display": (creator_display or "").strip()[:160],
           "work_kind": kind,
           "original_date": (original_date or "").strip()[:40] or None,
           "created_at": _now(), "created_by": "owner"}
    _append_work_row(row)
    return row


def link_work(work_id: str, subject_kind: str, subject_id: str,
               role: str = "", origin: str = "owner",
               proposal_trace_id: str = "") -> dict:
    """An owner ruling that one existing identity IS (or belongs to) this
    work. Auto-supersedes any active link for the same subject — the
    lineage is kept, never overwritten. Nothing links itself: this
    function is only ever reached by an explicit owner action."""
    if subject_kind not in LINK_SUBJECT_KINDS:
        raise ValueError("a link's subject is a source entry, map key, "
                         "document, wikipedia page, wikidata id, or saved "
                         "external reference")
    if origin not in ("owner", "adopted_proposal"):
        raise ValueError("a link's origin is owner or adopted_proposal")
    subject_id = (subject_id or "").strip()[:2000]
    if not subject_id:
        raise ValueError("a link needs its subject")
    works = {r["work_id"] for r in _read_work_rows() if r["type"] == "work"}
    if work_id not in works:
        raise ValueError("no such work")
    if subject_kind == "source_entry":
        if role not in DOORWAY_ROLES:
            raise ValueError("a source-entry link declares its doorway role: "
                             + ", ".join(DOORWAY_ROLES))
    elif subject_kind == "document":
        if role not in DOCUMENT_ROLES:
            raise ValueError("a document link declares what it is: "
                             + ", ".join(DOCUMENT_ROLES))
        if subject_id not in load_documents():
            raise ValueError("no such imported document")
    elif subject_kind == "wikidata":
        if not _QID_RX.fullmatch(subject_id):
            raise ValueError("a Wikidata link is a QID like Q12345 — it anchors "
                             "an identity you declared; it never establishes one")
        role = "reference"
    elif subject_kind == "wikipedia":
        subject_id = safe_external_url(subject_id)
        role = "reference"
    elif subject_kind == "external_ref":
        role = role or "reference"
    else:  # map_key
        role = role or "whole work"
    active = ""
    for r in _read_work_rows():
        if r["type"] == "work_link" and r.get("subject_kind") == subject_kind \
                and r.get("subject_id") == subject_id:
            active = r.get("link_id", "")
        elif r["type"] == "work_link_retract" and r.get("link_id") == active:
            active = ""
    row = {"type": "work_link",
           "link_id": "wlink_" + hashlib.sha256(
               (work_id + subject_kind + subject_id + _now()
                + os.urandom(6).hex()).encode()).hexdigest()[:12],
           "work_id": work_id, "subject_kind": subject_kind,
           "subject_id": subject_id, "role": role,
           "origin": origin, "proposal_trace_id": (proposal_trace_id or "")[:60],
           "ratified_by": "owner",
           "supersedes_link_id": active, "at": _now()}
    _append_work_row(row)
    return row


def retract_work_link(link_id: str) -> dict:
    if not any(r.get("link_id") == link_id and r["type"] == "work_link"
               for r in _read_work_rows()):
        raise ValueError("no such link")
    row = {"type": "work_link_retract", "link_id": link_id, "at": _now()}
    _append_work_row(row)
    return row


def save_external_ref(work_id: str, url: str, title: str,
                       source_function: str) -> dict:
    """An owner deliberately keeping a URL found through the shelf's
    doors. Two independent typed fields — what it IS (function) and how
    far you actually got (access status, appended separately). Saving
    records nothing about reading: the first status row is the owner's
    own claim, made explicitly."""
    if source_function not in SOURCE_FUNCTIONS:
        raise ValueError("a source's function is one of: "
                         + ", ".join(SOURCE_FUNCTIONS))
    works = {r["work_id"] for r in _read_work_rows() if r["type"] == "work"}
    if work_id not in works:
        raise ValueError("no such work")
    row = {"type": "external_ref",
           "ref_id": "xref_" + hashlib.sha256(
               (work_id + url + _now() + os.urandom(6).hex()).encode()
               ).hexdigest()[:12],
           "work_id": work_id, "url": safe_external_url(url),
           "title": (title or "").strip()[:300],
           "source_function": source_function, "at": _now()}
    _append_work_row(row)
    return row


def set_access_status(ref_id: str, status: str) -> dict:
    """Append-only, explicit, and descriptive — never an authority
    ranking, and never set by a click on a door."""
    if status not in ACCESS_STATUSES:
        raise ValueError("an access status is one of: "
                         + ", ".join(ACCESS_STATUSES))
    if not any(r.get("ref_id") == ref_id and r["type"] == "external_ref"
               for r in _read_work_rows()):
        raise ValueError("no such external reference")
    row = {"type": "access_status", "ref_id": ref_id, "status": status,
           "at": _now()}
    _append_work_row(row)
    return row


def load_works() -> dict:
    """Folded registry: works with their active links (supersession and
    retraction applied in log order), external refs with status history.
    A rebuildable view — the log is the record."""
    rows = _read_work_rows()
    works, links, refs = {}, {}, {}
    for r in rows:
        t = r["type"]
        if t == "work":
            works[r["work_id"]] = {**r, "links": [], "external_refs": []}
        elif t == "work_link":
            links[r["link_id"]] = {**r, "retracted": False}
            sup = r.get("supersedes_link_id")
            if sup and sup in links:
                links[sup]["superseded_by"] = r["link_id"]
        elif t == "work_link_retract" and r.get("link_id") in links:
            links[r["link_id"]]["retracted"] = True
        elif t == "external_ref":
            refs[r["ref_id"]] = {**r, "status": "", "status_history": []}
        elif t == "access_status" and r.get("ref_id") in refs:
            refs[r["ref_id"]]["status"] = r["status"]
            refs[r["ref_id"]]["status_history"].append(
                {"status": r["status"], "at": r["at"]})
    for l in links.values():
        if l["work_id"] in works and not l["retracted"] \
                and not l.get("superseded_by"):
            works[l["work_id"]]["links"].append(l)
    for x in refs.values():
        if x["work_id"] in works:
            works[x["work_id"]]["external_refs"].append(x)
    return works


def works_for_subject() -> dict:
    """(subject_kind, subject_id) → work summary, active links only —
    what the Sources page consults to render 'Enter <work>'."""
    out = {}
    for w in load_works().values():
        for l in w["links"]:
            out[(l["subject_kind"], l["subject_id"])] = {
                "work_id": w["work_id"],
                "canonical_title": w["canonical_title"],
                "creator_display": w["creator_display"],
                "role": l["role"], "link_id": l["link_id"]}
    return out


# ===========================================================================
# The media lane (slices 1 and 2 of the media spine — owner's go 2026-08-29).
# A recording enters byte-intact and zero-model, exactly like a document.
# The transcript is a SEPARATE, VERSIONED derivative that can be wrong —
# the audio or video remains the source, and the page says so on its face.
# v1 deliberately builds no speech recognition and touches no platform:
# files you own, transcripts you supply — SRT or WebVTT, because a
# transcript without timestamps cannot anchor time. Corrections never
# overwrite: a new transcript is a new version beside the old one. Time
# crossings carry the transcript version they were made against, and every
# displayed quotation is retrieved fresh from the stored segments — the
# snapshot only detects drift; it never testifies.

TRANSCRIPT_PARSER_REV = 1
MEDIA_EXTS = {".mp3": "audio", ".m4a": "audio", ".wav": "audio",
              ".ogg": "audio", ".oga": "audio", ".flac": "audio",
              ".weba": "audio",   # block 106: an audio-only WebM, as a browser's recorder makes it
              ".mp4": "video", ".m4v": "video", ".webm": "video",
              ".mov": "video"}
MEDIA_MIME = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".wav": "audio/wav",
              ".ogg": "audio/ogg", ".oga": "audio/ogg", ".flac": "audio/flac",
              ".weba": "audio/webm",   # block 106
              ".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm",
              ".mov": "video/quicktime"}
TRANSCRIPT_ORIGINS = ("publisher-supplied", "platform captions",
                       "locally generated", "owner-corrected")
MEDIA_CROSSING_KINDS = ("note", "claim", "citation", "ingredient")


def media_log() -> pathlib.Path:
    return lib_dir() / "media.jsonl"


def transcripts_dir() -> pathlib.Path:
    return lib_dir() / "transcripts"


def media_crossings_log() -> pathlib.Path:
    return lib_dir() / "media_crossings.jsonl"


def _read_media_rows() -> "list[dict]":
    p = media_log()
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("type"):
            out.append(row)
    return out


def _append_media_row(row: dict) -> None:
    lib_dir().mkdir(parents=True, exist_ok=True)
    with open(media_log(), "a") as f:
        f.write(json.dumps(row) + "\n")


def ingest_media(data: bytes, filename: str = "", source: str = "",
                  title: str = "") -> dict:
    """Store the recording byte-intact, record the acquisition. No model,
    no probe, no network — duration is the player's business at play time,
    never a record. Identity is the bytes: the same file re-ingested is
    the same media item with a new acquisition row."""
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    kind = MEDIA_EXTS.get(ext, "")
    if not kind:
        raise ValueError("Media takes the recordings you own — "
                         + ", ".join(sorted(MEDIA_EXTS)) + ". This file is "
                         "none of those; no platform is scraped and nothing "
                         "is fetched for you.")
    if not data:
        raise ValueError("that file is empty")
    blob_id = hashlib.sha256(data).hexdigest()
    lib_dir().mkdir(parents=True, exist_ok=True)
    blobs_dir().mkdir(exist_ok=True)
    blob_path = blobs_dir() / blob_id
    if not blob_path.exists():
        blob_path.write_bytes(data)
    media_id = "media_" + blob_id[:12]
    rows = _read_media_rows()
    existing = any(r.get("media_id") == media_id and r["type"] == "media"
                   for r in rows)
    if not existing:
        _append_media_row({"type": "media", "media_id": media_id,
                            "blob_id": blob_id, "kind": kind,
                            "mime": MEDIA_MIME[ext], "ext": ext,
                            "title": (title or filename or media_id)[:300],
                            "bytes": len(data), "created_at": _now()})
    _append_media_row({"type": "media_acquisition", "media_id": media_id,
                        "source": (source or filename or "(unstated)")[:500],
                        "filename": filename[:300], "retrieved_at": _now()})
    return {"media_id": media_id, "blob_id": blob_id, "kind": kind,
            "reused": existing}


# ---- transcript parsing — stdlib only, pinned by TRANSCRIPT_PARSER_REV ----
# Parser rules, stated because they are rules and not judgment: cue lines
# are stripped and joined with single spaces (SRT wraps lines for display
# width, which is presentation, not speech); WebVTT voice tags <v Name>
# become the segment's speaker because the FILE established it; other
# inline markup tags are removed and COUNTED into findings. Cues are kept
# in file order — reordering a transcript would be smoothing. A changed
# rule here MUST bump TRANSCRIPT_PARSER_REV or the suite goes red.

_TIME_RX = re.compile(
    r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[.,](\d{3})")
_VOICE_RX = re.compile(r"^<v(?:[ .][^>]*)?>")
_TAG_RX = re.compile(r"</?[^>]+>")


def _parse_ts(s: str):
    m = _TIME_RX.fullmatch(s.strip())
    if not m:
        return None
    h = int(m.group(1) or 0)
    return h * 3600 + int(m.group(2)) * 60 + int(m.group(3)) \
        + int(m.group(4)) / 1000.0


def _parse_cue_text(lines: "list[str]"):
    """Speaker from a leading WebVTT voice tag only; inline markup
    stripped and counted, never silently."""
    speaker = None
    stripped_tags = 0
    out = []
    for j, ln in enumerate(lines):
        ln = ln.strip()
        if j == 0:
            vm = _VOICE_RX.match(ln)
            if vm:
                inner = vm.group(0)[2:-1].strip()
                speaker = inner.lstrip(". ").strip() or None
                ln = ln[vm.end():].strip()
        n_tags = len(_TAG_RX.findall(ln))
        if n_tags:
            stripped_tags += n_tags
            ln = _TAG_RX.sub("", ln).strip()
        if ln:
            out.append(ln)
    return " ".join(out), speaker, stripped_tags


def parse_transcript(text: str, fmt: str):
    """SRT or WebVTT → ordered segments + findings. Malformed cues are
    skipped and COUNTED — a parser that swallows a cue silently is lying
    about the transcript it produced."""
    findings = []
    segments = []
    bad = 0
    first_bad = ""
    stripped_tags = 0
    body = text.replace("\r\n", "\n").replace("\r", "\n")
    if fmt == "vtt":
        if not body.lstrip().startswith("WEBVTT"):
            findings.append("file claims .vtt but has no WEBVTT header — "
                            "parsed anyway; treat with suspicion")
        else:
            body = body.lstrip().split("\n", 1)[1] if "\n" in body.lstrip() \
                else ""
    blocks = [b for b in re.split(r"\n\s*\n", body) if b.strip()]
    for b in blocks:
        lines = b.split("\n")
        # NOTE/STYLE/REGION blocks are VTT metadata, not speech
        if fmt == "vtt" and lines[0].split(" ")[0] in ("NOTE", "STYLE",
                                                        "REGION"):
            continue
        ti = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if ti is None:
            bad += 1
            first_bad = first_bad or b.strip().split("\n")[0][:60]
            continue
        halves = lines[ti].split("-->")
        start = _parse_ts(halves[0])
        end = _parse_ts(halves[1].strip().split(" ")[0]) \
            if len(halves) > 1 else None
        if start is None or end is None:
            bad += 1
            first_bad = first_bad or lines[ti][:60]
            continue
        cue_text, speaker, n_tags = _parse_cue_text(lines[ti + 1:])
        stripped_tags += n_tags
        if not cue_text:
            continue
        seg = {"i": len(segments), "start": round(start, 3),
               "end": round(end, 3), "text": cue_text}
        if speaker:
            seg["speaker"] = speaker
        segments.append(seg)
    if bad:
        findings.append(f"{bad} cue(s) could not be parsed and were skipped "
                        f"— first: “{first_bad}”. The recording still holds "
                        "whatever they said; this transcript does not.")
    if stripped_tags:
        findings.append(f"{stripped_tags} inline markup tag(s) removed by "
                        f"the parser (rev {TRANSCRIPT_PARSER_REV}); voice "
                        "tags became speakers, nothing else was kept")
    n_overlap = sum(1 for a, b2 in zip(segments, segments[1:])
                    if b2["start"] < a["end"])
    if n_overlap:
        findings.append(f"{n_overlap} cue(s) overlap the one before them — "
                        "kept in file order, not reordered")
    n_backwards = sum(1 for s in segments if s["end"] <= s["start"])
    if n_backwards:
        findings.append(f"{n_backwards} cue(s) end at or before their own "
                        "start — kept and flagged, not repaired")
    return segments, findings


def add_transcript(media_id: str, data: bytes, filename: str = "",
                    origin: str = "", source: str = "", engine: "dict | None" = None) -> dict:
    """A transcript version: byte-intact original, deterministic derived
    segments, origin DECLARED by you from a bounded vocabulary. A new
    upload — including your own correction — is a new version beside the
    old one; nothing here overwrites."""
    rows = _read_media_rows()
    if not any(r.get("media_id") == media_id and r["type"] == "media"
               for r in rows):
        raise ValueError("no such media item")
    if origin not in TRANSCRIPT_ORIGINS:
        raise ValueError("a transcript's origin is one of: "
                         + ", ".join(TRANSCRIPT_ORIGINS))
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("that transcript is not UTF-8 text — refused "
                         "plainly rather than guessed at")
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext == ".vtt" or text.lstrip().startswith("WEBVTT"):
        fmt = "vtt"
    elif ext == ".srt" or re.search(r"-->", text):
        fmt = "srt"
    else:
        raise ValueError("A transcript needs timestamps to anchor time — "
                         "SRT or WebVTT. Plain text can say what was said "
                         "but never WHEN, so it cannot drive the player or "
                         "hold a time crossing; refused plainly.")
    blob_id = hashlib.sha256(data).hexdigest()
    blobs_dir().mkdir(parents=True, exist_ok=True)
    if not (blobs_dir() / blob_id).exists():
        (blobs_dir() / blob_id).write_bytes(data)
    transcript_id = "tsc_" + hashlib.sha256(
        f"{blob_id}|{media_id}|{origin}|parser:{TRANSCRIPT_PARSER_REV}"
        .encode()).hexdigest()[:12]
    transcripts_dir().mkdir(parents=True, exist_ok=True)
    tpath = transcripts_dir() / f"{transcript_id}.json"
    reused = tpath.exists()
    if not reused:
        segments, findings = parse_transcript(text, fmt)
        if not segments:
            raise ValueError("no cue in that file survived parsing — "
                             "nothing to anchor; the findings would have "
                             "been: " + ("; ".join(findings) or "none"))
        tdoc = {"transcript_id": transcript_id, "media_id": media_id,
                "blob_id": blob_id, "format": fmt, "origin": origin,
                "parser_rev": TRANSCRIPT_PARSER_REV,
                "segments": segments, "findings": findings,
                "created_at": _now()}
        row = {"type": "transcript",
               "transcript_id": transcript_id,
               "media_id": media_id, "blob_id": blob_id,
               "format": fmt, "origin": origin,
               "source": (source or filename or "(unstated)")[:500],
               "filename": filename[:300],
               "n_segments": len(segments),
               "last_end": segments[-1]["end"],
               "parser_rev": TRANSCRIPT_PARSER_REV,
               "findings": findings, "created_at": _now()}
        # block 106: a transcript a local engine produced names the engine
        # and its settings; an owner correction names the machine version
        # it corrects. Recorded as given, never inferred.
        if isinstance(engine, dict) and engine:
            tdoc["engine"] = dict(engine); row["engine"] = dict(engine)
        tpath.write_text(json.dumps(tdoc, indent=1))
        _append_media_row(row)
    else:
        tdoc = json.loads(tpath.read_text())
    return {"transcript_id": transcript_id, "reused": reused,
            "n_segments": len(tdoc["segments"]),
            "findings": tdoc["findings"], "origin": origin}


def load_media() -> dict:
    """Folded view: each media item with its acquisitions and every
    transcript version — versions listed, never merged, never ranked."""
    out = {}
    for r in _read_media_rows():
        if r["type"] == "media":
            out[r["media_id"]] = {**r, "acquisitions": [], "transcripts": []}
        elif r["type"] == "media_acquisition" and r.get("media_id") in out:
            out[r["media_id"]]["acquisitions"].append(
                {k: r.get(k) for k in ("source", "filename", "retrieved_at")})
        elif r["type"] == "transcript" and r.get("media_id") in out:
            out[r["media_id"]]["transcripts"].append(
                {k: r.get(k) for k in ("transcript_id", "origin", "format",
                                        "n_segments", "last_end",
                                        "parser_rev", "findings", "source",
                                        "created_at", "engine")})   # engine: block 106, when a version names one
    return out


def load_transcript(transcript_id: str) -> dict:
    p = transcripts_dir() / f"{transcript_id}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def retrieve_media_span(tdoc: dict, start_i: int, end_i: int) -> dict:
    """Mechanical retrieval of a segment range — the authority every
    rendered quotation comes from."""
    segs = tdoc.get("segments") or []
    try:
        start_i, end_i = int(start_i), int(end_i)
    except (TypeError, ValueError):
        return {"ok": False, "why": "segment indices must be integers"}
    if start_i > end_i:
        start_i, end_i = end_i, start_i
    if start_i < 0 or end_i >= len(segs):
        return {"ok": False,
                "why": f"segment {max(start_i, end_i)} does not exist — this "
                       f"transcript has {len(segs)}"}
    got = segs[start_i:end_i + 1]
    return {"ok": True, "text": " ".join(s["text"] for s in got),
            "start": got[0]["start"], "end": got[-1]["end"],
            "speakers": sorted({s["speaker"] for s in got if s.get("speaker")})}


def _read_media_crossing_rows() -> "list[dict]":
    p = media_crossings_log()
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def make_media_crossing(kind: str, transcript_id: str, start_i: int,
                         end_i: int, owner_text: str = "") -> dict:
    """A moment kept: an immutable reference to a segment range of ONE
    transcript version, at its exact times. Same constitution as the text
    crossing — content-hash id so a double-click cannot stack, source
    wording and owner wording in separate fields, claims born unruled
    because presence is not support."""
    if kind not in MEDIA_CROSSING_KINDS:
        raise ValueError("a media crossing is a note, claim, citation, or "
                         "ingredient")
    tdoc = load_transcript(transcript_id)
    if not tdoc:
        raise ValueError("no such transcript")
    got = retrieve_media_span(tdoc, start_i, end_i)
    if not got["ok"]:
        raise ValueError(got["why"])
    owner_text = (owner_text or "").strip()[:2000]
    if kind == "claim" and not owner_text:
        raise ValueError("a claim needs your own wording — the spoken span "
                         "is the view, not the claim")
    crossing_id = "mcross_" + hashlib.sha256(
        f"{kind}|{transcript_id}|{int(start_i)}|{int(end_i)}|{owner_text}"
        .encode()).hexdigest()[:12]
    if any(r.get("crossing_id") == crossing_id and r.get("type") == "crossing"
           for r in _read_media_crossing_rows()):
        return {"crossing_id": crossing_id, "duplicate": True}
    row = {"type": "crossing", "crossing_id": crossing_id, "kind": kind,
           "media_id": tdoc["media_id"], "transcript_id": transcript_id,
           "start_i": int(min(start_i, end_i)),
           "end_i": int(max(start_i, end_i)),
           "start_time": got["start"], "end_time": got["end"],
           "selected_text_hash": hashlib.sha256(
               got["text"].encode()).hexdigest(),
           "snapshot_text": got["text"][:4000],   # drift detection ONLY
           "owner_text": owner_text, "created_at": _now()}
    if kind == "claim":
        row["support"] = "unruled"
    lib_dir().mkdir(parents=True, exist_ok=True)
    with open(media_crossings_log(), "a") as f:
        f.write(json.dumps(row) + "\n")
    return {**row, "duplicate": False, "retrieved_text": got["text"]}


def retract_media_crossing(crossing_id: str, undo: bool = False) -> dict:
    rows = _read_media_crossing_rows()
    if not any(r.get("crossing_id") == crossing_id
               and r.get("type") == "crossing" for r in rows):
        raise ValueError("no such crossing")
    row = {"type": "unretract" if undo else "retract",
           "crossing_id": crossing_id, "at": _now()}
    with open(media_crossings_log(), "a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def rule_media_claim(crossing_id: str, bearing: str, mode: str = None,
                      origin: str = "owner", reason: str = "") -> dict:
    """The owner's ruling on a media claim — same two-axis vocabulary as
    the text lane (one vocabulary family, never a fork), mechanical,
    model-free, supersession by link. The model's support question does
    not run on media claims yet, and this function is not it."""
    if bearing not in SUPPORT_RULING_BEARINGS:
        raise ValueError("a support ruling is one of the five bearings, "
                         "or rejected")
    if bearing in ("supports", "contradicts", "contextualizes"):
        if mode not in SUPPORT_RULING_MODES:
            raise ValueError(f"an operative bearing ({bearing}) needs a mode "
                             "— direct, inference, interpretation, or "
                             "speculation")
    elif mode:
        raise ValueError(f"{bearing} has no way of operating — no mode")
    if origin not in ("owner", "adopted_model"):
        raise ValueError("a ruling's origin is owner or adopted_model")
    base = [r for r in _read_media_crossing_rows()
            if r.get("crossing_id") == crossing_id
            and r.get("type") == "crossing"]
    if not base:
        raise ValueError("no such crossing")
    if base[0].get("kind") != "claim":
        raise ValueError("support is a question about claims")
    prior = ""
    for r in _read_media_crossing_rows():
        if r.get("type") == "support_ruling" \
                and r.get("crossing_id") == crossing_id \
                and r.get("bearing") != "rejected":
            prior = r.get("ruling_id", "")
    row = {"type": "support_ruling",
           "ruling_id": "mrul_" + hashlib.sha256(
               (crossing_id + bearing + _now() + os.urandom(6).hex())
               .encode()).hexdigest()[:12],
           "crossing_id": crossing_id, "bearing": bearing, "mode": mode,
           "origin": origin, "reason": (reason or "")[:500],
           "supersedes_ruling_id": prior, "at": _now()}
    with open(media_crossings_log(), "a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def load_media_crossings(transcript_id: str = "") -> "list[dict]":
    """Folded state, every quotation retrieved fresh — the stored snapshot
    is compared, never trusted."""
    by_id = {}
    for r in _read_media_crossing_rows():
        if r.get("type") == "crossing":
            if transcript_id and r.get("transcript_id") != transcript_id:
                continue
            by_id[r["crossing_id"]] = {**r, "retracted": False}
        elif r.get("crossing_id") in by_id:
            c = by_id[r["crossing_id"]]
            if r["type"] == "retract":
                c["retracted"] = True
            elif r["type"] == "unretract":
                c["retracted"] = False
            elif r["type"] == "support_ruling":
                if r.get("bearing") == "rejected":
                    c["support"] = "unruled"
                    c["support_mode"] = None
                    c["rejections"] = c.get("rejections", 0) + 1
                else:
                    c["support"] = r.get("bearing")
                    c["support_mode"] = r.get("mode")
                    c["support_origin"] = r.get("origin", "")
                    c["support_reason"] = r.get("reason", "")
                    c["ruling_history"] = c.get("ruling_history", 0) + 1
    out = []
    for c in by_id.values():
        tdoc = load_transcript(c["transcript_id"])
        got = retrieve_media_span(tdoc, c["start_i"], c["end_i"]) if tdoc \
            else {"ok": False, "why": "transcript missing"}
        if got.get("ok"):
            c["retrieved_text"] = got["text"]
            c["mismatch"] = hashlib.sha256(
                got["text"].encode()).hexdigest() != c["selected_text_hash"]
        else:
            c["retrieved_text"] = ""
            c["mismatch"] = True
            c["mismatch_why"] = got.get("why", "")
        out.append(c)
    out.sort(key=lambda c: c["created_at"], reverse=True)
    return out
