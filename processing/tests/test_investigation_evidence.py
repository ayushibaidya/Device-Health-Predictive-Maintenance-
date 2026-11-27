import json
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import psycopg
import pytest

from device_health_alerts.store import AlertNotFound
from device_health_ingestion.errors import TransientProcessingError
from device_health_investigation.evidence import EvidenceQueries, EvidenceUnavailable


def reading(event, order, **changes):
    payload = dict(event, event_id=str(uuid4()), device_state="WARNING", **changes)
    return {
        "event_id": UUID(payload["event_id"]), "device_id": payload["device_id"],
        "run_id": UUID(payload["run_id"]),
        "event_time": datetime.fromisoformat(payload["timestamp"]),
        "ingestion_order": order, "payload": payload,
    }


class FakeConnection:
    def __init__(self, responses):
        self.responses = responses
        self.statements = []
        self.closed = self.in_transaction = False
        self.finished = None

    @contextmanager
    def transaction(self):
        self.in_transaction = True
        try:
            yield
        except Exception:
            self.finished = "rollback"
            raise
        else:
            self.finished = "commit"
        finally:
            self.in_transaction = False

    def execute(self, statement):
        assert self.in_transaction
        self.statements.append((statement, ()))

    @contextmanager
    def cursor(self, **kwargs):
        connection = self

        class Cursor:
            def execute(self, statement, parameters):
                assert connection.in_transaction
                connection.statements.append((statement, parameters))
                self.result = connection.responses.pop(0)
                if isinstance(self.result, Exception):
                    raise self.result
                return self

            def fetchall(self):
                return self.result

        yield Cursor()

    def close(self):
        assert not self.in_transaction
        self.closed = True


@pytest.fixture
def snapshot_setup(event):
    opening = reading(event, 1)
    last = reading(event, 3, timestamp="2026-01-01T00:00:30Z")
    now = datetime(2026, 11, 27, tzinfo=timezone.utc)
    alert = {
        "alert_id": uuid4(), "alert_order": 1, "device_id": event["device_id"],
        "run_id": UUID(event["run_id"]), "rule_id": "simulator_state_v1", "source": "simulator",
        "severity": "WARNING", "status": "ACTIVE", "message": "Simulator reported WARNING.",
        "opening_event_id": opening["event_id"], "last_event_id": last["event_id"],
        "resolved_event_id": None, "opened_event_time": opening["event_time"],
        "last_event_time": last["event_time"], "resolved_event_time": None,
        "created_at": now, "updated_at": now, "acknowledged_at": None,
        "resolved_at": None, "resolution_reason": None,
    }
    return alert, opening, last


def capture(alert, linked, anchor, rows):
    connection = FakeConnection([[alert], linked, [anchor] if anchor else [], rows])
    reader = EvidenceQueries("test-only-not-a-database")
    reader.connection = connection
    return reader, connection


def test_read_only_snapshot_sources_are_json_safe_and_resources_close(snapshot_setup):
    alert, opening, last = snapshot_setup
    reader, connection = capture(alert, [opening, last], last, [last, opening])
    result = reader.get(alert["alert_id"])
    assert connection.statements[0][0] == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
    assert all(sql.lstrip().startswith(("SELECT", "SET")) for sql, _ in connection.statements)
    assert connection.closed and reader.connection is None and connection.finished == "commit"
    assert result["sources"]["alert"]["source_id"] == "A001"
    assert result["sources"]["alert"]["snapshot"]["alert_id"] == str(alert["alert_id"])
    assert result["sources"]["alert"]["closing_evidence"] is None
    assert [source["source_id"] for source in result["sources"]["telemetry"]] == ["E001", "E002"]
    assert result["evidence"]["cutoff_ingestion_order"] == 3
    assert result["evidence"]["window_start"] == "2025-12-31T23:55:30Z"
    assert result["sources"]["telemetry"][0]["event"] == opening["payload"]
    before = json.dumps(result, allow_nan=False)
    opening["payload"]["temperature_c"] = 9999
    alert["status"] = "ACKNOWLEDGED"
    assert json.dumps(result, allow_nan=False) == before


@pytest.mark.parametrize("status,reason", [
    ("ACTIVE", None), ("ACKNOWLEDGED", None),
    ("RESOLVED", "recovered"), ("RESOLVED", "superseded"),
])
def test_all_alert_statuses_and_same_run_closures(snapshot_setup, status, reason):
    alert, opening, last = snapshot_setup
    alert["status"], alert["resolution_reason"] = status, reason
    if status == "ACKNOWLEDGED":
        alert["acknowledged_at"] = alert["updated_at"]
    if reason:
        last["payload"]["device_state"] = "HEALTHY" if reason == "recovered" else "CRITICAL"
        alert.update(resolved_event_id=last["event_id"], resolved_event_time=last["event_time"],
                     resolved_at=alert["updated_at"])
    reader, _ = capture(alert, [opening, last], last, [last, opening])
    result = reader.get(alert["alert_id"])
    assert result["alert_status"] == status
    assert result["sources"]["alert"]["last_evidence"]["lifecycle_relation"] == "alert_lifecycle"
    assert bool(result["sources"]["alert"]["closing_evidence"]) == bool(reason)


def test_next_lifecycle_closure_is_identity_only_despite_restarted_clock(snapshot_setup, event):
    alert, opening, old_last = snapshot_setup
    closing = reading(event, 4, run_id=str(uuid4()), timestamp="2025-01-01T00:00:00Z",
                      temperature_c=9999)
    alert.update(status="RESOLVED", resolution_reason="lifecycle_changed",
                 last_event_id=closing["event_id"], last_event_time=closing["event_time"],
                 resolved_event_id=closing["event_id"], resolved_event_time=closing["event_time"],
                 resolved_at=alert["updated_at"])
    reader, _ = capture(alert, [opening, closing], old_last, [old_last, opening])
    result = reader.get(alert["alert_id"])
    source = result["sources"]["alert"]
    assert source["last_evidence"] == source["closing_evidence"]
    assert source["closing_evidence"]["lifecycle_relation"] == "subsequent_lifecycle"
    assert "payload" not in source["closing_evidence"] and "event" not in source["closing_evidence"]
    assert "9999" not in json.dumps(result)
    assert result["evidence"]["anchor_event_id"] == str(old_last["event_id"])
    assert result["evidence"]["cutoff_ingestion_order"] == 4
    assert all(item["event"]["run_id"] == str(alert["run_id"])
               for item in result["sources"]["telemetry"])


def test_sparse_window_keeps_opening_as_metadata_without_inventing_evidence(snapshot_setup):
    alert, opening, last = snapshot_setup
    opening["event_time"] -= timedelta(minutes=10)
    opening["payload"]["timestamp"] = opening["event_time"].isoformat().replace("+00:00", "Z")
    alert["opened_event_time"] = opening["event_time"]
    reader, _ = capture(alert, [opening, last], last, [last])
    result = reader.get(alert["alert_id"])
    assert result["evidence"]["reading_count"] == 1
    assert result["evidence"]["truncated"] is False
    assert result["sources"]["alert"]["opening_evidence"]["event_id"] == str(opening["event_id"])
    assert result["sources"]["telemetry"][0]["event_id"] == str(last["event_id"])
    assert "status" not in result and "report" not in result


@pytest.mark.parametrize("timestamp,unavailable", [
    ("0001-01-01T00:00:00Z", True),
    ("0001-01-01T00:04:59Z", True),
    ("0001-01-01T00:05:00Z", False),
])
def test_calendar_boundary_preserves_window_and_closes_resources(snapshot_setup, timestamp, unavailable):
    alert, opening, last = snapshot_setup
    for row in (opening, last):
        row["payload"]["timestamp"] = timestamp
        row["event_time"] = datetime.fromisoformat(timestamp)
    alert["opened_event_time"], alert["last_event_time"] = opening["event_time"], last["event_time"]
    reader, connection = capture(alert, [opening, last], last, [last, opening])
    if unavailable:
        with pytest.raises(EvidenceUnavailable, match="^Alert evidence is unavailable or inconsistent\\.$") as caught:
            reader.get(alert["alert_id"])
        assert isinstance(caught.value.__cause__, OverflowError)
        assert connection.finished == "rollback"
    else:
        result = reader.get(alert["alert_id"])
        assert result["evidence"]["window_start"] == "0001-01-01T00:00:00Z"
        assert result["evidence"]["window_end"] == timestamp
        assert result["evidence"]["reading_count"] == 2
        assert (
            datetime.fromisoformat(result["evidence"]["window_end"])
            - datetime.fromisoformat(result["evidence"]["window_start"])
        ) == timedelta(minutes=5)
        assert connection.finished == "commit"
    assert connection.closed and reader.connection is None


@pytest.mark.parametrize("missing", ["opening", "last", "anchor", "window"])
def test_missing_required_evidence_is_not_an_insufficient_evidence_success(snapshot_setup, missing):
    alert, opening, last = snapshot_setup
    linked = [row for name, row in [("opening", opening), ("last", last)] if name != missing]
    reader, connection = capture(alert, linked, None if missing == "anchor" else last,
                                 [] if missing == "window" else [last, opening])
    with pytest.raises(EvidenceUnavailable):
        reader.get(alert["alert_id"])
    assert connection.closed and reader.connection is None


@pytest.mark.parametrize("problem", [
    "opening_device", "opening_run", "opening_time", "last_device", "last_run", "last_time",
    "order", "payload_id", "payload_run", "payload_device", "payload_time", "payload_metric",
])
def test_inconsistent_links_or_payloads_fail_explicitly(snapshot_setup, problem):
    alert, opening, last = deepcopy(snapshot_setup)
    if problem == "opening_device":
        opening["device_id"] = opening["payload"]["device_id"] = "another-device"
    elif problem == "opening_run":
        opening["run_id"] = uuid4()
        opening["payload"]["run_id"] = str(opening["run_id"])
    elif problem == "opening_time":
        alert["opened_event_time"] -= timedelta(seconds=1)
    elif problem == "last_device":
        last["device_id"] = last["payload"]["device_id"] = "another-device"
    elif problem == "last_run":
        last["run_id"] = uuid4()
        last["payload"]["run_id"] = str(last["run_id"])
    elif problem == "last_time":
        alert["last_event_time"] += timedelta(seconds=1)
    elif problem == "order":
        opening["ingestion_order"] = 5
    elif problem == "payload_id":
        last["payload"]["event_id"] = str(uuid4())
    elif problem == "payload_run":
        last["payload"]["run_id"] = str(uuid4())
    elif problem == "payload_device":
        last["payload"]["device_id"] = "another-device"
    elif problem == "payload_time":
        last["payload"]["timestamp"] = "2026-01-01T00:00:40Z"
    else:
        last["payload"]["error_count"] = -1
    reader, connection = capture(alert, [opening, last], last, [last, opening])
    with pytest.raises(EvidenceUnavailable):
        reader.get(alert["alert_id"])
    assert connection.closed


def test_resolved_last_and_closing_must_identify_the_same_event(snapshot_setup):
    alert, opening, last = snapshot_setup
    alert.update(status="RESOLVED", resolved_event_id=opening["event_id"],
                 resolved_event_time=opening["event_time"], resolution_reason="recovered",
                 resolved_at=alert["updated_at"])
    reader, _ = capture(alert, [opening, last], last, [last, opening])
    with pytest.raises(EvidenceUnavailable):
        reader.get(alert["alert_id"])


def test_missing_alert_rolls_back_and_closes_connection():
    reader = EvidenceQueries("unused")
    connection = FakeConnection([[]])
    reader.connection = connection
    with pytest.raises(AlertNotFound):
        reader.get(uuid4())
    assert connection.closed and connection.finished == "rollback" and reader.connection is None


@pytest.mark.parametrize("identifier", ["bad-id", "", None, 123])
def test_invalid_identifier_fails_without_database_access(identifier):
    reader = EvidenceQueries("unused")
    with pytest.raises(ValueError):
        reader.get(identifier)
    assert reader.connection is None


@pytest.mark.parametrize("error_type", [
    psycopg.OperationalError, psycopg.InterfaceError,
    psycopg.errors.SerializationFailure, psycopg.errors.DeadlockDetected,
])
def test_database_failure_is_sanitized_and_connection_closed(error_type):
    reader = EvidenceQueries("unused")
    connection = FakeConnection([error_type("private database details")])
    reader.connection = connection
    with pytest.raises(TransientProcessingError, match="^database temporarily unavailable$"):
        reader.get(uuid4())
    assert connection.closed and reader.connection is None
