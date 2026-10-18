"""Pure MIT Receipts helpers, vendored without disk/network/model dependencies.

Source: https://github.com/Swixixle/Receipts
Commit: daf17d57a09b26ed82695a836c437453cb945474
Copyright (c) 2026 Alex Maksimovich. MIT license: docs/third-party/receipts-LICENSE.txt.
See receipts-upstream.json for exact file hashes and extracted symbols.
This is a selected verbatim extraction, not the complete Receipts application.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Literal

_NEG_BODY = re.compile(
    r"(?i)\b(no|without|not)\s+.{0,14}?\b(bodycam|body-worn|body\s+worn|bwc|911\s+call|dispatch)\b"
)


_NEG_EXHIBIT = re.compile(r"(?i)(no\s+exhibit|exhibit\s+not\s+attached|without\s+exhibit)")


@dataclass(frozen=True)
class _Rule:
    pattern: re.Pattern[str]
    item_type: str
    confidence: str
    suggested_action: str
    cover_needles: frozenset[str]
    referenced_label: str


def _rules() -> tuple[_Rule, ...]:
    return (
        _Rule(
            re.compile(
                r"(?i)\b(?:bodycam\s+footage|body-worn\s+camera|body\s+worn\s+camera|"
                r"bodycam\s+recording|\bbwc\b(?:\s+footage|\s+recording)?|"
                r"(?:body-worn\s+camera|bodycam|bwc)\s+was\s+activated|"
                r"activated\s+.{0,28}?(?:body-worn\s+camera|bodycam|bwc))\b"
            ),
            "bodycam",
            "high",
            "request_or_upload_bodycam",
            frozenset({"bodycam", "body-worn", "body worn", "bwc", "body camera"}),
            "bodycam footage",
        ),
        _Rule(
            re.compile(
                r"(?i)\b(dispatch\s+audio|911\s+call(?:\s+recording|\s+audio)?|"
                r"\b911\s+call\b|cad\s+report|radio\s+traffic\s+recording)\b"
            ),
            "dispatch_audio",
            "high",
            "request_dispatch_audio",
            frozenset(
                {
                    "dispatch",
                    "911",
                    "cad",
                    "dispatch audio",
                    "emergency call",
                    "call audio",
                }
            ),
            "dispatch audio or 911/CAD recording",
        ),
        _Rule(
            re.compile(
                r"(?i)\b(?:supplemental\s+)?witness\s+statement\s+(?:was\s+)?"
                r"(?:requested|filed|obtained|submitted)\b|"
                r"\b(?:requested|filed|obtained|submitted)\s+.{0,52}?"
                r"(?:supplemental\s+)?witness\s+statement\b"
            ),
            "witness_statement",
            "high",
            "request_witness_statement",
            frozenset(
                {
                    "witness statement",
                    "witnessstmt",
                    "sworn statement",
                    "affidavit",
                    "deposition",
                }
            ),
            "witness statement",
        ),
        _Rule(
            re.compile(r"(?i)\b(probable\s+cause\s+affidavit)\b"),
            "affidavit",
            "high",
            "request_probable_cause_affidavit",
            frozenset(
                {
                    "probable cause",
                    "pc affidavit",
                    "probable cause affidavit",
                }
            ),
            "probable cause affidavit",
        ),
        _Rule(
            re.compile(
                r"(?i)\b(search\s+warrant\s+return|return\s+of\s+search\s+warrant|"
                r"warrant\s+return)\b"
            ),
            "search_warrant",
            "high",
            "request_search_warrant",
            frozenset(
                {
                    "search warrant",
                    "warrant return",
                    "return of service",
                    "warrant inventory",
                }
            ),
            "search warrant return",
        ),
        _Rule(
            re.compile(
                r"(?i)\bappendix\s+[a-z]\b.{0,120}?"
                r"(?:search\s+warrant|warrant\s+return|return\s+of\s+service)\b"
            ),
            "search_warrant",
            "medium",
            "request_search_warrant",
            frozenset({"appendix", "search warrant", "warrant return"}),
            "appendix tied to warrant materials",
        ),
        _Rule(
            re.compile(r"(?i)\b(exhibit\s+[A-Z0-9]{1,8})\b"),
            "exhibit",
            "high",
            "upload_exhibit",
            frozenset(),
            "exhibit",
        ),
        _Rule(
            re.compile(
                r"(?i)\b(surveillance\s+video|security\s+footage|dashcam\s+footage|"
                r"dashcam\s+recording)\b"
            ),
            "recording",
            "high",
            "upload_recording_or_transcript",
            frozenset(
                {"surveillance", "security footage", "dashcam", "dash cam", "video recording"}
            ),
            "surveillance or dashcam recording",
        ),
        _Rule(
            re.compile(
                r"(?i)\b(photographs|photographs\s+of|photos\s+of|photos\s+were|"
                r"photographic\s+evidence)\b"
            ),
            "photo",
            "high",
            "request_or_upload_photos",
            frozenset({"photograph", "photo", "images", "picture", "jpg", "png"}),
            "photographs or photos",
        ),
        _Rule(
            re.compile(r"(?i)\b(supplemental\s+report|additional\s+incident\s+report)\b"),
            "report",
            "medium",
            "add_source",
            frozenset({"supplemental", "supplement", "additional report"}),
            "supplemental or additional report",
        ),
        _Rule(
            re.compile(
                r"(?i)\b(federal\s+lawsuit|court\s+records\s+allege)\b"
            ),
            "court_record",
            "medium",
            "add_court_record_source",
            frozenset(),
            "court record for cited lawsuit or allegation",
        ),
        _Rule(
            re.compile(r"(?i)\b(see\s+attached|report\s+attached|attachment\s+referenced)\b"),
            "unknown",
            "medium",
            "review_manually",
            frozenset({"attachment", "attached", "appendix", "exhibit"}),
            "attached or referenced document",
        ),
        _Rule(
            re.compile(r"(?i)\b(transcript|recording|audio\s+file)\b"),
            "recording",
            "medium",
            "upload_recording_or_transcript",
            frozenset({"transcript", "recording", "audio file", "wav", "mp3"}),
            "transcript or recording",
        ),
    )


def _negates_near(text: str, span: tuple[int, int]) -> bool:
    """True if a negation appears in the immediate neighborhood of this match (not whole paragraph)."""
    a, b = span
    lo = max(0, a - 28)
    hi = min(len(text), b + 12)
    chunk = text[lo:hi]
    if _NEG_BODY.search(chunk) or _NEG_EXHIBIT.search(chunk):
        return True
    return False


_MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|november|december"
)


_RE_ISO = re.compile(
    r"\b(\d{4})-(\d{2})-(\d{2})(?:[T\s](\d{1,2}):(\d{2})(?::(\d{2}))?)?\b",
    re.IGNORECASE,
)


_RE_US = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")


_RE_MON = re.compile(
    rf"\b({_MONTHS})\s+(\d{{1,2}}),?\s+(\d{{4}})\b",
    re.IGNORECASE,
)


_RE_FILED = re.compile(
    rf"\bfiled\s+({_MONTHS})\s+(\d{{1,2}}),?\s+(\d{{4}})\b",
    re.IGNORECASE,
)


_RE_CAD = re.compile(
    r"\b(?:opened|logged|received)\s+at\s+(\d{1,2}):(\d{2})\b", re.IGNORECASE
)


_RE_TIME_12 = re.compile(
    r"\b(\d{1,2}):(\d{2})\s*(am|pm)\b",
    re.IGNORECASE,
)


_RE_TIME_24 = re.compile(r"\b(\d{2}):(\d{2})\b")


_RE_APPROX = re.compile(
    r"\b(?:around|approximately|about)\s+(\d{1,2}):(\d{2})\s*(am|pm)\b",
    re.IGNORECASE,
)


DatePrecision = Literal[
    "date", "time", "approximate", "relative", "unknown", "source_date"
]


def _month_to_num(name: str) -> int:
    m = name.lower()[:3]
    mp = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    return mp.get(m, 1)


def _to_minutes(h: int, m: int, ampm: str | None) -> int:
    if ampm:
        ap = ampm.lower()
        h12 = h % 12
        if ap == "pm":
            h12 += 12
        return h12 * 60 + m
    return h * 60 + m


def extract_best_datetime(
    blob: str, manifest_date: str | None
) -> tuple[str | None, str | None, DatePrecision, bool, str | None]:
    """Pick one best date/time pair from text + optional ``manifest_date`` (YYYY-MM-DD)."""
    text = blob or ""
    date_iso: str | None = None
    time_hhmm: str | None = None
    prec: DatePrecision = "unknown"
    approx = False
    span: str | None = None
    got_time_from_iso = False

    for m in _RE_ISO.finditer(text):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        date_iso = f"{y:04d}-{mo:02d}-{d:02d}"
        span = m.group(0)
        if m.group(4) is not None:
            hh, mm = int(m.group(4)), int(m.group(5))
            time_hhmm = f"{hh:02d}:{mm:02d}"
            prec = "time"
            got_time_from_iso = True
        else:
            prec = "date"
        break

    if not date_iso:
        for m in _RE_US.finditer(text):
            mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if mo > 12:
                continue
            date_iso = f"{y:04d}-{mo:02d}-{d:02d}"
            span = m.group(0)
            prec = "date"
            break

    if not date_iso:
        for rx in (_RE_MON, _RE_FILED):
            for m in rx.finditer(text):
                mo_n = _month_to_num(m.group(1))
                d, y = int(m.group(2)), int(m.group(3))
                date_iso = f"{y:04d}-{mo_n:02d}-{d:02d}"
                span = m.group(0)
                prec = "date"
                break
            if date_iso:
                break

    if not got_time_from_iso:
        for m in _RE_APPROX.finditer(text):
            h, mi = int(m.group(1)), int(m.group(2))
            ap = m.group(3).upper()
            minutes = _to_minutes(h, mi, ap)
            hh24, mm = minutes // 60, minutes % 60
            time_hhmm = f"{hh24:02d}:{mm:02d}"
            approx = True
            prec = "approximate"
            span = m.group(0)
            break

    if not got_time_from_iso and not time_hhmm:
        for m in _RE_TIME_12.finditer(text):
            pre = text[max(0, m.start() - 24) : m.start()].lower()
            if "around" in pre or "approximately" in pre or "about" in pre:
                continue
            h, mi = int(m.group(1)), int(m.group(2))
            ap = m.group(3).upper()
            minutes = _to_minutes(h, mi, ap)
            hh24, mm = minutes // 60, minutes % 60
            time_hhmm = f"{hh24:02d}:{mm:02d}"
            prec = "time"
            span = m.group(0)
            break

    if not got_time_from_iso and not time_hhmm:
        for m in _RE_CAD.finditer(text):
            hh, mm = int(m.group(1)), int(m.group(2))
            time_hhmm = f"{hh:02d}:{mm:02d}"
            prec = "time"
            span = m.group(0)
            break

    if not got_time_from_iso and not time_hhmm:
        for m in _RE_TIME_24.finditer(text):
            if m.start() > 0 and text[m.start() - 1] == ":":
                continue
            if "T" in text[max(0, m.start() - 11) : m.start()]:
                continue
            hh, mm = int(m.group(1)), int(m.group(2))
            if hh > 23:
                continue
            time_hhmm = f"{hh:02d}:{mm:02d}"
            prec = "time"
            span = m.group(0)
            break

    md = str(manifest_date).strip() if manifest_date else ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", md):
        if not date_iso:
            date_iso = md
            span = span or f"manifest_date:{md}"
        elif not time_hhmm:
            span = span or f"manifest_date:{md}"

    if date_iso and time_hhmm:
        prec = "approximate" if approx else "time"
    elif date_iso:
        prec = "date"
    elif time_hhmm:
        prec = "approximate" if approx else "time"
    else:
        prec = "unknown"

    return date_iso, time_hhmm, prec, approx, span


_FORBIDDEN_WORDS = re.compile(
    r"\b(lied|lying|hidden|withheld|suppressed)\b", re.IGNORECASE
)


def _neutral_guard(text: str) -> str:
    """Replace accidental accusatory wording (defensive)."""
    t = _FORBIDDEN_WORDS.sub("discrepancy", text)
    return t


