# AI-assisted incident investigation

Status: architecture approved by the owner on November 26, 2026; Checkpoint 1
documentation committed as `091afa1`. Checkpoint 2A document validation and
chunking are implemented and verified with the real MiniLM tokenizer: 44 focused
tests passed with zero skips using the owner-installed optional runtime.
Checkpoint 2B's local embeddings, JSON index and candidate-retrieval CLI are
implemented and verified: 113 tests passed, including offline six-runbook
retrieval. The earlier owner-run 77-test embedding result remains below.
Checkpoint 3A's read-only PostgreSQL evidence reader is implemented and verified
independently of retrieval/generation; see the evidence-reader section below.
Generation, the endpoint and button do not exist yet. Concrete API fields,
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

### Checkpoint 3A: PostgreSQL evidence reader

Implement the approved database snapshot independently of retrieval/generation.
`EvidenceQueries(dsn).get(alert_id)` uses the existing PostgreSQL connection
settings and alert-column contract, with one REPEATABLE READ, READ ONLY
transaction. It returns only the existing proposed report contract's evidence
subset: `schema_version`, `data_mode`, alert/device/run identity, `alert_status`,
`evidence`, and `sources.alert`/`sources.telemetry`. No report, document retrieval,
generation status, API route or database write is introduced. Use one reader per
capture; its transaction and connection close on success or failure before return.

Validate linked opening/last/closing identities, simulation times and accepted
order, including the rule that resolved last/closing evidence identify the same
event. Stored payload identities/times must match inbox columns and the existing
telemetry validation contract. Next-run closure is permitted only for a resolved
`lifecycle_changed` alert; return its identity with `subsequent_lifecycle`, never
its payload. Keep all captured alert fields in `A001`; opening/closing events
outside the selected window contribute metadata only.

Freeze the cutoff at captured `last_event_id`. Find the last accepted same-device,
same-run row at/before that cutoff, then read the inclusive five-minute simulation
window at/before its anchor order. Read at most 101 rows descending to detect
truncation, keep the newest 100, and assign `E001` onward in ascending accepted
order. Each source includes `event_id`, `ingestion_order` and the exact validated
event under `event`, consistent with existing reading contracts. Serialize UUIDs
and aware timestamps as strings/UTC; retain the original telemetry JSON values.

Reuse `AlertNotFound` for a missing alert and `TransientProcessingError` for the
existing temporary database-failure categories. `EvidenceUnavailable` identifies
missing/inconsistent linked evidence or a missing/inconsistent anchor/window;
an anchor whose full five-minute window cannot be represented by calendar
arithmetic also raises this sanitized error. Preserve the exact five-minute
window rather than clamp its start. Invalid UUID inputs fail before connecting.
Messages are sanitized; no DSNs or payloads are logged. Future API error mapping
remains as proposed below.

Do not invent a minimum-reading or elapsed-coverage threshold here. A single
valid sample returns a factual `reading_count: 1`, without claiming a trend or a
complete investigation. A valid anchor necessarily belongs to its inclusive
window; missing anchor/rows is an availability failure, not a fabricated empty
success. The later composer still handles `insufficient_evidence` when guidance
or report evidence is inadequate. No interpolation or cross-lifecycle fill occurs.

Tests use fakes for validation/errors/resource cleanup and a disposable PostgreSQL
18.6 container/schema for actual ordering, bounds, lifecycle closure, cap,
read-only enforcement and concurrent-update snapshot consistency. Reuse cached
backend test dependencies and the existing optional AI environment. Do not run
the persistent-data demo, change migrations, or rebuild ingestion behavior.
The implementation is in
[`evidence.py`](../processing/device_health_investigation/evidence.py).

Run the isolated evidence checks with Docker running and the existing backend
test/PostgreSQL images cached:

```sh
bash scripts/test-ai-evidence.sh
```

The script uses the local `device-health-kafka-tests:latest` test artifact from
the existing locked backend Dockerfile, with current source mounted read-only.
`AI_EVIDENCE_TEST_IMAGE` can select another existing reviewed tag or immutable
image ID. The PostgreSQL repository digest matches the approved 18.6 image in
`compose.yaml`; the digest-only reference reuses Docker's cached image after
the restart. Nothing is automatically built, pulled or installed. The script
creates its own internal network and tmpfs PostgreSQL container, uses no host
ports or development volumes, and removes only its own resource IDs on exit.

November 27, 2026 verification after the macOS restart: Docker Desktop was started
and the existing Docker 29.9.3 ARM64 daemon/cached images became available.
`scripts/test-ai-evidence.sh` passed dependency consistency, Ruff, **260 backend
unit tests** (five optional-model cases skipped; 46 integration cases deselected)
and **27 PostgreSQL integration tests** (16 new evidence cases plus 11 existing
alert cases). At that verification, the new evidence suite contained 33 unit and
16 integration cases.
All selected integration tests passed, including actual read-only SQL rejection,
concurrent acknowledgement/telemetry updates, and otherwise eligible rows from
another device/previous run. The existing Starlette/httpx test-client deprecation
warning remains; dependency pins were preserved.

The unchanged optional retrieval environment separately passed all **113 AI
tests, zero failures/skips**, including real local MiniLM retrieval. Test runs
used fresh database state and did not run the persistent-data demo or change
application data. Full Kafka/broker-interruption and browser suites were not
rerun for this isolated reader; their earlier results remain historical evidence.

Subsequent approved calendar-boundary correction verification on November 27:
three new unit cases cover underflow at the minimum timestamp, one second below
the first full window, and successful capture at the exact five-minute boundary.
The failures are sanitized `EvidenceUnavailable` errors with rollback/connection
cleanup; the successful case retains the exact five-minute bounds. The latest
run passed **263 backend unit tests** (five optional-model skips, 46 integration
cases deselected), **27 PostgreSQL integration tests** and **113 AI tests**,
plus Ruff and dependency consistency. There are now 36 evidence unit cases and
16 evidence integration cases. The existing Starlette/httpx warning remains;
the earlier results above are preserved. No lifecycle, window, cap, ingestion,
acknowledgement or schema behavior changed.

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

### Checkpoint 2B initial scope: model setup and embedding smoke

Prepare the optional retrieval runtime, verified local model-copy helper and
minimal embedding adapter only. Do not implement an index, search, PostgreSQL
evidence, API/UI integration or Ollama in this increment. The owner performs
package installation/image builds and model preparation manually; the agent
must not build images, install dependencies or download model assets.

The 49-package plan was re-resolved for Python 3.13.18 on Linux ARM64 and AMD64
with identical locks, constrained by existing backend and 2A pins. Direct pins:
Sentence Transformers 6.3.0, CPU PyTorch 2.15.0+cpu, Transformers 5.24.1,
NumPy 2.5.5 and Tokenizers 0.23.3; pytest 9.1.1 and Ruff 0.17.3 remain the
test tools. Use a separate retrieval image and hash-locked requirements;
ingestion/runtime images and existing locks remain unchanged. This is metadata
compatibility evidence, not proof of successful installation or model loading.

`knowledge/model-manifest.json` records the approved model/revision and the 11
existing local files' sizes/SHA-256 values, including safetensors weights and
packaged pooling/normalization configuration. It contains no weights. The
preparation helper dereferences only those cached files into
`build/knowledge/models/<revision>/`, verifies every copy and publishes a complete
directory. It reuses a matching existing destination and rejects incompatible
destinations without deleting or overwriting them. Missing/altered source files
fail explicitly; no Hub client or download fallback is used. This is a manual
single-writer provisioning command. Prepared directories must be self-contained,
contain exactly the manifest files and have no symlinked files/directories.

`MiniLMEncoder(model_dir).encode(texts)` loads only that validated directory using
`local_files_only=True`, `trust_remote_code=False` and the CPU torch backend.
Heavy imports occur only when an encoder is constructed. Use float32 evaluation/
inference mode, batches of 16, two CPU threads and normalized sentence embeddings.
Require the packaged model's 256-token limit and 384-dimensional output. Accept
nonempty lists/tuples of nonblank UTF-8 strings, reject inputs over 256 complete
MiniLM tokens rather than truncating, and verify model-tokenizer input lengths
against the 2A tokenizer before encoding. Return a finite float32 NumPy array
with shape `(number_of_texts, 384)` and unit-length rows within tolerance.
Missing/mismatched assets or runtime dependencies, invalid inputs and failed
encoding have explicit exceptions; never switch hardware/model or return fakes.
Record model/file/runtime provenance in the encoder profile for the later index.

The focused real-model smoke must check dimensions, dtype, finite values, unit
norms, tokenizer compatibility and repeatability on the same CPU runtime
(`rtol=1e-5`, `atol=1e-6`). This is tolerance-based reproducibility, not a
cross-platform bitwise or retrieval-quality claim. Default suites can skip this
opt-in smoke; the explicit embedding runner must require the installed image and
prepared assets, run offline/read-only, and fail if the smoke cannot execute.
Runbook owner-review status remains unchanged. The initial runtime verification
below supplements the earlier setup-only results.

### Checkpoint 2B index and retrieval implementation scope

Implement only the approved local JSON index, exact cosine candidate retrieval
and a question-driven CLI. Reuse the installed optional retrieval image, existing
locks and cached model. Do not add packages, download models, or implement
PostgreSQL evidence, Ollama, FastAPI or dashboard changes. Replace the deprecated
dimension accessor with the installed library's `get_embedding_dimension()`;
retain the same 384-dimensional validation.
The real CLI also exposed a logged deprecation for `tokenize()`. Inspection of
the installed 6.3.0 source confirms it forwards directly to `preprocess(inputs=...)`;
use that replacement in the adapter/smoke while retaining full token-ID/length
checks and the existing model profile. No embedding behavior or dependency changes.

The version-1 JSON envelope contains a SHA-256 `index_id` over canonical payload
JSON, corpus/model/tokenizer/chunking fingerprints, the full runtime/model
profile, source document snapshots, exact chunk metadata/text and normalized
384-dimensional vectors. Fingerprint the raw corpus manifest too, so metadata
and review-status changes invalidate reuse. No timestamps enter identity.
Checksums detect corruption, not malicious editing of the trusted local corpus
and index together. On reload, validate envelope/schema/checksum, all vectors,
current manifest/documents, the current encoding profile and freshly reconstructed
chunks; stale, missing or corrupt indexes fail explicitly.

`build_index` validates/reuses an unchanged artifact without encoding. Otherwise,
under a nonblocking advisory `flock` on the adjacent persistent `.lock` file,
rebuild all chunks, recheck the corpus after encoding, write/fsync a temporary
file in the same directory, validate it and publish using `os.replace`. Only
the temporary file is cleaned on failure; preserve any prior index. Lock
contention returns an explicit busy failure; do not wait, delete the lock file
or retry implicitly. This is a local POSIX filesystem contract. Readers load
one immutable in-memory snapshot and require no writer lock.

`load_index(...).search(question, encoder, limit=3)` checks the matching encoder
profile, rejects invalid/oversized queries via the encoder, and returns zero to
three ranked hits with score and original `Chunk` records. Limits must be integers
from one to three. Rank by cosine descending and then chunk ID ascending. Source
identity/version/path, headings, character/line spans and original text remain
inspectable; report-scoped `D...` IDs belong to the later API/report increment.
CLI output explicitly calls hits `candidates` and relevance `uncalibrated`.
There is no score cutoff, abstention classifier or unsupported-query diagnosis.

Freeze six supported query-to-document expectations and one unsupported question
in the real-model tests before inspecting rankings. These are source-derived
smoke checks, not owner-reviewed relevance labels or a held-out accuracy study.
Test creation/reload/no-op reuse, known-vector ranking/ties/limits, corruption,
stale source/profile rejection, invalid vectors, interrupted replacement,
writer contention and unchanged old reader snapshots. Run real six-document
index/reload/search tests offline in temporary directories. Relevance calibration
and unsupported-query abstention remain TBD before report generation.

November 27, 2026 owner-reported initial runtime verification: all 11 cached
model files prepared, retrieval image built, normalized float32 embeddings with
shape `[3, 384]`, **77 tests passed, zero failures**, one FutureWarning from the
old dimension accessor. This is actual owner-run runtime evidence, separate from
the November 26 agent-run setup checks below. Subsequent index/retrieval results
are recorded separately under the CLI verification section.

### Manual embedding setup and smoke

Run these commands from the repository root with Docker running. The first
command uses the host's Python standard library to copy **cached files only**;
it does not install dependencies or contact Hugging Face. A matching prepared
directory is reused. If the cache is incomplete or a hash differs, stop and
review the failure; the script will not download replacements or overwrite an
incompatible destination.

```sh
task_revision=1110a243fdf4706b3f48f1d95db1a4f5529b4d41
python3 -B scripts/prepare-ai-model.py \
  --source "$HOME/.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2/snapshots/$task_revision" \
  --destination "build/knowledge/models/$task_revision"
```

Build the optional, CPU-only dependency image manually. This downloads Python
wheels from PyPI/the official PyTorch CPU index, **not model assets**, and does
not rebuild or change the ingestion environment. It uses the pinned Python
3.13.18 base, wheel-only hash-locked dependencies and `pip check`. Docker's first
build needs internet access and additional disk space for PyTorch and its
numerical dependencies.

```sh
docker build -f processing/Dockerfile.retrieval \
  -t device-health-ai-retrieval:test .
```

Run the checks against the prepared model. The runner requires an existing image;
it never builds or installs anything. It sets explicit model/tokenizer paths,
disables networking, and mounts the repository and model read-only. It checks
dependency consistency, Ruff, the 44 existing 2A cases, provisioning/input/index
unit tests and both real embedding/retrieval smokes. FutureWarnings are errors.
Missing assets or model/runtime failures
must fail this explicit run. No PostgreSQL, Kafka or Redis resources are used.

```sh
MINILM_MODEL_DIR="$PWD/build/knowledge/models/$task_revision" \
  bash scripts/test-ai-embeddings.sh
```

The smoke prints its shape, dtype, norm range, runtime pins and profile ID only
after real encoding checks pass. Successful encoding is not a retrieval-quality
or LLM report test. Use `AI_RETRIEVAL_TEST_IMAGE` to select another reviewed tag
for the same pinned runtime; no runtime dependency/version substitution is made.

November 26 setup verification used the **existing** optional 2A image, without
installing packages, building images or copying the real model: Ruff passed and
the focused suite reported **76 passed, 1 skipped**. This includes the original
44 real-tokenizer 2A cases and 32 new provisioning/input/runtime-guard cases.
The sole skip was the real embedding smoke because no model directory/retrieval
runtime was provisioned. Shell/Python syntax and all 11 cached model hashes also
passed. At that point dependency installation, model loading, encoding, latency
and memory were unverified. The subsequent November 27 runtime/index checks
supersede those installation/encoding gaps; no latency/memory benchmark is claimed.
Earlier 2A results remain historical evidence.

### Retrieval CLI and verification

With the existing image and prepared model, run from the repository root:

```sh
bash scripts/demo-ai-retrieval.sh
# Or supply one quoted question:
bash scripts/demo-ai-retrieval.sh "Is error_count cumulative or can it fall during recovery?"
```

The script prompts once when no question is supplied, then runs `build-index`
and `search` in separate offline containers. It uses the calling user's UID/GID
for the writable derived-index directory, mounts the repository/model read-only,
and mounts only `build/knowledge/` writable. `MINILM_MODEL_DIR` overrides the
default prepared revision path; `AI_INDEX_DIR` selects a different local output
directory, and `AI_RETRIEVAL_TEST_IMAGE` selects an existing reviewed image.
The index and persistent lock file remain local, ignored artifacts. The script
does not build images, install packages, download models or start application
services. A valid existing index is reused; an explicit build repairs/rebuilds
an invalid or stale artifact. `search` alone never rebuilds.

The Python CLI inside the optional runtime also supports:

```sh
python -m device_health_investigation build-index \
  --manifest /workspace/knowledge/manifest.json \
  --model-dir /models/minilm --index /index/index.json
python -m device_health_investigation search \
  --manifest /workspace/knowledge/manifest.json \
  --model-dir /models/minilm --index /index/index.json \
  --question "What does acknowledging an alert change?" --limit 3
```

Those absolute paths are the demo container's mounts, not host paths. Success
prints JSON; failures use the existing stderr error envelope and nonzero exit.
Candidates include rank/cosine score and full original chunk/source metadata;
`relevance: uncalibrated` and the actual corpus review status remain explicit.

November 27, 2026 agent-run verification: the existing optional retrieval image
passed `pip check`, Ruff and **113 tests, zero failures/skips**, with
`FutureWarning` treated as an error. This includes all earlier 77 cases and
36 new cases. The real model indexed **30 chunks from six documents**, reloaded
the same snapshot and found the expected document in the top three for all six
predeclared supported questions. The unsupported battery-maintenance question
returned candidates without any relevance/diagnosis claim. The lightweight 2A
image separately passed **111 tests, 2 skipped** (the real embedding and retrieval
smokes), confirming the unit path needs no heavy embedding runtime.

The shell CLI was also verified with a temporary index outside development data:
the error-count question returned `runbooks/jitter-errors.md` first, with original
text, version and exact character/line locations. Neither deprecated alias was
reported after the replacements. Tests/demo used disabled networking, read-only
repository/model mounts and disposable index storage; no package/image/model or
database changes were made. Runbook hashes and pending owner-review status remain
unchanged. Relevance calibration, held-out evaluation and report abstention
remain pending; six smoke questions are not an accuracy claim.

### Subsequent runtime integration

Metadata-only compatibility review found Python 3.13 builds for macOS ARM64,
Linux ARM64 and Linux x86-64. Actual embedding/index verification above used the
existing Linux ARM64 Docker runtime; other platforms and latency/memory benchmarks
remain unverified. Preserve the existing Python 3.13.18 and backend dependency pins.

| Component | Initial candidate / policy |
| --- | --- |
| Encoder | `sentence-transformers/all-MiniLM-L6-v2`, revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`; 384 dimensions, 256-token limit |
| Python library | Sentence Transformers 6.3.0; optional, separately hash-locked AI requirements constrained by existing backend pins |
| Tensor runtime | PyTorch 2.15.0+cpu for Linux; Transformers 5.24.1 and all 49 dependencies hash-locked for the separate retrieval image; CPU embedding/retrieval smoke verified |
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

These are acceptance gates for the complete feature. Completed document-preparation,
local-retrieval and PostgreSQL-evidence test results are recorded above. Relevance
calibration, generation/API, browser and full LLM demo verification remain pending.

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

Checkpoints 2A/2B supply verified document preparation, local embeddings and
candidate retrieval under `processing/device_health_investigation/`. Checkpoint
3A now implements the approved read-only PostgreSQL evidence reader; generation,
API and the inline dashboard interaction follow later. No job system or broader
persistence layer is required.

Remaining validation items include evidence/retrieval/report composition, Ollama
connectivity, Qwen digest and context/latency/memory behavior, and corpus relevance
calibration. A model substitution or material contract change returns to owner
review. README commands and verification results are added only after they exist;
3A authorizes no Ollama/model installs, API/UI work or Git writes.
