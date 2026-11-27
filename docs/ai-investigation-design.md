# AI-assisted incident investigation

Status: architecture approved by the owner on November 26, 2026; Checkpoint 1
documentation committed as `091afa1`. Checkpoint 2A document validation and
chunking are implemented and verified with the real MiniLM tokenizer: 44 focused
tests passed with zero skips using the owner-installed optional runtime.
Embeddings, ranked retrieval, generation,
the endpoint and button described below do not exist yet. Concrete API fields,
error codes and configuration defaults remain the design for a later increment.
Baseline: `main` / `feat/ai-investigation` at `2b919b7`, after alerts PR #3.

This contract replaces the older external retrieval-only drafts as the proposed
implementation reference. See [ADR-008](adr/ADR-008-local-ai-investigation.md),
[alert contracts](alerts-design.md) and the
[documentation-first workflow](development-standards.md#documentation-first-sdlc).

## Requirements and boundaries

Help an engineer investigate one existing alert using collected device evidence
and synthetic troubleshooting guidance. Explanations must separate observations,
possible explanations, suggested checks and limitations, with inspectable source
references. ACTIVE, ACKNOWLEDGED and RESOLVED alerts are eligible.

- Local-first: MiniLM semantic retrieval and Ollama generation; no paid APIs,
  cloud inference, training, web search, uploaded documents or remediation tools.
- PostgreSQL remains authoritative. Reports do not write telemetry, alerts,
  acknowledgements, Redis or report history; no migration is required.
- Return a transient report beneath the selected alert. A full browser reload
  discards it; another click generates a new snapshot rather than a saved report.
- Preserve existing endpoints, ingestion, alert decisions and acknowledgement.
  Missing AI assets must not break ordinary API startup, health checks or views.
- Label simulation evidence and AI assistance. No failure probabilities, risk
  scores, guaranteed diagnoses or predictive-ML completion claims.

## Request flow and evidence snapshot

1. The engineer clicks **Get AI Insights** on an alert. A Next.js Server Action
   sends only its alert ID to FastAPI; browsers never contact stores or Ollama.
2. FastAPI validates the ID and admits at most one investigation in the supported
   single-worker API process. Another concurrent request receives an explicit
   busy response; there is no queue, background job or automatic retry.
3. In one PostgreSQL REPEATABLE READ, READ ONLY transaction, load the alert and
   resolve its linked evidence. Freeze the cutoff at the inbox ingestion order
   of `last_event_id`; never use the current fleet/device reading as the cutoff.
4. Among accepted rows for that exact `device_id` and alert `run_id`, at or
   before that cutoff, choose the greatest ingestion order as the anchor. Select
   rows in the inclusive simulation-time range [anchor time minus five minutes,
   anchor time], at or before the anchor order. Keep the newest 100 by ingestion
   order and present them in ascending accepted order. Record whether eligible
   rows were omitted by the cap. Do not interpolate, fill gaps or invent readings.
5. Validate linked opening evidence belongs to the alert's device and run. A
   `lifecycle_changed` closing event may belong to the next run: retain its
   identity/reason in the server-owned `A001` alert source, label it as subsequent
   lifecycle evidence, exclude its payload from the telemetry window, and anchor
   to the last eligible old-run event. Other
   inconsistent or missing linked evidence is an explicit availability failure.
   Opening/closing payloads outside the window are not added beyond the cap.
6. Copy the bounded evidence into memory and close the transaction/connection
   before embedding, retrieval or generation. No row locks are taken for AI.
7. Build a bounded retrieval query from the alert and observed telemetry; retrieve
   up to three relevant chunks from the validated local index.
8. Give Ollama only the evidence, retrieved guidance and report schema. Validate
   the returned structure and every source reference before returning it.
9. Display the report, source excerpts and snapshot provenance beneath the alert.
   A failure leaves existing alert controls usable.

The anchor and window use simulation time. `generated_at` and timeout measurements
use wall-clock time. Accepted order, not cross-run timestamps, bounds the episode.
An alert can change after the snapshot; the result describes the captured status,
not a live claim about the device.

## Corpus, chunking and retrieval

The only ingestion inputs are the six UTF-8 Markdown files allowlisted by
[the corpus manifest](../knowledge/manifest.json). Paths are relative to
`knowledge/`; each entry supplies `document_id`, `title`, `path` and raw-byte
`sha256` (the document version). `implementation_refs` are repository-root-relative
review metadata, not extra documents to ingest. The manifest records baseline
and review status separately; content hashes do not imply owner approval.
Reject duplicate IDs, missing files, hash mismatches,
non-UTF-8 text, traversal and symlink escapes. No recursive repository ingestion.

Use the packaged MiniLM tokenizer/pooling with heading-aware chunks: target 192
total input tokens, overlap up to 32 body tokens, hard maximum 256 tokens including
heading/title prefixes and special tokens. Oversized queries fail explicitly;
never rely on silent tokenizer truncation. Preserve exact original text, document
SHA-256, heading path, character offsets and one-based inclusive line spans.

Encode documents and queries using the same immutable model/runtime profile,
CPU float32 inference and L2 normalization. Store 384-dimensional finite vectors
and source snapshots in `build/knowledge/index.json`, already ignored by Git.
Use exact cosine ranking; deterministic chunk-ID tie breaks; no vector database,
reranker, retrieval framework or keyword fallback.

Return at most three chunks. Calibrate relevance using labeled development cases,
then freeze the selection rule before evaluating untouched cases. Similarity is
not diagnostic confidence; do not invent a universal score cutoff. Until that
rule is verified, CLI results are candidates, not evidence of relevance. Report
generation must return `insufficient_evidence` when no relevant guidance remains.

An unchanged corpus/profile can reuse its validated index. Otherwise, fully
rebuild this six-document index. A model, tokenizer, chunker, normalization or
encoding-runtime change invalidates vectors and relevance calibration. Validate
the replacement and publish atomically under a single-writer lock; retain the
old artifact on failure. Readers use one immutable snapshot. Missing, corrupt
or incompatible assets fail explicitly; never publish partial or fake vectors.

## Local runtime and dependencies

### Checkpoint 2A implementation scope

Implement only manifest/document validation and chunk preparation. The reviewed
manifest is the allowlist/trust root: validate its schema, required metadata,
unique IDs/paths, raw-byte SHA-256 hashes and UTF-8 documents before producing any
chunks. Reject absolute/traversing paths, symlink escapes, malformed metadata,
missing/altered files and title mismatches. Unlisted files are never read or
accepted as chunk sources; implementation references are metadata only.

Keep original text unchanged, including internal newlines. Split at Markdown
heading boundaries (not heading-like lines inside fenced code). Short sections
may stay below 192 tokens; overlap stays inside a section. For longer sections,
target 192 total MiniLM input tokens with up to 32 body-token overlap and forward
progress. Count the complete title/heading/body input plus special tokens, and
validate every result against the 256-token maximum. Do not reconstruct source
text by decoding token IDs or silently truncate an oversized input.

Each chunk records document ID/version/path/title, heading path, exact original
text, zero-based half-open character span, one-based inclusive line span, complete
model input and token count. Its stable SHA-256 ID includes source identity/span,
input hash and the versioned chunking/tokenizer profile, without wall-clock data.

Use `tokenizers==0.23.3` to load only the approved MiniLM revision's serialized
tokenizer. Verify its asset checksum, disable the asset's saved 128-token
truncation/padding, and explicitly enforce the model's 256-token limit. No Torch,
Sentence Transformers, embeddings or model weights are required for this step.
Tokenizer assets are explicit local inputs; no code or test downloads them.
The currently cached approved tokenizer can be mounted read-only for verification.

Keep tokenizer/test dependencies in a separate hash-locked requirements set and
optional Python 3.13.18 test image, constrained by the existing backend pins.
Existing ingestion/runtime locks and images retain their dependencies. The
ordinary backend test image may copy the dependency-free investigation package
in its test stage; real-tokenizer cases skip explicitly when optional assets or
the tokenizer library are absent. Install/provision only after owner authorization.

Expose `python -m device_health_investigation validate --manifest <path>` and
`python -m device_health_investigation chunk --manifest <path> --tokenizer <tokenizer.json>`.
Both emit JSON to stdout; validation does not need tokenizer dependencies. Invalid
corpus/configuration exits 2; missing/incompatible tokenizer dependencies/assets
exit 1. Preserve the manifest's pending-owner-review status in both outputs.
No index, embeddings or other AI application functionality is implemented in 2A.

The optional tools image and runner are prepared; installation is owner-controlled:

```sh
docker build -f processing/Dockerfile.chunking -t device-health-ai-chunking:test .
MINILM_TOKENIZER_PATH=/absolute/path/to/approved/tokenizer.json bash scripts/test-ai-chunking.sh
```

The runner requires an already-built image and existing asset, then uses read-only
mounts, disposable temporary directories and no network. It never builds images,
installs packages or downloads assets automatically. The `validate`/`chunk` CLI
runs from `processing/` with this module on the Python path; for example, inside
the tools container use `--manifest /workspace/knowledge/manifest.json` and
`--tokenizer /models/tokenizer.json`. Chunk JSON includes the original review
status, tokenizer/chunking profiles and complete source metadata; it is not a
vector index or retrieval result.

Local verification on November 26, 2026: Ruff passed; focused tests passed
41 cases with three explicit real-tokenizer skips. The backend unit regression
passed 160 cases with the same three skips and 30 integration cases deselected.
The actual six-document validation CLI passed and retained pending owner review.
The cached tokenizer matched upstream Git blob
`cb202bfe2e3c98645018a6d12f182a434c9d3e02` and SHA-256
`be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037`.
The agent installed no dependencies or models. The optional image was unavailable
at that earlier checkpoint, so actual MiniLM chunking was not yet verified.
A pre-existing non-fatal Starlette/httpx deprecation warning remained in the
backend unit run.

Subsequent verification on November 26, 2026, after the owner manually built the
optional tokenizer image: `scripts/test-ai-chunking.sh` passed Ruff and all 44
focused tests, with zero failures and zero skips. The agent independently reran
the same offline checks successfully. This includes real MiniLM token counting
without saved truncation/padding, Unicode/subword spans and overlap, and repeated
CLI chunking of all six actual runbooks. Repository/model inputs were mounted
read-only; no assets were downloaded during verification. The runbooks and
manifest remain `source_checked_pending_owner_review`. These results complete
2A verification and supplement, rather than replace, the earlier skipped-test
record. They do not verify embeddings, generation or ranked retrieval.

For the later embedding runtime, metadata-only compatibility review found Python
3.13 builds for macOS ARM64, Linux ARM64 and Linux x86-64. No embedding-runtime
installation, inference, latency or memory result is claimed. Preserve the
existing Python 3.13.18 and backend dependency pins.

| Component | Initial candidate / policy |
| --- | --- |
| Encoder | `sentence-transformers/all-MiniLM-L6-v2`, revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`; 384 dimensions, 256-token limit |
| Python library | Sentence Transformers 6.3.0; optional, separately hash-locked AI requirements constrained by existing backend pins |
| Tensor runtime | PyTorch 2.15.0 CPU wheel for Linux; Transformers 5.x and numerical/tokenizer dependencies require final compatible transitive pins |
| Generation | Ollama 0.40.18 with `qwen3:4b-instruct-2507-q4_K_M`; candidate pending actual runtime testing and full model-digest recording |
| Packaging | Optional AI API build target; leave consumer, migrations and ordinary API image free of the heavy runtime |
| Local serving | Prefer native macOS Ollama for Metal; verify Docker API connectivity without exposing Ollama publicly; one API worker and Ollama parallelism one |
| Provisioning | Separately authorized one-time downloads; no weights or caches committed |
| Normal execution | Explicit local MiniLM path, `local_files_only=True`, `trust_remote_code=False`, `HF_HUB_OFFLINE=1`; disable Hub telemetry and Ollama cloud features |

No Ollama SDK, LangChain, vector database or new frontend dependency is needed.
Use ordinary HTTP and existing Pydantic validation. Load the encoder lazily for
investigation and reuse it; never import/load it during consumer startup or
ordinary health/read requests. Models and generated assets stay under ignored
build/cache locations. Record package locks, model revision/digest, index ID,
prompt version and applicable licenses/notices; do not promise bitwise generation
reproducibility across machines.

MiniLM's model card and Qwen's upstream card list Apache-2.0; Ollama uses MIT.
These model/library licenses do not assign a license to the authored runbooks.

Official references: [MiniLM](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2),
[Sentence Transformers 6.3.0](https://pypi.org/project/sentence-transformers/6.3.0/),
[CPU PyTorch wheels](https://download.pytorch.org/whl/cpu/torch/),
[Ollama release](https://github.com/ollama/ollama/releases/tag/v0.40.18),
[Qwen candidate](https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M),
[Qwen license](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507),
[Ollama license](https://github.com/ollama/ollama/blob/main/LICENSE),
[local serving/Metal](https://docs.ollama.com/faq) and
[structured outputs](https://docs.ollama.com/capabilities/structured-outputs).

## Proposed API and report contract

`POST /api/v1/alerts/{alert_id}/investigation`, UUID path parameter, no request
body. Clients cannot supply SQL, evidence, source paths, prompts or model names.
No streaming or report-history endpoint is introduced. Existing local access
policy and same-origin Server Actions remain; this does not authorize hosting.

A 200 response contains these fields; it is not persisted:

| Field | Contract |
| --- | --- |
| `schema_version`, `data_mode`, `status` | `1`, `simulated`, and `complete` or `insufficient_evidence` |
| `alert_id`, `device_id`, `run_id`, `alert_status` | Identity/status captured in the database snapshot |
| `evidence` | `window_start`, `window_end`, `anchor_event_id`, `cutoff_ingestion_order`, `reading_count` (0–100), `truncated` |
| `report` | `observations`, `possible_explanations`, `suggested_checks`: arrays of `{text, source_refs}`; `limitations`: string array |
| `sources.alert` | One server-owned object with `source_id: "A001"`, captured `snapshot`, and opening/last/closing evidence identities as defined below |
| `sources.telemetry` | Server-assigned `source_id` (`E001`-style), event ID, ingestion order and exact selected event payload from the alert's device/run; at most 100 |
| `sources.documents` | Server-assigned `source_id` (`D001`-style), document ID/version, chunk ID, title, relative path, heading/span and exact source text; at most three |
| `provenance` | Wall-clock `generated_at`, index/profile ID, prompt version, model tag and provisioned digest; generation fields nullable when no LLM call occurred |

`sources.alert.snapshot` contains the existing alert fields captured in the same
database snapshot: `alert_id`, `alert_order`, `device_id`, `run_id`, `rule_id`,
`source`, `severity`, `status`, `message`, opening/last/resolved event IDs and
simulation times, `resolution_reason`, and created/updated/acknowledged/resolved
wall-clock timestamps. Their names and nullability match the existing alert
contract. Top-level identity and `alert_status` must match this captured object;
no later live alert lookup replaces it.

`sources.alert.opening_evidence` and `last_evidence` are required identity objects;
`closing_evidence` is null while unresolved and identifies `resolved_event_id`
when resolved. Each identity contains `event_id`, `device_id`, `run_id`,
`event_time` (UTC simulation time), `ingestion_order` and `lifecycle_relation`:

- `alert_lifecycle`: the event matches the alert's device and opening `run_id`.
  Opening evidence always has this relation.
- `subsequent_lifecycle`: only permitted for the last/closing evidence of a
  RESOLVED `lifecycle_changed` alert, with the same device and a different run ID.
  Label the relation from the accepted lifecycle boundary, not timestamp order;
  the new run's simulation clock can restart. For a resolved alert, last and
  closing identities must identify the same closing event.

These identities contain no telemetry payload or metrics. Linked opening/closing
events outside the five-minute window remain metadata in `A001`; they do not add
readings beyond the 100-reading cap. Next-run closing telemetry never appears in
`sources.telemetry` or the original run's metric context. Claims about alert
severity/status or a lifecycle-change closure cite `A001`; metric observations
cite the selected `E...` sources and troubleshooting guidance cites `D...` sources.

The server constructs all three source categories from the captured evidence and
retrieval snapshot. The LLM may only reference `A001` and the `E...`/`D...` IDs
actually supplied; it cannot create or alter source objects. Unknown IDs or
inconsistent source identities are rejected.
Every statement requires at least one reference. Possible explanations must be
labeled hypotheses and grounded in supplied sources. Verify membership and
source integrity, not just JSON syntax. That verification does not prove that a
claim follows from its citation; relevance/grounding needs evaluation too.
Render text safely, without model-authored HTML or arbitrary outbound links.

For insufficient evidence, return empty statement arrays and a clear limitation;
retain any valid collected evidence/provenance. Do not call the LLM or manufacture
a diagnosis. Provider failures are errors, not insufficient-evidence successes.

## Proposed failure and timeout handling

Keep the existing `{error: {code, message}}` envelope. Add endpoint-specific
responses without changing existing storage or acknowledgement error semantics.

| HTTP | Code | Meaning |
| --- | --- | --- |
| 404 | `not_found` | Alert does not exist |
| 422 | `invalid_request` | Invalid identifier/request |
| 503 | `service_unavailable` | Existing durable-storage failure behavior |
| 503 | `ai_evidence_unavailable` | Linked evidence is inconsistent or unavailable |
| 503 | `ai_unavailable` | Missing/incompatible index, encoder, local model or Ollama |
| 503 | `ai_busy` | Another investigation occupies the single generation slot |
| 504 | `ai_timeout` | Investigation generation exceeded its configured timeout |
| 502 | `ai_invalid_response` | Malformed/truncated output, invalid schema or unknown source references |
| 500 | `internal_error` | Existing sanitized unexpected-failure behavior |

Proposed `INVESTIGATION_TIMEOUT_SECONDS` default: 90 seconds for the generation
HTTP call. Use a separate investigation fetch timeout derived from that setting
with 15 seconds of transport/preparation headroom; ordinary eight-second reads
and acknowledgement remain unchanged. Bound encoder inputs, prompt size and
output length separately; verify the selected evidence fits the configured LLM
context without silent truncation. Initial context/output budgets are runtime
tuning items, not measured guarantees.

Release database resources before waiting on the model. Hold admission while the
actual underlying request is active; do not release it just because a browser
disconnects. Close upstream requests on timeout and test cancellation/recovery.
Ollama parallelism one is an additional runtime guard, not a distributed job lock.
Do not retry generation automatically, silently switch models, or hide errors
behind mock output. Logs contain sanitized failure types, not telemetry, prompts
or raw provider responses. No report contents are retained in application logs.

UI states: idle button; pending/disabled for that alert; completed report;
insufficient evidence; and explicit retryable failure/busy/timeout. The engineer
may retry manually. No report is generated during ordinary page loading or
automatically when acknowledgement changes.

## Acceptance criteria and next increment

These are future verification gates, not tests already run:

| Area | Required evidence |
| --- | --- |
| Corpus | Exactly six manifest files; IDs/paths/hashes valid; each factual claim traceable to the baseline implementation |
| Retrieval | Exact source spans, token budgets, deterministic ranking/ties, restart loading, atomic rebuild and profile mismatch tested |
| Real embeddings | Explicitly provisioned MiniLM produces normalized 384-dimensional vectors offline and retrieves relevant top-three guidance for reviewed cases |
| Relevance | Labeled supported/unsupported cases; frozen development selection rule; untouched cases reviewed without tuning on their labels |
| PostgreSQL | Same-device/run five-minute window, 100-row cap, accepted-order cutoff, captured `A001` identity/status/evidence, explicitly labeled cross-run closure and concurrent updates tested; no writes; transaction closed before generation |
| Generation/API | Valid `A001`/telemetry/document references; next-run metrics excluded; insufficient guidance avoids LLM; missing assets, busy, timeout and invalid output return the specified errors without affecting existing APIs |
| Browser | Existing alert → Get AI Insights → pending → referenced inline report; unavailable/insufficient/retry cases; acknowledgement still works |
| Local demo | Real existing alert and PostgreSQL evidence, real MiniLM retrieval and real Qwen generation; record actual versions, latency and resource observations |
| Regression | Relevant isolated backend/dashboard suites pass; no changes to ingestion or alert/acknowledgement behavior |

Checkpoint 2A supplies verified manifest loading and chunk preparation under
`processing/device_health_investigation/`. The next separately authorized coding
increment adds
local embeddings, a file index and ranked retrieval/evaluation. Evidence selection,
generation/API and the inline dashboard interaction follow later. No job system
or broader persistence layer is required.

Remaining validation items are the final transitive hash lock, actual model
loading/connectivity, Qwen digest and context/latency/memory behavior, and corpus
relevance calibration. A model substitution or material contract change returns
to owner review. README commands and verification results are added only after
they exist; this checkpoint authorizes no installs, model downloads or Git writes.
