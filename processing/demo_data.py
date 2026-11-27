"""Show history, latest state, and recovery using actual simulator telemetry."""

import json
import pathlib

from device_health_ingestion.latest import LatestState, configured_cache
from device_health_ingestion.queries import TelemetryQueries
from device_health_ingestion.store import database_dsn


def main():
    events = [
        json.loads(line)
        for line in pathlib.Path("/fixtures/producer-events.jsonl").read_text().splitlines()
    ]
    device = "device-002"
    expected = [event for event in events if event["device_id"] == device][-1]
    queries, cache = TelemetryQueries(database_dsn()), configured_cache()
    assert cache is not None
    try:
        latest = LatestState(queries, cache)
        history = queries.history(device, run_id=expected["run_id"])
        assert expected["event_id"] in [item["event"]["event_id"] for item in history["items"]]
        print(
            json.dumps(
                {
                    "demo": "history",
                    "device_id": device,
                    "run_id": expected["run_id"],
                    "readings": len(history["items"]),
                }
            )
        )
        assert latest.get(device).event == expected
        assert cache.get(device).event == expected
        print(json.dumps({"demo": "latest", "event": expected}))
        # Delete only this disposable device cache entry to demonstrate PostgreSQL fallback.
        cache.client.delete(cache.key(device))
        assert cache.get(device) is None
        assert latest.get(device).event == expected
        assert cache.get(device).event == expected
        print("Empty cache recovered automatically from PostgreSQL.")
        rebuilt = latest.rebuild()
        assert rebuilt["failed"] == 0 and rebuilt["refreshed"] >= 3
        print(json.dumps({"demo": "cache_rebuild", **rebuilt}))
        print("DATA ACCESS DEMO PASSED: history, current state, and cache recovery.")
    finally:
        queries.close()
        cache.close()


if __name__ == "__main__":
    main()
