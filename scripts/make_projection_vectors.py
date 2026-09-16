#!/usr/bin/env python3
"""Writes tests/fixtures/projection_vectors.json — the golden vectors the
browser and the server both have to reproduce (workspace-v2 slice C).

Each vector carries a v1 document, its projection (the exact body), its
canonical JSON, the fingerprint_v2 for empty title fields, and the position
map (ProseMirror position · UTF-16 offset · code-point offset for every run
and separator). The suite checks Python against the file; the workspace
journey checks the editor bundle against the same file. String equality of
the projection alone proves nothing about the mapping, so the map is in
the vector too."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import document_schema as ds  # noqa: E402


def p(*inline):
    return {"type": "paragraph", "content": list(inline)}


def t(text, *marks):
    return {"type": "text", "text": text, "marks": list(marks)}


def br():
    return {"type": "hard_break"}


STRONG, EM = {"type": "strong"}, {"type": "em"}


def link(href):
    return {"type": "link", "attrs": {"href": href}}


VECTORS = [
    ("one paragraph", {"type": "doc", "content": [p(t("He threw it once."))]}),
    ("hard break inside a paragraph", {"type": "doc", "content": [p(t("A"), br(), t("B"))]}),
    ("two paragraphs", {"type": "doc", "content": [p(t("A")), p(t("B"))]}),
    ("empty paragraphs between: six LF", {"type": "doc", "content": [p(t("A")), p(), p(), p(t("B"))]}),
    ("terminal hard break kept", {"type": "doc", "content": [p(t("A"), br())]}),
    ("leading hard break kept", {"type": "doc", "content": [p(br(), t("A"))]}),
    ("emoji outside the BMP", {"type": "doc", "content": [p(t("x🙂y"))]}),
    ("zwj sequence and variation selector", {"type": "doc", "content": [p(t("👩‍👩‍👧 ✍️ end"))]}),
    ("combining marks", {"type": "doc", "content": [p(t("é ạ̈ ñ"))]}),
    ("tab inside", {"type": "doc", "content": [p(t("a\tb"))]}),
    ("nbsp at a run boundary", {"type": "doc", "content": [p(t("a ", STRONG), t("b"))]}),
    ("runs of spaces and trailing spaces", {"type": "doc", "content": [p(t("  lead   mid  trail  "))]}),
    ("heading and a list with a nested list under the second item", {"type": "doc", "content": [
        {"type": "heading", "attrs": {"level": 2}, "content": [t("Title")]},
        {"type": "bullet_list", "content": [
            {"type": "list_item", "content": [p(t("one"))]},
            {"type": "list_item", "content": [p(t("two")), {"type": "bullet_list", "content": [{"type": "list_item", "content": [p(t("two-a"))]}]}]},
            {"type": "list_item", "content": [p(t("three"))]},
        ]},
    ]}),
    ("ordered list starting at 4 with a two-paragraph item", {"type": "doc", "content": [
        {"type": "ordered_list", "attrs": {"order": 4}, "content": [
            {"type": "list_item", "content": [p(t("four")), p(t("still four"))]},
            {"type": "list_item", "content": [p(t("five"))]},
        ]},
    ]}),
    ("blockquote with two paragraphs, then a paragraph", {"type": "doc", "content": [
        {"type": "blockquote", "content": [p(t("Q1")), p(t("Q2"))]}, p(t("after")),
    ]}),
    ("marks: strong, em, link, and their order", {"type": "doc", "content": [
        p(t("plain "), t("bold", STRONG), t(" "), t("both", EM, STRONG), t(" "), t("linked", link("https://example.org/a?b=1"), EM)),
    ]}),
    ("a document that is one empty paragraph", {"type": "doc", "content": [p()]}),
    ("a document of three empty paragraphs", {"type": "doc", "content": [p(), p(), p()]}),
]


def main() -> None:
    out = []
    for name, doc in VECTORS:
        canon = ds.validate(doc)
        body = ds.project(canon)
        out.append({
            "name": name, "doc": canon, "body": body, "canonical": ds.canonical(canon),
            "fp2": ds.fingerprint_v2("", False, body, canon, ds.SCHEMA_VERSION, ds.PROJECTION_VERSION),
            "text_sha256": ds.slice_hash(body),
            "map": ds.position_map(canon),
            "leaf_count": len(ds.leaf_blocks(canon)),
            "round_trip_plain": ds.project(ds.validate(ds.parse_plain(body))) == body,
        })
    path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "projection_vectors.json"
    path.write_text(json.dumps({"schema": ds.SCHEMA_VERSION, "projection": ds.PROJECTION_VERSION, "vectors": out},
                               ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {path} — {len(out)} vectors")


if __name__ == "__main__":
    main()
