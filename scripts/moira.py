"""Professor Moira — three readers beside the draft (block 125).

A reading faculty met through three aspects, each executed on its own and
blind to the others: one reads for what is alive, one for what can bear
weight, one for what actually reached a stranger. Moira herself is a
procedure, not a judge: she freezes one exact snapshot of the text, says what
it costs, dispatches the three calls separately, keeps the outputs separate,
checks every quoted span against the text, and records the owner's rulings
without interpreting them. No conference. No synthesized verdict. No score.

What is recorded, and where (all under local_state/moira/, all append-only or
write-once; nothing here is ever rewritten in place):
  readings/<reading_id>.json     one exact snapshot of the text plus the
                                 dispatch list — written once
  responses/<response_id>.json   one reader's answer (or its failure) —
                                 written once, never overwritten; a retry
                                 or a follow-up is a NEW response
  notebook.jsonl                 the writer's notebook: remember / correct /
                                 retire events, each with its source
  settings.jsonl                 faculty settings as the owner changed them;
                                 every response records the settings it was
                                 read under
  rulings.jsonl                  owner rulings (Phase 0 result)

The blind reading (Atropos) is isolated STRUCTURALLY: blind_request() takes
the instructions and the draft and nothing else, and the response records
the hash of exactly what was sent. The notebook, prior drafts, intent and the
sibling responses cannot reach it because no code path carries them there.
"Discuss this reading" afterwards is a separate response, labelled informed
consultation, and the blind response file stays byte-identical.

Ids are uuid4-based (never a hash of the text and the clock second — two
readings of one draft inside one second are two readings). Every file is
written with open(..., "x") so a collision refuses rather than overwrites.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wordicon_cli as cli  # noqa: E402

PROMPTS_VERSION = "moira-prompts/1"     # the expressive prompts; Phase 0's frozen prompts live outside the repo, untouched
READERS = ("clotho", "lachesis", "atropos")
READS_FOR = {"clotho": "what is alive", "lachesis": "what can bear weight",
             "atropos": "what reached a stranger"}
NOTEBOOK_READERS = ("clotho", "lachesis")   # the only readers that ever receive the notebook
ROLE_KINDS = ("reading", "followup", "consultation")
FACULTY_NAME_IF_PASSED = "Moira"
FACULTY_NAME_OTHERWISE = "Readers"

# ---------------------------------------------------------------------------
# the prompts — responsibilities first, manner second
# ---------------------------------------------------------------------------
#
# Each reader's RESPONSIBILITY is fixed by the role and does not move when the
# owner adjusts how it speaks. The manner (warmth, directness, playfulness,
# length) is rendered from the faculty settings into a short clause, and the
# whole instruction text is hashed onto every response, so a reading can
# always say exactly what it was read under. These are creative adaptations
# of the mythic roles; nothing here claims the myth specifies a psychology.

CLOTHO = """You read this once, aloud in your head, and your ear grades before your mouth does. You read for one thing: whether it is alive.

You are imaginative and attentive to rhythm and possibility, and you are protective of what a revision must not kill. You do not care whether the argument is clear or whether a stranger could rebuild it; that is someone else's ground. You are not judging whether anything here is true. You are not judging the writer, and nothing you write may be about them.

Your allergies: cliché, borrowed music, cleverness worn as armor, the flinch where a braver writer would have stayed in the wound. Your law: a glorious wreck beats a tidy corpse — but a wreck that knows it is wrecking, on purpose, beats both.

Report exactly these, and nothing else:
- the line carrying the living current;
- where sentence pressure or sound creates movement;
- where compression makes energy;
- where compression withholds a step the reader needs;
- where the voice goes generic or performs profundity;
- what must survive the next draft;
- one expansion that would preserve this writer's fingerprint rather than replace it;
- what you predict will still be in a reader's head later, marked as prediction, since you cannot measure it;
- anything you cannot hear clearly.

No scores. No verdict. Do not rewrite a line; name what it does. You may mention a writer this reaches toward at most once, and it is recall, not evidence.

Respond with ONLY this JSON, no prose outside it:
{"segments":[{"class":"current|pressure|compression_energy|compression_withholds|generic|must_survive|expansion|projected_residue|uncertain","span":"...","text":"..."}]}
Every span must be copied exactly, character for character, from the passage."""

LACHESIS = """You read one thing only: whether the argument on this page can be rebuilt by someone who does not have its author in the room.

You are measured, exacting, and dryly witty, and you are attentive to structure, to missing bridges, and to what the wording actually permits. For thirty years you have watched brilliant, charismatic people emit dazzling noise that nobody could repeat the next morning. You are completely immune to charm, voltage, momentum, and clever phrasing — they do not work on you, and you say so when they are attempted. If a line is hot but disconnected, that is heat, not wiring. An unconventional structure may be deliberate; you still ask whether it works.

You are not judging voice, music, register, beauty, or whether anything here is true. It is not your ground, and a sentence about it is a sentence you have wasted. You are not judging the writer. Nothing you write may be about them.

Report exactly these, and nothing else:
- the path you believe the piece walks, in one sentence;
- every place the path breaks, forks, or dumps its branches: quote the words on both sides of the gap and name the bridge that was assumed and never built;
- the ordinary interpretation the prose accidentally permits, quoting what permits it;
- one high-leverage structural repair, quoting where;
- what is not the structural problem and should survive untouched, quoting it;
- anything you cannot settle from the text.

No scores. No verdict. One repair, not a list. You are not cruel for sport.

Respond with ONLY this JSON, no prose outside it:
{"segments":[{"class":"path|break|permitted_reading|repair|leave_alone|uncertain","span":"...","span2":"...","text":"..."}]}
Every span must be copied exactly, character for character, from the passage. "path" carries no span. "break" uses span and span2 for the two sides of the gap. Omit span2 otherwise."""

ATROPOS = """You are reading a passage once, the way a stranger reads something handed to them with no introduction.

You know nothing about who wrote it, why, what it belongs to, or what it was meant to do. Nothing more exists for you, you will not be given more, and you may not ask.

You are spare, direct, and unsentimental. You report what arrived; you do not help the passage pretend something arrived that did not.

Do not evaluate the writing. Do not say whether it is good, clear, effective, or well made. Do not repair it and do not suggest improvements. Do not guess what the author intended — you have no access to intention, and a guess about it is outside what you were given.

Report only what happened as you read:
- what you believe the piece says;
- which single idea you believe governs it;
- what movement you experienced, if any;
- where you lost certainty;
- where you filled a gap with something familiar — a story you already know, a genre, a stock image, a common argument — and the exact words that made you reach for it;
- what cannot be recovered from this text alone.

The place where you substituted something familiar is the most useful thing you can report. Quote the words exactly. If you are uncertain, say so; uncertainty is a result, not a failure.

Respond with ONLY this JSON, no prose outside it:
{"segments":[{"class":"received|governing_idea|movement|lost_certainty|substituted|unrecoverable|uncertain","span":"...","text":"..."}]}
Every span must be copied exactly, character for character, from the passage. "received", "governing_idea", "movement" and "unrecoverable" carry no span."""

CONSULT = """Earlier you read a passage blind — knowing nothing about who wrote it or why — and reported what reached you. That blind report is below, unchanged, and it stands: nothing you say now revises it.

The writer now wants to discuss that reading with you. This is an informed consultation: the writer may share context, and you may use what they share. You remain spare, direct, and unsentimental. Report what you actually experienced then, what the shared context changes and what it does not, and where your first reading would still hold for a stranger who had none of this context. Do not repair the passage and do not evaluate whether it is good. Answer the writer's question in plain prose."""

FOLLOWUP = """The writer has a question about your reading. Your responsibility has not changed: stay on your own ground, quote the passage exactly when you point at it, and answer the question in plain prose. Do not rewrite the passage."""

ROLE_TEXT = {"clotho": CLOTHO, "lachesis": LACHESIS, "atropos": ATROPOS}

CLASS_WORDS = {
    "current": "the living current", "pressure": "pressure makes movement",
    "compression_energy": "compression makes energy", "compression_withholds": "compression withholds a step",
    "generic": "goes generic", "must_survive": "must survive the next draft", "expansion": "one expansion",
    "projected_residue": "predicted residue", "uncertain": "cannot settle this",
    "path": "the path", "break": "the path breaks here", "permitted_reading": "an ordinary reading it permits",
    "repair": "one structural repair", "leave_alone": "leave this alone",
    "received": "what arrived", "governing_idea": "the governing idea", "movement": "the movement",
    "lost_certainty": "lost certainty here", "substituted": "substituted something familiar",
    "unrecoverable": "cannot be recovered from the text",
}

# ---- expression: the manner, rendered from the settings ----
LEVELS = (0, 1, 2, 3)
LENGTHS = ("short", "medium", "long")
DEFAULT_SETTINGS = {
    "clotho":   {"warmth": 2, "directness": 1, "playfulness": 2, "length": "medium"},
    "lachesis": {"warmth": 1, "directness": 3, "playfulness": 1, "length": "medium"},
    "atropos":  {"warmth": 0, "directness": 3, "playfulness": 0, "length": "short"},
}
WARMTH = ("Keep the manner cool and impersonal.", "Be civil; no reassurance.",
          "Be warm toward the work without softening what you report.",
          "Be openly on the writer's side, which is why you say the hard thing plainly.")
DIRECTNESS = ("Approach conclusions obliquely; let the quoted words carry the point.",
              "State findings plainly once each.",
              "State findings plainly and without cushioning.",
              "Be blunt: lead every observation with the finding, then the evidence.")
PLAYFULNESS = ("No wit. Plain statements only.", "A dry aside is allowed, rarely.",
               "Wit is welcome where it sharpens a point.",
               "Be playful and imaginative in how you phrase things, never in what you report.")
LENGTH = {"short": "Keep each observation to one or two sentences.",
          "medium": "Two to four sentences per observation.",
          "long": "Develop each observation fully, up to a short paragraph."}


def _level(v, default) -> int:
    try:
        v = int(v)
    except (TypeError, ValueError):
        return default
    return v if v in LEVELS else default


def normalize_settings(raw: dict | None) -> dict:
    """The settings, whole and bounded: one block per reader, unknown values
    replaced by the defaults, nothing else kept."""
    out = {}
    raw = raw if isinstance(raw, dict) else {}
    for r in READERS:
        d = DEFAULT_SETTINGS[r]
        s = raw.get(r) if isinstance(raw.get(r), dict) else {}
        out[r] = {"warmth": _level(s.get("warmth"), d["warmth"]),
                  "directness": _level(s.get("directness"), d["directness"]),
                  "playfulness": _level(s.get("playfulness"), d["playfulness"]),
                  "length": s.get("length") if s.get("length") in LENGTHS else d["length"]}
    return out


def manner_clause(s: dict) -> str:
    return ("Manner: " + WARMTH[s["warmth"]] + " " + DIRECTNESS[s["directness"]] + " "
            + PLAYFULNESS[s["playfulness"]] + " " + LENGTH[s["length"]])


def instructions_for(reader: str, settings: dict) -> str:
    """The full instruction text for one reader under these settings — the
    role's responsibility, then its manner. Hashed onto every response."""
    if reader not in READERS:
        raise ValueError(f"unknown reader {reader!r}")
    s = normalize_settings(settings)[reader]
    return ROLE_TEXT[reader] + "\n\n" + manner_clause(s)


def sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# the store
# ---------------------------------------------------------------------------

def store_dir() -> Path:
    return Path(cli.LOCAL_STATE) / "moira"


def readings_dir() -> Path:
    return store_dir() / "readings"


def responses_dir() -> Path:
    return store_dir() / "responses"


def notebook_log() -> Path:
    return store_dir() / "notebook.jsonl"


def settings_log() -> Path:
    return store_dir() / "settings.jsonl"


def rulings_log() -> Path:
    return store_dir() / "rulings.jsonl"


def _ensure_dirs() -> None:
    readings_dir().mkdir(parents=True, exist_ok=True)
    responses_dir().mkdir(parents=True, exist_ok=True)


def _write_once(path: Path, row: dict) -> None:
    """Never overwrite: a second writer for the same id is refused."""
    _ensure_dirs()
    with open(path, "x", encoding="utf-8") as f:
        f.write(json.dumps(row, indent=2, ensure_ascii=False))


def _append(path: Path, row: dict) -> dict:
    _ensure_dirs()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _read(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _safe_id(s: str) -> str:
    return s if re.fullmatch(r"[A-Za-z0-9_]{1,40}", s or "") else ""


def load_reading(reading_id: str) -> dict | None:
    rid = _safe_id(reading_id)
    return _read(readings_dir() / f"{rid}.json") if rid else None


def load_response(response_id: str) -> dict | None:
    rid = _safe_id(response_id)
    return _read(responses_dir() / f"{rid}.json") if rid else None


# ---------------------------------------------------------------------------
# settings and rulings
# ---------------------------------------------------------------------------

def current_settings() -> dict:
    rows = _rows(settings_log())
    return normalize_settings(rows[-1].get("settings") if rows else None)


def record_settings(settings: dict, note: str = "") -> dict:
    """The owner changed how the faculty speaks. Kept as a row, never as an
    overwrite; the current settings are the last row."""
    row = {"kind": "settings", "at": cli._now(), "epoch": cli.current_epoch(),
           "settings": normalize_settings(settings), "note": (note or "")[:300]}
    _append(settings_log(), row)
    return row["settings"]


def record_phase0(result: str, note: str = "", by: str = "owner") -> dict:
    """The owner records the Phase 0 outcome. PASS names the faculty Moira
    and keeps three readers; FAIL keeps the precommitment: two readers, the
    name stays out of the interface."""
    result = (result or "").strip().upper()
    if result not in ("PASS", "FAIL"):
        raise ValueError("the Phase 0 result is PASS or FAIL, recorded as ruled")
    row = {"kind": "phase0", "at": cli._now(), "epoch": cli.current_epoch(),
           "result": result, "note": (note or "")[:600], "by": by}
    return _append(rulings_log(), row)


def phase0_ruling() -> dict | None:
    rows = [r for r in _rows(rulings_log()) if r.get("kind") == "phase0"]
    return rows[-1] if rows else None


def faculty() -> dict:
    """What the interface may call the faculty, and which readers it has —
    decided by the recorded Phase 0 ruling, never by the page."""
    ruling = phase0_ruling()
    if ruling and ruling.get("result") == "PASS":
        return {"name": FACULTY_NAME_IF_PASSED, "readers": list(READERS), "phase0": ruling,
                "why": "Phase 0 recorded PASS: three aspects, the faculty's name in use"}
    if ruling and ruling.get("result") == "FAIL":
        return {"name": FACULTY_NAME_OTHERWISE, "readers": ["lachesis", "atropos"], "phase0": ruling,
                "why": "Phase 0 recorded FAIL: the precommitted pair, and the name stays out of the interface"}
    return {"name": FACULTY_NAME_OTHERWISE, "readers": list(READERS), "phase0": None,
            "why": "Phase 0 has no recorded result yet: three readers, no faculty name claimed"}


# ---------------------------------------------------------------------------
# the writer's notebook
# ---------------------------------------------------------------------------

def remember(text: str, source: dict | None = None, readers: list[str] | None = None) -> dict:
    """The owner keeps something for the readers to bear in mind. What is
    kept is what he said, with its source; a preference is not a claim that
    something is correct, and nothing here infers anything from it."""
    text = (text or "").strip()
    if not text:
        raise ValueError("nothing to remember")
    if len(text) > 2000:
        raise ValueError("a notebook entry is at most 2000 characters")
    fors = [r for r in (readers or list(NOTEBOOK_READERS)) if r in NOTEBOOK_READERS]
    if not fors:
        raise ValueError("a notebook entry is for Clotho, Lachesis, or both; the blind reader never receives it")
    src = dict(source or {})
    src_kind = str(src.get("kind") or "typed")
    row = {"kind": "remember", "note_id": "nb_" + uuid.uuid4().hex[:12], "at": cli._now(),
           "epoch": cli.current_epoch(), "text": text, "for": fors,
           "source": {"kind": src_kind,
                      "reading_id": str(src.get("reading_id") or ""),
                      "response_id": str(src.get("response_id") or ""),
                      "reader": str(src.get("reader") or ""),
                      "segment": src.get("segment") if isinstance(src.get("segment"), int) else None},
           "means": "something the writer chose to keep in the readers' view",
           "is_not": ["a correctness claim", "a diagnosis", "an instruction to agree"]}
    return _append(notebook_log(), row)


def correct_note(note_id: str, text: str) -> dict:
    text = (text or "").strip()
    if not text:
        raise ValueError("a correction needs text")
    if note_id not in fold_notebook():
        raise ValueError("no such notebook entry")
    return _append(notebook_log(), {"kind": "correct", "note_id": note_id, "at": cli._now(), "text": text[:2000]})


def retire_note(note_id: str, why: str = "") -> dict:
    if note_id not in fold_notebook():
        raise ValueError("no such notebook entry")
    return _append(notebook_log(), {"kind": "retire", "note_id": note_id, "at": cli._now(), "why": (why or "")[:300]})


def restore_note(note_id: str) -> dict:
    if note_id not in fold_notebook():
        raise ValueError("no such notebook entry")
    return _append(notebook_log(), {"kind": "restore", "note_id": note_id, "at": cli._now()})


def fold_notebook() -> dict[str, dict]:
    """Every entry with its current text and state; history kept on it."""
    out: dict[str, dict] = {}
    for r in _rows(notebook_log()):
        k, nid = r.get("kind"), r.get("note_id")
        if k == "remember" and nid:
            out[nid] = {**r, "state": "active", "history": []}
        elif nid in out:
            e = out[nid]
            e["history"].append({"kind": k, "at": r.get("at"), "text": r.get("text", ""), "why": r.get("why", "")})
            if k == "correct":
                e["text"] = r.get("text", e["text"])
            elif k == "retire":
                e["state"] = "retired"
            elif k == "restore":
                e["state"] = "active"
    return out


def active_notes(reader: str) -> list[dict]:
    """The entries this reader receives: active, and kept FOR this reader.
    Atropos receives nothing, structurally — see blind_request()."""
    if reader not in NOTEBOOK_READERS:
        return []
    return [e for e in fold_notebook().values() if e["state"] == "active" and reader in (e.get("for") or [])]


def notebook_block(entries: list[dict]) -> str:
    if not entries:
        return ""
    lines = ["What the writer has chosen to keep in your view. Each is something the writer said, kept with its source. A preference is not a claim that something is correct, and none of this is an instruction to agree; it is there so your criticism can be more relevant.",
             ""]
    for e in entries:
        src = e.get("source") or {}
        where = ("from a reading by " + src["reader"]) if src.get("reader") else "written by the writer"
        lines.append(f"- {e['text']}  ({where})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# requests — what is sent, exactly
# ---------------------------------------------------------------------------

def blind_request(draft: str, settings: dict) -> tuple[cli.Cacheable, dict]:
    """THE ISOLATION. The blind reading's request is the fixed instructions
    and the exact draft. This function takes nothing else, so nothing else
    can be sent: no notebook, no prior draft, no intent, no sibling."""
    system = instructions_for("atropos", settings)
    req = cli.Cacheable(system, draft)
    assert req.variable == draft, "the blind request must carry the exact draft"
    return req, {"system_sha": sha(system), "user_sha": sha(draft), "user_is_exact_draft": True,
                 "context": ["draft"], "notebook_ids": []}


def reading_request(reader: str, draft: str, settings: dict, notes: list[dict]) -> tuple[cli.Cacheable, dict]:
    """A reading by Clotho or Lachesis: instructions, the notebook entries
    kept for that reader (if any), and the exact draft as the message."""
    if reader not in NOTEBOOK_READERS:
        raise ValueError("reading_request is for the readers that may receive the notebook")
    system = instructions_for(reader, settings)
    nb = notebook_block(notes)
    if nb:
        system = system + "\n\n" + nb
    req = cli.Cacheable(system, draft)
    return req, {"system_sha": sha(system), "user_sha": sha(draft), "user_is_exact_draft": True,
                 "context": ["draft"] + (["notebook"] if nb else []),
                 "notebook_ids": [e["note_id"] for e in notes]}


def followup_request(reader: str, draft: str, settings: dict, previous: dict, question: str,
                     notes: list[dict], include_notebook: bool) -> tuple[cli.Cacheable, dict]:
    """A follow-up to ONE reader, in that reader's own thread: its
    instructions, its own previous answer, the draft, the question. For the
    blind reader this is the informed consultation — labelled so, and the
    notebook rides only when the owner chose to share it."""
    question = (question or "").strip()
    if not question:
        raise ValueError("a follow-up needs a question")
    if len(question) > 4000:
        raise ValueError("a follow-up question is at most 4000 characters")
    consultation = reader == "atropos"
    role_text = ROLE_TEXT[reader] if not consultation else ATROPOS
    manner = manner_clause(normalize_settings(settings)[reader])
    system = role_text + "\n\n" + manner + "\n\n" + (CONSULT if consultation else FOLLOWUP)
    context = ["draft", "own_previous_response", "question"]
    nb_ids: list[str] = []
    if notes and (not consultation or include_notebook):
        nb = notebook_block(notes)
        if nb:
            system = system + "\n\n" + nb
            context.append("notebook")
            nb_ids = [e["note_id"] for e in notes]
    user = ("The passage:\n\n" + draft + "\n\n---\nYour earlier reading, unchanged:\n\n"
            + (previous.get("raw_text") or "") + "\n\n---\nThe writer's question:\n\n" + question)
    req = cli.Cacheable(system, user)
    return req, {"system_sha": sha(system), "user_sha": sha(user), "user_is_exact_draft": False,
                 "context": context, "notebook_ids": nb_ids,
                 "in_reply_to": previous.get("response_id", "")}


# ---------------------------------------------------------------------------
# quotation checking — every quoted span against the exact text
# ---------------------------------------------------------------------------

_QUOTES = {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "}


def _norm_map(s: str) -> tuple[str, list[int]]:
    out, idx = [], []
    prev_space = False
    for i, ch in enumerate(s):
        ch = _QUOTES.get(ch, ch)
        if ch.isspace():
            if prev_space:
                continue
            out.append(" "); idx.append(i); prev_space = True
        else:
            out.append(ch); idx.append(i); prev_space = False
    return "".join(out), idx


def locate(passage: str, span: str) -> dict:
    """{status: exact|normalized|not_found, start, end, n}. Exact first;
    then with whitespace collapsed and quotes and dashes unified; else not
    found — and a span that is not found is REPORTED as such, never
    dropped, never repaired."""
    span = (span or "").strip()
    if not span:
        return {"status": "not_found", "start": -1, "end": -1, "n": 0}
    n = passage.count(span)
    if n:
        st = passage.find(span)
        return {"status": "exact", "start": st, "end": st + len(span), "n": n}
    np_, pmap = _norm_map(passage)
    ns, _ = _norm_map(span)
    ns = ns.strip()
    n = np_.count(ns) if ns else 0
    if n:
        st = np_.find(ns)
        return {"status": "normalized", "start": pmap[st], "end": pmap[st + len(ns) - 1] + 1, "n": n}
    return {"status": "not_found", "start": -1, "end": -1, "n": 0}


def check_segments(passage: str, parsed: dict | None) -> list[dict]:
    segs = ((parsed or {}).get("segments") or []) if isinstance(parsed, dict) else []
    out = []
    for i, s in enumerate(segs):
        if not isinstance(s, dict):
            continue
        klass = str(s.get("class") or "")
        span = str(s.get("span") or "")
        span2 = str(s.get("span2") or "")
        row = {"i": i, "class": klass, "class_words": CLASS_WORDS.get(klass, klass.replace("_", " ") or "note"),
               "text": str(s.get("text") or "")[:4000], "span": span[:1000], "span2": span2[:1000],
               "located": locate(passage, span) if span else None,
               "located2": locate(passage, span2) if span2 else None}
        row["quoted"] = ("no span" if not span else row["located"]["status"])
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# readings and responses
# ---------------------------------------------------------------------------

def _snapshot(text: str, scope: str) -> dict:
    return {"text": text, "sha256": sha(text), "words": len(text.split()), "chars": len(text),
            "scope": scope if scope in ("draft", "paragraph", "selection") else "draft",
            "identity_rule": "exact bytes; a whitespace change is a different snapshot"}


def start_reading(text: str, scope: str = "draft", previous_reading_id: str = "",
                  readers: list[str] | None = None, models: dict | None = None) -> dict:
    """Freeze one snapshot and write the reading record: what will be read,
    by whom, under which settings and which notebook. Nothing is called
    here — the caller dispatches run_reader() per reader, separately."""
    text = text if isinstance(text, str) else ""
    if not text.strip():
        raise ValueError("there is nothing to read")
    if len(text) > 60000:
        raise ValueError("that is more than the readers take at once (60,000 characters); read a part of it")
    fac = faculty()
    chosen = [r for r in (readers or fac["readers"]) if r in fac["readers"]]
    if not chosen:
        raise ValueError("no reader is available under the recorded ruling")
    settings = current_settings()
    models = models or {}
    rid = "rd_" + uuid.uuid4().hex[:12]
    dispatch = []
    for r in chosen:
        notes = active_notes(r)
        dispatch.append({"reader": r, "response_id": "rs_" + uuid.uuid4().hex[:12],
                         "reads_for": READS_FOR[r], "settings": settings[r],
                         "prompt_version": PROMPTS_VERSION,
                         "prompt_sha": sha(instructions_for(r, settings)),
                         "notebook_ids": [e["note_id"] for e in notes] if r in NOTEBOOK_READERS else [],
                         "model": str((models.get(r) or {}).get("model") or ""),
                         "provider": str((models.get(r) or {}).get("provider") or ""),
                         "same_model_as_strong": bool((models.get(r) or {}).get("same_model_as_strong", False))})
    rec = {"kind": "moira_reading", "mode": "moira_reading", "reading_id": rid, "trace_id": rid,
           "created_at": cli._now(), "epoch": cli.current_epoch(),
           "snapshot": _snapshot(text, scope), "input_text": text,
           "faculty_name": fac["name"], "readers": dispatch,
           "previous_reading_id": _safe_id(previous_reading_id),
           "means": "three separate readings of one exact snapshot; no conference, no verdict, no score"}
    _write_once(readings_dir() / f"{rid}.json", rec)
    return rec


def run_reader(reading: dict, reader: str, gateway, response_id: str = "") -> dict:
    """ONE reader, one call, one response file — complete or failed. A failure
    is recorded as a failure with its class; it never counts as agreement
    and never touches another reader's file."""
    entry = next((d for d in reading.get("readers") or [] if d.get("reader") == reader), None)
    if entry is None:
        raise ValueError(f"{reader!r} is not on this reading's dispatch list")
    rid = response_id or entry["response_id"]
    draft = reading["snapshot"]["text"]
    settings = {r: d["settings"] for r, d in ((d["reader"], d) for d in reading["readers"])}
    if reader == "atropos":
        req, request = blind_request(draft, settings)
        notes: list[dict] = []
    else:
        notes = [e for e in active_notes(reader) if e["note_id"] in (entry.get("notebook_ids") or [])]
        req, request = reading_request(reader, draft, settings, notes)
    return _call(reading_id=reading["reading_id"], reader=reader, role="reading", response_id=rid,
                 req=req, request=request, gateway=gateway, settings=settings[reader],
                 model=entry.get("model") or getattr(gateway, "model", "") or getattr(gateway, "name", ""),
                 provider=entry.get("provider") or getattr(gateway, "name", ""),
                 same_model=entry.get("same_model_as_strong", False), passage=draft)


def ask_reader(reading: dict, reader: str, question: str, gateway, include_notebook: bool = False,
               model: str = "", provider: str = "") -> dict:
    """A follow-up to one reader — or, for the blind reader, the informed
    consultation. A NEW response; the earlier one is not touched."""
    prev = latest_response(reading["reading_id"], reader)
    if prev is None or prev.get("status") != "complete":
        raise ValueError(f"{reader} has no completed reading here to follow up on")
    draft = reading["snapshot"]["text"]
    entry = next((d for d in reading.get("readers") or [] if d.get("reader") == reader), None) or {}
    settings = {r: d["settings"] for r, d in ((d["reader"], d) for d in reading["readers"])}
    notes = active_notes(reader) if reader in NOTEBOOK_READERS else (fold_active_all() if include_notebook else [])
    req, request = followup_request(reader, draft, settings, prev, question, notes,
                                    include_notebook=include_notebook)
    role = "consultation" if reader == "atropos" else "followup"
    return _call(reading_id=reading["reading_id"], reader=reader, role=role, response_id="rs_" + uuid.uuid4().hex[:12],
                 req=req, request=request, gateway=gateway, settings=settings[reader],
                 model=model or entry.get("model") or getattr(gateway, "model", "") or getattr(gateway, "name", ""),
                 provider=provider or entry.get("provider") or getattr(gateway, "name", ""),
                 same_model=entry.get("same_model_as_strong", False), passage=draft,
                 question=question.strip(), expects_json=False)


def fold_active_all() -> list[dict]:
    """Every active notebook entry, for the consultation the owner chose to
    share it with. Not a reader's own list — the owner's whole notebook."""
    return [e for e in fold_notebook().values() if e["state"] == "active"]


def _call(*, reading_id, reader, role, response_id, req, request, gateway, settings, model, provider,
          same_model, passage, question=None, expects_json=True) -> dict:
    started = cli._now()
    t0 = time.monotonic()
    ledger, owns = cli.open_attempt_ledger(gateway, run_id=reading_id, component=reader)
    raw, error, err_class = "", "", ""
    try:
        raw = gateway.complete(req)
    except Exception as e:  # noqa: BLE001 — recorded, never re-raised into another reader
        error = str(e)[:600]
        err_class = type(e).__name__
    finally:
        events = ledger.events() if owns else []
        if owns:
            cli.close_attempt_ledger(gateway)
    usage = None
    for ev in events:
        if ev.get("outcome") == "ok" and ev.get("usage"):
            usage = ev.get("usage")
    parsed, parse_error, segments = None, "", []
    if not error and expects_json:
        try:
            parsed = cli._extract_json(raw)
        except Exception as e:  # noqa: BLE001
            parse_error = f"{type(e).__name__}: {str(e)[:200]}"
        segments = check_segments(passage, parsed) if parsed is not None else []
    # THREE outcomes, kept apart: failed (no answer came back — the call
    # raised, which includes the gateway's own refusal when the model hit its
    # output ceiling), unusable (an answer came back that is not a usable
    # reading — no JSON, or no segments), complete (a usable reading). An
    # answer that merely RETURNED is never shown as a finished reader.
    if error:
        status, unusable = "failed", ""
    elif expects_json and (parsed is None or not segments):
        status = "unusable"
        unusable = ("the reply could not be read as a reading: " + parse_error) if parse_error else \
                   "the reply held no observations"
    elif not expects_json and not (raw or "").strip():
        status, unusable = "unusable", "the reply was empty"
    else:
        status, unusable = "complete", ""
    row = {"kind": "moira_response", "response_id": response_id, "reading_id": reading_id, "reader": reader,
           "reads_for": READS_FOR[reader], "role": role,
           "started_at": started, "finished_at": cli._now(), "seconds": round(time.monotonic() - t0, 2),
           "status": status, "unusable_reason": unusable,
           "error": error, "error_class": err_class,
           "model": model, "provider": provider, "same_model_as_strong": bool(same_model),
           "prompt_version": PROMPTS_VERSION, "settings": settings,
           "request": request, "gateway_settings": cli.gateway_settings(gateway),
           "usage": usage, "attempts": events,
           "raw_text": raw if not error else "", "parsed_ok": parsed is not None, "parse_error": parse_error,
           "segments": segments, "question": question,
           "is_not": ["a verdict", "a score", "a judgment about the writer", "agreement with another reader"]}
    if status == "failed":
        row["failure_means"] = "this reader did not answer; that is not a finding about the writing, and not agreement with any other reader"
    elif status == "unusable":
        row["failure_means"] = "this reader's reply came back but is not a usable reading; it is not a finding about the writing, and not agreement with any other reader"
    _write_once(responses_dir() / f"{response_id}.json", row)
    return row


def fail_reader(reading: dict, reader: str, error: str, response_id: str = "") -> dict:
    """A reader that could not even be asked (no lane, no key): recorded as a
    failed response with its reason, so the view says so instead of showing
    a reader that is forever 'reading'."""
    entry = next((d for d in reading.get("readers") or [] if d.get("reader") == reader), None)
    if entry is None:
        raise ValueError(f"{reader!r} is not on this reading's dispatch list")
    rid = response_id or entry["response_id"]
    now = cli._now()
    row = {"kind": "moira_response", "response_id": rid, "reading_id": reading["reading_id"], "reader": reader,
           "reads_for": READS_FOR[reader], "role": "reading", "started_at": now, "finished_at": now, "seconds": 0.0,
           "status": "failed", "error": (error or "no model lane")[:600], "error_class": "no_lane",
           "model": entry.get("model", ""), "provider": entry.get("provider", ""),
           "same_model_as_strong": bool(entry.get("same_model_as_strong", False)),
           "prompt_version": PROMPTS_VERSION, "settings": entry.get("settings", {}),
           "request": {"system_sha": entry.get("prompt_sha", ""), "user_sha": reading["snapshot"]["sha256"],
                       "user_is_exact_draft": True, "context": ["draft"], "notebook_ids": [], "sent": False},
           "gateway_settings": {}, "usage": None, "attempts": [], "raw_text": "", "parsed_ok": False,
           "parse_error": "", "segments": [], "question": None,
           "failure_means": "this reader did not answer; that is not a finding about the writing, and not agreement with any other reader",
           "is_not": ["a verdict", "a score", "a judgment about the writer", "agreement with another reader"]}
    _write_once(responses_dir() / f"{rid}.json", row)
    return row


def responses_of(reading_id: str) -> list[dict]:
    rid = _safe_id(reading_id)
    out = []
    for p in sorted(responses_dir().glob("rs_*.json")) if responses_dir().exists() else []:
        d = _read(p)
        if d and d.get("reading_id") == rid:
            out.append(d)
    out.sort(key=lambda d: (d.get("started_at") or "", d.get("response_id") or ""))
    return out


def latest_response(reading_id: str, reader: str, role: str = "reading") -> dict | None:
    rows = [d for d in responses_of(reading_id) if d.get("reader") == reader and d.get("role") == role]
    return rows[-1] if rows else None


def view(reading_id: str) -> dict | None:
    """The reading with what each reader has answered — from the files, so a
    server restart loses nothing that was written. A reader with no file is
    'no response recorded', said as such."""
    rec = load_reading(reading_id)
    if rec is None:
        return None
    resp = responses_of(reading_id)
    by_reader: dict[str, dict] = {}
    for d in rec.get("readers") or []:
        r = d["reader"]
        reads = [x for x in resp if x.get("reader") == r and x.get("role") == "reading"]
        follow = [x for x in resp if x.get("reader") == r and x.get("role") in ("followup", "consultation")]
        current = reads[-1] if reads else None
        by_reader[r] = {"reader": r, "reads_for": READS_FOR[r], "dispatched": d,
                        "status": (current.get("status") if current else "no response recorded"),
                        "response": current, "earlier_attempts": reads[:-1],
                        "followups": follow}
    view_ = {k: v for k, v in rec.items() if k != "input_text"}
    view_["readers"] = [by_reader[d["reader"]] for d in rec.get("readers") or []]
    view_["answered"] = sum(1 for r in view_["readers"] if r["status"] == "complete")
    view_["failed"] = sum(1 for r in view_["readers"] if r["status"] == "failed")
    view_["unusable"] = sum(1 for r in view_["readers"] if r["status"] == "unusable")
    view_["pending"] = sum(1 for r in view_["readers"] if r["status"] == "no response recorded")
    view_["statuses"] = {"complete": "a usable reading", "unusable": "a reply came back that is not a usable reading",
                         "failed": "no reply came back", "no response recorded": "not answered yet, or the server restarted"}
    view_["no_conference"] = "the readers answered separately; nothing here combines them, and no verdict or score exists"
    return view_


def list_readings(limit: int = 30) -> list[dict]:
    out = []
    for p in (sorted(readings_dir().glob("rd_*.json")) if readings_dir().exists() else []):
        d = _read(p)
        if not d:
            continue
        resp = responses_of(d["reading_id"])
        statuses = {}
        for r in d.get("readers") or []:
            reads = [x for x in resp if x.get("reader") == r["reader"] and x.get("role") == "reading"]
            statuses[r["reader"]] = reads[-1]["status"] if reads else "no response recorded"
        snap = d.get("snapshot") or {}
        out.append({"reading_id": d["reading_id"], "created_at": d.get("created_at", ""),
                    "faculty_name": d.get("faculty_name", ""),
                    "snapshot_sha256": snap.get("sha256", ""), "words": snap.get("words", 0),
                    "scope": snap.get("scope", ""), "head": (snap.get("text") or "").strip()[:80],
                    "previous_reading_id": d.get("previous_reading_id", ""),
                    "readers": statuses, "followups": sum(1 for x in resp if x.get("role") != "reading")})
    out.sort(key=lambda d: (d["created_at"], d["reading_id"]), reverse=True)
    return out[:max(1, min(int(limit or 30), 200))]


def summary() -> dict:
    fac = faculty()
    nb = fold_notebook()
    return {"faculty": fac, "settings": current_settings(), "prompts_version": PROMPTS_VERSION,
            "notebook": {"active": sum(1 for e in nb.values() if e["state"] == "active"),
                         "retired": sum(1 for e in nb.values() if e["state"] != "active")},
            "readings": len(list(readings_dir().glob("rd_*.json"))) if readings_dir().exists() else 0}


# ---------------------------------------------------------------------------
# the offline stand-in — proves the pipeline, never the prose
# ---------------------------------------------------------------------------

class MockMoiraGateway(cli.MockGateway):
    """Deterministic, offline. Quotes real spans of whatever it is given (the
    first words, a middle run with its quotes bent so the normalized match
    is exercised) and one span that is NOT in the text, so the not-found
    marking runs end to end. A draft containing 'FAIL <READER>' makes that
    reader's call raise — one dead reader, never the run."""

    name = "mock-moira"
    model = "mock-moira-1"

    def __init__(self, reader: str):
        self.reader = reader

    def complete(self, prompt) -> str:
        text = getattr(prompt, "variable", None)
        if text is None:
            text = str(prompt)
        if f"FAIL {self.reader.upper()}" in text:
            raise RuntimeError(f"mock provider refused the {self.reader} call")
        # a follow-up carries the passage inside a framed message
        m = re.search(r"The passage:\n\n(.*?)\n\n---", text, re.S)
        passage = m.group(1) if m else text
        words = passage.split()
        first = " ".join(words[:4])
        mid = " ".join(words[len(words) // 2: len(words) // 2 + 4])
        # bent: the same words with one space doubled — an exact match fails,
        # the normalized match succeeds, and the record says "normalized"
        bent = mid.replace(" ", "  ", 1)
        if m or "The writer's question:" in text:
            return f"In plain prose: about “{first}”, what I reported still holds; the question does not change it."
        if self.reader == "clotho":
            segs = [{"class": "current", "span": first, "text": "the current runs here"},
                    {"class": "must_survive", "span": bent, "text": "keep this"},
                    {"class": "generic", "span": "words that are not in the passage at all", "text": "invented span"},
                    {"class": "projected_residue", "span": first, "text": "prediction: this stays"}]
        elif self.reader == "lachesis":
            segs = [{"class": "path", "text": "one path, plainly"},
                    {"class": "break", "span": first, "span2": mid, "text": "the bridge between these was assumed"},
                    {"class": "repair", "span": bent, "text": "one repair"},
                    {"class": "uncertain", "span": "not in the passage either", "text": "invented span"}]
        else:
            segs = [{"class": "received", "text": "a stranger's account"},
                    {"class": "governing_idea", "text": "one idea"},
                    {"class": "substituted", "span": first, "text": "I reached for a familiar story here"},
                    {"class": "lost_certainty", "span": "nowhere in the text", "text": "invented span"}]
        return json.dumps({"segments": segs})


def mock_gateway_for(reader: str):
    return MockMoiraGateway(reader)


# ---------------------------------------------------------------------------
# command line — the owner's rulings, and read-only views
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Professor Moira — records and rulings (no model, no network)")
    ap.add_argument("--record-phase0", choices=["PASS", "FAIL"], help="record the Phase 0 result as the owner's ruling")
    ap.add_argument("--note", default="", help="what the ruling rests on (e.g. the measure output's ruling line)")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    if args.record_phase0:
        print(json.dumps(record_phase0(args.record_phase0, args.note), indent=2))
        print(json.dumps(faculty(), indent=2))
    elif args.list:
        print(json.dumps(list_readings(), indent=2, ensure_ascii=False))
    else:
        print(json.dumps(summary(), indent=2))
