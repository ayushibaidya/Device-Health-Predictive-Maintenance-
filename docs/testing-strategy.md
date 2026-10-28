# Testing Strategy

## Testing Goals
The testing strategy for this project will focus on validating that the system behaves correctly, remains stable under failure, supports maintainability, and provides evidence that product requirements are met as implementation proceeds.

The strategy will be extended as the platform becomes more concrete. The broader
strategy remains at the requirements level; component-specific executable tests
and verification commands are documented with each implemented component.

The first simulator increment now has executable lifecycle, model, JSON contract,
CLI, recovery, and repeatability checks. Its commands and demo are documented in
[simulator.md](simulator.md); the broader strategy below applies as additional
components are introduced. Run `ctest --preset dev` after building.

Kafka ingestion adds producer identity/failure tests, Python validation and
acknowledgement-boundary checks, and real Kafka/PostgreSQL integration tests.
`bash scripts/test-kafka.sh` checks restart deduplication, the database-before-
offset crash window, DLQ delivery, database recovery, and broker interruption.
The Kafka ingestion GitHub Actions workflow runs the same script.

## Unit Testing
Unit tests will validate the correctness of individual logic components, calculations, feature transformations, model utility functions, and validation logic.

The unit testing focus should include:
- telemetry validation logic
- feature engineering logic
- health and risk calculations
- alert threshold evaluation
- data serialization and conversion
- ML helper functions and evaluation utilities

## Component Testing
Component tests will validate the behavior of meaningful subsystems in isolation, including processing components, adapters, and service-layer logic.

The initial focus should include:
- telemetry processing steps
- anomaly detection workflow components
- prediction workflow logic
- device health aggregation logic
- alert generation logic

## API Testing
API tests will validate the behavior of backend interfaces, request/response contracts, error handling, validation, and service integration boundaries.

The testing scope should include:
- telemetry ingestion endpoints
- health queries
- historical retrieval APIs
- alert and prediction read APIs
- failure and validation scenarios

## Database Testing
Database testing will validate persistence, schema integrity, transactional behavior, historical data retrieval, and relationship accuracy.

This should include:
- data insertion and retrieval correctness
- time-series retention patterns
- relationship integrity for device, firmware, and alert records
- query performance under representative conditions

## Kafka/Event Pipeline Testing
Kafka testing will validate the reliability and correctness of event-driven ingestion and downstream processing.

Key areas include:
- message publication and consumption
- ordering and replay assumptions
- failure recovery and retry behavior
- message backlog handling
- processing lag and downstream backlog visibility

## Redis Testing
Redis testing will validate current-state access, ephemeral data handling, cached values, and operational coordination logic.

Areas should include:
- cache correctness
- TTL behavior
- transient state accuracy
- failover and resilience assumptions
- read/write consistency expectations

## ML Validation Testing
ML validation testing will assess the quality of the predictive and anomaly workflows using documented metrics and evaluation processes.

This should include:
- baseline model validation
- model comparison across candidate algorithms
- classification performance checks
- anomaly detection quality checks
- drift and stability monitoring preparation
- performance and latency validation for inference

## Integration Testing
Integration tests will validate interactions between multiple system components, including telemetry flow, storage, processing, API, and monitoring components.

This will be required for validating operational correctness across the real platform architecture once implementation begins.

## End-to-End Testing
End-to-end testing will validate the entire user flow from simulated device emissions through ingestion, processing, storage, API access, and dashboard visibility.

This testing layer should confirm that the end-to-end system supports the intended operational workflow for device monitoring and predictive maintenance.

## Performance / Load Testing
Performance testing will validate throughput, latency, queue behavior, and resource utilization under expected and stress conditions.

This will include:
- telemetry ingestion under sustained load
- downstream analytics and prediction processing under backlog
- API responsiveness under concurrent access
- storage and query behavior under historical data growth

Performance targets must remain labeled as TARGET values until measured experimentally.

## Failure-Injection Testing
Failure-injection tests will deliberately trigger service, queue, dependency, or data issues to validate resilience and recovery behavior.

This should include:
- producer interruption
- consumer failure
- database connectivity issues
- queue backlog and recovery
- degraded service mode validation
- operational alerting during failure scenarios

## Regression Testing
Regression testing will protect against accidental behavior changes across firmware changes, model changes, service updates, and platform refactors.

This includes validating:
- alerting consistency
- health-score changes over time
- model output stability with known data
- previously resolved issue reproduction

## CI Expectations
The implementation phase should include CI expectations that verify correctness and quality before merge, such as:
- automated unit tests
- API validation tests
- relevant integration tests
- linting or static checks where applicable
- performance smoke checks for critical flows
- regression checks for ML and alerting workflows

The implemented ingestion/data-access workflow runs `bash scripts/test-kafka.sh`
in GitHub Actions. It covers 68 Python unit tests and 10 real-service integration
tests, including history/pagination, lifecycle replay, migration of populated
inboxes, Redis recovery/expiry, and durable processing during cache connection
failure. The C++ producer image retains its 39 CTest checks. The script also
exercises a broker interruption and cleans only its own test volumes.
`bash scripts/demo-data.sh` demonstrates the full implemented pipeline and
history/current-state/cache recovery. Future API/UI/ML tests are added with
their respective increments.
