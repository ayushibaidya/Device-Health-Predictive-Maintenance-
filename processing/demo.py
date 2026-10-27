import json
import pathlib
import subprocess
import sys

import psycopg

from device_health_ingestion.store import database_dsn

events = [
    json.loads(line)
    for line in pathlib.Path("/fixtures/producer-events.jsonl").read_text().splitlines()
]
if not events:
    raise SystemExit("Producer emitted no events")
subprocess.run([sys.executable, "-m", "device_health_ingestion", "--idle-timeout", "5"], check=True)
with psycopg.connect(database_dsn()) as connection:
    count = connection.execute(
        "SELECT count(*) FROM telemetry_inbox WHERE event_id = ANY(%s::uuid[])",
        ([event["event_id"] for event in events],),
    ).fetchone()[0]
assert count == len(events), f"Expected {len(events)} persisted events, found {count}"
print(f"DEMO PASSED: C++ simulator -> Kafka -> Python validation -> PostgreSQL: {count} events")
