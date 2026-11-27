import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo

from device_health_api.app import create_app
from device_health_ingestion.latest import RedisLatest
from device_health_ingestion.migrate import migrate
from device_health_ingestion.queries import TelemetryQueries
from device_health_ingestion.store import PostgresInbox, database_dsn
from test_persistence_integration import accept

pytestmark = pytest.mark.integration


@pytest.fixture
def http():
    with httpx.Client(base_url=os.environ["API_BASE_URL"], timeout=15) as client:
        yield client


@pytest.fixture
def isolated_database():
    schema = "api_" + uuid.uuid4().hex
    with psycopg.connect(database_dsn(), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            yield make_conninfo(database_dsn(), options=f"-c search_path={schema}")
        finally:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_real_http_reads_cpp_events_and_paginates_devices(http):
    events = [
        json.loads(line)
        for line in Path("/fixtures/producer-events.jsonl").read_text().splitlines()
    ]
    summary = http.get("/api/v1/fleet/summary")
    assert summary.status_code == 200
    assert summary.json()["total_devices"] >= 3
    assert summary.json()["total_devices"] == sum(summary.json()["by_state"].values())
    seen, cursor = [], ""
    for _ in range(100):
        page = http.get("/api/v1/devices", params={"limit": 1, "after_device": cursor})
        assert page.status_code == 200
        body = page.json()
        seen.extend(item["event"]["device_id"] for item in body["items"])
        cursor = body["next_after_device"]
        if cursor is None:
            break
    else:
        raise AssertionError("Device pagination did not terminate")
    assert len(seen) == len(set(seen)) == summary.json()["total_devices"]
    assert set(("device-001", "device-002", "device-003")).issubset(seen)
    for device in ("device-001", "device-002", "device-003"):
        expected = [event for event in events if event["device_id"] == device][-1]
        response = http.get(f"/api/v1/devices/{device}")
        assert response.status_code == 200
        assert response.json()["event"] == expected
        assert response.json()["data_mode"] == "simulated"


def test_real_http_history_filters_reset_and_pagination(http):
    events = [
        json.loads(line)
        for line in Path("/fixtures/producer-events.jsonl").read_text().splitlines()
    ]
    expected = [event for event in events if event["device_id"] == "device-002"]
    route = "/api/v1/devices/device-002/telemetry"
    page = http.get(route, params={"limit": 1}).json()
    assert page["items"][0]["event"] == expected[-1]
    second = http.get(route, params={"limit": 1, "before": page["next_before"]}).json()
    assert second["items"][0]["event"] == expected[-2]
    filtered = http.get(
        route,
        params={
            "run_id": expected[-1]["run_id"],
            "start": expected[-1]["timestamp"],
            "end": expected[-1]["timestamp"],
        },
    ).json()
    assert [item["event"] for item in filtered["items"]] == [expected[-1]]
    assert len(http.get(route, params={"run_id": expected[0]["run_id"]}).json()["items"]) == 1
    empty = http.get(route, params={"start": "2099-01-01T00:00:00Z"})
    assert empty.status_code == 200 and empty.json()["items"] == []
    assert http.get("/api/v1/devices/not-an-observed-device").status_code == 404
    assert http.get(route, params={"before": -1}).status_code == 422


def test_real_http_health_docs_and_read_only_methods(http):
    assert http.get("/health/live").json() == {"status": "alive"}
    assert http.get("/health/ready").json() == {"status": "ready", "database": "up", "cache": "up"}
    assert http.get("/docs").status_code == 200
    assert "/api/v1/fleet/summary" in http.get("/openapi.json").json()["paths"]
    assert http.post("/api/v1/devices").status_code == 405


def test_actual_redis_connection_failure_allows_http_reads():
    cache = RedisLatest("redis://redis:1/0")
    app = create_app(dsn=database_dsn(), cache_factory=lambda: cache)
    with TestClient(app) as client:
        assert client.get("/health/ready").json() == {
            "status": "ready",
            "database": "up",
            "cache": "degraded",
        }
        response = client.get("/api/v1/devices/device-001")
        assert response.status_code == 200
        assert response.json()["event"]["device_id"] == "device-001"


def test_actual_database_connection_failure_keeps_liveness_and_sanitizes_errors(capsys):
    app = create_app(dsn=make_conninfo(database_dsn(), port=1), cache_factory=lambda: None)
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        for path in (
            "/health/ready",
            "/api/v1/fleet/summary",
            "/api/v1/devices",
            "/api/v1/devices/device-001",
            "/api/v1/devices/device-001/telemetry",
        ):
            response = client.get(path)
            assert response.status_code == 503
            assert response.json() == {
                "error": {
                    "code": "service_unavailable",
                    "message": "Durable storage is unavailable.",
                }
            }
            assert "password" not in response.text.lower()
    assert os.environ["PGPASSWORD"] not in capsys.readouterr().err


def test_concurrent_http_requests_use_separate_real_database_connections():
    connections = []

    class TrackingQueries(TelemetryQueries):
        def close(self):
            if self.connection is not None:
                connections.append(self.connection)
            super().close()

    app = create_app(
        dsn=database_dsn(), cache_factory=lambda: None, queries_factory=TrackingQueries
    )
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.get("/api/v1/devices/device-001"), range(12)))
    assert all(response.status_code == 200 for response in responses)
    assert len(connections) == len({id(connection) for connection in connections}) == 12
    assert all(connection.closed for connection in connections)


def test_fleet_counts_latest_accepted_state_not_old_lifecycle_or_duplicates(
    isolated_database, event
):
    migrate(isolated_database)
    inbox = PostgresInbox(isolated_database)
    initial = dict(event, device_id="a", device_state="WARNING")
    try:
        assert accept(inbox, initial, 0)
        for offset, (device, state) in enumerate(
            (("b", "HEALTHY"), ("c", "CRITICAL"), ("d", "FAILED")),
            start=1,
        ):
            assert accept(
                inbox,
                dict(event, event_id=str(uuid.uuid4()), device_id=device, device_state=state),
                offset,
            )
        reset = dict(
            initial, event_id=str(uuid.uuid4()), run_id=str(uuid.uuid4()), device_state="HEALTHY"
        )
        assert accept(inbox, reset, 4)
        assert not accept(inbox, initial, 5)
        app = create_app(dsn=isolated_database, cache_factory=lambda: None)
        with TestClient(app) as client:
            assert client.get("/api/v1/fleet/summary").json() == {
                "data_mode": "simulated",
                "total_devices": 4,
                "by_state": {"HEALTHY": 2, "WARNING": 0, "CRITICAL": 1, "FAILED": 1},
            }
            assert client.get("/api/v1/devices/a").json()["event"] == reset
    finally:
        inbox.close()


def test_readiness_requires_migrations_and_empty_fleet_is_valid(isolated_database):
    app = create_app(dsn=isolated_database, cache_factory=lambda: None)
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
        migrate(isolated_database)
        assert client.get("/health/ready").status_code == 200
        assert client.get("/api/v1/devices").json() == {
            "data_mode": "simulated",
            "items": [],
            "next_after_device": None,
        }
        summary = client.get("/api/v1/fleet/summary").json()
        assert summary["total_devices"] == 0 and sum(summary["by_state"].values()) == 0
