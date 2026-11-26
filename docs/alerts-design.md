# Simulator-state alerts

Status: proposals A–F approved October 29, 2026; implemented on `feat/alerts`.
Branch: `feat/alerts`, based on the pushed dashboard checkpoint `159472f`.
The dashboard has not merged into main; preserve that dependency when preparing
pull requests. See [alerts.md](alerts.md) for rollout, demo and verification.

## A. Alert rules

Use a logically separate simulator-alert evaluator in the existing Python
consumer process, as permitted by ADR-005. Rule ID: `simulator_state_v1`;
source: `simulator`. Read only the validated simulator `device_state`:

| Reported device state | Alert severity |
| --- | --- |
| HEALTHY | No new alert; resolve any open episode |
| WARNING | WARNING |
| CRITICAL | CRITICAL |
| FAILED | FAILURE (simulator-confirmed) |

Evaluate accepted ingestion order, not wall-clock age or global simulation-time
sorting. A first observed unhealthy reading creates an alert even if no preceding
healthy sample exists. No new numeric thresholds, cooldown, debounce, ML policy,
notification integration, or simulator state changes are introduced.

## B. Lifecycle and acknowledgement

An episode has immutable severity and belongs to one device, lifecycle, and rule.
At most one episode per `(device_id, rule_id)` is unresolved, including both
ACTIVE and ACKNOWLEDGED statuses.

| Input/action | Result |
| --- | --- |
| First unhealthy state | Create ACTIVE episode |
| Same unhealthy state and lifecycle | Update last-event evidence; keep the same alert ID and acknowledgement |
| Different unhealthy severity | Resolve the old episode as `superseded`; create a new ACTIVE episode requiring fresh acknowledgement |
| HEALTHY | Resolve the open episode as `recovered` |
| Different run_id | Resolve any old episode as `lifecycle_changed`; create a new ACTIVE episode only if the new reading is unhealthy |
| Acknowledge ACTIVE | Set ACKNOWLEDGED and record the first acknowledgement time |
| Acknowledge ACKNOWLEDGED | Return current resource, preserving the first acknowledgement time |
| Acknowledge RESOLVED | Return 409 `alert_resolved`; do not reopen it |

ACTIVE may resolve without first being acknowledged. RESOLVED is terminal;
recurrence creates a new alert. Both severity increases and decreases produce
new episodes. A run change takes precedence over recovery or severity changes,
so a reset to HEALTHY closes the old episode as `lifecycle_changed`.
The stored `run_id` remains the opening lifecycle. Resolution updates both
last-event and resolved-event evidence to the closing event. For a lifecycle
change, that event can belong to the new run; it is boundary evidence, not a
reading from the opening run. Accepted order governs the transition even if the
new run restarts its simulation clock.
When severity changes, the UI explicitly distinguishes
"superseded" from recovery: closing a warning does not imply that the device is
healthy when a critical/failure episode replaces it.

Acknowledgement means reviewed for investigation; it never changes device
health, clears a condition, or marks it recovered. This local increment records
the acknowledgement timestamp, with no invented user identity. Authenticated
actors/public demo write policy require a separate decision before hosting.

## C. Transaction, concurrency, idempotency, and recovery

Persist telemetry and evaluate the simulator rule within the **same PostgreSQL
transaction**, before committing the Kafka offset:

1. Ensure and lock the device/rule evaluation-state row with `SELECT FOR UPDATE`.
   Acquire this lock before the inbox insert so concurrent same-device writers
   receive accepted orders in their serialized evaluation order.
2. Insert the inbox event using the existing event_id uniqueness contract.
3. For a newly inserted event, apply the episode transition and advance the
   durable evaluation cursor. For an identical duplicate, perform no alert or
   cursor update; preserve the existing payload-conflict/DLQ behavior.
4. Commit inbox, alerts, and evaluation state together.
5. Attempt the existing best-effort Redis latest-state update and commit the
   Kafka offset under the current processing contract.

A deterministic UUID v5 derived from the fixed application namespace,
`rule_id`, and opening event_id identifies each episode. Database uniqueness on
`(rule_id, opening_event_id)` adds an independent duplicate guard. Repeated bad
readings update evidence rather than creating an alert per reading. A crash after
PostgreSQL commit but before Kafka offset commit safely redelivers the event.

PostgreSQL row locks serialize same-device evaluation; different devices remain
independent. Acknowledgement locks only its alert row. The evaluator locks the
device/rule row before the alert row; acknowledgement never locks the cursor.
If resolution wins the race, acknowledgement returns 409. If acknowledgement
wins, later resolution preserves its acknowledgement timestamp. Concurrent
acknowledgements preserve one first timestamp and return current state.

Transient database/lock/deadlock failures roll back and use the current bounded
consumer retry policy. Unexpected evaluator/schema failures roll back and stop
processing without committing the offset or misrouting a valid event to the DLQ.
Invalid telemetry continues through the acknowledged DLQ path with no alerts.
Redis remains optional for ingestion and does not own alert state.

This deliberately couples ingestion success to durable alert evaluation. It
avoids introducing a second consumer, outbox, or additional Kafka topic in this
increment. Kafka topics, payloads, keys, delivery settings and simulator behavior
remain unchanged. Additional transactional work requires performance measurement
later; existing throughput figures remain targets.

## D. Schema, migration, and existing data

Add `003_simulator_alerts.sql`; leave applied migrations 001 and 002 unchanged.

`alerts` stores:

- `alert_id uuid` primary key; `alert_order bigint` unique generated sequence
  for stable creation-order pagination.
- `device_id text`, `run_id uuid`, `rule_id text`, `source text`.
- `severity` constrained to WARNING/CRITICAL/FAILURE; `status` constrained to
  ACTIVE/ACKNOWLEDGED/RESOLVED; a human-readable simulator-state `message`.
- `opening_event_id`, `last_event_id`, nullable `resolved_event_id`, referencing
  the immutable inbox with deletion restricted to preserve alert evidence.
- `opened_event_time`, `last_event_time`, nullable `resolved_event_time`: the
  corresponding **simulation** timestamps.
- `created_at`, `updated_at`, nullable `acknowledged_at`, nullable `resolved_at`:
  PostgreSQL **wall-clock** operational timestamps.
- Nullable `resolution_reason`: `recovered`, `superseded`, or `lifecycle_changed`.

Use status/nullable-field consistency checks, a unique `(rule_id, opening_event_id)`
constraint, and a partial unique `(device_id, rule_id)` index for unresolved rows.
Add device/order and status/order indexes for bounded alert queries. There is no
new devices registry, historical-telemetry schema, or Redis alert cache.

`alert_evaluation_state` stores `(device_id, rule_id)` as its primary key, the
last accepted ingestion order/run/state, and nullable open alert ID. This is
durable rule progress, not the source of device health. The simulator still owns
health; PostgreSQL owns alert lifecycle and acknowledgement.

Bootstrap existing inbox history in accepted order using the same evaluator as
live ingestion. Add a narrowly registered Python backfill hook for migration
003 to the current migration runner, inside its existing transaction and before
recording migration completion. Stream rows in bounded batches. Do not re-create
alerts on ordinary restarts or regenerate acknowledgement state.

Rollout: pause old consumer processes, run the migration/backfill, deploy the new
consumer/API together, then resume the existing consumer group. The backfill
holds a SHARE ROW EXCLUSIVE inbox lock, blocking inserts while permitting normal
reads. A bounded lock-acquisition timeout fails the migration safely if necessary.
Schema, backfill and migration bookkeeping commit together; failure rolls all
three back. Invalid stored data fails the migration for investigation rather
than being silently skipped. No data deletion or Kafka offset reset occurs.

Readiness requires migration 003 and readable alert tables. The existing health
response shape is unchanged. The migration's brief ingestion pause and historical
backfill are material parts of this proposal, not routine implementation assumptions.

## E. API contracts

Add routes under the existing `/api/v1` prefix; preserve existing response shapes:

| Method and path | Result |
| --- | --- |
| GET /alerts | Bounded alert list, including history |
| GET /alerts/{alert_id} | One alert or 404 |
| GET /devices/{device_id}/alerts | Device-scoped alert list; unknown device is 404 |
| POST /alerts/{alert_id}/acknowledge | Acknowledge; 200 current alert, 404 unknown, 409 resolved |

List query parameters: optional `device_id` (global route), repeated `status`
(ACTIVE/ACKNOWLEDGED/RESOLVED), optional `severity`, `limit` default 100/max 1,000,
and positive `before` cursor. Omitted status means all statuses. Results are
descending `alert_order`, with live-view pagination rather than a frozen snapshot.

List envelope: `{data_mode: "simulated", items: [Alert], next_before: number|null}`.
Detail/ack envelope: `{data_mode: "simulated", ...Alert}`. `Alert` exposes all
fields listed for the alerts table above. UUIDs are strings; times are ISO 8601
UTC; nullable fields are explicit null. No actor field or ML/risk fields exist.
Acknowledgement requires no request body and changes only operational status/time.

Errors retain `{error: {code, message}}`: 422 invalid parameters, 503 unavailable
storage, and sanitized 500 for unexpected faults. Add only 409 `alert_resolved`;
unknown alert/device returns the existing 404 `not_found`. Repeated successful
acknowledgement does not advance its timestamp or invent a new mutation. A lost
response can safely be retried; no automatic unbounded retry is introduced.

Keep localhost-only deployment and existing disabled CORS. Login/public access
is deferred as stated above. The frontend submits acknowledgement through a
Next.js Server Action to FastAPI; it never writes to PostgreSQL or Redis directly.
Retain Next.js same-origin action checks and refresh affected views after success
or a resolved-alert conflict. Show sanitized failure feedback and retry controls.

## F. UI, verification, and documentation

Add an Alerts navigation link and `/alerts` page with Open/Resolved/All views,
optional device/severity filters, status/severity badges, simulation event time,
clearly labelled wall-clock acknowledgement time, and acknowledgement actions.
Open explicitly queries ACTIVE plus ACKNOWLEDGED; acknowledgement does not make
an open condition disappear. Resolved rows show their resolution reason.

Add a compact recent-open-alerts panel to the fleet and an alert section to device
detail. Each panel shows up to five newest open episodes; links open the complete
Alerts list, with the device filter preserved and an All view for device history.
Do not label a bounded recent list as a global count. Keep existing fleet summary
fields/health cards unchanged. Preserve
loading, empty, unavailable and conflict states. Acknowledgement buttons show a
pending state and are offered only for ACTIVE alerts. Manual refresh remains the
data-update model; no polling, new state framework, or new dependency is proposed.

Tests: pure rule/lifecycle unit tests; real PostgreSQL constraints, rollback,
historical backfill, duplicate replay/restart, and concurrent acknowledgement/
resolution tests; API contracts/error/readiness tests; browser display/filter/
acknowledgement/loading/error tests; full real-pipeline alert → acknowledge demo.
Run the complete relevant backend and frontend suites, including existing tests.

The November 23, 2026 isolated baseline verification passed both scripts; results
are recorded in [alerts.md](alerts.md#verification-and-remaining-decisions).
Following owner approval, the
[partial-index test correction](testing-strategy.md#alert-constraint-coverage-correction)
was verified locally on November 23, 2026: distinct valid opening evidence now
isolates `alerts_one_open_episode_idx` for both ACTIVE and ACKNOWLEDGED first
episodes, with the actual constraint name asserted. Invalid-status checks and
separate opening-evidence uniqueness coverage remain. The focused 11-test alert
integration module and full backend suite (119 unit/30 integration tests, Ruff
and broker recovery) passed. No production or migration changes were needed.

`scripts/demo-alerts.sh` uses the existing C++ 100-simulated-minute scenario to
exercise WARNING, CRITICAL, FAILED and recovery. It verifies persisted alert
history and repeat-safe acknowledgement, then starts the dashboard for manual
inspection. Automated browser verification is provided by
`scripts/test-dashboard.sh`. This is real simulator data, not a production mock
or a change to Kafka behavior.

Document the approved contract, migration/rollout, verified results, and remaining
TBDs. Update README because the demo and capabilities change. Add an ADR for the
meaningful atomic-ingestion/alert decision and historical-bootstrap approach;
routine alert UI choices stay in the component guide. Before any further
implementation or test-code changes, follow the
[documentation-first SDLC approval gate](development-standards.md#documentation-first-sdlc).
Prepare the focused backend-with-tests, dashboard-with-tests, end-to-end
automation, and separate documentation checkpoints described in
[alerts.md](alerts.md#owner-commit-checkpoint) for the owner to run. Do not merge
or push automatically. Cross-check code, tests, schema and documentation against
A–F and the constraint-correction verification before merge. ADR-007's
approved transaction, locking, idempotency and bootstrap decisions remain intact.

References: [existing ADR-005](adr/ADR-005-separate-alert-evaluation-from-ml.md),
[PostgreSQL locking](https://www.postgresql.org/docs/18/explicit-locking.html),
[partial uniqueness](https://www.postgresql.org/docs/18/indexes-partial.html),
[Next.js Server Action security](https://nextjs.org/docs/app/guides/data-security).
