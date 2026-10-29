# First recruiter-facing dashboard increment

Status: proposals A–D explicitly approved October 28, 2026. The frontend is
implemented on `feat/dashboard`; verification results are recorded in
[frontend.md](frontend.md).

The owner approved creating `feat/dashboard` from the clean `feat/basic-api`
checkpoint `480bde8`. The owner creates all commits and pushes; documentation changes belong
in a separate focused commit before merge.

## A. Screens, components, and API contracts

Use the approved Next.js, React, TypeScript, and Tailwind CSS stack. Create:

```text
frontend/
  app/
    layout.tsx
    globals.css
    page.tsx                         # fleet overview at /
    loading.tsx
    error.tsx
    not-found.tsx
    devices/[deviceId]/
      page.tsx                       # device investigation
      loading.tsx
      error.tsx
      not-found.tsx
  components/
    fleet-summary.tsx
    device-table.tsx
    device-header.tsx
    telemetry-values.tsx
    telemetry-history.tsx
    telemetry-chart.tsx
    health-badge.tsx
    view-state.tsx
    refresh-button.tsx
  lib/
    api.server.ts                    # FastAPI fetches and error mapping
    api-types.ts                     # types derived from existing responses
    format.ts                        # shared value/UTC formatting
    history.ts                       # chart ordering and lifecycle boundaries
  tests/
    dashboard.spec.ts
    real-api.spec.ts
    history.test.ts                   # accepted-order/lifecycle transformation
    fixtures/api-server.mjs           # isolated tests only
  playwright.config.ts
  package.json
  package-lock.json
  Dockerfile
  ...Next.js/TypeScript/PostCSS configuration and version pins
scripts/demo-dashboard.sh
scripts/test-dashboard.sh
docs/frontend.md
```

| Screen | Existing FastAPI endpoints |
| --- | --- |
| `/` | `GET /api/v1/fleet/summary`, `GET /api/v1/devices` with `after_device` pagination |
| `/devices/[deviceId]` | `GET /api/v1/devices/{device_id}`, `GET /api/v1/devices/{device_id}/telemetry` with `limit` and optional `before` |

Fleet: a Total devices card plus the four health counts, followed by a device
table with device ID, state, firmware, temperature, CPU utilization, error count,
and simulation timestamp. Each row uses a native link covering its surface, a
View details cue, and pointer/keyboard-focus highlighting. Desktop fleet spacing
is content-driven, without a forced viewport-height gap before the footer.
The fleet payload contains only latest readings, so fleet sparklines are omitted;
history remains available on the device page without additional fleet requests.
Follow `next_after_device` until exhausted to display all observed devices, rather
than silently stopping at the first API page. Preserve available device rows if
the separate summary request fails, showing an error in the summary region.

Detail: back-to-fleet navigation; device ID, firmware, lifecycle ID and state;
latest telemetry with units; history charts and a readable history table. Metadata
comes only from existing fields. Optional metrics are shown when supplied; missing
values are displayed as unavailable, never as zero.

Use a restrained, light engineering-dashboard layout, clear typography, status
text plus color, keyboard-accessible links, and responsive grids/tables. Display
the API's simulated-data designation prominently. Health labels come directly
from `device_state`; do not derive online/offline status, risk scores, thresholds,
alerts, or predictions. Simulation timestamps are not wall-clock freshness.

## B. Data access, refresh, and application states

Use Next.js App Router server components for initial reads. The Next.js server
calls only the approved FastAPI endpoints using a server-only `API_BASE_URL`.
The browser requests Next.js pages and interactions; it never connects directly
to PostgreSQL, Redis, or Kafka. This preserves the API's current disabled CORS
configuration without adding proxy endpoints or modifying the backend.

Use native `fetch` with `cache: no-store` and bounded request timeouts. Add an
explicit Refresh action using Next.js navigation refresh. No automatic polling,
WebSockets, background data synchronization, or global state-management library
is proposed. Redis's existing cache expiry remains unchanged.

Use route/panel loading skeletons, zero-device and zero-history empty states,
retryable API/network error states, and a distinct device-not-found view on API
404. Do not fall back to fixture data or present loading/error counts as zero.

History starts with the latest 100 accepted readings. An Older readings link
uses the existing `next_before` cursor via a URL query parameter; a Latest
readings link returns to the current window. The displayed charts and table
cover the selected window, while the device header remains the latest state.

## C. Charting and dependencies requiring approval

Use the approved **Recharts** production dependency for responsive line
charts, tooltips, axes, legends, and keyboard navigation. Keep it inside client
chart components; the page and API client remain server-side.

Charts: temperature (degrees C), power draw (W), CPU/memory utilization together
(percent), and timing jitter (ms). Show error count and other supplied metrics in
the table and latest-value cards. Use linear lines without animation, separate
axes/panels for different units, and a data table as an accessible alternative.

Reverse the API's descending accepted order for display; do not globally sort
by simulation timestamp across lifecycle resets. Use accepted sample order on
the x-axis with simulation timestamps in labels/tooltips. Break lines at each
`run_id` change and at missing values; never connect independent lifecycles or
turn missing readings into zero.

Use the approved **Playwright** development dependency for browser tests.
Use no additional UI kit, chart framework, global store, or data-fetching library.
Pin supported compatible Node/npm, framework, TypeScript, Tailwind, Recharts and
Playwright versions and retain the npm integrity lockfile. Implemented pins:
Node 24.22.1, npm 11.19.1, Next.js 16.4.3, React 19.3.1, TypeScript 6.0.3,
Tailwind CSS 4.3.3, Recharts 3.10.1, and Playwright 1.64.1.

References: [Next.js server/client components](https://nextjs.org/docs/app/getting-started/server-and-client-components),
[Next.js data fetching](https://nextjs.org/docs/app/getting-started/fetching-data),
[Recharts sizing](https://recharts.github.io/en-US/guide/sizes/),
[Recharts accessibility](https://github.com/recharts/recharts/blob/main/storybook/stories/API/Accessibility.mdx),
[Playwright web servers](https://playwright.dev/docs/test-webserver).

## D. Verification, demo, and documentation

Browser tests cover fleet/count rendering, selection/navigation, device metadata
and latest metrics, history charts, loading, empty, unknown-device and API-failure
states, with delayed/error responses from an isolated test-only HTTP fixture
server. These fixture responses follow the existing FastAPI contracts and are
not bundled as runtime fallback data.

Include a separate real-backend browser smoke test: seed through the existing
simulator/Kafka pipeline, open the fleet, select a real device, and verify detail
and telemetry. Run TypeScript checks, lint, a production build, and browser tests;
check normal desktop/laptop layouts and keyboard navigation. Extend Compose,
demo/test scripts and CI without changing Kafka, database, or cache behavior.

Update this design document and `docs/frontend.md` with implemented behavior and
verification results. Update README for the new dashboard setup, demo, and actual
capabilities, and resolve relevant frontend TBDs. Preserve unimplemented alert/ML
status. No ADR is anticipated for this UI increment because it follows the
existing frontend-to-FastAPI boundary; a newly discovered architectural decision
requires review before implementation.

After verification, report changed files, test results, and remaining frontend
TBDs; provide separate implementation and documentation commit commands. Hosting,
public-access/authentication design, alerts, and predictions remain later work.
