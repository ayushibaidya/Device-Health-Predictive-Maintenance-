# Kafka ingestion

Approved October 27, 2026: C++ simulator -> Kafka -> Python validation -> a narrow
PostgreSQL inbox. The inbox was explicitly brought forward for durable
idempotency. The subsequent approved [data-access increment](persistence.md)
reuses this inbox for indexed history/latest queries and adds Redis as a
recoverable cache; the full historical schema remains deferred.

## Run the demo

With Docker running, from the repository root:

```sh
bash scripts/demo-kafka.sh
```

This builds pinned containers, publishes nine real C++ events, processes the
queue, and verifies those IDs were persisted. Success prints `DEMO PASSED`.
Repeating the demo generates new identities and safely processes any backlog.
Inspect the stored evidence and stop the services:

```sh
docker compose exec postgres psql -U device_health -d device_health -c \
  "SELECT device_id, event_time, payload->>'device_state' AS state FROM telemetry_inbox ORDER BY persisted_at DESC LIMIT 12;"
docker compose down
```

`down` preserves named data volumes. Local Kafka binds to `localhost:19092`;
PostgreSQL stays inside the Compose network. `.env.example` contains public
local-demo defaults only. Keep real credentials in untracked configuration.

## Event and delivery contract

- Producer: C++ with librdkafka 2.15.1. Consumer: Python.
- Telemetry: `device.telemetry.v1`. DLQ: `device.telemetry.dlq.v1`.
- Message key: UTF-8 `device_id`; ordering is per device, not global.
- Kafka events add nonzero canonical UUID `event_id` and `run_id` fields. Every
  sample gets a new UUID v4. Each device retains its lifecycle ID until reset;
  resetting one device changes only its own run ID.
- Record IDs stay unchanged during retries and replay. The legacy repeatable
  stdout simulator demo still emits ten-field samples; Kafka mode attaches the
  required identities before those samples enter the ingestion pipeline.
- Delivery is at least once. Producer idempotence does not establish end-to-end
  exactly-once delivery. Database uniqueness makes redelivery safe.

The local KRaft broker has one node, three partitions per topic, replication
factor one, and 24-hour retention. This is a local demo configuration; hosted
deployment configuration is a later release task.

## Durable processing boundary

[001_telemetry_inbox.sql](../processing/migrations/001_telemetry_inbox.sql) creates
only `telemetry_inbox`: unique event ID, lifecycle/device IDs, event time,
validated JSON, Kafka source coordinates, and persistence time.

The consumer disables auto-commit and auto-offset-store. It validates an event,
commits its PostgreSQL insert, attempts an optional derived-state cache refresh,
then synchronously commits the Kafka offset. Redis failure does not block that
offset commit. An
identical duplicate is identified in PostgreSQL and acknowledged without a new
row. A conflicting payload reusing an ID goes to the DLQ without overwriting the
original row. A crash between database and Kafka commits causes safe redelivery.

Invalid events require a broker-acknowledged DLQ send before their source offset
is committed. DLQ envelopes include source coordinates, a failure reason, and
base64 input. Large input is explicitly marked truncated with its original size
and SHA-256; source coordinates identify the original during Kafka retention.
Transient database or DLQ failures retry with bounded backoff, then exit without
committing the affected offset. Unexpected processing errors also remain
uncommitted.

Producer delivery reports and flush results are checked. Failed/unconfirmed
sends report event IDs and exit nonzero. Kafka mode writes complete records to
stdout before enqueueing, allowing captured events to be replayed unchanged.
This is not a crash-durable producer outbox; retain captured records for replay
after producer process interruption.

The demo captures `build/kafka-integration/producer-events.jsonl`. Replay with:

```sh
docker compose run --rm --no-deps tests python -m device_health_ingestion.replay \
  /fixtures/producer-events.jsonl
docker compose run --rm consumer --idle-timeout 5
```

## Tests and native build

```sh
bash scripts/test-kafka.sh

# Native Mac build, using installed librdkafka 2.15.1:
cmake --preset kafka
cmake --build --preset kafka --parallel 4
ctest --preset kafka --parallel 4
```

The test script uses its own temporary Compose project and removes only that
project's services/volumes on exit. It runs C++ tests during the producer image
build, Python static/unit checks, real Kafka/PostgreSQL integration tests, and a
real broker pause/resume test while the producer is sending. Set `KAFKA_PORT`
to an unused port if its default test port 29092 is occupied. GitHub Actions runs
the same script.

Integration tests cover consumer process restart, replay deduplication, reset
identity, per-device ordering, the database-before-offset crash window, DLQ
delivery, database failure/recovery, and conflicting identity protection.

## Pinned tools

- C++20, CMake 4.4.3, librdkafka 2.15.1; Apple Clang locally, GCC 16.2 in Docker.
- Python 3.13.18, confluent-kafka 2.15.1, psycopg/psycopg-binary 3.3.6.
- Tests: pytest 9.1.1 and Ruff 0.17.3.
- Kafka 4.3.1 and PostgreSQL 18.6, with explicit image tags and digests.
- Runtime/dev lockfiles pin transitive versions and wheel hashes. Regenerate them
  with `scripts/lock-ingestion.py` inside the pinned Python container.
- Tool baseline: Docker Engine 27+ and Compose 2.24+. Locally tested with Docker
  29.2.1 and Compose 5.0.2.

Reference behavior: [librdkafka](https://github.com/confluentinc/librdkafka/blob/v2.15.1/INTRODUCTION.md),
[Kafka Docker](https://kafka.apache.org/43/getting-started/docker/), and
[PostgreSQL transactions](https://www.psycopg.org/psycopg3/docs/basic/transactions.html).

## Verification recorded October 27, 2026

| Check | Observed result |
| --- | --- |
| Native Apple Clang 21 / Kafka build | 39 CTest checks passed |
| Linux GCC 16.2 producer container | 39 CTest checks passed |
| Python 3.13.18 unit checks | 59 passed |
| Real Kafka/PostgreSQL integration | 5 passed |
| Broker pause/resume during publication | All three queued records acknowledged |
| Documented demo command | Nine newly published IDs verified in PostgreSQL; `DEMO PASSED` |

The checks include startup/drain regressions for unassigned and empty Kafka
partitions. Static Python checks, shell syntax, YAML parsing, and Git whitespace
checks also passed. The GitHub workflow is prepared; these results are local,
including real service containers. They are not throughput benchmarks or a claim
that the public hosted product is complete.
