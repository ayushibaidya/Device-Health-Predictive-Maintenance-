# Device Health and Predictive Maintenance Platform

## Project description
This project simulates a device fleet, streams telemetry through Kafka, saves
validated readings in PostgreSQL, and presents current device state and history
in a Next.js dashboard. Redis provides recoverable latest state and FastAPI
provides the application data interface. Alert processing, ML predictions, and a
public hosted release are planned subsequent increments.

## Project status
Status: the C++ simulator and Kafka ingestion path are implemented. Events flow
through Kafka, Python validation, and a durable PostgreSQL inbox with replay
deduplication. App-ready history queries and recoverable Redis latest state are
implemented. A read-only FastAPI service now exposes fleet summary, device
details, and telemetry history with interactive API documentation. The frontend
now provides fleet counts, device investigation, telemetry charts/history,
manual refresh, and loading/empty/error states. Alerts, ML, and public hosting
remain upcoming increments.

Before implementing each component, its toolchain and dependency versions must
be pinned as described in [docs/development-standards.md](docs/development-standards.md).

## Run the dashboard demo

With Docker running:

```sh
bash scripts/demo-dashboard.sh
```

Open **[http://localhost:3000](http://localhost:3000)**, select a device, and inspect
its current readings and history. The first Docker build may take several
minutes. This runs **C++ simulator -> Kafka -> Python validation ->
PostgreSQL/Redis -> FastAPI -> Next.js**. All displayed readings come from the
real API; the devices themselves are simulated. When finished, stop services
with `docker compose --profile tools down`, which preserves saved data.

Run `bash scripts/test-dashboard.sh` for the isolated frontend checks, including
a browser journey through the real pipeline. The backend-only demo remains
`bash scripts/demo-api.sh`, with interactive docs at
[http://localhost:8000/docs](http://localhost:8000/docs). See the
[frontend guide](docs/frontend.md) for setup, behavior, and tests, the
[API guide](docs/basic-api.md) for routes and health checks, the
[data-access guide](docs/persistence.md) for recovery, and the
[Kafka guide](docs/kafka-ingestion.md) for delivery/replay details. Run
`bash scripts/test-kafka.sh` for the isolated automated check.

The delivery goal is a public demo with fleet/device views, alert acknowledgement,
and genuine ML predictions. Each increment gets a focused feature branch, tests,
commit, and pull request:

| Increment | Outcome |
| --- | --- |
| Simulator | Completed and merged |
| Kafka ingestion | Implemented, including the approved ingestion inbox |
| Persistence/current state | Implemented: bounded history queries and recoverable Redis latest state |
| Basic API | Implemented: fleet/device/history endpoints, health checks, and interactive docs; alert endpoints follow alert processing |
| Dashboard | Implemented: fleet/device views, current values, history charts, refresh, and application states |
| Alerts | Planned: durable alert processing, display, and acknowledgement |
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
- Backend: Python 3.13.18, FastAPI 0.162.0, Pydantic 2.14.1, Uvicorn 0.54.0; existing psycopg queries and SQL migrations
- Frontend: Node 24.22.1/npm 11.19.1, Next.js 16.4.3, React 19.3.1, TypeScript 6.0.3, Tailwind CSS 4.3.3, Recharts 3.10.1
- Frontend browser tests: Playwright 1.64.1; Docker/Chromium and native Apple Silicon checks
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
- [docs/basic-api-design.md](docs/basic-api-design.md)
- [docs/basic-api.md](docs/basic-api.md)
- [docs/dashboard-design.md](docs/dashboard-design.md)
- [docs/frontend.md](docs/frontend.md)

Implementation is local-first and follows the documented architecture, schema,
security, and development standards. Cloud infrastructure and production
deployment are planned for the hosted-release increment after the tested
recruiter-facing product workflow is working.
