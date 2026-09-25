# Architecture Document

Status: Intentionally incomplete for SDLC Phase 1.

This document is a template for the next architecture phase and should not be interpreted as a finalized design. The architecture will be completed during Phase 2 after requirements are validated and approved.

## System Context
This section will describe the operational environment, external systems, actors, device fleet assumptions, and the platform boundary within which the system will operate.

## Architecture Goals
This section will document the key goals for the architecture, including maintainability, scalability, observability, testability, resilience, and alignment with the product requirements.

## High-Level Architecture
This section will summarize the major architecture layers, processing stages, and interactions among the platform components. It will be completed only after requirements are approved for architecture design.

## Component Diagram
This section will contain a high-level component diagram and a brief explanation of major subsystems. Component names, responsibilities, and interactions remain TBD until Phase 2.

## Data Flow
This section will describe how telemetry, derived features, alerts, predictions, and maintenance information move through the platform. This will be defined after architectural decisions are made.

## Service Responsibilities
This section will describe the responsibilities of major services, processing stages, and support components. Current ownership is intentionally not finalized.

## Device / Edge Architecture
This section will cover the simulated device environment, telemetry generation patterns, fault injection, timing characteristics, data buffering, and any device-side responsibilities.

## Kafka Design
This section will describe event streaming responsibilities, topics, producers, consumers, durability assumptions, partitioning strategy, and operational concerns if Kafka is selected for the eventual implementation.

## Redis Design
This section will define the intended use of Redis for ephemeral state, current-state views, short-lived coordination, caching, and performance-sensitive operations.

## PostgreSQL Design
This section will describe the durable relational source-of-truth responsibilities, schema strategy, device metadata, telemetry history, alerts, predictions, and model metadata as relevant to the final architecture.

## API Architecture
This section will describe the interface layer for external and internal API interactions, including request routing, validation, service responsibilities, and documentation expectations.

## ML Architecture
The ML architecture will separate online inference from offline training and keep the model lifecycle explicit.

### ML Inference Service — Python
Responsibilities:
- consume validated telemetry from the processing pipeline
- maintain and build rolling feature windows from recent telemetry
- run anomaly detection
- run supervised failure prediction
- output anomaly score or anomaly status, failure probability, model name/version, and prediction timestamp
- persist prediction results to PostgreSQL
- update latest risk and prediction state in Redis
- emit risk signals used for alert generation

MVP inference flow:
Validated telemetry → feature window → anomaly model + failure prediction model → prediction result → PostgreSQL + Redis → alert evaluation / API

Model usage:
- inference uses pre-trained, versioned model artifacts
- model training happens separately in the offline ML Training Pipeline
- the inference service must never train models during normal request or event processing

Execution model:
- inference should be asynchronous and event-driven rather than triggered directly by frontend requests
- the frontend and API read previously computed prediction results

Boundary:
- ML Inference owns online prediction
- ML Training owns training, evaluation, and model creation
- Alert logic consumes prediction and risk outputs but remains conceptually separate from the ML models themselves

### ML Problem Contract
Primary supervised prediction target:
"Will this currently operating device enter the FAILED state within the next 30 minutes of simulated time?"

Observation window:
- previous 5 minutes of telemetry

Prediction window:
- next 30 minutes of simulated time

These are separate concepts:
- observation window = data used to construct features
- prediction window = future period in which failure is predicted

Label generation:
- the simulator owns ground-truth failure events
- label = 1 if the device enters FAILED within the next 30 simulated minutes
- label = 0 otherwise
- the model must never define the ground-truth failure state

Model candidates:
- Logistic Regression as the baseline
- Random Forest
- XGBoost

The MVP will compare these candidates and select a model based on measured validation performance rather than choosing one in advance.

Anomaly detection:
- use Isolation Forest as a separate parallel detection system
- anomaly detection is part of the MVP
- its output may support alert generation and investigation
- anomaly score should not replace the supervised failure prediction
- anomaly detection and failure prediction should produce separate signals

Primary evaluation metrics:
- precision
- recall
- F1
- PR-AUC
- false-positive rate

Secondary evaluation metrics:
- ROC-AUC
- inference latency

Because failure events may be relatively rare, PR-AUC, recall, precision, and false-positive rate should receive particular attention.

Secondary prediction horizons:
- 10 minutes
- 60 minutes

These are comparison and experimentation horizons only. The 30-minute horizon remains the primary MVP requirement unless explicitly changed later.

The 5-minute observation window and 30-minute prediction window are design requirements, not measured outcomes.

This ML contract will drive simulator label generation, feature engineering, training, model evaluation, online inference, and alert-related risk signals.

This separation will be reflected in the future Phase 2 architecture and data-flow documentation.

## Frontend Architecture
This section will describe the dashboard and user interaction model, role-based views, integrations with backend APIs, and web application architecture.

## Security Architecture
This section will define authentication, authorization, secrets handling, network boundaries, and operational controls for deployment.

## Deployment Architecture
This section will describe the local and cloud deployment model, containers, orchestration, environment boundaries, and deployment patterns.

## AWS Architecture
This section will outline the intended AWS footprint, including services considered for the final implementation, their roles, and justification for inclusion.

## Observability
This section will describe metrics, logs, traces, alerting, dashboards, service health checks, and operational monitoring design.

## Scaling Strategy
This section will describe how the system is expected to scale with additional devices, increased telemetry volume, and operational load. Scaling targets remain TBD.

## Failure Handling
This section will describe recovery patterns, degradation strategy, circuit breakers, retries, timeouts, and operational failure handling as relevant to eventual implementation.

## Architecture Tradeoffs
This section will summarize design tradeoffs, technology choices, alternative approaches, and the reasons for selecting or deferring a given architecture.

## Open Decisions
The following decisions remain open and must be finalized during Phase 2:
- detailed service boundaries
- data flow topology
- message broker topology
- storage and processing split
- ML deployment model
- web dashboard architecture
- local vs cloud-first operational model
- scaling and latency targets
- observability stack integration model

This document is intentionally incomplete and will be completed during Phase 2 of the SDLC after explicit approval to proceed.
