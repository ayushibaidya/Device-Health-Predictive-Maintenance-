# App-ready data access

Approved scope: reuse the durable inbox for telemetry history and latest device
state, add a recoverable Redis cache, and provide tests and a runnable demo.
No API, frontend, alerts, ML, or broader historical schema is added here.

## Demo and inspection

With Docker running, from the repository root:

```sh
bash scripts/demo-data.sh
```

This applies migrations without deleting existing data, publishes nine C++
readings through Kafka (including a device reset), validates/persists them,
shows lifecycle-filtered history and current device state, and demonstrates
cache recovery and rebuild. Success ends with `DATA ACCESS DEMO PASSED`.
Services stay running; `docker compose down` stops them and keeps PostgreSQL data.

Read the same data through the reusable Python query layer and CLI:

```sh
docker compose run --rm --no-deps -T tests python -m device_health_ingestion.data_access latest device-002
docker compose run --rm --no-deps -T tests python -m device_health_ingestion.data_access history device-002 --limit 10
docker compose run --rm --no-deps -T tests python -m device_health_ingestion.data_access history device-002 --start 2026-01-01T00:00:00Z --end 2026-01-01T01:00:00Z
docker compose run --rm --no-deps -T tests python -m device_health_ingestion.data_access rebuild-cache
```

History supports `--run-id UUID`, inclusive timezone-aware `--start`/`--end`,
`--limit` (default 100, maximum 1,000), and `--before` using the previous page's
`next_before`. Results are newest accepted reading first. Each item contains
`ingestion_order` and the original validated `event`. An unknown device has
empty history and `null` latest state. A database error is reported as an error,
never as an empty or healthy device.

## Durable ordering and migrations

[002_data_access.sql](../processing/migrations/002_data_access.sql) adds a unique
monotonic `ingestion_order` and indexes for device/order, device/time, and
device/lifecycle/time queries to the existing inbox. No event contract changes.
An identical replay keeps its original row and order; sequence gaps are normal.
Per-device Kafka order determines new accepted readings. A new lifecycle can
restart its simulation clock, so latest state uses accepted order rather than
the greatest simulation timestamp. A newly accepted late reading is current by
this rule; this is not a separate event-time reordering system.

The migration runner records applied filenames under a transaction/advisory
lock. It also upgrades volumes created by the earlier ingestion demo, preserving
rows and reconstructing their per-device order from original Kafka coordinates.
Do not edit applied migrations; add another migration for future changes.
To apply migrations separately:

```sh
docker compose build migrate
docker compose run --rm -T migrate
```

## Cache contract and recovery

PostgreSQL remains authoritative. [Redis 8.10.3](https://github.com/redis/redis/releases/tag/8.10.3)
is pinned by image digest; [redis-py 8.1.0](https://pypi.org/project/redis/8.1.0/)
is pinned with wheel hashes. Redis has no host port or persistent
volume: it is disposable derived data. Each device has a hash under
`device-health:latest:v1:<SHA256(device_id)>` containing the accepted order and
validated event. A single atomic Lua operation accepts only equal or newer
orders, preventing a delayed refresh/rebuild from replacing newer state.

After PostgreSQL accepts an event or identifies a duplicate, the consumer reads
the durable latest row and attempts a cache refresh before committing its Kafka
offset. Redis failures use short connection/read timeouts and no SDK retries;
they produce `latest_cache: degraded` in the processing log and do not block
durable ingestion. Invalid events still require acknowledged DLQ delivery.

Reads use Redis when present and valid, otherwise PostgreSQL, followed by a
best-effort cache fill. Empty/lost/malformed entries recover automatically.
Explicit rebuild walks the durable latest readings in bounded device pages and
uses the same atomic ordering guard; it does not flush Redis or history.
An interrupted rebuild can safely be repeated. Concurrent devices created behind
the rebuild cursor are picked up by normal ingestion or a later rebuild/read.

`LATEST_CACHE_TTL_SECONDS` defaults to 30 (supported 1–3,600). This bounds stale
cached readings after a missed refresh: a read may return the earlier accepted
state until expiry. Successful ingestion normally refreshes immediately. Redis
failure itself falls back to PostgreSQL. Freshness warnings in the future UI
must be based on the telemetry timestamp/run, not cache presence. Omit
`REDIS_URL` outside Compose to use PostgreSQL-only operation.

## Verification and next increment

```sh
bash scripts/test-kafka.sh
```

The isolated suite checks existing ingestion guarantees plus history filters,
pagination, duplicate/lifecycle behavior, migration of populated inboxes,
empty/corrupt-cache fallback, rebuild, stale-writer rejection (including bigint
precision), expiry, and offset commits during a real Redis connection failure.
It uses real Kafka, PostgreSQL, and Redis, cleans up only its own project/volumes,
and runs in GitHub Actions. Performance targets remain unmeasured.

The subsequent `feat/basic-api` increment exposes fleet summary, device detail,
and history through FastAPI; see [basic-api.md](basic-api.md). Alert processing
and the dashboard remain upcoming increments.
