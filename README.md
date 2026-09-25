# Device Health and Predictive Maintenance Platform

## Project description
The Device Health and Predictive Maintenance Platform is a distributed full-stack system for ingesting real-time telemetry from simulated embedded devices, analyzing device behavior, detecting anomalies, predicting failures using machine learning, and presenting device-health information to engineers through a web interface. The platform is intended to demonstrate broad software engineering capability across telemetry processing, distributed systems, backend services, machine learning, database design, observability, and cloud deployment.

## Project status
Status: Requirements Gathering & Analysis

Implementation has not yet begun. This repository currently contains only planning and requirements documentation for SDLC Phase 1.

## Planned technology stack
- Device / Edge: C++, multithreading, telemetry generation, fault injection
- Streaming: Apache Kafka
- Caching / low-latency state: Redis
- Relational storage: PostgreSQL
- Backend: Python, FastAPI, Pydantic, SQLAlchemy, Alembic
- Frontend: Next.js, React, TypeScript, Tailwind CSS
- Machine learning: Python, NumPy, Pandas, scikit-learn, optional XGBoost
- Infrastructure: Docker, Docker Compose, Kubernetes, Terraform
- Cloud: AWS
- Observability: Prometheus, Grafana, CloudWatch
- CI/CD: GitHub Actions

## Documentation
- [docs/requirements.md](docs/requirements.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/testing-strategy.md](docs/testing-strategy.md)
- [docs/adr/README.md](docs/adr/README.md)

## Important note
This project is intentionally in the requirements and analysis phase. Architecture, implementation, infrastructure, backend code, frontend code, ML training, containers, and deployment work are intentionally deferred until a later SDLC phase after explicit approval.
