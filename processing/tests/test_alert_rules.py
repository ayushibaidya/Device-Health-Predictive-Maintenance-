from uuid import uuid4

import pytest

from device_health_alerts.rules import AlertEvaluationError, episode_id, transition


@pytest.mark.parametrize("previous", [None, "HEALTHY", "WARNING", "CRITICAL", "FAILED"])
@pytest.mark.parametrize("state", ["HEALTHY", "WARNING", "CRITICAL", "FAILED"])
def test_severity_episode_transitions(previous, state):
    result = transition("run" if previous else None, previous, "run", state)
    severity = {"WARNING": "WARNING", "CRITICAL": "CRITICAL", "FAILED": "FAILURE"}.get(state)
    assert result.open_severity == (severity if state != previous else None)
    assert result.refresh_existing == (state == previous and state != "HEALTHY")
    reason = "recovered" if state == "HEALTHY" else "superseded"
    assert result.close_reason == (reason if previous and previous != state else None)


def test_run_reset_precedes_state_change_and_identity_is_stable():
    assert transition("old", "CRITICAL", "new", "HEALTHY").close_reason == "lifecycle_changed"
    result = transition("old", "WARNING", "new", "WARNING")
    assert result.close_reason == "lifecycle_changed" and result.open_severity == "WARNING"
    event = str(uuid4())
    assert episode_id(event) == episode_id(event)
    assert episode_id(event).version == 5
    assert episode_id(event) != episode_id(str(uuid4()))
    with pytest.raises(AlertEvaluationError):
        transition(None, None, "run", "UNKNOWN")
