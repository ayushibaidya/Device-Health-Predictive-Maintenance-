import json
import subprocess
import sys
from copy import deepcopy

import pytest

from device_health_investigation.reporting import GenerationLimits
from device_health_investigation.verification import (
    Recorder, relay, safe_error, summary, supervise, validate_summary,
)


def test_owner_approved_default_limits():
    limits = GenerationLimits()
    assert (limits.context_tokens, limits.output_tokens, limits.prompt_bytes, limits.timeout_seconds) == (
        16384, 2048, 12000, 90,
    )


@pytest.mark.parametrize("problem", ["extra", "text_count", "boolean", "negative", "huge", "nan", "timing_key", "error", "status", "categories_type"])
def test_summary_validation_rejects_unapproved_or_malicious_fields(problem):
    value = summary(passed=1)
    if problem == "extra":
        value["prompt"] = "CANARY_PROMPT"
    elif problem == "text_count":
        value["counts"]["passed"] = "CANARY_PASSWORD"
    elif problem == "boolean":
        value["counts"]["passed"] = True
    elif problem == "negative":
        value["counts"]["passed"] = -1
    elif problem == "huge":
        value["counts"]["passed"] = 1000001
    elif problem == "nan":
        value["timings_seconds"]["total"] = float("nan")
    elif problem == "timing_key":
        value["timings_seconds"]["CANARY_RECORD"] = 1
    elif problem == "error":
        value["error_categories"] = ["CANARY_REPORT"]
    elif problem == "categories_type":
        value["error_categories"] = "internal_error"
    else:
        value["status"] = "CANARY_SECRET"
    with pytest.raises(ValueError):
        validate_summary(value)


def test_supervisor_drops_failing_child_records_prompts_credentials_and_reports(tmp_path, capsys):
    path = tmp_path / "summary.json"
    expected = summary(failed=1, categories=["test_failure"])
    command = [sys.executable, "-c", "import pathlib,sys; "
               "print('CANARY_PASSWORD CANARY_RECORD CANARY_PROMPT CANARY_REPORT'); "
               "print('CANARY_CREDENTIAL',file=sys.stderr); "
               f"pathlib.Path({str(path)!r}).write_text({json.dumps(expected)!r}); sys.exit(1)"]
    actual = supervise(command, path)
    print(json.dumps(actual))
    captured = capsys.readouterr()
    assert json.loads(captured.out) == expected
    assert "CANARY" not in captured.out + captured.err


@pytest.mark.parametrize("raw", ['{"status":"pass","status":"pass"}', "not-json", '"CANARY"', "x" * 4097])
def test_invalid_child_summary_has_only_fixed_error_category(tmp_path, raw):
    path = tmp_path / "summary.json"
    path.write_text(raw)
    actual = supervise([sys.executable, "-c", "pass"], path)
    assert actual["status"] == "fail" and actual["error_categories"] == ["invalid_summary"]


def test_supervisor_rejects_exit_status_disagreement(tmp_path):
    path = tmp_path / "summary.json"
    path.write_text(json.dumps(summary(passed=1)))
    assert supervise([sys.executable, "-c", "raise SystemExit(1)"], path)["status"] == "fail"


def test_timeout_is_a_safe_category_without_raw_exception(tmp_path):
    actual = supervise([sys.executable, "-c", "import time; time.sleep(1)"], tmp_path / "unused", timeout=0.01)
    assert actual["error_categories"] == ["verification_timeout"]


def test_unknown_exception_message_and_code_are_not_serialized():
    error = RuntimeError("CANARY_PASSWORD")
    error.code = "CANARY_REPORT"
    assert safe_error(error) == "internal_error"


def test_bad_cli_arguments_do_not_echo_their_values():
    result = subprocess.run([sys.executable, "-m", "device_health_investigation.verification", "CANARY_PROMPT"],
                            capture_output=True, text=True)
    assert result.returncode == 2 and "CANARY" not in result.stdout + result.stderr
    assert json.loads(result.stdout)["error_categories"] == ["invalid_request"]


def test_recorder_preserves_error_classification_without_tracebacks():
    from types import SimpleNamespace
    recorder = Recorder()
    report = SimpleNamespace(nodeid="CANARY_ID", failed=False, skipped=False, when="call")
    recorder.pytest_runtest_logreport(report)
    report = deepcopy(report)
    report.failed, report.when = True, "teardown"
    recorder.pytest_runtest_logreport(report)
    assert list(recorder.results.values()) == ["errors"]


@pytest.mark.parametrize("raw,code", [("CANARY_PASSWORD", 125), ('{"prompt":"CANARY_REPORT"}', 0),
                                      (json.dumps(summary(passed=1)), 1)])
def test_outer_relay_validates_and_never_echoes_docker_output(raw, code, capsys):
    assert relay(raw, code) == 1
    output = capsys.readouterr()
    assert "CANARY" not in output.out + output.err
    assert json.loads(output.out)["error_categories"] == ["invalid_summary"]


@pytest.mark.parametrize("stage", [None, "CANARY_SECRET", ["CANARY_SECRET"], {"secret": "CANARY_SECRET"}])
def test_response_stage_must_be_allowlisted_before_serialization(stage):
    from device_health_investigation.reporting import AIInvalidResponse

    error = AIInvalidResponse("CANARY_PROVIDER_RESPONSE", stage=stage)
    category = safe_error(error)
    assert category == "ai_invalid_response"
    assert "CANARY" not in json.dumps(summary(errors=1, categories=[category]))
