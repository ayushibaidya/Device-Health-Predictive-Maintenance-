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

Status: Checkpoint 1 documentation/runbooks are committed; Checkpoint 2A manifest
validation and chunking are implemented and verified. All 44 focused tests passed
with zero skips using the real MiniLM tokenizer and owner-installed optional runtime.
The owner subsequently verified the real MiniLM smoke (77 tests passed; see the
November 27 record below); no generation result is claimed. The
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

Checkpoint 2A focuses on corpus metadata/path/hash failures, unlisted-source
exclusion, exact source spans, heading/code-fence boundaries, overlap, Unicode,
repeatability and complete-input token limits. Use temporary corpus fixtures;
verify the six actual runbooks separately without changing their review status.
Run the real cached MiniLM tokenizer in an isolated optional tools image, with
network access disabled during tests. Keep dependency-free/fake-tokenizer checks
available to the existing backend suite. Record actual results after execution;
no embedding, Ollama, FastAPI or dashboard work belongs to this increment.

November 26, 2026 Checkpoint 2A checks used the existing pinned Python 3.13.18
backend test image with read-only source and no network/installations: Ruff passed;
41 focused cases passed and three real-tokenizer cases skipped explicitly. The
backend unit suite passed 160 cases, with three skips, 30 integration cases
deselected and the existing non-fatal Starlette/httpx warning. The real six-file
validation CLI succeeded without changing corpus hashes or review status.
The initial Docker mount invocation failed before tests started because the
workspace ends with a space; the corrected read-only volume syntax then passed.
The three skipped cases cover real MiniLM truncation/padding, Unicode/subword
spans/overlap, and repeatable six-runbook CLI chunking. They were not passing
results at that earlier checkpoint. The owner chose to install the isolated
runtime personally; no packages or models were installed by the agent.
Backend integration and frontend suites were not rerun for this isolated,
read-only preparation component.

Subsequent November 26, 2026 verification: after the owner built the optional
image, `scripts/test-ai-chunking.sh` passed Ruff and all 44 focused cases, with
zero failures and zero skips. The agent independently reran the checks and
confirmed the same result, including all three previously skipped cases. Tests ran
offline with read-only repository/tokenizer mounts and disposable temporary
storage. Runbook hashes and the pending-owner-review status were preserved.
This completes 2A verification; it does not establish embedding, ranked retrieval
or LLM-generation functionality. The earlier 41-passed/three-skipped and backend
unit results above remain historical evidence.

## Checkpoint 2B initial embedding smoke plan

Only model preparation, isolated dependency setup and a minimal local encoder are
authorized here. Revalidate the pinned 49-package CPU plan against Python 3.13.18
and existing backend/2A constraints without installation. Keep source runbooks
and their pending-owner-review status unchanged.

Unit checks use temporary, test-only assets for manifest/path/hash validation,
dereferenced copies, idempotent preparation, partial-copy cleanup and refusal to
overwrite an incompatible destination. Encoder unit checks cover invalid
text/token limits and missing/incompatible assets/runtime; the real smoke
validates actual output shape/dtype/values.
Importing the package must not load Torch or Sentence Transformers.

The opt-in real smoke loads the prepared, checksum-verified MiniLM locally,
with networking disabled. Require float32 `(N, 384)` output, finite values,
unit norms, agreement with 2A token counts and repeatability within
`rtol=1e-5`, `atol=1e-6`; include input longer than the asset's old 128-token
truncation setting. An explicit run must fail rather than skip if its runtime or
assets are missing. Keep the existing 44 2A cases as regression coverage.

At the initial setup-only checkpoint no embedding smoke had passed. The owner
needed to build the separate image, prepare cached assets and run the smoke;
the subsequent November 27 verification records below close that runtime gap.
They do not establish LLM or application integration functionality.

November 26, 2026 initial 2B setup verification used the existing 2A optional
image, Python 3.13.18 and the real cached tokenizer, with networking disabled
and read-only mounts. Ruff passed; **76 tests passed, 1 skipped**: the original
44 2A cases and 32 new provisioning/input/runtime-guard checks passed. The only
skip was the explicit real-model smoke without `MINILM_MODEL_DIR`. All 11 cached
model hashes, Python syntax and embedding-runner shell syntax also passed.
No dependencies were installed, images built or model assets downloaded/copied
for this verification. This supplements the earlier 44-passed/zero-skipped and
41-passed/three-skipped 2A records; it does not replace them or establish actual
MiniLM encoding. Follow the [manual embedding setup and smoke](ai-investigation-design.md#manual-embedding-setup-and-smoke)
to provision and run the real embedding checks.

## Checkpoint 2B index and retrieval verification plan

November 27, 2026 owner-reported runtime result: 11 model files prepared, optional
retrieval image built, normalized float32 output with shape `[3, 384]`, **77 tests
passed, zero failures**, one FutureWarning concerning the dimension accessor.
Preserve the earlier setup-only and 2A verification records above.

The approved next scope replaces that deprecated accessor without changing its
dimension check, then adds the rebuildable JSON index and cosine candidate search.
Unit/filesystem cases must verify creation, complete reload, no-op reuse without
re-encoding, exact source references, known-vector ranking and ties, top-three
limits, invalid vectors/queries, JSON/checksum corruption, source/model/tokenizer/
chunker incompatibility, missing files, lock contention, atomic replacement and
preservation of the old artifact on failures. Fake vectors are isolated tests
only; production never uses a fake encoder or keyword fallback.

Add a separately enabled offline real-model test using all six existing runbooks
and temporary index paths. Freeze six source-derived supported questions with
expected document IDs and an unsupported battery-maintenance question before
looking at scores. Require the expected document among the top three for each
supported question, inspect source spans, and preserve deterministic results after
reload. Unsupported questions still return explicitly uncalibrated candidates;
this increment does not establish a relevance cutoff or an abstention model.
These smoke expectations are not owner-approved labels or held-out accuracy.
No database, broker, Redis, Ollama, API or dashboard resources are required.
Run the existing 77 cases and the new tests in the already-built separate image,
with networking disabled and models/repository mounted read-only. Record actual
results after implementation without replacing historical evidence.

November 27, 2026 agent-run final verification:

- Existing retrieval image: `pip check` and Ruff passed; **113 tests passed,
  zero failures/skips**, with FutureWarnings treated as errors. All previous
  77 cases passed alongside 36 new index/retrieval cases.
- Real offline MiniLM: normalized float32 `[3, 384]` smoke passed; 30 chunks
  from all six existing documents were indexed/reloaded; all six predefined
  supported questions found the expected document among the top three.
  The unsupported question returned explicitly uncalibrated candidates.
- Lightweight 2A image without embedding dependencies: **111 passed, 2 skipped**;
  only the explicit real embedding/retrieval smokes were skipped. This confirms
  the unit/default path stays separate from the heavy optional runtime.
- The actual shell CLI built/searched a temporary index and returned the
  error-count runbook first with original text, document version and source
  locations. Both deprecated aliases were replaced after inspecting the
  installed library; the final demo emitted neither notice.

All runs were offline, used read-only repository/model mounts and isolated
temporary indexes, and did not touch PostgreSQL, Kafka, Redis or the persistent
development index. No dependencies were installed, images built or models
downloaded. Application/backend/dashboard suites were not rerun because this
increment changes only the optional AI module/tooling. Runbook content/hashes
and pending owner-review status are unchanged. Relevance calibration and
held-out evaluation remain pending; these source-derived questions are smoke
coverage, not a claim of production accuracy or unsupported-query abstention.

Approved Checkpoint 2B fixture correction: isolate boolean rejection with a
384-dimensional boolean vector that would have unit length if numerically
coerced. Insert duplicate JSON keys into otherwise valid index/manifest data,
preserving required fields and the index checksum. Check the duplicate-key error
(including the wrapped manifest cause) so unrelated validation cannot satisfy
these negative tests. Production behavior and the 113-case count remain unchanged.
The corrected-fixture rerun passed all **113 tests, zero failures/skips**, Ruff
and dependency consistency in the existing offline retrieval image. No production
defect was found and no production code changed. This supplements, rather than
replaces, the earlier Checkpoint 2B results.

## Checkpoint 3A PostgreSQL evidence verification plan

The approved evidence contract requires one repeatable-read/read-only snapshot,
captured alert fields and `A001`/`E...` references, inclusive five-minute simulation
bounds, at most 100 readings with cap detection, and accepted-order lifecycle
isolation. Review that contract before implementing; no new database schema,
ingestion/acknowledgement behavior or report-sufficiency threshold is required.

Unit cases cover missing/invalid alerts, inconsistent/missing evidence, payload
identity mismatches, closing relations, sparse/no-anchor cases, database failures
and transaction/connection cleanup. Real PostgreSQL cases cover ACTIVE,
ACKNOWLEDGED and RESOLVED alerts, simulation-clock resets, opening/closing evidence
outside the window, ordering and cutoff, 100/101-row boundaries, actual read-only
enforcement and concurrent updates after snapshot capture. Sparse valid evidence
retains its actual count; absent/inconsistent required links fail explicitly.

Use only cached images and a uniquely named internal Docker network with a fresh
PostgreSQL 18.6 container backed by tmpfs, no host ports/development volumes and
explicit test-only database credentials. Test schemas/migrations are confined to
that disposable instance. Run relevant backend unit/alert integration checks in
the existing lightweight backend environment; separately rerun the 113 existing
AI tests in the optional retrieval image. Do not install models, run the persistent
demo, or merge/stage/commit anything. Record actual results after execution.

November 27, 2026 Checkpoint 3A verification:

- Docker Desktop was restarted after macOS; Docker 29.9.3 ARM64 and the existing
  backend, PostgreSQL and optional retrieval images were reused. No packages,
  images or models were installed/downloaded. The first evidence-runner attempt
  stopped before tests because the combined PostgreSQL tag/digest was not found
  locally; using its identical cached repository digest resolved that lookup.
- `scripts/test-ai-evidence.sh`: dependency consistency and Ruff passed;
  **260 passed, 5 skipped, 46 deselected** in the backend unit phase. The skipped
  cases require optional tokenizer/model provisioning and are covered by the
  separate real-model suite. All 33 new evidence unit cases passed.
- Disposable PostgreSQL phase: **27 passed**, covering all 16 new evidence cases
  and 11 existing alert integration cases. Checks include otherwise eligible
  other-device/prior-run rows, clock resets, accepted-order/time boundaries,
  99/100/101-reading caps, old opening identity outside the window, actual
  read-only SQLSTATE `25006`, zero application-row changes, connection closure,
  captured status during concurrent updates and explicit database/evidence errors.
- `scripts/test-ai-embeddings.sh`: **113 passed, zero failures/skips**, Ruff and
  dependency consistency passed with the unchanged optional model environment.

The backend phases each retain the existing Starlette/httpx TestClient
deprecation warning; no dependency change was made to silence it. Databases were
fresh tmpfs containers on unique internal networks, not persistent development
volumes. Full Kafka interruption and browser workflows were not rerun; their
earlier results above remain historical evidence. This verifies the evidence
module, not the unimplemented report/API/UI composition or LLM.

Approved Checkpoint 3A calendar-boundary correction: a valid anchor whose exact
five-minute window underflows the supported calendar range must raise sanitized
`EvidenceUnavailable`, with rollback and connection cleanup. Regression cases
cover the minimum timestamp and one second below the first representable full
window; the exact five-minute boundary must still succeed with unchanged bounds.
This changes failure handling only, not ingestion acceptance, lifecycle filtering,
the evidence window or existing alert behavior.

The corrected November 27 rerun passed **263 backend unit tests, 5 skipped,
46 deselected**, including all three calendar-boundary cases; **27 PostgreSQL
integration tests**; and **113 AI tests, zero failures/skips**. Ruff and dependency
consistency passed. The evidence suite now has 36 unit and 16 integration cases.
Underflow cases assert the sanitized error, original `OverflowError` cause,
transaction rollback and closed connection; the successful boundary case asserts
the full five-minute interval and cleanup. The existing Starlette/httpx warning
remains nonfatal. Fresh tmpfs test resources were used; no development data,
dependencies or Git history changed. The earlier 260-test result remains above
as historical evidence.

## Checkpoint 3B report/provider verification plan

The approved continuation adds the 16K/2,048-output/12,000-byte/90-second defaults,
a development-only calibrated relevance threshold and separate held-out checks.
Freeze the labeled questions before observing scores. Test threshold selection,
wrong-source/unsupported rejection, index/evaluation mismatch, and disabled-gate
abstention with no provider invocation. A failed real relevance evaluation is a
reported blocker; do not change labels or thresholds to fit held-out outcomes.

Add a validated summary runner which suppresses raw test/demo child output and
prints only pass/fail, aggregate counts, timings and fixed error categories.
Test unknown fields, malicious strings, invalid numbers, malformed summaries,
and canary credentials/records/prompts/reports emitted by a failing child. These
checks validate this output path, not every dependency or arbitrary future log.
The disposable terminal demo must enforce isolated database naming, use only
existing migrations, close database work before model calls and fail explicitly
on prompt overflow. Real generation is opt-in; model/runtime installation and
network configuration changes remain outside this increment.

Verify the exact two-reading demo prompt without installing a combined runtime:
the disposable PostgreSQL integration test may export only its synthetic fixture
to a unique temporary directory shared with the offline retrieval tests. Use real
MiniLM candidates from the unchanged corpus for a size-only preflight, without
accepting their relevance or calling Ollama. Delete the fixture directory with
the test resources. No production database records enter this handoff.

Start with strict report/source validation and a local-only HTTP client. Use
fake providers and local in-process HTTP servers; never download a model during
tests. Cover malformed/duplicate-key JSON, missing/extra fields, source-reference
membership and citation categories, unlabeled hypotheses, altered server-owned
sources, incomplete/truncated output, unavailable/wrong runtime or model digest,
bounded bodies, hard deadlines and resource cleanup. Keep PostgreSQL evidence and
the optional embedding environment unchanged. The initial preparation required
owner review of relevance policy and prompt/context defaults; the approved
continuation above supplies those defaults and fail-closed evaluation criteria.
Real Qwen grounding, latency, context sizing and host connectivity remain pending
until the owner manually provisions the selected runtime/model.

November 27, 2026 implementation verification (preserving the earlier results
above):

- **59 new tests passed** across `test_investigation_reporting.py` and
  `test_ollama_client.py`. They cover server-owned references and lifecycle
  filtering, strict report structure, malformed/duplicate JSON, mandatory
  guidance selection, insufficient guidance without an LLM request, prompt
  budget rejection without dropping evidence, shared admission/release,
  runtime/model provenance, local-only transport, bounded/truncated responses,
  stalled/drip-fed HTTP deadlines and cleanup. Selectors/providers are explicit
  test fakes, not a production relevance policy or actual model.
- `scripts/test-ai-evidence.sh`: **322 passed, 5 skipped, 46 deselected** in
  the backend unit phase; **27 passed** in fresh PostgreSQL containers, including
  the existing alert integration cases. Ruff and dependency consistency passed.
  The five optional tokenizer/model skips are covered by the separate runtime.
- `scripts/test-ai-embeddings.sh`: **113 passed, zero failures/skips** with
  the unchanged cached MiniLM assets and optional image; Ruff and dependency
  consistency passed. No embedding/index behavior or dependencies changed.

The existing Starlette/httpx TestClient deprecation warning remains nonfatal.
All repository mounts were read-only; PostgreSQL used unique internal networks
and tmpfs, without development volumes or host ports. No models, software or
dependencies were installed. The optional combined Dockerfile was reviewed for
matching shared pins (60 combined packages, no version conflicts), but not
built; combined installation/import compatibility therefore remains unverified.
At that initial verification, real Qwen generation, unsupported-claim/grounding
review, relevance calibration, default budgets and connectivity remained pending.
API/browser/full demo and Kafka interruption suites were not rerun in this
increment. The earlier 3A/2B and full workflow results remain historical evidence.

Subsequent approved continuation, November 27, 2026:

- `scripts/test-ai-investigation.sh` passed **374 backend unit tests, 7 skipped**
  in **2.318 seconds**; **28 PostgreSQL integration tests, zero skips**, in
  **1.590 seconds**; and **137 optional AI tests, zero skips**, in **6.873 seconds**.
  Skips concern optional model/tokenizer/synthetic-handoff provisioning in the
  backend-only phase; the offline AI phase covers them with the explicit assets.
- Real MiniLM relevance evaluation took **3.138 seconds**: **12 development cases
  passed, one failed**, and **13 held-out cases remained unscored**. No threshold
  satisfied the development acceptance gate. The script intentionally exits 1
  with `relevance_unvalidated`; this is a relevance blocker, not a failed unit
  test. Do not retune using held-out labels or silently accept the top three.
- Real candidate-size preflight passed for the two-reading disposable PostgreSQL
  fixture and all three MiniLM candidates at the approved 12,000-byte limit.
  It supplies no relevance or generated-report/grounding claim.
- Unit checks cover summary schema/enum/numeric validation, duplicate/malformed
  JSON, canary child stdout/stderr, unknown exception messages/codes, CLI error
  values, outer Docker relay validation, and consistent process exit status.
  Disabled-gate and empty-selection cases assert zero provider calls.
- The default terminal demo returned `missing_runtime` (exit 2) before database
  creation because the optional combined image is absent. That full workflow,
  real report generation, Docker-to-host connectivity and optional saved-report
  mount remain unverified. No Ollama generation was called by this continuation.

Existing runbook/model hashes and dependencies were preserved. Temporary
synthetic-fixture handoffs, databases and networks were cleaned up; no persistent
development data was used. The earlier 322/27/113 test records remain historical
results; the results above are the
final synthetic-handoff verification, not a new real-Qwen benchmark.

Relevance-blocker diagnosis and correction plan: the failing development question
asks “What command repairs the device firmware automatically?” and correctly
expects no accepted documents. Firmware chunks score 0.6364894273640975,
0.6040028097435218 and 0.5837521896606158, all above the development-derived
0.48011912149223085 threshold. The threshold is limited by the supported old
simulation-timestamp question, so raising it cannot solve the separation problem.

Before implementation, document a narrow guard for explicit requests for
remediation commands/scripts, using the existing no-remediation scope. Add
paraphrase, read-only capability-question, runtime/evaluation consistency and
policy-version mismatch tests. Keep all corpus/evaluation labels and held-out
questions unchanged. Real-model regression tests must score development only;
the separately finalized policy gets one explicit held-out run. Record failures
without changing the threshold, labels or guard after seeing held-out results.

November 27 relevance-only correction verification:

- Real development evaluation: **13 passed, zero failed**, same threshold
  **0.48011912149223085**. The unsupported firmware-command request is rejected
  by the scope guard, with unchanged labels, documents and embeddings.
- Regression checks before held-out scoring: **390 backend unit tests passed,
  7 optional skips**, in **2.744 seconds**; **152 AI tests passed, 1 skip**, in
  **6.570 seconds**. The AI skip is the PostgreSQL synthetic-fixture prompt-size
  check, not relevant to this retrieval-only run; its earlier passing result is
  retained above. Real relevance regressions now score development only.
- Ruff passed. No dependency, model, database, API, frontend or ingestion changes.
  PostgreSQL/browser/real-LLM workflows were not rerun in this correction.
- The single explicit held-out run took **3.370 seconds**, with **11 passed,
  2 failed, zero skipped**. One correct error-count chunk scored below the frozen
  cutoff; another case accepted a thermal chunk outside its allowed document
  label. Full questions, scores, locations and all outcomes are in
  [the diagnosis](ai-generation.md#relevance-blocker-diagnosis).

Policy source, dataset and index fingerprints were checked before held-out
scoring. The finalized policy was not changed afterwards; the entire gate remains
disabled. No held-out-driven threshold/label correction is claimed. These cases
are now inspected evaluation evidence; a subsequent policy needs a newly frozen
held-out set. The original 12/1 development failure and 374/28/137 regression
record remain historical evidence above.

Approved manual-smoke preparation: preserve held-out failures without rescoring
or tuning. Review all six runbooks against the actual simulator/alerts code and
record design-only/unverified claims without marking owner approval. The
[manual smoke contract](ai-manual-smoke.md) requires two fixed, hash-checked
original excerpts, a fresh disposable PostgreSQL packet and the approved prompt
budget. Test missing confirmation, changed chunks, non-demo/mixed-run packets,
phase-2 database credentials, schema/citation errors, and local report labeling.
Generation is opt-in and faked in automated tests. Verify cached-container
connectivity using metadata only; do not build images, install or generate.

The standalone tool must be present only in the backend Dockerfile's test stage
so the added tests can import it during CI. The production runtime remains
unchanged. This is packaging for verification, not an application integration.

November 27 manual-smoke verification: **413 backend unit tests passed, 9 optional
skips**, in **2.603 seconds**; **28 disposable PostgreSQL tests passed**, in
**1.980 seconds**; and **154 offline AI tests passed, one skip** (the separate
synthetic-handoff-dependent check), in **8.418 seconds**. Fake tests cover the
manual confirmation, pinned sources, no generation-phase DB configuration,
source-reference errors, fixture boundaries/budget, development labeling and
explicit 0600 report saving. Ruff passed.

The public preparation script separately created the actual two-reading packet,
destroyed its database/network and passed offline source/budget checks. Its prompt
including the development notice is **7,878 / 12,000 bytes**. The public metadata
probe passed from the same cached image used for the manual generation phase;
an internal-network probe failed. The staged workflow preserves DB isolation
without changing server binding. Missing manual confirmation was rejected before
generation. The combined image was not built, dependencies/models were not
installed, and real generation was not run. Existing held-out failures and older
verification results remain unchanged. See [manual review and commands](ai-manual-smoke.md).

First real manual generation failure (owner-reported): `ai_invalid_response`,
66.745 seconds, no saved validated report. The aggregate cannot identify the
original substage. Before code changes, specify fixed stage diagnostics for
provider body/JSON/completion/token checks, report JSON/schema/references and
model provenance. Keep every existing rejection and the original application
error code. Focused fake-response tests must verify stage categories, unchanged
schema/reference rejection and no raw input/message leakage. No real LLM retry,
retrieval tuning, new dependencies or generation-parameter changes are authorized.

Diagnostic-only verification passed **117 focused tests, zero failures/skips**,
in **1.214 seconds**, with Ruff passing. Fake cases distinguish provider length,
envelope, HTTP/body/JSON and token failures, report JSON/schema/reference failures
and manual provenance. Canary tests reject unapproved stage values and expose no
provider input/error text in summaries. The original rejected response was not
retained, so its cause is unconfirmed. No real-model call or generation-setting,
schema, reference-policy, cutoff or label change was made.

Checkpoint 3B preservation verification, November 27: **422 backend tests passed,
9 optional skips** (2.519 seconds), **28 isolated PostgreSQL tests passed, zero
skips** (1.580 seconds), and **155 offline AI tests passed, zero skips** (8.309
seconds). The PostgreSQL-to-AI handoff uses only a fresh synthetic fixture and is
deleted with the temporary resources. This verifies the full uncommitted 3B scope
including the diagnostic correction; the earlier 117-test focused result remains
above. Ruff and dependency checks passed. No held-out cases were rescored, no
real Qwen generation ran, and no packages/images/models were installed or built.
See the [pause handoff](ai-investigation-handoff.md) for the unresolved 11/13 gate
and failed real attempt; neither is reported as a passing validation.
