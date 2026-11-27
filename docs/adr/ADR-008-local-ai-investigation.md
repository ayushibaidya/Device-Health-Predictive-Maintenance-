# ADR-008: Local AI investigation with a rebuildable retrieval index

Status: architecture accepted November 26, 2026 through explicit owner approval.
Document preparation, local candidate retrieval and read-only PostgreSQL evidence
capture are implemented on the feature branch. Report composition, generation
and API/UI integration remain pending; the approved
[design](../ai-investigation-design.md) records the contracts and verification.

## Context

An engineer needs an evidence-backed explanation for an existing simulator-state
alert. The local portfolio demo must use collected telemetry and relevant
troubleshooting guidance without paid APIs, model training or changes to the
completed ingestion/alert workflow.

## Decision

Keep investigation as a logical module behind existing FastAPI and Next.js
boundaries. PostgreSQL supplies a consistent read-only snapshot for one selected
alert lifecycle: a five-minute simulation window with at most 100 readings.
Close its transaction before embedding or generation.

Author six synthetic Markdown runbooks in Git with an explicit hashed manifest.
Encode them locally with MiniLM; use a rebuildable file index and exact cosine
search to retrieve up to three relevant chunks with provenance. The index and
model caches are derived/local artifacts, not new durable application stores.
Model/profile changes require full re-embedding and relevance re-evaluation.

Use Ollama with Qwen3 4B as the initial pretrained generation candidate, subject
to actual runtime testing. Permit one synchronous generation at a time with a
separate configurable timeout and explicit failures. Return a structured,
source-validated report beneath the alert without persisting it. Keep AI runtime
dependencies optional; ordinary reads, readiness, ingestion and acknowledgement
must remain usable without models.

## Alternatives

- Hosted paid inference/embeddings: outside the approved local-first increment.
- A vector database or PostgreSQL vector extension: unnecessary services/schema
  for six static documents; revisit only for measured corpus-management needs.
- Background jobs, report tables or an agent/tool framework: defer because this
  MVP requests one transient report and performs no automated action.

## Consequences

Local provisioning and sufficient memory/disk are prerequisites; runtime speed
and relevance remain unmeasured. Explicit version/digest/profile provenance and
source references support inspection, but do not guarantee factual correctness.
A full browser reload discards the report; concurrent requests can receive a
busy response.
There is no report audit history, new Kafka path, Redis report cache, schema
migration or predictive-ML implementation. Persisting reports, adding hosted
access or changing concurrency/model boundaries requires another reviewed
decision. Existing ADR-001–007 decisions remain intact.
