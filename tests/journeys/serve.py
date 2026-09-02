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
            "DEFINITION_EVENTS_LOG", "ENCOUNTER_SWITCH_LOG", "ENCOUNTERS_LOG")   # block 104
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
DIR.mkdir(parents=True, exist_ok=True)
(DIR / "token").write_text(gate.issue_session("journeys")["token"])
(DIR / "cookie").write_text(gate.SESSION_COOKIE)
print(f"journey server: state={STATE} port={PORT} gateway=poisoned key=absent", flush=True)
server.app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)
