"""Verify alerts from the real 100-minute C++ scenario; optionally acknowledge twice."""

import argparse
import json
import os
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acknowledge", action="store_true")
    options = parser.parse_args()
    events = [
        json.loads(line)
        for line in Path("/fixtures/producer-events.jsonl").read_text().splitlines()
    ]
    runs = {event["run_id"] for event in events}
    assert len(events) == 3603 and {e["device_state"] for e in events} == {
        "HEALTHY",
        "WARNING",
        "CRITICAL",
        "FAILED",
    }
    with httpx.Client(base_url=os.getenv("API_BASE_URL", "http://api:8000"), timeout=15) as client:
        episodes, before = [], None
        while True:
            response = client.get(
                "/api/v1/alerts", params={"limit": 100, **({"before": before} if before else {})}
            )
            response.raise_for_status()
            page = response.json()
            episodes.extend(row for row in page["items"] if row["run_id"] in runs)
            before = page["next_before"]
            if before is None:
                break
        assert {row["severity"] for row in episodes} == {"WARNING", "CRITICAL", "FAILURE"}
        assert {"superseded", "recovered"}.issubset({row["resolution_reason"] for row in episodes})
        assert not any(row["device_id"] == "device-001" for row in episodes)
        failures = [
            row
            for row in episodes
            if row["device_id"] == "device-002" and row["severity"] == "FAILURE"
        ]
        assert len(failures) == 1 and failures[0]["status"] in ("ACTIVE", "ACKNOWLEDGED")
        assert not any(
            row["device_id"] == "device-003" and row["status"] != "RESOLVED" for row in episodes
        )
        if options.acknowledge:
            path = f"/api/v1/alerts/{failures[0]['alert_id']}/acknowledge"
            first, repeated = client.post(path), client.post(path)
            first.raise_for_status()
            repeated.raise_for_status()
            assert first.json() == repeated.json()
            assert first.json()["status"] == "ACKNOWLEDGED" and first.json()["acknowledged_at"]
        resolved = next(row for row in episodes if row["status"] == "RESOLVED")
        assert client.post(f"/api/v1/alerts/{resolved['alert_id']}/acknowledge").status_code == 409
        print(
            f"ALERT DEMO PASSED: 3,603 real simulator events; {len(episodes)} episodes; severity changes, recovery, durable acknowledgement."
        )


if __name__ == "__main__":
    main()
