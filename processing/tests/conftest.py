import json
import uuid

import pytest

from device_health_ingestion.core import Record


@pytest.fixture
def event():
    return {
        "event_id": str(uuid.uuid4()),
        "run_id": str(uuid.uuid4()),
        "device_id": "device-test",
        "timestamp": "2026-01-01T00:00:00Z",
        "firmware_version": "1.0.0",
        "temperature_c": 40.0,
        "power_draw_w": 5.0,
        "cpu_utilization_pct": 20.0,
        "memory_utilization_pct": 30.0,
        "timing_jitter_ms": 1.0,
        "error_count": 0,
        "device_state": "HEALTHY",
    }


@pytest.fixture
def record(event):
    return Record(
        "device.telemetry.v1", 0, 0, event["device_id"].encode(), json.dumps(event).encode()
    )
