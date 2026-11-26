# ADR-007: Atomic simulator alerts and historical bootstrap

Status: accepted October 29, 2026, through approval of alerts design A–F.

## Context

Kafka redelivery must not duplicate alert episodes or erase acknowledgements.
Existing inbox history predates alert evaluation; evaluating only new events
would omit that history and misidentify ongoing conditions after rollout.

## Decision

Keep a logically separate simulator-state evaluator in the existing ingestion
process. Persist inbox, severity-specific alert episodes and durable per-device/
rule progress in one PostgreSQL transaction before committing Kafka offsets.
Lock progress before inbox insertion; acknowledgement locks only its alert.
Use deterministic UUID v5 episode identities, unique opening evidence and one
unresolved episode per device/rule. Every unhealthy severity change opens a fresh
episode; acknowledgement never changes health or carries into a new episode.

Migration 003 uses the same evaluator to bootstrap accepted inbox history in its
migration transaction, before recording completion. Pause old ingestion during
rollout and hold a bounded-acquisition inbox write lock while backfilling. Resume
the existing consumer group after deploying the matching consumer/API. Preserve
the established invalid-event DLQ path and best-effort Redis behavior.

## Alternatives

- A separate alert consumer/outbox adds deployment and recovery coordination for
  this small deterministic rule; defer until measured needs justify it.
- Non-transactional post-persistence evaluation permits missed alerts after a
  crash; reject.
- Bootstrapping only current device state loses historical episodes; deleting
  data or resetting offsets is unnecessary and would risk acknowledgement loss.

## Consequences

Telemetry ingestion success now depends on durable rule evaluation. Unexpected
evaluator/schema faults stop processing without offset commit; transient lock/
database failures retain bounded retries. Same-device writes serialize; different
devices remain independent. Historical rollout briefly pauses ingestion and may
take longer on large inboxes; throughput/backfill benchmarks remain future work.
There is no new Kafka topic, Redis alert cache, service or library. ML policy is
still separate and unimplemented. See [the full contract](../alerts-design.md)
and [operational guide](../alerts.md).
