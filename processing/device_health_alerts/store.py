import psycopg
from psycopg.rows import dict_row

from device_health_ingestion.errors import TransientProcessingError
from device_health_ingestion.store import PostgresConnection

COLUMNS = """alert_id, alert_order, device_id, run_id, rule_id, source, severity,
    status, message, opening_event_id, last_event_id, resolved_event_id,
    opened_event_time, last_event_time, resolved_event_time, created_at,
    updated_at, acknowledged_at, resolved_at, resolution_reason"""


class AlertNotFound(Exception):
    pass


class AlertResolved(Exception):
    pass


class AlertQueries(PostgresConnection):
    def _operation(self, operation):
        try:
            return operation(self._connect())
        except (
            psycopg.OperationalError,
            psycopg.InterfaceError,
            psycopg.errors.SerializationFailure,
            psycopg.errors.DeadlockDetected,
        ) as error:
            self.close()
            raise TransientProcessingError("database temporarily unavailable") from error

    @staticmethod
    def _rows(connection, sql, parameters):
        with connection.cursor(row_factory=dict_row) as cursor:
            return cursor.execute(sql, parameters).fetchall()

    def get(self, alert_id):
        rows = self._operation(
            lambda connection: self._rows(
                connection,
                f"SELECT {COLUMNS} FROM alerts WHERE alert_id = %s",
                (alert_id,),
            )
        )
        if not rows:
            raise AlertNotFound()
        return rows[0]

    def page(self, *, device_id=None, statuses=None, severity=None, limit=100, before=None):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("limit must be in [1, 1000]")
        if before is not None and (type(before) is not int or before <= 0):
            raise ValueError("before must be positive")
        if statuses is not None and any(
            s not in ("ACTIVE", "ACKNOWLEDGED", "RESOLVED") for s in statuses
        ):
            raise ValueError("invalid alert status")
        if severity is not None and severity not in ("WARNING", "CRITICAL", "FAILURE"):
            raise ValueError("invalid alert severity")
        clauses, parameters = ["TRUE"], []
        for clause, value in (
            ("device_id = %s", device_id),
            ("status = ANY(%s)", statuses),
            ("severity = %s", severity),
            ("alert_order < %s", before),
        ):
            if value is not None:
                clauses.append(clause)
                parameters.append(value)
        parameters.append(limit + 1)
        rows = self._operation(
            lambda connection: self._rows(
                connection,
                f"SELECT {COLUMNS} FROM alerts WHERE "
                + " AND ".join(clauses)
                + " ORDER BY alert_order DESC LIMIT %s",
                parameters,
            )
        )
        return {
            "items": rows[:limit],
            "next_before": rows[limit - 1]["alert_order"] if len(rows) > limit else None,
        }

    def acknowledge(self, alert_id):
        def operation(connection):
            with connection.transaction():
                rows = self._rows(
                    connection,
                    f"SELECT {COLUMNS} FROM alerts WHERE alert_id = %s FOR UPDATE",
                    (alert_id,),
                )
                if not rows:
                    raise AlertNotFound()
                alert = rows[0]
                if alert["status"] == "RESOLVED":
                    raise AlertResolved()
                if alert["status"] == "ACTIVE":
                    alert = self._rows(
                        connection,
                        f"""UPDATE alerts SET status = 'ACKNOWLEDGED',
                            acknowledged_at = clock_timestamp(), updated_at = clock_timestamp()
                            WHERE alert_id = %s RETURNING {COLUMNS}""",
                        (alert_id,),
                    )[0]
                return alert

        return self._operation(operation)
