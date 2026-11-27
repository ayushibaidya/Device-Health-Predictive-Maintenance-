"""Exercise the real HTTP service using the C++ simulator's captured events."""

import json
import os
from pathlib import Path

import httpx


def main():
    events = [
        json.loads(line)
        for line in Path("/fixtures/producer-events.jsonl").read_text().splitlines()
    ]
    with httpx.Client(base_url=os.getenv("API_BASE_URL", "http://api:8000"), timeout=15) as client:
        for path in ("/health/live", "/health/ready", "/openapi.json", "/docs"):
            response = client.get(path)
            response.raise_for_status()
        summary = client.get("/api/v1/fleet/summary")
        summary.raise_for_status()
        assert summary.json()["total_devices"] >= 3
        print(json.dumps({"demo": "fleet_summary", **summary.json()}))
        response = client.get("/api/v1/devices", params={"limit": 1})
        response.raise_for_status()
        assert len(response.json()["items"]) == 1
        assert response.json()["next_after_device"] is not None
        for device in ("device-001", "device-002", "device-003"):
            expected = [event for event in events if event["device_id"] == device][-1]
            detail = client.get(f"/api/v1/devices/{device}")
            detail.raise_for_status()
            assert detail.json()["event"] == expected
            history = client.get(
                f"/api/v1/devices/{device}/telemetry", params={"run_id": expected["run_id"]}
            )
            history.raise_for_status()
            assert history.json()["items"][0]["event"] == expected
            print(
                json.dumps(
                    {
                        "demo": "device",
                        "device_id": device,
                        "state": expected["device_state"],
                        "history_readings": len(history.json()["items"]),
                    }
                )
            )
        assert client.get("/api/v1/devices/unknown-demo-device").status_code == 404
        assert client.get("/api/v1/devices?limit=1001").status_code == 422
    print("API DEMO PASSED: simulator -> Kafka -> PostgreSQL/Redis -> HTTP.")


if __name__ == "__main__":
    main()
