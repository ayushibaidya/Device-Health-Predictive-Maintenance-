# Simulator-state alerts

Implements the approved [A–F design](alerts-design.md) and
[ADR-007](adr/ADR-007-atomic-simulator-alerts.md). These are deterministic
simulator-state episodes, not predictions or numeric threshold alerts.

## Run the real demo

With Docker running, from the repository root:

```sh
bash scripts/demo-alerts.sh
```

The script builds the consumer/API/dashboard, stops any Compose-managed consumer,
applies migrations, and publishes the existing 100-simulation-minute C++ scenario
through Kafka. Python validates and persists 3,603 events with alert evaluation.
The verifier checks all three alert severities, severity replacement, recovery,
repeat-safe acknowledgement, and resolved-acknowledgement rejection. It leaves
the services available at [the dashboard](http://localhost:3000/alerts) and
[API docs](http://localhost:8000/docs) by default. The script prints the configured
frontend address; `API_PORT` selects the API host port (default 8000).

Try Open to see the acknowledged device-002 failure, All/Resolved to inspect
severity changes and device-003 recovery, and a device link to inspect telemetry.
The script deliberately acknowledges the surviving failure twice to verify
idempotency. To demonstrate a fresh acknowledgement yourself, publish another run
and drain it with the same consumer group (this creates new lifecycle episodes):

```sh
docker compose run --rm --no-deps -T producer --output kafka --steps 1200
docker compose run --rm --no-deps -T consumer --idle-timeout 5
```

Refresh the dashboard, select the new active failure, and click Acknowledge.
Acknowledgement records review; it does not repair the device or clear the
condition. To stop all services while preserving data:

```sh
docker compose --profile tools down
```

## Rules, ownership and reliability

`simulator_state_v1` maps WARNING → WARNING, CRITICAL → CRITICAL and FAILED →
FAILURE. HEALTHY creates no alert. One unresolved episode per device/rule may be
ACTIVE or ACKNOWLEDGED. Repeated readings update evidence and preserve identity
and acknowledgement. Every severity change, including de-escalation, resolves
the old episode as `superseded` and opens a fresh ACTIVE episode. HEALTHY resolves
as `recovered`. A new run resolves as `lifecycle_changed` before applying its state.
RESOLVED is terminal; recurrence opens another episode.

The alert's `run_id` identifies its opening lifecycle. Resolution updates both
last-event and resolved-event evidence to the closing event. For
`lifecycle_changed`, the closing event may come from the new run while the alert
retains its original run ID. Simulation timestamps may restart across runs;
accepted ingestion order, rather than cross-run clock comparisons, determines
which event closes the episode.

The separate Python evaluator runs within the existing inbox transaction. It
locks the device/rule progress row before allocating accepted ingestion order;
inbox, episode changes and progress commit together. Identical event replay
does not update alerts, including their evidence/timestamps. Conflicting event
identities and invalid telemetry retain the existing DLQ behavior. Unexpected
evaluation/schema failures roll back and stop processing without offset commit;
transient database/lock failures use the existing bounded retries. Redis refresh
remains best effort after persistence, before the synchronous Kafka offset commit.

Episode IDs are deterministic UUID v5 values derived from the fixed namespace,
rule ID and opening event ID. PostgreSQL also enforces unique opening evidence
and one unresolved device/rule episode. Acknowledgement locks only its alert row.
Concurrent acknowledgement preserves the first timestamp. If resolution wins
the lock race, acknowledgement returns 409; if acknowledgement wins, resolution
retains its timestamp. All lifecycle and acknowledgement state survives restarts.

## Existing database upgrade

Migrations 001/002 remain unchanged. Migration 003 creates `alerts` and
`alert_evaluation_state` and streams existing inbox history in accepted order
through the same live evaluator in batches of 500. Its narrowly registered
Python backfill runs inside the migration transaction before its completion
marker. A SHARE ROW EXCLUSIVE inbox lock blocks inserts and permits ordinary
reads; lock acquisition times out after five seconds. Invalid legacy data fails
the migration rather than being skipped. DDL, backfill and bookkeeping roll back
together. Ordinary restarts do not replay the backfill or reset acknowledgement.

Pause **all old ingestion processes**, including separately launched ones, before
running the migration. `demo-alerts.sh` stops the Compose-managed service; operators
must stop independently launched consumers themselves. Deploy the new consumer
and API after migration, then resume the existing group. No volume deletion or
offset reset is needed. Readiness requires all three migrations and readable alert
tables; Redis failure still permits degraded readiness. Larger history backfill
duration/throughput remain unmeasured beyond the local demo.

## API and dashboard contract

All paths below use `/api/v1`:

| Method/path | Result |
| --- | --- |
| GET /alerts | Alert history/list |
| GET /devices/{device_id}/alerts | Scoped list; unknown device 404 |
| GET /alerts/{alert_id} | One episode; unknown ID 404 |
| POST /alerts/{alert_id}/acknowledge | No body; 200 current episode, 404 missing, 409 resolved |

List filters: optional `device_id` on the global list, repeated `status`, optional
`severity`, `limit` default 100/max 1,000, and positive `before` alert-order cursor.
Omitting status returns all statuses. Results descend by alert creation order;
pagination is a live view. List envelope is `{data_mode, items, next_before}`;
detail/ack is `{data_mode, ...Alert}`. All business responses label simulated data.
Every field from the implemented [schema](telemetry-schema.md#35-alerts-implemented)
is exposed, with UTC ISO times and explicit nullable fields.

Errors retain the existing `{error: {code, message}}` envelope: 404 `not_found`,
422 `invalid_request`, 503 `service_unavailable`, sanitized 500 `internal_error`,
and the additive 409 `alert_resolved`. Repeating acknowledgement preserves its
first timestamp; retrying a lost response is safe. A resolved alert never reopens.

`/alerts` has Open (ACTIVE + ACKNOWLEDGED), Resolved and All views, device/severity
filters, and bounded history navigation. Fleet/device panels show up to five
newest open episodes without claiming a total count. Simulation evidence times
and wall-clock acknowledgement times are labelled separately. Buttons appear
only for ACTIVE alerts and show pending, success, retryable failure and conflict
feedback. Next.js Server Actions call FastAPI server-side; default same-origin
action checks and disabled backend CORS remain. No alert state is stored in Redis.

## Verification and remaining decisions

```sh
bash scripts/test-kafka.sh
bash scripts/test-dashboard.sh
```

The backend suite covers the pure transition matrix, API validation/errors,
PostgreSQL constraints and atomic rollback, legacy backfill/repeatability/failure,
replay/restarts, distinct concurrent writers, concurrent acknowledgement and both
resolution-race outcomes, plus real Kafka redelivery after a commit crash.
The frontend suite covers existing views and alert display/filter/pagination,
loading/empty/errors, acknowledgement/pending/retry/conflict, keyboard/narrow
layouts, and a real C++ → Kafka → PostgreSQL → API → browser acknowledgement.
The isolated scripts clean only their own volumes; they do not erase demo data.

Local verification on October 29, 2026: 119 Python unit tests, 29 real-service
integration tests, production frontend build/TypeScript/lint, four chart-data
unit tests, 25 fixture browser cases and two real-pipeline browser journeys
passed. The documented alerts demo also passed against the existing saved inbox,
applying migration 003 without deleting data. The 3,603-event scenario produced
six episodes, covering all severities, supersession and recovery. These are
local checks; remote GitHub Actions results had not been verified at that
checkpoint. Throughput is not benchmarked by these checks.

Isolated baseline verification on **November 23, 2026** ran
`scripts/test-kafka.sh` followed by `scripts/test-dashboard.sh`; both exited 0:

| Check | Result |
| --- | --- |
| Backend Ruff, unit and integration checks | Passed; 119 unit tests and 29 integration tests |
| Broker interruption/recovery | Passed |
| Frontend build, TypeScript and lint | Passed |
| Chart-data unit tests | 4 passed |
| Fixture browser tests | 25 passed |
| Real-pipeline browser journeys | 2 passed |
| Longer isolated alert scenario | 3,603 events and six episodes verified, including acknowledgement and recovery |

This was a verification-only run. The normal development demo script was not
run; the test wrappers executed their ingestion/alert verifiers against
disposable test data. Each suite cleaned its own containers and volumes. The
persistent development volumes were retained and development services remained
stopped. All 162 tracked/untracked repository file contents checked, Git HEAD,
refs, index, and working-tree status remained unchanged during verification.
One existing Starlette/httpx deprecation warning was non-fatal; no fixes were made.
These results supplement the October 29 record above; they do not establish
remote CI success or a throughput benchmark.

**Constraint-test correction verified on November 23, 2026:** after documentation
review and owner approval, the existing integration test was corrected to use
distinct valid opening evidence and assert `alerts_one_open_episode_idx` by name
for both ACTIVE and ACKNOWLEDGED first episodes. The invalid-status assertions
remain, duplicate opening evidence is checked separately after resolution, and
fresh evidence is then accepted. The identified coverage gap is corrected;
production code, migrations and intended behavior are unchanged. See
[the correction and acceptance evidence](testing-strategy.md#alert-constraint-coverage-correction).

All 11 tests in the alert integration module passed in a separate PostgreSQL test
project. The subsequent isolated `scripts/test-kafka.sh` run exited 0: Ruff,
119 unit tests, 30 integration tests and broker recovery passed. The extra
integration case comes from testing both unresolved statuses. Both test projects
cleaned their disposable resources. The non-fatal Starlette/httpx warning remains.
The development demo and frontend suites were not rerun for this correction;
the October and earlier November records above are preserved.

Remaining decisions: public demo access/write policy and authenticated actors;
ML risk integration and policy; throughput/backfill benchmarks at larger scale;
retention/archival; broader browser coverage. There is no ML, email/notification,
assignment or escalation functionality in this increment. No dependency was added.

## Owner commit checkpoint

Cross-check A–F against implementation/tests and the synchronized docs before
merging. README now describes actual capabilities and the longer demo; schema,
API, architecture and frontend guides match the implementation. ADR-007 records
the meaningful transaction/bootstrap choice; ordinary UI details have no new ADR.
Resolved TBDs include simulator rules/episodes, acknowledgement semantics,
locking/replay, schema/bootstrap, alert APIs and UI. Remaining decisions are listed
above. The branch depends on `feat/dashboard`. The owner has approved preparing
one integration PR from `feat/alerts` to `main` for the completed feature chain,
with a proposed merge commit to preserve its development history. This is a
one-time exception to separate upstream feature merges and the documented
squash-merge convention. Merging still requires separate owner approval.

Before any further implementation or test-code changes, review requirements,
architecture, design and relevant documentation, update documents where
necessary, and obtain owner approval under the
[documentation-first SDLC rule](development-standards.md#documentation-first-sdlc).
This applies to all further corrections and to the upcoming AI/RAG feature.
Documentation-only approval does not authorize implementation or test edits.

The reviewed checkpoints package the existing alerts scope, including the
verified constraint-test correction. Documentation/design approval preceded
implementation; code and associated tests were grouped together, with
documentation kept separate.

As of November 26, 2026, all four checkpoints are committed and pushed to
`origin/feat/alerts` under explicit owner authorization:

| Checkpoint | Scope | Commit | Status |
| --- | --- | --- | --- |
| 1. Backend, migration and associated tests | 19 backend, test and verification/CI files | `bc20946` | Committed and pushed |
| 2. Dashboard and associated tests | 17 frontend implementation and test files | `0cac5cf` | Committed and pushed |
| 3. End-to-end verification/demo automation | Three automation files | `7acb665` | Committed and pushed |
| 4. Documentation | README and the 14 reviewed files below | `56834f6` | Committed and pushed |

All four checkpoints are complete. Do not repeat the completed commits.
Git operations remain owner-controlled under the
[explicit authorization rule](development-standards.md#phase-based-implementation-commits).
The commands below record the completed checkpoint 4 procedure, executed after
explicit owner approval of the reviewed diffs and exact 15-file allowlist. They
are historical instructions, not a request to stage or commit these files again;
documentation approval alone does not authorize Git mutations:

```sh
git add -- \
  README.md \
  docs/adr/ADR-005-separate-alert-evaluation-from-ml.md \
  docs/adr/ADR-007-atomic-simulator-alerts.md \
  docs/adr/README.md \
  docs/architecture.md \
  docs/basic-api-design.md \
  docs/basic-api.md \
  docs/dashboard-design.md \
  docs/development-standards.md \
  docs/frontend.md \
  docs/persistence.md \
  docs/telemetry-schema.md \
  docs/testing-strategy.md \
  docs/alerts-design.md \
  docs/alerts.md
git diff --cached --stat
git diff --cached --check
git diff --cached
git commit -m "docs(alerts): document contracts, rollout, and verification"
git push origin feat/alerts
```

Pushing backs up committed work; it does not merge the upstream feature chain
into `main` or trigger the workflows' main-only push events. PRs or manual
workflow dispatch provide remote CI. The local verification records above do
not establish remote CI success. Integration of the dependent features remains
a separate reviewed step; these instructions do not authorize merging or
starting AI/RAG implementation.
