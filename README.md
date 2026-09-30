# Device Health and Predictive Maintenance Platform

## Project description
The Device Health and Predictive Maintenance Platform is a distributed full-stack system for ingesting real-time telemetry from simulated embedded devices, analyzing device behavior, detecting anomalies, predicting failures using machine learning, and presenting device-health information to engineers through a web interface. The platform is intended to demonstrate broad software engineering capability across telemetry processing, distributed systems, backend services, machine learning, database design, observability, and cloud deployment.

## Project status
Status: architecture and Phase 3 design baselines are documented; implementation
is starting with the simulator and Kafka telemetry ingestion.

Before implementing each component, its toolchain and dependency versions must
be pinned as described in [docs/development-standards.md](docs/development-standards.md).

## Planned technology stack
- Device / Edge: C++20, Apple Clang (stable Xcode Command Line Tools) locally, GCC 16.2 in Linux CI
- Build system: CMake 4.4.3
- Streaming: Apache Kafka 4.3.1, official Docker image, KRaft mode (no ZooKeeper)
- Kafka client: librdkafka 2.15.1; upgrade to 2.16.0 after its official release/tag is published and verified
- Caching / low-latency state: Redis (version to be pinned before implementation)
- Relational storage: PostgreSQL (version to be pinned before implementation)
- Backend: Python, FastAPI, Pydantic, SQLAlchemy, Alembic (versions to be pinned before implementation)
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

Implementation is local-first and follows the documented architecture, schema,
security, and development standards. Cloud infrastructure and production
deployment remain out of scope for the initial implementation phase.
