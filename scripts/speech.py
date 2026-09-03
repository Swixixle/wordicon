"""Speak to Nikodemus — the transcription adapter (block 106, amended in
106b; backlog items 53, 55, 56; docs/adr-speak.md).

The one boundary between a recording and words. Audio arrives as bytes
in memory and leaves as a transcript with the engine's identity on it;
the transcription path opens no file for writing, spools to no
temporary file, touches no network, and consults no language model.
The real engine is faster-whisper (MIT; CTranslate2, PyAV with its
decoders bundled), running on this machine with a model fetched ONCE
by a visible owner action into a cache outside local_state — and that
fetch is recorded: the model's source, revision, file hashes and
license.

The vocabulary hint biases what is heard, so it is governed (block
106b, the reviewer's ruling): in order of standing, the visible name
and the words the owner declared the engine must hear right; the names
of what is open now (a concept, a Room, a document, a work); the shelf
titles the owner pinned for speech; then the shelf as space remains,
in a deterministic order that is not newness. Every transcript cites a
content-addressed manifest of the exact terms it was told and where
each came from — a count and a hash alone cannot reconstruct why the
engine heard a word one way. The owner's declared and pinned words are
appended events, never a file rewritten in place; their projection is
a plain file rebuilt from the events.

The writes this module makes, each by an owner action and none by
transcribing: the vocabulary events and their projection (his Save),
the model record (his fetch), and the hint manifest (his Send or Keep
— content-addressed, written once per distinct hint). The mock engine
is the suite's and the journeys'; production never falls back to it —
an engine that is not installed is reported as not installed."""
from __future__ import annotations

import collections
import hashlib
import io
import json
import os
import pathlib
import re
import time

import wordicon_cli as cli

ENGINE_NAME = "faster-whisper"
DEFAULT_MODEL = "base.en"
COMPUTE_TYPE = "int8"
MODEL_REPOS = {"tiny.en": "Systran/faster-whisper-tiny.en", "base.en": "Systran/faster-whisper-base.en",
               "small.en": "Systran/faster-whisper-small.en"}
MODEL_SOURCE = "https://huggingface.co/"
MAX_AUDIO_BYTES = 25_000_000          # about four minutes of opus at 32 kb/s, with room
ACCEPTED_MIMES = ("audio/webm", "audio/mp4", "audio/ogg", "audio/wav", "audio/x-wav", "audio/mpeg", "audio/m4a", "audio/x-m4a")
VOCAB_CHAR_CAP = 700                  # the outer bound in characters, for when no tokenizer can measure
VOCAB_TOKEN_CAP = 190                 # Whisper keeps the LAST 223 prompt tokens: over that, the front — the owner's own words — is what gets cut (found on the real shelf, 106b)
TERM_TOKEN_CEILING = 12               # a shelf title costing more than this (a gloss, a foreign script) is left out of the fallback, and listed
ENGINE = None                         # set to an Engine by the server (real) or the suite (mock)
_MODEL_CACHE: dict = {}
_TOKENIZER: dict = {}

HINT_FRAME = "Words in use here: "
HINT_REV = "hint-2"                   # block 106b: tiers, sources, manifest, the token cap
HINT_TIERS = ("brand", "declared", "context", "pinned", "shelf")
VOCAB_KINDS = ("declare", "undeclare", "pin", "unpin")
CONTEXT_KINDS = ("concept", "room", "media", "work", "artifact")
HINT_CACHE: "collections.OrderedDict[str, dict]" = collections.OrderedDict()
HINT_CACHE_SIZE = 64
_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")


# ---- paths (all under local_state, so the Vault carries them) ---------------

def vocabulary_path() -> pathlib.Path:
    """The projection — a plain file rebuilt from the events."""
    return cli.LOCAL_STATE / "speech_vocabulary.json"


def vocabulary_events_path() -> pathlib.Path:
    return cli.LOCAL_STATE / "speech_vocabulary_events.jsonl"


def hints_dir() -> pathlib.Path:
    return cli.LOCAL_STATE / "speech_hints"


def model_records_path() -> pathlib.Path:
    return cli.LOCAL_STATE / "speech_models.jsonl"


def _read_rows(p: pathlib.Path) -> "list[dict]":
    if not p.exists():
        return []
    out = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return out


def _append_row(p: pathlib.Path, row: dict) -> None:
    cli.LOCAL_STATE.mkdir(exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


# ---- the owner's words: events, never a rewrite --------------------------------

def brand_words() -> "list[str]":
    """The visible name, from config/brand.json — never a shelf title, and
    the first thing the engine must hear right (the spike heard it as the
    Biblical spelling every time until it was told)."""
    try:
        name = (json.loads((cli.REPO_ROOT / "config" / "brand.json").read_text(encoding="utf-8")).get("name") or "").strip()
        return [name] if name else []
    except Exception:  # noqa: BLE001
        return []


def _clean_term(w) -> str:
    return str(w or "").strip()[:80]


def load_vocabulary_events() -> "list[dict]":
    return [r for r in _read_rows(vocabulary_events_path()) if r.get("kind") in VOCAB_KINDS]


def fold_vocabulary(events: "list[dict]") -> dict:
    """The events folded in order: declare adds a word (at the end, if it
    was not there), undeclare removes it; pin adds a shelf entry by its
    id, unpin removes it. Nothing is ever edited in place."""
    words: "list[str]" = []
    pinned: "list[dict]" = []
    for e in events:
        k, term = e.get("kind"), _clean_term(e.get("term"))
        if k == "declare" and term and term.lower() not in {w.lower() for w in words}:
            words.append(term)
        elif k == "undeclare" and term:
            words = [w for w in words if w.lower() != term.lower()]
        elif k == "pin" and e.get("concept_id"):
            if not any(p["concept_id"] == e["concept_id"] for p in pinned):
                pinned.append({"concept_id": str(e["concept_id"]), "term": term})
        elif k == "unpin" and e.get("concept_id"):
            pinned = [p for p in pinned if p["concept_id"] != e["concept_id"]]
    return {"words": words[:200], "pinned": pinned[:200]}


def _legacy_projection_words() -> "list[str]":
    """Block 106 kept the declared words as a file rewritten in place.
    Read for compatibility only until the first event migrates them."""
    p = vocabulary_path()
    if not p.exists():
        return []
    try:
        rows = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(rows, dict) and rows.get("events") is not None:
            return []          # already a projection of the events
        return [_clean_term(w) for w in (rows.get("words") if isinstance(rows, dict) else rows) if _clean_term(w)]
    except Exception:  # noqa: BLE001
        return []


def vocabulary_state() -> dict:
    events = load_vocabulary_events()
    if not events and not vocabulary_events_path().exists():
        return {"words": _legacy_projection_words(), "pinned": [], "events": 0, "migrated": False}
    st = fold_vocabulary(events)
    st["events"] = len(events)
    return st


def load_declared_vocabulary() -> "list[str]":
    """Words the owner declared the engine must hear right — his coinages
    that are not on the shelf, the clinical acronyms of his work."""
    return vocabulary_state()["words"]


def load_pinned_vocabulary() -> "list[dict]":
    return vocabulary_state()["pinned"]


def _write_projection(state: dict) -> None:
    cli.LOCAL_STATE.mkdir(exist_ok=True)
    vocabulary_path().write_text(json.dumps({"words": state["words"], "pinned": state["pinned"], "events": state.get("events", 0),
                                             "rebuilt_at": cli._now(), "note": "a projection of speech_vocabulary_events.jsonl — the events are the record"},
                                            ensure_ascii=False, indent=1), encoding="utf-8")


def _vocab_event(kind: str, term: str, by: str, concept_id: str = "", note: str = "") -> dict:
    row = {"id": "spv_" + hashlib.sha256(f"{kind}|{term}|{concept_id}|{cli._now()}|{os.urandom(4).hex()}".encode()).hexdigest()[:12],
           "at": cli._now(), "by": by, "kind": kind, "term": term}
    if concept_id:
        row["concept_id"] = concept_id
    if note:
        row["note"] = note
    _append_row(vocabulary_events_path(), row)
    return row


def _migrate_legacy_words(by: str) -> "list[dict]":
    if vocabulary_events_path().exists():
        return []
    rows = []
    for w in _legacy_projection_words():
        rows.append(_vocab_event("declare", w, by, note="migrated from the block-106 setting file"))
    return rows


def set_declared_vocabulary(words: "list[str]", by: str = "owner") -> dict:
    """The owner's declared words, as a difference: a word new to the list
    is a declare event, a word gone from it an undeclare event. The log is
    appended, the projection rebuilt; nothing is rewritten."""
    clean, seen = [], set()
    for w in words:
        w = _clean_term(w)
        if w and w.lower() not in seen:
            seen.add(w.lower()); clean.append(w)
    clean = clean[:200]
    appended = _migrate_legacy_words(by)
    current = vocabulary_state()["words"]
    cur_l = {w.lower() for w in current}
    for w in clean:
        if w.lower() not in cur_l:
            appended.append(_vocab_event("declare", w, by))
    for w in current:
        if w.lower() not in seen:
            appended.append(_vocab_event("undeclare", w, by))
    state = vocabulary_state()
    _write_projection(state)
    return {"words": state["words"], "count": len(state["words"]), "events_appended": [r["id"] for r in appended]}


def shelf_entries() -> "list[dict]":
    """The shelf's accepted titles with the id each is kept under — the
    concept id where one exists, the entry's own id for a legacy row."""
    out, seen = [], set()
    try:
        rows = cli.load_accepted_concepts()
    except Exception:  # noqa: BLE001 — a hint is a convenience, never a gate
        return []
    for c in rows:
        name = _clean_term(c.get("name"))
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append({"term": name, "id": str(c.get("concept_id") or c.get("id") or ("title:" + name.lower()))})
    return out


def set_pinned_vocabulary(titles: "list[str]", by: str = "owner") -> dict:
    """Shelf titles the owner pins into the engine's ear, by exact title,
    kept by the entry's id. A title not on the shelf is refused by name,
    never guessed at."""
    shelf = shelf_entries()
    by_title = {e["term"].lower(): e for e in shelf}
    by_id = {e["id"]: e for e in shelf}
    wanted, unknown, seen = [], [], set()
    for t in titles:
        t = _clean_term(t)
        if not t:
            continue
        e = by_title.get(t.lower()) or by_id.get(t)
        if not e:
            unknown.append(t)
        elif e["id"] not in seen:
            seen.add(e["id"]); wanted.append(e)
    appended = _migrate_legacy_words(by)
    current = vocabulary_state()["pinned"]
    cur_ids = {p["concept_id"] for p in current}
    for e in wanted:
        if e["id"] not in cur_ids:
            appended.append(_vocab_event("pin", e["term"], by, concept_id=e["id"]))
    for p in current:
        if p["concept_id"] not in seen:
            appended.append(_vocab_event("unpin", p["term"], by, concept_id=p["concept_id"]))
    state = vocabulary_state()
    _write_projection(state)
    return {"pinned": state["pinned"], "count": len(state["pinned"]), "unknown": unknown, "events_appended": [r["id"] for r in appended]}


# ---- what is open now: names from the record, by id, never from the request ----

def context_terms(context: "dict | None") -> "list[dict]":
    """The names of what the owner has open — a concept, a Room, a
    document, a work, an attached artifact — resolved from the record by
    the ids the page sends. A name never comes from the request itself:
    an id that is not in the record yields nothing."""
    out = []
    if not isinstance(context, dict):
        return out

    def _ok(v) -> str:
        v = str(v or "").strip()
        return v if _ID_RE.match(v) else ""

    cid = _ok(context.get("concept"))
    if cid:
        for e in shelf_entries():
            if e["id"] == cid:
                out.append({"term": e["term"], "source": f"context:concept:{cid}"})
                break
    rid = _ok(context.get("room"))
    if rid:
        try:
            import clinic
            room = (clinic.load_rooms() or {}).get(rid) or {}
            t = _clean_term(room.get("subject") or room.get("title") or room.get("name"))
            if t:
                out.append({"term": t, "source": f"context:room:{rid}"})
        except Exception:  # noqa: BLE001
            pass
    mid = _ok(context.get("media"))
    if mid:
        try:
            import library
            m = (library.load_media() or {}).get(mid) or {}
            t = _clean_term(m.get("title"))
            if t:
                out.append({"term": t, "source": f"context:media:{mid}"})
        except Exception:  # noqa: BLE001
            pass
    wid = _ok(context.get("work"))
    if wid:
        try:
            import library
            w = (library.load_works() or {}).get(wid) or {}
            t = _clean_term(w.get("canonical_title") or w.get("title"))
            if t:
                out.append({"term": t, "source": f"context:work:{wid}"})
        except Exception:  # noqa: BLE001
            pass
    aid = _ok(context.get("artifact"))
    if aid:
        try:
            a = cli.load_artifact(aid) or {}
            t = _clean_term(a.get("title") or a.get("filename") or a.get("name"))
            if t:
                out.append({"term": t, "source": f"context:artifact:{aid}"})
        except Exception:  # noqa: BLE001
            pass
    return out


# ---- the fallback order: deterministic, and not newness ------------------------

def token_counter():
    """A counter of the engine's own tokens for a term, from the model's
    tokenizer in the cache — loaded once, never the model itself. None
    when there is no model on this machine (the mock, the absent engine):
    the fallback is then alphabetical, and the manifest says which."""
    model = getattr(ENGINE, "model_name", None) if ENGINE is not None and ENGINE.name != "mock" else None
    if not model:
        return None
    if model in _TOKENIZER:
        return _TOKENIZER[model]
    fn = None
    try:
        snap = model_snapshot(model)
        tok_file = snap / "tokenizer.json" if snap else None
        if tok_file and tok_file.exists():
            from tokenizers import Tokenizer
            tok = Tokenizer.from_file(str(tok_file))
            fn = lambda text: len(tok.encode(text, add_special_tokens=False).ids)  # noqa: E731
    except Exception:  # noqa: BLE001
        fn = None
    _TOKENIZER[model] = fn
    return fn


def rarity(term: str, count) -> float:
    """Tokens per letter under the engine's tokenizer: a word the engine
    knows well is one piece, a coinage or an acronym is many. Higher is
    rarer — and rarer is what the hint is for."""
    letters = max(1, len(term.replace(" ", "")))
    try:
        return round(float(count(term)) / letters, 4)
    except Exception:  # noqa: BLE001
        return 0.0


def shelf_fallback_order(entries: "list[dict]", count=None) -> "tuple[list[dict], str]":
    """The shelf in the order the fallback takes it, and the rule's name.
    With the engine's tokenizer: rarest first, ties alphabetical. Without
    one: alphabetical. Never newest first — newness says nothing about
    how a word is heard (the reviewer's ruling, block 106b)."""
    if count is not None:
        ordered = sorted(entries, key=lambda e: (-rarity(e["term"], count), e["term"].lower()))
        return ordered, "tokenizer_rarity"
    return sorted(entries, key=lambda e: e["term"].lower()), "alphabetical"


# ---- the hint and its manifest --------------------------------------------------

def vocabulary_hint(shelf: "list", declared: "list[str] | None" = None, brand: "list[str] | None" = None,
                    context: "list[dict] | None" = None, pinned: "list[dict] | None" = None,
                    token_count=None, cap: int = VOCAB_CHAR_CAP, model: "dict | None" = None,
                    token_cap: int = VOCAB_TOKEN_CAP, term_ceiling: int = TERM_TOKEN_CEILING) -> dict:
    """The transcription hint and its manifest. Tiers in order of standing
    (block 106b): the visible name and the owner's declared words; the
    names of what is open; the owner's pinned shelf titles; then the
    shelf as space remains, in a deterministic order that is not newness.
    Framed as a sentence so the engine copies the words and not their
    capitalization.

    The cap is in the engine's own tokens when its tokenizer is here to
    count them, because Whisper keeps only the LAST 223 tokens of the
    prompt: a hint over that loses its front — the name and the owner's
    words, the highest-standing tier — while looking whole. The real
    shelf exposed this: 715 characters of rare coinages were 251 tokens,
    and "Nikodemus" fell off the front. In characters only when nothing
    can count tokens (the mock, no model). A shelf title over the
    per-term ceiling (a gloss, a foreign script) is left out of the
    fallback and listed; the owner's own tiers are never dropped for
    cost, only for the cap.

    The manifest lists every term with its tier and its source id, what
    was dropped and why, the rule, the caps and the measured tokens, and
    the model whose tokenizer ordered and measured; it is content-
    addressed by its own sha256 — the transcript cites that, and a record
    can be read back to the exact words the engine was told."""
    brand = brand_words() if brand is None else list(brand)
    declared = list(declared or [])
    context = list(context or [])
    pinned = list(pinned or [])
    shelf_rows = [e if isinstance(e, dict) else {"term": str(e), "id": "title:" + str(e).strip().lower()} for e in (shelf or [])]
    ordered_shelf, rule = shelf_fallback_order([e for e in shelf_rows if _clean_term(e.get("term"))], token_count)
    tiers = [("brand", [{"term": t, "source": "brand:config/brand.json"} for t in brand]),
             ("declared", [{"term": t, "source": "declared:owner"} for t in declared]),
             ("context", [{"term": c.get("term", ""), "source": c.get("source", "context:unknown")} for c in context]),
             ("pinned", [{"term": p.get("term", ""), "source": f"pinned:{p.get('concept_id', '')}"} for p in pinned]),
             ("shelf", [{"term": e["term"], "source": f"shelf:{e.get('id', '')}"} for e in ordered_shelf])]

    def _tokens(text: str) -> "int | None":
        if token_count is None:
            return None
        try:
            return int(token_count(text))
        except Exception:  # noqa: BLE001
            return None

    def _render(terms: "list[str]") -> str:
        return (HINT_FRAME + ", ".join(terms) + ".") if terms else ""

    seen, kept, dropped, used = set(), [], [], 0
    counts = {k: 0 for k in HINT_TIERS}
    tokens_now = _tokens(_render([])) or 0
    for tier, rows in tiers:
        for r in rows:
            t = _clean_term(r["term"])
            if not t or t.lower() in seen:
                continue
            drop = ""
            if used + len(t) + 2 > cap:
                drop = "cap"
            elif token_count is not None:
                cost = _tokens(t)
                if tier == "shelf" and cost is not None and cost > term_ceiling:
                    drop = "term ceiling"
                else:
                    trial = _tokens(_render([k["term"] for k in kept] + [t]))
                    if trial is not None and trial > token_cap:
                        drop = "cap"
                    else:
                        tokens_now = trial if trial is not None else tokens_now
            if drop:
                if len(dropped) < 50:
                    dropped.append({"term": t, "tier": tier, "source": r["source"], "reason": drop})
                continue
            seen.add(t.lower()); used += len(t) + 2
            kept.append({"term": t, "tier": tier, "source": r["source"]})
            counts[tier] += 1
    hint = _render([k["term"] for k in kept])
    body = {"kind": "speech_hint", "rev": HINT_REV, "frame": HINT_FRAME, "cap": cap, "token_cap": token_cap, "term_token_ceiling": term_ceiling,
            "tokens": (_tokens(hint) if kept else 0) if token_count is not None else None, "fallback_rule": rule,
            "model": {"name": (model or {}).get("name", ""), "sha": (model or {}).get("sha", "")},
            "terms": kept, "dropped": dropped, "hint": hint, "count": len(kept), **counts,
            "sha": hashlib.sha256(hint.encode("utf-8")).hexdigest()[:16] if kept else ""}
    body["manifest_sha"] = hashlib.sha256(_canonical(body)).hexdigest()
    return body


def manifest_verifies(manifest) -> bool:
    """Content-addressed: the manifest's name is its own hash."""
    if not isinstance(manifest, dict) or not isinstance(manifest.get("manifest_sha"), str):
        return False
    body = {k: v for k, v in manifest.items() if k != "manifest_sha"}
    return hashlib.sha256(_canonical(body)).hexdigest() == manifest["manifest_sha"]


def remember_hint(manifest: dict) -> None:
    sha = manifest.get("manifest_sha")
    if not sha:
        return
    HINT_CACHE[sha] = manifest
    HINT_CACHE.move_to_end(sha)
    while len(HINT_CACHE) > HINT_CACHE_SIZE:
        HINT_CACHE.popitem(last=False)


def hint_manifest_path(sha: str) -> "pathlib.Path | None":
    if not isinstance(sha, str) or not re.match(r"^[0-9a-f]{64}$", sha):
        return None
    return hints_dir() / f"{sha}.json"


def load_hint_manifest(sha: str) -> "dict | None":
    p = hint_manifest_path(sha)
    if not p or not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def persist_hint_manifest(speech) -> str:
    """At Send or Keep — the moment the transcript enters the record — the
    manifest it cites is written, content-addressed, once. The server's
    own copy from the transcription is preferred; the page's copy is
    taken only when it hashes to the sha it claims. Returns the sha the
    record may cite, or "" when nothing verifiable was offered — a row
    never cites a manifest that is not on disk."""
    if not isinstance(speech, dict):
        return ""
    sha = speech.get("hint_manifest")
    if not isinstance(sha, str) or not hint_manifest_path(sha):
        return ""
    manifest = HINT_CACHE.get(sha)
    if manifest is None:
        offered = speech.get("hint")
        if isinstance(offered, dict) and offered.get("manifest_sha") == sha and manifest_verifies(offered):
            manifest = offered
    if manifest is None:
        return sha if load_hint_manifest(sha) else ""
    p = hint_manifest_path(sha)
    if not p.exists():
        hints_dir().mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return sha


def current_hint(context: "dict | None" = None) -> dict:
    model = getattr(ENGINE, "model_name", DEFAULT_MODEL) if ENGINE is not None else DEFAULT_MODEL
    mock = ENGINE is not None and ENGINE.name == "mock"
    return vocabulary_hint(shelf_entries(), declared=load_declared_vocabulary(), context=context_terms(context),
                           pinned=load_pinned_vocabulary(), token_count=token_counter(),
                           model={"name": "mock" if mock else model, "sha": "" if mock else model_fingerprint(model)})


def to_vtt(segments: "list[dict]") -> str:
    def ts(s: float) -> str:
        s = max(0.0, float(s or 0.0))
        h, rem = divmod(s, 3600); m, sec = divmod(rem, 60)
        return f"{int(h):02d}:{int(m):02d}:{sec:06.3f}"
    lines = ["WEBVTT", ""]
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        lines += [f"{ts(seg.get('start', 0))} --> {ts(seg.get('end', 0))}", text, ""]
    return "\n".join(lines)


# ---- engines ---------------------------------------------------------------------

class Engine:
    name = "none"
    version = ""
    external = False

    def transcribe(self, audio: bytes, mime: str, hint: dict) -> dict:
        raise NotImplementedError


class MockEngine(Engine):
    """Deterministic and offline, for the suite and the journeys. Says a
    fixed sentence unless the bytes carry a test marker naming one. Never
    installed by the server."""
    name = "mock"
    version = "mock-1"
    DEFAULT_TEXT = "I would like to know about the historical superstitions involving cats."

    def transcribe(self, audio: bytes, mime: str, hint: dict) -> dict:
        text = self.DEFAULT_TEXT
        marker = b"NIKODEMUS-TEST:"
        if marker in audio:
            text = audio.split(marker, 1)[1].split(b"\n", 1)[0].decode("utf-8", "replace").strip() or text
        dur = round(max(0.5, len(audio) / 32000.0), 2)
        return {"text": text, "segments": [{"start": 0.0, "end": dur, "text": text}], "duration_s": dur,
                "model": "mock", "model_sha": "", "compute_type": "none"}


class FasterWhisperEngine(Engine):
    name = ENGINE_NAME

    def __init__(self, model: str = DEFAULT_MODEL, compute_type: str = COMPUTE_TYPE):
        import faster_whisper  # noqa: F401 — the import is the availability check
        self.version = _engine_version()
        self.model_name = model if model in MODEL_REPOS else DEFAULT_MODEL
        self.compute_type = compute_type
        self._model = None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            # local_files_only: the model is fetched only by fetch_model(), never here
            self._model = WhisperModel(self.model_name, device="cpu", compute_type=self.compute_type, local_files_only=True)
        return self._model

    def transcribe(self, audio: bytes, mime: str, hint: dict) -> dict:
        from faster_whisper import decode_audio
        arr = decode_audio(io.BytesIO(audio))           # from memory: nothing touches the disk
        model = self._load()
        kw = {"beam_size": 5, "language": "en"}
        if hint.get("hint"):
            kw["initial_prompt"] = hint["hint"]
        segs, info = model.transcribe(arr, **kw)
        segments = [{"start": round(float(s.start), 3), "end": round(float(s.end), 3), "text": s.text.strip()} for s in segs]
        text = " ".join(s["text"] for s in segments if s["text"])
        return {"text": text, "segments": segments, "duration_s": round(float(getattr(info, "duration", 0.0) or len(arr) / 16000.0), 2),
                "model": self.model_name, "model_sha": model_fingerprint(self.model_name), "compute_type": self.compute_type}


def _engine_version() -> str:
    try:
        import importlib.metadata as md
        return md.version("faster-whisper")
    except Exception:  # noqa: BLE001
        return "unknown"


def engine_installed() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


# ---- the model: a replaceable cache outside the record, and a record of it -------

def cache_dir() -> pathlib.Path:
    home = os.environ.get("HF_HOME")
    return pathlib.Path(home) / "hub" if home else pathlib.Path.home() / ".cache" / "huggingface" / "hub"


def model_snapshot(model: str = DEFAULT_MODEL) -> "pathlib.Path | None":
    repo = MODEL_REPOS.get(model)
    if not repo:
        return None
    base = cache_dir() / ("models--" + repo.replace("/", "--")) / "snapshots"
    if not base.exists():
        return None
    snaps = [p for p in base.iterdir() if p.is_dir() and (p / "model.bin").exists()]
    return sorted(snaps, key=lambda p: p.stat().st_mtime)[-1] if snaps else None


def model_files(snap: pathlib.Path) -> "list[dict]":
    out = []
    for p in sorted(x for x in snap.rglob("*") if x.is_file()):
        out.append({"name": p.name, "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    return out


def model_fingerprint(model: str = DEFAULT_MODEL) -> str:
    """sha256 over the snapshot's files (name, then bytes), the spike's
    recipe — computed once per process."""
    if model in _MODEL_CACHE:
        return _MODEL_CACHE[model]
    snap = model_snapshot(model)
    if not snap:
        return ""
    h = hashlib.sha256()
    for p in sorted(x for x in snap.rglob("*") if x.is_file()):
        h.update(p.name.encode()); h.update(p.read_bytes())
    _MODEL_CACHE[model] = h.hexdigest()[:16]
    return _MODEL_CACHE[model]


def model_bytes(model: str = DEFAULT_MODEL) -> int:
    snap = model_snapshot(model)
    return sum(p.stat().st_size for p in snap.rglob("*") if p.is_file()) if snap else 0


def model_revision(snap: "pathlib.Path | None") -> str:
    """The hub's commit for the snapshot — the cache keeps each snapshot
    under its revision's name."""
    return snap.name if snap else ""


def model_license(snap: "pathlib.Path | None") -> dict:
    """The license as the model card states it (README.md front matter,
    fetched with the snapshot), or an honest 'unstated in the cache'."""
    if snap and (snap / "README.md").exists():
        try:
            head = (snap / "README.md").read_text(encoding="utf-8", errors="replace")[:4000]
            m = re.search(r"^license:\s*['\"]?([A-Za-z0-9._+-]+)", head, re.M)
            if m:
                return {"license": m.group(1), "license_from": "README.md front matter in the snapshot"}
        except OSError:
            pass
    return {"license": "unstated in the cache", "license_from": "no model card in the snapshot — see the source"}


def model_identity(model: str = DEFAULT_MODEL) -> dict:
    snap = model_snapshot(model)
    repo = MODEL_REPOS.get(model, "")
    if not snap:
        return {"model": model, "repo": repo, "source": MODEL_SOURCE + repo if repo else "", "present": False}
    return {"model": model, "repo": repo, "source": MODEL_SOURCE + repo, "present": True, "revision": model_revision(snap),
            "sha": model_fingerprint(model), "bytes": model_bytes(model), **model_license(snap)}


def model_records(model: str = DEFAULT_MODEL) -> "list[dict]":
    return [r for r in _read_rows(model_records_path()) if r.get("model") == model]


def model_record(model: str = DEFAULT_MODEL) -> "dict | None":
    """The latest record of the model now in the cache — matched by its
    file hash, so a replaced cache is seen as unrecorded."""
    sha = model_fingerprint(model)
    if not sha:
        return None
    rows = [r for r in model_records(model) if r.get("sha") == sha]
    return rows[-1] if rows else None


def record_model(kind: str, model: str = DEFAULT_MODEL, by: str = "owner", seconds: "float | None" = None) -> dict:
    """The record of the model on this machine: its source, revision,
    every file's size and hash, the composite hash the transcripts cite,
    and its license — written when the owner fetches it (kind fetched) or
    has an already-cached model recorded (kind observed)."""
    snap = model_snapshot(model)
    if not snap:
        raise RuntimeError("the model is not on this machine")
    ident = model_identity(model)
    row = {"id": "spm_" + hashlib.sha256(f"{model}|{ident['sha']}|{cli._now()}".encode()).hexdigest()[:12],
           "at": cli._now(), "by": by, "kind": kind, "model": model, "repo": ident["repo"], "source": ident["source"],
           "revision": ident["revision"], "sha": ident["sha"], "bytes": ident["bytes"], "files": model_files(snap),
           "license": ident["license"], "license_from": ident["license_from"], "cache": str(snap),
           "engine": ENGINE_NAME, "engine_version": _engine_version()}
    if seconds is not None:
        row["seconds"] = seconds
    _append_row(model_records_path(), row)
    return row


def status() -> dict:
    """What the doorway can say about itself without touching the
    network: the engine, whether it is installed, the model and whether
    it is present, its size, hash, revision, source and license when it
    is, whether its record exists, the ear's composition, and that
    nothing leaves this machine."""
    eng = ENGINE
    installed = engine_installed()
    model = getattr(eng, "model_name", DEFAULT_MODEL) if eng is not None else DEFAULT_MODEL
    present = model_snapshot(model) is not None
    ident = model_identity(model) if present else {}
    rec = model_record(model) if present else None
    hint = current_hint()
    vocab = vocabulary_state()
    return {"engine": getattr(eng, "name", ENGINE_NAME if installed else "none"),
            "engine_version": getattr(eng, "version", _engine_version() if installed else ""),
            "installed": installed or (eng is not None and eng.name == "mock"),
            "mock": bool(eng is not None and eng.name == "mock"),
            "model": model, "model_present": present or bool(eng is not None and eng.name == "mock"),
            "model_bytes": model_bytes(model) if present else 0, "model_sha": model_fingerprint(model) if present else "",
            "model_revision": ident.get("revision", ""), "model_license": ident.get("license", ""),
            "model_source": ident.get("source", MODEL_SOURCE + MODEL_REPOS.get(model, "")),
            "model_record": (rec or {}).get("id", ""), "model_recorded_at": (rec or {}).get("at", ""),
            "compute_type": getattr(eng, "compute_type", COMPUTE_TYPE), "external": False,
            "cache_dir": str(cache_dir()), "max_audio_bytes": MAX_AUDIO_BYTES,
            "vocabulary": {k: v for k, v in hint.items() if k not in ("hint", "terms")},
            "declared_vocabulary": vocab["words"], "pinned_vocabulary": vocab["pinned"], "vocabulary_events": vocab.get("events", 0),
            "install_hint": "pip install -r requirements-speech.txt (faster-whisper, MIT)" if not installed else ""}


def fetch_model(model: str = DEFAULT_MODEL) -> dict:
    """The one network act on this path — the owner's visible click.
    Downloads the model's snapshot (its card included, so the license is
    on disk beside the weights) into the cache and records what arrived:
    source, revision, file hashes, license. A model already in the cache
    is not fetched again — it is recorded as observed, with no network.
    Never called by transcribe()."""
    repo = MODEL_REPOS.get(model)
    if not repo:
        raise ValueError("unknown model")
    if model_snapshot(model) is not None:
        rec = model_record(model) or record_model("observed", model)
        return {"model": model, "fetched": False, "recorded": rec["id"], "path": str(model_snapshot(model)), "bytes": model_bytes(model),
                "sha": model_fingerprint(model), "revision": rec.get("revision", ""), "license": rec.get("license", ""), "source": rec.get("source", "")}
    from huggingface_hub import snapshot_download
    t0 = time.time()
    path = snapshot_download(repo_id=repo)
    _MODEL_CACHE.pop(model, None)
    _TOKENIZER.pop(model, None)
    rec = record_model("fetched", model, seconds=round(time.time() - t0, 1))
    return {"model": model, "fetched": True, "recorded": rec["id"], "path": str(path), "bytes": model_bytes(model),
            "sha": model_fingerprint(model), "revision": rec["revision"], "license": rec["license"], "source": rec["source"],
            "seconds": round(time.time() - t0, 1)}


# ---- the doorway ---------------------------------------------------------------------

BODY_TIMEOUT_S = 30                   # a 25 MB body on a home LAN arrives in seconds; a stalled one is dropped
BODY_CHUNK = 65536


class BodyTooLarge(ValueError):
    pass


class BodyTimeout(TimeoutError):
    pass


class BodyShort(ValueError):
    pass


def read_bounded(stream, declared: int, cap: int = MAX_AUDIO_BYTES, timeout_s: float = BODY_TIMEOUT_S) -> bytes:
    """A request body into memory — only as far as the cap allows and only
    as long as the deadline lasts (block 106b). 'Does not spool to disk'
    must not become 'will absorb unlimited RAM': the declared length is
    refused above the cap before a byte is read, the read stops at the
    cap plus one whatever the header claimed, and a body that trickles
    past the deadline is dropped. A body shorter than declared is refused
    too — nothing half-arrived is transcribed."""
    if declared > cap:
        raise BodyTooLarge(f"declared {declared} bytes, cap {cap}")
    buf = bytearray()
    deadline = time.monotonic() + timeout_s
    while True:
        chunk = stream.read(min(BODY_CHUNK, cap + 1 - len(buf)))
        if not chunk:
            break
        buf += chunk
        if len(buf) > cap:
            raise BodyTooLarge(f"more than {cap} bytes arrived")
        if time.monotonic() > deadline:
            raise BodyTimeout(f"the body did not arrive within {timeout_s} s")
    if len(buf) != declared:
        raise BodyShort(f"declared {declared} bytes, {len(buf)} arrived")
    return bytes(buf)


def transcribe_bytes(audio: bytes, mime: str, context: "dict | None" = None) -> dict:
    """Bytes in, a transcript with the engine's identity out — and the
    manifest of what the engine was told. Refuses what it cannot honestly
    take: no engine, a model not yet fetched, a body over the cap, a type
    that is not audio. Writes nothing."""
    if ENGINE is None:
        raise RuntimeError("the transcription engine is not installed on this machine — " + status()["install_hint"])
    if not audio:
        raise ValueError("no audio arrived")
    if len(audio) > MAX_AUDIO_BYTES:
        raise ValueError(f"the recording is over the cap ({MAX_AUDIO_BYTES} bytes)")
    base_mime = (mime or "").split(";", 1)[0].strip().lower()
    if base_mime not in ACCEPTED_MIMES:
        raise ValueError("the body must be audio (webm/opus, mp4/aac, ogg, wav, mpeg)")
    if ENGINE.name != "mock" and model_snapshot(getattr(ENGINE, "model_name", DEFAULT_MODEL)) is None:
        raise RuntimeError("the model is not on this machine yet — fetch it once from About & proof")
    hint = current_hint(context)
    t0 = time.time()
    out = ENGINE.transcribe(audio, base_mime, hint)
    elapsed = round(time.time() - t0, 2)
    remember_hint(hint)
    return {"text": out.get("text", ""), "segments": out.get("segments") or [], "duration_s": out.get("duration_s", 0.0),
            "elapsed_s": elapsed, "mime": base_mime, "bytes": len(audio),
            "engine": {"name": ENGINE.name, "version": ENGINE.version, "model": out.get("model", ""),
                       "model_sha": out.get("model_sha", ""), "compute_type": out.get("compute_type", ""),
                       "vocabulary_count": hint["count"], "vocabulary_sha": hint["sha"],
                       "vocabulary_sources": {k: hint[k] for k in HINT_TIERS},
                       "hint_manifest": hint["manifest_sha"], "hint_rev": HINT_REV, "external": False},
            "hint": hint}
