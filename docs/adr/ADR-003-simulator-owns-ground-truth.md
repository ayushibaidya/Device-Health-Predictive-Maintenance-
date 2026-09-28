# ADR-003: Simulator Owns Device Ground Truth

Status: Accepted for the Phase 2 architecture baseline

Context:
The system needs deterministic device lifecycle behavior and reliable labels for model evaluation. Allowing predicted risk to determine whether a simulated failure occurred would contaminate labels and operational state.

Decision:
The simulator owns hidden degradation progression, deterministic state transitions, true failure occurrence, recovery, and reset/restart behavior. Its states are HEALTHY, WARNING, CRITICAL, and FAILED, with allowed transitions HEALTHY ↔ WARNING, WARNING ↔ CRITICAL, and CRITICAL → FAILED. WARNING may recover to HEALTHY; CRITICAL may recover to WARNING but not directly to HEALTHY. FAILED is terminal for the current run and requires an explicit reset, restart, or replacement to begin a new lifecycle. ML may use observable telemetry only; hidden degradation, future state, known future failure time, and ground-truth state that leaks the target are excluded as inference features.

Alternatives Considered:
- Allowing model predictions to change simulated state: rejected because it confounds prediction with the actual outcome.
- Exposing hidden degradation variables to inference: rejected because it leaks target information.

Consequences:
Ground-truth events can provide training labels and evaluation data while predictions remain risk signals only. Exact degradation equations, transition thresholds, recovery durations, fault injection, and reset semantics remain TBD during detailed simulator design.
