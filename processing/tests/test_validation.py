import json

import pytest

from device_health_ingestion.errors import ValidationError
from device_health_ingestion.validation import validate


def test_valid_event_round_trips(event, record):
    assert validate(record.payload, record.key) == event


@pytest.mark.parametrize(
    "field,value",
    [
        ("event_id", ""),
        ("event_id", "00000000-0000-0000-0000-000000000000"),
        ("run_id", 1),
        ("device_id", ""),
        ("firmware_version", None),
        ("firmware_version", "\ud800"),
        ("temperature_c", True),
        ("temperature_c", None),
        ("power_draw_w", -1),
        ("cpu_utilization_pct", 101),
        ("memory_utilization_pct", -1),
        ("timing_jitter_ms", float("nan")),
        ("timing_jitter_ms", float("inf")),
        ("error_count", True),
        ("error_count", -1),
        ("error_count", 1.1),
        ("device_state", "UNKNOWN"),
        ("device_state", []),
        ("timestamp", "2026-02-29T00:00:00Z"),
        ("timestamp", "2026-01-01T00:00:00+00:00"),
        ("timestamp", "2026-01-01T00:00:60Z"),
        ("hidden_degradation", 0.5),
    ],
)
def test_invalid_fields_are_rejected(event, field, value):
    event[field] = value
    with pytest.raises(ValidationError):
        validate(json.dumps(event).encode(), b"device-test")


@pytest.mark.parametrize(
    "payload", [None, b"", b"{broken", b"[]", b"null", b"\xff", b'{"event_id":1,"event_id":2}']
)
def test_malformed_records_are_rejected(payload):
    with pytest.raises(ValidationError):
        validate(payload, b"device-test")


@pytest.mark.parametrize("key", [None, b"another-device", b""])
def test_message_key_must_match_device(record, key):
    with pytest.raises(ValidationError):
        validate(record.payload, key)


def test_missing_required_field(event):
    del event["run_id"]
    with pytest.raises(ValidationError):
        validate(json.dumps(event).encode(), b"device-test")


def test_optional_actuator_fields(event):
    event.update(actuator_load_pct=50.0, position_error_mm=None)
    assert validate(json.dumps(event).encode(), b"device-test") == event
