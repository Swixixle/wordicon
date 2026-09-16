#!/usr/bin/env python3
"""The structured document: schema v1, projection v1, the canonical form and
the versioned fingerprint (workspace-v2, slice C; instructions §7).

What a document is. `body` is the exact text — the thing every analysis,
search and hash has always used, and still the authority for what the words
are. `doc_json` is the structure around those words: paragraphs, headings,
lists (nested, items of several paragraphs), quotes, strong, emphasis,
links and hard breaks. The two are one versioned document: a save carries
both, the server computes the projection of the structure itself and
refuses a body that does not equal it, and the fingerprint covers both.

Schema v1 (explicitly: no code block, no image, no table — a later version
adds what it adds and says so):

  doc          > block+
  block        = paragraph | heading | bullet_list | ordered_list | blockquote
  paragraph    > inline*                (a leaf textblock)
  heading      > inline*  attrs {level: 1|2|3}
  bullet_list  > list_item+
  ordered_list > list_item+  attrs {order: int >= 0}
  list_item    > paragraph (paragraph | bullet_list | ordered_list)*   (a container; the first child is a paragraph)
  blockquote   > block+                                      (a container)
  inline       = text (marks: strong | em | link{href}) | hard_break

Projection v1. Visit the LEAF textblocks (paragraph, heading) in document
order exactly once; inside a block the text is unchanged and a hard break
is one LF; consecutive leaf blocks are joined with two LF; nothing is added
at the end. Numbering and quote markers live in the structure, not in the
text. So leaf blocks ["A", "", "", "B"] project to "A" + six LF + "B", and a
paragraph that ends in a hard break keeps its trailing LF.

Import of plain text splits on double LF (empty pieces kept), then single
LF becomes a hard break. It generates nodes directly and never touches the
characters: tabs, runs of spaces, combining marks and every other code
point stay as they are. A body with a carriage return or another C0
control (tab and LF excepted) is NOT convertible: it keeps the plain-text
path with its exact body, and nothing rewrites it.

The canonical form is the JSON of the document with sorted keys and no
whitespace, attributes as integers only, marks in a fixed order; the
browser produces the same bytes (tests/fixtures/projection_vectors.json is
the shared proof). The versioned fingerprint is

  fp2_ + sha256(canonical({"b": body, "m": title_is_manual, "t": title,
                            "d": canonical doc or null, "s": doc_schema,
                            "p": projection_version}))[:32]

Historical `fp_` fingerprints (body and title only) stay valid for the
records that carry them; nothing is rehashed in place."""
from __future__ import annotations

import hashlib
import json
import re

SCHEMA_VERSION = 1
PROJECTION_VERSION = 1
SUPPORTED_SCHEMAS = (1,)
SUPPORTED_PROJECTIONS = (1,)

BLOCKS = ("paragraph", "heading", "bullet_list", "ordered_list", "blockquote")
LEAF_BLOCKS = ("paragraph", "heading")
MARKS = ("strong", "em", "link")
MARK_ORDER = {"link": 0, "strong": 1, "em": 2}
_SAFE_HREF = re.compile(r"^(https?://|mailto:)[^\s\x00-\x1f]+$", re.I)
_C0 = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class SchemaError(ValueError):
    """The structure is not a v1 document. `where` is a path like
    'doc.content[2].content[0]'."""

    def __init__(self, message: str, where: str = "doc", error_class: str = "schema_invalid"):
        super().__init__(f"{where}: {message}")
        self.where = where
        self.error_class = error_class


# ---- validation ----------------------------------------------------------------

def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _check_marks(marks, where: str) -> list:
    if marks is None:
        return []
    if not isinstance(marks, list):
        raise SchemaError("marks must be a list", where)
    seen = set()
    out = []
    for i, m in enumerate(marks):
        w = f"{where}.marks[{i}]"
        if not isinstance(m, dict) or set(m.keys()) - {"type", "attrs"}:
            raise SchemaError("a mark is {type, attrs?}", w)
        t = m.get("type")
        if t not in MARKS:
            raise SchemaError(f"unknown mark {t!r}", w)
        if t in seen:
            raise SchemaError(f"mark {t!r} given twice", w)
        seen.add(t)
        attrs = m.get("attrs")
        if t == "link":
            if not isinstance(attrs, dict) or set(attrs.keys()) != {"href"} or not isinstance(attrs["href"], str):
                raise SchemaError("a link carries exactly {href}", w)
            if not _SAFE_HREF.match(attrs["href"]) or len(attrs["href"]) > 2000:
                raise SchemaError("a link href must be http(s) or mailto, without control characters", w, "unsafe_link")
            out.append({"type": "link", "attrs": {"href": attrs["href"]}})
        else:
            if attrs not in (None, {}):
                raise SchemaError(f"{t} takes no attrs", w)
            out.append({"type": t})
    out.sort(key=lambda m: MARK_ORDER[m["type"]])
    return out


def _check_inline(nodes, where: str) -> list:
    if nodes is None:
        return []
    if not isinstance(nodes, list):
        raise SchemaError("content must be a list", where)
    out = []
    for i, n in enumerate(nodes):
        w = f"{where}.content[{i}]"
        if not isinstance(n, dict):
            raise SchemaError("a node is an object", w)
        t = n.get("type")
        if t == "text":
            if set(n.keys()) - {"type", "text", "marks"}:
                raise SchemaError("a text node is {type, text, marks?}", w)
            s = n.get("text")
            if not isinstance(s, str) or s == "":
                raise SchemaError("a text node carries a non-empty string", w)
            if _C0.search(s) or "\n" in s or "\r" in s:
                raise SchemaError("text may not carry line breaks or control characters (a hard break is a node)", w, "unsupported_character")
            out.append({"type": "text", "text": s, "marks": _check_marks(n.get("marks"), w)})
        elif t == "hard_break":
            if set(n.keys()) - {"type"}:
                raise SchemaError("a hard break carries nothing", w)
            out.append({"type": "hard_break"})
        else:
            raise SchemaError(f"unknown inline node {t!r}", w)
    return out


def _check_block(n, where: str, depth: int = 0) -> dict:
    if not isinstance(n, dict):
        raise SchemaError("a node is an object", where)
    if depth > 24:
        raise SchemaError("nesting deeper than 24 is refused", where)
    t = n.get("type")
    keys = set(n.keys())
    if t == "paragraph":
        if keys - {"type", "content"}:
            raise SchemaError("a paragraph is {type, content?}", where)
        return {"type": "paragraph", "content": _check_inline(n.get("content"), where)}
    if t == "heading":
        if keys - {"type", "content", "attrs"}:
            raise SchemaError("a heading is {type, attrs, content?}", where)
        attrs = n.get("attrs") or {}
        lvl = attrs.get("level") if isinstance(attrs, dict) else None
        if not isinstance(attrs, dict) or set(attrs.keys()) != {"level"} or not _is_int(lvl) or lvl not in (1, 2, 3):
            raise SchemaError("a heading carries exactly {level: 1|2|3}", where)
        return {"type": "heading", "attrs": {"level": lvl}, "content": _check_inline(n.get("content"), where)}
    if t in ("bullet_list", "ordered_list"):
        if keys - {"type", "content", "attrs"}:
            raise SchemaError("a list is {type, attrs?, content}", where)
        items = n.get("content")
        if not isinstance(items, list) or not items:
            raise SchemaError("a list carries at least one item", where)
        out = {"type": t, "content": []}
        if t == "ordered_list":
            attrs = n.get("attrs") or {}
            order = attrs.get("order", 1) if isinstance(attrs, dict) else None
            if not isinstance(attrs, dict) or set(attrs.keys()) - {"order"} or not _is_int(order) or order < 0:
                raise SchemaError("an ordered list carries {order: int >= 0}", where)
            out["attrs"] = {"order": order}
        elif n.get("attrs") not in (None, {}):
            raise SchemaError("a bullet list takes no attrs", where)
        for i, it in enumerate(items):
            w = f"{where}.content[{i}]"
            if not isinstance(it, dict) or it.get("type") != "list_item" or set(it.keys()) - {"type", "content"}:
                raise SchemaError("a list holds list_item nodes", w)
            kids = it.get("content")
            if not isinstance(kids, list) or not kids:
                raise SchemaError("a list item carries at least one block", w)
            item = {"type": "list_item", "content": []}
            for j, k in enumerate(kids):
                kw = f"{w}.content[{j}]"
                if not isinstance(k, dict) or k.get("type") not in ("paragraph", "bullet_list", "ordered_list"):
                    raise SchemaError("a list item holds paragraphs and lists", kw)
                if j == 0 and k.get("type") != "paragraph":
                    raise SchemaError("a list item starts with a paragraph", kw)
                item["content"].append(_check_block(k, kw, depth + 1))
            out["content"].append(item)
        return out
    if t == "blockquote":
        if keys - {"type", "content"}:
            raise SchemaError("a blockquote is {type, content}", where)
        kids = n.get("content")
        if not isinstance(kids, list) or not kids:
            raise SchemaError("a blockquote carries at least one block", where)
        return {"type": "blockquote", "content": [_check_block(k, f"{where}.content[{i}]", depth + 1) for i, k in enumerate(kids)]}
    raise SchemaError(f"unknown block {t!r}", where)


def validate(doc, doc_schema: int = SCHEMA_VERSION) -> dict:
    """Returns the document in canonical node form (defaults filled, marks
    ordered, nothing else added) or raises SchemaError."""
    if doc_schema not in SUPPORTED_SCHEMAS:
        raise SchemaError(f"schema version {doc_schema!r} is not supported here (supported: {SUPPORTED_SCHEMAS})", "doc", "schema_unsupported")
    if not isinstance(doc, dict) or doc.get("type") != "doc" or set(doc.keys()) - {"type", "content"}:
        raise SchemaError("the root is {type: 'doc', content}", "doc")
    blocks = doc.get("content")
    if not isinstance(blocks, list) or not blocks:
        raise SchemaError("a document carries at least one block", "doc")
    return {"type": "doc", "content": [_check_block(b, f"doc.content[{i}]") for i, b in enumerate(blocks)]}


# ---- projection ------------------------------------------------------------------

def _leaves(node, out: list) -> None:
    t = node.get("type")
    if t in LEAF_BLOCKS:
        out.append(node)
        return
    for k in node.get("content") or []:
        _leaves(k, out)


def leaf_blocks(doc: dict) -> list:
    out: list = []
    for b in doc.get("content") or []:
        _leaves(b, out)
    return out


def block_text(block: dict) -> str:
    parts = []
    for n in block.get("content") or []:
        if n.get("type") == "text":
            parts.append(n["text"])
        elif n.get("type") == "hard_break":
            parts.append("\n")
    return "".join(parts)


def project(doc: dict, projection_version: int = PROJECTION_VERSION) -> str:
    if projection_version not in SUPPORTED_PROJECTIONS:
        raise SchemaError(f"projection version {projection_version!r} is not supported here", "doc", "projection_unsupported")
    return "\n\n".join(block_text(b) for b in leaf_blocks(doc))


def convertible(body: str) -> tuple[bool, str]:
    """Can this plain body become a v1 document without any character
    changing? A carriage return or another C0 control (tab and LF
    excepted) means no — the plain path keeps it exactly."""
    if not isinstance(body, str):
        return False, "not text"
    if "\r" in body:
        return False, "carriage return (CR) in the text — the structured schema keeps LF only; the plain path keeps the text exactly"
    if _C0.search(body):
        return False, "a control character in the text — the plain path keeps it exactly"
    return True, ""


def parse_plain(body: str) -> dict:
    """Plain text to a v1 document: double LF splits paragraphs (empty pieces
    kept), single LF is a hard break. No character is changed."""
    ok, why = convertible(body)
    if not ok:
        raise SchemaError(why, "body", "not_convertible")
    blocks = []
    for piece in body.split("\n\n"):
        content = []
        lines = piece.split("\n")
        for i, line in enumerate(lines):
            if i:
                content.append({"type": "hard_break"})
            if line:
                content.append({"type": "text", "text": line, "marks": []})
        blocks.append({"type": "paragraph", "content": content})
    return {"type": "doc", "content": blocks}


# ---- canonical form and fingerprint --------------------------------------------------

def canonical(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint_v2(title: str, title_is_manual: bool, body: str, doc: dict | None,
                   doc_schema: int | None, projection_version: int | None) -> str:
    canon = json.dumps({"b": body, "m": bool(title_is_manual), "t": title,
                        "d": canonical(doc) if doc is not None else None,
                        "s": doc_schema, "p": projection_version},
                       ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "fp2_" + hashlib.sha256(canon.encode("utf-8")).hexdigest()[:32]


# ---- position maps ---------------------------------------------------------------------

def position_map(doc: dict) -> list:
    """The three coordinate systems side by side. For every text run, hard
    break and synthetic separator in document order: ProseMirror position
    of its start, UTF-16 offset and code-point offset in the projected text,
    and its length in each unit. ProseMirror counts one for each node
    boundary and one per UTF-16 unit of text; a hard break is a node of size
    1; a synthetic separator (the two LF between leaf blocks) occupies no
    ProseMirror position of its own — it stands for the boundary tokens
    between the blocks, which is the bias policy: a text offset inside a
    separator maps to the position just after the block that precedes it."""
    out = []
    pm = 0          # position: 0 is before the first block
    u16 = 0
    cp = 0
    first_leaf = True

    def walk(node, depth):
        nonlocal pm, u16, cp, first_leaf
        t = node.get("type")
        if t in LEAF_BLOCKS:
            if not first_leaf:
                out.append({"kind": "separator", "pm": pm, "utf16": u16, "cp": cp, "len_pm": 0, "len_utf16": 2, "len_cp": 2})
                u16 += 2
                cp += 2
            first_leaf = False
            pm += 1   # into the block
            for n in node.get("content") or []:
                if n.get("type") == "text":
                    s = n["text"]
                    lu = len(s.encode("utf-16-le")) // 2
                    lc = len(s)
                    out.append({"kind": "text", "pm": pm, "utf16": u16, "cp": cp, "len_pm": lu, "len_utf16": lu, "len_cp": lc})
                    pm += lu
                    u16 += lu
                    cp += lc
                elif n.get("type") == "hard_break":
                    out.append({"kind": "hard_break", "pm": pm, "utf16": u16, "cp": cp, "len_pm": 1, "len_utf16": 1, "len_cp": 1})
                    pm += 1
                    u16 += 1
                    cp += 1
            pm += 1   # out of the block
            return
        pm += 1       # into a container
        for k in node.get("content") or []:
            walk(k, depth + 1)
        pm += 1       # out of the container

    for b in doc.get("content") or []:
        walk(b, 0)
    return out


def cp_to_utf16(text: str, cp_offset: int) -> int:
    return len(text[:cp_offset].encode("utf-16-le")) // 2


def utf16_to_cp(text: str, utf16_offset: int) -> int:
    """UTF-16 units to code points; an offset inside a surrogate pair rounds
    down to the pair's start."""
    n = 0
    units = 0
    for ch in text:
        w = 2 if ord(ch) > 0xFFFF else 1
        if units + w > utf16_offset:
            break
        units += w
        n += 1
    return n


def slice_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
