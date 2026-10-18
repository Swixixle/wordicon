"""Source identity is separate from capture bytes and model interpretation.

Only explicit producer identities (or verified correction overlays) resolve an
underlying record. Titles, URLs and text similarity never establish independence.
"""
from __future__ import annotations
import hashlib
import json
import re

SCHEMA = 'nikodemus.evidence.lineage.v1'


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def for_finding(finding, capture_id=''):
    identity = finding.get('source_identity') or {}
    source = identity.get('record_identity') or identity.get('source_record_id')
    family = identity.get('provenance_family_id')
    revision = identity.get('substantive_revision_sha256')
    resolved = bool(source and family and revision and identity.get('namespace'))
    return {'schema': SCHEMA, 'capture_id': str(capture_id) + ':' + str(finding.get('id') or _sha(finding)),
            'capture_sha256': _sha(finding), 'source_record_id': source if resolved else None,
            'substantive_revision_id': revision if resolved else None,
            'provenance_family_id': family if resolved else None,
            'identity_status': 'resolved' if resolved else 'unresolved',
            'basis': identity if resolved else 'No authoritative upstream identity supplied; URL and text alone do not resolve identity.',
            'independence': 'same_source_family' if resolved else 'unresolved',
            'evidence_kind': finding.get('evidence_kind', 'unclassified')}


def for_deflate(envelope, capture_id=''):
    """A reading is an interpretation of a transcript, not a second witness.

    Exact transcript hashes group copies even when external attribution remains
    unresolved. The same run/reading revision can be imported multiple times.
    """
    payload = envelope.get('payload') or {}
    claims = payload.get('claims') or {}
    run = claims.get('run') or {}
    transcript = payload.get('transcript') or run.get('transcript') or {}
    digest = transcript.get('sha256')
    if transcript.get('included') and isinstance(transcript.get('text'), str):
        actual = hashlib.sha256(transcript['text'].encode()).hexdigest()
        if actual != digest:
            raise ValueError('Deflate transcript does not match its supplied hash.')
    run_id = run.get('id') or (envelope.get('object') or {}).get('id')
    readings = [{'id': p.get('id'), 'revision': p.get('readingRev'), 'based_on': p.get('basedOn')} for p in claims.get('passages', [])]
    source_identity = run.get('sourceIdentity') or {}
    confirmed = source_identity.get('state') in ('confirmed', 'verified')
    return {'schema': SCHEMA, 'capture_id': capture_id, 'capture_sha256': _sha(envelope),
            'reading_id': run_id, 'interpretation_revision_id': _sha({'run': run_id, 'passages': readings, 'claims': claims.get('claims', [])}),
            'source_record_id': 'deflate:reading:' + str(run_id) if run_id else None,
            'substantive_revision_id': digest,
            'provenance_family_id': 'deflate:reading:' + str(run_id) if run_id else None,
            'content_duplicate_group': 'transcript-sha256:' + digest if digest else None,
            'identity_status': 'reading_identified' if run_id else 'unresolved',
            'external_attribution': 'confirmed_by_producer' if confirmed else 'unresolved',
            'independence': 'derived_interpretation', 'evidence_kind': 'derived_interpretation',
            'basis': 'Producer reading identity groups reimports and new interpretations of that reading. Identical transcript hashes separately identify content copies; external attribution can remain unresolved.'}


def group(records):
    """Return distinct captures, revisions and families without discarding any."""
    families, unresolved = {}, []
    for record in records:
        lineage = record.get('lineage') or for_finding(record)
        family = lineage.get('provenance_family_id')
        if not family:
            unresolved.append(lineage.get('capture_id'))
            continue
        bucket = families.setdefault(family, {'provenance_family_id': family, 'captures': [], 'revisions': []})
        bucket['captures'].append(lineage.get('capture_id'))
        revision = lineage.get('substantive_revision_id')
        if revision not in bucket['revisions']:
            bucket['revisions'].append(revision)
    return {'families': list(families.values()), 'unresolved_captures': unresolved,
            'note': 'Different source families are distinct records; independence still requires provenance evidence.'}


def validate_answer(answer, citations):
    """Conservatively block unsupported positive independence language.

    This is a structural claim guard, not a semantic truth verifier. Distinct
    resolved primary families are necessary, not sufficient, for corroboration.
    """
    positive = False
    for sentence in re.split(r'[.!?;,\n]+|\band\b|\bbut\b', answer.lower()):
        if re.search(r'\bindependen\w*|\bcorroborat\w*|\bseparate\s+(?:sources|records)', sentence):
            if not re.search(r'\b(?:not|no|without|cannot|can.t|doesn.t|do not|lack\w*|unresolved|unknown|unproven)\b', sentence):
                positive = True
    if not positive:
        return {'ok': True, 'reason': ''}
    families = set()
    for citation in citations:
        lineage = citation.get('lineage') or {}
        if (lineage.get('identity_status') == 'resolved' and lineage.get('provenance_family_id')
                and (citation.get('evidence_kind') or lineage.get('evidence_kind')) == 'official_primary_record'):
            families.add(lineage['provenance_family_id'])
    if len(families) < 2:
        return {'ok': False, 'reason': 'The answer claims independent corroboration without at least two resolved primary-source families. Copies and interpretations are not independent evidence.'}
    return {'ok': True, 'reason': 'Distinct primary families are present; independence remains an interpretation requiring review.'}
