"""Standalone development experiment. Never imported by automatic investigation/API."""

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from device_health_investigation.local_demo import MODEL_DIGEST, save_report
from device_health_investigation.ollama import OllamaClient, ProviderReply
from device_health_investigation.reporting import (
    AIInvalidResponse, AIUnavailable, ContextUnavailable, GenerationLimits, MODEL_TAG,
    OLLAMA_VERSION, prepare_messages, prepare_sources, strict_json, validate_report,
)
from device_health_investigation.verification import Parser, safe_error, summary, supervise, validate_summary

EXCERPTS = (
    ("alert-episodes", "518a1d1191f7c36092729ffe234132fb0783284f7929dc5ea34e8fc32d40a88f"),
    ("thermal-power", "87e11161160de85d2be1fd2aa664b37581f6c110fe8074b1edf380bc3bc00202"),
)
FIXTURE = "hand_authored_two_warning_readings_v1"
DATABASE_ENV = ("DATABASE_URL", "PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGUSER",
                "PGPASSWORD", "PGSERVICE", "PGSERVICEFILE", "PGPASSFILE")
NOTICE = (
    "\nDevelopment-only controlled smoke: hand-authored simulator-compatible readings, "
    "two manually selected source excerpts, automatic retrieval relevance unvalidated. "
    "Two samples five seconds apart do not establish a long-term trend or hardware cause."
)


def selected_chunks(manifest, tokenizer_path):
    from device_health_investigation.chunking import ChunkingError, chunk_corpus
    from device_health_investigation.documents import DocumentError, load_corpus
    from device_health_investigation.tokenizer import MiniLMTokenizer, TokenizerUnavailable

    try:
        corpus = load_corpus(manifest)
        chunks = {chunk.chunk_id: chunk for chunk in chunk_corpus(corpus, MiniLMTokenizer(tokenizer_path))}
        selected = tuple(chunks[identity] for _, identity in EXCERPTS)
        if (
            corpus.corpus_id != "device-health-synthetic-troubleshooting-v1"
            or corpus.review_status != "source_checked_pending_owner_review"
            or any(chunk.document_id != expected[0] for chunk, expected in zip(selected, EXCERPTS, strict=True))
        ):
            raise ValueError()
        return selected
    except (DocumentError, ChunkingError, TokenizerUnavailable, KeyError, ValueError):
        raise AIUnavailable("The manually reviewed excerpts do not match their pins.") from None


def assemble(evidence, chunks):
    if tuple((chunk.document_id, chunk.chunk_id) for chunk in chunks) != EXCERPTS:
        raise AIUnavailable("Only the two pinned development excerpts are eligible.")
    packet, references = prepare_sources(evidence, [SimpleNamespace(chunk=chunk) for chunk in chunks])
    rows = packet["sources"]["telemetry"]
    if (
        packet["device_id"] != "ai-local-demo" or packet["alert_status"] != "ACTIVE"
        or packet["sources"]["alert"]["snapshot"]["severity"] != "WARNING"
        or len(rows) != 2 or any(row["event"]["device_state"] != "WARNING" for row in rows)
        or (datetime.fromisoformat(rows[1]["event"]["timestamp"]) -
            datetime.fromisoformat(rows[0]["event"]["timestamp"])).total_seconds() != 5
    ):
        raise ContextUnavailable("Only the controlled development fixture is eligible.")
    limits = GenerationLimits()
    messages, schema = prepare_messages(packet, limits)
    messages[0]["content"] += NOTICE
    if len(json.dumps(messages, ensure_ascii=False).encode()) > limits.prompt_bytes:
        raise ContextUnavailable("The manual smoke exceeds the approved prompt budget.")
    return packet, references, messages, schema


def load_packet(path):
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(131073)
        value = strict_json(raw.decode())
        if (
            len(raw) > 131072 or set(value) != {"development_only", "fixture_id", "evidence"}
            or value["development_only"] is not True or value["fixture_id"] != FIXTURE
        ):
            raise ValueError()
        return value["evidence"]
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        raise ContextUnavailable("The local development packet is invalid.") from None


def generate(evidence, chunks, provider):
    if any(os.getenv(name) for name in DATABASE_ENV):
        raise ContextUnavailable("Generation must run without database credentials or configuration.")
    packet, references, messages, schema = assemble(evidence, chunks)
    reply = provider.generate(messages, schema, GenerationLimits())
    if (
        not isinstance(reply, ProviderReply) or reply.model_tag != MODEL_TAG
        or reply.model_digest != MODEL_DIGEST or reply.runtime_version != OLLAMA_VERSION
    ):
        raise AIInvalidResponse("The manual smoke has invalid model provenance.", stage="model_provenance")
    report = validate_report(reply.content, references)
    report["limitations"].extend([
        "Development-only experiment with manually selected excerpts; automatic relevance is unvalidated.",
        "Runbooks remain pending owner review; report grounding requires manual review.",
        "Two hand-authored simulator-compatible samples do not establish long-term behavior or physical causes.",
    ])
    return {
        "development_only": True, "selection_mode": "manual_pinned_excerpts",
        "automatic_relevance_validated": False, "runbook_owner_approval": "pending",
        "fixture_id": FIXTURE, "result": {**packet, "report": report},
        "provenance": {"model_tag": reply.model_tag, "model_digest": reply.model_digest,
                       "ollama_version": reply.runtime_version},
    }


def worker(args):
    started = time.monotonic()
    try:
        if args.mode == "probe":
            OllamaClient(MODEL_DIGEST, args.ollama_url).verify(GenerationLimits())
            return summary(passed=1, seconds=time.monotonic() - started)
        if args.mode == "packet":
            from device_health_ingestion.store import database_dsn
            from device_health_investigation.local_demo import seed_snapshot

            _, evidence = seed_snapshot(database_dsn())
            save_report(args.packet_file, {"development_only": True, "fixture_id": FIXTURE, "evidence": evidence})
            return summary(passed=1, seconds=time.monotonic() - started)
        if args.mode == "generate" and not args.confirm_manual_excerpts:
            return summary(errors=1, categories=["invalid_request"], seconds=time.monotonic() - started)
        if any(os.getenv(name) for name in DATABASE_ENV):
            raise ContextUnavailable("This phase must have no database configuration.")
        evidence = load_packet(args.packet_file)
        chunks = selected_chunks(args.manifest, args.tokenizer)
        assemble(evidence, chunks)
        if args.mode == "prepare":
            return summary(passed=3, skipped=1, seconds=time.monotonic() - started)
        if args.save_report and Path(args.report_file).exists():
            raise ContextUnavailable("The local report already exists; no generation was started.")
        artifact = generate(evidence, chunks, OllamaClient(MODEL_DIGEST, args.ollama_url))
        if args.save_report:
            save_report(args.report_file, artifact)
        return summary(passed=4, seconds=time.monotonic() - started)
    except Exception as error:
        return summary(errors=1, categories=[safe_error(error)], seconds=time.monotonic() - started)


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument("mode", choices=("probe", "packet", "prepare", "generate"))
    parser.add_argument("--packet-file", default="/artifacts/evidence.json")
    parser.add_argument("--report-file", default="/artifacts/report.json")
    parser.add_argument("--manifest", default="../knowledge/manifest.json")
    parser.add_argument("--tokenizer", default="/models/minilm/tokenizer.json")
    parser.add_argument("--ollama-url", default="http://host.docker.internal:11434")
    parser.add_argument("--confirm-manual-excerpts", action="store_true")
    parser.add_argument("--save-report", action="store_true")
    parser.add_argument("--worker-summary", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker_summary:
        value = worker(args)
        Path(args.worker_summary).write_text(json.dumps(validate_summary(value)))
        return int(value["status"] == "fail")
    with tempfile.TemporaryDirectory(prefix="manual-ai-summary-") as directory:
        target = str(Path(directory) / "summary.json")
        command = [sys.executable, str(Path(__file__).resolve()),
                   *(sys.argv[1:] if argv is None else argv), "--worker-summary", target]
        value = supervise(command, target)
    print(json.dumps(validate_summary(value), sort_keys=True))
    return int(value["status"] == "fail")


if __name__ == "__main__":
    raise SystemExit(main())
