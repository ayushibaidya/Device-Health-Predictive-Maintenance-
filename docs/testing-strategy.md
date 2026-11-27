# Testing Strategy

## Testing Goals
The testing strategy for this project will focus on validating that the system behaves correctly, remains stable under failure, supports maintainability, and provides evidence that product requirements are met as implementation proceeds.

The strategy will be extended as the platform becomes more concrete. The broader
strategy remains at the requirements level; component-specific executable tests
and verification commands are documented with each implemented component.

The first simulator increment now has executable lifecycle, model, JSON contract,
CLI, recovery, and repeatability checks. Its commands and demo are documented in
[simulator.md](simulator.md); the broader strategy below applies as additional
components are introduced. Run `ctest --preset dev` after building.

Kafka ingestion adds producer identity/failure tests, Python validation and
acknowledgement-boundary checks, and real Kafka/PostgreSQL integration tests.
`bash scripts/test-kafka.sh` checks restart deduplication, the database-before-
offset crash window, DLQ delivery, database recovery, and broker interruption.
The Kafka ingestion GitHub Actions workflow runs the same script.

## Unit Testing
Unit tests will validate the correctness of individual logic components, calculations, feature transformations, model utility functions, and validation logic.

The unit testing focus should include:
- telemetry validation logic
- feature engineering logic
- health and risk calculations
- alert threshold evaluation
- data serialization and conversion
- ML helper functions and evaluation utilities

## Component Testing
Component tests will validate the behavior of meaningful subsystems in isolation, including processing components, adapters, and service-layer logic.

The initial focus should include:
- telemetry processing steps
- anomaly detection workflow components
- prediction workflow logic
- device health aggregation logic
- alert generation logic

## API Testing
API tests will validate the behavior of backend interfaces, request/response contracts, error handling, validation, and service integration boundaries.

The testing scope should include:
- telemetry ingestion endpoints
- health queries
- historical retrieval APIs
- alert and prediction read APIs
- failure and validation scenarios

## Database Testing
Database testing will validate persistence, schema integrity, transactional behavior, historical data retrieval, and relationship accuracy.

This should include:
- data insertion and retrieval correctness
- time-series retention patterns
- relationship integrity for device, firmware, and alert records
- query performance under representative conditions

## Kafka/Event Pipeline Testing
Kafka testing will validate the reliability and correctness of event-driven ingestion and downstream processing.

Key areas include:
- message publication and consumption
- ordering and replay assumptions
- failure recovery and retry behavior
- message backlog handling
- processing lag and downstream backlog visibility

## Redis Testing
Redis testing will validate current-state access, ephemeral data handling, cached values, and operational coordination logic.

Areas should include:
- cache correctness
- TTL behavior
- transient state accuracy
- failover and resilience assumptions
- read/write consistency expectations

## ML Validation Testing
ML validation testing will assess the quality of the predictive and anomaly workflows using documented metrics and evaluation processes.

This should include:
- baseline model validation
- model comparison across candidate algorithms
- classification performance checks
- anomaly detection quality checks
- drift and stability monitoring preparation
- performance and latency validation for inference

## Integration Testing
Integration tests will validate interactions between multiple system components, including telemetry flow, storage, processing, API, and monitoring components.

This will be required for validating operational correctness across the real platform architecture once implementation begins.

## End-to-End Testing
End-to-end testing will validate the entire user flow from simulated device emissions through ingestion, processing, storage, API access, and dashboard visibility.

This testing layer should confirm that the end-to-end system supports the intended operational workflow for device monitoring and predictive maintenance.

## Performance / Load Testing
Performance testing will validate throughput, latency, queue behavior, and resource utilization under expected and stress conditions.

This will include:
- telemetry ingestion under sustained load
- downstream analytics and prediction processing under backlog
- API responsiveness under concurrent access
- storage and query behavior under historical data growth

Performance targets must remain labeled as TARGET values until measured experimentally.

## Failure-Injection Testing
Failure-injection tests will deliberately trigger service, queue, dependency, or data issues to validate resilience and recovery behavior.

This should include:
- producer interruption
- consumer failure
- database connectivity issues
- queue backlog and recovery
- degraded service mode validation
- operational alerting during failure scenarios

## Regression Testing
Regression testing will protect against accidental behavior changes across firmware changes, model changes, service updates, and platform refactors.

This includes validating:
- alerting consistency
- health-score changes over time
- model output stability with known data
- previously resolved issue reproduction

## CI Expectations
The implementation phase should include CI expectations that verify correctness and quality before merge, such as:
- automated unit tests
- API validation tests
- relevant integration tests
- linting or static checks where applicable
- performance smoke checks for critical flows
- regression checks for ML and alerting workflows

The implemented ingestion/data-access workflow runs `bash scripts/test-kafka.sh`
in GitHub Actions. It covers 119 Python unit tests and 30 real-service integration
tests, including API response/error contracts, HTTP reads of simulator events,
health/readiness, concurrent database connection isolation, history/pagination,
lifecycle replay, migration of populated inboxes, Redis recovery/expiry, and
durable processing during cache connection failure. The C++ producer image
retains its 39 CTest checks. The script also
exercises a broker interruption and cleans only its own test volumes.
`bash scripts/demo-api.sh` demonstrates the full implemented pipeline through
HTTP, with history/current-state/cache recovery. Alert tests additionally cover
the transition matrix, episode identity, atomic inbox/alert/cursor rollback,
historical backfill and its rollback, constraints, concurrent distinct events,
acknowledgement idempotency, both resolution lock races, and acknowledgement
surviving a real Kafka offset-commit crash/replay. ML tests arrive with ML.

## Implemented Frontend Verification

`bash scripts/test-dashboard.sh` builds the pinned Next.js application and runs
TypeScript, lint, four Node chart-data unit tests, and 25 Chromium browser cases.
Test-only HTTP fixtures provide deterministic loading, empty, failure, pagination,
and rendering scenarios. A separate browser smoke test uses real C++ events
through Kafka, validation, PostgreSQL/Redis and FastAPI: fleet → device → history.
A second real-pipeline browser journey uses the existing 1,200-step C++ scenario
(3,603 events), verifies WARNING/CRITICAL/FAILURE and recovery, and acknowledges
the active failure through the dashboard, reloads and repeats safely through
the API. UI fixtures cover alert filters/history, action pending/error/conflict,
loading/empty/API failure and narrow/keyboard behavior.
No fixture data is used by the production application. The isolated test project
owns its own ports, containers and disposable volumes; GitHub Actions runs the
same command. Other browser engines and large-fleet measurements remain pending.

The November 23, 2026 isolated baseline run passed both test scripts sequentially:
Ruff, 119 Python unit tests, 29 backend integration tests, broker recovery,
frontend build/TypeScript/lint, four chart-data tests, 25 fixture browser tests,
and two real-pipeline browser journeys. These local results record the baseline
before the constraint-test correction below; they do not establish remote CI success.
See [the dated alerts verification record](alerts.md#verification-and-remaining-decisions)
for resource isolation and historical results.

## Alert constraint coverage correction

Status: **corrected and verified locally on November 23, 2026**, after owner
approval of the documented test-change scope under the
[documentation-first SDLC rule](development-standards.md#documentation-first-sdlc).
The intended alert behavior, production code and migrations are unchanged.

The original `test_database_rejects_invalid_status_and_second_open_episode` in
[test_alerts_integration.py](../processing/tests/test_alerts_integration.py)
attempted to insert a second unresolved episode by copying an existing alert's
`rule_id` and `opening_event_id`. It accepted any `psycopg.errors.UniqueViolation`.
That insert violated both the unique `(rule_id, opening_event_id)`
constraint and the partial unique `alerts_one_open_episode_idx` on
`(device_id, rule_id)` for ACTIVE/ACKNOWLEDGED rows. The opening-event constraint
could satisfy the assertion even if the partial index were missing.

The corrected test persists a distinct valid WARNING event for the same device
and lifecycle, then attempts a new alert ID/opening event for the same rule while
the first episode remains unresolved. It runs once with the first episode ACTIVE
and once with it ACKNOWLEDGED, asserting the actual
`diag.constraint_name == "alerts_one_open_episode_idx"` in each case.

The existing invalid-status checks remain. After resolving the first episode,
the test separately verifies duplicate opening evidence is rejected by
`alerts_rule_id_opening_event_id_key`, then confirms the distinct opening evidence
can create an episode. This isolates both uniqueness guards and checks that the
partial index stops blocking a new episode after resolution.

Verification after correction: all 11 tests in `tests/test_alerts_integration.py`
passed against an isolated PostgreSQL instance. Then `scripts/test-kafka.sh`
passed Ruff, 119 unit tests, 30 integration tests and broker interruption/recovery.
The increase from 29 to 30 integration cases comes from parametrizing the existing
constraint test. Both disposable projects were cleaned up; the development demo
was not run. The existing Starlette/httpx warning was non-fatal. Frontend suites
were not rerun for this test-only correction; their earlier results remain above.

## AI investigation acceptance plan

Status: documentation/runbook preparation only. No AI implementation, dependency
installation, model execution or passing AI test result is claimed. The
[feature contract](ai-investigation-design.md#acceptance-criteria-and-next-increment)
and [ADR-008](adr/ADR-008-local-ai-investigation.md) define the approved direction.
The historical simulator, alerts and frontend results above remain unchanged.

| Layer | Planned checks |
| --- | --- |
| Corpus review | Six allowlisted Markdown files; unique IDs, safe paths, exact SHA-256 values and source references checked against baseline `2b919b7`; no invented diagnoses or thresholds |
| Retrieval unit/filesystem | Temporary directories and fake encoders for parsing, exact source spans, 256-token limit including prefixes/special tokens, overlap, known-vector cosine ranking/ties, top-three bounds, restart loading, no-op reuse, atomic replacement and incompatible profile rejection |
| Local MiniLM | Separately provisioned, explicitly enabled real-model test: local-only loading, normalized 384-dimensional vectors, relevant/unsupported queries and useful top-three guidance; network disabled during execution |
| Evidence integration | Disposable PostgreSQL fixtures: all alert statuses, captured `A001` alert fields and linked evidence identities, same-device/run isolation, five-minute inclusive window, 100-row cap/truncation, accepted-order cutoff, explicitly labeled next-run closing metadata, concurrent updates and transaction/connection closed before model invocation; assert no writes |
| Generation/API | Fake HTTP/model responses for `A001`/`E...`/`D...` source validation, rejection of unknown IDs or altered source identities, exclusion of next-run telemetry, unavailable assets, busy admission, timeout/cancellation/recovery, malformed output and insufficient guidance without LLM calls; existing error envelopes and endpoints preserved |
| Browser | Existing alert to button/pending/inline report with inspectable sources; insufficient evidence, errors and manual retry; existing navigation and acknowledgement still work |
| Real local demo | Real PostgreSQL alert evidence, real MiniLM retrieval and real Qwen/Ollama report; record actual runtime/model versions/digests, source references, latency and resource observations |

Keep supported/unsupported retrieval cases labeled before tuning. Freeze relevance
selection on development cases and evaluate untouched cases separately; do not
invent a universal similarity cutoff or publish accuracy numbers before measuring.
Reference membership checks do not establish that generated claims follow from
their citations; review grounding and simulation-specific limitations separately.

Default automated suites must remain usable without model weights or a running
Ollama: fast tests use isolated fakes, and real-model cases require explicit
opt-in/provisioning. Tests never download models implicitly, substitute fake
production vectors, run the persistent-data demo or modify development volumes.
Add test configuration/scripts only in the approved implementation increment.
After implementation, run relevant isolated backend/dashboard regression suites
and the opt-in real-model demo. Keep new verification evidence dated and separate
from historical passing results. Large-corpus/load studies are deferred.

Checkpoint 1 documentation verification on November 26, 2026: all six runbooks
were cross-checked against the simulator and related ingestion/alert code at
`2b919b7`; all 12 implementation-reference files exist at that baseline. The six
manifest hashes, 151 local file links, 19 anchors and changed-file whitespace
checks passed. The 39 external URLs were checked for syntax, not HTTP availability.
These are documentation checks; no models or runtime test suites were run.
