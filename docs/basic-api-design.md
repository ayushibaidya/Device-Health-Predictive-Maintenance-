# Basic API increment

Status: proposals A–C explicitly approved October 28, 2026; implemented and locally
verified with 90 Python unit tests, 18 integration tests, and the full HTTP demo.
Branch: `feat/basic-api`, based on the pushed persistence checkpoint. Merge order
remains Kafka ingestion, persistence, then basic API. The user runs all commit
and push commands; this increment must stay uncommitted until they do so.

## Purpose and frontend boundary

FastAPI exposes the saved telemetry to the future website. The frontend is a
separate increment using Next.js, React, TypeScript, and Tailwind CSS. This API
increment provides interactive request documentation in the browser at `/docs`.

## Proposal A: first API surface

| Method and route | Result |
| --- | --- |
| `GET /api/v1/fleet/summary` | Total observed devices and latest-state HEALTHY/WARNING/CRITICAL/FAILED counts |
| `GET /api/v1/devices` | Bounded page of devices and their latest readings |
| `GET /api/v1/devices/{device_id}` | Latest reading, including firmware, lifecycle, state, and metrics |
| `GET /api/v1/devices/{device_id}/telemetry` | Bounded history filtered by lifecycle and inclusive start/end times |
| `GET /health/live` | Whether the API process can respond |
| `GET /health/ready` | Whether PostgreSQL and the required inbox migration are available; Redis status reported separately |

Business responses identify the data as `data_mode: simulated`. Device readings
retain the existing `{ingestion_order, event}` shape. Fleet counts use the newest
accepted reading per device from PostgreSQL in one query. A device is observed
only once telemetry exists; there is no new device registry in this increment.

Device pages use alphabetical `device_id` order, `limit` default 100/max 1,000,
and an `after_device` cursor returned as `next_after_device`. History reuses the
existing accepted-order pagination: `run_id`, timezone-aware `start`/`end`,
`limit` default 100/max 1,000, and `before`/`next_before`.

Alert creation/acknowledgement and prediction endpoints arrive with their actual
processing increments. This API does not manufacture alert counts or predictions.

## Proposal B: reads, errors, and local access

- Reuse the current PostgreSQL queries, migration runner, and Redis fallback.
  No ORM, replacement migration framework, or broader historical schema is added.
- Fleet listing/summary read PostgreSQL. Device detail uses Redis with PostgreSQL
  fallback and the approved 30-second default cache TTL. Responses expose the
  original simulation timestamp and accepted order; request time is never used
  to imply fresh device telemetry or real-world device liveness.
- Use typed Pydantic response models and bounded, validated query parameters.
  Return 404 for unknown devices, 422 for invalid inputs, 503 for unavailable
  durable storage, and a sanitized 500 for unexpected errors. Errors use
  `{error: {code, message}}`; never expose connection strings or driver messages.
  An existing device with no readings matching history filters returns an empty page.
- Readiness is 503 when PostgreSQL/the required migration is unavailable. Redis
  failure reports degraded cache status with readiness 200 because reads fall back
  to PostgreSQL. Liveness is independent of either data store.
- This increment serves read-only local development access, bound to
  `127.0.0.1:8000` on the host, without login. Public access/authentication is a
  separate deployment decision before hosting. Leave CORS disabled until the
  frontend origin is known; no wildcard origins or write endpoints are added.
- Reuse synchronous psycopg calls with synchronous FastAPI handlers. Each request
  owns and closes its database connection; concurrent requests must not share a
  mutable connection. Redis uses its client connection pool and application cleanup.

## Proposal C: reproducible implementation and verification

Keep Python 3.13.18 and the existing consumer/data-store dependency pins. Add
FastAPI 0.162.0, Pydantic 2.14.1, Uvicorn 0.54.0, and test-only HTTPX 0.28.1,
verified against the official PyPI metadata. Resolve compatibility and pin all
transitive dependencies with hashes before building. References:
[FastAPI](https://pypi.org/project/fastapi/0.162.0/),
[Pydantic](https://pypi.org/project/pydantic/2.14.1/),
[Uvicorn](https://pypi.org/project/uvicorn/0.54.0/),
[HTTPX](https://pypi.org/project/httpx/0.28.1/).

Add a `device_health_api` package beside ingestion, an API service using the same
pinned Python build, and a one-command demo that runs the existing simulator/data
pipeline before querying the HTTP endpoints. Health checks and `/docs` make the
service inspectable without a frontend.

Tests cover response contracts, filtering/pagination, invalid/unknown requests,
error sanitization, concurrent request isolation, database failure, Redis fallback,
and health semantics. Real-service tests exercise HTTP over persisted simulator
data. Retain the ingestion/replay tests and update GitHub Actions. Document the
demo and give the user the exact commit/push commands after checks pass.

FastAPI references: [synchronous handlers](https://fastapi.tiangolo.com/async/)
and [testing with HTTPX](https://fastapi.tiangolo.com/tutorial/testing/).
