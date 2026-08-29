#!/usr/bin/env python3
"""
Email notification when a background job finishes — deliberately the
simplest of the three channels (email/SMS/push) discussed: no new account,
no per-message cost, uses credentials you already have.

Configured entirely from server-side environment variables, same discipline
as ANTHROPIC_API_KEY: nothing here is ever sent from or requested by the
phone. If the variables aren't set, notify_job_complete() is a no-op — jobs
still run and their results are still retrievable, you just won't get an
email about it.

Required env vars to enable sending:
  WORDICON_NOTIFY_EMAIL_FROM           the Gmail address sending the mail
  WORDICON_NOTIFY_EMAIL_APP_PASSWORD   a Gmail "App Password" (not your
                                        normal password — see below)

Optional:
  WORDICON_NOTIFY_EMAIL_TO             where to send it; defaults to the
                                        FROM address if unset
  WORDICON_NOTIFY_BASE_URL             e.g. http://192.168.1.23:8420 — if
                                        set, the email includes a direct
                                        link back to the finished job

To get an app password: Google Account -> Security -> 2-Step Verification
must already be on -> App Passwords -> generate one for "Mail". Gmail's
SMTP no longer accepts your normal account password for this.
"""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _configured() -> bool:
    return bool(os.environ.get("WORDICON_NOTIFY_EMAIL_FROM") and
                os.environ.get("WORDICON_NOTIFY_EMAIL_APP_PASSWORD"))


def _job_summary_text(job: dict) -> str:
    """Deliberately withholds the actual winning candidate/title — the
    notification shouldn't spoil the result, just tell you it's ready."""
    result = job.get("result") or {}
    mode = job.get("mode")

    if mode == "sprout":
        threads = result.get("threads", [])
        n_suspect = sum(1 for t in threads if t.get("review_verdict") == "suspect")
        return (f"{len(threads)} lateral thread(s) found · "
                f"{n_suspect} marked suspect by the reviewer · all recall, unverified.")

    if mode == "refract":
        refs = result.get("refractions", [])
        n_coll = sum(1 for r in refs if (r.get("collision") or "").strip())
        return (f"{len(refs)} language(s) refracted through"
                + (f" · {n_coll} possible existing name(s) elsewhere" if n_coll else "")
                + " · all recall, unverified.")

    if mode == "decompose":
        groups = result.get("groups", [])
        n_concepts = len(groups)
        n_failed = sum(1 for g in groups if g.get("failed"))
        n_candidates = sum(len(g.get("candidates", [])) for g in groups)
        n_survived = sum(
            1 for g in groups for c in g.get("candidates", [])
            if c.get("bone_flesh_friction", {}).get("friction", {}).get("verdict") != "reject"
        )
        line = f"{n_concepts} concept(s) found · {n_candidates} candidates tested · {n_survived} survived Friction."
        if n_failed:
            line = (f"PARTIAL — {n_concepts - n_failed} of {n_concepts} concept(s) completed, "
                    f"{n_failed} failed (retryable individually in the app). " + line)
        return line

    candidates = result.get("candidates", [])
    n_candidates = len(candidates)
    n_survived = sum(
        1 for c in candidates
        if c.get("bone_flesh_friction", {}).get("friction", {}).get("verdict") != "reject"
    )
    n_flagged = n_candidates - n_survived
    return f"{n_candidates} candidate(s) · {n_survived} survived Friction, {n_flagged} flagged."


def notify_job_complete(job: dict) -> None:
    """Best-effort. A notification failure never fails the job itself —
    the result is already persisted and retrievable regardless of whether
    this succeeds, same principle as the Bone-attachment call degrading
    gracefully instead of taking the whole operation down with it."""
    if not _configured():
        return

    mode = job.get("mode", "operation")
    input_preview = (job.get("input_text") or "")[:60]
    if len(job.get("input_text") or "") > 60:
        input_preview += "…"

    if job.get("status") == "failed":
        subject = f"Wordicon hit an error — {mode}"
        body = (f"Wordicon failed on {mode} (\"{input_preview}\").\n\n"
                f"{job.get('error', 'no error detail recorded')}\n\n"
                f"Open Wordicon to retry.")
    else:
        subject = f"Wordicon finished — {mode}"
        body = f"Wordicon finished {mode} on \"{input_preview}\".\n\n{_job_summary_text(job)}\n\nOpen Wordicon to see the result."

    base_url = os.environ.get("WORDICON_NOTIFY_BASE_URL")
    if base_url:
        body += f"\n\n{base_url.rstrip('/')}/?job={job['id']}"

    msg = EmailMessage()
    msg["Subject"] = subject
    from_addr = os.environ["WORDICON_NOTIFY_EMAIL_FROM"]
    to_addr = os.environ.get("WORDICON_NOTIFY_EMAIL_TO") or from_addr
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.starttls(context=context)
            server.login(from_addr, os.environ["WORDICON_NOTIFY_EMAIL_APP_PASSWORD"])
            server.send_message(msg)
    except Exception as e:
        print(f"[notify] email send failed, job result is still saved and retrievable: {e}")
