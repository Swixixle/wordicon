"""The scratch server the journeys drive. Everything the suite's redirect
does, plus: the model gateway poisoned (constructing it raises), the API
key removed from the environment, and a session minted straight into
JOURNEY_DIR for the browser to carry. Never the real store: LOCAL_STATE
is the scratch directory run.sh made. Listens on JOURNEY_PORT."""
import os
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
DIR = pathlib.Path(os.environ.get("JOURNEY_DIR", "/tmp/anat"))
STATE = pathlib.Path(os.environ.get("JOURNEY_STATE", str(DIR / "state")))
PORT = int(os.environ.get("JOURNEY_PORT", "8499"))

# workspace-v2 slice A: the environment that fails closed. Set BEFORE the
# first application import so wordicon_cli reads it on its first line: the
# socket guard goes in, .env stays unread, providers refuse to construct,
# and the server resolves its data root from WORDICON_STATE — the scratch
# directory, verified at import against the repository's own store.
os.environ["WORDICON_TEST_MODE"] = "1"
os.environ["WORDICON_STATE"] = str(STATE)
os.environ["JOURNEY_PORT"] = str(PORT)
os.environ.setdefault("WORDICON_TEST_EGRESS_LOG", str(DIR / "egress_denied.jsonl"))
import testmode  # noqa: E402

import wordicon_cli as cli  # noqa: E402
REDIRECT = ("JUDGMENTS_LOG", "RECEIPTS_DIR", "RESULTS_DIR", "ACCEPTED_CONCEPTS_PATH", "EDGES_LOG", "WARPS_LOG",
            "WARP_NOTES_LOG", "BENCH_CORRECTIONS", "CONCEPT_NAMES_LOG", "BENCH_DIR", "INPUTS_LOG", "WAYFINDER_LOG",
            "DEFINITION_EVENTS_LOG", "ENCOUNTER_SWITCH_LOG", "ENCOUNTERS_LOG",   # block 104
            "OPEN_QUESTIONS_LOG")   # block 105
STATE.mkdir(parents=True, exist_ok=True)
for _n in REDIRECT:
    setattr(cli, _n, STATE / str(getattr(cli, _n)).split("/")[-1])
cli.LOCAL_STATE = STATE
(STATE / "receipts").mkdir(exist_ok=True)
(STATE / "results").mkdir(exist_ok=True)

os.environ.pop("ANTHROPIC_API_KEY", None)
import server  # noqa: E402
import gate  # noqa: E402


def _poisoned(*a, **k):
    raise RuntimeError("the journeys run with the model gateway poisoned — nothing here may construct it")


# workspace-v2 slice B: the workspace journeys need a run to COMPLETE through
# the one job path (write → choose an action → a fixture result → reopen), so
# a second scratch server runs with the mock lane instead of the poison. Test
# mode still refuses every provider and every outbound socket; the mock
# gateway is the canned fixture, and the lane says so on every proposal.
if os.environ.get("JOURNEY_MOCK_LANE") == "1":
    server.server_gateway = lambda: cli.make_gateway("mock", None)
else:
    server.server_gateway = _poisoned
# block 111 phase 2: the Reader's deterministic offline stand-in. The rest of
# the server stays poisoned; only the Question Reader has a stand-in, and it
# runs the real check, the real run record and the real adoption.
server.READER_GATEWAY = cli.MockReader()
# block 125: the readers' deterministic offline stand-ins — one per reader, so
# the whole path (snapshot, three separate dispatches, quotation check, the
# carry, a follow-up, the consultation) runs for real with nothing reaching a
# provider. A draft containing "FAIL LACHESIS" makes that one reader fail.
import moira  # noqa: E402
server.MOIRA_GATEWAY_FACTORY = moira.mock_gateway_for
import speech  # noqa: E402
speech.ENGINE = speech.MockEngine()   # block 106: the journeys transcribe with the mock, offline, deterministic
# block 107: the mock producers on their own loopback port, and two development
# connectors registered in the scratch state with the fixtures' public keys
# pinned. The Open Case credential lives only in this process's environment,
# named by reference on the connector. The journey imports on its own press;
# nothing here fetches.
import mock_producer  # noqa: E402
import federation  # noqa: E402
_producer, PRODUCER_PORT = mock_producer.start(int(os.environ.get("JOURNEY_PRODUCER_PORT", "0")))
testmode.allow_port(PRODUCER_PORT)   # the one loopback port the server may connect to besides itself
os.environ[mock_producer.OC_KEY_ENV] = "open_case_" + "j" * 64
_pbase = f"http://127.0.0.1:{PRODUCER_PORT}"
federation.register_connector("open-case-dev", "open_case", _pbase, display="Open Case (scratch)",
                              credential_ref="env:" + mock_producer.OC_KEY_ENV, dev_loopback=True, by="journeys")
federation.register_connector("ethicalalt-dev", "ethicalalt", _pbase, display="EthicalAlt (scratch)", dev_loopback=True, by="journeys")
federation.pin_key("open-case-dev", (mock_producer.FIXTURES / "open_case.fixture.pub.b64").read_text().strip(), label="package fixture key", by="journeys")
federation.pin_key("ethicalalt-dev", (mock_producer.FIXTURES / "ethicalalt.fixture.pub.b64").read_text().strip(), label="package fixture key", by="journeys")
# the producers' contracts at the pinned revisions (the review of 6e5b59c, finding 3): the receipt and snapshot keys
federation.pin_key("ethicalalt-dev", (mock_producer.PFIX / "ethicalalt.receipt.pub.spki.b64").read_text().strip(), label="receipt fixture key", by="journeys")
federation.pin_key("open-case-dev", (mock_producer.PFIX / "open_case.snapshot.pub.spki.b64").read_text().strip(), label="snapshot fixture key", by="journeys")
DIR.mkdir(parents=True, exist_ok=True)
(DIR / "producer_port").write_text(str(PRODUCER_PORT))
(DIR / "token").write_text(gate.issue_session("journeys")["token"])
(DIR / "cookie").write_text(gate.SESSION_COOKIE)
print(f"journey server: state={STATE} port={PORT} gateway=poisoned key=absent producers=127.0.0.1:{PRODUCER_PORT} "
      f"testmode={testmode.status()}", flush=True)
server.ops_startup_report()   # slice D: the serving process reconciles what a dead process left, then serves
server.app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)
