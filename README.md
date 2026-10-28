# Device Health and Predictive Maintenance Platform

## Project description
The Device Health and Predictive Maintenance Platform is a distributed full-stack system for ingesting real-time telemetry from simulated embedded devices, analyzing device behavior, detecting anomalies, predicting failures using machine learning, and presenting device-health information to engineers through a web interface. The platform is intended to demonstrate broad software engineering capability across telemetry processing, distributed systems, backend services, machine learning, database design, observability, and cloud deployment.

## Project status
Status: the C++ simulator and Kafka ingestion path are implemented. Events flow
through Kafka, Python validation, and a durable PostgreSQL inbox with replay
deduplication. App-ready history queries and recoverable Redis latest state are
implemented. Upcoming increments add APIs, dashboard/alerts, ML, and a public
hosted demo.

Before implementing each component, its toolchain and dependency versions must
be pinned as described in [docs/development-standards.md](docs/development-standards.md).

## Run the data-access demo

With Docker running:

```sh
bash scripts/demo-data.sh
```

This runs **C++ simulator -> Kafka -> Python validation -> PostgreSQL -> Redis**,
shows history/current state, and demonstrates cache recovery. See the
[data-access guide](docs/persistence.md) for query commands and recovery, and the
[Kafka ingestion guide](docs/kafka-ingestion.md) for delivery/replay details.
Run `bash scripts/test-kafka.sh` for the isolated automated check.

The delivery goal is a public demo with fleet/device views, alert acknowledgement,
and genuine ML predictions. Each increment gets a focused feature branch, tests,
commit, and pull request:

| Increment | Outcome |
| --- | --- |
| Simulator | Completed and merged |
| Kafka ingestion | Implemented, including the approved ingestion inbox |
| Persistence/current state | Implemented: bounded history queries and recoverable Redis latest state |
| Basic API | Fleet, device, history, and alert endpoints |
| Dashboard | Fleet/device views and alert acknowledgement |
| ML baseline | Failure probability and anomaly signal visible in the UI |
| Hosted release | Public URL, health checks, and automatically seeded demo data |

## Build, test, and demonstrate the simulator

From the repository root, using CMake 4.4.3 and Apple Clang locally:

```sh
cmake --preset dev
cmake --build --preset dev --parallel 4
ctest --preset dev --parallel 4
cmake --build --preset dev --target simulator_demo
```

The demo runs three devices for 100 simulated minutes without wall-clock waits,
validates 3,603 real JSON events, and prints the observed state changes. See the
[simulator guide](docs/simulator.md) for direct CLI commands, configuration,
offline dependency setup, and current limitations. The first configure fetches
the checksum-pinned nlohmann/json 3.12.0 dependency.

## Planned technology stack
- Device / Edge: C++20, Apple Clang (stable Xcode Command Line Tools) locally, GCC 16.2 in Linux CI
- Build system: CMake 4.4.3
- Streaming: Apache Kafka 4.3.1, official Docker image, KRaft mode (no ZooKeeper)
- Kafka client: librdkafka 2.15.1, the approved ingestion baseline
- Caching / low-latency state: Redis 8.10.3, redis-py 8.1.0
- Relational storage: PostgreSQL 18.6 (inbox, indexed history queries, durable latest state)
- Backend: Python 3.13.18; FastAPI, Pydantic, SQLAlchemy, and Alembic versions pinned when adopted
- Frontend: Next.js, React, TypeScript, Tailwind CSS (versions to be pinned before implementation)
- Machine learning: Python, NumPy, Pandas, scikit-learn, optional XGBoost
- Infrastructure: Docker, Docker Compose, Kubernetes, Terraform
- Cloud: AWS
- Observability: Prometheus, Grafana, CloudWatch
- CI/CD: GitHub Actions; Linux/GCC 16.2 build required for C++ portability

## Documentation
- [docs/requirements.md](docs/requirements.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/telemetry-schema.md](docs/telemetry-schema.md)
- [docs/security-scalability.md](docs/security-scalability.md)
- [docs/development-standards.md](docs/development-standards.md)
- [docs/adr/README.md](docs/adr/README.md)
- [docs/testing-strategy.md](docs/testing-strategy.md)
- [docs/simulator-design.md](docs/simulator-design.md)
- [docs/simulator.md](docs/simulator.md)
- [docs/kafka-ingestion.md](docs/kafka-ingestion.md)
- [docs/persistence.md](docs/persistence.md)

Implementation is local-first and follows the documented architecture, schema,
security, and development standards. Cloud infrastructure and production
deployment are planned for the hosted-release increment after the tested
recruiter-facing product workflow is working.
