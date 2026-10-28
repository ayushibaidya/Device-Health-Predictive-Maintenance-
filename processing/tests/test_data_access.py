import pytest

from device_health_ingestion.errors import TransientProcessingError
from device_health_ingestion.latest import CacheUnavailable, LatestState
from device_health_ingestion.queries import Reading, TelemetryQueries


class UnavailableCache:
    def get(self, _):
        raise CacheUnavailable()

    def put(self, _):
        raise CacheUnavailable()


def test_cache_outage_falls_back_and_does_not_hide_database_failure(event):
    class Queries:
        def latest(self, _):
            return Reading(1, event)

    latest = LatestState(Queries(), UnavailableCache())
    assert latest.get(event["device_id"]).event == event
    assert latest.refresh(event["device_id"]) is False

    class FailedQueries:
        def latest(self, _):
            raise TransientProcessingError()

    latest = LatestState(FailedQueries(), UnavailableCache())
    with pytest.raises(TransientProcessingError):
        latest.get(event["device_id"])
    assert latest.refresh(event["device_id"]) is False


@pytest.mark.parametrize(
    "arguments",
    [
        {"limit": 0},
        {"limit": 1001},
        {"limit": True},
        {"before": -1},
        {"start": "2026-01-01"},
        {"end": "bad"},
        {"run_id": "bad"},
        {"start": "2026-01-02T00:00:00Z", "end": "2026-01-01T00:00:00Z"},
    ],
)
def test_invalid_history_bounds_fail_before_database_access(arguments):
    queries = TelemetryQueries("not-a-database")
    with pytest.raises(ValueError):
        queries.history("device-test", **arguments)
    assert queries.connection is None
