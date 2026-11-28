"""Opt-in local report preparation, exclusively against a fresh disposable database."""

import json
import re
import time
from pathlib import Path
from uuid import uuid4

from .reporting import ContextUnavailable, GenerationLimits, prepare_messages, prepare_sources

MODEL_DIGEST = "sha256:0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0"


def seed_snapshot(dsn):
    import psycopg
    from psycopg.conninfo import conninfo_to_dict

    from device_health_alerts.rules import episode_id
    from device_health_ingestion.core import Record
    from device_health_ingestion.migrate import migrate
    from device_health_ingestion.store import PostgresInbox
    from device_health_ingestion.validation import validate
    from .evidence import EvidenceQueries

    settings = conninfo_to_dict(dsn)
    if (
        not re.fullmatch(r"ai_investigation_[0-9a-f]{32}", settings.get("dbname", ""))
        or settings.get("host") != "postgres" or settings.get("user") != "ai_investigation_demo"
    ):
        raise ContextUnavailable("The demo requires its disposable database.")
    with psycopg.connect(dsn, connect_timeout=5) as connection:
        if connection.execute("SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='public')").fetchone()[0]:
            raise ContextUnavailable("The demo requires an empty disposable database.")
    migrate(dsn)
    run_id, events = str(uuid4()), []
    for offset in range(2):
        # Hand-authored fixture matching default C++ sample formulas at degradation
        # 4000/4020 with zero noise; not a claim of actual C++ output or hardware data.
        degradation = 4000 + 20 * offset
        event = {
            "event_id": str(uuid4()), "run_id": run_id, "device_id": "ai-local-demo",
            "timestamp": f"2026-01-01T00:16:4{offset * 5}Z", "firmware_version": "1.0.0",
            "temperature_c": (4000 + 6000 * degradation // 10000) / 100,
            "power_draw_w": (500 + 1500 * degradation // 10000) / 100,
            "cpu_utilization_pct": (2000 + 7000 * degradation // 10000) / 100,
            "memory_utilization_pct": (3000 + 5000 * degradation // 10000) / 100,
            "timing_jitter_ms": (100 + 2000 * degradation // 10000) / 100,
            "error_count": 10 * degradation // 10000,
            "device_state": "WARNING",
        }
        events.append(event)
    inbox = PostgresInbox(dsn)
    try:
        for offset, event in enumerate(events):
            raw, key = json.dumps(event).encode(), event["device_id"].encode()
            inbox.persist(validate(raw, key), Record("device.telemetry.v1", 0, offset, key, raw))
    finally:
        inbox.close()
    reader = EvidenceQueries(dsn)
    evidence = reader.get(episode_id(events[0]["event_id"]))
    if reader.connection is not None or evidence["evidence"]["reading_count"] != 2:
        raise ContextUnavailable("The disposable snapshot is inconsistent.")
    return reader, evidence


def save_report(path, report):
    # Explicit opt-in local artifact, exclusive creation and restrictive permissions.
    import os

    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(report, stream, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def run_demo(args, started):
    from device_health_ingestion.store import database_dsn
    from .investigation import InvestigationAdapter, retrieval_query
    from .ollama import OllamaClient
    from .verification import runtime_calibration, summary

    encoder, index, gate = runtime_calibration(args)
    reader, evidence = seed_snapshot(database_dsn())
    # Size-only preflight includes all three candidates; it never authorizes their use.
    candidates = index.search(retrieval_query(evidence), encoder, limit=3)
    packet, _ = prepare_sources(evidence, candidates)
    prepare_messages(packet, GenerationLimits())
    if not gate.enabled:
        return summary(passed=2, failed=1, skipped=1, seconds=time.monotonic() - started,
                       categories=["relevance_unvalidated"])
    if args.mode == "prepare":
        return summary(passed=3, skipped=1, seconds=time.monotonic() - started)
    provider = OllamaClient(MODEL_DIGEST, args.ollama_url)
    result = InvestigationAdapter(reader, index, encoder, provider, GenerationLimits(), gate).investigate(evidence["alert_id"])
    if result["status"] != "complete":
        return summary(passed=3, failed=1, seconds=time.monotonic() - started,
                       categories=["relevance_unvalidated"])
    if args.report_file:
        save_report(Path(args.report_file), result)
    return summary(passed=4, seconds=time.monotonic() - started)
