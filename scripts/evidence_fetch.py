"""Bounded public text retrieval and mechanical quotation checks.

fetch_public(url) performs credential-free GETs only. Every redirect is
validated anew; all resolved addresses must be public and the connection
uses one of those exact addresses (TLS still verifies the original host).
It returns bytes, never executes a page, and makes no model or store calls.

inspect_quote(body, content_type, quote) derives text with the Library's
versioned extractor and locates the quotation using Moira's exact/normalized
matcher. Offsets address that extracted section, NOT the original HTML.
Located text establishes presence in those bytes, not authorship or truth.
Neither function admits anything into the Library or changes a source ruling.
"""
from __future__ import annotations

import hashlib
import html.parser
import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
from urllib.parse import quote as urlquote, urljoin, urlsplit, urlunsplit
from evidence_quality import meaningful_terms

MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
SOCKET_TIMEOUT_S = 10
TOTAL_TIMEOUT_S = 30
TEXT_TYPES = {"text/html", "application/xhtml+xml", "text/plain"}
REDIRECT_CODES = {301, 302, 303, 307, 308}
MAX_GROUNDING_CHARS = 12000
QUESTION_EXCERPT_CHARS = 3000
MAX_PASSAGES_PER_INSPECTION = 8


class FetchRefused(ValueError):
    def __init__(self, outcome: str, detail: str):
        super().__init__(detail)
        self.outcome = outcome


def _public_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        return (address.is_global and not address.is_multicast
                and not address.is_reserved and not address.is_unspecified
                and not address.is_loopback and not address.is_link_local
                and not address.is_private and not getattr(address, "is_site_local", False))
    except ValueError:
        return False


def _url(value: str) -> tuple[str, str, str, int, str]:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise FetchRefused("invalid_url", "A bounded absolute public URL is required.")
    if any(ord(c) < 33 or ord(c) == 127 or c in '\\<>"' for c in value):
        raise FetchRefused("invalid_url", "Whitespace, controls and ambiguous URL characters are refused.")
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise ValueError("scheme or host")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("credentials")
        host = parsed.hostname.encode("idna").decode("ascii").lower()
        if "%" in host:
            raise ValueError("scoped or escaped host")
        scheme = parsed.scheme.lower()
        port = parsed.port or (443 if scheme == "https" else 80)
        if port != (443 if scheme == "https" else 80):
            raise ValueError("nondefault port")
        if parsed.port == 0:
            raise ValueError("zero port")
    except (ValueError, UnicodeError) as exc:
        raise FetchRefused("invalid_url", "Only HTTP/HTTPS default ports without credentials are allowed.") from exc
    path = urlquote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~")
    query = urlquote(parsed.query, safe="/%?:@!$&'()*+,;=-._~")
    netloc = f"[{host}]" if ":" in host else host
    normalized = urlunsplit((scheme, netloc, path, query, ""))
    target = path + ("?" + query if query else "")
    return normalized, scheme, host, port, target


def _resolve_public(host: str, port: int) -> tuple:
    """Reject mixed public/private answers as a whole; never resolve at connect."""
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses:
        raise FetchRefused("dns_failure", "The source hostname returned no addresses.")
    for family, socktype, protocol, _name, sockaddr in addresses:
        if family not in {socket.AF_INET, socket.AF_INET6} or not _public_ip(sockaddr[0]):
            raise FetchRefused("non_public_address", "The source resolves to a non-public or mixed address set.")
        if family == socket.AF_INET6 and (len(sockaddr) < 4 or sockaddr[3] != 0):
            raise FetchRefused("non_public_address", "Scoped network addresses are refused.")
    return addresses[0]


def _connect_address(address: tuple, timeout: float):
    family, socktype, protocol, _name, sockaddr = address
    sock = socket.socket(family, socktype, protocol)
    try:
        sock.settimeout(timeout)
        sock.connect(sockaddr)
        return sock
    except BaseException:
        sock.close()
        raise


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host, port, address, timeout):
        super().__init__(host, port=port, timeout=timeout)
        self.address = address

    def connect(self):
        self.sock = _connect_address(self.address, self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, port, address, timeout):
        super().__init__(host, port=port, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        raw = _connect_address(self.address, self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def _new_connection(scheme, host, port, address, timeout):
    cls = _PinnedHTTPSConnection if scheme == "https" else _PinnedHTTPConnection
    return cls(host, port, address, timeout)


def fetch_public(url: str) -> dict:
    """Return {ok, status, final_url, content_type, body} or a named failure.

    Only HTML/plain text is supported in v1. Redirect history is retained on
    success and failure. HTTP error pages and unsupported encodings are never
    passed off as retrieved works. Socket timeouts apply to DNS-independent
    connection/read operations; DNS uses the host resolver's own timeout.
    """
    current, redirects, seen = url, [], set()
    status, ctype = None, ""
    deadline = time.monotonic() + TOTAL_TIMEOUT_S
    try:
        for hop in range(MAX_REDIRECTS + 1):
            # Status belongs to this hop. An unsafe redirect target has
            # no HTTP response; the prior 30x lives only in redirect history.
            status, ctype = None, ""
            current, scheme, host, port, target = _url(current)
            if current in seen:
                raise FetchRefused("redirect_loop", "The source redirected to an already attempted URL.")
            seen.add(current)
            address = _resolve_public(host, port)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            conn = _new_connection(scheme, host, port, address, min(SOCKET_TIMEOUT_S, remaining))
            try:
                # http.client ignores proxy env vars; no Cookie/Authorization
                # header or browser session ever enters this connection.
                conn.request("GET", target, headers={
                    "Accept": "text/html, application/xhtml+xml, text/plain",
                    "Accept-Encoding": "identity", "Connection": "close",
                    "User-Agent": "Nikodemus-evidence/1"})
                response = conn.getresponse()
                status = response.status
                ctype = (response.getheader("Content-Type") or "").split(";", 1)[0].strip().lower()
                if status in REDIRECT_CODES:
                    location = response.getheader("Location")
                    if not location:
                        raise FetchRefused("redirect_without_location", "The source supplied no redirect destination.")
                    destination = urljoin(current, location)
                    redirects.append({"url": current, "status": status, "location": destination})
                    if hop >= MAX_REDIRECTS:
                        raise FetchRefused("redirect_limit", "The source exceeded the disclosed redirect limit.")
                    current = destination
                    continue
                if status != 200:
                    outcome = ("authentication_required" if status == 401 else
                               "access_denied" if status == 403 else
                               "rate_limited" if status == 429 else
                               "not_found" if status == 404 else "http_error")
                    raise FetchRefused(outcome, f"The source returned HTTP {status}.")
                if ctype not in TEXT_TYPES:
                    raise FetchRefused("unsupported_content_type", "Only public HTML and plain text can be read by this adapter.")
                encoding = (response.getheader("Content-Encoding") or "identity").strip().lower()
                if encoding != "identity":
                    raise FetchRefused("unsupported_encoding", "The source did not honor the uncompressed text request.")
                length = response.getheader("Content-Length")
                if length is not None:
                    try:
                        length = int(length)
                    except ValueError as exc:
                        raise FetchRefused("invalid_content_length", "The source supplied an invalid body length.") from exc
                    if length < 0:
                        raise FetchRefused("invalid_content_length", "The source supplied an invalid body length.")
                    if length > MAX_BYTES:
                        raise FetchRefused("oversized", "The source exceeds the 2 MiB read limit.")
                chunks, total = [], 0
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError()
                    if conn.sock is not None:
                        conn.sock.settimeout(min(SOCKET_TIMEOUT_S, remaining))
                    # read1 performs at most one underlying buffered read;
                    # a slowly trickling body cannot reset our total deadline.
                    chunk = response.read1(min(65536, MAX_BYTES + 1 - total))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise FetchRefused("oversized", "The source exceeds the 2 MiB read limit.")
                body = b"".join(chunks)
                if length is not None and len(body) != length:
                    raise FetchRefused("incomplete_body", "The source ended before its declared body length.")
                return {"ok": True, "status": status, "final_url": current,
                        "content_type": ctype, "body": body, "redirects": redirects,
                        "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
            finally:
                conn.close()
    except FetchRefused as exc:
        outcome, detail = exc.outcome, str(exc)
    except socket.gaierror:
        outcome, detail = "dns_failure", "The source hostname could not be resolved."
    except ssl.SSLError:
        outcome, detail = "tls_failure", "The source did not establish a verified TLS connection."
    except (TimeoutError, socket.timeout):
        outcome, detail = "timeout", "The public source read exceeded its time allowance."
    except (OSError, http.client.HTTPException, ValueError):
        outcome, detail = "connection_failure", "The public source connection did not complete."
    return {"ok": False, "outcome": outcome, "detail": detail,
            "status": status, "final_url": current, "content_type": ctype,
            "redirects": redirects}


class _PageFeatures(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.password = False
        self.scripts = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.password |= tag == "input" and str(attrs.get("type", "")).lower() == "password"
        self.scripts |= tag == "script"


def _binary_kind(body: bytes) -> str:
    """MIME is a source's claim; recognizable binary bytes take precedence."""
    head = body[:1024].lstrip()
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08", b"\x1f\x8b",
                        b"Rar!\x1a\x07", b"7z\xbc\xaf\x27\x1c")):
        return "archive"
    if head.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a",
                        b"II\x2a\x00", b"MM\x00\x2a", b"RIFF")):
        return "image_or_media"
    # This adapter has no UTF-16/32 decoder. Do not let binary strings or
    # unsupported wide-character encodings masquerade as ordinary text.
    if b"\x00" in body:
        return "binary_or_unsupported_encoding"
    return ""


def _span_overlap(start: int, end: int, spans) -> bool:
    """True when [start, end) shares at least half its length with any span."""
    length = max(1, end - start)
    for span in spans or ():
        s, e = span
        shared = min(end, e) - max(start, s)
        if shared * 2 >= length:
            return True
    return False


def _question_excerpt(rep: dict, question: str, full_text_length: int, exclude_spans=None) -> dict:
    """Lexical window selection only; it makes no relevance judgment.

    Scan overlapping 3,000-character windows across every section. Work is
    bounded by the retrieved body's size and at most 32 question terms.
    Distinct term overlap wins; ties retain the first window in source order.

    Revision five (2026-10-18, the Shakuntala record): a continuation that
    reuses a saved full text must ADVANCE through it, not re-show the model
    the same window — the deployed record held Ryder's Act IV and Act VI in
    custody while the same Act I window was packed twice. `exclude_spans`
    maps a section path to the (start, end) windows already shown to the
    model for this text; a window sharing at least half its length with one
    is passed over when any unshown window still matches. When ONLY
    already-shown windows match, the best of them is reselected and the
    selection says so by name — advancement never hides the fallback.
    """
    if not isinstance(question, str) or not question.strip():
        return {}
    terms = meaningful_terms(question[:2000])[:32]
    if not terms:
        return {}
    exclude_spans = exclude_spans or {}
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(term) for term in terms) + r")(?!\w)", re.I)
    best, best_score = None, 0                 # best among windows NOT yet shown
    shown_best, shown_best_score = None, 0     # best among already-shown windows
    excluded_hits = 0
    for section in rep["sections"]:
        text = section["text"]
        section_spans = exclude_spans.get(section["path"]) or ()
        last_start = max(0, len(text) - QUESTION_EXCERPT_CHARS)
        starts = list(range(0, last_start + 1, QUESTION_EXCERPT_CHARS // 2))
        if not starts or starts[-1] != last_start:
            starts.append(last_start)
        for start in starts:
            excerpt = text[start:start + QUESTION_EXCERPT_CHARS]
            overlap = sorted({match.group(0).casefold() for match in pattern.finditer(excerpt)})
            if not overlap:
                continue
            candidate = {"text": excerpt, "selection_method": "question_term_overlap",
                         "relevance_verified": False,
                         "text_omitted_chars": max(0, full_text_length - len(excerpt)),
                         "excerpt_selection": {"section_path": section["path"], "start": start,
                                               "end": start + len(excerpt), "matched_terms": overlap}}
            if _span_overlap(start, start + len(excerpt), section_spans):
                excluded_hits += 1
                if len(overlap) > shown_best_score:
                    shown_best_score = len(overlap)
                    shown_best = candidate
                continue
            if len(overlap) > best_score:
                best_score = len(overlap)
                best = candidate
    if best is not None:
        if excluded_hits:
            best["excerpt_selection"]["advanced_past_shown_windows"] = excluded_hits
        return best
    if shown_best is not None:
        shown_best["excerpt_selection"]["reselected_previously_shown_window"] = True
        return shown_best
    return {}


_NUMBERED_DIVISION = re.compile(
    r"^(?:act|chapter|book|part|canto|section)\s+"
    r"(?:[ivxlcdm]+|\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b", re.I)


def _passage_regions(section: dict) -> list[dict]:
    """Locate printed divisions without changing the Library representation.

    HTML headings and short numbered division labels supply reading diversity,
    not verified work identity. A prose paragraph beginning 'Act IV ...' is not
    a heading merely because it mentions an act. Offsets remain addresses in the
    original extracted section, even when that section contains a whole book.
    """
    text = section["text"]
    boundaries = [{"start": 0, "heading": section.get("heading", ""),
                   "numbered_division": False}]
    for para in section.get("paragraphs", []):
        sentences = [s for s in para.get("sentences", []) if s.get("start", -1) >= 0]
        if not sentences:
            continue
        start = text.rfind("\n", 0, sentences[0]["start"]) + 1
        end = text.find("\n", start)
        line = text[start:end if end >= 0 else len(text)].strip()
        numbered = (bool(_NUMBERED_DIVISION.match(line)) and len(line) <= 160
                    and not re.search(r"[.!?;]", line))
        is_heading = bool(re.fullmatch(r"h[1-6]", para.get("tag", "")))
        if not line or not (is_heading or numbered):
            continue
        boundary = {"start": start, "heading": line[:240],
                    "numbered_division": numbered}
        if start == boundaries[-1]["start"]:
            boundaries[-1] = boundary
        elif start > boundaries[-1]["start"]:
            boundaries.append(boundary)
    return [{**boundary, "end": (boundaries[i + 1]["start"]
                                if i + 1 < len(boundaries) else len(text))}
            for i, boundary in enumerate(boundaries)]


def _question_passages(rep: dict, question: str, passage_limit: int,
                       exclude_spans=None) -> list[dict]:
    """Select distinct lexical passages, spreading a read across a whole work.

    One best window per printed division is considered before a second window
    from a division. Among equally complete question-term matches, numbered
    divisions precede other sections; rarer question terms carry more weight
    than frequent names when selecting a passage within a division. This
    is a disclosed lexical heuristic, never a finding that the text is relevant
    or that a question has been answered. Already shown windows are bypassed as
    in r5; fallback to one shown window is explicit when no new match remains.
    """
    if not isinstance(question, str) or not question.strip():
        return []
    terms = meaningful_terms(question[:2000])[:32]
    if not terms:
        return []
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(t) for t in terms) + r")(?!\w)", re.I)
    counts = {term: 0 for term in terms}
    for section in rep["sections"]:
        for match in pattern.finditer(section["text"]):
            term = match.group(0).casefold()
            counts[term] = counts.get(term, 0) + 1
    exclude_spans = exclude_spans or {}
    candidates, shown, excluded_hits = [], [], 0
    for section_index, section in enumerate(rep["sections"]):
        text = section["text"]
        section_hash = hashlib.sha256(text.encode()).hexdigest()
        for region in _passage_regions(section):
            first, stop = region["start"], region["end"]
            last = max(first, stop - QUESTION_EXCERPT_CHARS)
            starts = set(range(first, last + 1, QUESTION_EXCERPT_CHARS // 2))
            starts.add(last)
            # Term-centered candidates prevent the fixed stride from clipping
            # a cluster just across a window edge. Quantization bounds the total
            # candidates by body size, even on highly repetitive pages.
            for hit in pattern.finditer(text, first, stop):
                for proposed in (hit.start() - 250, hit.end() + 250 - QUESTION_EXCERPT_CHARS):
                    start = first + ((proposed - first) // 250) * 250
                    starts.add(min(last, max(first, start)))
            starts = sorted(starts)
            for start in starts:
                end = min(start + QUESTION_EXCERPT_CHARS, stop)
                excerpt = text[start:end]
                raw_hits = list(pattern.finditer(excerpt))
                if not raw_hits:
                    continue
                # Center on the rarer topic term(s), leaving context on both
                # sides. Otherwise repeated names can push the topic sentence
                # against the end of a window and hide its immediate reply.
                rare_count = min(counts[hit.group(0).casefold()] for hit in raw_hits)
                anchors = [hit for hit in raw_hits if counts[hit.group(0).casefold()] == rare_count]
                center = start + (anchors[0].start() + anchors[-1].end()) // 2
                start = min(last, max(first, center - QUESTION_EXCERPT_CHARS // 2))
                end = min(start + QUESTION_EXCERPT_CHARS, stop)
                excerpt = text[start:end]
                hits = [match.group(0).casefold() for match in pattern.finditer(excerpt)]
                matched = sorted(set(hits))
                if not matched:
                    continue
                selection = {"section_path": section["path"], "start": start, "end": end,
                             "matched_terms": matched, "heading": region["heading"]}
                passage = {"text": excerpt, "excerpt_selection": selection,
                           "text_sha256": hashlib.sha256(excerpt.encode()).hexdigest(),
                           "section_sha256": section_hash,
                           "selection_method": "question_terms_across_divisions",
                           "relevance_verified": False}
                # A repeated protagonist's name must not swamp the rarer topic
                # word. Capped inverse-frequency overlap is lexical only; it
                # does not imply that this passage answers the question.
                score = (len(matched), int(region["numbered_division"]),
                         sum(min(8, hits.count(term)) / counts[term] for term in matched),
                         -section_index, -start)
                candidate = (score, (section["path"], first), passage)
                if _span_overlap(start, end, exclude_spans.get(section["path"], ())):
                    excluded_hits += 1
                    shown.append(candidate)
                else:
                    candidates.append(candidate)
    candidates.sort(key=lambda candidate: candidate[0], reverse=True)
    selected, selected_regions, selected_spans = [], set(), {}
    for distinct_regions in (True, False):
        for _score, region_id, passage in candidates:
            location = passage["excerpt_selection"]
            path, start, end = location["section_path"], location["start"], location["end"]
            if distinct_regions and region_id in selected_regions:
                continue
            # Within a single inspection, no character is offered twice. The
            # half-window rule above is retained only for prior shown spans.
            if any(min(end, previous_end) > max(start, previous_start)
                   for previous_start, previous_end in selected_spans.get(path, ())):
                continue
            if excluded_hits:
                location["advanced_past_shown_windows"] = excluded_hits
            selected.append(passage)
            selected_regions.add(region_id)
            selected_spans.setdefault(path, []).append((start, end))
            if len(selected) >= passage_limit:
                return selected
    if not selected and shown:
        fallback = max(shown, key=lambda candidate: candidate[0])[2]
        fallback["excerpt_selection"]["reselected_previously_shown_window"] = True
        selected.append(fallback)
    return selected


def _replay_passages(rep: dict, requested: list[dict], representation_sha256: str) -> list[dict]:
    """Resolve a failed answer's recorded input without selecting new passages."""
    if not isinstance(requested, list) or not 1 <= len(requested) <= MAX_PASSAGES_PER_INSPECTION:
        raise ValueError("A bounded nonempty passage manifest is required.")
    sections = {section["path"]: section for section in rep["sections"]}
    passages = []
    for descriptor in requested:
        if not isinstance(descriptor, dict):
            raise ValueError("A passage descriptor is malformed.")
        if not isinstance(descriptor.get("section_path"), str):
            raise ValueError("A passage section is malformed.")
        if (descriptor.get("representation_sha256")
                and descriptor["representation_sha256"] != representation_sha256):
            raise ValueError("The passage representation no longer matches.")
        section = sections.get(descriptor.get("section_path"))
        start, end = descriptor.get("start"), descriptor.get("end")
        if (section is None or type(start) is not int or type(end) is not int
                or not 0 <= start < end <= len(section["text"])
                or end - start > QUESTION_EXCERPT_CHARS):
            raise ValueError("A passage location no longer resolves.")
        text = section["text"][start:end]
        digest = hashlib.sha256(text.encode()).hexdigest()
        section_digest = hashlib.sha256(section["text"].encode()).hexdigest()
        if ((descriptor.get("text_sha256") and descriptor["text_sha256"] != digest)
                or (descriptor.get("section_sha256") and descriptor["section_sha256"] != section_digest)):
            raise ValueError("A passage hash no longer matches.")
        heading = section.get("heading", "")
        for region in _passage_regions(section):
            if region["start"] <= start < region["end"]:
                heading = region["heading"]
                break
        passages.append({"text": text, "text_sha256": digest,
                         "section_sha256": section_digest,
                         "selection_method": "replayed_answer_input", "relevance_verified": False,
                         "excerpt_selection": {"section_path": section["path"], "start": start,
                                               "end": end, "heading": heading,
                                               "replayed_answer_input": True}})
    return passages


def inspect_quote(body: bytes, content_type: str, quote: str, *, question: str = "", exclude_spans=None,
                  passage_limit: int | None = None, requested_passages=None) -> dict:
    """Locate a quote in a pure derivative; return offsets and exact kept text.

    `ok` means text extraction succeeded, `matched` means located. The status
    is exact, normalized, not_found, or a named extraction failure. `text`
    contains the first 12,000 extracted characters by default. For unmatched
    or absent quotations, an optional question selects a <=3,000-character
    lexical-overlap window from the complete representation. This is labeled
    selection, never relevance verification; omitted length is always stated.
    `representation_sha256` hashes the versioned representation with its
    nondeterministic created_at omitted. Repeated
    matches are counted; up to eight section matches are described. A title
    is page-supplied metadata and is never promoted to a work identity.
    With `passage_limit`, unmatched reads additionally expose that many distinct
    <=3,000-character `passages`, selected across printed divisions. Each carries
    its own location and hashes. The top-level r5 excerpt remains compatible.
    Exact/normalized quotation matches retain their existing path unchanged.
    For an answer-only retry without a quote, `requested_passages` replays exact
    ranges from its prior answer-input manifest. Invalid locations/hashes fail
    by name instead of silently replacing the material the answer was using.
    """
    import library
    import moira

    if passage_limit is not None and (type(passage_limit) is not int
                                      or not 1 <= passage_limit <= MAX_PASSAGES_PER_INSPECTION):
        raise ValueError(f"passage_limit must be between 1 and {MAX_PASSAGES_PER_INSPECTION}")
    if not isinstance(body, bytes) or len(body) > MAX_BYTES:
        return {"ok": False, "matched": False, "status": "invalid_body"}
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime not in TEXT_TYPES:
        return {"ok": False, "matched": False, "status": "unsupported_content_type"}
    digest = hashlib.sha256(body).hexdigest()
    metadata = {"sha256": digest, "body_sha256": digest, "bytes": len(body),
                "verified": False, "source_admitted": False,
                "standing": "Text presence only; no finding about authorship, attribution or truth."}
    binary_kind = _binary_kind(body)
    if binary_kind:
        return {**metadata, "ok": False, "matched": False,
                "status": "unsupported_binary_content", "detected_kind": binary_kind}
    kind = "txt" if mime == "text/plain" else "html"
    features = _PageFeatures()
    if kind == "html":
        features.feed(body.decode("utf-8", errors="replace"))
        if features.password:
            return {**metadata, "ok": False, "matched": False, "status": "login_required"}
    try:
        rep = library.build_representation(digest, kind, body)
    except (ValueError, UnicodeError) as exc:
        return {**metadata, "ok": False, "matched": False,
                "status": "extraction_failed", "exception": type(exc).__name__}
    metadata.update({"representation_id": rep["representation_id"],
                     "extractor": rep["extractor"], "segmenter_rev": rep["segmenter_rev"],
                     "findings": rep["findings"], "page_title": rep["title"]})
    canonical_rep = {key: value for key, value in rep.items() if key != "created_at"}
    full_text = "\n\n".join(sec["text"] for sec in rep["sections"])
    metadata.update({
        "representation_sha256": hashlib.sha256(json.dumps(
            canonical_rep, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "text": full_text[:MAX_GROUNDING_CHARS],
        "text_omitted_chars": max(0, len(full_text) - MAX_GROUNDING_CHARS),
        "selection_method": "opening_excerpt", "relevance_verified": False,
        "extracted_text_sha256": hashlib.sha256(full_text.encode()).hexdigest(),
    })
    text_length = sum(len(sec["text"].strip()) for sec in rep["sections"])
    if not text_length:
        return {**metadata, "ok": False, "matched": False,
                "status": "javascript_required" if features.scripts else "no_extractable_text"}
    if not isinstance(quote, str) or not quote.strip():
        metadata.update(_question_excerpt(rep, question, len(full_text), exclude_spans=exclude_spans))
        if requested_passages is not None:
            try:
                metadata["passages"] = _replay_passages(
                    rep, requested_passages, metadata["representation_sha256"])
            except ValueError as exc:
                return {**metadata, "ok": False, "matched": False,
                        "status": "passage_replay_mismatch", "passages": [], "detail": str(exc)}
        elif passage_limit is not None:
            metadata["passages"] = _question_passages(rep, question, passage_limit, exclude_spans)
        return {**metadata, "ok": True, "matched": False, "status": "no_quote",
                "extracted_chars": text_length}
    matches = []
    count = 0
    for sec in rep["sections"]:
        found = moira.locate(sec["text"], quote)
        if found["status"] == "not_found":
            continue
        start, end = found["start"], found["end"]
        count += found["n"]
        text = sec["text"][start:end]
        matches.append({"status": found["status"], "section_path": sec["path"],
                        "heading": sec["heading"], "start": start, "end": end,
                        "matched_text": text, "exact_text": text,
                        "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "section_sha256": hashlib.sha256(sec["text"].encode()).hexdigest(),
                        "excerpt": sec["text"][max(0, start - 250):end + 250],
                        "occurrences_in_section": found["n"]})
    matches.sort(key=lambda hit: hit["status"] != "exact")
    best = matches[0] if matches else {}
    if not matches:
        metadata.update(_question_excerpt(rep, question, len(full_text)))
        if passage_limit is not None:
            metadata["passages"] = _question_passages(rep, question, passage_limit, exclude_spans)
    return {**metadata, "ok": True, "matched": bool(matches),
            "status": best.get("status", "not_found"),
            "extracted_chars": text_length, "match_count": count,
            "matches": matches[:8], **best}
