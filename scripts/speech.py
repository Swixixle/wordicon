"""Speak to Nikodemus — the transcription adapter (block 106; backlog items
53, 55; docs/adr-speak.md).

The one boundary between a recording and words. Audio arrives as bytes
in memory and leaves as a transcript with the engine's identity on it;
nothing here opens a file for writing, spools to a temporary file,
touches the network, or consults the language model. The real engine is
faster-whisper (MIT; CTranslate2, PyAV with its decoders bundled),
running on this machine with a model fetched ONCE by a visible owner
action into a cache outside local_state. The vocabulary hint is the
owner's own accepted titles, read from the record at call time and
recorded on the transcript as a setting (count and hash), because it
biases what is heard. The mock engine is the suite's and the journeys';
production never falls back to it — an engine that is not installed is
reported as not installed."""
from __future__ import annotations

import hashlib
import io
import os
import pathlib
import time

import wordicon_cli as cli

ENGINE_NAME = "faster-whisper"
DEFAULT_MODEL = "base.en"
COMPUTE_TYPE = "int8"
MODEL_REPOS = {"tiny.en": "Systran/faster-whisper-tiny.en", "base.en": "Systran/faster-whisper-base.en",
               "small.en": "Systran/faster-whisper-small.en"}
MAX_AUDIO_BYTES = 25_000_000          # about four minutes of opus at 32 kb/s, with room
ACCEPTED_MIMES = ("audio/webm", "audio/mp4", "audio/ogg", "audio/wav", "audio/x-wav", "audio/mpeg", "audio/m4a", "audio/x-m4a")
VOCAB_CHAR_CAP = 700                  # Whisper's prompt window is 224 tokens; titles are short
ENGINE = None                         # set to an Engine by the server (real) or the suite (mock)
_MODEL_CACHE: dict = {}


HINT_FRAME = "Words in use here: "


def brand_words() -> "list[str]":
    """The visible name, from config/brand.json — never a shelf title, and
    the first thing the engine must hear right (the spike heard it as the
    Biblical spelling every time until it was told)."""
    try:
        import json as _json
        name = (_json.loads((cli.REPO_ROOT / "config" / "brand.json").read_text(encoding="utf-8")).get("name") or "").strip()
        return [name] if name else []
    except Exception:  # noqa: BLE001
        return []


def vocabulary_path() -> pathlib.Path:
    return cli.LOCAL_STATE / "speech_vocabulary.json"


def load_declared_vocabulary() -> "list[str]":
    """Words the owner declared the engine must hear right — his coinages
    that are not on the shelf, the clinical acronyms of his work. An
    owner-declared setting, written only by his own action."""
    p = vocabulary_path()
    if not p.exists():
        return []
    try:
        import json as _json
        rows = _json.loads(p.read_text(encoding="utf-8"))
        return [str(w).strip() for w in (rows.get("words") if isinstance(rows, dict) else rows) if str(w).strip()]
    except Exception:  # noqa: BLE001
        return []


def set_declared_vocabulary(words: "list[str]", by: str = "owner") -> dict:
    import json as _json
    clean, seen = [], set()
    for w in words:
        w = str(w or "").strip()[:80]
        if w and w.lower() not in seen:
            seen.add(w.lower()); clean.append(w)
    clean = clean[:200]
    cli.LOCAL_STATE.mkdir(exist_ok=True)
    vocabulary_path().write_text(_json.dumps({"words": clean, "by": by, "at": cli._now()}, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"words": clean, "count": len(clean)}


def vocabulary_hint(titles: "list[str]", declared: "list[str] | None" = None, brand: "list[str] | None" = None) -> dict:
    """The transcription hint, in order of standing: the visible name, the
    owner's declared words, then the shelf's accepted titles newest first,
    to the cap — framed as a sentence so the engine copies the words and
    not their capitalization. Recorded as count, sources and hash,
    because it biases what is heard."""
    brand = brand_words() if brand is None else list(brand)
    declared = list(declared or [])
    seen, kept, used = set(), [], 0
    n_brand = n_declared = n_shelf = 0
    for group, words in (("brand", brand), ("declared", declared), ("shelf", list(reversed([(x or "").strip() for x in titles])))):
        for t in words:
            t = (t or "").strip()
            if not t or t.lower() in seen:
                continue
            if used + len(t) + 2 > VOCAB_CHAR_CAP:
                break
            seen.add(t.lower()); kept.append(t); used += len(t) + 2
            if group == "brand":
                n_brand += 1
            elif group == "declared":
                n_declared += 1
            else:
                n_shelf += 1
    hint = (HINT_FRAME + ", ".join(kept) + ".") if kept else ""
    return {"hint": hint, "count": len(kept), "brand": n_brand, "declared": n_declared, "shelf": n_shelf,
            "sha": hashlib.sha256(hint.encode("utf-8")).hexdigest()[:16] if kept else ""}


def shelf_vocabulary() -> "list[str]":
    try:
        return [c.get("name") or "" for c in cli.load_accepted_concepts()]
    except Exception:  # noqa: BLE001 — a hint is a convenience, never a gate
        return []


def current_hint() -> dict:
    return vocabulary_hint(shelf_vocabulary(), declared=load_declared_vocabulary())


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


def status() -> dict:
    """What the doorway can say about itself without touching the
    network: the engine, whether it is installed, the model and whether
    it is present, its size and hash when it is, and that nothing leaves
    this machine."""
    eng = ENGINE
    installed = engine_installed()
    model = getattr(eng, "model_name", DEFAULT_MODEL) if eng is not None else DEFAULT_MODEL
    present = model_snapshot(model) is not None
    return {"engine": getattr(eng, "name", ENGINE_NAME if installed else "none"),
            "engine_version": getattr(eng, "version", _engine_version() if installed else ""),
            "installed": installed or (eng is not None and eng.name == "mock"),
            "mock": bool(eng is not None and eng.name == "mock"),
            "model": model, "model_present": present or bool(eng is not None and eng.name == "mock"),
            "model_bytes": model_bytes(model) if present else 0, "model_sha": model_fingerprint(model) if present else "",
            "compute_type": getattr(eng, "compute_type", COMPUTE_TYPE), "external": False,
            "cache_dir": str(cache_dir()), "max_audio_bytes": MAX_AUDIO_BYTES,
            "vocabulary": {k: v for k, v in current_hint().items() if k != "hint"},
            "declared_vocabulary": load_declared_vocabulary(),
            "install_hint": "pip install -r requirements-speech.txt (faster-whisper, MIT)" if not installed else ""}


def fetch_model(model: str = DEFAULT_MODEL) -> dict:
    """The one network act on this path — the owner's visible click.
    Downloads the model's snapshot into the cache and returns what
    arrived. Never called by transcribe()."""
    repo = MODEL_REPOS.get(model)
    if not repo:
        raise ValueError("unknown model")
    from huggingface_hub import snapshot_download
    t0 = time.time()
    path = snapshot_download(repo_id=repo)
    _MODEL_CACHE.pop(model, None)
    return {"model": model, "path": str(path), "bytes": model_bytes(model), "sha": model_fingerprint(model),
            "seconds": round(time.time() - t0, 1)}


def transcribe_bytes(audio: bytes, mime: str) -> dict:
    """Bytes in, a transcript with the engine's identity out. Refuses
    what it cannot honestly take: no engine, a model not yet fetched,
    a body over the cap, a type that is not audio."""
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
    hint = current_hint()
    t0 = time.time()
    out = ENGINE.transcribe(audio, base_mime, hint)
    elapsed = round(time.time() - t0, 2)
    return {"text": out.get("text", ""), "segments": out.get("segments") or [], "duration_s": out.get("duration_s", 0.0),
            "elapsed_s": elapsed, "mime": base_mime, "bytes": len(audio),
            "engine": {"name": ENGINE.name, "version": ENGINE.version, "model": out.get("model", ""),
                       "model_sha": out.get("model_sha", ""), "compute_type": out.get("compute_type", ""),
                       "vocabulary_count": hint["count"], "vocabulary_sha": hint["sha"],
                       "vocabulary_sources": {"brand": hint["brand"], "declared": hint["declared"], "shelf": hint["shelf"]},
                       "external": False}}
