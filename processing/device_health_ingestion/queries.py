"""Bounded, parameterized reads over the durable inbox; reusable by the future API."""

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import psycopg

from .errors import TransientProcessingError
from .store import PostgresConnection


@dataclass(frozen=True)
class Reading:
    ingestion_order: int
    event: dict

    def as_dict(self):
        return {"ingestion_order": self.ingestion_order, "event": self.event}


def time_bound(value):
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as error:
        raise ValueError("time bounds must be ISO 8601 timestamps with a timezone") from error
    if parsed.tzinfo is None:
        raise ValueError("time bounds require a timezone")
    return parsed.astimezone(timezone.utc)


class TelemetryQueries(PostgresConnection):
    def _read(self, sql, parameters):
        try:
            return self._connect().execute(sql, parameters).fetchall()
        except (psycopg.OperationalError, psycopg.InterfaceError) as error:
            self.close()
            raise TransientProcessingError("database temporarily unavailable") from error

    def latest(self, device_id):
        rows = self._read(
            """SELECT ingestion_order, payload FROM telemetry_inbox
               WHERE device_id = %s ORDER BY ingestion_order DESC LIMIT 1""",
            (device_id,),
        )
        return Reading(*rows[0]) if rows else None

    def latest_page(self, *, after_device="", limit=500):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("limit must be an integer in [1, 1000]")
        # Index-backed lookup of one reading for each device in this bounded page.
        rows = self._read(
            """SELECT latest.ingestion_order, latest.payload FROM (
                   SELECT DISTINCT device_id FROM telemetry_inbox
                   WHERE device_id > %s ORDER BY device_id LIMIT %s
               ) AS devices CROSS JOIN LATERAL (
                   SELECT ingestion_order, payload FROM telemetry_inbox
                   WHERE device_id = devices.device_id ORDER BY ingestion_order DESC LIMIT 1
               ) AS latest ORDER BY devices.device_id""",
            (after_device, limit),
        )
        return [Reading(*row) for row in rows]

    def history(self, device_id, *, run_id=None, start=None, end=None, limit=100, before=None):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("limit must be an integer in [1, 1000]")
        if before is not None and (type(before) is not int or before <= 0):
            raise ValueError("before must be a positive ingestion_order")
        if not isinstance(device_id, str) or not device_id or "\x00" in device_id:
            raise ValueError("device_id must be nonempty text without NUL")
        if run_id is not None:
            run_id = str(UUID(run_id))
        start, end = time_bound(start), time_bound(end)
        if start is not None and end is not None and start > end:
            raise ValueError("start must be before or equal to end")
        clauses, parameters = ["device_id = %s"], [device_id]
        for clause, value in (
            ("run_id = %s", run_id),
            ("event_time >= %s", start),
            ("event_time <= %s", end),
            ("ingestion_order < %s", before),
        ):
            if value is not None:
                clauses.append(clause)
                parameters.append(value)
        parameters.append(limit + 1)
        rows = self._read(
            "SELECT ingestion_order, payload FROM telemetry_inbox WHERE "
            + " AND ".join(clauses)
            + " ORDER BY ingestion_order DESC LIMIT %s",
            parameters,
        )
        items = [Reading(*row).as_dict() for row in rows[:limit]]
        return {
            "items": items,
            "next_before": items[-1]["ingestion_order"] if len(rows) > limit else None,
        }
