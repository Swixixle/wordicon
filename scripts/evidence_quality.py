"""Bounded lexical hints for ordering evidence reads and describing excerpts.

These helpers inspect untrusted text as data. They do not fetch, execute,
identify an author, certify a work or decide whether a question was answered.
In particular, keyword overlap must never serve as a completion condition.
No domain earns a bonus or a penalty; URL signals use its path/query only.
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import unquote, urlsplit


VERSION = 3
MAX_TERMS = 128
MAX_TERM_INPUT = 40000
MAX_EXCERPT_INPUT = 200000
MAX_METADATA_FIELD = 8000

# Question scaffolding, navigation and generic work labels are poor evidence
# of conceptual overlap. Keep substantive words such as memory, life, joy,
# beata, vita and gaudium. Roman chapter locators are handled separately.
STOPWORDS = frozenset("""
a an and are as at be been being but by can cannot could did do does doing
done for from had has have having how i if in into is it its itself just me
more most much my myself no nor not of on once only or other our ours
ourselves out own same shall she her hers herself he him his himself should
so some such than that the their theirs them themselves then there these
they this those through to too under until up us very was we were what
whatever when whenever where wherever whether which while who whom whose
why with within without would you your yours yourself yourselves
all any both each either few many neither several ever never always also
already again yet still even else another something anything everything
nothing someone anyone everyone nobody here below above across around
please tell explain explanation describe description discuss question
answer answers ask asked asking want need find found finding search
searches searching result results see show look looking read reading
reads reader chapter chapters book books work works page pages section
sections part parts text texts passage passages quote quotes quotation
quotations source sources excerpt excerpts edition editions volume
volumes author authors title titles link links site website home menu
navigation copyright rights reserved contents content index next
previous back continue click download downloads online available full
complete original primary translation translated translator translations
connect connects connected connecting connection connections relation
relationship relationships related compare comparison between versus
both versus actually specifically particular relevant relevance means
meaning discusses discusses about concerning according referring
refer referred following first second third one two three four five six
seven eight nine ten et al s t d ll ve re m
help helps helped helping understand understands understanding understood
deeply own idea ideas context contexts term terms
""".split())
# The last two lines are the Go deeper question template's own framing
# ("Help me understand X more deeply on its own terms. Explain the idea in
# context..."): in the live Shakuntala records these words were among the
# matched terms steering 3,000-character window selection into reference
# lists and navigation chrome ("help" matched in all four packed excerpts).
# Framing vocabulary is not question substance — same law as explain/describe.
_TOKENS = re.compile(r"[^\W_]+", re.UNICODE)
_ROMAN = re.compile(r"m{0,3}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})$")


def _string(value, limit: int) -> str:
    return value[:limit] if isinstance(value, str) else ""


def _normalized(value: str, limit: int) -> str:
    return unicodedata.normalize("NFKC", _string(value, limit)).casefold()


def _words(value: str, limit: int) -> set[str]:
    return set(_TOKENS.findall(_normalized(value, limit)))


def meaningful_terms(text: str) -> list[str]:
    """Distinct concept tokens, in input order; no stemming or synonym claims."""
    result, seen = [], set()
    for token in _TOKENS.findall(_normalized(text, MAX_TERM_INPUT)):
        if (len(token) < 2 or token.isnumeric() or token in STOPWORDS
                or _ROMAN.fullmatch(token) or token in seen):
            continue
        seen.add(token)
        result.append(token)
        if len(result) >= MAX_TERMS:
            break
    return result


def _url_text(value: str) -> str:
    try:
        parsed = urlsplit(_string(value, MAX_METADATA_FIELD))
    except ValueError:
        return ""
    # Host reputation is deliberately outside this heuristic. Decode once
    # so /beata%20vita and /beata-vita have comparable term signals.
    return unquote(" ".join((parsed.path, parsed.query, parsed.fragment)))[:MAX_METADATA_FIELD]


def _url_route_hints(value: str) -> dict:
    """Inspect bounded URL paths only; page and format hints remain fallible.

    A query mentioning a PDF is not a direct PDF URL. Book routes here are
    deliberately narrow: a numeric show id or ISBN-shaped identifier, not
    every /book/<slug> path. No host, response, or content is consulted.
    """
    try:
        path = unquote(urlsplit(_string(value, MAX_METADATA_FIELD)).path)
    except ValueError:
        path = ""
    path = _normalized(path, MAX_METADATA_FIELD)
    parts = [part for part in path.split("/") if part]
    catalog = []
    for index, part in enumerate(parts):
        if part != "book":
            continue
        following = parts[index + 1:]
        if (len(following) == 2 and following[0] == "show"
                and re.fullmatch(r"[0-9]+(?:[._-][^/]+)?", following[1])):
            catalog.append("book_show_id_path")
        if len(following) == 1:
            # This identifies ISBN-like shapes, not valid registered ISBNs.
            identifier = following[0].replace("-", "")
            if re.fullmatch(r"(?:[0-9]{9}[0-9x]|97[89][0-9]{10})", identifier):
                catalog.append("book_isbn_path")
    # Retail product routes (2026-10-18, the Shakuntala record: an Amazon
    # /dp/<id> page ranked tier 0, score 13, above the actual full text at 8,
    # and spent the pass's first read). URL shape only, same law as
    # /book/show/: no host reputation, and a hint defers, never excludes.
    for index, part in enumerate(parts):
        rest = parts[index + 1:]
        if part == "dp" and rest and re.fullmatch(r"[a-z0-9]{10}", rest[0]):
            catalog.append("retail_product_path")
        if part == "gp" and len(rest) >= 2 and rest[0] == "product" and re.fullmatch(r"[a-z0-9]{10}", rest[1]):
            catalog.append("retail_product_path")
    return {"catalog": list(dict.fromkeys(catalog)),
            "unsupported_format_hint": "pdf" if path.endswith(".pdf") else None}


def _phrase_text(value: str) -> str:
    return " ".join(_TOKENS.findall(_normalized(value, MAX_METADATA_FIELD * 3)))


def _markers(value: str, phrases: tuple[str, ...]) -> list[str]:
    padded = " " + _phrase_text(value) + " "
    return [phrase for phrase in phrases if " " + phrase + " " in padded]


_FULL_TEXT = ("full text", "complete text", "plain text", "source text",
              "original text", "read online", "transcript", "transcription")
_CATALOG = ("audiobook", "audiobooks", "audio book", "audio books", "listen now",
            "listen online", "audio download", "recorded by", "read by volunteers",
            "catalog", "catalogue", "product", "products", "add to cart",
            "buy now", "shopping cart", "purchase", "isbn", "book details")
_ACCESS = ("log in", "login", "sign in", "signin", "subscribe to read",
           "subscription required", "access denied")
# A prose passage may discuss a catalog, a product or a purchase. Those nouns
# alone do not identify its page type. Body hints require media/action/access
# language; title and URL hints can retain the broader ordering vocabulary.
_BODY_CATALOG = tuple(phrase for phrase in _CATALOG if phrase not in {
    "catalog", "catalogue", "product", "products", "purchase", "isbn", "book details"})


def _kind(title: str, url: str, extra: str = "") -> dict:
    metadata = " ".join((_string(title, MAX_METADATA_FIELD), _url_text(url), extra))
    full = _markers(metadata, _FULL_TEXT)
    path_words = _words(_url_text(url), MAX_METADATA_FIELD)
    if path_words & {"text", "texts", "txt", "transcript", "transcription"}:
        full = list(dict.fromkeys(full + ["text_path"]))
    catalog, access = _markers(metadata, _CATALOG), _markers(metadata, _ACCESS)
    route = _url_route_hints(url)
    catalog += route["catalog"]
    # A specific book-listing route survives a title advertising full text.
    # Less specific catalog metadata keeps the pre-existing text preference.
    kind = ("catalog_like" if route["catalog"] else "text_indicated" if full
            else "catalog_like" if catalog or access else "unknown")
    return {"candidate_kind": kind,
            "unsupported_format_hint": route["unsupported_format_hint"],
            "metadata_signals": {"text_indications": full, "catalog_indications": catalog,
                                 "access_indications": access,
                                 "route_catalog_indications": route["catalog"]}}


def _matches(work: str, question: str, haystack: str, limit: int) -> dict:
    work_terms, question_terms = meaningful_terms(work), meaningful_terms(question)
    present = _words(haystack, limit)
    return {"meaningful_question_terms": question_terms,
            "meaningful_work_terms": work_terms,
            "matched_question_terms": [term for term in question_terms if term in present],
            "matched_work_terms": [term for term in work_terms if term in present]}


def rank_candidate(row: dict, *, work: str, question: str) -> dict:
    """Return a retrieval tier, score and signals; caller keeps ties stable.

    Counts are distinct terms, so repeating boilerplate cannot inflate them.
    Known row fields only are used. Snippets are untrusted provider metadata,
    not the document itself and never proof of content or credibility.
    Lower retrieval tiers put possible text before catalog or unsupported
    format hints. Tiers defer reads rather than excluding any candidate.
    """
    row = row if isinstance(row, dict) else {}
    title, url = _string(row.get("title"), MAX_METADATA_FIELD), _string(row.get("url"), MAX_METADATA_FIELD)
    pieces = [_string(row.get(key), MAX_METADATA_FIELD)
              for key in ("snippet", "excerpt", "description", "cited_text")]
    provider_excerpts = row.get("provider_citation_excerpts")
    if isinstance(provider_excerpts, list):
        pieces.extend(_string(item.get("excerpt"), 400)
                      for item in provider_excerpts[:8] if isinstance(item, dict))
    snippet = " ".join(pieces)[:MAX_METADATA_FIELD]
    haystack = " ".join((title, _url_text(url), snippet))
    matches = _matches(work, question, haystack, MAX_METADATA_FIELD * 3 + 2)
    kind = _kind(title, url, snippet)
    # Work identity hints matter to ordering, without establishing identity.
    score = 5 * len(matches["matched_work_terms"]) + 3 * len(matches["matched_question_terms"])
    reason = []
    if matches["matched_work_terms"]:
        reason.append("work_term_overlap")
    if matches["matched_question_terms"]:
        reason.append("question_term_overlap")
    if kind["candidate_kind"] == "text_indicated":
        score += 8
        reason.append("metadata_indicates_text")
    elif kind["candidate_kind"] == "catalog_like":
        score -= 20
        reason.append("metadata_indicates_catalog_or_access_page")
    if kind["metadata_signals"]["route_catalog_indications"]:
        reason.append("url_indicates_book_listing")
    unsupported = kind["unsupported_format_hint"]
    if unsupported:
        reason.append("url_suffix_indicates_unsupported_pdf")
    # An ISBN in the TITLE stays a weak clue (his ruling, 2026-10-18):
    # catalog listings print ISBNs, but legitimate full-text pages can too,
    # so it nudges the score and never moves the tier or the kind.
    if re.search(r"(?<![0-9])(?:97[89][-\s]?(?:[0-9][-\s]?){9}[0-9]|(?:[0-9][-\s]?){9}[0-9xX])(?![0-9])", title):
        score -= 4
        reason.append("isbn_in_title_weak_catalog_clue")
    retrieval_tier = 2 if unsupported else 1 if kind["candidate_kind"] == "catalog_like" else 0
    if not reason:
        reason.append("no_ordering_signal")
    return {"version": VERSION, "retrieval_tier": retrieval_tier, "score": score, **matches, **kind,
            "reason": reason, "relevance_verified": False}


def assess_excerpt(text: str, *, work: str, question: str, title: str = "", url: str = "") -> dict:
    """Describe lexical overlap and landing-page hints; never certify success.

    Matched terms here must occur in the supplied extracted text, rather than
    merely its URL/title. `weak` is a queue/grounding hint, not an irrelevance
    finding. A relevant translation may share no literal question terms.
    """
    bounded = _string(text, MAX_EXCERPT_INPUT)
    matches = _matches(work, question, bounded, MAX_EXCERPT_INPUT)
    # Text itself can expose a catalog/login page even when metadata did not.
    # Inspect only the first bounded portion for page-kind hints, to prevent
    # this classification step from expanding with a large document.
    kind = _kind(title, url)
    body_catalog = _markers(bounded[:MAX_METADATA_FIELD], _BODY_CATALOG)
    body_access = _markers(bounded[:MAX_METADATA_FIELD], _ACCESS)
    body_full = _markers(bounded[:MAX_METADATA_FIELD],
                         tuple(phrase for phrase in _FULL_TEXT if phrase != "read online"))
    kind["metadata_signals"]["catalog_indications"] = list(dict.fromkeys(
        kind["metadata_signals"]["catalog_indications"] + body_catalog))
    kind["metadata_signals"]["access_indications"] = list(dict.fromkeys(
        kind["metadata_signals"]["access_indications"] + body_access))
    catalog_signals = (kind["metadata_signals"]["catalog_indications"]
                       or kind["metadata_signals"]["access_indications"])
    # A URL/title advertising "full text" cannot cancel catalog evidence in
    # the actual page. Even an explicit body marker remains only a hint.
    if catalog_signals and not body_full:
        kind["candidate_kind"] = "catalog_like"
    elif body_full:
        kind["candidate_kind"] = "text_indicated"
    kind["metadata_signals"]["body_text_indications"] = body_full
    kind["metadata_signals"]["body_catalog_indications"] = body_catalog
    kind["metadata_signals"]["body_access_indications"] = body_access
    weak = not matches["matched_question_terms"] or kind["candidate_kind"] == "catalog_like"
    reason = []
    if not matches["meaningful_question_terms"]:
        reason.append("question_has_no_meaningful_terms")
    elif not matches["matched_question_terms"]:
        reason.append("no_meaningful_question_overlap")
    else:
        reason.append("meaningful_question_overlap_only")
    if matches["matched_work_terms"]:
        reason.append("work_terms_present_only")
    if kind["candidate_kind"] == "catalog_like":
        reason.append("catalog_or_access_page_signals")
    if isinstance(text, str) and len(bounded) < len(text):
        reason.append("assessment_input_truncated")
    return {"version": VERSION, **matches, **kind, "weak": weak,
            "reason": reason, "relevance_verified": False,
            "assessed_characters": len(bounded)}
