import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from device_health_investigation.relevance import (
    Case, Evaluation, RelevanceInvalid, calibrate, load_evaluation, requests_remediation_command,
)


def hit(score, document="allowed"):
    return SimpleNamespace(score=score, chunk=SimpleNamespace(document_id=document))


class Index:
    index_id = "index-one"

    def __init__(self, scores):
        self.scores, self.calls = scores, []

    def search(self, question, encoder, limit):
        assert limit == 3
        self.calls.append(question)
        return self.scores[question]


def evaluation():
    supported = frozenset({"allowed"})
    return Evaluation("evaluation-one", (Case("dev-positive", supported), Case("dev-negative", frozenset())),
                      (Case("held-positive", supported), Case("held-negative", frozenset())))


def index():
    return Index({"dev-positive": (hit(0.8), hit(0.2, "other")), "dev-negative": (hit(0.3, "other"),),
                  "held-positive": (hit(0.9),), "held-negative": (hit(0.1, "other"),)})


def test_threshold_comes_only_from_development_and_filters_each_candidate():
    source = index()
    gate = calibrate(source, None, evaluation())
    assert gate.enabled and gate.threshold == 0.8
    assert source.calls == ["dev-positive", "dev-negative", "held-positive", "held-negative"]
    candidates = (hit(0.9), hit(0.7, "other"), hit(0.1, "other"))
    assert gate("question", candidates, source.index_id) == (candidates[0],)
    assert gate("question", (hit(0.4),), source.index_id) == ()


def test_held_out_scores_do_not_retune_the_development_threshold():
    source = index()
    source.scores["held-positive"] = (hit(0.79),)
    gate = calibrate(source, None, evaluation())
    assert gate.threshold == 0.8 and not gate.enabled
    assert gate.held_out.failed == 1
    assert gate("question", (hit(0.99),), source.index_id) == ()


@pytest.mark.parametrize("question", ["dev-negative", "dev-positive"])
def test_wrong_document_acceptance_disables_gate_before_held_out(question):
    source = index()
    source.scores[question] = (*source.scores[question], hit(0.95, "other"))
    gate = calibrate(source, None, evaluation())
    assert not gate.enabled and gate.development.failed == 1
    assert gate.held_out.skipped == 2
    assert source.calls == ["dev-positive", "dev-negative"]


def test_missing_expected_candidate_disables_gate():
    source = index()
    source.scores["dev-positive"] = (hit(0.9, "other"),)
    gate = calibrate(source, None, evaluation())
    assert gate.threshold is None and not gate.enabled


def test_unsupported_held_out_acceptance_disables_gate():
    source = index()
    source.scores["held-negative"] = (hit(0.85, "other"),)
    gate = calibrate(source, None, evaluation())
    assert not gate.enabled and gate.held_out.failed == 1


@pytest.mark.parametrize("mismatch", ["index", "query", "policy"])
def test_gate_cannot_be_reused_for_different_snapshot_or_query_version(mismatch):
    source = index()
    gate = calibrate(source, None, evaluation())
    if mismatch == "query":
        gate = replace(gate, query_version=2)
    if mismatch == "policy":
        gate = replace(gate, policy_version=1)
    with pytest.raises(RelevanceInvalid):
        gate("question", (), "different" if mismatch == "index" else source.index_id)


@pytest.mark.parametrize("question", [
    "What command repairs the device firmware automatically?",
    "Which shell script resets the device?",
    "Please provide a script to update firmware.",
    "How can I use commands to reboot a device?",
    "Write a command to replace hardware.",
    "Suggest commands that delete records.",
    "Give me a script to flash firmware.",
])
def test_explicit_remediation_command_requests_reject_high_similarity_candidates(question):
    assert requests_remediation_command(question)
    source = index()
    # A topical limitations chunk can score above valid guidance without providing an action.
    source.scores[question] = (hit(0.99),)
    data = replace(evaluation(), development=(evaluation().development[0], Case(question, frozenset())))
    gate = calibrate(source, None, data)
    assert gate.enabled and gate.threshold == 0.8
    assert gate(question, (hit(0.99),), source.index_id) == ()


@pytest.mark.parametrize("question", [
    "How do run identifiers distinguish resets and firmware evidence?",
    "Does the simulator expose a firmware repair command?",
    "What does a changed firmware version establish?",
    "Explain why firmware-update workflows are not implemented.",
    "How should I compare readings across a reset?",
    "What command inspects a firmware version?",
])
def test_read_only_questions_are_not_rejected_by_remediation_guard(question):
    assert not requests_remediation_command(question)


def test_scope_guard_preserves_development_coverage_failure_for_supported_labels():
    question = "What command repairs the device?"
    data = replace(evaluation(), development=(Case(question, frozenset({"allowed"})),
                                               evaluation().development[1]))
    source = index()
    source.scores[question] = (hit(0.9),)
    gate = calibrate(source, None, data)
    assert not gate.enabled and gate.development.failed == 1
    assert gate.held_out.skipped == 2


def test_overlapping_cosine_scores_alone_keep_gate_disabled():
    source = index()
    source.scores["dev-positive"] = (hit(0.48011912149223085),)
    source.scores["dev-negative"] = (hit(0.6364894273640975),)
    gate = calibrate(source, None, evaluation())
    assert gate.threshold == 0.48011912149223085
    assert not gate.enabled and gate.development.failed == 1


@pytest.mark.parametrize("score", [True, float("nan"), float("inf"), 1.1, "0.9"])
def test_invalid_candidate_scores_fail_closed(score):
    gate = calibrate(index(), None, evaluation())
    with pytest.raises(RelevanceInvalid):
        gate("question", (hit(score),), gate.index_id)


def valid_data():
    return {
        "schema_version": 1, "query_version": 1, "review_status": "source_derived_pending_owner_review",
        **{split: [{"question": f"{split}-{i}", "relevant_document_ids": ["allowed"] if i < 6 else []}
                   for i in range(12)] for split in ("development", "held_out")},
    }


def test_evaluation_hash_changes_with_labels_and_never_marks_owner_approval(tmp_path):
    path = tmp_path / "evaluation.json"
    value = valid_data()
    path.write_text(json.dumps(value))
    first = load_evaluation(path, {"allowed"})
    value["development"][0]["question"] += " paraphrase"
    path.write_text(json.dumps(value))
    assert first.fingerprint != load_evaluation(path, {"allowed"}).fingerprint


@pytest.mark.parametrize("problem", ["unknown_source", "duplicate_question", "small", "version", "review", "extra", "duplicate_key", "missing"])
def test_bad_evaluation_is_rejected(tmp_path, problem):
    path = tmp_path / "evaluation.json"
    value = valid_data()
    if problem == "unknown_source":
        value["development"][0]["relevant_document_ids"] = ["unknown"]
    elif problem == "duplicate_question":
        value["held_out"][0]["question"] = value["development"][0]["question"]
    elif problem == "small":
        value["held_out"] = value["held_out"][:6]
    elif problem == "version":
        value["query_version"] = 2
    elif problem == "review":
        value["review_status"] = "owner_approved"
    elif problem == "extra":
        value["threshold"] = 0.5
    if problem != "missing":
        raw = json.dumps(value)
        if problem == "duplicate_key":
            raw = '{"schema_version":1,' + raw[1:]
            assert json.loads(raw) == value
        path.write_text(raw)
    with pytest.raises(RelevanceInvalid):
        load_evaluation(path, {"allowed"})
