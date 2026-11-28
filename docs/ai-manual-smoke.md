# Development-only manual investigation smoke

This is a controlled generation experiment, not automatic RAG validation or an
application endpoint. Automatic relevance remains disabled: development 13/13,
held-out 11/13. The error-count paraphrase scored 0.35276493876953824 below
0.48011912149223085; the lifecycle question additionally selected a thermal
chunk at 0.5014121688242127 outside its label. Preserve these failures and the
unchanged cutoff/labels. See [full evaluation evidence](ai-generation.md#relevance-blocker-diagnosis).

## Runbook factual review

Reviewed against the actual repository implementation at `798621d` plus current
AI-only work. All six original documents retain
`source_checked_pending_owner_review`; no owner approval or corpus rewrite occurs.

| Runbook | Source-checked facts | Remaining limits / unverified content |
| --- | --- | --- |
| `thermal-power` | `Device::sample` derives both metrics from hidden degradation plus bounded noise; `Device::advance` uses hidden-state rules, not those metrics | Physical overheating/electrical diagnoses are unsupported; AI wording is a required constraint, not verified generated behavior |
| `cpu-memory` | Both percentages are synthetic and clamped 0–100; validator accepts optional actuator fields that the simulator does not emit | Process/memory-leak/resource-exhaustion diagnoses are unsupported |
| `jitter-errors` | Jitter has a nonnegative floor; integer `10 * degradation / 10000` produces per-sample 0–10 error values; validator only requires a nonnegative integer | No real timing, packet-loss or hardware-fault measurement is established |
| `alert-episodes` | `rules.transition`, `evaluator.evaluate`, acknowledgement SQL and migration 003 implement severity episodes, closure reasons, preserved/repeated acknowledgement and one unresolved episode | No predictions, notifications or identities; proposed AI behavior is not a deployed capability |
| `lifecycle-firmware` | FAILED is absorbing; reset clears state/fault/degradation but not PRNG/clock/device ID; Kafka producer changes run IDs; generated firmware is 1.0.0 | Run ID alone cannot identify reset versus producer restart; firmware update/repair workflows are absent |
| `telemetry-availability` | Five-second intervals, initial tick and 1,200 advances across three devices yield 3,603 samples; inbox is durable and Redis is recoverable | No heartbeat/disconnection diagnosis; text describing planned AI behavior is design-only, not evidence of a working report UI |

Implementation references: [simulator](../simulator/src/simulator.cpp),
[configuration](../simulator/include/device_health/simulator.hpp),
[producer identities](../simulator/src/main.cpp),
[validation](../processing/device_health_ingestion/validation.py),
[alert rules](../processing/device_health_alerts/rules.py),
[evaluation](../processing/device_health_alerts/evaluator.py),
[acknowledgement](../processing/device_health_alerts/store.py),
[inbox](../processing/device_health_ingestion/store.py),
[Redis](../processing/device_health_ingestion/latest.py).
This is a source review, not physical-hardware validation or owner sign-off.

## Explicitly selected excerpts

Only these two original chunks are eligible; there is no search, threshold,
reranking or selection callback in this smoke. Source hashes, tokenization and
stable chunk identities must match. The owner confirms these excerpts for one
development experiment with `--confirm-manual-excerpts`, without changing any
global review status.

1. `alert-episodes`, “What creates an episode”, lines 6–16.
   Chunk `518a1d1191f7c36092729ffe234132fb0783284f7929dc5ea34e8fc32d40a88f`.
   Original text:

   > The `simulator_state_v1` rule maps reported WARNING to alert severity WARNING,
   > CRITICAL to CRITICAL, and FAILED to FAILURE. HEALTHY opens no alert. These are
   > simulator-state episodes, not predicted failures or metric-threshold diagnoses.
   >
   > For the same device, rule and run, repeated identical unhealthy states refresh
   > the existing episode's last evidence and preserve acknowledgement. A severity
   > change, including de-escalation, resolves it as `superseded` and opens a fresh
   > ACTIVE episode. HEALTHY resolves an open episode as `recovered`. A run change
   > closes an open episode as `lifecycle_changed` before applying the new state.

2. `thermal-power`, “What the readings mean”, lines 6–15.
   Chunk `87e11161160de85d2be1fd2aa664b37581f6c110fe8074b1edf380bc3bc00202`.
   Original text:

   > The simulator generates `temperature_c` and `power_draw_w` from the same hidden
   > degradation value, with bounded random noise. Their values can rise together
   > during injected degradation. They are not measurements from physical sensors.
   >
   > Device state is determined by hidden degradation and configured transition/
   > recovery rules. The state machine does not compare temperature or power readings
   > with operational thresholds. A noisy rise in either metric does not independently
   > create an alert or prove a thermal or electrical failure.

## Isolation and acceptance

Use a standalone development script outside the application package. It reuses
the source/evidence/report validators and pinned HTTP client, but never imports
or modifies the automatic gate/adapter or adds a production override.

Phase 1 uses fresh tmpfs PostgreSQL on a unique internal network. Apply existing
migrations and use existing persistence/evaluation, then capture read-only evidence
and close connections. The two hand-authored samples use the simulator's default
WARNING-compatible values at degradation 4000/4020 with zero noise, five seconds
apart. They are not claimed to be actual C++ output or measured physical data.
Save only this synthetic packet locally with mode 0600; remove PostgreSQL/network.

Phase 2 uses Docker's normal bridge solely to reach macOS Ollama through
`host.docker.internal:11434`; it has no database network, credentials or production
volumes. The internal network failed the metadata probe, while the normal bridge
passed. Do not change server binding, enable host networking or expose ports.
The client permits local hosts only, ignores proxies, and checks 0.40.18 plus the
pinned model digest. Internet egress is not blocked by the normal bridge; this is
not an air-gap claim. The smoke performs no pulls/downloads or remote API calls.

Validate the same approved limits (16K context, 2,048 output, 12,000 prompt bytes,
90 seconds, temperature zero) before one opt-in generation. Fail closed on
changed excerpts, invalid packets, missing confirmation, credentials in phase 2,
budget overflow, unavailable/wrong provider, timeout or malformed output. No retry.

Default output contains only validated summary fields. Optional full local report
is exclusively created with mode 0600 and conspicuously labeled development-only,
manual selection, relevance unvalidated and owner review pending. Do not save raw
prompts or raw provider bodies by default. Summary pass means structure,
references/provenance and transport succeeded; semantic grounding still requires
manual review. Review must reject invented readings, long-term trends from two
samples, physical diagnoses, unsupported thresholds, actions and predictions.

The combined Python image is still missing, but is not required for this staged
manual experiment. Reuse the cached backend image for PostgreSQL packet creation,
then the cached retrieval image for tokenizer/source preparation and local HTTP
generation. The latter needs no PostgreSQL driver or embedding inference. The
combined image remains an optional owner-run build for later automatic
composition; its build/import compatibility is not claimed here. No model weights
enter any build. Real-report checks remain pending until the owner runs them.

The backend Dockerfile copies the standalone tool only into its test stage so
the new tests remain importable in CI. Production runtime COPY/ENTRYPOINT stay
unchanged; no application module imports this development tool.

## Owner-run commands

From the repository root, keep the already installed native Ollama server
running with its reviewed loopback/cloud-disabled settings. Do not pull models
again. The two cached test images and prepared tokenizer are sufficient:

```sh
export MINILM_MODEL_DIR="$PWD/build/knowledge/models/1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
export AI_MANUAL_RUN_DIR="$PWD/build/ai-investigation/manual-$(date +%Y%m%d-%H%M%S)"
bash scripts/manual-ai-smoke.sh prepare
bash scripts/manual-ai-smoke.sh probe
```

Run the next command only after reading the two selected excerpts above:

```sh
bash scripts/manual-ai-smoke.sh generate --confirm-manual-excerpts --save-report
```

`prepare` prints a packet-check summary and a three-check preparation summary
(one skipped generation check). It creates a private directory (0700) containing
`evidence.json` (0600), removes its database/network, and tests source/packet/budget
without network access. `probe` checks runtime version, exact model digest,
quantization and context capacity using metadata only. `generate` performs one
call and prints four-check success or sanitized failure; counts are development
checks, not pytest case counts. Failure does not print raw provider output.

Without `--confirm-manual-excerpts`, generation fails before reading the packet
or contacting Ollama. Without `--save-report`, no full report is saved. Existing
packet/report files are not overwritten; use a new run directory to repeat.

Explicit local review, in your own terminal only:

```sh
python3 -m json.tool "$AI_MANUAL_RUN_DIR/report.json" | less
```

Verify the development/manual-selection warning, exact A/E/D references and the
limits above. A passing summary is not semantic sign-off. Share only the summary
JSON for troubleshooting, not this file, telemetry or prompts. No report has yet
been generated by the agent.

## Optional combined image (not needed for the staged smoke)

If wanted for later full composition, the owner can run:

```sh
docker build --pull=false -f processing/Dockerfile.investigation \
  -t device-health-ai-investigation:test .
AI_RETRIEVAL_TEST_IMAGE=device-health-ai-investigation:test \
  bash scripts/manual-ai-smoke.sh probe
```

This owner-run build installs the existing 60 combined hash-locked packages;
shared pins agree, with no new dependencies. It performs no model downloads and
copies no model weights or application source. `.dockerignore` excludes `.env`,
Git and ignored build artifacts. Source/tokenizer/packet mounts are explicit at
runtime. The image has not been built or runtime-verified by the agent.

Docker Desktop's documented host-service name is
[`host.docker.internal`](https://docs.docker.com/desktop/features/networking/networking-how-tos/#connect-a-container-to-a-service-on-the-host).
The actual normal-bridge metadata probe passed with the cached retrieval image;
the internal-network probe failed. The staged workflow avoids changing either
database isolation or the Ollama host binding. A failed future probe is a blocker;
do not enable host networking or bind Ollama to all interfaces automatically.

## Actual preparation results (November 27, 2026)

- Source/tokenizer checks selected exactly the two original pinned chunks (163
  and 117 input tokens). Corpus hashes and pending-owner-review status remain
  unchanged; the relevance policy/cutoff/evaluation data were not modified.
- The public preparation script passed against a fresh tmpfs PostgreSQL instance,
  saved only its private synthetic packet, removed PostgreSQL/network and passed
  offline source/budget checks. Full serialized prompt including the development
  notice: **7,878 bytes**, below **12,000**. Generation was skipped.
- The public retrieval-image metadata probe passed in **0.067 seconds**. The
  internal-network probe failed `ai_unavailable`; no binding/configuration change
  was made. Generation without confirmation returned `invalid_request` before
  reading a packet or calling the model.
- **413 backend unit tests passed, 9 optional skips** (2.603 seconds), **28
  PostgreSQL integration tests passed** (1.980 seconds), and **154 offline AI tests
  passed, 1 synthetic-handoff-dependent skip** (8.418 seconds). Earlier prompt
  handoff verification remains recorded; this manual preparation supplies its
  own actual PostgreSQL/budget check. Real relevance regressions use development
  only; held-out cases were not rescored. Ruff passed.
- Fake-provider tests cover output labels/references, explicit confirmation,
  phase-2 credential rejection, changed excerpt pins, wrong lifecycle/device,
  prompt overflow and opt-in private report saving. No real Qwen report, semantic
  grounding result, combined image build or Git mutation is claimed.

## First real attempt: diagnostic limit

The owner reported `ai_invalid_response` after 66.745 seconds on the first real
manual generation attempt. No validated report was saved. The rejected provider
body and temporary summary were not retained, so the exact original validation
failure cannot be recovered from this aggregate. It may be provider truncation,
an invalid envelope/token count, malformed report JSON/schema or source references.
Local metadata still matches Ollama 0.40.18 and advertises thinking capability;
that does not establish whether thinking was active or caused this failure.

Add closed, constant validation-stage categories to local summaries while
retaining the `ai_invalid_response` application error code, original schema,
reference checks, limits and rejection behavior. Never include model text,
Pydantic errors/inputs, offending reference values or exception messages.
Use fake providers to verify stage attribution and canary suppression. Do not
retry the real model or change thinking/output budgets without a confirmed cause.

Implemented diagnostic categories include `ai_invalid_response_provider_output_truncated`,
`ai_invalid_response_provider_envelope`, `ai_invalid_response_provider_token_budget`,
`ai_invalid_response_report_json`, `ai_invalid_response_report_schema` and
`ai_invalid_response_report_references`; body-limit/HTTP/JSON and model-provenance
stages also have fixed categories. Unknown/non-string stages retain the coarse
category. These are local summary diagnostics; the application error code stays
`ai_invalid_response`. No extra response text is retained or exposed.

Focused fake-provider/manual/privacy verification: **117 passed, zero failures
or skips**, in **1.214 seconds**; Ruff passed. Existing schema/reference failures
still reject, including token-limit completion and forged citations. No real LLM
retry occurred. The original cause remains a blocker; generation behavior and
the automatic relevance gate remain unchanged. This is an observability correction,
not a successful real-generation result.
