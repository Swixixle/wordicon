#!/usr/bin/env python3
"""A schema-1 copy, one incremental edge/ruling, and refusal on bad input.

All files are synthetic and outside the owner's state. No model calls.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sqlite3
import sys
import tempfile

os.environ["WORDICON_TEST_MODE"] = "1"
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import wordicon_cli as cli  # noqa: E402
import workindex as wi  # noqa: E402
import state_root  # noqa: E402
import workindex_history as wh  # noqa: E402


def run_checks():
    failures = []

    def pin(name, condition):
        if not condition:
            failures.append("history: " + name)

    with tempfile.TemporaryDirectory(prefix="nikodemus_history_index_") as scratch:
        state = pathlib.Path(scratch)
        original_root = cli.LOCAL_STATE
        state_root.apply(state)
        cli.RESULTS_DIR.mkdir()
        cli.RECEIPTS_DIR.mkdir()
        cli.EDGES_LOG.write_text("")
        cli.JUDGMENTS_LOG.write_text("")
        try:
            # Create a schema-1 file with an existing item, then open it with
            # the new reader. A migration must not lose the item or generation.
            conn = wi._connect()
            conn.execute("INSERT INTO items (gen, item_id, store, kind, native_id) "
                         "VALUES (7, 'notebook:writing:existing', 'notebook', 'writing', 'existing')")
            conn.execute("UPDATE meta SET value = '7' WHERE key = 'generation'")
            conn.execute("UPDATE meta SET value = '1' WHERE key = 'schema'")
            for table in ("history_edges", "history_rulings"):
                conn.execute(f"DROP TABLE {table}")
            conn.close()
            migrated = wi._connect()
            try:
                pin("schema-1 item and generation survive additive migration",
                    wi.generation(migrated) == 7 and
                    migrated.execute("SELECT item_id FROM items WHERE gen = 7").fetchone()[0]
                    == "notebook:writing:existing" and
                    wi._meta(migrated, "schema") == "2")
            finally:
                migrated.close()

            # Full rebuild deliberately uses a new generation. It indexes one
            # native run; later edge/ruling append should leave generation 8.
            (cli.RESULTS_DIR / "trace_memory.json").write_text(json.dumps({
                "trace_id": "trace_memory", "mode": "forge", "input_text": "Memory and forgetting",
                "created_at": "2026-10-19T08:50:00Z", "candidates": [{"title": "Memory's door"}]}))
            built = wi.rebuild()
            pin("rebuild switched once and indexed the native run",
                built.get("generation") == 8 and not built.get("failed") and
                any(i["native_id"] == "trace_memory" for i in wi.search("memory")["items"]))

            edge = {"edge_id": "edge_memory", "rel": "parallels",
                    "source": {"kind": "word", "key": "word:memory", "label": "Memory"},
                    "target": {"kind": "word", "key": "word:forgetting", "label": "Forgetting",
                               "concept_id": "concept_a"},
                    "producer": {"kind": "receipt", "id": "receipt_a"}, "verdict": ""}
            ruling = {"id": "ruling_a", "decision": "revised", "decision_source": "owner",
                      "scope": "parallel", "concept_id": "concept_a",
                      "candidate_text": "Memory and forgetting", "ruled_at": "2026-10-19T08:51:00Z"}
            with cli.EDGES_LOG.open("a") as handle:
                handle.write(json.dumps(edge) + "\n")
            with cli.JUDGMENTS_LOG.open("a") as handle:
                handle.write(json.dumps(ruling) + "\n")
            before = wi.search_history("memory")
            pin("pending links make a pre-refresh answer non-exhaustive",
                not before["edges"] and not before["rulings"] and not before["exhaustive"])
            changed = wi.refresh()
            answer = wi.search_history("memory")
            pin("one edge and ruling appear through refresh without a rebuild",
                wi.generation() == 8 and not changed["failed"] and
                len(answer["edges"]) == len(answer["rulings"]) == 1 and
                any(i["native_id"] == "trace_memory" for i in answer["items"]) and
                answer["exhaustive"])
            e, j = answer["edges"][0], answer["rulings"][0]
            pin("recorded edge basis and empty verdict retain their meaning",
                e["source_key"] == "word:memory" and e["target_key"] == "word:forgetting" and
                e["target_concept_id"] == "concept_a" and e["basis"] == "source_declared" and
                e["producer_id"] == "receipt_a" and e["verdict"] is None)
            pin("owner scope and timestamp stay on their own ruling",
                j["decision_source"] == "owner" and j["aspect_scope"] == "parallel" and
                j["ruled_at"] == "2026-10-19T08:51:00Z")
            injected = wi.search_history("%' OR 1=1 --")
            with wi._connect() as checked:
                retained = checked.execute(
                    "SELECT COUNT(*) FROM history_edges WHERE gen = 8").fetchone()[0]
            pin("hostile history query cannot alter the index",
                isinstance(injected["edges"], list) and retained == 1)

            # IDs may repeat; source line occurrences may not collapse.
            repeated = {**edge, "source": {"kind": "word", "key": "word:other", "label": "Other memory"},
                        "producer": None, "verdict": "strained"}
            validator = {**ruling, "id": "ruling_validator", "decision_source": "validator",
                         "decision": "rejected", "ruled_at": None}
            with cli.EDGES_LOG.open("a") as handle:
                handle.write(json.dumps(repeated) + "\n")
            with cli.JUDGMENTS_LOG.open("a") as handle:
                handle.write(json.dumps(validator) + "\n")
            wi.refresh()
            answer = wi.search_history("memory")
            pin("duplicate edge ids retain two distinct source declarations",
                len(answer["edges"]) == 2 and {e["source_key"] for e in answer["edges"]}
                == {"word:memory", "word:other"})
            pin("producerless edge has unknown basis with no invented evidence",
                any(e["basis"] == "unknown" and e["producer_id"] is None
                    for e in answer["edges"]))
            pin("validator ruling remains attributed and separately retrievable",
                len(answer["rulings"]) == 2 and
                {j["decision_source"] for j in answer["rulings"]} == {"owner", "validator"})

            # A replacement of equal length does not change the byte count.
            original_log = cli.EDGES_LOG.read_bytes()
            replaced_log = original_log.replace(b"word:other", b"word:ether")
            pin("same-size fixture actually changed the consumed prefix",
                len(replaced_log) == len(original_log) and replaced_log != original_log)
            cli.EDGES_LOG.write_bytes(replaced_log)
            pin("same-size rewrite makes the answer non-exhaustive before refresh",
                wi.health()["pending"]["edges"] is None and
                not wi.search_history("memory")["exhaustive"])
            wi.refresh()
            pin("same-size replacement reprojects without switching generation",
                wi.generation() == 8 and
                {e["source_key"] for e in wi.search_history("memory")["edges"]}
                == {"word:memory", "word:ether"})

            # A malformed line followed by a valid one must be a named
            # incomplete family, never a skipped line or a false absence.
            with cli.EDGES_LOG.open("a") as handle:
                handle.write('{"edge_id": "broken"\n')
                handle.write(json.dumps({**edge, "edge_id": "after_bad", "source":
                                         {"kind": "word", "key": "word:next", "label": "Next memory"}}) + "\n")
            failed = wi.refresh()
            answer = wi.search_history("next memory")
            pin("malformed edge names its family and line and rolls back",
                any("edges" in f and "edges.jsonl:3" in f for f in failed["failed"]) and
                not any(e["edge_id"] == "after_bad" for e in answer["edges"]) and
                not answer["exhaustive"] and
                wi.health()["history"]["edges"] == 2)
            content = cli.EDGES_LOG.read_text()
            cli.EDGES_LOG.write_text(content.replace('{"edge_id": "broken"\n', ''))
            repaired = wi.refresh()
            pin("a repaired append is read and the index remains generation 8",
                not repaired["failed"] and wi.generation() == 8 and
                any(e["edge_id"] == "after_bad" for e in wi.search_history("next memory")["edges"]))

            # A present optional field with the wrong shape fails this
            # family's refresh without crashing the query or relabeling it.
            with cli.JUDGMENTS_LOG.open("a") as handle:
                handle.write(json.dumps({**ruling, "id": "bad_shape", "concept_id": ["concept_a"]}) + "\n")
            bad_shape = wi.refresh()
            pin("wrong-shaped optional concept id reports incomplete, not a ruling",
                any("judgments" in f and "concept_id" in f for f in bad_shape["failed"]) and
                wi.health()["history"]["rulings"] == 2 and
                not wi.search_history("memory")["exhaustive"])
            cli.JUDGMENTS_LOG.write_text("\n".join(cli.JUDGMENTS_LOG.read_text().splitlines()[:-1]) + "\n")
            wi.refresh()
            with cli.JUDGMENTS_LOG.open("a") as handle:
                handle.write('{"id": "unfinished"')
            trailing = wi.refresh()
            pin("partial trailing line stays pending and cannot establish absence",
                any("judgments: incomplete" == f for f in trailing["failed"]) and
                not wi.search_history("unfinished")["exhaustive"] and
                wi.health()["history"]["rulings"] == 2)
            cli.JUDGMENTS_LOG.write_bytes(cli.JUDGMENTS_LOG.read_bytes().split(b'{"id": "unfinished"')[0])
            wi.refresh()
            again = wi.rebuild()
            with wi._connect() as checked:
                old_edges = checked.execute(
                    "SELECT COUNT(*) FROM history_edges WHERE gen != 9").fetchone()[0]
            pin("rebuild removes prior-generation history rows without losing the answer",
                again.get("generation") == 9 and not again["failed"] and
                wi.health()["history"] == {"edges": 3, "rulings": 2,
                                            "producer_identity_gaps": 0} and old_edges == 0)

            # An incremental refresh can land between item and relationship
            # reads without switching generations. Interpose it precisely.
            original_matches = wh.matches
            def refresh_during_matches(conn, gen, query, limit=50):
                interleaved_edge = {**edge, "edge_id": "edge_interleaved",
                                    "source": {"kind": "word", "key": "word:interleaved",
                                               "label": "Interleaved memory"}}
                with cli.EDGES_LOG.open("a") as handle:
                    handle.write(json.dumps(interleaved_edge) + "\n")
                wi.refresh()
                return original_matches(conn, gen, query, limit)
            wh.matches = refresh_during_matches
            try:
                interleaved = wi.search_history("interleaved")
            finally:
                wh.matches = original_matches
            pin("refresh between item and edge reads cannot claim one exhaustive state",
                wi.generation() == 9 and not interleaved["exhaustive"] and
                any(e["edge_id"] == "edge_interleaved" for e in interleaved["edges"]) and
                wi.health()["pending"]["edges"] == 0)

            accented_edge = {**edge, "edge_id": "edge_unicode",
                             "source": {"kind": "word", "key": "word:accented",
                                        "label": "MÉMOIRE et oubli"}}
            with cli.EDGES_LOG.open("a") as handle:
                handle.write(json.dumps(accented_edge, ensure_ascii=False) + "\n")
            wi.refresh()
            pin("uppercase accented topic is found under either query casing",
                all(any(e["edge_id"] == "edge_unicode" for e in wi.search_history(q)["edges"])
                    for q in ("mémoire", "MÉMOIRE")))

            with cli.EDGES_LOG.open("a") as handle:
                handle.write(json.dumps({**edge, "edge_id": "edge_producer_gap",
                                         "producer": {"kind": "receipt"}}) + "\n")
            wi.refresh()
            with_gap = wi.search_history("memory")
            gap = next(e for e in with_gap["edges"] if e["edge_id"] == "edge_producer_gap")
            absent = next(e for e in with_gap["edges"] if e["basis"] == "unknown" and
                          e["producer_gap"] is None)
            pin("recorded but unidentifiable producer stays distinct from absent producer",
                gap["basis"] == "unknown" and gap["producer_id"] is None and
                "no id field" in gap["producer_gap"] and absent["producer_gap"] is None and
                with_gap["health"]["history"]["producer_identity_gaps"] == 1 and
                not with_gap["exhaustive"])

            # Reopen an earlier schema-2 projection and recover the reason
            # from its retained raw record while adding the new column.
            with sqlite3.connect(":memory:", isolation_level=None) as old:
                old.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
                old.execute("INSERT INTO meta VALUES ('schema', '2')")
                old.execute(wh.DDL[0].replace("        producer_gap TEXT,\n", ""))
                old.execute(wh.DDL[1])
                old.execute("INSERT INTO history_edges (gen, line_offset, edge_id, rel, basis, "
                            "search_text, raw) VALUES (1, 0, 'old', 'parallels', 'unknown', '', ?)",
                            (json.dumps({**edge, "producer": {"kind": "receipt"}}),))
                wh.ensure_schema(old)
                pin("earlier schema-2 row gains its recorded producer gap",
                    "no id field" in old.execute("SELECT producer_gap FROM history_edges").fetchone()[0])

            # Unknown future schemas must be refused before a table is added.
            future = state / "future.sqlite3"
            with sqlite3.connect(future) as c:
                c.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
                c.execute("INSERT INTO meta VALUES ('schema', 'nikodemus.work_history.index.v3')")
            original_db = wi.db_path
            wi.db_path = lambda: future
            try:
                before_hash = hashlib.sha256(future.read_bytes()).hexdigest()
                try:
                    wi._connect()
                except wi.IndexError_:
                    refused = True
                else:
                    refused = False
                pin("future or rival schema refused without modifying its bytes",
                    refused and hashlib.sha256(future.read_bytes()).hexdigest() == before_hash)
            finally:
                wi.db_path = original_db
            no_schema = state / "missing_schema.sqlite3"
            with sqlite3.connect(no_schema) as c:
                c.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
            wi.db_path = lambda: no_schema
            try:
                before_hash = hashlib.sha256(no_schema.read_bytes()).hexdigest()
                try:
                    wi._connect()
                except wi.IndexError_:
                    refused = True
                else:
                    refused = False
                with sqlite3.connect(f"file:{no_schema}?mode=ro", uri=True) as c:
                    tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                pin("meta without schema is refused byte-identically before item DDL",
                    refused and tables == {"meta"} and
                    hashlib.sha256(no_schema.read_bytes()).hexdigest() == before_hash)
            finally:
                wi.db_path = original_db
        finally:
            state_root.apply(original_root)
    return failures


if __name__ == "__main__":
    failed = run_checks()
    for name in failed:
        print("FAIL " + name)
    if not failed:
        print("OK work index history: schema migration, incremental update, attribution, incomplete reads")
    raise SystemExit(bool(failed))
