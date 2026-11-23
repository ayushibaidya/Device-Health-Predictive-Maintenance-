import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb

from device_health_alerts.rules import AlertEvaluationError, episode_id
from device_health_alerts.store import AlertQueries, AlertResolved
from device_health_api.app import create_app
from device_health_ingestion.core import Processor, Record
from device_health_ingestion.migrate import migrate
from device_health_ingestion.store import PostgresInbox, database_dsn
from test_persistence_integration import accept

pytestmark = pytest.mark.integration


@pytest.fixture
def isolated_database():
    schema = "alerts_" + uuid4().hex
    with psycopg.connect(database_dsn(), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            yield make_conninfo(database_dsn(), options=f"-c search_path={schema}")
        finally:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture
def alerts_db(isolated_database):
    migrate(isolated_database)
    inbox, alerts = PostgresInbox(isolated_database), AlertQueries(isolated_database)
    try:
        yield isolated_database, inbox, alerts
    finally:
        inbox.close()
        alerts.close()


def sample(event, state, **changes):
    return dict(event, event_id=str(uuid4()), device_state=state, **changes)


def test_lifecycle_acknowledgement_replay_and_restart(alerts_db, event):
    dsn, inbox, alerts = alerts_db
    warning = sample(event, "WARNING")
    assert accept(inbox, warning, 0)
    first = alerts.page()["items"][0]
    assert first["alert_id"] == episode_id(warning["event_id"])
    ack = alerts.acknowledge(first["alert_id"])
    assert ack["status"] == "ACKNOWLEDGED"
    assert alerts.acknowledge(first["alert_id"]) == ack
    continued = sample(warning, "WARNING", timestamp="2026-01-01T00:00:05Z")
    assert accept(inbox, continued, 1)
    refreshed = alerts.get(first["alert_id"])
    assert str(refreshed["last_event_id"]) == continued["event_id"]
    assert refreshed["acknowledged_at"] == ack["acknowledged_at"]
    inbox.close()
    alerts.close()
    assert not accept(inbox, warning, 2)
    assert alerts.get(first["alert_id"]) == refreshed
    critical = sample(event, "CRITICAL")
    assert accept(inbox, critical, 3)
    old, new = alerts.get(first["alert_id"]), alerts.page()["items"][0]
    assert old["status"] == "RESOLVED" and old["resolution_reason"] == "superseded"
    assert old["acknowledged_at"] == ack["acknowledged_at"]
    assert new["severity"] == "CRITICAL" and new["acknowledged_at"] is None
    assert new["status"] == "ACTIVE"
    with pytest.raises(AlertResolved):
        alerts.acknowledge(first["alert_id"])
    # De-escalation also requires fresh acknowledgement; recovery and recurrence split episodes.
    for index, state in enumerate(("WARNING", "HEALTHY", "FAILED"), start=4):
        assert accept(inbox, sample(event, state), index)
    failure = alerts.page()["items"][0]
    assert failure["severity"] == "FAILURE"
    reset = sample(event, "FAILED", run_id=str(uuid4()), timestamp="2025-01-01T00:00:00Z")
    assert accept(inbox, reset, 10)
    assert alerts.get(failure["alert_id"])["resolution_reason"] == "lifecycle_changed"
    rows = alerts.page()["items"]
    assert len(rows) == 5 and sum(row["status"] == "ACTIVE" for row in rows) == 1
    assert "recovered" in {row["resolution_reason"] for row in rows}
    with psycopg.connect(dsn) as connection:
        assert connection.execute("SELECT count(*) FROM telemetry_inbox").fetchone()[0] == 7


def test_evaluator_failure_rolls_back_inbox_alert_cursor_and_never_commits(
    alerts_db, event, monkeypatch
):
    dsn, inbox, _ = alerts_db
    from device_health_ingestion import store

    real_evaluate = store.evaluate

    def fail_after_evaluation(*args):
        real_evaluate(*args)
        raise AlertEvaluationError("injected evaluator failure")

    monkeypatch.setattr(store, "evaluate", fail_after_evaluation)
    warning = sample(event, "WARNING")
    record = Record(
        "device.telemetry.v1", 0, 0, event["device_id"].encode(), json.dumps(warning).encode()
    )
    committed, dead_letters = [], []
    processor = Processor(inbox, dead_letters.append)
    with pytest.raises(AlertEvaluationError):
        processor.process(record, lambda: committed.append(True))
    assert committed == dead_letters == []
    with psycopg.connect(dsn) as connection:
        for table in ("telemetry_inbox", "alerts", "alert_evaluation_state"):
            assert connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    monkeypatch.setattr(store, "evaluate", real_evaluate)
    assert accept(inbox, warning, 1)


def test_real_database_api_filters_pagination_and_acknowledgement(alerts_db, event):
    dsn, inbox, _ = alerts_db
    for offset, state in enumerate(("WARNING", "CRITICAL", "HEALTHY", "FAILED")):
        accept(inbox, sample(event, state), offset)
    with TestClient(create_app(dsn=dsn, cache_factory=lambda: None)) as client:
        page = client.get("/api/v1/alerts?limit=1").json()
        failure = page["items"][0]
        assert failure["severity"] == "FAILURE" and failure["status"] == "ACTIVE"
        assert failure["acknowledged_at"] is None and failure["resolved_at"] is None
        assert failure["opened_event_time"].endswith("Z")
        tail = client.get(f"/api/v1/alerts?before={page['next_before']}").json()
        assert len(tail["items"]) == 2 and tail["next_before"] is None
        assert client.get("/api/v1/alerts?status=ACTIVE&status=ACKNOWLEDGED").json()["items"] == [
            failure
        ]
        assert len(client.get("/api/v1/alerts?status=RESOLVED").json()["items"]) == 2
        assert (
            client.get("/api/v1/alerts?severity=WARNING").json()["items"][0]["resolution_reason"]
            == "superseded"
        )
        path = f"/api/v1/alerts/{failure['alert_id']}"
        assert client.get(path).json() == {"data_mode": "simulated", **failure}
        acknowledged = client.post(path + "/acknowledge").json()
        assert acknowledged["acknowledged_at"] and acknowledged["status"] == "ACKNOWLEDGED"
        assert client.post(path + "/acknowledge").json() == acknowledged
        assert len(client.get(f"/api/v1/devices/{event['device_id']}/alerts").json()["items"]) == 3
        assert client.get("/api/v1/devices/missing/alerts").status_code == 404
        assert client.get(f"/api/v1/alerts/{uuid4()}").status_code == 404
        assert (
            client.post(f"/api/v1/alerts/{tail['items'][0]['alert_id']}/acknowledge").status_code
            == 409
        )


def legacy_rows(dsn, events):
    with psycopg.connect(dsn) as connection:
        connection.execute((Path("migrations") / "001_telemetry_inbox.sql").read_text())
        for offset, event in enumerate(events):
            connection.execute(
                """INSERT INTO telemetry_inbox
                   (event_id, run_id, device_id, event_time, payload, source_topic, source_partition, source_offset)
                   VALUES (%s,%s,%s,%s,%s,'device.telemetry.v1',0,%s)""",
                (
                    event["event_id"],
                    event["run_id"],
                    event["device_id"],
                    event["timestamp"],
                    Jsonb(event),
                    offset,
                ),
            )


def test_backfill_reuses_live_evaluator_and_is_repeatable(isolated_database, event):
    readings = [sample(event, state) for state in ("WARNING", "CRITICAL", "HEALTHY", "FAILED")]
    # 001 is deliberately pre-existing without migration markers, as on the original demo database.
    with psycopg.connect(isolated_database) as connection:
        connection.execute((Path("migrations") / "001_telemetry_inbox.sql").read_text())
    # Only raw inserts can seed a pre-alert schema.
    legacy_rows(isolated_database, readings)
    assert len(migrate(isolated_database)) == 3
    assert migrate(isolated_database) == []
    alerts, inbox = AlertQueries(isolated_database), PostgresInbox(isolated_database)
    try:
        before = alerts.page()["items"]
        assert len(before) == 3
        assert {row["alert_id"] for row in before} == {
            episode_id(e["event_id"]) for e in readings if e["device_state"] != "HEALTHY"
        }
        for offset, reading in enumerate(readings):
            assert not accept(inbox, reading, offset)
        assert alerts.page()["items"] == before
    finally:
        alerts.close()
        inbox.close()


def test_bad_history_rolls_back_entire_backfill_and_marker(isolated_database, event):
    legacy_rows(isolated_database, [sample(event, "WARNING"), sample(event, "UNKNOWN")])
    with pytest.raises(ValueError):
        migrate(isolated_database)
    with psycopg.connect(isolated_database) as connection:
        assert connection.execute("SELECT to_regclass('alerts')").fetchone()[0] is None
        assert connection.execute("SELECT count(*) FROM telemetry_inbox").fetchone()[0] == 2


def test_concurrent_first_events_and_acknowledgements_serialize(alerts_db, event):
    dsn, _, alerts = alerts_db
    warning = sample(event, "WARNING")

    def persist(index):
        inbox = PostgresInbox(dsn)
        try:
            return accept(inbox, warning, index)
        finally:
            inbox.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(persist, range(8))) == 1
    opened = alerts.page()["items"][0]

    def acknowledge(_):
        query = AlertQueries(dsn)
        try:
            return query.acknowledge(opened["alert_id"])["acknowledged_at"]
        finally:
            query.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert len(set(pool.map(acknowledge, range(8)))) == 1


def test_distinct_concurrent_events_follow_accepted_order(alerts_db, event):
    dsn, _, alerts = alerts_db
    readings = [sample(event, state) for state in ("WARNING", "CRITICAL", "FAILED", "HEALTHY") * 4]

    def persist(pair):
        offset, reading = pair
        inbox = PostgresInbox(dsn)
        try:
            return accept(inbox, reading, offset)
        finally:
            inbox.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(pool.map(persist, enumerate(readings)))
    with psycopg.connect(dsn) as connection:
        accepted = connection.execute(
            "SELECT payload FROM telemetry_inbox ORDER BY ingestion_order"
        ).fetchall()
        progress = connection.execute(
            "SELECT last_state, last_ingestion_order FROM alert_evaluation_state"
        ).fetchone()
        last_order = connection.execute(
            "SELECT max(ingestion_order) FROM telemetry_inbox"
        ).fetchone()[0]
    expected, previous = set(), None
    for (reading,) in accepted:
        if reading["device_state"] != previous and reading["device_state"] != "HEALTHY":
            expected.add(episode_id(reading["event_id"]))
        previous = reading["device_state"]
    assert {row["alert_id"] for row in alerts.page()["items"]} == expected
    assert progress == (previous, last_order)
    assert sum(row["status"] != "RESOLVED" for row in alerts.page()["items"]) == (
        previous != "HEALTHY"
    )


@pytest.mark.parametrize("ack_first", [True, False])
def test_ack_resolution_lock_race_is_deterministic(alerts_db, event, ack_first):
    dsn, inbox, alerts = alerts_db
    accept(inbox, sample(event, "WARNING"), 0)
    opened = alerts.page()["items"][0]
    started = Event()

    def other():
        started.set()
        query = AlertQueries(dsn)
        worker = PostgresInbox(dsn)
        try:
            if ack_first:
                return accept(worker, sample(event, "HEALTHY"), 1)
            with pytest.raises(AlertResolved):
                query.acknowledge(opened["alert_id"])
        finally:
            query.close()
            worker.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with psycopg.connect(dsn) as connection:
            connection.execute(
                "SELECT alert_id FROM alerts WHERE alert_id=%s FOR UPDATE", (opened["alert_id"],)
            )
            if ack_first:
                connection.execute(
                    "UPDATE alerts SET status='ACKNOWLEDGED', acknowledged_at=clock_timestamp() WHERE alert_id=%s",
                    (opened["alert_id"],),
                )
            else:
                # Same approved evaluator on this transaction, holding its alert row lock.
                transactional = PostgresInbox(dsn)
                transactional.connection = connection
                accept(transactional, sample(event, "HEALTHY"), 1)
            pending = pool.submit(other)
            assert started.wait(5)
            assert not pending.done()
        pending.result(timeout=10)
    resolved = alerts.get(opened["alert_id"])
    assert resolved["status"] == "RESOLVED"
    assert (resolved["acknowledged_at"] is not None) == ack_first


@pytest.mark.parametrize("first_status", ["ACTIVE", "ACKNOWLEDGED"])
def test_database_rejects_invalid_status_and_second_open_episode(alerts_db, event, first_status):
    dsn, inbox, alerts = alerts_db
    first = sample(event, "WARNING")
    assert accept(inbox, first, 0)
    opened = alerts.page()["items"][0]
    with psycopg.connect(dsn, autocommit=True) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                "UPDATE alerts SET status='ACKNOWLEDGED' WHERE alert_id=%s", (opened["alert_id"],)
            )
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                "UPDATE alerts SET status='RESOLVED' WHERE alert_id=%s", (opened["alert_id"],)
            )
    second = sample(first, "WARNING", timestamp="2026-01-01T00:00:05Z")
    assert accept(inbox, second, 1)
    if first_status == "ACKNOWLEDGED":
        alerts.acknowledge(opened["alert_id"])
    assert alerts.get(opened["alert_id"])["status"] == first_status

    insert_episode = """INSERT INTO alerts
                (alert_id, device_id, run_id, rule_id, source, severity, status, message,
                 opening_event_id, last_event_id, opened_event_time, last_event_time)
                SELECT %s, device_id, run_id, %s, 'simulator', 'WARNING', 'ACTIVE',
                 'Simulator reported WARNING.', event_id, event_id, event_time, event_time
                FROM telemetry_inbox WHERE event_id=%s"""
    with psycopg.connect(dsn, autocommit=True) as connection:
        # Fresh opening evidence avoids the independent opening-event uniqueness guard.
        with pytest.raises(psycopg.errors.UniqueViolation) as duplicate_open:
            connection.execute(
                insert_episode, (uuid4(), opened["rule_id"], second["event_id"])
            )
        assert duplicate_open.value.diag.constraint_name == "alerts_one_open_episode_idx"

    assert accept(inbox, sample(second, "HEALTHY", timestamp="2026-01-01T00:00:10Z"), 2)
    assert alerts.get(opened["alert_id"])["status"] == "RESOLVED"
    with psycopg.connect(dsn, autocommit=True) as connection:
        # Resolution removes the partial-index conflict; duplicate evidence still fails.
        with pytest.raises(psycopg.errors.UniqueViolation) as duplicate_evidence:
            connection.execute(
                insert_episode, (uuid4(), opened["rule_id"], first["event_id"])
            )
        assert (
            duplicate_evidence.value.diag.constraint_name
            == "alerts_rule_id_opening_event_id_key"
        )
        # The fresh evidence can open an episode once the first is resolved.
        assert (
            connection.execute(
                insert_episode, (uuid4(), opened["rule_id"], second["event_id"])
            ).rowcount
            == 1
        )
