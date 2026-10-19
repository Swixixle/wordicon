"""Endpoint identity, because an endpoint is an object and not a string.

An edge endpoint may be `{kind, key, label}` or
`{kind, key, label, concept_id}`. A `carries` endpoint can be shaped
differently again: `{kind, ref, trace_id}` on one side and
`{draft, source_key}` on the other. A reader that treats any of these as a
string crashes, and one that treats them as interchangeable is wrong in a
quieter way.

So identity is computed here, once, with three rules:

  1. The stable identity is the store's own key — `key` for an edge endpoint,
     `ref`/`source_key` for a carry. It is a string, so it can be grouped.
  2. `concept_id` travels ALONGSIDE the key, never instead of it. Two
     endpoints sharing a key while carrying different concept ids are a
     candidate identity assertion, not an automatic merge.
  3. An endpoint that cannot be identified returns `None` and a stated
     reason. It is reported as an identity gap, never bucketed under a
     fallback key that would silently group unrelated records.
"""
from __future__ import annotations

SCHEMA = "nikodemus.work_history.endpoints.v1"

# Which field carries the stable key, per family and side. Ordered: the first
# present wins, so a new variant that adds a better key is picked up without
# losing the old one.
KEY_FIELDS = {
    "edges": ("key",),
    # A carry source's `ref` is an object — {concept_id, field, title} or
    # {index, title, work} — with no stable key inside it, so identifying a
    # carry source by `ref` identified nothing at all (found by review,
    # 2026-10-18). The trace_id is the stable part; the ref is recorded as a
    # sub-locator beside it rather than squeezed into an identity.
    "carries.source": ("trace_id",),
    "carries.target": ("source_key",),
}


def identify(value, family="edges", side=None):
    """Return {identity, kind, label, concept_id, shape, reason}.

    `identity` is a string or None. Never raises on an unexpected value: an
    endpoint shape nobody has seen before is an identity gap with its shape
    recorded, which is a fact a reader can report.
    """
    lookup = f"{family}.{side}" if side and f"{family}.{side}" in KEY_FIELDS else family
    fields = KEY_FIELDS.get(lookup, ("key",))
    if value is None:
        return {"identity": None, "kind": None, "label": None, "concept_id": None,
                "sub_locator": None, "shape": "absent",
                "reason": "the row carries no endpoint on this side"}
    if isinstance(value, str):
        # Legacy and fixture rows. A bare string is its own key, and saying so
        # is honest: it is not evidence that the store still writes strings.
        return {"identity": value or None, "kind": None, "label": None,
                "concept_id": None, "sub_locator": None, "shape": "str",
                "reason": "" if value else "the endpoint string is empty"}
    if not isinstance(value, dict):
        return {"identity": None, "kind": None, "label": None, "concept_id": None,
                "sub_locator": None, "shape": type(value).__name__,
                "reason": f"an endpoint of type {type(value).__name__} is not one this "
                          f"reader can identify"}
    shape = "dict{" + ",".join(sorted(value)) + "}"
    identity = None
    for field in fields:
        if isinstance(value.get(field), str) and value[field]:
            identity = value[field]
            break
    reason = ""
    if identity is None:
        reason = (f"no key field present; this reader identifies a {lookup} endpoint by "
                  f"{' or '.join(fields)}")
    concept = value.get("concept_id")
    if concept is not None and not isinstance(concept, str):
        # A concept id that is not a string cannot be grouped or compared, and
        # putting it in a set raised TypeError before this check existed.
        return {"identity": identity, "kind": value.get("kind"),
                "label": value.get("label"), "concept_id": None,
                "sub_locator": None, "shape": shape,
                "reason": f"concept_id has shape {type(concept).__name__}, which this reader "
                          f"cannot use as an identifier"}
    sub = value.get("ref")
    return {"identity": identity, "kind": value.get("kind"), "label": value.get("label"),
            "concept_id": concept,
            "sub_locator": sub if isinstance(sub, (dict, str)) else None,
            "shape": shape, "reason": reason}


def declaring_producer(value):
    """Identify the record that declared an edge.

    A producer may be a reference object with {kind, id} or
    {kind, id, stage}. A reader that drops it
    into a `declared_by` string field puts a dict there, which is how this
    went unnoticed until the typed shape check found it. Returns None when no
    producer is recorded; an absent producer leaves the edge's basis unknown.
    """
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return {"identity": value, "kind": None, "stage": None, "shape": "str",
                "reason": ""}
    if not isinstance(value, dict):
        return {"identity": None, "kind": None, "stage": None,
                "shape": type(value).__name__,
                "reason": f"a producer of type {type(value).__name__} is not one this "
                          f"reader can identify"}
    shape = "dict{" + ",".join(sorted(value)) + "}"
    identity = value.get("id") if isinstance(value.get("id"), str) else None
    return {"identity": identity, "kind": value.get("kind"), "stage": value.get("stage"),
            "shape": shape,
            "reason": "" if identity else "no id field; this reader identifies a declaring "
                                          "producer by its id"}


def same_key_different_concept(endpoints):
    """Endpoints that share a key while carrying different concept ids.

    Returned for reporting as a candidate identity question, not resolved
    here: deciding whether two records are the same thing is an assertion
    with evidence, and this module has none.
    """
    by_key = {}
    for endpoint in endpoints:
        identity, concept = endpoint.get("identity"), endpoint.get("concept_id")
        if not identity or (concept is not None and not isinstance(concept, str)):
            continue
        by_key.setdefault(identity, set()).add(concept)
    return {key: sorted(concepts, key=lambda value: (value is None, value))
            for key, concepts in sorted(by_key.items())
            if len({concept for concept in concepts if concept}) > 1}
