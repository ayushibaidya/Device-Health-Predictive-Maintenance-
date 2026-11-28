import json
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

import manual_investigation_smoke as smoke
from device_health_investigation.ollama import ProviderReply
from device_health_investigation.reporting import AIInvalidResponse, ContextUnavailable, MODEL_TAG, OLLAMA_VERSION
from test_investigation_reporting import adapter_factory as adapter_factory, valid_report


@pytest.fixture
def manual_case(adapter_factory, event, monkeypatch):
    for key in smoke.DATABASE_ENV:
        monkeypatch.delenv(key, raising=False)
    event.update(device_id="ai-local-demo", timestamp="2026-01-01T00:00:25Z")
    adapter, alert, _ = adapter_factory()
    evidence = adapter.reader.get(alert["alert_id"])

    class Provider:
        calls = 0
        content = json.dumps(valid_report())

        def generate(self, messages, schema, limits):
            self.calls += 1
            assert limits.context_tokens == 16384 and limits.output_tokens == 2048
            assert "Development-only controlled smoke" in messages[0]["content"]
            return ProviderReply(self.content, MODEL_TAG, smoke.MODEL_DIGEST, OLLAMA_VERSION)

    chunks = tuple(replace(adapter.index.hits[0].chunk, document_id=doc, chunk_id=identity)
                   for doc, identity in smoke.EXCERPTS)
    return evidence, chunks, Provider()


def test_fake_manual_generation_is_conspicuously_labeled_without_validating_gate(manual_case):
    evidence, chunks, provider = manual_case
    result = smoke.generate(evidence, chunks, provider)
    assert result["development_only"] is True
    assert result["selection_mode"] == "manual_pinned_excerpts"
    assert result["automatic_relevance_validated"] is False
    assert result["runbook_owner_approval"] == "pending"
    assert result["result"]["sources"]["telemetry"] == evidence["sources"]["telemetry"]
    assert provider.calls == 1


@pytest.mark.parametrize("name", smoke.DATABASE_ENV)
def test_generation_refuses_database_environment_before_calling_provider(manual_case, monkeypatch, name):
    evidence, chunks, provider = manual_case
    monkeypatch.setenv(name, "CANARY_CREDENTIAL")
    with pytest.raises(ContextUnavailable):
        smoke.generate(evidence, chunks, provider)
    assert provider.calls == 0


@pytest.mark.parametrize("problem", ["device", "run", "count", "gap"])
def test_non_demo_or_inconsistent_evidence_never_calls_provider(manual_case, problem):
    evidence, chunks, provider = manual_case
    evidence = deepcopy(evidence)
    if problem == "device":
        evidence["device_id"] = "production-device"
    elif problem == "run":
        evidence["sources"]["telemetry"][0]["event"]["run_id"] = "11111111-1111-1111-1111-111111111111"
    elif problem == "count":
        evidence["evidence"]["reading_count"] = 3
    else:
        evidence["sources"]["telemetry"][0]["event"]["timestamp"] = "2026-01-01T00:00:24Z"
    with pytest.raises(ContextUnavailable):
        smoke.generate(evidence, chunks, provider)
    assert provider.calls == 0


def test_unknown_citation_rejects_manual_output(manual_case):
    evidence, chunks, provider = manual_case
    value = valid_report()
    value["observations"][0]["source_refs"] = ["E999"]
    provider.content = json.dumps(value)
    with pytest.raises(AIInvalidResponse):
        smoke.generate(evidence, chunks, provider)


def test_unreviewed_chunk_is_rejected_before_provider_call(manual_case):
    evidence, chunks, provider = manual_case
    changed = (replace(chunks[0], chunk_id="unreviewed"), chunks[1])
    with pytest.raises(smoke.AIUnavailable):
        smoke.generate(evidence, changed, provider)
    assert provider.calls == 0


def test_oversized_packet_is_rejected_without_dropping_evidence(manual_case):
    evidence, chunks, provider = manual_case
    evidence["sources"]["alert"]["snapshot"]["message"] = "x" * 20000
    with pytest.raises(ContextUnavailable):
        smoke.generate(evidence, chunks, provider)
    assert provider.calls == 0


def test_worker_saves_full_report_only_with_explicit_option(manual_case, monkeypatch, tmp_path):
    evidence, chunks, provider = manual_case
    target = tmp_path / "report.json"
    monkeypatch.setattr(smoke, "load_packet", lambda path: evidence)
    monkeypatch.setattr(smoke, "selected_chunks", lambda *args: chunks)
    monkeypatch.setattr(smoke, "OllamaClient", lambda *args: provider)
    args = SimpleNamespace(mode="generate", confirm_manual_excerpts=True, packet_file="test-only",
                           manifest="test-only", tokenizer="test-only", save_report=False,
                           report_file=str(target), ollama_url="http://127.0.0.1:11434")
    assert smoke.worker(args)["status"] == "pass" and not target.exists()
    args.save_report = True
    assert smoke.worker(args)["status"] == "pass"
    assert target.stat().st_mode & 0o777 == 0o600
    assert json.loads(target.read_text())["development_only"] is True


def test_generation_requires_explicit_manual_confirmation_before_reading_packet(monkeypatch):
    monkeypatch.setattr(smoke, "load_packet", lambda path: pytest.fail("No packet read before confirmation"))
    result = smoke.worker(SimpleNamespace(mode="generate", confirm_manual_excerpts=False))
    assert result["error_categories"] == ["invalid_request"]


@pytest.mark.parametrize("value", [{}, {"development_only": False, "fixture_id": smoke.FIXTURE, "evidence": {}},
                                   {"development_only": True, "fixture_id": "unknown", "evidence": {}}])
def test_only_marked_local_packets_are_eligible(tmp_path, value):
    path = tmp_path / "packet.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ContextUnavailable):
        smoke.load_packet(path)


def test_manual_provenance_failure_has_safe_specific_stage(manual_case):
    from device_health_investigation.verification import safe_error

    evidence, chunks, provider = manual_case
    provider.generate = lambda *args: ProviderReply(json.dumps(valid_report()), MODEL_TAG,
                                                    "sha256:" + "f" * 64, OLLAMA_VERSION)
    with pytest.raises(AIInvalidResponse) as captured:
        smoke.generate(evidence, chunks, provider)
    assert safe_error(captured.value) == "ai_invalid_response_model_provenance"
