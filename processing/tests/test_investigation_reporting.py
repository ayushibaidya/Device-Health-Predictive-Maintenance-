import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from threading import Event
from types import SimpleNamespace

import pytest

from device_health_investigation.chunking import Chunk
from device_health_investigation.index import IndexInvalid, SearchHit
from device_health_investigation.investigation import InvestigationAdapter
from device_health_investigation.ollama import ProviderReply
from device_health_investigation.reporting import (
    AIBusy, AIInvalidResponse, AITimeout, AIUnavailable, ContextUnavailable,
    GenerationLimits, MODEL_TAG, OLLAMA_VERSION, validate_report,
)
from test_investigation_evidence import capture, snapshot_setup


def valid_report():
    return {
        "observations": [{"text": "The captured alert is WARNING.", "source_refs": ["A001"]}],
        "possible_explanations": [{
            "text": "Hypothesis: The readings may reflect synthetic degradation.",
            "source_refs": ["E001", "D001"],
        }],
        "suggested_checks": [{"text": "Compare same-run readings.", "source_refs": ["D001"]}],
        "limitations": ["The evidence is simulated."],
    }


@pytest.fixture
def adapter_factory(event):
    def create(selector=None):
        alert, opening, last = snapshot_setup.__wrapped__(deepcopy(event))
        reader, connection = capture(alert, [opening, last], last, [last, opening])
        text = "Synthetic degradation can affect readings. Compare same-run evidence."
        chunk = Chunk("a" * 64, "test-guidance", "b" * 64, "runbooks/test-only.md", "Test guidance",
                      ("Test guidance",), 0, len(text), 1, 1, text, text, 20, 0, "test-tokenizer")

        class Index:
            index_id = "c" * 64
            review_status = "source_checked_pending_owner_review"
            hits = (SearchHit(1, 0.8, chunk),)
            calls = 0

            def search(self, query, encoder, limit):
                assert reader.connection is None and connection.closed
                assert limit == 3
                self.calls += 1
                return self.hits

        class Provider:
            calls = 0
            content = json.dumps(valid_report())
            error = None

            def on_generate(self):
                return None

            def generate(self, messages, schema, limits):
                assert reader.connection is None and connection.closed
                self.calls += 1
                self.messages, self.schema = deepcopy(messages), deepcopy(schema)
                self.on_generate()
                if self.error:
                    raise self.error
                return ProviderReply(self.content, MODEL_TAG, "sha256:" + "d" * 64, OLLAMA_VERSION)

        index, provider = Index(), Provider()
        # Test-only accepted guidance; production selection policy remains unapproved.
        selector = selector or (lambda query, candidates, index_id: candidates)
        adapter = InvestigationAdapter(reader, index, SimpleNamespace(profile_id="test-profile"),
                                       provider, GenerationLimits(65536, 2048, 60000), selector)
        return adapter, alert, connection
    return create


def test_fake_provider_complete_report_preserves_captured_sources(adapter_factory):
    adapter, alert, connection = adapter_factory()
    result = adapter.investigate(alert["alert_id"])
    assert result["status"] == "complete"
    assert result["alert_id"] == str(alert["alert_id"])
    assert result["sources"]["alert"]["source_id"] == "A001"
    assert result["sources"]["documents"][0]["source_id"] == "D001"
    assert result["sources"]["documents"][0]["chunk_id"] == "a" * 64
    assert result["provenance"]["model_digest"] == "sha256:" + "d" * 64
    assert result["provenance"]["ollama_version"] == OLLAMA_VERSION
    assert any("owner review" in text for text in result["report"]["limitations"])
    assert connection.closed
    context = json.loads(adapter.provider.messages[1]["content"])["captured_context"]
    assert context["sources"] == result["sources"]
    assert "sources" not in adapter.provider.schema["properties"]


def test_rejected_guidance_returns_insufficient_evidence_without_provider_call(adapter_factory):
    adapter, alert, _ = adapter_factory(lambda query, candidates, index_id: ())
    adapter.provider.error = AIUnavailable("not installed")
    result = adapter.investigate(alert["alert_id"])
    assert result["status"] == "insufficient_evidence"
    assert result["report"]["observations"] == []
    assert result["report"]["possible_explanations"] == []
    assert result["report"]["suggested_checks"] == []
    assert result["sources"]["documents"] == []
    assert result["sources"]["telemetry"]
    assert result["provenance"]["model_digest"] is None
    assert adapter.provider.calls == 0


@pytest.mark.parametrize("problem", [
    "missing", "extra_root", "extra_statement", "unknown_reference", "duplicate_reference",
    "no_reference", "unlabeled_hypothesis", "blank", "html", "url", "wrong_type",
    "document_only_observation", "ungrounded_hypothesis", "unguided_check", "empty_observations",
    "empty_checks", "empty_limitations",
])
def test_invalid_model_reports_are_rejected(problem):
    value = valid_report()
    statement = value["observations"][0]
    if problem == "missing":
        value.pop("observations")
    elif problem == "extra_root":
        value["sources"] = {"A001": "altered"}
    elif problem == "extra_statement":
        statement["confidence"] = 0.99
    elif problem == "unknown_reference":
        statement["source_refs"] = ["E999"]
    elif problem == "duplicate_reference":
        statement["source_refs"] = ["A001", "A001"]
    elif problem == "no_reference":
        statement["source_refs"] = []
    elif problem == "unlabeled_hypothesis":
        value["possible_explanations"][0]["text"] = "A certain diagnosis."
    elif problem == "blank":
        statement["text"] = "  "
    elif problem == "html":
        statement["text"] = "<script>bad</script>"
    elif problem == "url":
        statement["text"] = "See https://example.com"
    elif problem == "wrong_type":
        statement["text"] = 123
    elif problem == "document_only_observation":
        statement["source_refs"] = ["D001"]
    elif problem == "ungrounded_hypothesis":
        value["possible_explanations"][0]["source_refs"] = ["D001"]
    elif problem == "unguided_check":
        value["suggested_checks"][0]["source_refs"] = ["A001"]
    elif problem == "empty_observations":
        value["observations"] = []
    elif problem == "empty_checks":
        value["suggested_checks"] = []
    else:
        value["limitations"] = []
    with pytest.raises(AIInvalidResponse, match="^The local model returned an invalid investigation report\\.$"):
        validate_report(json.dumps(value), {"A001", "E001", "D001"})


@pytest.mark.parametrize("raw", ["not JSON", "```json\n{}\n```", '{"x":NaN}', "[]"])
def test_malformed_report_json_fails(raw):
    with pytest.raises(AIInvalidResponse):
        validate_report(raw, {"A001", "E001", "D001"})


def test_duplicate_report_key_is_rejected_in_otherwise_valid_report():
    value = valid_report()
    raw = '{"limitations": ["same"], ' + json.dumps(value)[1:]
    # Normal JSON deduplication gives a complete valid report; only duplicate detection fails.
    assert json.loads(raw) == value
    with pytest.raises(AIInvalidResponse):
        validate_report(raw, {"A001", "E001", "D001"})


@pytest.mark.parametrize("error", [AIUnavailable("offline"), AITimeout("timeout"), AIInvalidResponse("invalid")])
def test_provider_errors_propagate_and_admission_is_released(adapter_factory, error):
    adapter, alert, _ = adapter_factory()
    adapter.provider.error = error
    with pytest.raises(type(error)):
        adapter.investigate(alert["alert_id"])
    assert adapter.provider.calls == 1
    next_adapter, next_alert, _ = adapter_factory()
    assert next_adapter.investigate(next_alert["alert_id"])["status"] == "complete"


def test_busy_admission_is_shared_and_held_until_provider_returns(adapter_factory):
    adapter, alert, _ = adapter_factory()
    entered, release = Event(), Event()

    def block():
        entered.set()
        assert release.wait(5)

    adapter.provider.on_generate = block
    other, other_alert, _ = adapter_factory()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(adapter.investigate, alert["alert_id"])
        try:
            assert entered.wait(5)
            with pytest.raises(AIBusy):
                other.investigate(other_alert["alert_id"])
            assert other.index.calls == other.provider.calls == 0
        finally:
            release.set()
        assert future.result(timeout=5)["status"] == "complete"


def test_prompt_budget_rejects_instead_of_dropping_evidence(adapter_factory):
    adapter, alert, _ = adapter_factory()
    adapter.limits = GenerationLimits(4096, 512, 1)
    with pytest.raises(ContextUnavailable, match="prompt budget"):
        adapter.investigate(alert["alert_id"])
    assert adapter.provider.calls == 0


def test_modified_telemetry_run_is_rejected_before_retrieval(adapter_factory, monkeypatch):
    adapter, alert, _ = adapter_factory()
    original = adapter.reader.get

    def altered(alert_id):
        packet = original(alert_id)
        packet["sources"]["telemetry"][0]["event"]["run_id"] = "11111111-1111-1111-1111-111111111111"
        return packet

    monkeypatch.setattr(adapter.reader, "get", altered)
    with pytest.raises(ContextUnavailable):
        adapter.investigate(alert["alert_id"])
    assert adapter.index.calls == adapter.provider.calls == 0


def test_selector_cannot_invent_or_modify_retrieved_sources(adapter_factory):
    adapter, alert, _ = adapter_factory(lambda q, hits, index_id: [replace(hits[0], score=0.1)])
    with pytest.raises(ContextUnavailable, match="validated retrieval snapshot"):
        adapter.investigate(alert["alert_id"])
    assert adapter.provider.calls == 0


def test_missing_retrieval_assets_are_not_hidden_as_insufficient_evidence(adapter_factory, monkeypatch):
    adapter, alert, _ = adapter_factory()

    def fail(*args, **kwargs):
        raise IndexInvalid("fixture missing index")

    monkeypatch.setattr(adapter.index, "search", fail)
    with pytest.raises(AIUnavailable):
        adapter.investigate(alert["alert_id"])


def test_guidance_rule_is_explicitly_required(adapter_factory):
    adapter, _, _ = adapter_factory()
    with pytest.raises(ValueError, match="guidance-selection rule"):
        InvestigationAdapter(adapter.reader, adapter.index, adapter.encoder, adapter.provider,
                             adapter.limits, None)


def test_disabled_calibrated_gate_does_not_invoke_llm(adapter_factory):
    from device_health_investigation.relevance import Counts, RelevanceGate

    adapter, alert, _ = adapter_factory()
    adapter.select_guidance = RelevanceGate(adapter.index.index_id, "evaluation", 1, None,
                                            Counts(failed=1), Counts(skipped=1))
    result = adapter.investigate(alert["alert_id"])
    assert result["status"] == "insufficient_evidence"
    assert adapter.provider.calls == 0


def test_incompatible_gate_is_an_availability_error(adapter_factory):
    from device_health_investigation.relevance import Counts, RelevanceGate

    adapter, alert, _ = adapter_factory()
    adapter.select_guidance = RelevanceGate("different-index", "evaluation", 1, 0.7,
                                            Counts(passed=1), Counts(passed=1))
    with pytest.raises(AIUnavailable):
        adapter.investigate(alert["alert_id"])
    assert adapter.provider.calls == 0


@pytest.mark.parametrize("stage", ["report_json", "report_schema", "report_references"])
def test_report_validation_stage_is_specific_and_does_not_expose_inputs(stage):
    from device_health_investigation.verification import safe_error, summary

    value = valid_report()
    value["observations"][0]["text"] = "CANARY_PROVIDER_RESPONSE"
    if stage == "report_schema":
        value.pop("limitations")
    elif stage == "report_references":
        value["observations"][0]["source_refs"] = ["CANARY_REFERENCE"]
    raw = "CANARY_INVALID_JSON" if stage == "report_json" else json.dumps(value)
    with pytest.raises(AIInvalidResponse) as captured:
        validate_report(raw, {"A001", "E001", "D001"})
    assert captured.value.code == "ai_invalid_response" and captured.value.stage == stage
    category = safe_error(captured.value)
    assert category == "ai_invalid_response_" + stage
    assert "CANARY" not in json.dumps(summary(errors=1, categories=[category]))
