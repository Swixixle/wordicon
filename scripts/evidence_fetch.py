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


def _question_excerpt(rep: dict, question: str, full_text_length: int) -> dict:
    """Lexical window selection only; it makes no relevance judgment.

    Scan overlapping 3,000-character windows across every section. Work is
    bounded by the retrieved body's size and at most 32 question terms.
    Distinct term overlap wins; ties retain the first window in source order.
    """
    if not isinstance(question, str) or not question.strip():
        return {}
    terms = meaningful_terms(question[:2000])[:32]
    if not terms:
        return {}
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(term) for term in terms) + r")(?!\w)", re.I)
    best, best_score = None, 0
    for section in rep["sections"]:
        text = section["text"]
        last_start = max(0, len(text) - QUESTION_EXCERPT_CHARS)
        starts = list(range(0, last_start + 1, QUESTION_EXCERPT_CHARS // 2))
        if not starts or starts[-1] != last_start:
            starts.append(last_start)
        for start in starts:
            excerpt = text[start:start + QUESTION_EXCERPT_CHARS]
            overlap = sorted({match.group(0).casefold() for match in pattern.finditer(excerpt)})
            if len(overlap) > best_score:
                best_score = len(overlap)
                best = {"text": excerpt, "selection_method": "question_term_overlap",
                        "relevance_verified": False,
                        "text_omitted_chars": max(0, full_text_length - len(excerpt)),
                        "excerpt_selection": {"section_path": section["path"], "start": start,
                                              "end": start + len(excerpt), "matched_terms": overlap}}
    return best or {}


def inspect_quote(body: bytes, content_type: str, quote: str, *, question: str = "") -> dict:
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
    """
    import library
    import moira

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
        metadata.update(_question_excerpt(rep, question, len(full_text)))
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
    return {**metadata, "ok": True, "matched": bool(matches),
            "status": best.get("status", "not_found"),
            "extracted_chars": text_length, "match_count": count,
            "matches": matches[:8], **best}
