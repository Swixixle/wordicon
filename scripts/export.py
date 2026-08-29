#!/usr/bin/env python3
"""Get the corpus out — in a shape something other than Wordicon can read.

    python3 scripts/export.py lexicon        # markdown you can write from
    python3 scripts/export.py bundle         # dated tarball + checksummed manifest
    python3 scripts/export.py table          # one JSONL row per accepted word
    python3 scripts/export.py all

Blueprint §18 and acceptance test 11 asked for this in January: "corpus export
does not depend on a model vendor's proprietary format." The test has been
passing green ever since without any export existing — it only checks that the
schema files parse. A test that guards an unbuilt feature is a vacuous probe,
and this file is what finally makes it mean something.

THE RULE THAT GOVERNS ALL THREE SHAPES: an export either carries the receipts
or says on its face that it does not. A tidy document full of coinages with no
trace back to what was checked is exactly the artifact this project exists to
refuse — it would launder unverified claims out of the one system built to keep
them marked. So the lexicon ends every entry with its trace id, and its header
says plainly where the evidence actually lives.

Standalone on purpose, like digest.py: an exporter that can crash the tool it
exports is worse than no exporter.
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import sys
import tarfile

LOCAL_STATE = pathlib.Path(
    os.environ.get("WORDICON_STATE")
    or (pathlib.Path(__file__).resolve().parent.parent / "local_state"))
TOOL = "wordicon-export/1"


def _load(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _sha256(p, _buf=1 << 20):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(_buf)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def load_accepted():
    """Every word the owner accepted — from BOTH places acceptance is recorded.

    accepted_concepts.json holds the rich entries. judgments.jsonl holds the
    ruling itself, and for acceptances made before definitions were written at
    judgment time there is a row there and nothing else. The CLI already merges
    the two (load_accepted_concepts); an exporter that read only the json file
    would print a confident "53 accepted coin(s)" over a corpus containing 59
    rulings, and the six it dropped would be exactly the six with the least
    recorded about them. Silent omission with a confident count is the failure
    this file exists to refuse, so the fallback entries are carried through and
    marked, never skipped.

    A fallback entry keeps its trace: the judgment row's originating_operation
    is the run that produced the name, and its receipt is on disk even when no
    result file is. That is the difference between "we lost this" and "we know
    where to look."
    """
    out, seen = [], set()
    for x in (_load(LOCAL_STATE / "accepted_concepts.json") or []):
        if not isinstance(x, dict):
            continue
        k = (x.get("name") or "").strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(x)

    jl = LOCAL_STATE / "judgments.jsonl"
    if jl.exists():
        for line in jl.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                j = json.loads(line)
            except Exception:
                continue
            if j.get("decision") != "accepted":
                continue
            k = (j.get("candidate_text") or "").strip().lower()
            if not k or k in seen:
                continue
            seen.add(k)
            out.append({
                "id": j.get("id", ""), "name": j["candidate_text"],
                "definition": "", "status": "accepted",
                "accepted_from": j.get("originating_operation") or "",
                "accepted_at": "", "_judgment_only": True,
            })
    return out


def index_results():
    """title -> the card that produced it, so the lexicon can carry the
    contradiction and the axiom rather than the definition alone. Keyed by
    normalized title because that is the identity the owner sees; where two
    runs made the same title the LATEST wins, and the entry records which
    trace it came from so the tie is inspectable rather than silent."""
    by_title = {}
    for p in sorted((LOCAL_STATE / "results").glob("*.json")):
        d = _load(p)
        if not isinstance(d, dict):
            continue
        for c in (d.get("candidates") or []):
            b = c.get("bff") or {}
            t = (b.get("title") or "").strip().lower()
            if not t:
                continue
            prev = by_title.get(t)
            if prev and (prev["run"].get("created_at") or "") > (d.get("created_at") or ""):
                continue
            by_title[t] = {"bff": b, "run": d}
    return by_title


def _entry(acc, hit):
    b = (hit or {}).get("bff") or {}
    flesh = b.get("flesh") or {}
    fric = b.get("friction") or {}
    sup = (b.get("claim_support") or {}).get("support") or ""
    return {
        "word": acc.get("name", ""),
        "definition": (acc.get("definition") or flesh.get("definition") or "").strip(),
        "contradiction": (flesh.get("central_contradiction") or "").strip(),
        "axiom": (flesh.get("axiom") or "").strip(),
        "plain": (flesh.get("plain_gloss") or "").strip(),
        "example": (flesh.get("example_sentence") or "").strip(),
        "register": fric.get("register") or "",
        "friction_verdict": fric.get("verdict") or "",
        "grounding": sup,
        "accepted_at": acc.get("accepted_at") or "",
        "trace": acc.get("accepted_from") or ((hit or {}).get("run") or {}).get("trace_id", ""),
        "id": acc.get("id", ""),
        # Computed from what is actually present, never from which file the
        # entry came out of: a judgment-only acceptance whose run WAS kept
        # recovers its meaning through the results index and is not marked.
        "meaning_recorded": bool(
            (acc.get("definition") or flesh.get("definition") or "").strip()
            or (flesh.get("plain_gloss") or "").strip()),
    }


def build_entries():
    idx = index_results()
    out = []
    for acc in load_accepted():
        out.append(_entry(acc, idx.get((acc.get("name") or "").strip().lower())))
    out.sort(key=lambda e: (e["word"] or "").lower())
    return out


# ---------------------------------------------------------------------------
def lexicon_md(entries, bundle_note=""):
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    nomeaning = sum(1 for e in entries if not e["meaning_recorded"])
    count = f"{len(entries)} accepted coin(s)"
    if nomeaning:
        # Computed from the entries below, in the same pass that writes them.
        # A header stating a total while the body quietly holds a different
        # story is a defect this project has shipped three times already.
        count += f" — {nomeaning} of them with no recorded meaning"
    L = [f"# Wordicon lexicon", "",
         f"{count} · exported {now}", "",
         "**This document does not carry the evidence.** Each entry ends with the "
         "trace id of the run that produced it; the grounding checks, the critic's "
         "objections, the anchors and the receipts live in the corpus bundle, not "
         "here. A coin read out of this file is the owner's ruling, not a "
         "verified claim, and the two are different things.",
         ""]
    if bundle_note:
        L += [f"Evidence bundle: `{bundle_note}`", ""]
    L.append("---")
    L.append("")
    for e in entries:
        L.append(f"## {e['word']}")
        L.append("")
        # The accepted record sometimes stores the plain gloss AS the
        # definition, which printed the same sentence twice under two
        # different headings and made the document look padded. Where they
        # are the same text, say it once.
        same = e["plain"] and e["definition"] and \
            e["plain"].strip().lower() == e["definition"].strip().lower()
        if e["plain"]:
            L.append(e["plain"])
            L.append("")
        if e["definition"] and not same:
            L.append(f"**Definition.** {e['definition']}")
            L.append("")
        if not e["meaning_recorded"]:
            # The word was accepted; what it meant was never written down.
            # Printing a bare heading here would read as an entry the reader
            # simply hasn't scrolled to the meaning of.
            L.append("*No meaning recorded.* This name was accepted before "
                     "definitions were stored at judgment time. The run's "
                     "receipt records that it was produced and from which "
                     "sources; what it was taken to mean is not on disk "
                     "anywhere, and nothing below reconstructs it.")
            L.append("")
        if e["contradiction"]:
            L.append(f"**Contradiction.** {e['contradiction']}")
            L.append("")
        if e["axiom"]:
            L.append(f"**Axiom.** {e['axiom']}")
            L.append("")
        if e["example"]:
            L.append(f"> {e['example']}")
            L.append("")
        # Provenance line. Deliberately blunt about what was NOT established:
        # a blank grounding field means no check ran, and saying "—" is more
        # honest than omitting the field and letting the gap read as a pass.
        bits = [f"`{e['trace'] or 'trace unrecorded'}`"]
        if e["register"]:
            bits.append(e["register"] + " word" if e["register"] == "kitchen" else "seminar term")
        bits.append("grounding: " + (e["grounding"] or "not checked"))
        if e["friction_verdict"]:
            bits.append("critic: " + e["friction_verdict"])
        if e["accepted_at"]:
            bits.append("accepted " + e["accepted_at"][:10])
        L.append("<sub>" + " · ".join(bits) + "</sub>")
        L.append("")
        L.append("---")
        L.append("")
    return "\n".join(L)


def table_jsonl(entries):
    return "\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n"


def bundle(out_dir):
    """A dated tarball plus a manifest that lets someone who does not trust the
    owner check that nothing was edited after the fact. Without the manifest
    this is a backup; with it, it is evidence."""
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in LOCAL_STATE.rglob("*")
                   if p.is_file() and not p.name.startswith("."))
    manifest = {
        "tool": TOOL, "created_at": now.isoformat(),
        "state_root": str(LOCAL_STATE), "file_count": len(files),
        "note": ("Every entry below is sha256 of the file as exported. Re-hash "
                 "any file and compare; a mismatch means the copy changed after "
                 "this manifest was written. The manifest hash is printed by the "
                 "exporter and is not stored inside the manifest, so altering a "
                 "file and rewriting its entry still changes the digest."),
        "files": [{"path": str(p.relative_to(LOCAL_STATE)),
                   "bytes": p.stat().st_size, "sha256": _sha256(p)} for p in files],
    }
    mtext = json.dumps(manifest, indent=2, ensure_ascii=False)
    mdigest = hashlib.sha256(mtext.encode("utf-8")).hexdigest()
    tar_path = out_dir / f"wordicon-corpus-{stamp}.tar.gz"
    man_path = out_dir / f"wordicon-corpus-{stamp}.manifest.json"
    man_path.write_text(mtext, encoding="utf-8")
    with tarfile.open(tar_path, "w:gz") as tf:
        for p in files:
            tf.add(p, arcname=str(pathlib.Path("local_state") / p.relative_to(LOCAL_STATE)))
        tf.add(man_path, arcname="MANIFEST.json")
    return tar_path, man_path, mdigest, len(files)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("what", choices=["lexicon", "bundle", "table", "all"])
    ap.add_argument("-o", "--out", help="output file, or directory for bundle/all")
    a = ap.parse_args(argv)

    default_dir = pathlib.Path(a.out) if (a.out and a.what in ("bundle", "all")) \
        else pathlib.Path("exports")
    entries = [] if a.what == "bundle" else build_entries()

    if a.what in ("bundle", "all"):
        tar, man, digest, n = bundle(default_dir)
        print(f"bundle  {tar}  ({n} files)")
        print(f"manifest {man}")
        print(f"manifest sha256: {digest}")
        print("  keep that digest somewhere other than the bundle — a manifest that\n"
              "  travels with the thing it vouches for vouches for nothing.")
        bundle_note = tar.name
    else:
        bundle_note = ""

    if a.what in ("lexicon", "all"):
        p = pathlib.Path(a.out) if (a.out and a.what == "lexicon") else default_dir / "lexicon.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(lexicon_md(entries, bundle_note), encoding="utf-8")
        print(f"lexicon {p}  ({len(entries)} accepted coin(s))")

    if a.what in ("table", "all"):
        p = pathlib.Path(a.out) if (a.out and a.what == "table") else default_dir / "lexicon.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(table_jsonl(entries), encoding="utf-8")
        print(f"table   {p}  ({len(entries)} row(s))")

    if entries:
        nomeaning = sum(1 for e in entries if not e["meaning_recorded"])
        if nomeaning:
            print(f"  note: {nomeaning} of {len(entries)} accepted word(s) have no "
                  f"recorded meaning — exported as names with their trace, marked.")
        ungrounded = sum(1 for e in entries if not e["grounding"])
        if ungrounded:
            # Named, never silent. The lexicon is the owner's rulings; how many
            # of them rest on a check that never ran is a fact about the
            # document and belongs on the way out, not buried in a column.
            print(f"  note: {ungrounded} of {len(entries)} entries carry no recorded "
                  f"grounding check — their provenance line says so.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
