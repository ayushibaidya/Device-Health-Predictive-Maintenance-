import json
from datetime import datetime

from psycopg.rows import dict_row

from .rules import AlertEvaluationError, RULE_ID, episode_id, transition


def lock_device(connection, device_id):
    connection.execute(
        """INSERT INTO alert_evaluation_state (device_id, rule_id) VALUES (%s, %s)
           ON CONFLICT (device_id, rule_id) DO NOTHING""",
        (device_id, RULE_ID),
    )
    with connection.cursor(row_factory=dict_row) as cursor:
        return cursor.execute(
            """SELECT * FROM alert_evaluation_state
               WHERE device_id = %s AND rule_id = %s FOR UPDATE""",
            (device_id, RULE_ID),
        ).fetchone()


def evaluate(connection, event, ingestion_order, progress=None):
    progress = progress if progress is not None else lock_device(connection, event["device_id"])
    if ingestion_order <= progress["last_ingestion_order"]:
        return
    decision = transition(
        progress["last_run_id"], progress["last_state"], event["run_id"], event["device_state"]
    )
    open_id = progress["open_alert_id"]
    if open_id is not None and decision.close_reason:
        closed = connection.execute(
            """UPDATE alerts SET status = 'RESOLVED', resolution_reason = %s,
                   resolved_event_id = %s, resolved_event_time = %s,
                   last_event_id = %s, last_event_time = %s,
                   resolved_at = clock_timestamp(), updated_at = clock_timestamp()
               WHERE alert_id = %s AND status IN ('ACTIVE', 'ACKNOWLEDGED')
               RETURNING alert_id""",
            (
                decision.close_reason,
                event["event_id"],
                event["timestamp"],
                event["event_id"],
                event["timestamp"],
                open_id,
            ),
        ).fetchone()
        if closed is None:
            raise AlertEvaluationError("open episode invariant failed")
        open_id = None
    if decision.open_severity:
        if open_id is not None:
            raise AlertEvaluationError("cannot replace an unresolved episode")
        open_id = episode_id(event["event_id"])
        connection.execute(
            """INSERT INTO alerts
               (alert_id, device_id, run_id, rule_id, source, severity, status, message,
                opening_event_id, last_event_id, opened_event_time, last_event_time)
               VALUES (%s, %s, %s, %s, 'simulator', %s, 'ACTIVE', %s, %s, %s, %s, %s)""",
            (
                open_id,
                event["device_id"],
                event["run_id"],
                RULE_ID,
                decision.open_severity,
                f"Simulator reported {event['device_state']}.",
                event["event_id"],
                event["event_id"],
                event["timestamp"],
                event["timestamp"],
            ),
        )
    elif decision.refresh_existing:
        if open_id is None:
            raise AlertEvaluationError("unhealthy state has no open episode")
        refreshed = connection.execute(
            """UPDATE alerts SET last_event_id = %s, last_event_time = %s,
                   updated_at = clock_timestamp()
               WHERE alert_id = %s AND status IN ('ACTIVE', 'ACKNOWLEDGED')
               RETURNING alert_id""",
            (event["event_id"], event["timestamp"], open_id),
        ).fetchone()
        if refreshed is None:
            raise AlertEvaluationError("open episode invariant failed")
    connection.execute(
        """UPDATE alert_evaluation_state SET last_ingestion_order = %s,
               last_run_id = %s, last_state = %s, open_alert_id = %s
           WHERE device_id = %s AND rule_id = %s""",
        (
            ingestion_order,
            event["run_id"],
            event["device_state"],
            open_id,
            event["device_id"],
            RULE_ID,
        ),
    )


def backfill(connection):
    # Use exactly the live evaluator in the migration's transaction/table lock.
    from device_health_ingestion.validation import validate

    with connection.cursor(name="simulator_alert_bootstrap", row_factory=dict_row) as rows:
        rows.itersize = 500
        rows.execute("""SELECT event_id, run_id, device_id, event_time, payload, ingestion_order
                        FROM telemetry_inbox ORDER BY ingestion_order""")
        for row in rows:
            event = validate(json.dumps(row["payload"]).encode(), row["device_id"].encode())
            if (
                event["event_id"] != str(row["event_id"])
                or event["run_id"] != str(row["run_id"])
                or datetime.fromisoformat(event["timestamp"]) != row["event_time"]
            ):
                raise AlertEvaluationError("inbox evidence does not match stored metadata")
            evaluate(connection, event, row["ingestion_order"])
