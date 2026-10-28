import os

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Jsonb

from .errors import PermanentProcessingError, TransientProcessingError


def database_dsn():
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    if not all(os.getenv(name) for name in ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD")):
        raise ValueError("Configure DATABASE_URL or PGHOST/PGDATABASE/PGUSER/PGPASSWORD")
    return make_conninfo(
        host=os.environ["PGHOST"],
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        port=os.getenv("PGPORT", "5432"),
    )


class PostgresConnection:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.connection = None

    def _connect(self):
        if self.connection is None or self.connection.closed:
            self.connection = psycopg.connect(
                self.dsn,
                autocommit=True,
                connect_timeout=5,
                options=conninfo_to_dict(self.dsn).get("options", "")
                + " -c statement_timeout=5000 -c lock_timeout=5000",
            )
        return self.connection

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None


class PostgresInbox(PostgresConnection):
    def persist(self, event, record):
        try:
            connection = self._connect()
            with connection.transaction():
                inserted = connection.execute(
                    """INSERT INTO telemetry_inbox
                       (event_id, run_id, device_id, event_time, payload,
                        source_topic, source_partition, source_offset)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (event_id) DO NOTHING RETURNING event_id""",
                    (
                        event["event_id"],
                        event["run_id"],
                        event["device_id"],
                        event["timestamp"],
                        Jsonb(event),
                        record.topic,
                        record.partition,
                        record.offset,
                    ),
                ).fetchone()
                if inserted is None:
                    previous = connection.execute(
                        "SELECT payload FROM telemetry_inbox WHERE event_id = %s",
                        (event["event_id"],),
                    ).fetchone()
                    if previous is None or previous[0] != event:
                        raise PermanentProcessingError(
                            "event_id conflicts with an existing payload"
                        )
            return inserted is not None
        except (
            psycopg.OperationalError,
            psycopg.InterfaceError,
            psycopg.errors.SerializationFailure,
            psycopg.errors.DeadlockDetected,
        ) as error:
            self.close()
            raise TransientProcessingError("database temporarily unavailable") from error
