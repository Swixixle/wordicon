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
    resolved = bool(source and family and identity.get('namespace'))
    return {'schema': SCHEMA, 'capture_id': str(capture_id) + ':' + str(finding.get('id') or _sha(finding)),
            'capture_sha256': _sha(finding), 'source_record_id': source if resolved else None,
            'substantive_revision_id': revision if resolved else None,
            'substantive_revision_status': 'identified' if resolved and revision else 'unknown',
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


def citation_relationships(citations):
    """A read-only projection of the cited records, never of model prose.

    Family identity comes from the frozen evidence manifest. Repeated citations,
    changed revisions and copied renderings cannot increase the family count.
    Different primary families are necessary, not sufficient, for independence.
    """
    records, families, unresolved, derived, primary = {}, {}, [], [], set()
    for index, citation in enumerate(citations):
        rid = citation.get('record_id') or 'unbound:' + str(index)
        if rid in records:
            continue
        lineage = citation.get('lineage') or {}
        records[rid] = lineage
        family = lineage.get('provenance_family_id')
        kind = citation.get('evidence_kind') or lineage.get('evidence_kind')
        if lineage.get('independence') == 'derived_interpretation' or kind == 'derived_interpretation':
            derived.append(rid)
        if lineage.get('identity_status') != 'resolved' or not family:
            unresolved.append(rid)
            continue
        bucket = families.setdefault(family, {'provenance_family_id': family, 'record_ids': [],
                                             'source_record_ids': [], 'revision_ids': []})
        bucket['record_ids'].append(rid)
        for field, source in [('source_record_ids', 'source_record_id'), ('revision_ids', 'substantive_revision_id')]:
            value = lineage.get(source)
            if value not in bucket[field]:
                bucket[field].append(value)
        if kind == 'official_primary_record' and rid not in derived:
            primary.add(family)
    copies = [b for b in families.values() if len(b['record_ids']) > 1]
    return {'schema': 'nikodemus.citation_relationships.v1', 'record_count': len(records),
            'resolved_family_count': len(families), 'resolved_primary_family_count': len(primary),
            'families': list(families.values()), 'same_family_groups': copies,
            'unresolved_record_ids': unresolved, 'derived_record_ids': derived,
            'independence_verified': False,
            'basis': 'Frozen cited-record lineage; no title, URL, name or model claim establishes independence.',
            'note': ('Some cited records share a source family. Agreement between those copies or revisions is not independent corroboration. '
                     if copies else '') + 'Distinct source families alone do not verify independent corroboration or source truth.'}


def validate_answer(answer, citations):
    """Supplement legacy prose with a statement-local structural guard.

    Current checked-excerpt answers add no free model claim. Legacy prose needs
    both explicit citation relationships and a conservative language screen;
    this screen is not complete semantic validation. An unrelated second family
    elsewhere in the answer cannot license a claim about copies of one record.
    """
    all_relationships = citation_relationships(citations)
    by_id = {c['record_id']: c for c in citations if c.get('record_id')}
    checks = []
    # Keep periods inside record IDs intact. Clause splits keep a negated claim
    # from licensing a later positive one in the same sentence.
    for clause in re.split(r'(?<=[.!?])\s+|[;\n]+|\s+(?:and|but)\s+', answer, flags=re.IGNORECASE):
        words = re.sub(r'\[[^\]\n]+\]', '', clause).lower()
        claim = re.search(r'\bindependen\w*|\bcorroborat\w*|\bseparate\s+(?:sources|records)|'
                          r'\bconfirm\w*\b.*\b(?:two|multiple|both|second)\b|'
                          r'\b(?:two|multiple|both|second)\b.*\b(?:confirm\w*|agree\w*|support\w*|verif\w*)\b', words)
        if not claim:
            continue
        negative = re.search(r'\b(?:not|no|without|cannot|can.t|doesn.t|do not|lack\w*)\s+(?:\w+\s+){0,2}(?:independen\w*|corroborat\w*|confirm\w*|agree\w*|verif\w*)\b|'
                             r'\b(?:independence|corroboration)\s+(?:is\s+)?(?:unresolved|unknown|unproven)\b', words)
        qualified_copy = (re.search(r'\b(?:same|one|single|shared)\s+(?:underlying\s+)?(?:source\s+)?(?:family|record|source)\b', words)
                          and not re.search(r'\bindependen\w*|\bcorroborat\w*', words))
        ids = list(dict.fromkeys(re.findall(r'\[([^\]\n]+)\]', clause)))
        # Pre-manifest callers had no record IDs; preserve their conservative
        # all-citation behavior. Actual synthesis records always carry IDs.
        local = [by_id[rid] for rid in ids if rid in by_id] if by_id else citations
        relationships = citation_relationships(local)
        eligible = relationships['resolved_primary_family_count'] >= 2
        ok = bool(negative or qualified_copy or eligible)
        checks.append({'record_ids': ids, 'relationships': relationships, 'ok': ok,
                       'basis': 'qualified_copy' if qualified_copy else 'negated_claim' if negative else 'statement_citations'})
        if not ok:
            return {'ok': False, 'reason': 'This statement claims corroboration or agreement without two resolved primary-source families among its own citations. Copies may agree, but must be identified as copies of one family, not independent evidence.',
                    'evidence_relationships': all_relationships, 'statement_checks': checks,
                    'semantic_verification': False}
    return {'ok': True, 'reason': 'Citation relationships checked; independence and factual support still require review.',
            'evidence_relationships': all_relationships, 'statement_checks': checks,
            'semantic_verification': False}
