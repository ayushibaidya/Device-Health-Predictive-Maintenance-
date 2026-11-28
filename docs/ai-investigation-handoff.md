# Checkpoint 3B pause handoff

Owner-requested pause recorded November 27, 2026, until after the Geode interview
on **December 2, 2026**. Resume only when the owner asks. No automated generation,
new feature work, model downloads or merge is scheduled.

Branch: `feat/ai-investigation`. Previous pushed checkpoint: `798621d` (3A).
Preservation uses separate implementation/testing and documentation commits.
Implementation/testing commit: `b7058529b2f56a1f28531faf838b7311e0712291`.

## What works

- Existing simulator → Kafka → PostgreSQL/Redis → FastAPI → Next.js dashboard and
  durable alerts/acknowledgement remain the completed application baseline.
- AI document validation/chunking, pinned local MiniLM embeddings, file index and
  candidate retrieval, plus read-only PostgreSQL evidence snapshots, are verified.
- Checkpoint 3B adds the local Ollama client, report composition/validation,
  process-wide admission, approved budgets and fixed sanitized failure stages.
  Fake-provider tests cover these paths without real-model calls.
- Separate development-only tooling prepares a two-reading disposable PostgreSQL
  packet and two pinned runbook excerpts. The 7,878-byte prompt fits the 12,000-byte
  limit. Its bridge-network metadata probe works; its internal-network probe
  does not. Database preparation ends before generation, which has no DB credentials.
- Manual report generation requires explicit excerpt confirmation. Full reports
  are not printed; local saving is opt-in, private and refuses overwrite.

## What is unfinished

**Real evidence-backed investigation generation is not verified.** The owner's
first Qwen3 attempt failed after **66.745 seconds** with `ai_invalid_response`.
The rejected response was not retained; the exact failed substage is unknown.
Output truncation is a hypothesis, not a diagnosis. New safe stage categories
distinguish provider completion/body/JSON/token failures, report JSON/schema/
references and manual provenance. No generation settings or validation were relaxed.

**Automatic generation stays disabled.** Policy 2 has development **13/13** and
held-out **11/13**, with the original cutoff **0.48011912149223085**. One correct
error-count source scored **0.35276493876953824** below the cutoff; a lifecycle
question accepted an additional thermal source at **0.5014121688242127** outside
its label. The latter may require label review, not silent expansion. All labels,
runbooks and the recorded held-out result are preserved. These held-out cases
have now been inspected; a future policy needs a fresh held-out set.

All six runbooks remain `source_checked_pending_owner_review`. There is no AI
FastAPI route, Get AI Insights button, predictive-ML training or hosted release.
The optional combined Python Dockerfile is prepared but unbuilt; the staged
manual smoke reuses cached images and does not require that build.

## Verification at preservation

- Backend: **422 passed, 9 optional skips** (2.519 seconds).
- Disposable PostgreSQL: **28 passed, zero skips** (1.580 seconds).
- Offline AI: **155 passed, zero skips** (8.309 seconds), including the synthetic
  PostgreSQL prompt-size handoff. Real relevance regression uses development only.
- The preceding focused diagnostic run passed **117 tests, zero skips**.
- Ruff and cached-image dependency checks passed. Runbook/model fingerprints,
  evaluation/policy hashes, summary privacy checks and documentation checks passed.

These are local checks, not a new GitHub CI result or real-model success. No
Qwen generation, model/software installation, persistent-data mutation or held-out
rescoring occurred during preservation. Local packets remain ignored under
`build/ai-investigation/`; no prompts, reports, credentials or model weights enter Git.

The project-specific Next.js dev server was stopped gracefully because it kept
rewriting generated type imports. Those imports were restored to the committed
form and a local backup retained; no frontend source change is committed. Other
services and persistent data were left alone. Restart the existing dashboard
with `npm run dev` from `frontend/` when needed; this does not resume AI development.

## Exactly where to resume

1. Read [the manual smoke contract and selected excerpts](ai-manual-smoke.md) and
   its first-real-attempt diagnostic record. Start at
   [the Ollama client](../processing/device_health_investigation/ollama.py),
   [report validation](../processing/device_health_investigation/reporting.py), and
   [the standalone smoke](../processing/manual_investigation_smoke.py).
2. After owner authorization to resume, use `scripts/manual-ai-smoke.sh` to prepare
   a fresh private packet, probe metadata, and make **one** owner-run controlled
   generation attempt with the new stage diagnostics. Share only its summary.
   Do not change thinking mode, output budget, schema or references based on a guess.
3. Make a targeted correction only after the failure stage is known. If a report
   validates, manually inspect grounding and simulation limitations locally;
   a valid schema/reference list alone is not factual verification.
4. Separately review relevance-label completeness and development paraphrases;
   approve a new evaluation plan and fresh held-out set before further tuning.
   Keep automatic selection disabled until its acceptance checks pass.
5. API/frontend integration follows a reviewed, verified generation/retrieval
   increment. Preserve documentation-first approval, focused commits and existing
   ingestion/alert/schema behavior.
