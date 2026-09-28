# ADR-005: Separate Alert Evaluation from ML Risk Signals

Status: Accepted for the Phase 2 architecture baseline

Context:
Anomaly and failure-risk outputs are evidence for operators, while alerts are operational decisions with durable lifecycle and acknowledgement. Conflating the two would let a model output act as ground truth or make alert workflow inseparable from a particular model.

Decision:
ML Inference produces anomaly and failure-risk signals. A logically separate Alert Evaluation component interprets those signals alongside deterministic simulator/device-state conditions and existing alert state. It owns operational alert decisions and persistence; it may initially run in the same deployable process as telemetry processing or inference. The MVP supports WARNING, CRITICAL, and simulator-confirmed FAILURE levels, with ACTIVE → ACKNOWLEDGED → RESOLVED lifecycle and durable PostgreSQL records. ML probability cannot declare ground-truth failure.

Alternatives Considered:
- Let the ML model create or own device failure state: rejected because risk and truth differ.
- Require a separately deployed alert microservice from the start: rejected as unnecessary deployment complexity absent a concrete need.

Consequences:
Alert policy can change independently of model implementation while retaining explicit acknowledgement/history. Exact thresholds, combinations, cooldown/debounce, and reactivation behavior remain TBD during detailed alert design. Assignment, escalation, and external notifications are out of MVP scope.
