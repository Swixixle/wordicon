"""Public evidence retrieval: no real network, and no model or corpus writes."""
from __future__ import annotations

import hashlib
import io
import socket
import ssl
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import evidence_fetch as ef
import library
import wordicon_cli as cli


def addr(ip="8.8.8.8", port=443):
    if ":" in ip:
        return (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port, 0, 0))
    return (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port))


class Response:
    def __init__(self, body=b"<p>A retained primary passage.</p>", status=200, headers=None):
        self.status = status
        self.headers = {"Content-Type": "text/html", **(headers or {})}
        self.stream = io.BytesIO(body)

    def getheader(self, key):
        return self.headers.get(key)

    def read1(self, size):
        return self.stream.read(size)


@pytest.fixture
def network(monkeypatch):
    calls, responses = [], []
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, **kwargs: [addr(port=port)])

    class Connection:
        sock = None

        def __init__(self, scheme, host, port, address, timeout):
            self.call = {"scheme": scheme, "host": host, "port": port, "address": address,
                         "timeout": timeout, "closed": False}
            calls.append(self.call)

        def request(self, method, target, headers):
            self.call.update(method=method, target=target, headers=headers)

        def getresponse(self):
            return responses.pop(0)

        def close(self):
            self.call["closed"] = True

    monkeypatch.setattr(ef, "_new_connection", Connection)
    return calls, responses


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://example.org/work", "https://owner:secret@example.org/",
    "https://owner@example.org/", "https://example.org:8443/", "http://example.org:443/",
    "https://example.org:0/", "https://example.org/\nother", "https://example.org\\@localhost/",
    "http://[fe80::1%25eth0]/", "https://", "", None,
])
def test_invalid_urls_never_resolve_or_connect(url, monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: pytest.fail("must not resolve"))
    assert ef.fetch_public(url)["outcome"] == "invalid_url"


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.1", "172.16.2.3", "192.168.1.1",
                                   "169.254.169.254", "100.64.0.1", "0.0.0.0", "224.0.0.1",
                                   "::1", "fc00::1", "fe80::1", "ff02::1", "::ffff:127.0.0.1"])
def test_non_public_and_mixed_dns_are_rejected(ip, network, monkeypatch):
    calls, _ = network
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [addr(), addr(ip)])
    result = ef.fetch_public("https://example.org/work")
    assert result["outcome"] == "non_public_address"
    assert result["status"] is None
    assert calls == []


def test_redirect_to_private_is_rechecked_before_connection(network, monkeypatch):
    calls, responses = network
    responses.append(Response(status=302, headers={"Location": "http://internal.example/metadata"}))
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, **kw:
                        [addr("127.0.0.1" if host == "internal.example" else "8.8.8.8", port)])
    result = ef.fetch_public("https://example.org/book")
    assert result["outcome"] == "non_public_address"
    assert len(calls) == 1 and calls[0]["closed"]
    assert result["redirects"][0]["status"] == 302


def test_redirect_scheme_credentials_and_port_are_rechecked(network):
    calls, responses = network
    responses.append(Response(status=302, headers={"Location": "https://me:secret@example.org/"}))
    assert ef.fetch_public("https://example.org/book")["outcome"] == "invalid_url"
    assert len(calls) == 1


def test_public_redirect_keeps_exact_returned_bytes_and_never_sends_credentials(network, monkeypatch):
    calls, responses = network
    body = b"<html><p>The exact retained passage.</p></html>"
    responses.extend([Response(status=301, headers={"Location": "/edition"}), Response(body)])
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9000")
    result = ef.fetch_public("https://example.org/book#chapter")
    assert result["ok"] and result["body"] == body
    assert result["sha256"] == hashlib.sha256(body).hexdigest()
    assert result["final_url"] == "https://example.org/edition"
    assert [call["target"] for call in calls] == ["/book", "/edition"]
    assert all(call["method"] == "GET" and call["closed"] for call in calls)
    assert all(not {key.lower() for key in call["headers"]} & {"cookie", "authorization", "proxy-authorization"}
               for call in calls)
    assert all(call["address"][4][0] == "8.8.8.8" for call in calls)


def test_redirect_loop_and_limit(network):
    calls, responses = network
    responses.append(Response(status=302, headers={"Location": "/book"}))
    assert ef.fetch_public("https://example.org/book")["outcome"] == "redirect_loop"
    responses.extend(Response(status=302, headers={"Location": f"/hop{i}"}) for i in range(4))
    assert ef.fetch_public("https://example.org/start")["outcome"] == "redirect_limit"
    assert len(calls) == 5  # one loop request + four bounded redirect requests


def test_tcp_connection_is_pinned_to_validated_address(monkeypatch):
    connected = []

    class Socket:
        def __init__(self, *args):
            pass

        def settimeout(self, value):
            pass

        def connect(self, value):
            connected.append(value)

        def close(self):
            pass

    monkeypatch.setattr(socket, "socket", Socket)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: pytest.fail("must not resolve twice"))
    conn = ef._PinnedHTTPConnection("example.org", 80, addr("8.8.8.8", 80), 10)
    conn.connect()
    assert connected == [("8.8.8.8", 80)]


def test_tls_uses_original_hostname_and_verified_context(monkeypatch):
    raw = object()
    seen = {}
    monkeypatch.setattr(ef, "_connect_address", lambda address, timeout: raw)
    conn = ef._PinnedHTTPSConnection("example.org", 443, addr(), 10)
    assert conn._context.verify_mode == ssl.CERT_REQUIRED and conn._context.check_hostname

    class Context:
        def wrap_socket(self, sock, server_hostname):
            seen.update(sock=sock, host=server_hostname)
            return "tls_socket"

    conn._context = Context()
    conn.connect()
    assert seen == {"sock": raw, "host": "example.org"} and conn.sock == "tls_socket"


@pytest.mark.parametrize("status,outcome", [(401, "authentication_required"), (403, "access_denied"),
                                             (404, "not_found"), (429, "rate_limited"), (503, "http_error")])
def test_http_failure_is_not_a_source(status, outcome, network):
    _, responses = network
    responses.append(Response(b"<p>The quotation in an error page.</p>", status))
    result = ef.fetch_public("https://example.org/book")
    assert result["outcome"] == outcome and "body" not in result


@pytest.mark.parametrize("headers,outcome", [
    ({"Content-Type": "application/pdf"}, "unsupported_content_type"),
    ({"Content-Encoding": "gzip"}, "unsupported_encoding"),
    ({"Content-Length": str(ef.MAX_BYTES + 1)}, "oversized"),
    ({"Content-Length": "not-a-number"}, "invalid_content_length"),
    ({"Content-Length": "-5"}, "invalid_content_length"),
    ({"Content-Length": "900"}, "incomplete_body"),
])
def test_unsupported_and_incomplete_responses_are_named(headers, outcome, network):
    calls, responses = network
    responses.append(Response(headers=headers))
    assert ef.fetch_public("https://example.org/book")["outcome"] == outcome
    assert calls[0]["closed"]


def test_streaming_size_limit_applies_without_content_length(network):
    _, responses = network
    responses.append(Response(b"x" * (ef.MAX_BYTES + 1), headers={"Content-Type": "text/plain"}))
    assert ef.fetch_public("https://example.org/book")["outcome"] == "oversized"


def test_timeout_is_named_and_closes_connection(network, monkeypatch):
    calls, responses = network
    response = Response()
    monkeypatch.setattr(response, "read1", lambda size: (_ for _ in ()).throw(TimeoutError()))
    responses.append(response)
    assert ef.fetch_public("https://example.org/book")["outcome"] == "timeout"
    assert calls[0]["closed"]


def test_quote_match_is_slice_of_returned_bytes_derivative_and_has_no_store_write(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "LOCAL_STATE", tmp_path)
    body = b"<title>An edition</title><p>Before. Memory is a vast chamber. After.</p>"
    result = ef.inspect_quote(body, "text/html; charset=utf-8", "Memory is a vast chamber.")
    assert result["ok"] and result["matched"] and result["status"] == "exact"
    rep = library.build_representation(result["sha256"], "html", body)
    text = rep["sections"][int(result["section_path"])]["text"]
    assert text[result["start"]:result["end"]] == result["matched_text"] == "Memory is a vast chamber."
    assert result["text_sha256"] == hashlib.sha256(result["matched_text"].encode()).hexdigest()
    assert result["verified"] is False and result["source_admitted"] is False
    assert list(tmp_path.iterdir()) == []


def test_normalized_match_keeps_original_punctuation_and_offsets():
    body = "Before. Memory—‘a chamber’—remains. After.".encode()
    result = ef.inspect_quote(body, "text/plain", "Memory-'a chamber'-remains.")
    assert result["status"] == "normalized" and result["matched"]
    assert result["matched_text"] == "Memory—‘a chamber’—remains."


def test_changed_negation_is_not_repaired_into_match():
    result = ef.inspect_quote(b"Memory is not a chamber.", "text/plain", "Memory is a chamber.")
    assert result["ok"] and not result["matched"] and result["status"] == "not_found"


def test_repeated_matches_are_counted_not_unique_by_assertion():
    result = ef.inspect_quote(b"A chamber. A chamber.", "text/plain", "A chamber.")
    assert result["match_count"] == 2 and result["occurrences_in_section"] == 2


@pytest.mark.parametrize("body,mime,status", [
    (b"%PDF-1.7", "application/pdf", "unsupported_content_type"),
    (b"<input type='password'><p>Sign in.</p>", "text/html", "login_required"),
    (b"<script>renderTheBook()</script><div id='root'></div>", "text/html", "javascript_required"),
    (b"<html></html>", "text/html", "no_extractable_text"),
])
def test_inaccessible_text_is_a_named_contingency(body, mime, status):
    result = ef.inspect_quote(body, mime, "a chamber")
    assert not result["ok"] and not result["matched"] and result["status"] == status


def test_no_quote_does_not_manufacture_a_success():
    result = ef.inspect_quote(b"A substantial passage.", "text/plain", "")
    assert result["ok"] and not result["matched"] and result["status"] == "no_quote"


def test_grounding_text_is_bounded_but_later_exact_match_survives():
    body = ("Long prefatory context. " * 800 + "The passage at the end.").encode()
    result = ef.inspect_quote(body, "text/plain", "The passage at the end.")
    assert len(result["text"]) == ef.MAX_GROUNDING_CHARS
    assert result["text_omitted_chars"] > 0
    assert "The passage at the end." not in result["text"]
    assert result["exact_text"] == "The passage at the end."
    assert "The passage at the end." in result["excerpt"]
    assert len(result["representation_sha256"]) == 64


def test_extraction_only_retains_grounding_text():
    result = ef.inspect_quote(b"A passage to read without a quotation target.", "text/plain", None)
    assert result["text"] == "A passage to read without a quotation target."
    assert result["text_omitted_chars"] == 0 and result["status"] == "no_quote"


@pytest.mark.parametrize("mime", ["text/plain", "text/html"])
@pytest.mark.parametrize("prefix", [b"%PDF-1.7\n", b" \n%PDF-1.7\n", b"PK\x03\x04",
                                    b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF89a",
                                    b"\x1f\x8b", b"binary\x00"])
def test_binary_body_cannot_become_evidence_by_claiming_text_mime(prefix, mime):
    body = prefix + b"<p>The exact target quotation.</p>"
    result = ef.inspect_quote(body, mime, "The exact target quotation.")
    assert result["status"] == "unsupported_binary_content"
    assert not result["ok"] and not result["matched"]
    assert result["body_sha256"] == hashlib.sha256(body).hexdigest()
    assert "text" not in result


@pytest.mark.parametrize("quote,status", [(None, "no_quote"), ("A missing quotation.", "not_found")])
def test_question_selects_later_chapter_beyond_opening_window(quote, status):
    body = ("Prefatory material about travel. " * 800 +
            "\nChapter ten: memory and desire. Memory holds the past while desire reaches forward. " +
            "Closing material. " * 200).encode()
    result = ef.inspect_quote(body, "text/plain", quote, question="How are memory and desire related?")
    assert result["status"] == status and not result["matched"]
    assert result["selection_method"] == "question_term_overlap"
    assert "Chapter ten: memory and desire." in result["text"]
    assert len(result["text"]) <= ef.QUESTION_EXCERPT_CHARS
    assert result["excerpt_selection"]["start"] > ef.MAX_GROUNDING_CHARS
    assert result["relevance_verified"] is False and result["verified"] is False
    rep = library.build_representation(result["body_sha256"], "txt", body)
    selection = result["excerpt_selection"]
    section = rep["sections"][int(selection["section_path"])]
    assert section["text"][selection["start"]:selection["end"]] == result["text"]


def test_question_without_matching_terms_uses_labeled_opening_excerpt():
    result = ef.inspect_quote(b"A passage about mountains.", "text/plain", "", question="Explain memory and desire.")
    assert result["selection_method"] == "opening_excerpt"
    assert result["text"] == "A passage about mountains." and result["relevance_verified"] is False


def test_question_window_does_not_replace_full_text_quote_matching():
    body = ("A chapter about justice. " * 800 + "The exact target quotation.").encode()
    result = ef.inspect_quote(body, "text/plain", "The exact target quotation.", question="What is justice?")
    assert result["matched"] and result["status"] == "exact"
    assert result["exact_text"] == "The exact target quotation."
    assert result["start"] > ef.MAX_GROUNDING_CHARS
    assert "The exact target quotation." in result["excerpt"]
