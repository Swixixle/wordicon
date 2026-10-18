"""Authenticated read/prepare tests, isolated from owner data and network.

Staged: NK_ROOT=.../nikodemus RECEIPTS_STAGE=.../receipts-stage python this_file
After promotion: run normally from the Nikodemus checkout.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

FILES=Path(__file__).resolve().parents[1]
ROOT=Path(os.environ.get("NK_ROOT", FILES))
STAGE=Path(os.environ["RECEIPTS_STAGE"]) if os.environ.get("RECEIPTS_STAGE") else None
SCRATCH=tempfile.TemporaryDirectory(prefix="nk-receipts-",dir=Path(tempfile.gettempdir()).resolve())
os.environ["WORDICON_TEST_MODE"]="1"
os.environ["WORDICON_PREVIEW"]="1"
os.environ["WORDICON_STATE"]=SCRATCH.name
sys.path[:0]=([str(STAGE/"modified/scripts")] if STAGE else [])+[str(FILES/"scripts"),str(ROOT/"scripts"),str(ROOT/"src"),str(ROOT)]
import opencase  # Select the staged module before server prepends its scripts.
import server
import gate
import operations as ops
import producers
import receipts_projection
import wordicon_cli as cli

# Execute the exact staged route definition against the scratch Flask app.
# After promotion the actual server already registers this endpoint.
if STAGE and "api_open_case_receipts" not in server.app.view_functions:
    tree=ast.parse((STAGE/"modified/server.py").read_text())
    route=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="api_open_case_receipts")
    exec(compile(ast.Module(body=[route],type_ignores=[]),str(STAGE/"modified/server.py"),"exec"),server.__dict__)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="nk-receipts-case-",dir=Path(tempfile.gettempdir()).resolve())
        cli.LOCAL_STATE=Path(self.temp.name)
        self.op,_=ops.reserve(request_key="saved",kind="investigation",action_id=opencase.ACTION,
            execution={"plan":{"question":"What remains unavailable?","subject_name":"Fixture Judge",
                "subject_type":"federal_judge_district","jurisdiction":"United States",
                "origin":{"kind":"selection","doc_id":"original-doc","revision":4,"text":"Original passage"},
                "synthesis":{"enabled":False}}})
        self.raw=json.dumps({"findings":[{"id":"metadata","title":"Saved source","body":"","source_url":"https://example.test/source"}],
            "source_statuses":{"courtlistener":{"status":"credential_failure","detail":"API key unavailable"}},"model_runs":[],"actual_cost_usd":0}).encode()
        self.kept=producers.keep_artifact(self.op["op_id"],"result.json",self.raw)
        ops.mark(self.op["op_id"],"complete",result_ref={"result_artifact":self.kept,"kept":[self.kept]})
        self.op=ops.get(self.op["op_id"])
        self.client=server.app.test_client()
        self.client.set_cookie(gate.SESSION_COOKIE,gate.issue_session("fixture")["token"])
        self.url=f'/api/open-case/operations/{self.op["op_id"]}/receipts'

    def tearDown(self):
        self.temp.cleanup()

    def test_authenticated_reopen_has_no_model_network_or_store_mutation(self):
        self.assertEqual(server.app.test_client().get(self.url).status_code,401)
        before=ops.db_path().read_bytes()
        with patch.object(producers,"_request",side_effect=AssertionError("No producer call")),patch.object(server,"server_gateway",side_effect=AssertionError("No gateway")):
            first=self.client.get(self.url);second=self.client.get(self.url)
        self.assertEqual(first.status_code,200,first.json)
        self.assertEqual(first.json,second.json)
        self.assertEqual(ops.db_path().read_bytes(),before)
        self.assertEqual(producers.artifact_bytes(self.op["op_id"],"result.json"),self.raw)
        self.assertEqual(first.json["manifest"]["inputs"][0]["result_artifact"]["sha256"],hashlib.sha256(self.raw).hexdigest())

    def test_prepare_freezes_gap_and_hashes_preserving_parent_origin(self):
        projected=self.client.get(self.url).json
        suggestion=projected["continuations"][0]
        request={"operation_id":self.op["op_id"],"id":suggestion["id"],"projection_sha256":projected["projection_sha256"]}
        with patch.object(producers,"_request",side_effect=AssertionError("No network")),patch.object(server,"server_gateway",side_effect=AssertionError("No gateway")):
            plan=opencase.prepare(suggestion["question"],{"subject_name":"Fixture Judge","follow_up_of":self.op["op_id"],
                "receipts_continuation":request,"synthesis":{"enabled":False}})
        self.assertEqual(plan["origin"],self.op["execution"]["plan"]["origin"])
        self.assertEqual(plan["receipts_continuation"]["gap_id"],suggestion["gap_id"])
        self.assertEqual(plan["receipts_continuation"]["source_refs"],suggestion["source_refs"])
        with self.assertRaises(opencase.WorkflowError):
            opencase.prepare(suggestion["question"],{"subject_name":"Fixture Judge","follow_up_of":self.op["op_id"],
                "receipts_continuation":{**request,"id":"invented"}})

    def test_tampered_raw_result_is_rejected_before_projection(self):
        with patch.object(producers,"artifact_bytes",return_value=self.raw+b" "):
            response=self.client.get(self.url)
        self.assertEqual(response.status_code,409,response.json)
        self.assertNotIn("evidence_matrix",response.json)

    def test_unknown_operation_in_empty_store_does_not_initialize_database(self):
        cli.LOCAL_STATE=Path(self.temp.name)/"empty-store"
        self.client.set_cookie(gate.SESSION_COOKIE,gate.issue_session("empty-fixture")["token"])
        response=self.client.get(self.url)
        self.assertEqual(response.status_code,404,response.json)
        self.assertFalse(ops.db_path().exists())

    def test_complete_answer_and_exact_receipt_hold_project_without_mutating_connector(self):
        receipt = producers.keep_artifact(self.op["op_id"], "response.json", b'{"text":"Saved answer"}')
        state = {"status":"complete", "answer":"Saved answer", "response_artifact":receipt,
                 "citations":[{"record_id":self.op["op_id"]+":metadata"}]}
        ops.mark(self.op["op_id"], "complete", result_ref={"result_artifact":self.kept,
            "synthesis":state, "kept":[self.kept, receipt]})
        before = ops.db_path().read_bytes()
        with patch.object(ops, "_connect", side_effect=AssertionError("GET must not initialize or migrate SQLite")):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertTrue(response.json["evidence_matrix"][0]["used_in_answer"])
        self.assertEqual(ops.db_path().read_bytes(), before)
        # A review of a different saved receipt cannot hold this selected answer.
        review = {"schema":"nikodemus.open_case.answer_review.v1", "response_artifact":{**receipt,"sha256":"0"*64},
                  "verdict":"hold", "reason":"Unsupported inference in another receipt."}
        ops.event(self.op["op_id"], "note", detail={"answer_review":review})
        with patch.object(ops, "_connect", side_effect=AssertionError("No mutating connector")):
            self.assertTrue(self.client.get(self.url).json["evidence_matrix"][0]["used_in_answer"])
        ops.event(self.op["op_id"], "note", detail={"answer_review":{**review,"response_artifact":receipt}})
        before = ops.db_path().read_bytes()
        with patch.object(ops, "_connect", side_effect=AssertionError("No mutating connector")):
            held = self.client.get(self.url)
        self.assertEqual(held.status_code, 200, held.json)
        self.assertFalse(held.json["evidence_matrix"][0]["used_in_answer"])
        self.assertEqual(ops.db_path().read_bytes(), before)
        self.assertEqual(producers.artifact_bytes(self.op["op_id"], "result.json"), self.raw)

    def test_complete_label_without_receipt_does_not_claim_answer_usage(self):
        ops.mark(self.op["op_id"], "complete", result_ref={"result_artifact":self.kept,"kept":[self.kept],
            "synthesis":{"status":"complete","citations":[{"record_id":self.op["op_id"]+":metadata"}]}})
        with patch.object(ops, "_connect", side_effect=AssertionError("No mutating connector")):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertFalse(response.json["evidence_matrix"][0]["used_in_answer"])


if __name__=="__main__":
    unittest.main()
