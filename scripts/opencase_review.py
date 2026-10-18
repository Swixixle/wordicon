"""Append-only local answer reviews, bound to an immutable provider receipt.

A review changes the derived presentation, never the saved synthesis or source.
It is an observation by the workspace operator, not an automated truth verdict.
"""
import hashlib
import json
import operations as ops

SCHEMA = "nikodemus.open_case.answer_review.v1"


def hold(op, inputs):
    import opencase
    if not opencase.is_ours(op):
        raise opencase.WorkflowError("No Open Case investigation with that id.", 404)
    state = (op.get("result_ref") or {}).get("synthesis") or {}
    receipt = state.get("response_artifact") or {}
    if not receipt or not state.get("answer"):
        raise opencase.WorkflowError("There is no saved model answer to review.", 409)
    opencase.artifact(op, receipt["name"])
    reason = inputs.get("reason") if isinstance(inputs, dict) else None
    if not isinstance(reason, str) or not 10 <= len(reason.strip()) <= 4000:
        raise opencase.WorkflowError("Describe the unsupported claim and evidence gap in 10–4,000 characters.")
    if inputs.get("response_sha256") != receipt.get("sha256"):
        raise opencase.WorkflowError("The review must identify the exact saved answer receipt.", 409)
    review = {"schema": SCHEMA, "verdict": "hold", "reason": reason.strip(),
              "response_artifact": receipt, "basis": "workspace_operator_review"}
    review["review_id"] = hashlib.sha256(json.dumps(review, sort_keys=True).encode()).hexdigest()
    if not any(e.get("detail", {}).get("answer_review", {}).get("review_id") == review["review_id"]
               for e in ops.events(op["op_id"], limit=-1)):
        opencase._event(op["op_id"], "note", detail={"answer_review": review})
    return opencase.view(ops.get(op["op_id"]))


def apply(op, state):
    receipt = state.get("response_artifact") or {}
    reviews = [dict(e["detail"]["answer_review"], recorded_at=e["at"])
               for e in ops.events(op["op_id"], limit=-1)
               if e.get("detail", {}).get("answer_review", {}).get("schema") == SCHEMA
               and e["detail"]["answer_review"].get("response_artifact") == receipt]
    if not reviews:
        return state
    return {**state, "status": "rejected", "answer_status": "held", "hold_reason": "support_disputed",
            "answer": "", "citations": [], "held_answer": state.get("answer", ""),
            "held_citations": state.get("citations", []), "reviews": reviews,
            "error": reviews[-1]["reason"], "adequacy_reason": "A workspace review identified an unsupported claim; the original response is preserved."}
