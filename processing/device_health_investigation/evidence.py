"""Bounded, read-only alert evidence; no retrieval, generation or HTTP dependency."""

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from device_health_alerts.store import COLUMNS, AlertNotFound
from device_health_ingestion.errors import TransientProcessingError, ValidationError
from device_health_ingestion.store import PostgresConnection
from device_health_ingestion.validation import validate

READING_COLUMNS = "event_id, device_id, run_id, event_time, ingestion_order, payload"


class EvidenceUnavailable(RuntimeError):
    """Required alert evidence is missing or inconsistent; never invent a snapshot."""


def _require(condition):
    if not condition:
        raise EvidenceUnavailable("Alert evidence is unavailable or inconsistent.")


def _json_value(value):
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        _require(value.tzinfo is not None)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def _validate_reading(row):
    try:
        event = validate(
            json.dumps(row["payload"], allow_nan=False).encode("utf-8"),
            row["device_id"].encode("utf-8"),
        )
        _require(
            event["event_id"] == str(row["event_id"])
            and event["device_id"] == row["device_id"]
            and event["run_id"] == str(row["run_id"])
            and datetime.fromisoformat(event["timestamp"]) == row["event_time"]
            and type(row["ingestion_order"]) is int and row["ingestion_order"] > 0
        )
    except (ValidationError, KeyError, TypeError, ValueError, AttributeError, UnicodeError) as error:
        raise EvidenceUnavailable("Alert evidence is unavailable or inconsistent.") from error
    return row


def _identity(row, relation):
    return {
        "event_id": str(row["event_id"]), "device_id": row["device_id"],
        "run_id": str(row["run_id"]), "event_time": _json_value(row["event_time"]),
        "ingestion_order": row["ingestion_order"], "lifecycle_relation": relation,
    }


class EvidenceQueries(PostgresConnection):
    @staticmethod
    def _rows(connection, statement, parameters):
        with connection.cursor(row_factory=dict_row) as cursor:
            return cursor.execute(statement, parameters).fetchall()

    def get(self, alert_id):
        # Invalid identifiers must not connect, execute SQL or expose driver errors.
        alert_id = UUID(str(alert_id))
        try:
            connection = self._connect()
            with connection.transaction():
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                return self._capture(connection, alert_id)
        except (
            psycopg.OperationalError, psycopg.InterfaceError,
            psycopg.errors.SerializationFailure, psycopg.errors.DeadlockDetected,
        ) as error:
            raise TransientProcessingError("database temporarily unavailable") from error
        finally:
            self.close()

    def _capture(self, connection, alert_id):
        alerts = self._rows(
            connection, f"SELECT {COLUMNS} FROM alerts WHERE alert_id = %s", (alert_id,),
        )
        if not alerts:
            raise AlertNotFound()
        alert = alerts[0]
        resolved = alert["status"] == "RESOLVED"
        _require(alert["status"] in {"ACTIVE", "ACKNOWLEDGED", "RESOLVED"})
        _require(resolved == (alert["resolved_event_id"] is not None))
        if resolved:
            _require(
                alert["last_event_id"] == alert["resolved_event_id"]
                and alert["last_event_time"] == alert["resolved_event_time"]
                and alert["resolution_reason"] in {"recovered", "superseded", "lifecycle_changed"}
            )
        else:
            _require(alert["resolution_reason"] is None and alert["resolved_event_time"] is None)
        identifiers = list({
            alert["opening_event_id"], alert["last_event_id"], alert["resolved_event_id"],
        } - {None})
        linked = self._rows(
            connection,
            f"SELECT {READING_COLUMNS} FROM telemetry_inbox WHERE event_id = ANY(%s)",
            (identifiers,),
        )
        by_id = {str(row["event_id"]): _validate_reading(row) for row in linked}
        _require(all(str(identifier) in by_id for identifier in identifiers))
        opening = by_id[str(alert["opening_event_id"])]
        last = by_id[str(alert["last_event_id"])]
        _require(
            opening["device_id"] == last["device_id"] == alert["device_id"]
            and opening["run_id"] == alert["run_id"]
            and opening["event_time"] == alert["opened_event_time"]
            and last["event_time"] == alert["last_event_time"]
            and opening["ingestion_order"] <= last["ingestion_order"]
        )
        next_lifecycle = last["run_id"] != alert["run_id"]
        _require(not next_lifecycle or (resolved and alert["resolution_reason"] == "lifecycle_changed"))
        _require(alert["resolution_reason"] != "lifecycle_changed" or next_lifecycle)

        cutoff = last["ingestion_order"]
        anchors = self._rows(
            connection,
            f"""SELECT {READING_COLUMNS} FROM telemetry_inbox
                WHERE device_id = %s AND run_id = %s AND ingestion_order <= %s
                ORDER BY ingestion_order DESC LIMIT 1""",
            (alert["device_id"], alert["run_id"], cutoff),
        )
        _require(len(anchors) == 1)
        anchor = _validate_reading(anchors[0])
        _require(
            anchor["device_id"] == alert["device_id"] and anchor["run_id"] == alert["run_id"]
            and opening["ingestion_order"] <= anchor["ingestion_order"] <= cutoff
        )
        end = anchor["event_time"]
        try:
            start = end - timedelta(minutes=5)
        except OverflowError as error:
            raise EvidenceUnavailable("Alert evidence is unavailable or inconsistent.") from error
        rows = self._rows(
            connection,
            f"""SELECT {READING_COLUMNS} FROM telemetry_inbox
                WHERE device_id = %s AND run_id = %s AND ingestion_order <= %s
                  AND event_time >= %s AND event_time <= %s
                ORDER BY ingestion_order DESC LIMIT 101""",
            (alert["device_id"], alert["run_id"], anchor["ingestion_order"], start, end),
        )
        _require(bool(rows) and rows[0]["event_id"] == anchor["event_id"])
        selected = list(reversed(rows[:100]))
        previous = 0
        for row in selected:
            _validate_reading(row)
            _require(
                row["device_id"] == alert["device_id"] and row["run_id"] == alert["run_id"]
                and previous < row["ingestion_order"] <= anchor["ingestion_order"]
                and start <= row["event_time"] <= end
            )
            previous = row["ingestion_order"]

        relation = "subsequent_lifecycle" if next_lifecycle else "alert_lifecycle"
        snapshot = _json_value(alert)
        return {
            "schema_version": 1, "data_mode": "simulated",
            "alert_id": snapshot["alert_id"], "device_id": snapshot["device_id"],
            "run_id": snapshot["run_id"], "alert_status": snapshot["status"],
            "evidence": {
                "window_start": _json_value(start), "window_end": _json_value(end),
                "anchor_event_id": str(anchor["event_id"]), "cutoff_ingestion_order": cutoff,
                "reading_count": len(selected), "truncated": len(rows) > 100,
            },
            "sources": {
                "alert": {
                    "source_id": "A001", "snapshot": snapshot,
                    "opening_evidence": _identity(opening, "alert_lifecycle"),
                    "last_evidence": _identity(last, relation),
                    "closing_evidence": _identity(last, relation) if resolved else None,
                },
                "telemetry": [{
                    "source_id": f"E{index:03d}", "event_id": str(row["event_id"]),
                    "ingestion_order": row["ingestion_order"], "event": deepcopy(row["payload"]),
                } for index, row in enumerate(selected, start=1)],
            },
        }
