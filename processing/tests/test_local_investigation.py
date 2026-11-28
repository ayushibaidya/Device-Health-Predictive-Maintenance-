from types import SimpleNamespace

import pytest

from device_health_investigation.local_demo import save_report, seed_snapshot
from device_health_investigation.reporting import ContextUnavailable


@pytest.mark.parametrize("dsn", ["dbname=development host=postgres user=ai_investigation_demo",
                                 "dbname=ai_investigation_" + "a" * 32 + " host=localhost user=developer"])
def test_demo_rejects_non_disposable_database_before_connecting(dsn, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Must not connect to development data")
    monkeypatch.setattr("psycopg.connect", forbidden)
    with pytest.raises(ContextUnavailable):
        seed_snapshot(dsn)


def test_report_is_opt_in_exclusive_and_has_restrictive_permissions(tmp_path):
    path = tmp_path / "report.json"
    save_report(path, {"test_only": True})
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        save_report(path, {"overwritten": True})


def test_prepare_mode_never_invokes_llm_even_when_gate_enabled(monkeypatch):
    import time
    from device_health_investigation import local_demo, verification
    # Actual evidence preparation is covered by reader tests; this test isolates admission to generation.
    monkeypatch.setattr(verification, "runtime_calibration", lambda args: (None, SimpleNamespace(
        search=lambda *args, **kwargs: (),
    ), SimpleNamespace(enabled=True)))
    monkeypatch.setattr(local_demo, "seed_snapshot", lambda dsn: (None, {}))
    monkeypatch.setattr(local_demo, "prepare_sources", lambda *args: ({}, set()))
    monkeypatch.setattr(local_demo, "prepare_messages", lambda *args: ([], {}))
    monkeypatch.setattr("device_health_investigation.investigation.retrieval_query", lambda packet: "test")
    monkeypatch.setattr("device_health_ingestion.store.database_dsn", lambda: "test-only")
    monkeypatch.setattr("device_health_investigation.ollama.OllamaClient", lambda *args: pytest.fail("No LLM"))
    assert local_demo.run_demo(SimpleNamespace(mode="prepare"), time.monotonic())["status"] == "pass"


@pytest.mark.integration
def test_disposable_demo_uses_existing_persistence_and_closes_snapshot_resources():
    import json
    import os
    from pathlib import Path
    from uuid import uuid4

    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    from device_health_ingestion.store import database_dsn
    from device_health_investigation.chunking import Chunk
    from device_health_investigation.index import SearchHit
    from device_health_investigation.reporting import GenerationLimits, prepare_messages, prepare_sources

    name = "ai_investigation_" + uuid4().hex
    with psycopg.connect(database_dsn(), autocommit=True) as admin:
        admin.execute("CREATE ROLE ai_investigation_demo LOGIN PASSWORD 'isolated-test-only'")
        admin.execute(sql.SQL("CREATE DATABASE {} OWNER ai_investigation_demo").format(sql.Identifier(name)))
        try:
            dsn = make_conninfo(database_dsn(), dbname=name, user="ai_investigation_demo", password="isolated-test-only")
            reader, evidence = seed_snapshot(dsn)
            assert reader.connection is None and evidence["evidence"]["reading_count"] == 2
            if os.getenv("AI_SYNTHETIC_EVIDENCE_PATH"):
                Path(os.environ["AI_SYNTHETIC_EVIDENCE_PATH"]).write_text(json.dumps(evidence))
            text = "Review same-run simulator readings; WARNING is simulator-reported."
            chunk = Chunk("a" * 64, "alert-episodes", "b" * 64, "runbooks/alert-episodes.md", "Alerts",
                          ("Alerts",), 0, len(text), 1, 1, text, text, 15, 0, "test-tokenizer")
            packet, _ = prepare_sources(evidence, (SearchHit(1, 0.9, chunk),))
            messages, _ = prepare_messages(packet, GenerationLimits())
            assert len(json.dumps(messages, ensure_ascii=False).encode()) <= 12000
            with pytest.raises(ContextUnavailable):
                seed_snapshot(dsn)  # Never overwrite/reseed a populated database.
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
            admin.execute("DROP ROLE ai_investigation_demo")
