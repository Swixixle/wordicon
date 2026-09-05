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


server.server_gateway = _poisoned
# block 111 phase 2: the Reader's deterministic offline stand-in. The rest of
# the server stays poisoned; only the Question Reader has a stand-in, and it
# runs the real check, the real run record and the real adoption.
server.READER_GATEWAY = cli.MockReader()
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
os.environ[mock_producer.OC_KEY_ENV] = "open_case_" + "j" * 64
_pbase = f"http://127.0.0.1:{PRODUCER_PORT}"
federation.register_connector("open-case-dev", "open_case", _pbase, display="Open Case (scratch)",
                              credential_ref="env:" + mock_producer.OC_KEY_ENV, dev_loopback=True, by="journeys")
federation.register_connector("ethicalalt-dev", "ethicalalt", _pbase, display="EthicalAlt (scratch)", dev_loopback=True, by="journeys")
federation.pin_key("open-case-dev", (mock_producer.FIXTURES / "open_case.fixture.pub.b64").read_text().strip(), label="fixture key", by="journeys")
federation.pin_key("ethicalalt-dev", (mock_producer.FIXTURES / "ethicalalt.fixture.pub.b64").read_text().strip(), label="fixture key", by="journeys")
DIR.mkdir(parents=True, exist_ok=True)
(DIR / "producer_port").write_text(str(PRODUCER_PORT))
(DIR / "token").write_text(gate.issue_session("journeys")["token"])
(DIR / "cookie").write_text(gate.SESSION_COOKIE)
print(f"journey server: state={STATE} port={PORT} gateway=poisoned key=absent producers=127.0.0.1:{PRODUCER_PORT}", flush=True)
server.app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)
