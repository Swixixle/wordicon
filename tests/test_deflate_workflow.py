"""Bounded Deflate lifecycle fixtures: no external sources, provider or owner data.

Staged: NK_ROOT=.../nikodemus DEFLATE_STAGE=.../deflate-nikodemus-stage python this_file
After promotion: run normally from the Nikodemus checkout.
"""
import ast
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

FILES=Path(__file__).resolve().parents[1]
ROOT=Path(os.environ.get('NK_ROOT',FILES))
STAGE=Path(os.environ['DEFLATE_STAGE']) if os.environ.get('DEFLATE_STAGE') else None
SCRATCH=tempfile.TemporaryDirectory(prefix='nk-deflate-',dir=Path(tempfile.gettempdir()).resolve())
os.environ['WORDICON_TEST_MODE']='1'
os.environ['WORDICON_PREVIEW']='1'
os.environ['WORDICON_STATE']=SCRATCH.name
sys.path[:0]=([str(STAGE/'modified/scripts')] if STAGE else [])+[str(FILES/'scripts'),str(ROOT/'scripts'),str(ROOT/'src'),str(ROOT)]
if STAGE:
    import importlib.util
    for name,path in [('operation_costs',STAGE/'modified/scripts/operation_costs.py'),('actions',STAGE/'modified/scripts/actions.py'),('deflate_workflow',FILES/'scripts/deflate_workflow.py')]:
        spec=importlib.util.spec_from_file_location(name,path)
        module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
import actions
import operation_costs as costs
import deflate_workflow as dw
import server
import gate
import federation
import operations as ops
import producers
import wordicon_cli as cli
import workspace_identity

if STAGE:
    server.deflate_workflow=dw
    tree=ast.parse((STAGE/'modified/server.py').read_text())
    names={'_start_deflate_reading','_shape_investigation_view','api_operations_start','deflate_reading_page'}
    for fn in tree.body:
        if not isinstance(fn,ast.FunctionDef) or not (fn.name in names or fn.name.startswith('api_deflate_')): continue
        if fn.name in server.app.view_functions:
            fn.decorator_list=[]
            exec(compile(ast.Module(body=[fn],type_ignores=[]),str(STAGE/'modified/server.py'),'exec'),server.__dict__)
            server.app.view_functions[fn.name]=server.__dict__[fn.name]
        else:
            exec(compile(ast.Module(body=[fn],type_ignores=[]),str(STAGE/'modified/server.py'),'exec'),server.__dict__)


def encoded(obj): return json.dumps(obj,sort_keys=True).encode()
def digest(raw): return hashlib.sha256(raw).hexdigest()


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='nk-deflate-case-',dir=Path(tempfile.gettempdir()).resolve())
        cli.LOCAL_STATE=Path(self.temp.name)
        workspace_identity.ensure()
        federation.register_connector('deflate-test','deflate','http://127.0.0.1:31888',dev_loopback=True)
        federation.pin_key('deflate-test',(ROOT/'tests/fixtures/federation/deflate.fixture.pub.b64').read_text().strip())
        self.client=server.app.test_client()
        self.client.set_cookie(gate.SESSION_COOKIE,gate.issue_session('fixture')['token'])
        self.dep=(ROOT/'tests/fixtures/federation/deflate.exemplar.deposition.json').read_bytes()
        self.calls=[];self.plans={};self.jobs={};self.remote={};self.attempts=[]
        self.lost_start=False;self.hide_request=False;self.tamper_artifact=False
        self.hook=None

    def tearDown(self): self.temp.cleanup()

    def response(self,obj):
        raw=obj if isinstance(obj,bytes) else encoded(obj)
        try: parsed=json.loads(raw)
        except ValueError: parsed=None
        return {'ok':True,'json':parsed,'raw':raw,'status':200,'delivery':'delivered'}

    def ref(self,bid,name,raw):
        path='/api/bridge/jobs/'+bid+'/artifacts/'+name
        self.remote[path]=raw
        return {'name':name,'sha256':digest(raw),'bytes':len(raw),'path':path}

    def fixture(self,connector,method,path,body=None,auth='none'):
        self.calls.append((method,path,copy.deepcopy(body)))
        self.assertEqual(auth,'none')
        if path=='/api/bridge/prepare':
            plan={**copy.deepcopy(body),'contract':dw.CONTRACT,'created_at':'2026-10-18T00:00:00Z','ready':True,'blockers':[],
                'model':None,'outbound':[],'exclusions':[],'estimate_basis':'fixture'}
            if body['reading_enabled']:
                card=costs.rate_card('anthropic','claude-sonnet-5-5')
                plan['model']={'provider':'anthropic','model':'claude-sonnet-5-5','priced':True,'mock':False,
                    'rate_card':{'id':'fixture-known-rate','per_million':{r['category']:r['usd_per_million'] for r in card['categories']}}}
            sha=federation.payload_sha256(plan);pid='p_'+sha;self.plans[pid]=plan
            return self.response({'plan':plan,'plan_id':pid,'plan_sha256':sha,'ready':True,'blockers':[]})
        if path=='/api/bridge/start':
            oid=body['request_id'];bid='b_'+digest(oid.encode())[:32];plan=self.plans[body['plan_id']]
            dep=json.loads(self.dep);rid=dep['object']['id']
            job={'contract':dw.CONTRACT,'bridge_id':bid,'request_id':oid,'plan_id':body['plan_id'],'plan_sha256':body['plan_sha256'],
                'plan':copy.deepcopy(plan),'state':'completed','finished_at':'2026-10-18T00:01:00Z','runId':rid,
                'acquisition':{'status':'completed','result_kind':'article','artifact':self.ref(bid,'acquisition.json',encoded({'source':plan['input'],'transcript':dep['payload']['transcript']['text']}))},
                'reading':{'status':'completed' if plan['reading_enabled'] else 'not_requested'},'progress':{'stage':'saved'},
                'attempts':[],'costs':{'acquisition':{'engine':'local','paid_cost_usd':0}},
                'source_artifact':self.ref(bid,'source.json',encoded({'html':'<article>Original source</article>','url':plan['input'].get('url')})),
                'result':{'runId':rid,'deposition':self.ref(bid,'deposition.json',self.dep),'transcript_sha256':dep['payload']['transcript']['sha256'],'reading_count':1,'held_count':0}}
            for idx,usage in enumerate(self.attempts,1):
                aid='model_%03d'%idx
                receipt={'attempt_id':aid,'model':'claude-sonnet-5-5','request_id':'msg_fixture_'+str(idx),'stop_reason':'max_tokens' if idx==2 else 'end_turn',
                    'usage':usage,'provider_response':{'id':'msg_fixture_'+str(idx),'model':'claude-sonnet-5-5','usage':usage},'error':None,'text':'Retained model interpretation'}
                job['attempts'].append({'attempt_id':aid,'provider':'anthropic','model':'claude-sonnet-5-5','rate_card':plan['model']['rate_card'],
                    'status':'completed' if usage else 'unknown','reserved_usd':.1,'usage':usage,'provider_response_id':receipt['request_id'],'stop_reason':receipt['stop_reason'],
                    'request':self.ref(bid,aid+'-request.json',encoded({'prompt':'untrusted source fixture','max_tokens':8192})),
                    'response':self.ref(bid,aid+'-response.json',encoded(receipt))})
            if self.hook:self.hook(job)
            self.jobs[oid]=job
            if self.lost_start:return {'ok':False,'delivery':'unknown','outcome':'unreachable','detail':'Fixture reply lost'}
            return self.response(job)
        if path.startswith('/api/bridge/requests/'):
            oid=path.rsplit('/',1)[-1]
            if self.hide_request or oid not in self.jobs:return {'ok':False,'delivery':'delivered','status':404,'outcome':'not_found'}
            return self.response(self.jobs[oid])
        if '/artifacts/' in path:
            raw=self.remote[path]
            return self.response(raw+b' ' if self.tamper_artifact else raw)
        if path.startswith('/api/bridge/jobs/'):
            return self.response(next(j for j in self.jobs.values() if j['bridge_id']==path.rsplit('/',1)[-1]))
        raise AssertionError((method,path))

    def prepare(self,**inputs):
        response=self.client.post('/api/actions/prepare',json={'action_id':dw.ACTION,'subject':{'kind':'description','text':'What does this source establish?'},
            'inputs':{'url':'https://example.test/public-source','origin':{'kind':'description','title':'Origin','text':'PRIVATE ORIGINAL PASSAGE'},**inputs}})
        self.assertEqual(response.status_code,200,response.json)
        return response.json

    def start(self,p,key='one',run=True):
        with patch.object(server,'_dispatching',return_value=True),patch.object(dw,'launch',return_value=True):
            response=self.client.post('/api/operations',json={'prepared_id':p['prepared_id'],'request_key':key})
        if run and response.status_code==200 and not response.json.get('repeated'):dw._run(response.json['operation_id'])
        return response

    def run_one(self,**inputs):
        with patch.object(producers,'_request',side_effect=self.fixture):
            p=self.prepare(**inputs);response=self.start(p)
        self.assertEqual(response.status_code,200,response.json)
        return p,response.json['operation_id']

    def test_prepare_only_freezes_plan_and_keeps_full_origin_local(self):
        with patch.object(producers,'_request',side_effect=self.fixture):p=self.prepare()
        self.assertEqual([p[:2] for p in self.calls],[('POST','/api/bridge/prepare')])
        plan=p['inputs']['plan'];sent=self.calls[0][2]
        self.assertEqual(plan['origin']['text'],'PRIVATE ORIGINAL PASSAGE')
        self.assertNotIn('PRIVATE ORIGINAL PASSAGE',json.dumps(sent))
        self.assertEqual(sent['allowance_usd'],0)
        self.assertFalse(sent['reading_enabled'])
        self.assertEqual(plan['producer_prepare_artifact']['sha256'],digest(plan['producer_prepare_bytes'].encode()))
        self.assertIn('purpose',plan['limitations'][0])

    def test_complete_save_reopen_signed_bytes_local_and_no_second_start(self):
        p,oid=self.run_one()
        with patch.object(producers,'_request',side_effect=AssertionError('No network on local reads')):
            repeated=self.start(p)
            self.assertTrue(repeated.json['repeated'])
            got=self.client.get('/api/deflate/operations/'+oid)
            self.assertEqual(got.status_code,200,got.json)
            self.assertEqual(got.json['status'],'complete',got.json['error'])
            self.assertTrue(got.json['custody']['verification']['ok'])
            self.assertEqual(got.json['deposition'],json.loads(self.dep))
            saved=self.client.post('/api/deflate/operations/'+oid+'/save',json={})
            self.assertTrue(saved.json['saved'])
        before=ops.db_path().read_bytes()
        with patch.object(producers,'_request',side_effect=AssertionError('No network')),patch.object(ops,'_connect',side_effect=AssertionError('No writable database')):
            reopened=dw.view(dw._read_operation(oid));listing=dw.list_views()
        self.assertEqual(before,ops.db_path().read_bytes())
        self.assertEqual(reopened['deposition'],got.json['deposition']);self.assertTrue(reopened['saved'])
        self.assertEqual(listing[0]['operation_id'],oid)
        self.assertEqual(sum(m=='POST' and p=='/api/bridge/start' for m,p,_ in self.calls),1)
        self.assertEqual(reopened['costs']['estimated_cost_usd'],0)
        self.assertEqual(len([r for r in costs._events(oid) if r['event_type']=='source_cost']),1)
        self.assertIn('not requested',reopened['progress'])
        for a in reopened['artifacts']:
            self.assertEqual(digest(self.client.get(a['url']).data),a['sha256'])
        self.assertTrue(any(a['name']=='producer-source.json' for a in reopened['artifacts']))

    def test_authenticated_routes_and_empty_read_do_not_create_database(self):
        self.assertEqual(server.app.test_client().get('/api/deflate/status').status_code,401)
        self.assertEqual(server.app.test_client().post('/api/deflate/uploads?name=x.mp3',data=b'ID3fixture').status_code,401)
        self.assertEqual(self.client.get('/api/deflate/operations/missing').status_code,404)
        self.assertFalse(ops.db_path().exists())

    def test_nested_stage_errors_survive_new_finish_and_historical_readonly_reopen(self):
        for field, code in (("reading", "sensitive_response"), ("acquisition", "decoder_unavailable")):
            with self.subTest(stage=field):
                def incomplete(job):
                    job['state']='partial';job[field].update(status='error',error={'code':code,'message':'The stage could not finish.'})
                self.hook=incomplete
                with patch.object(producers,'_request',side_effect=self.fixture):
                    proposal=self.prepare();reply=self.start(proposal,key='nested-'+field)
                self.assertEqual(reply.status_code,200,reply.json);oid=reply.json['operation_id']
                op=dw._read_operation(oid)
                self.assertIn(code,op['last_error'])
                # Historical rows predate this display fix. Reading their
                # retained nested failure must not repair or rewrite them.
                ops.mark(oid,op['status'],last_error='')
                original=dw._read_operation(oid);original_cost=costs.total(original)
                before={p.relative_to(cli.LOCAL_STATE):p.read_bytes() for p in cli.LOCAL_STATE.rglob('*') if p.is_file()}
                with patch.object(producers,'_request',side_effect=AssertionError('No producer read')),patch.object(ops,'_connect',side_effect=AssertionError('No writable database')):
                    response=self.client.get('/api/deflate/operations/'+oid)
                    listing=dw.list_views()
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.json['error'],field.title()+' error ('+code+'): The stage could not finish.')
                self.assertIn(code,next(v for v in listing if v['operation_id']==oid)['error'])
                self.assertEqual(response.json['costs'],original_cost)
                self.assertEqual(response.json['result_ref'],original['result_ref'])
                self.assertEqual(response.json['status'],original['status'])
                self.assertEqual(before,{p.relative_to(cli.LOCAL_STATE):p.read_bytes() for p in cli.LOCAL_STATE.rglob('*') if p.is_file()})
                self.assertEqual(dw._read_operation(oid)['last_error'],'')

    def test_retained_stage_error_is_bounded_sanitized_and_does_not_hide_custody_failure(self):
        message='Bearer '+('fixture' * 20)+' <img src=x onerror=alert(1)> '+('x' * 1000)
        error=dw._producer_error({'reading':{'error':{'code':'sensitive_response','message':message}},'acquisition':{'error':{'code':'decoder_unavailable'}}})
        self.assertIn('sensitive_response',error);self.assertIn('decoder_unavailable',error)
        self.assertIn('[redacted]',error);self.assertNotIn('fixture' * 20,error)
        self.assertLess(len(error),850)
        self.assertEqual(dw._producer_error({'reading':{'status':'partial','message':'Progress is not a named error'}}),'')
        self.hook=lambda job:job['reading'].update(error={'code':'sensitive_response','message':'Retained failure'})
        _,oid=self.run_one()
        with patch.object(dw,'_current_deposition',return_value=(None,{'ok':False,'why':'Current custody verification failed'})):
            self.assertEqual(dw.view(dw._read_operation(oid))['error'],'Current custody verification failed')

    def test_upload_is_exact_local_then_staged_only_after_start(self):
        raw=b'ID3'+b'\x00'*64+b'chosen audio'
        response=self.client.post('/api/deflate/uploads?name=chosen.mp3',data=raw,content_type='audio/mpeg')
        self.assertEqual(response.status_code,201,response.json)
        upload=response.json['upload'];record,path=dw.load_upload(upload['upload_id'])
        self.assertEqual(path.read_bytes(),raw);self.assertEqual(path.stat().st_mode&0o777,0o600)
        self.assertEqual(upload['sha256'],digest(raw));self.assertNotIn(str(cli.LOCAL_STATE),json.dumps(upload))
        def remote(c,u,p):
            self.assertEqual(p.read_bytes(),raw)
            return self.response({'upload':{'id':'u_'+u['sha256'],**{k:u[k] for k in ('name','sha256','bytes','format')}}})
        with patch.object(producers,'_request',side_effect=self.fixture),patch.object(dw,'_upload_request',side_effect=remote) as up:
            prepared=self.prepare(upload_id=upload['upload_id']);up.assert_not_called()
            started=self.start(prepared);self.assertEqual(up.call_count,1)
        self.assertEqual(dw._read_operation(started.json['operation_id'])['status'],'complete')
        self.assertEqual(path.read_bytes(),raw)
        got=self.client.get('/api/deflate/operations/'+started.json['operation_id']+'/original')
        self.assertEqual(got.data,raw);self.assertEqual(got.mimetype,'audio/mpeg');self.assertEqual(got.headers['X-Content-SHA256'],digest(raw));got.close()
        self.assertEqual(self.client.get('/api/deflate/operations/missing/original').status_code,404)
        sent=next(body for method,url,body in self.calls if url=='/api/bridge/start')
        self.assertEqual(sent['upload_id'],'u_'+digest(raw))

    def test_upload_and_url_reject_unsupported_metadata_and_corrupt_bytes(self):
        for name,data in [('bad.txt',b'not media'),('../chosen.mp3',b'ID3'+b'x'*20),(('sk-'+'ant-api03-secretsecretsecretsecret.mp3'),b'ID3'+b'x'*20)]:
            with self.assertRaises(dw.WorkflowError):dw.stage_upload(io.BytesIO(data),name,len(data))
        with self.assertRaises(dw.WorkflowError):dw.stage_upload(io.BytesIO(b'ID3abc'),'x.mp3',90)
        for url in ['http://127.0.0.1/x','https://user:pass@example.com','https://example.com/x?api_key=secretsecret','https://example.com/x#part']:
            with self.assertRaises(dw.WorkflowError):dw._url(url)
        record=dw.stage_upload(io.BytesIO(b'ID3'+b'x'*20),'good.mp3',23)
        _,path=dw.load_upload(record['upload_id']);path.write_bytes(b'ID3'+b'y'*20)
        with self.assertRaises(dw.WorkflowError):dw.load_upload(record['upload_id'])

    def test_lost_start_reconciles_by_get_then_never_replays(self):
        self.lost_start=True
        p,oid=self.run_one()
        self.assertEqual(dw._read_operation(oid)['status'],'unknown')
        with patch.object(producers,'_request',side_effect=self.fixture):dw._run(oid,resume=True);dw._run(oid,resume=True)
        self.assertEqual(dw._read_operation(oid)['status'],'complete')
        self.assertEqual(sum(m=='POST' and p=='/api/bridge/start' for m,p,_ in self.calls),1)
        self.assertTrue(any('/requests/' in p for _,p,_ in self.calls))

    def test_uncertain_start_404_never_grants_paid_replay(self):
        self.lost_start=True;self.hide_request=True
        _,oid=self.run_one(reading_enabled=True)
        with patch.object(producers,'_request',side_effect=self.fixture):dw._run(oid,resume=True);dw._run(oid,resume=True)
        self.assertEqual(dw._read_operation(oid)['status'],'unknown')
        self.assertEqual(sum(m=='POST' and p=='/api/bridge/start' for m,p,_ in self.calls),1)

    def test_attempts_cache_categories_truncation_and_duplicate_poll_count_once(self):
        self.attempts=[{'input_tokens':1000,'output_tokens':100,'cache_read_input_tokens':500,'cache_creation_input_tokens':100,
            'cache_creation':{'ephemeral_5m_input_tokens':60,'ephemeral_1h_input_tokens':40}}, {'input_tokens':200,'output_tokens':40}]
        _,oid=self.run_one(reading_enabled=True)
        op=dw._read_operation(oid);self.assertEqual(op['status'],'complete',op['last_error'])
        with patch.object(producers,'_request',side_effect=self.fixture):dw._ingest_attempts(op,dw.connector(),self.jobs[oid])
        rows=costs._events(oid);settled=[r for r in rows if r['event_type']=='settlement']
        self.assertEqual(len(settled),2);self.assertEqual(settled[1]['stop_reason'],'max_tokens')
        self.assertEqual(settled[0]['estimated_cost_usd'],.00336)
        self.assertEqual(costs.total(op)['estimated_cost_usd'],.00416)
        self.assertIsNone(costs.total(op)['actual_cost_usd'])
        self.assertEqual({r['category']:r['count'] for r in settled[0]['usage']}['cache_creation_1h_input_tokens'],40)
        self.assertTrue(all(r['receipt_artifact']['sha256'] for r in settled))

    def test_unknown_usage_is_not_reported_free(self):
        self.attempts=[None]
        _,oid=self.run_one(reading_enabled=True)
        total=costs.total(dw._read_operation(oid))
        self.assertIsNone(total['estimated_cost_usd']);self.assertIsNone(total['actual_cost_usd'])
        self.assertTrue(total['unknown_components'])

    def test_source_cost_failure_cannot_finalize_without_receipt(self):
        real=costs._append
        def fail(oid,row,**kwargs):
            if row['event_type']=='source_cost':raise OSError('fixture accounting write interrupted')
            return real(oid,row,**kwargs)
        with patch.object(costs,'_append',side_effect=fail):_,oid=self.run_one()
        op=dw._read_operation(oid);self.assertEqual(op['status'],'unknown')
        self.assertNotIn('result_artifact',op['result_ref'])
        with patch.object(producers,'_request',side_effect=self.fixture):dw._run(oid,resume=True)
        self.assertEqual(dw._read_operation(oid)['status'],'complete')
        self.assertEqual(len([r for r in costs._events(oid) if r['event_type']=='source_cost']),1)
        self.assertEqual(sum(m=='POST' and p=='/api/bridge/start' for m,p,_ in self.calls),1)

    def test_hash_mismatch_keeps_received_bytes_without_accepting_result(self):
        self.tamper_artifact=True
        _,oid=self.run_one();op=dw._read_operation(oid)
        self.assertEqual(op['status'],'unknown');self.assertNotIn('result_artifact',op['result_ref'])
        self.assertTrue(any(r['name'].startswith('producer-') for r in op['result_ref']['kept']))

    def test_wrong_result_identity_cannot_replace_saved_plan(self):
        self.hook=lambda job:job.update(request_id='another-operation')
        _,oid=self.run_one();op=dw._read_operation(oid)
        self.assertEqual(op['status'],'unknown');self.assertIn('different reading',op['last_error'])

    def test_changed_connector_refuses_before_start(self):
        with patch.object(producers,'_request',side_effect=self.fixture):p=self.prepare()
        federation.register_connector('deflate-test','deflate','http://127.0.0.1:31889',dev_loopback=True)
        with patch.object(producers,'_request',side_effect=AssertionError('No dispatch')):response=self.start(p)
        self.assertEqual(response.status_code,409,response.json);self.assertTrue(response.json['nothing_was_sent'])

    def test_signed_custody_does_not_accept_unverified_reading(self):
        dep=json.loads(self.dep);dep['payload']['claims']['fixture_change']='not signed';self.dep=encoded(dep)
        _,oid=self.run_one();got=dw.view(dw._read_operation(oid))
        self.assertFalse(got['custody']['verification']['ok']);self.assertIsNone(got['deposition'])
        self.assertIn('Partial',got['progress'])
        self.assertTrue(got['result_ref']['deposition_artifact'])

    def test_reopen_rechecks_current_pin_without_rewriting_historical_custody(self):
        _,oid=self.run_one()
        op=dw._read_operation(oid); historic=copy.deepcopy(op['result_ref']['custody'])
        key=federation.get_connector('deflate-test')['trusted_keys'][0]['key_id']
        federation.unpin_key('deflate-test',key)
        before={str(p.relative_to(cli.LOCAL_STATE)):digest(p.read_bytes()) for p in cli.LOCAL_STATE.rglob('*') if p.is_file()}
        with patch.object(producers,'_request',side_effect=AssertionError('No network')),patch.object(ops,'_connect',side_effect=AssertionError('No writable database')),patch.object(federation,'import_package',side_effect=AssertionError('No reimport')):
            view=dw.view(dw._read_operation(oid))
            raw=dw.artifact(op,op['result_ref']['deposition_artifact']['name'])
        self.assertIsNone(view['deposition'])
        self.assertFalse(view['current_verification']['ok'])
        self.assertIn('pinned-key',view['error'])
        self.assertEqual(view['custody'],historic)
        self.assertTrue(view['custody']['verification']['ok'])
        self.assertEqual(raw,self.dep)
        self.assertEqual(before,{str(p.relative_to(cli.LOCAL_STATE)):digest(p.read_bytes()) for p in cli.LOCAL_STATE.rglob('*') if p.is_file()})

    def test_signed_inconsistent_run_hash_is_withheld_on_read_with_original_preserved(self):
        import base64
        from cryptography.hazmat.primitives import serialization
        key=serialization.load_der_private_key(base64.b64decode((ROOT/'tests/fixtures/producers/deflate.fixture.key.pkcs8.b64').read_text()),password=None)
        dep=json.loads(self.dep);dep['payload']['claims']['run']['transcript']['sha256']='f'*64
        dep['payload_sha256']=federation.payload_sha256(dep['payload'])
        dep['signature']['value']=base64.b64encode(key.sign(federation.canonical_json(dep['payload']))).decode()
        self.dep=encoded(dep)
        _,oid=self.run_one();op=dw._read_operation(oid)
        before=ops.db_path().read_bytes()
        with patch.object(producers,'_request',side_effect=AssertionError('No network')),patch.object(ops,'_connect',side_effect=AssertionError('No writable database')):
            view=dw.view(op)
        self.assertTrue(view['custody']['verification']['ok'])
        self.assertFalse(view['current_verification']['ok'])
        self.assertIsNone(view['deposition']);self.assertIn('hashes do not agree',view['error'])
        self.assertEqual(dw.artifact(op,op['result_ref']['deposition_artifact']['name']),self.dep)
        self.assertEqual(before,ops.db_path().read_bytes())

    def test_signed_empty_transcript_cannot_become_a_current_source(self):
        import base64
        from cryptography.hazmat.primitives import serialization
        key=serialization.load_der_private_key(base64.b64decode((ROOT/'tests/fixtures/producers/deflate.fixture.key.pkcs8.b64').read_text()),password=None)
        dep=json.loads(self.dep);source=' \n';source_hash=digest(source.encode())
        dep['payload']['transcript'].update(text=source,sha256=source_hash)
        dep['payload']['claims']['run']['transcript']['sha256']=source_hash
        dep['payload_sha256']=federation.payload_sha256(dep['payload'])
        dep['signature']['value']=base64.b64encode(key.sign(federation.canonical_json(dep['payload']))).decode()
        self.dep=encoded(dep)
        _,oid=self.run_one();op=dw._read_operation(oid);view=dw.view(op)
        self.assertTrue(view['custody']['verification']['ok'])
        self.assertFalse(view['current_verification']['ok']);self.assertIsNone(view['deposition'])
        self.assertEqual(dw.artifact(op,op['result_ref']['deposition_artifact']['name']),self.dep)

    def test_terminal_export_pending_does_not_finalize_until_settled(self):
        calls=[0]
        original=self.fixture
        def fixture(c,m,p,b=None,auth='none'):
            result=original(c,m,p,b,auth)
            if m=='GET' and p.startswith('/api/bridge/jobs/') and '/artifacts/' not in p:
                calls[0]+=1
                if calls[0]==1:
                    job=copy.deepcopy(result['json']);job.pop('finished_at');job['state']='exporting';job['result']=None
                    return self.response(job)
            return result
        with patch.object(producers,'_request',side_effect=fixture),patch.object(dw.time,'sleep'):
            prepared=self.prepare();response=self.start(prepared)
        self.assertEqual(calls[0],2);self.assertEqual(dw._read_operation(response.json['operation_id'])['status'],'complete')

    def test_operation_origin_freezes_saved_result_and_receipts_gap(self):
        import opencase,receipts_projection
        parent,_=ops.reserve(request_key='parent',kind='investigation',action_id=opencase.ACTION,
            execution={'plan':{'question':'What remains missing?','subject_name':'Fixture Judge','subject_type':'federal_judge_district',
                'jurisdiction':'United States','origin':{'kind':'question','text':'Original question'},'synthesis':{'enabled':False}}})
        raw=encoded({'findings':[],'source_statuses':{'courtlistener':{'status':'credential_failure','detail':'API key unavailable'}},'model_runs':[],'actual_cost_usd':0})
        kept=producers.keep_artifact(parent['op_id'],'result.json',raw)
        ops.mark(parent['op_id'],'complete',result_ref={'result_artifact':kept,'kept':[kept]});parent=ops.get(parent['op_id'])
        projection=receipts_projection.from_operation(parent);suggestion=projection['continuations'][0]
        origin={'kind':'operation','operation_id':parent['op_id'],'receipts_continuation':{'operation_id':parent['op_id'],'id':suggestion['id'],'projection_sha256':projection['projection_sha256']}}
        with patch.object(producers,'_request',side_effect=self.fixture):prepared=self.prepare(origin=origin)
        plan=prepared['inputs']['plan']
        self.assertEqual(plan['follow_up_of'],parent['op_id']);self.assertEqual(plan['origin']['result_sha256'],digest(raw))
        self.assertEqual(plan['origin']['parent_origin']['text'],'Original question')
        self.assertEqual(plan['origin']['receipts_continuation']['gap_id'],suggestion['gap_id'])
        self.assertNotIn('Original question',json.dumps(plan['producer_request']))
        self.assertEqual(producers.artifact_bytes(parent['op_id'],'result.json'),raw)

    def test_pending_known_job_restart_only_queries_existing_identity(self):
        with patch.object(producers,'_request',side_effect=self.fixture):
            p=self.prepare();response=self.start(p,run=False);oid=response.json['operation_id']
            plan=p['inputs']['plan']
            job=self.fixture(dw.connector(),'POST','/api/bridge/start',{'request_id':oid,'plan_id':plan['plan_id'],'plan_sha256':plan['plan_sha256']})['json']
            ops.mark(oid,'unknown',result_ref={'upstream_id':job['bridge_id']})
        with patch.object(dw,'launch',return_value=True) as launch:
            self.assertEqual(dw.resume_known(),[oid]);launch.assert_called_once_with(oid,resume=True)
        self.calls=[]
        with patch.object(producers,'_request',side_effect=self.fixture):dw._run(oid,resume=True)
        self.assertEqual(dw._read_operation(oid)['status'],'complete')
        self.assertTrue(all(m=='GET' for m,_,_ in self.calls))

    def test_workspace_replacement_refuses_frozen_proposal(self):
        with patch.object(producers,'_request',side_effect=self.fixture):prepared=self.prepare()
        with patch.object(workspace_identity,'read',return_value={'workspace_id':'workspace_'+'a'*32}),patch.object(producers,'_request',side_effect=AssertionError('No cross-store dispatch')):
            response=self.start(prepared)
        self.assertEqual(response.status_code,409)
        self.assertIn('workspace identity',response.json['error'])

    def test_same_start_key_with_changed_plan_is_refused(self):
        with patch.object(producers,'_request',side_effect=self.fixture):
            first=self.prepare();second=self.prepare(url='https://example.test/another-source')
            one=self.start(first,run=False);two=self.start(second,run=False)
        self.assertEqual(one.status_code,200);self.assertEqual(two.status_code,409)
        self.assertFalse(any(path=='/api/bridge/start' for _,path,_ in self.calls))

    def test_optional_model_unknown_price_refused_at_prepare(self):
        original=self.fixture
        def changed(c,m,p,b=None,auth='none'):
            r=original(c,m,p,b,auth)
            if p=='/api/bridge/prepare':
                obj=r['json'];obj['plan']['model']['model']='unpriced-model';obj['plan_sha256']=federation.payload_sha256(obj['plan']);obj['plan_id']='p_'+obj['plan_sha256'];return self.response(obj)
            return r
        with patch.object(producers,'_request',side_effect=changed),self.assertRaises(dw.WorkflowError):
            dw.prepare('Read it',{'url':'https://example.test/source','reading_enabled':True})
        self.assertEqual(len(self.calls),1)

    def test_exact_model_receipt_mismatch_is_held_without_accepting_cost(self):
        self.attempts=[{'input_tokens':20,'output_tokens':10}]
        def alter(job):
            attempt=job['attempts'][0];path=attempt['response']['path'];receipt=json.loads(self.remote[path]);receipt['provider_response']['usage']['input_tokens']=9999
            attempt['response']=self.ref(job['bridge_id'],attempt['response']['name'],encoded(receipt))
        self.hook=alter
        _,oid=self.run_one(reading_enabled=True);op=dw._read_operation(oid)
        self.assertEqual(op['status'],'unknown');self.assertIn('exact provider response',op['last_error'])
        rows=costs._events(oid)
        self.assertEqual([r['event_type'] for r in rows],['reservation'])
        self.assertEqual(costs.total(op)['reserved_usd'],.1)

    def test_provider_model_drift_holds_charge_but_preserves_signed_source(self):
        self.attempts=[{'input_tokens':20,'output_tokens':10}]
        def drift(job):
            attempt=job['attempts'][0];receipt=json.loads(self.remote[attempt['response']['path']])
            receipt['model']='unpriced-provider-model';receipt['provider_response']['model']=receipt['model']
            attempt['response']=self.ref(job['bridge_id'],attempt['response']['name'],encoded(receipt));attempt['status']='unknown';job['state']='unknown'
        self.hook=drift
        _,oid=self.run_one(reading_enabled=True);op=dw._read_operation(oid);view=dw.view(op)
        self.assertEqual(op['status'],'unknown')
        self.assertTrue(view['result_ref']['result_artifact']);self.assertTrue(view['custody']['verification']['ok'])
        self.assertEqual(view['deposition'],json.loads(self.dep))
        self.assertIsNone(view['costs']['estimated_cost_usd']);self.assertEqual(view['costs']['reserved_usd'],.1)
        self.assertEqual(view['result_ref']['accounting_issues'][0]['kind'],'provider_model_changed')
        before=len(self.calls)
        with patch.object(producers,'_request',side_effect=self.fixture):dw._run(oid,resume=True)
        self.assertEqual(len(self.calls),before)

if __name__=='__main__':unittest.main()
