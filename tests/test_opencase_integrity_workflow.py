"""Integrity boundaries using scratch stores, fake model and signed fixtures."""
import base64
import copy
import hashlib
import json
import unittest
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from test_opencase_synthesis import SynthesisTests
from test_opencase_workflow import opencase, ops, federation, producers
import operation_costs

class IntegrityWorkflowTests(SynthesisTests):
    def test_legacy_unnamed_hold_is_derived_without_rewriting_history(self):
        self.model.mode='truncated'
        op=self.run_prepared(self.prepare_model())
        ref=copy.deepcopy(op['result_ref']);ref['synthesis'].pop('hold_reason')
        ops.mark(op['op_id'],result_ref=ref)
        current=ops.get(op['op_id']);cost=operation_costs.total(current)
        state=opencase.view(current)['synthesis']
        self.assertEqual(state['hold_reason'],'output_limit')
        self.assertEqual(state['hold_basis'],'derived_from_preserved_provider_receipt')
        self.assertEqual(ops.get(op['op_id'])['result_ref'],ref)
        self.assertEqual(operation_costs.total(current),cost)

    def test_review_hold_is_durable_bound_to_receipt_and_preserves_original_and_cost(self):
        op=self.run_prepared(self.prepare_model())
        original=copy.deepcopy(op['result_ref'])
        before=operation_costs.total(op)
        payload={'reason':'The cited record does not establish the additional timing inference.',
                 'response_sha256':original['synthesis']['response_artifact']['sha256']}
        url='/api/open-case/operations/'+op['op_id']+'/answer-review'
        for _ in range(2):
            r=self.client.post(url,json=payload)
            self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(r.json['dimensions']['display_status'],'Answer held')
        self.assertEqual(r.json['synthesis']['hold_reason'],'support_disputed')
        self.assertEqual(r.json['synthesis']['answer'],'')
        self.assertEqual(r.json['synthesis']['held_answer'],original['synthesis']['answer'])
        self.assertEqual(len(r.json['synthesis']['reviews']),1)
        current=ops.get(op['op_id'])
        self.assertEqual(current['result_ref'],original)
        self.assertEqual(operation_costs.total(current),before)
        with patch.object(producers,'_request',side_effect=AssertionError('review is local')):
            opencase._run(op['op_id'],resume=True)
        self.assertEqual(opencase.view(ops.get(op['op_id']))['synthesis']['hold_reason'],'support_disputed')
        self.assertEqual(len(self.model.calls),1)

    def test_review_requires_exact_saved_receipt_and_explanation(self):
        op=self.run_prepared(self.prepare_model())
        url='/api/open-case/operations/'+op['op_id']+'/answer-review'
        r=self.client.post(url,json={'reason':'Unsupported timing claim in the answer.','response_sha256':'other'})
        self.assertEqual(r.status_code,409)
        r=self.client.post(url,json={'reason':'short','response_sha256':op['result_ref']['synthesis']['response_artifact']['sha256']})
        self.assertEqual(r.status_code,400)
        self.assertNotIn('reviews',opencase.view(ops.get(op['op_id']))['synthesis'])

    def test_answer_recovery_reuses_exact_evidence_and_does_not_repeat_collection(self):
        self.model.mode='truncated'
        parent=self.run_prepared(self.prepare_model(), 'held')
        original=opencase.artifact(parent,'result.json')
        self.model.mode='complete'
        plan=parent['execution']['plan']
        p=self.prepare(follow_up_of=parent['op_id'],reuse_evidence_from=parent['op_id'],
                       synthesis={'enabled':True,'max_output_tokens':8192})
        # No producer is required: the frozen artifact is the whole collection.
        with patch.object(producers,'_request',side_effect=AssertionError('recovery must not contact producer')):
            r=self.start(p,'recovery')
        self.assertEqual(r.status_code,200,r.json)
        child=ops.get(r.json['operation_id']);v=opencase.view(child)
        self.assertEqual(opencase.artifact(child,'result.json'),original)
        self.assertEqual(len(self.model.calls),2)
        self.assertEqual(self.model.calls[-1][1],8192)
        self.assertEqual(v['synthesis']['status'],'complete',v)
        self.assertEqual(opencase.view(ops.get(parent['op_id']))['synthesis']['status'],'truncated')
        self.assertEqual(v['plan']['root_question'],plan['question'])
        self.assertIn(parent['op_id'],v['thread_costs']['operation_ids'])
        with patch.object(producers,'_request',side_effect=AssertionError('reopen is local')):
            opencase._run(child['op_id'],resume=True)
        self.assertEqual(len(self.model.calls),2)

    def test_recovery_without_upstream_job_is_reconciled_after_restart(self):
        parent=self.run_prepared(self.prepare_model())
        p=self.prepare(follow_up_of=parent['op_id'],reuse_evidence_from=parent['op_id'],synthesis={'enabled':True})
        with patch.object(opencase.synthesis,'run'):
            child=self.run_prepared(p,'waiting-recovery')
        self.assertNotIn('upstream_id',child['result_ref'])
        with patch.object(opencase,'launch',return_value=True) as launch:
            self.assertIn(child['op_id'],opencase.resume_known())
            launch.assert_called_with(child['op_id'],resume=True)

    def test_signed_source_body_mismatch_is_held_before_model_dispatch(self):
        from test_opencase_workflow import ROOT
        key=Ed25519PrivateKey.generate()
        public=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        federation.pin_key('case-test',base64.b64encode(public).decode(),label='fixture key')
        template=json.loads((ROOT/'tests/fixtures/federation/open_case.exemplar.deposition.json').read_text())
        self.case_id=template['object']['id']
        sealed=template['payload']['evidence'][0]
        sealed['producer_semantics']={'evidence_kind':'official_primary_record'}
        digest=federation.payload_sha256(template['payload']);template['payload_sha256']=digest
        template['signature'].update(trusted_key_id='ed25519:sha256:'+hashlib.sha256(public).hexdigest(),value=base64.b64encode(key.sign(digest.encode())).decode())
        original=self.fixture
        def mismatch(*args,**kwargs):
            response=original(*args,**kwargs)
            if args[2].endswith('/result'):
                finding={**sealed,'evidence_kind':'official_primary_record','body':'ALTERED UNSIGNED TEXT'}
                result=response['json'];result.update(findings=[finding],deposition=template,deposition_json=json.dumps(template))
                response['raw']=json.dumps(result).encode()
            return response
        with patch.object(self,'fixture',side_effect=mismatch):
            op=self.run_prepared(self.prepare_model())
        self.assertEqual(self.model.calls,[])
        self.assertIn('differs from the signed',op['last_error'])
        self.assertEqual(op['status'],'unknown')

    def test_no_completed_label_for_held_partial_or_unassessed_answer(self):
        self.model.mode='truncated';op=self.run_prepared(self.prepare_model())
        v=opencase.view(op)
        self.assertEqual(v['dimensions']['display_status'],'Answer held')
        self.assertFalse(v['dimensions']['completed'])
        result=copy.deepcopy(v['result']);result['dimensions']={'acquisition':{'status':'ready','required_ready':True}}
        with patch.object(opencase.synthesis,'view',return_value={'status':'complete','answer_status':'partial'}):
            self.assertFalse(opencase.result_dimensions(op,result)['completed'])
        with patch.object(opencase.synthesis,'view',return_value={'status':'complete','answer_status':'answered'}):
            self.assertTrue(opencase.result_dimensions(op,result)['completed'])

    def test_signed_correction_bound_to_original_and_preserves_bytes(self):
        op=self.run_prepared(self.prepare(),'original');original=opencase.artifact(op,'result.json');result=json.loads(original)
        key=Ed25519PrivateKey.generate();public=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        federation.pin_key('case-test',base64.b64encode(public).decode(),label='fixture trusted independently')
        kid='ed25519:sha256:'+hashlib.sha256(public).hexdigest()
        finding=result['findings'][0]
        payload={'job_id':result['job_id'],'original_result_sha256':federation.payload_sha256(result),
                 'original_deposition_payload_sha256':None,'evidence':[{'evidence_id':finding['id'],
                 'original_finding_sha256':federation.payload_sha256(finding),'evidence_kind':'official_primary_record',
                 'source_identity':{'namespace':'fixture','record_identity':'record:1','provenance_family_id':'family:1','substantive_revision_sha256':'rev1'}}]}
        digest=federation.payload_sha256(payload)
        envelope={'schema':'open_case.investigation.correction.v1','correction_id':'fixture-correction','job_id':result['job_id'],
                  'payload':payload,'payload_sha256':digest,'signature':{'algorithm':'Ed25519','canonicalization':'RFC8785',
                  'signed_bytes':'utf8(hex(sha256(jcs(payload))))','trusted_key_id':kid,'value':base64.b64encode(key.sign(digest.encode())).decode()}}
        self.assertEqual(opencase._verified_correction(op,envelope,result),payload)
        raw=json.dumps(envelope).encode()
        with patch.object(producers,'_request',return_value={'ok':True,'json':envelope,'raw':raw}):
            kept=opencase.correct_saved_evidence(op)
        current=ops.get(op['op_id']);v=opencase.view(current)
        self.assertEqual(v['findings'][0]['lineage']['source_record_id'],'record:1')
        self.assertEqual(opencase.artifact(current,'result.json'),original)
        self.assertNotIn('evidence_kind',v['result']['findings'][0])
        changed=copy.deepcopy(result);changed['findings'][0]['title']='changed'
        with self.assertRaises(opencase.WorkflowError):opencase._verified_correction(current,envelope,changed)
        envelope['signature']['value']=base64.b64encode(b'0'*64).decode()
        with self.assertRaises(opencase.WorkflowError):opencase._verified_correction(current,envelope,result)

    def test_settings_accounting_reads_same_ledger(self):
        op=self.run_prepared(self.prepare_model())
        per=operation_costs.total(op)
        summary=self.client.get('/api/operation-costs').json
        self.assertEqual(per['estimated_cost_usd'],summary['estimated_cost_usd'])
        self.assertEqual(per['actual_cost_usd'],None)
        self.assertEqual(per['known_estimated_subtotal_usd'],summary['known_estimated_subtotal_usd'])

if __name__=='__main__': unittest.main()
