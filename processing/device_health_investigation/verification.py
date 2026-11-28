"""Validated aggregate output; child test/demo streams are never forwarded."""

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RESPONSE_STAGES = frozenset({
    "provider_body_limit", "provider_http_truncated", "provider_json", "provider_output_truncated",
    "provider_envelope", "provider_token_budget", "report_json", "report_schema",
    "report_references", "model_provenance",
})
ERRORS = frozenset({
    "test_failure", "test_error", "no_tests", "verification_timeout", "invalid_summary",
    "relevance_unvalidated", "invalid_request", "ai_unavailable", "ai_invalid_response",
    "ai_timeout", "ai_busy", "ai_evidence_unavailable", "database_unavailable",
    "not_found", "internal_error", "missing_runtime", "setup_failed",
}) | frozenset("ai_invalid_response_" + stage for stage in RESPONSE_STAGES)
SUITES = {
    "report": ["tests/test_investigation_reporting.py", "tests/test_ollama_client.py",
               "tests/test_verification.py", "tests/test_manual_investigation_smoke.py"],
    "backend": ["-m", "not integration"],
    "retrieval": ["--confcutdir=tests/investigation", "tests/investigation", "-W", "error::FutureWarning"],
    "database": ["-m", "integration", "tests/test_investigation_evidence_integration.py",
                 "tests/test_alerts_integration.py", "tests/test_local_investigation.py"],
}


def summary(passed=0, failed=0, skipped=0, errors=0, seconds=0, categories=()):
    return validate_summary({
        "status": "fail" if failed or errors else "pass",
        "counts": {"passed": passed, "failed": failed, "skipped": skipped, "errors": errors},
        "timings_seconds": {"total": round(seconds, 3)}, "error_categories": sorted(set(categories)),
    })


def validate_summary(value):
    if not isinstance(value, dict) or set(value) != {
        "status", "counts", "timings_seconds", "error_categories",
    }:
        raise ValueError("Invalid summary")
    counts, timings, categories = value["counts"], value["timings_seconds"], value["error_categories"]
    if (
        not isinstance(counts, dict) or set(counts) != {"passed", "failed", "skipped", "errors"}
        or any(type(n) is not int or not 0 <= n <= 1000000 for n in counts.values())
        or not isinstance(timings, dict) or set(timings) != {"total"}
        or any(type(n) not in (int, float) or not math.isfinite(n) or not 0 <= n <= 86400
               for n in timings.values())
        or not isinstance(categories, list) or any(type(c) is not str or c not in ERRORS for c in categories)
        or len(categories) != len(set(categories))
        or value["status"] != ("fail" if counts["failed"] or counts["errors"] else "pass")
        or bool(categories) != (value["status"] == "fail")
    ):
        raise ValueError("Invalid summary")
    return value


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate summary key")
        value[key] = item
    return value


def relay(raw, returncode):
    """Validate Docker/worker output again at the outer terminal boundary."""
    try:
        if len(raw.encode("utf-8")) > 4096:
            raise ValueError()
        value = validate_summary(json.loads(raw, object_pairs_hook=_object))
        if bool(returncode) != (value["status"] == "fail"):
            raise ValueError()
    except (ValueError, TypeError, UnicodeError, RecursionError):
        value = summary(errors=1, categories=["invalid_summary"])
    print(json.dumps(value, sort_keys=True))
    return int(value["status"] == "fail")


def supervise(command, output_path, timeout=180):
    """A trusted child writes a summary, not raw output, to the explicit temp path."""
    started = time.monotonic()
    try:
        result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=timeout, check=False)
        raw = Path(output_path).read_bytes()
        if len(raw) > 4096:
            raise ValueError()
        value = validate_summary(json.loads(raw, object_pairs_hook=_object))
        if bool(result.returncode) != (value["status"] == "fail"):
            raise ValueError()
        return value
    except subprocess.TimeoutExpired:
        return summary(errors=1, seconds=time.monotonic() - started, categories=["verification_timeout"])
    except (OSError, ValueError, TypeError, RecursionError):
        return summary(errors=1, seconds=time.monotonic() - started, categories=["invalid_summary"])


class Recorder:
    def __init__(self):
        self.results, self.collection_errors = {}, 0

    def pytest_runtest_logreport(self, report):
        # Store classifications only, never longrepr, test IDs in output or captured streams.
        previous = self.results.get(report.nodeid)
        if report.failed:
            self.results[report.nodeid] = "failed" if report.when == "call" else "errors"
        elif previous not in {"failed", "errors"}:
            if report.skipped:
                self.results[report.nodeid] = "skipped"
            elif report.when == "call":
                self.results[report.nodeid] = "passed"

    def pytest_collectreport(self, report):
        self.collection_errors += bool(report.failed)


def run_tests(mode):
    import pytest

    recorder, started = Recorder(), time.monotonic()
    result = pytest.main([*SUITES[mode], "-q", "-o", "cache_dir=/tmp/pytest-cache"], plugins=[recorder])
    counts = {name: list(recorder.results.values()).count(name) for name in ("passed", "failed", "skipped", "errors")}
    counts["errors"] += recorder.collection_errors
    categories = []
    if counts["failed"]:
        categories.append("test_failure")
    if counts["errors"]:
        categories.append("test_error")
    if result and not categories:
        counts["errors"] += 1
        categories.append("no_tests" if int(result) == 5 else "test_error")
    return summary(**counts, seconds=time.monotonic() - started, categories=categories)


def runtime_calibration(args):
    from .embeddings import EmbeddingUnavailable, MiniLMEncoder
    from .index import build_index
    from .relevance import calibrate, load_evaluation
    from .tokenizer import MiniLMTokenizer

    if not args.model_dir:
        raise EmbeddingUnavailable("Provide the existing local MiniLM directory")
    encoder = MiniLMEncoder(args.model_dir)
    tokenizer = MiniLMTokenizer(Path(args.model_dir) / "tokenizer.json")
    index, _ = build_index(args.index, args.manifest, encoder, tokenizer)
    evaluation = load_evaluation(args.evaluation, {chunk.document_id for chunk in index.chunks})
    return encoder, index, calibrate(index, encoder, evaluation)


def safe_error(error):
    # Never serialize exception text, arbitrary .code attributes or type names.
    from .embeddings import EmbeddingFailed, EmbeddingUnavailable
    from .index import IndexInvalid
    from .relevance import RelevanceInvalid
    from .reporting import AIBusy, AIInvalidResponse, AITimeout, AIUnavailable, ContextUnavailable

    if isinstance(error, AIInvalidResponse):
        stage = getattr(error, "stage", None)
        if type(stage) is str and stage in RESPONSE_STAGES:
            return "ai_invalid_response_" + stage
        return "ai_invalid_response"

    for kind, category in (
        (AIBusy, "ai_busy"), (AIInvalidResponse, "ai_invalid_response"), (AITimeout, "ai_timeout"),
        (AIUnavailable, "ai_unavailable"), (ContextUnavailable, "ai_evidence_unavailable"),
        (EmbeddingFailed, "ai_unavailable"), (EmbeddingUnavailable, "ai_unavailable"),
        (IndexInvalid, "ai_unavailable"), (RelevanceInvalid, "ai_unavailable"),
    ):
        if isinstance(error, kind):
            return category
    # These imports are optional in the retrieval-only image.
    try:
        import psycopg
        from device_health_ingestion.errors import TransientProcessingError
        from .evidence import EvidenceUnavailable
        if isinstance(error, (TransientProcessingError, psycopg.OperationalError, psycopg.InterfaceError)):
            return "database_unavailable"
        if isinstance(error, EvidenceUnavailable):
            return "ai_evidence_unavailable"
    except ImportError:
        pass
    return "missing_runtime" if isinstance(error, ImportError) else "internal_error"


def worker(args):
    started = time.monotonic()
    try:
        if args.mode in SUITES:
            return run_tests(args.mode)
        if args.mode == "calibrate":
            _, _, gate = runtime_calibration(args)
            return summary(passed=gate.development.passed + gate.held_out.passed,
                           failed=gate.development.failed + gate.held_out.failed,
                           skipped=gate.held_out.skipped, seconds=time.monotonic() - started,
                           categories=() if gate.enabled else ["relevance_unvalidated"])
        from .local_demo import run_demo
        return run_demo(args, started)
    except Exception as error:
        return summary(errors=1, seconds=time.monotonic() - started, categories=[safe_error(error)])


class Parser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps(summary(errors=1, categories=["invalid_request"])))
        raise SystemExit(2)


def main(argv=None):
    parser = Parser(description="Aggregate local AI verification; raw child output is suppressed")
    parser.add_argument("mode", choices=[*SUITES, "calibrate", "prepare", "generate"])
    parser.add_argument("--model-dir", default=os.getenv("MINILM_MODEL_DIR"))
    parser.add_argument("--manifest", default="../knowledge/manifest.json")
    parser.add_argument("--evaluation", default="../knowledge/evaluation/relevance-v1.json")
    parser.add_argument("--index", default="/tmp/investigation-index.json")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--report-file")
    parser.add_argument("--worker-summary", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker_summary:
        value = worker(args)
        Path(args.worker_summary).write_text(json.dumps(validate_summary(value)))
        return int(value["status"] == "fail")
    with tempfile.TemporaryDirectory(prefix="ai-summary-") as directory:
        output = str(Path(directory) / "summary.json")
        command = [sys.executable, "-m", "device_health_investigation.verification",
                   *(sys.argv[1:] if argv is None else argv), "--worker-summary", output]
        value = supervise(command, output)
    print(json.dumps(validate_summary(value), sort_keys=True))
    return int(value["status"] == "fail")


if __name__ == "__main__":
    raise SystemExit(main())
