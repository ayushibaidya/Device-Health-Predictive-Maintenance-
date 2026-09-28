# ADR-002: Kafka as Asynchronous Event Transport

Status: Accepted for the Phase 2 architecture baseline

Context:
The simulator emits telemetry independently of persistence, inference, alert evaluation, and user-facing reads. Synchronous coupling would make the producer and dashboard depend on downstream processing availability.

Decision:
Use Kafka as the asynchronous transport for telemetry and related events. Telemetry processing consumes and validates events before persistence and downstream inference. Frontend-to-FastAPI requests and user alert acknowledgement remain synchronous request/response operations. Frontend requests do not trigger inference.

Alternatives Considered:
- Direct synchronous simulator-to-database or simulator-to-inference calls: rejected for the main telemetry flow because they tightly couple producer availability and processing.
- Kafka as a query store: rejected; PostgreSQL and Redis serve durable history and current operational reads respectively.

Consequences:
Producers and consumers can be decoupled and processing can tolerate transient service interruptions subject to the eventual durability/replay design. Exact topics, message schemas, partitions, retention, retry behavior, consumer coordination, and whether predictions or alerts also use Kafka remain TBD during detailed component design / implementation.
