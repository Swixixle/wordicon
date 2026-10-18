"""Read-only Deflate history from scratch operation artifacts and signed fixtures."""
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

STAGE = Path(__file__).resolve().parents[1]
MAIN = STAGE if (STAGE / "scripts/federation.py").is_file() else STAGE.parents[1] / "nikodemus"
sys.path[:0] = [str(MAIN), str(MAIN / "scripts")]
os.environ["WORDICON_TEST_MODE"] = "1"
BOOT = tempfile.TemporaryDirectory(prefix="nk-deflate-history-import-", dir=Path(tempfile.gettempdir()).resolve())
os.environ["WORDICON_STATE"] = BOOT.name
import wordicon_cli as cli
import operations as ops
import producers
import federation
import workspace_identity
spec = importlib.util.spec_from_file_location("reviewed_deflate_history", STAGE / "scripts/capture_history.py")
history = importlib.util.module_from_spec(spec); spec.loader.exec_module(history)


class DeflateHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nk-deflate-history-", dir=Path(tempfile.gettempdir()).resolve())
        self.prior = cli.LOCAL_STATE; cli.LOCAL_STATE = Path(self.temp.name)
        workspace_identity.ensure()
        fixtures = MAIN / "tests/fixtures"
        self.envelope = json.loads((fixtures / "federation/deflate.exemplar.deposition.json").read_text())
        federation.register_connector("fixture_deflate", "deflate", "http://127.0.0.1:3123", dev_loopback=True)
        federation.pin_key("fixture_deflate", (fixtures / "federation/deflate.fixture.pub.b64").read_text().strip())
        from cryptography.hazmat.primitives import serialization
        self.key = serialization.load_der_private_key(base64.b64decode((fixtures / "producers/deflate.fixture.key.pkcs8.b64").read_text()), password=None)
        self.envelope["payload"]["claims"]["passages"][0]["readingGate"] = {"status": "ready"}
        self.envelope["payload"]["claims"]["passages"][0]["reading"] = {"deflated":{"hs":"PRIVATE MODEL READING"}}
        self.parent, _ = ops.reserve(request_key="parent", kind="investigation", action_id="investigate.opencase.question", execution={"plan":{"question":"Parent question"}})
        self.plan = {"producer_plan":{"contract":"deflate.bridge.v1","reading_enabled":True,"allowance_usd":.5},
                     "connector":{"connector_id":"fixture_deflate"}, "question":"What does this source say?",
                     "origin":{"kind":"operation","operation_id":self.parent["op_id"]},"follow_up_of":self.parent["op_id"]}
        self.plan["plan_sha256"] = federation.payload_sha256(self.plan["producer_plan"])
        self.plan["plan_id"] = "p_" + self.plan["plan_sha256"]
        self.op, _ = ops.reserve(request_key="deflate-child", kind="investigation", action_id="investigate.deflate.read", execution={"plan":self.plan})
        self.bid = "b_" + hashlib.sha256(self.op["op_id"].encode()).hexdigest()[:32]
        self.refs = []

    def tearDown(self):
        cli.LOCAL_STATE = self.prior; self.temp.cleanup()

    def hashes(self):
        return {str(p.relative_to(cli.LOCAL_STATE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cli.LOCAL_STATE.rglob("*") if p.is_file()}

    def keep(self, name, value):
        raw = value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False).encode()
        ref = producers.keep_artifact(self.op["op_id"],name,raw); self.refs.append(ref)
        remote = {**ref,"path":f"/api/bridge/jobs/{self.bid}/artifacts/{ref['name']}","exact":True}
        return ref, remote

    def save(self, mutate=None, *, missing_request=False):
        env = copy.deepcopy(self.envelope)
        if mutate: mutate(env)
        env["payload_sha256"] = federation.payload_sha256(env["payload"])
        env["signature"]["value"] = base64.b64encode(self.key.sign(federation.canonical_json(env["payload"]))).decode()
        dep, remote_dep = self.keep("producer-deposition.json",env)
        req, remote_req = self.keep("producer-model-request.json",b'{"prompt":"PRIVATE MODEL INPUT"}')
        response, remote_response = self.keep("producer-model-response.json",b'{"text":"PRIVATE MODEL OUTPUT"}')
        acq, remote_acq = self.keep("producer-acquisition.json",b'{"result":{"text":"PRIVATE ACQUIRED BODY"}}')
        job = {"contract":"deflate.bridge.v1","request_id":self.op["op_id"],"bridge_id":self.bid,
               "plan":self.plan["producer_plan"],"plan_id":self.plan["plan_id"],"plan_sha256":self.plan["plan_sha256"],
               "runId":env["object"]["id"],"state":"partial","acquisition":{"status":"done","result_kind":"transcript","artifact":remote_acq},
               "reading":{"status":"partial"},"attempts":[{"attempt_id":"model_001","producer_call_id":"call_fixture","provider":"anthropic","model":"fixture-model",
                    "purpose":"deflate","status":"completed","request":remote_req,"response":remote_response}],
               "result":{"runId":env["object"]["id"],"deposition":remote_dep,"transcript_sha256":env["payload"]["transcript"]["sha256"]}}
        result, _ = self.keep("bridge-result.json",job)
        ref = {"kept":self.refs,"result_artifact":result,"deposition_artifact":dep,"upstream_id":self.bid,"custody":{"verification":{"ok":True}}}
        if missing_request: ref["kept"] = [r for r in self.refs if r!=req]
        ops.mark(self.op["op_id"],"complete",result_ref=ref)
        return job, ref

    def readonly(self):
        with patch.object(ops,"_connect",side_effect=AssertionError("no SQLite init")), patch.object(producers,"_request",side_effect=AssertionError("no producer request")), patch.object(federation,"import_package",side_effect=AssertionError("no custody re-import")):
            return history.view(operation_id=self.op["op_id"])

    def test_verified_transcript_readings_and_attempts_use_explicit_cross_engine_links(self):
        self.save(); before=self.hashes(); view=self.readonly()
        self.assertEqual({o["operation_id"] for o in view["nodes"]["operations"]},{self.op["op_id"],self.parent["op_id"]})
        self.assertTrue(any(e["relation"]=="follow_up" and e["from"]==self.parent["op_id"] for e in view["links"]))
        current=next(o for o in view["nodes"]["operations"] if o["operation_id"]==self.op["op_id"])
        self.assertEqual(current["url"],"/deflate-reading?operation="+self.op["op_id"])
        source=view["nodes"]["evidence"][0]
        self.assertEqual(source["body_sha256"],self.envelope["payload"]["transcript"]["sha256"])
        self.assertEqual(source["evidence_kind"],"captured_source_text")
        readings=[a for a in view["nodes"]["answers"] if a.get("kind")=="deflate_passage_reading"]
        self.assertEqual({r["current_status"] for r in readings},{"held","reading_available"})
        self.assertTrue(all(not r["answer_available"] for r in readings))
        attempt=next(a for a in view["nodes"]["attempts"] if a["kind"]=="producer_model_attempt")
        self.assertEqual(attempt["detail"]["attempt_id"],"model_001")
        self.assertEqual({e["relation"] for e in view["links"] if e["from"]==attempt["id"]},{"captured_status","captured_request","captured_response"})
        text=json.dumps(view)
        for secret in ("PRIVATE MODEL INPUT","PRIVATE MODEL OUTPUT","PRIVATE ACQUIRED BODY","PRIVATE MODEL READING",self.envelope["payload"]["transcript"]["text"]): self.assertNotIn(secret,text)
        self.assertEqual(before,self.hashes())

    def test_wrong_operation_identity_retains_artifacts_but_withholds_projection(self):
        job,ref=self.save(); job["request_id"]="another_operation"
        new,_=self.keep("wrong-result.json",job);ref.update(result_artifact=new,kept=self.refs);ops.mark(self.op["op_id"],result_ref=ref)
        view=self.readonly()
        self.assertEqual(view["nodes"]["evidence"],[])
        self.assertIn("deflate_result_identity",{g["kind"] for g in view["gaps"]})

    def test_unpinned_signature_retains_attempts_without_promoting_signed_text(self):
        self.save(); key=federation.get_connector("fixture_deflate")["trusted_keys"][0]["key_id"]
        federation.unpin_key("fixture_deflate",key)
        before=self.hashes(); view=self.readonly()
        self.assertEqual(view["nodes"]["evidence"],[])
        self.assertEqual(len(view["nodes"]["attempts"]),1)
        self.assertIn("deflate_deposition_unverified",{g["kind"] for g in view["gaps"]})
        self.assertEqual(before,self.hashes())

    def test_changed_deposition_bytes_never_replace_the_saved_source(self):
        _,ref=self.save(); (producers.artifact_dir(self.op["op_id"])/ref["deposition_artifact"]["name"]).write_bytes(b'{"payload":"SUBSTITUTE"}')
        view=self.readonly();self.assertEqual(view["nodes"]["evidence"],[])
        self.assertIn("artifact_integrity",{g["kind"] for g in view["gaps"]})
        self.assertNotIn("SUBSTITUTE",json.dumps(view))

    def test_signed_wrong_transcript_hash_cannot_become_usable_reading(self):
        self.save(lambda e:e["payload"]["transcript"].update(text="Different captured words"))
        view=self.readonly(); self.assertEqual(view["nodes"]["evidence"],[])
        self.assertIn("deflate_transcript_integrity",{g["kind"] for g in view["gaps"]})
        self.assertFalse(any(a.get("reading_available") for a in view["nodes"]["answers"]))

    def test_signed_empty_source_does_not_establish_a_usable_reading(self):
        def empty(env):
            source = " \n"; sha = hashlib.sha256(source.encode()).hexdigest()
            env["payload"]["transcript"].update(text=source, sha256=sha)
            env["payload"]["claims"]["run"]["transcript"]["sha256"] = sha
            env["payload"]["claims"]["passages"][0]["basedOn"]["inputHash"] = sha
        self.save(empty); view = self.readonly()
        self.assertEqual(view["nodes"]["evidence"], [])
        self.assertFalse(any(a.get("reading_available") for a in view["nodes"]["answers"]))
        self.assertIn("deflate_transcript_integrity", {g["kind"] for g in view["gaps"]})

    def test_missing_request_capture_and_source_failure_remain_visible(self):
        job,ref=self.save(missing_request=True)
        job.update(export_gap="Signed export could not be saved",result=None)
        job["acquisition"].update(status="error",error={"message":"Source timeout"})
        result,_=self.keep("failed-result.json",job);ref.update(result_artifact=result);ref["kept"].append(result)
        ops.mark(self.op["op_id"],"failed",result_ref=ref)
        view=self.readonly(); kinds={g["kind"] for g in view["gaps"]}
        self.assertTrue({"deflate_capture_missing","deflate_export_gap","deflate_deposition_unverified"}.issubset(kinds))
        check=next(s for s in view["nodes"]["source_checks"] if s["kind"]=="acquisition")
        self.assertEqual(check["status"],"error");self.assertEqual(check["reason"],"Source timeout")
        self.assertEqual(view["nodes"]["evidence"],[])

    def test_stale_reading_stays_stale_and_unsupported_payload_is_not_projected(self):
        self.save(lambda e:e["payload"]["claims"]["passages"][0].update(stale=["source changed"]))
        view=self.readonly(); self.assertTrue(any(a["current_status"]=="stale" for a in view["nodes"]["answers"]))
        self.refs=[]
        self.save(lambda e:e["payload"].update(schema="unsupported-v99"))
        view=self.readonly();self.assertEqual(view["nodes"]["evidence"],[])
        self.assertTrue({"deflate_payload_schema","deflate_deposition_unverified"} & {g["kind"] for g in view["gaps"]})

    def test_legacy_ready_metadata_does_not_invent_missing_reading_prose(self):
        self.save(lambda e:e["payload"]["claims"]["passages"][0].pop("reading"))
        view=self.readonly()
        old=next(a for a in view["nodes"]["answers"] if a.get("passage_id")=="p001")
        self.assertEqual(old["current_status"],"reading_metadata_only")
        self.assertTrue(old["reading_metadata_available"])
        self.assertFalse(old["reading_available"])

    def test_duplicate_passage_identity_retains_both_records_without_promoting_reading(self):
        def duplicate(env):
            passages = env["payload"]["claims"]["passages"]
            passages.append(copy.deepcopy(passages[0]))
        self.save(duplicate); before = self.hashes(); view = self.readonly()
        records = [a for a in view["nodes"]["answers"] if a.get("passage_id") == "p001"]
        self.assertEqual(len(records), 2)
        self.assertTrue(all(a["current_status"] == "identity_ambiguous" and not a["reading_available"] for a in records))
        self.assertEqual(len({a["source_pointer"] for a in records}), 2)
        self.assertEqual(before, self.hashes())

    def test_fresh_process_reopens_exact_projection_without_network_import_or_store_mutation(self):
        self.save(); before=self.hashes(); expected=self.readonly()
        code="import json,importlib.util; from unittest.mock import patch; from pathlib import Path; import wordicon_cli as cli,operations,producers,federation; cli.LOCAL_STATE=Path("+repr(str(cli.LOCAL_STATE))+"); s=importlib.util.spec_from_file_location('h',"+repr(str(STAGE / 'scripts/capture_history.py'))+"); h=importlib.util.module_from_spec(s); s.loader.exec_module(h);\nwith patch.object(operations,'_connect',side_effect=AssertionError('no init')),patch.object(producers,'_request',side_effect=AssertionError('no fetch')),patch.object(federation,'import_package',side_effect=AssertionError('no reimport')): print(json.dumps(h.view(operation_id="+repr(self.op['op_id'])+"),sort_keys=True))"
        env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1","WORDICON_STATE":str(cli.LOCAL_STATE),"PYTHONPATH":str(MAIN / 'scripts')+os.pathsep+str(MAIN)}
        actual=json.loads(subprocess.check_output([sys.executable,"-c",code],text=True,env=env))
        self.assertEqual(expected,actual);self.assertEqual(before,self.hashes())

if __name__=="__main__": unittest.main()
