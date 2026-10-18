import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import evidence_lineage as lineage


def record(nid='1', revision='abc', body='Commission date: 2013-03-26'):
    return {'id':'e1','body':body,'evidence_kind':'official_primary_record',
            'source_identity':{'namespace':'fjc','record_identity':'fjc:'+nid,
            'provenance_family_id':'fjc:'+nid,'substantive_revision_sha256':revision}}

class IdentityTests(unittest.TestCase):
    def test_renderer_variants_share_family_and_revision_but_keep_capture(self):
        a=lineage.for_finding(record(), 'op1'); b=lineage.for_finding(record(body='Commission (oath) date: 2013-03-26'), 'op2')
        self.assertNotEqual(a['capture_sha256'],b['capture_sha256'])
        self.assertEqual(a['source_record_id'],b['source_record_id'])
        self.assertEqual(a['substantive_revision_id'],b['substantive_revision_id'])
    def test_substantive_change_and_subject_separation(self):
        a=lineage.for_finding(record()); b=lineage.for_finding(record(revision='changed',body='Commission date: 2013-03-27'))
        c=lineage.for_finding(record(nid='2'))
        self.assertEqual(a['source_record_id'],b['source_record_id']);self.assertNotEqual(a['substantive_revision_id'],b['substantive_revision_id'])
        self.assertNotEqual(a['source_record_id'],c['source_record_id'])
    def test_known_record_can_have_unknown_historical_revision(self):
        f=record();f['source_identity'].pop('substantive_revision_sha256')
        got=lineage.for_finding(f)
        self.assertEqual(got['identity_status'],'resolved')
        self.assertEqual(got['substantive_revision_status'],'unknown')
        self.assertEqual(got['provenance_family_id'],'fjc:1')

    def test_explicit_mirror_same_family_unresolved_url_does_not_resolve(self):
        a=record(); b=copy.deepcopy(a);b['source_url']='https://mirror.example/biography'
        self.assertEqual(lineage.for_finding(a)['provenance_family_id'],lineage.for_finding(b)['provenance_family_id'])
        self.assertEqual(lineage.for_finding({'source_url':'https://fjc.gov/example'})['identity_status'],'unresolved')
    def test_independence_guard(self):
        citations=[{'lineage':lineage.for_finding(record(),str(n))} for n in range(2)]
        self.assertFalse(lineage.validate_answer('Independent records corroborate this.',citations)['ok'])
        self.assertTrue(lineage.validate_answer('These copies are not independent corroboration.',citations)['ok'])
        self.assertFalse(lineage.validate_answer('There are no contradictions, and independent sources corroborate this.',citations)['ok'])
        citations.append({'lineage':lineage.for_finding(record(nid='2'))})
        self.assertTrue(lineage.validate_answer('Two independent sources.',citations)['ok'])
    def test_deflate_reimport_and_new_interpretation(self):
        fixture=Path(__file__).parent/'fixtures/federation/deflate.exemplar.deposition.json'
        env=json.loads(fixture.read_text());a=lineage.for_deflate(env,'import1');b=lineage.for_deflate(env,'import2')
        self.assertEqual(a['interpretation_revision_id'],b['interpretation_revision_id']);self.assertNotEqual(a['capture_id'],b['capture_id'])
        other=copy.deepcopy(env);other['payload']['claims']['passages'][0]['readingRev']=2
        c=lineage.for_deflate(other,'import3')
        self.assertNotEqual(a['interpretation_revision_id'],c['interpretation_revision_id']);self.assertEqual(a['provenance_family_id'],c['provenance_family_id'])
        self.assertEqual(c['external_attribution'],'unresolved')
        other['payload']['claims']['run']['id']='another-reading'
        d=lineage.for_deflate(other,'import4')
        self.assertNotEqual(c['provenance_family_id'],d['provenance_family_id'])
        self.assertEqual(c['content_duplicate_group'],d['content_duplicate_group'])
    def test_deflate_tampered_transcript(self):
        with self.assertRaises(ValueError):lineage.for_deflate({'payload':{'transcript':{'included':True,'text':'wrong','sha256':'bad'}}})

    def test_citation_relationships_keep_copies_revisions_and_unknowns_separate(self):
        citations=[{'record_id':'original','lineage':lineage.for_finding(record(), 'first')},
                   {'record_id':'mirror','lineage':lineage.for_finding(record(body='Old renderer'), 'second')},
                   {'record_id':'revision','lineage':lineage.for_finding(record(revision='new'), 'third')},
                   {'record_id':'unknown','lineage':lineage.for_finding({'source_url':'https://other.example'})}]
        before=copy.deepcopy(citations)
        got=lineage.citation_relationships(citations+[citations[0]])
        self.assertEqual(got['record_count'],4)
        self.assertEqual(got['resolved_primary_family_count'],1)
        self.assertEqual(got['same_family_groups'][0]['record_ids'],['original','mirror','revision'])
        self.assertEqual(got['same_family_groups'][0]['revision_ids'],['abc','new'])
        self.assertEqual(got['unresolved_record_ids'],['unknown'])
        self.assertFalse(got['independence_verified'])
        self.assertEqual(citations,before)

    def test_statement_relationships_do_not_borrow_an_unrelated_family(self):
        citations=[{'record_id':'original','lineage':lineage.for_finding(record(), 'first')},
                   {'record_id':'copy','lineage':lineage.for_finding(record(), 'second')},
                   {'record_id':'other','lineage':lineage.for_finding(record(nid='2'), 'third')}]
        for phrase in ['The date is confirmed by two sources', 'The second record agrees',
                       'No contradiction is recorded, and two sources confirm the date']:
            with self.subTest(phrase=phrase):
                got=lineage.validate_answer(phrase+' [original] [copy]. Another subject is recorded [other].',citations)
                self.assertFalse(got['ok'])
                self.assertEqual(got['evidence_relationships']['resolved_primary_family_count'],2)
                self.assertEqual(got['statement_checks'][-1]['relationships']['resolved_primary_family_count'],1)
        self.assertTrue(lineage.validate_answer('The second record agrees within the same source family [original] [copy]. Another subject [other].',citations)['ok'])
        self.assertFalse(lineage.validate_answer('The same family independently corroborates this [original] [copy]. Another [other].',citations)['ok'])
        for phrase in ['The date is confirmed by two sources', 'The second record agrees']:
            self.assertTrue(lineage.validate_answer(phrase+' [original] [other].',citations)['ok'])
        for conjunction in ['and','AND','But','BUT']:
            self.assertFalse(lineage.validate_answer('The second record agrees [original] [copy] '+conjunction+' an unrelated subject [other].',citations)['ok'])

if __name__=='__main__':unittest.main()
