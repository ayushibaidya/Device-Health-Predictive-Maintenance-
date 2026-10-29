# Device-health dashboard

The first recruiter-facing frontend implements the approved
[dashboard design](dashboard-design.md): fleet overview and device investigation,
using real FastAPI data. Alerts, predictions, authentication, and public hosting
are later increments; there are no placeholder alert counts or prediction scores.

## Run the complete demo

Start Docker Desktop, then run from the repository root:

```sh
bash scripts/demo-dashboard.sh
```

The initial build installs pinned frontend dependencies and may take several
minutes. The script runs the existing simulator → Kafka → consumer → PostgreSQL/
Redis → FastAPI demo, then starts the dashboard. Open
[http://localhost:3000](http://localhost:3000), select a device, and inspect its
readings and history. The script prints the actual bound address if configured
through `FRONTEND_PORT` in `.env` or the environment. API docs remain at port 8000.

If your backend is already running, start only the dashboard:

```sh
docker compose up -d --build --wait frontend
```

The frontend starts independently and displays an API error when the backend is
unavailable. To stop the project when finished, preserving saved data:

```sh
docker compose --profile tools down
```

For optional native development, use Node 24.22.1/npm 11.19.1 (the frontend
`.nvmrc` and package engines record the pins). From `frontend/`, run `npm ci`,
then `API_BASE_URL=http://127.0.0.1:8000 npm run dev`. Docker is the supported
single-command demo and does not require changing your global Node installation.

## Screens and data access

`/` renders Total devices and the four backend health counts, plus a device table
including the existing `error_count`. Each row is a native full-surface link with
a View details cue and hover/focus highlighting; keyboard navigation and browser
open-in-new-tab behavior are preserved. Desktop fleet spacing follows content
without forcing the footer down to the viewport edge. The fleet response has one
reading per device, so sparklines are omitted rather than adding per-device
history requests. The view follows `next_after_device` to retrieve all device pages. A
failed summary does not hide successfully loaded device rows; a failed device
page prevents presenting an incomplete fleet as the full list.

`/devices/[deviceId]` displays device ID, firmware, current lifecycle, accepted
reading order, reported health, and latest metrics with units. Its charts and
reading log initially cover the latest 100 accepted readings. Older readings
uses `next_before` in the page URL; Latest readings clears that cursor. The
header remains the latest accepted state when viewing an older history window.

Next.js server components call only these existing FastAPI endpoints:

- `GET /api/v1/fleet/summary`
- `GET /api/v1/devices`
- `GET /api/v1/devices/{device_id}`
- `GET /api/v1/devices/{device_id}/telemetry`

`API_BASE_URL` is server-only; Compose sets it to `http://api:8000`. The browser
does not call infrastructure or FastAPI directly, so the backend CORS policy
stays unchanged. Requests use `cache: no-store`, an eight-second per-request
timeout, and sanitized error views. The Refresh action re-fetches the current page;
there is no automatic polling or global state library. Existing Redis cache
expiry still applies to device detail.

## Chart and state semantics

Recharts renders temperature, power, CPU/memory utilization, and timing jitter.
Display order follows `ingestion_order`, not global timestamp sorting. Lifecycle
changes create gaps; independent simulated runs are never joined. The x-axis is
accepted sample order with simulation-time labels and tooltips, so it does not
imply uniform elapsed time across samples or runs. Error count and supplied
optional metrics remain available as values. Missing values are never zero-filled.

Charts have keyboard navigation, do not animate, and are accompanied by a reading
table. State badges include text as well as color. Loading placeholders, empty
fleet/history states, retryable API failures, and device-not-found views are
implemented. An API 404 is distinguished from an unavailable API. Malformed
payloads or repeated pagination cursors fail safely instead of inventing values
or looping indefinitely. Fixture data is used only by isolated tests and is not
present in the production runtime image.

All views prominently identify simulated data. State names come directly from
the API; the UI derives no health thresholds, online/offline labels, risk scores,
or wall-clock freshness claims from simulation timestamps.

## Verification

```sh
bash scripts/test-dashboard.sh
```

The isolated Docker check runs TypeScript validation, lint, a production build,
four chart-data unit tests, and 18 browser cases using a local test-only API.
It then starts a separate Kafka/PostgreSQL/Redis/FastAPI stack, publishes real C++
events, and runs a fleet → device → history browser smoke test. Only the test
project's containers and volumes are removed. Default isolated ports are 39092,
38000, and 33000; they do not interrupt the usual local demo.

Browser cases cover rendering, all-page fleet traversal, device navigation,
history navigation, loading, empty/error/404 states, refresh, optional metrics,
partial failures, keyboard interactions, and desktop/laptop/narrow layouts.
Fleet refinements also cover whole-row and middle-click navigation, reported
error counts, and content-driven desktop spacing.
GitHub Actions is configured to run the same script. The initial browser target
is Chromium; other engines and large-fleet benchmarks remain future checks.

Local verification on October 28, 2026 passed: TypeScript, lint, production
build, four chart-data unit tests, all 18 fixture browser cases, and the separate
real-pipeline browser test. The one-command dashboard demo also passed. Native
Apple Silicon Chromium and Docker/Linux ARM64 were exercised; remote CI awaits
the owner's push and pull request.

## Pre-merge documentation review and remaining TBDs

README changes are needed because setup, the runnable demo, and visible
capabilities changed. The dashboard design and architecture references document
the resolved routing, API access, refresh, charting and pagination choices. No ADR
is required: this follows the approved frontend-to-FastAPI boundary. Keep these
documentation updates in a separate commit from code/configuration/tests.

Remaining frontend work: broader browser coverage and fleet-size measurements;
additional history-filter controls if approved; alert/prediction screens once
their backend contracts exist; and public deployment/access design. These are
not implemented by this increment. Existing backend contracts are unchanged.
