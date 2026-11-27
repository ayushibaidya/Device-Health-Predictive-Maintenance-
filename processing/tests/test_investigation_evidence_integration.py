import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Event
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb

from device_health_alerts.rules import episode_id
from device_health_alerts.store import AlertNotFound, AlertQueries
from device_health_ingestion.core import Record
from device_health_ingestion.errors import TransientProcessingError
from device_health_ingestion.migrate import migrate
from device_health_ingestion.store import PostgresInbox, database_dsn
from device_health_investigation.evidence import EvidenceQueries, EvidenceUnavailable

pytestmark = pytest.mark.integration


@pytest.fixture
def evidence_db():
    schema = "investigation_" + uuid4().hex
    with psycopg.connect(database_dsn(), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        dsn = make_conninfo(database_dsn(), options=f"-c search_path={schema}")
        inbox, alerts, reader = PostgresInbox(dsn), AlertQueries(dsn), EvidenceQueries(dsn)
        try:
            migrate(dsn)
            yield dsn, inbox, alerts, reader
        finally:
            inbox.close()
            alerts.close()
            reader.close()
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def sample(event, state="WARNING", seconds=0, **changes):
    value = deepcopy(event)
    value.update(event_id=str(uuid4()), device_state=state, **changes)
    value["timestamp"] = (
        datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    ).isoformat().replace("+00:00", "Z")
    return value


def accept(inbox, event, offset):
    record = Record("device.telemetry.v1", 0, offset, event["device_id"].encode(), json.dumps(event).encode())
    assert inbox.persist(event, record)
    return episode_id(event["event_id"])


def telemetry_ids(snapshot):
    return [source["event_id"] for source in snapshot["sources"]["telemetry"]]


def table_state(dsn):
    with psycopg.connect(dsn) as connection:
        return connection.execute("""SELECT
            (SELECT jsonb_agg(t ORDER BY ingestion_order) FROM telemetry_inbox t),
            (SELECT jsonb_agg(a ORDER BY alert_order) FROM alerts a),
            (SELECT jsonb_agg(s ORDER BY device_id) FROM alert_evaluation_state s)""").fetchone()


@pytest.mark.parametrize("status", ["ACTIVE", "ACKNOWLEDGED", "RESOLVED"])
def test_real_snapshot_for_all_alert_statuses(evidence_db, event, status):
    _, inbox, alerts, reader = evidence_db
    opening = sample(event)
    alert_id = accept(inbox, opening, 0)
    if status == "ACKNOWLEDGED":
        alerts.acknowledge(alert_id)
    if status == "RESOLVED":
        accept(inbox, sample(event, "HEALTHY", 5), 1)
    result = reader.get(alert_id)
    assert result["alert_status"] == result["sources"]["alert"]["snapshot"]["status"] == status
    assert result["alert_id"] == str(alert_id)
    assert result["sources"]["alert"]["source_id"] == "A001"
    assert result["evidence"]["reading_count"] == (2 if status == "RESOLVED" else 1)
    assert reader.connection is None
    json.dumps(result, allow_nan=False)


def test_inclusive_simulation_window_and_accepted_order_cutoff(evidence_db, event):
    _, inbox, _, reader = evidence_db
    old = sample(event, "HEALTHY", 299)
    boundary = sample(event, "HEALTHY", 300)
    opening = sample(event, "WARNING", 480)
    future_time = sample(event, "WARNING", 630)
    closing = sample(event, "HEALTHY", 600)
    after_cutoff = sample(event, "HEALTHY", 540)
    for offset, row in enumerate([old, boundary, opening, future_time]):
        accept(inbox, row, offset)
    # This device is inside both time/order bounds; only device isolation excludes it.
    accept(inbox, sample(event, "HEALTHY", 600, device_id="another-device"), 4)
    accept(inbox, closing, 5)
    accept(inbox, after_cutoff, 6)
    result = reader.get(episode_id(opening["event_id"]))
    assert telemetry_ids(result) == [row["event_id"] for row in [boundary, opening, closing]]
    assert result["evidence"]["window_start"] == "2026-01-01T00:05:00Z"
    assert result["evidence"]["window_end"] == "2026-01-01T00:10:00Z"
    assert result["evidence"]["anchor_event_id"] == closing["event_id"]
    sources = result["sources"]["telemetry"]
    assert [source["source_id"] for source in sources] == ["E001", "E002", "E003"]
    assert [source["ingestion_order"] for source in sources] == sorted(source["ingestion_order"] for source in sources)
    assert all(source["ingestion_order"] <= result["evidence"]["cutoff_ingestion_order"] for source in sources)


@pytest.mark.parametrize("count", [99, 100, 101])
def test_newest_100_readings_and_exact_truncation_boundary(evidence_db, event, count):
    _, inbox, _, reader = evidence_db
    rows = [sample(event) for _ in range(count)]
    alert_id = episode_id(rows[0]["event_id"])
    for offset, row in enumerate(rows):
        accept(inbox, row, offset)
    result = reader.get(alert_id)
    assert telemetry_ids(result) == [row["event_id"] for row in rows[-100:]]
    assert result["evidence"]["reading_count"] == min(count, 100)
    assert result["evidence"]["truncated"] is (count > 100)
    assert result["sources"]["alert"]["opening_evidence"]["event_id"] == rows[0]["event_id"]
    if count == 101:
        assert rows[0]["event_id"] not in telemetry_ids(result)


def test_lifecycle_closing_metadata_never_imports_new_run_metrics(evidence_db, event):
    _, inbox, _, reader = evidence_db
    opening = sample(event, "FAILED", 600)
    old_last = sample(event, "FAILED", 605)
    new_run = str(uuid4())
    closing = sample(event, "HEALTHY", 0, run_id=new_run, temperature_c=9999)
    new_last = sample(event, "WARNING", 5, run_id=new_run)
    for offset, row in enumerate([opening, old_last, closing, new_last]):
        accept(inbox, row, offset)
    result = reader.get(episode_id(opening["event_id"]))
    assert telemetry_ids(result) == [opening["event_id"], old_last["event_id"]]
    assert result["run_id"] == event["run_id"]
    assert result["evidence"]["window_end"] == old_last["timestamp"]
    assert result["evidence"]["anchor_event_id"] == old_last["event_id"]
    source = result["sources"]["alert"]
    assert source["snapshot"]["resolution_reason"] == "lifecycle_changed"
    assert source["last_evidence"] == source["closing_evidence"]
    assert source["closing_evidence"]["run_id"] == new_run
    assert source["closing_evidence"]["lifecycle_relation"] == "subsequent_lifecycle"
    assert "9999" not in json.dumps(result)


def test_previous_lifecycle_inside_time_and_order_bounds_is_excluded(evidence_db, event):
    _, inbox, _, reader = evidence_db
    old = sample(event, "WARNING", 120)
    new_run = str(uuid4())
    start = sample(event, "HEALTHY", 0, run_id=new_run)
    opening = sample(event, "WARNING", 60, run_id=new_run)
    last = sample(event, "WARNING", 300, run_id=new_run)
    for offset, row in enumerate([old, start, opening, last]):
        accept(inbox, row, offset)
    result = reader.get(episode_id(opening["event_id"]))
    # The old row passes time/device/cutoff filters; only run isolation excludes it.
    assert telemetry_ids(result) == [start["event_id"], opening["event_id"], last["event_id"]]
    assert result["evidence"]["window_start"] == "2026-01-01T00:00:00Z"
    assert all(source["event"]["run_id"] == new_run for source in result["sources"]["telemetry"])


def test_opening_outside_window_remains_identity_only(evidence_db, event):
    _, inbox, _, reader = evidence_db
    opening, last = sample(event), sample(event, seconds=600)
    accept(inbox, opening, 0)
    accept(inbox, last, 1)
    result = reader.get(episode_id(opening["event_id"]))
    assert telemetry_ids(result) == [last["event_id"]]
    assert result["evidence"]["reading_count"] == 1
    assert result["sources"]["alert"]["opening_evidence"]["event_id"] == opening["event_id"]


def test_database_enforces_read_only_and_all_connections_close(evidence_db, event, monkeypatch):
    dsn, inbox, _, reader = evidence_db
    alert_id = accept(inbox, sample(event), 0)
    before = table_state(dsn)
    original = reader._rows
    connections = []

    def observe(connection, statement, parameters):
        assert connection.execute("SHOW transaction_isolation").fetchone()[0] == "repeatable read"
        assert connection.execute("SHOW transaction_read_only").fetchone()[0] == "on"
        if not connections:
            with pytest.raises(psycopg.errors.ReadOnlySqlTransaction) as caught:
                with connection.transaction():
                    connection.execute("DELETE FROM alerts WHERE false")
            assert caught.value.sqlstate == "25006"
        connections.append(connection)
        return original(connection, statement, parameters)

    monkeypatch.setattr(reader, "_rows", observe)
    result = reader.get(alert_id)
    assert all(connection.closed for connection in connections)
    assert reader.connection is None
    assert table_state(dsn) == before
    assert result["evidence"]["reading_count"] == 1


def test_concurrent_acknowledgement_and_new_telemetry_cannot_change_snapshot(evidence_db, event, monkeypatch):
    _, inbox, alerts, reader = evidence_db
    opening = sample(event)
    alert_id = accept(inbox, opening, 0)
    captured, resume = Event(), Event()
    original = reader._rows

    def pause_after_alert(connection, statement, parameters):
        result = original(connection, statement, parameters)
        if "FROM alerts" in statement and not captured.is_set():
            captured.set()
            assert resume.wait(5)
        return result

    monkeypatch.setattr(reader, "_rows", pause_after_alert)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(reader.get, alert_id)
        try:
            assert captured.wait(5)
            alerts.acknowledge(alert_id)
            closing = sample(event, "CRITICAL", 5)
            accept(inbox, closing, 1)
        finally:
            resume.set()
        result = future.result(timeout=5)
    assert result["alert_status"] == "ACTIVE"
    assert result["sources"]["alert"]["closing_evidence"] is None
    assert telemetry_ids(result) == [opening["event_id"]]
    monkeypatch.setattr(reader, "_rows", original)
    later = reader.get(alert_id)
    assert later["alert_status"] == "RESOLVED"
    assert later["sources"]["alert"]["snapshot"]["acknowledged_at"] is not None
    assert telemetry_ids(later) == [opening["event_id"], closing["event_id"]]


@pytest.mark.parametrize("problem", ["wrong_device", "wrong_run", "bad_payload"])
def test_real_inconsistent_linked_evidence_fails_without_returning_metrics(evidence_db, event, problem):
    dsn, inbox, _, reader = evidence_db
    opening = sample(event)
    alert_id = accept(inbox, opening, 0)
    with psycopg.connect(dsn) as connection:
        if problem == "wrong_device":
            payload = dict(opening, device_id="another-device")
            connection.execute("UPDATE telemetry_inbox SET device_id=%s, payload=%s",
                               (payload["device_id"], Jsonb(payload)))
        elif problem == "wrong_run":
            payload = dict(opening, run_id=str(uuid4()))
            connection.execute("UPDATE telemetry_inbox SET run_id=%s, payload=%s",
                               (payload["run_id"], Jsonb(payload)))
        else:
            connection.execute("UPDATE telemetry_inbox SET payload=%s", (Jsonb(dict(opening, error_count=-1)),))
    with pytest.raises(EvidenceUnavailable):
        reader.get(alert_id)
    assert reader.connection is None


def test_missing_alert_and_unreachable_database_are_distinct(evidence_db):
    _, _, _, reader = evidence_db
    with pytest.raises(AlertNotFound):
        reader.get(uuid4())
    assert reader.connection is None
    unavailable = EvidenceQueries("host=127.0.0.1 port=1 dbname=unused user=unused password=private")
    with pytest.raises(TransientProcessingError, match="^database temporarily unavailable$"):
        unavailable.get(uuid4())
    assert unavailable.connection is None
