"""Apply reviewed SQL migrations to fresh or existing local databases."""

import pathlib
import sys

import psycopg

from .store import database_dsn


def migrate(dsn, directory=None):
    directory = directory or pathlib.Path(__file__).resolve().parents[1] / "migrations"
    with psycopg.connect(dsn, connect_timeout=5) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(841927302)")
        connection.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
            name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())""")
        applied = []
        for path in sorted(directory.glob("*.sql")):
            if connection.execute(
                "SELECT 1 FROM schema_migrations WHERE name = %s", (path.name,)
            ).fetchone():
                continue
            connection.execute(path.read_text())
            connection.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
            applied.append(path.name)
    return applied


def main():
    try:
        applied = migrate(database_dsn())
        print("Migrations applied: " + (", ".join(applied) or "already up to date"))
        return 0
    except Exception as error:
        print(f"Migration failed: {type(error).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
