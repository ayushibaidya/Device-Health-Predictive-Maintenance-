# ADR-004: Separate Offline Training and Online Inference

Status: Accepted for the Phase 2 architecture baseline

Context:
Training is iterative and resource-intensive, while online inference must consume validated telemetry predictably. Coupling training to normal event processing or user requests would make operational behavior harder to control and reproduce.

Decision:
Keep offline ML Training and online ML Inference as distinct responsibilities. Training prepares historical datasets and labels, creates/evaluates candidate models, and produces versioned artifacts. Inference loads one explicitly selected version, builds rolling feature windows, runs anomaly detection and failure prediction asynchronously, persists predictions, and updates current risk state. The primary target uses 5 simulated minutes of observable telemetry to predict FAILED entry in the next 30 simulated minutes. Isolation Forest anomaly output remains separate from supervised failure probability.

Alternatives Considered:
- Train models in the inference service: rejected because it couples model creation to the online path.
- Trigger inference synchronously from dashboard requests: rejected because frontend reads should not wait on model execution.
- Require an advanced model registry for MVP: deferred; a local versioned artifact abstraction is sufficient initially.

Consequences:
Training and inference can evolve and be validated independently; artifacts and active model selection must be traceable. Model serialization, artifact implementation, feature details, promotion workflow, hyperparameters, and retraining cadence remain TBD. Drift monitoring and automated retraining are post-MVP; MLflow may be introduced later.
