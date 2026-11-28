# Local investigation generation: Checkpoint 3B

Status: report composition, validation and the local HTTP adapter are implemented
and verified with fake providers; real generation is not verified. Checkpoint
3A is committed and pushed at `798621d`. The owner has now installed native
Ollama 0.40.18 and the pinned Qwen3 model, verified its digest and reported simple
responses of approximately 12.19 seconds cold / 0.67 seconds warm. Local metadata
matches the pins; these are not evidence-backed report results. No software/model
downloads have been performed by the agent.

Use the [approved investigation contract](ai-investigation-design.md) and its
server-owned evidence/source objects. This increment adds no HTTP API, frontend,
ingestion changes, migrations, durable report storage or predictive-model training.
The terminal demo can save a local debug report only by explicit opt-in.
The owner approved 16,384 context tokens, 2,048 output tokens, 12,000 prompt bytes,
90 seconds, temperature zero, one generation and up to three candidates. Relevance
selection must pass development/held-out validation before it is enabled. A passing
fake-provider test does not establish actual Qwen runtime speed or grounding.

A separate [development-only manual smoke](ai-manual-smoke.md) is now prepared
for explicitly reviewed, pinned excerpts and a disposable PostgreSQL packet.
It does not enable automatic relevance or add a bypass to the application.
The staged workflow reuses cached images; a combined image build is optional.
The owner's first real attempt failed with `ai_invalid_response`; successful
report generation and full-report review remain pending. See the
[pause handoff](ai-investigation-handoff.md) before resuming after December 2.

## Manual installation on this Mac

These commands are for the owner to run, not an automatic installer. They use
the pinned official Ollama 0.40.18 macOS application archive, verified against the
release's published SHA-256. The application is unpacked into a user-owned
directory; no Homebrew upgrade or Python package installation is required.
Run from the repository root:

```sh
mkdir -p build/downloads
curl -fL --retry 2 \
  https://github.com/ollama/ollama/releases/download/v0.40.18/Ollama-darwin.zip \
  -o build/downloads/Ollama-0.40.18-darwin.zip
printf '%s\n' '1d990f4a8a76985c9defaa9a6ddd007556d117fd8ed586d7e9cbf25a6e9a4a23  build/downloads/Ollama-0.40.18-darwin.zip' \
  | shasum -a 256 -c -
mkdir -p "$HOME/Applications/device-health-ollama-0.40.18"
ditto -x -k build/downloads/Ollama-0.40.18-darwin.zip \
  "$HOME/Applications/device-health-ollama-0.40.18"
```

In terminal 1, keep the native server running for Metal acceleration. It listens
only on this machine's loopback interface; do not expose it to the public network.

```sh
task_ollama_bin="$HOME/Applications/device-health-ollama-0.40.18/Ollama.app/Contents/Resources/ollama"
OLLAMA_NO_CLOUD=1 OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NUM_PARALLEL=1 \
  "$task_ollama_bin" serve
```

In terminal 2, download only the previously selected model, about 2.5 GB:

```sh
task_ollama_bin="$HOME/Applications/device-health-ollama-0.40.18/Ollama.app/Contents/Resources/ollama"
"$task_ollama_bin" pull qwen3:4b-instruct-2507-q4_K_M
curl -fsS http://127.0.0.1:11434/api/version
curl -fsS http://127.0.0.1:11434/api/tags
"$task_ollama_bin" show qwen3:4b-instruct-2507-q4_K_M
```

Record the exact matching model's full `digest` from `/api/tags`; the model tag
alone is mutable. Confirm `show` reports the selected Qwen3 4B/Q4_K_M model.
Runtime version must be 0.40.18; review differences before
changing the pin. Keep the model cached locally and do not commit weights. Native
loopback and later Docker-to-host connectivity need actual verification after
installation; no LAN binding or Docker settings change has been authorized here.

Official sources: [versioned release and assets](https://github.com/ollama/ollama/releases/tag/v0.40.18),
[release metadata/checksums](https://api.github.com/repos/ollama/ollama/releases/tags/v0.40.18),
[selected model](https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M),
[structured outputs](https://docs.ollama.com/capabilities/structured-outputs),
[chat API](https://docs.ollama.com/api/chat), [local runtime settings](https://docs.ollama.com/faq).

## Optional combined Python runtime

The existing backend image supplies psycopg/Pydantic; the separate retrieval
image supplies MiniLM. Full composition needs both. An optional standalone
Dockerfile reuses the two existing hash locks, with no new version pins and no
change to ingestion or the original images. Its build has **not** been run.
The owner can build it manually after reviewing the setup:

```sh
docker build -f processing/Dockerfile.investigation \
  -t device-health-ai-investigation:test .
```

This installs the existing locked Python packages in a new image, not Ollama or
Qwen. The terminal script below supplies a fresh disposable PostgreSQL instance
and explicit prepared MiniLM mount. The image remains absent locally and the
relevance gate failed validation; do not install/build anything automatically.
Native loopback reachability from Docker must also be checked. Do not
change Ollama's LAN binding to work around a failed connectivity check.

## Current adapter behavior and limits

`InvestigationAdapter` takes the existing evidence reader, validated index,
encoder, Ollama provider, explicit `GenerationLimits` and an explicit reviewed
guidance-selection callable. It closes database work before retrieval/generation,
holds process-wide nonblocking admission throughout the request, and returns
server-owned `A001`/`E...`/`D...` sources and provenance. The selection callable
can only filter the captured candidates. The gate derives its threshold from
development questions alone, freezes it, and checks separate held-out questions
only if development passes. The original development failure was corrected by a
narrow read-only scope guard. Policy 2 passes development but failed its single
held-out run; selection remains disabled. No guessed cutoff or fallback is used.
No guidance means `insufficient_evidence` with no provider request; provider
failures remain errors. No report is saved and no action is executed.

Provider output is limited to eight statements per section, 1,200 characters per
statement, eight references per statement and ten provider-authored limitations.
Required server limitations about simulation, engineer review, pending runbook
review, sparse evidence and truncation are then appended as applicable. JSON and
citation checks cannot establish that every generated claim follows from its
sources. Actual Qwen grounding and adversarial output review remain pending;
the adapter must not be described as guaranteeing factual diagnoses.

The owner has completed native runtime/model installation and simple responses.
Combined image provisioning, Docker-to-host connectivity, relevance validation,
actual report grounding/latency/memory checks remain outstanding. All six
runbooks and the source-derived evaluation labels remain pending owner review.

## Summary-only verification and disposable terminal demo

From the repository root, with the existing cached backend/retrieval images:

```sh
export MINILM_MODEL_DIR="$PWD/build/knowledge/models/1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
bash scripts/test-ai-investigation.sh
```

Four JSON summaries appear in order: backend tests, isolated PostgreSQL tests,
offline AI tests, and relevance evaluation. Each uses only status, aggregate
counts, total seconds and fixed error categories. Test/demo child stdout/stderr
is suppressed, and summaries are validated before printing and again at the
outer Docker boundary. Canary tests cover malicious output and extra fields.
This validates the described summary path; it is not a claim that arbitrary
dependency output or local artifacts are secret-free. Previous scripts retain
their historical output behavior; use this new entry point for summary-only AI
verification.

The command exits **1** at relevance evaluation. The original result was
**12 development checks passed, one failed; 13 held-out checks were unscored**.
After the documented policy-2 scope correction, development passes **13/13**, but
the one held-out run passed **11/13**, with two failures. The source-derived
26-question evaluation remains unchanged. Automatic generation remains disabled;
the adapter returns `insufficient_evidence` without
calling Ollama when no guidance is accepted. Operational/provider failures
remain errors.

### Relevance-blocker diagnosis

The failing development question is “What command repairs the device firmware
automatically?” Its expected result remains no accepted guidance. Initial
development cutoff: **0.48011912149223085**, set by the valid question “Does an old
simulation timestamp prove the device is disconnected?” The actual candidates
are all from `runbooks/lifecycle-firmware.md`:

| Rank | Lines | Section | Cosine | Initially selected |
| --- | --- | --- | --- | --- |
| 1 | 29–36 | Limits | 0.6364894273640975 | Yes |
| 2 | 18–27 | Investigation checks | 0.6040028097435218 | Yes |
| 3 | 1–4 | Document introduction | 0.5837521896606158 | Yes |

Stable chunk IDs, in rank order:

- `a4987002f56f87325b2fb487eb5503dfa1ec9afe4cd151b2324dadfecff0c907`
- `93e5aa5116d0ef47ed793b060671a138e79a1ec9952fea5f9dc7f7d0417b22b5`
- `033c4179b35ab97afc186456037c48de295f10c2df582e9560e4c3736c3c7d80`

The first chunk explicitly says firmware-update workflows and repair history
are not implemented. Retrieval found topical text, but cosine alone cannot tell
that it does not supply the requested repair command. The content and unsupported
label are correct; the policy conflated topical similarity with answerability.
Raising the cutoff above the strongest incorrect acceptance would reject the
supported 0.480119 case.

The minimal correction enforces the existing read-only scope for explicit
remediation-command/script requests before accepting candidates. It changes no
label or document, introduces no model/dependency, and does not lower the cutoff.
It is a narrow guard, not a complete semantic safety classifier. Development and
runtime use the same rule. Policy 2 passed all 13 development cases without
changing the cutoff or data. The real-model regression now evaluates development
only, so regression runs do not repeatedly inspect held-out scores.

The finalized policy, dataset/index fingerprints and policy source hash were
frozen before one held-out run. It passed 11 cases and failed two in 3.370 seconds:

| Held-out topic | Result |
| --- | --- |
| Physical-overheating claim | Pass: thermal guidance |
| CPU/memory comparison | Pass: CPU/memory guidance |
| Sum successive error counts | Fail: correct source ranked first but below cutoff |
| Acknowledgement versus health | Pass: alert guidance |
| Next-run closure versus original readings | Fail: an additional thermal source is outside the label |
| Five-minute coverage gaps | Pass: coverage guidance |
| Generated CRITICAL investigation query | Pass: in-scope candidates |
| Purchase replacement power supply | Pass: abstain |
| Automatic CPU restart threshold | Pass: abstain |
| Battery-voltage diagnosis | Pass: abstain |
| Physical disk remaining life | Pass: abstain |
| Command to clear alerts/fix hardware | Pass: scope rejection |
| Football question | Pass: abstain |

Failure details (candidate-rule selections before global gate disablement):

- “Can I total successive error_count samples to estimate all errors?” expects
  `jitter-errors`. The top correct chunk (`da293b2ad4992f0fc46df43e718c47e3f743df9bc7d725b7b2db3345e3f45407`,
  lines 6–17) scores **0.35276493876953824** and is rejected. Other candidates:
  `cpu-memory` **0.2712326923815592**, `jitter-errors` **0.25771400582748666**.
- “Can the next run closing an alert provide measurements for its original
  lifecycle?” allows `alert-episodes` and `lifecycle-firmware`. The rule accepts
  those at **0.6157387865695577** and **0.5310762544351016**, plus `thermal-power`
  at **0.5014121688242127** (chunk
  `87187697e6c7e50f6c144eb56c4b76221136d0d84e54b145c46e54bbfc98227f`, lines
  17–24). The thermal chunk also warns about lifecycle boundaries; the document
  label may be incomplete. It was not changed after seeing this failure.

Runtime selection accepts **nothing** while either held-out check fails. No
post-held-out policy/threshold tuning or corpus/label edits were performed.
Next review should address paraphrase coverage and label granularity, retain
these results as historical evidence, and define a fresh held-out set for any
new policy. Do not treat these 13 now-inspected cases as an untouched holdout.

The preparation command (no generation) is:

```sh
bash scripts/demo-ai-investigation.sh
```

It requires the optional combined image to exist already. It currently returns
`missing_runtime` before creating a database because that image is absent.
When provisioned, it creates a unique internal Docker network and fresh tmpfs
PostgreSQL database, applies the existing migrations and persists two synthetic
WARNING readings through the existing inbox/evaluator. It captures the alert
read-only and closes the connection before retrieval. It checks the full prompt
budget without trimming evidence. A failed gate blocks the workflow. It has no
development-volume mounts or PostgreSQL host ports and cleans up its own resources.

For later use only after the gate passes and connectivity is verified:

```sh
bash scripts/demo-ai-investigation.sh --generate
# Explicitly save the full local report, never print it:
bash scripts/demo-ai-investigation.sh --generate --save-report
```

By default no report is printed or saved. Explicit saving creates
`build/ai-investigation/reports/report.json` with mode 0600 and refuses to overwrite
an existing file. This ignored local debug artifact is not report persistence in
the application. The generation command still enforces the gate and pinned
runtime/model; there is no force/bypass flag.

## Verification without installing Ollama

With the existing cached backend test image, run from the repository root:

```sh
bash scripts/test-ai-evidence.sh
```

On November 27, 2026 this passed **322 backend unit tests, 5 skipped, 46
deselected**, including **59 new report/provider cases**, and **27 PostgreSQL
integration tests**. The optional offline MiniLM suite separately passed **113
tests, zero failures/skips**. Ruff and dependency consistency passed. PostgreSQL
used fresh tmpfs containers; the provider tests used only fake responses and
in-process loopback HTTP servers. No development data or model downloads were
required. These results do not verify actual Qwen output, native/Docker
connectivity, semantic entailment or the optional combined image build.
