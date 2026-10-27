import json
import math
import re
import uuid
from datetime import datetime

from .errors import ValidationError

METRICS = (
    "temperature_c",
    "power_draw_w",
    "cpu_utilization_pct",
    "memory_utilization_pct",
    "timing_jitter_ms",
)
REQUIRED = {
    "event_id",
    "run_id",
    "device_id",
    "timestamp",
    "firmware_version",
    "error_count",
    "device_state",
    *METRICS,
}
OPTIONAL = {"actuator_load_pct", "position_error_mm"}
STATES = {"HEALTHY", "WARNING", "CRITICAL", "FAILED"}


def _object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValidationError("duplicate JSON field")
        result[name] = value
    return result


def _constant(_):
    raise ValidationError("non-finite JSON number")


def validate(payload: bytes | None, key: bytes | None) -> dict:
    if payload is None:
        raise ValidationError("telemetry tombstones are unsupported")
    try:
        event = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant
        )
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ValidationError("malformed telemetry JSON") from error
    if not isinstance(event, dict) or not REQUIRED.issubset(event):
        raise ValidationError("required event fields are missing")
    if set(event) - REQUIRED - OPTIONAL:
        raise ValidationError("unsupported event fields")
    for name in ("device_id", "firmware_version"):
        if not isinstance(event[name], str) or not event[name] or "\x00" in event[name]:
            raise ValidationError("invalid device metadata")
        try:
            event[name].encode("utf-8")
        except UnicodeError as error:
            raise ValidationError("invalid Unicode metadata") from error
    if key != event["device_id"].encode("utf-8"):
        raise ValidationError("Kafka key must equal device_id")
    for name in ("event_id", "run_id"):
        try:
            identifier = uuid.UUID(event[name])
            if str(identifier) != event[name] or identifier.int == 0:
                raise ValueError("noncanonical UUID")
        except (ValueError, TypeError, AttributeError) as error:
            raise ValidationError("invalid event or lifecycle UUID") from error
    timestamp = event["timestamp"]
    if not isinstance(timestamp, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", timestamp
    ):
        raise ValidationError("timestamp must be canonical ISO 8601 UTC")
    try:
        datetime.fromisoformat(timestamp)
    except ValueError as error:
        raise ValidationError("invalid calendar timestamp") from error
    for name in (*METRICS, *OPTIONAL):
        if name not in event or (name in OPTIONAL and event[name] is None):
            continue
        value = event[name]
        try:
            finite = type(value) in (int, float) and math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            raise ValidationError("metrics must be finite numbers")
        if name in ("cpu_utilization_pct", "memory_utilization_pct", "actuator_load_pct"):
            if not 0 <= value <= 100:
                raise ValidationError("percentage outside [0, 100]")
        elif name != "temperature_c" and value < 0:
            raise ValidationError("negative operational metric")
    if type(event["error_count"]) is not int or event["error_count"] < 0:
        raise ValidationError("error_count must be a nonnegative integer")
    if not isinstance(event["device_state"], str) or event["device_state"] not in STATES:
        raise ValidationError("unknown device state")
    return event
