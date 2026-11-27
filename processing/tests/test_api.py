from concurrent.futures import ThreadPoolExecutor

import pytest
import redis
from fastapi.testclient import TestClient

from device_health_api.app import create_app
from device_health_ingestion.errors import TransientProcessingError
from device_health_ingestion.latest import CacheUnavailable
from device_health_ingestion.queries import Reading


@pytest.fixture
def api(event):
    class Queries:
        instances = []
        failure = None
        available = True
        history_arguments = None

        def __init__(self, _):
            self.closed = False
            self.instances.append(self)

        def latest(self, device_id):
            if self.failure:
                raise self.failure
            return Reading(5, event) if device_id == event["device_id"] else None

        def latest_page(self, *, after_device, limit):
            return [Reading(5, event)] if after_device < event["device_id"] else []

        def history(self, device_id, **kwargs):
            type(self).history_arguments = (device_id, kwargs)
            return {"items": [Reading(5, event).as_dict()], "next_before": None}

        def fleet_summary(self):
            return {
                "total_devices": 1,
                "by_state": {"HEALTHY": 1, "WARNING": 0, "CRITICAL": 0, "FAILED": 0},
            }

        def ready(self):
            if self.failure:
                raise self.failure
            return self.available

        def close(self):
            self.closed = True

    app = create_app(dsn="unused", cache_factory=lambda: None, queries_factory=Queries)
    with TestClient(app) as client:
        yield client, Queries
    assert all(query.closed for query in Queries.instances)


def test_read_contracts_preserve_event_and_absent_optional_fields(api, event):
    client, _ = api
    reading = {"ingestion_order": 5, "event": event}
    assert client.get("/api/v1/devices/device-test").json() == {"data_mode": "simulated", **reading}
    assert client.get("/api/v1/devices").json() == {
        "data_mode": "simulated",
        "items": [reading],
        "next_after_device": None,
    }
    assert client.get("/api/v1/devices/device-test/telemetry").json() == {
        "data_mode": "simulated",
        "items": [reading],
        "next_before": None,
    }
    assert client.get("/api/v1/fleet/summary").json() == {
        "data_mode": "simulated",
        "total_devices": 1,
        "by_state": {"HEALTHY": 1, "WARNING": 0, "CRITICAL": 0, "FAILED": 0},
    }
    assert client.get("/api/v1/devices?limit=1000").status_code == 200
    event["actuator_load_pct"] = None
    event["position_error_mm"] = 1.5
    assert client.get("/api/v1/devices/device-test").json()["event"] == event


def test_history_passes_existing_filters_and_cursors(api, event):
    client, queries = api
    parameters = {
        "run_id": event["run_id"],
        "start": "2026-01-01T00:00:00Z",
        "end": "2026-01-02T00:00:00+00:00",
        "limit": 2,
        "before": 9,
    }
    response = client.get("/api/v1/devices/device-test/telemetry", params=parameters)
    assert response.status_code == 200
    assert queries.history_arguments == (event["device_id"], parameters)


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/devices?limit=0",
        "/api/v1/devices?limit=1001",
        "/api/v1/devices?limit=bad",
        "/api/v1/devices?after_device=%00",
        "/api/v1/devices/%00",
        "/api/v1/devices/device-test/telemetry?before=0",
        "/api/v1/devices/device-test/telemetry?run_id=bad",
        "/api/v1/devices/device-test/telemetry?start=2026-01-01",
        "/api/v1/devices/device-test/telemetry?end=bad",
        "/api/v1/devices/device-test/telemetry?start=0001-01-01T00:00:00%2B23:59",
        "/api/v1/devices/device-test/telemetry?start=2026-01-02T00:00:00Z&end=2026-01-01T00:00:00Z",
    ],
)
def test_invalid_requests_are_sanitized(api, path):
    client, _ = api
    response = client.get(path)
    assert response.status_code == 422
    assert response.json() == {
        "error": {"code": "invalid_request", "message": "Request parameters are invalid."}
    }


@pytest.mark.parametrize(
    "path", ["/api/v1/devices/unknown", "/api/v1/devices/unknown/telemetry", "/unknown"]
)
def test_unknown_resources(api, path):
    response = api[0].get(path)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_read_only_and_cors_disabled(api):
    client, _ = api
    response = client.post("/api/v1/devices")
    assert response.status_code == 405 and response.headers["allow"] == "GET"
    assert response.json()["error"]["code"] == "method_not_allowed"
    response = client.get("/api/v1/devices", headers={"Origin": "https://example.com"})
    assert "access-control-allow-origin" not in response.headers


def test_health_and_documentation_do_not_require_live_database(api):
    client, queries = api
    queries.failure = TransientProcessingError("sensitive-driver-configuration")
    assert client.get("/health/live").json() == {"status": "alive"}
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert "/api/v1/devices/{device_id}/telemetry" in schema["paths"]
    assert queries.instances == []
    for path in ("/health/ready", "/api/v1/devices/device-test"):
        response = client.get(path)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "service_unavailable"
        assert "sensitive" not in response.text


def test_missing_migration_is_not_ready(api):
    client, queries = api
    queries.available = False
    assert client.get("/health/ready").status_code == 503
    queries.available = True
    assert client.get("/health/ready").json() == {
        "status": "ready",
        "database": "up",
        "cache": "disabled",
    }


def test_unexpected_and_response_errors_hide_driver_details(api, event, capsys):
    client, queries = api
    queries.failure = RuntimeError("postgresql://user:secret-password@host/database")
    response = client.get("/api/v1/devices/device-test")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret-password" not in response.text + capsys.readouterr().err
    queries.failure = None
    event["power_draw_w"] = -1  # Bad stored output is an internal error, not a valid response.
    assert client.get("/api/v1/devices/device-test").status_code == 500


def test_concurrent_requests_own_and_close_query_objects(api):
    client, queries = api
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.get("/api/v1/devices/device-test"), range(12)))
    assert all(response.status_code == 200 for response in responses)
    assert len(queries.instances) == 12
    assert len({id(query) for query in queries.instances}) == 12
    assert all(query.closed for query in queries.instances)


def test_redis_failure_is_degraded_and_reads_fall_back(api, event):
    client, _ = api

    class FailedCache:
        @property
        def client(self):
            return self

        def ping(self):
            raise redis.ConnectionError("secret-driver-message")

        def get(self, _):
            raise CacheUnavailable()

        def put(self, _):
            raise CacheUnavailable()

        def close(self):
            pass

    client.app.state.cache = FailedCache()
    assert client.get("/health/ready").json() == {
        "status": "ready",
        "database": "up",
        "cache": "degraded",
    }
    assert client.get("/api/v1/devices/device-test").json()["event"] == event
