# Basic API

The approved [API design](basic-api-design.md) exposes the existing simulated
telemetry through FastAPI. It reuses the inbox, accepted-event order, history
filters, and Redis fallback without changing the ingestion event or SQL schema.

## Run and try requests

With Docker running, from the repository root:

```sh
bash scripts/demo-api.sh
```

The script builds the pinned services, applies migrations, runs the C++ simulator
through Kafka/validation/PostgreSQL/Redis, and verifies the HTTP responses against
those real simulator events. Success ends with `API DEMO PASSED`. Open
[interactive API docs](http://localhost:8000/docs) to try requests in a browser.
Set `API_PORT` in the environment or local `.env` if port 8000 is occupied.

```sh
curl http://localhost:8000/api/v1/fleet/summary
curl 'http://localhost:8000/api/v1/devices?limit=2'
curl http://localhost:8000/api/v1/devices/device-002
curl 'http://localhost:8000/api/v1/devices/device-002/telemetry?limit=2'
curl http://localhost:8000/health/ready
docker compose down
```

`down` keeps the database volumes. To start only the API against existing data:

```sh
docker compose up -d --build --wait api
```

Redis may be started separately with `docker compose up -d redis`; it is optional
for API reads. The API needs PostgreSQL/migrations and has no Kafka dependency.
The full demo starts Redis and Kafka for the simulator/ingestion workflow.

## HTTP contract

Routes are listed in `/docs` and machine-readable `/openapi.json`. Fleet summary
returns `data_mode`, `total_devices`, and `by_state` with all four device states.
Each device has one latest accepted reading; counts use a single PostgreSQL query.
Detail returns `{data_mode, ingestion_order, event}`. Event fields retain their
ingestion names and original simulation timestamp; absent optional metrics remain
absent, while explicit null values are preserved. All business responses use
`data_mode: simulated`. There is no new device registry or fabricated alert/ML data.

Device listing returns `{data_mode, items, next_after_device}` in device-ID order.
Pass `next_after_device` back as `after_device` to continue. History returns
`{data_mode, items, next_before}` in descending accepted order, with `before` as
its continuation cursor. Both default to 100 results and cap `limit` at 1,000.
History additionally accepts `run_id`, inclusive timezone-aware ISO 8601 `start`
and `end`. Unknown devices return 404; an existing device whose filters match no
readings returns an empty page. Pagination is a live view, not a frozen snapshot.

Errors use `{error: {code, message}}`: 404 `not_found`, 422 `invalid_request`,
503 `service_unavailable` when a required database operation is unavailable,
and sanitized 500 `internal_error` for unexpected faults. Unsupported methods
return 405 `method_not_allowed`. Connection strings, raw inputs, and driver
exception messages are not returned; unexpected faults log only their type.

`/health/live` returns 200 independently of stores. `/health/ready` requires a
readable migrated inbox; otherwise it returns 503. A healthy readiness response
contains `status: ready`, `database: up`, and `cache: up|degraded|disabled`. Redis
failure degrades cache status but permits PostgreSQL-backed reads. Each request
owns and closes its database connection; Redis uses an application-scoped pool.
Cached detail reads retain the existing default 30-second expiry and may succeed
while PostgreSQL is unavailable. Readiness still reports that storage outage.
Simulation time is not wall-clock device freshness.

## Tests and scope

```sh
bash scripts/test-kafka.sh
```

The isolated pipeline suite includes API response/validation/error tests,
real HTTP reads of C++ simulator events, history/device pagination, lifecycle
counts, migrations/readiness, real database/Redis connection failures, and
concurrent request isolation. Local verification passed 90 Python unit tests,
18 integration tests, and the full API demo. GitHub Actions is configured to run
the same automated suite on pull requests and main pushes.

This is read-only local development access on `127.0.0.1`; login/public-access
design is deferred until deployment. CORS is disabled until a frontend origin
is selected. The next feature is the Next.js/React/TypeScript/Tailwind dashboard,
with alert processing and ML added in their own reviewed increments. The user
creates the commit and push after reviewing the finished changes.
