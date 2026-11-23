from dataclasses import dataclass
from uuid import UUID, uuid5

RULE_ID = "simulator_state_v1"
NAMESPACE = UUID("8192bfa4-782f-46a7-aea8-10c9b8598f11")
SEVERITIES = {"WARNING": "WARNING", "CRITICAL": "CRITICAL", "FAILED": "FAILURE"}


class AlertEvaluationError(RuntimeError):
    """An evaluator/data invariant failed; never classify this as invalid telemetry."""


@dataclass(frozen=True)
class Transition:
    close_reason: str | None = None
    open_severity: str | None = None
    refresh_existing: bool = False


def episode_id(event_id):
    return uuid5(NAMESPACE, f"{RULE_ID}:{event_id}")


def transition(previous_run, previous_state, run, state):
    if state not in {"HEALTHY", *SEVERITIES}:
        raise AlertEvaluationError("unsupported simulator state")
    severity = SEVERITIES.get(state)
    if previous_run is None:
        return Transition(open_severity=severity)
    if str(previous_run) != str(run):
        return Transition("lifecycle_changed", severity)
    if previous_state != state:
        return Transition("recovered" if state == "HEALTHY" else "superseded", severity)
    return Transition(refresh_existing=severity is not None)
