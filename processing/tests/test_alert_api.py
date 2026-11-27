from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from device_health_alerts.store import AlertNotFound, AlertResolved
from device_health_api.app import create_app
from device_health_ingestion.errors import TransientProcessingError


@pytest.fixture
def alerts_api():
    class Queries:
        failure = None
        arguments = None
        closed = 0

        def __init__(self, _):
            pass

        def close(self):
            type(self).closed += 1

        def page(self, **arguments):
            type(self).arguments = arguments
            if self.failure:
                raise self.failure
            return {"items": [], "next_before": None}

        def get(self, _):
            raise self.failure or AlertNotFound()

        acknowledge = get

        def latest(self, device):
            return object() if device == "known" else None

    with TestClient(
        create_app(
            dsn="unused",
            cache_factory=lambda: None,
            queries_factory=Queries,
            alert_queries_factory=Queries,
        )
    ) as client:
        yield client, Queries


def test_alert_list_contract_and_filters(alerts_api):
    client, queries = alerts_api
    response = client.get(
        "/api/v1/alerts?status=ACTIVE&status=ACKNOWLEDGED&severity=FAILURE&limit=5&before=12&device_id=known"
    )
    assert response.json() == {"data_mode": "simulated", "items": [], "next_before": None}
    assert queries.arguments == dict(
        device_id="known",
        statuses=["ACTIVE", "ACKNOWLEDGED"],
        severity="FAILURE",
        limit=5,
        before=12,
    )
    assert client.get("/api/v1/devices/known/alerts").status_code == 200
    assert client.get("/api/v1/devices/missing/alerts").status_code == 404
    assert queries.closed == 5


@pytest.mark.parametrize(
    "suffix",
    ["?status=OPEN", "?severity=FAILED", "?limit=0", "?limit=1001", "?before=0", "?device_id=%00"],
)
def test_invalid_alert_queries(alerts_api, suffix):
    response = alerts_api[0].get("/api/v1/alerts" + suffix)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_alert_errors_are_sanitized_and_connections_closed(alerts_api):
    client, queries = alerts_api
    path = f"/api/v1/alerts/{uuid4()}"
    assert client.get(path).status_code == 404
    assert client.post(path + "/acknowledge").status_code == 404
    queries.failure = AlertResolved()
    response = client.post(path + "/acknowledge")
    assert response.status_code == 409 and response.json()["error"]["code"] == "alert_resolved"
    queries.failure = TransientProcessingError("secret-dsn")
    response = client.post(path + "/acknowledge")
    assert response.status_code == 503 and "secret-dsn" not in response.text
    queries.failure = RuntimeError("secret-dsn")
    response = client.get(path)
    assert response.status_code == 500 and "secret-dsn" not in response.text
    assert client.post("/api/v1/alerts/not-a-uuid/acknowledge").status_code == 422
    assert queries.closed >= 5
