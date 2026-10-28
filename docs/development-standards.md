# Development Standards

This document defines the minimum reproducibility, security, collaboration, and
quality rules for implementation. The simulator, Kafka, and data-access baseline is
pinned below. Other planned technologies remain unpinned until their component
implementation begins. Do not infer a version from a developer's machine or use
floating `latest` dependencies.

## 1. Toolchain and dependency versions

Before the first code for a component is merged, record its supported toolchain
and pin its runtime, framework, database/broker engine, and direct dependencies.
Use the repository's version files, build manifests, dependency lockfiles, and
container image tags as the executable source of truth. CI and local setup must
use those same pins.

### Implemented simulator, ingestion, and data access

| Component | Required baseline |
| --- | --- |
| Local hardware/architecture | MacBook Air M3, Apple Silicon `arm64` |
| C++ language | Standard C++20; standard C++ only unless an extension is justified and documented |
| Local C++ compiler | Apple Clang provided by the stable Xcode Command Line Tools |
| Reference/CI C++ compiler | GCC 16.2 on Linux |
| Build system | CMake 4.4.3 |
| Simulator JSON encoding | nlohmann/json 3.12.0; release archive and SHA-256 pinned in `cmake/Dependencies.cmake` |
| Kafka client | `librdkafka` 2.15.1 |
| Kafka broker | Apache Kafka 4.3.1, official Docker image, KRaft mode; ZooKeeper is not used |
| Latest-state cache | Redis 8.10.3, official Alpine image pinned by digest; redis-py 8.1.0 |

`librdkafka` 2.15.1 remains the explicitly approved ingestion baseline. Dependency
upgrades are separate reviewed changes, rather than implicit updates to whichever
release is newest.

Local builds target `arm64`. Docker images and services must support Apple
Silicon where available. The same C++ project must compile with both the local
Apple Clang toolchain and the Linux/GCC reference toolchain. CI must include a
Linux build using GCC 16.2; retain a local Apple Clang build as a required
developer check, and add a macOS CI job if/when the project enables macOS runners.

The CMake project must require C++20 and reject compiler extensions by default.
The simulator-only increment consumes the pinned JSON dependency; it emits JSON
Lines locally without requiring a broker or Kafka client. When Kafka publishing
is introduced, the CMake project must consume the pinned `librdkafka` version.
The local Kafka service must use the
explicit `apache/kafka:4.3.1` image tag and configure KRaft without ZooKeeper.
These pins must be reflected in build configuration and local-run configuration
as those files are introduced; this table is the reviewable baseline, not a
substitute for executable pins.

The simulator build, approved behavior, CLI, tests, and demonstration are
documented in [simulator.md](simulator.md) and [simulator-design.md](simulator-design.md).
CTest is supplied by the pinned CMake toolchain; no additional test framework is
required. The C++ CI bootstrap uses Python solely to install pinned CMake inside an
ephemeral GCC container; it does not introduce a Python runtime for the simulator.

The consumer pins Python 3.13.18, confluent-kafka 2.15.1, and
psycopg/psycopg-binary 3.3.6. PostgreSQL 18.6 stores the ingestion inbox, now also
used for indexed history and durable latest-state queries. Broader historical
tables remain deferred. Redis latest state is derived and recoverable, as
described in [persistence.md](persistence.md).
Runtime/dev lockfiles pin transitive dependencies and hashes; image tags and
digests pin execution environments. Docker Engine 27+ and Compose 2.24+ are the
supported baseline, tested locally with 29.2.1 and 5.0.2 respectively. See
[kafka-ingestion.md](kafka-ingestion.md) for the contract and verification.

Before adding API services, pin FastAPI and related versions; before adding the
frontend, pin Node.js and frontend package versions; before using PostgreSQL or
Redis, pin their engine versions. Pin Docker/Compose versions or document the
supported range for local orchestration. Optional and future technologies are
not requirements until adopted by an implementation decision.

Version changes must update the appropriate manifest/lockfile and pass CI. A
version change that affects compatibility or architecture requires an ADR or a
documented design decision. Container images must use explicit versions; use
digests where supply-chain reproducibility requires immutable image identity.

## 2. Environment and secrets

- Commit a `.env.example` containing variable names, safe local defaults where
  possible, and descriptions; never put real credentials in it.
- Keep developer-specific `.env` files untracked. The root `.gitignore` already
  excludes `.env` patterns; preserve that protection and verify it for any new
  environment-file naming convention.
- Read configuration from environment variables or the approved local secret
  mechanism. Do not hard-code secrets, commit credentials, place secrets in
  container images, or print them in logs, test output, or error messages.
- Keep local credentials scoped to development and separate from CI or deployed
  credentials. Use the CI platform's secret store for CI and a managed secret
  store for deployed environments; do not copy production secrets to laptops.
- Validate required configuration at startup and fail clearly when required
  values are missing or malformed. Keep non-secret configuration distinct from
  credentials, and document required variables without documenting secret values.
- Rotate any credential that is accidentally exposed and remove it from active
  use; deleting it from a later commit is not sufficient.

## 3. Branching and pull requests

Use a lightweight GitHub Flow: `main` is the shared integration branch, and all
work is done on short-lived branches created from an up-to-date `main`.

Branch names use a type and concise kebab-case description, optionally including
an issue number: `feat/123-device-simulator`, `fix/telemetry-validation`,
`docs/development-standards`, or `chore/pin-toolchain`. Open a pull request to
`main` for every change; do not push feature work directly to `main`. Keep pull
requests focused, link related issues when available, and squash-merge after
required checks pass and the change is reviewed. Delete the branch after merge.

Configure repository protection for `main` to require pull requests and passing
CI checks, and to block force-pushes and branch deletion. Require at least one
approval when another maintainer is available; a solo maintainer must still use
a pull request and passing checks rather than self-approving. Branch protection
is a GitHub repository setting and must be enabled separately; this document
does not enforce it by itself.

### Phase-based implementation commits

Keep Git checkpoints aligned with approved implementation increments. Commit
each completed increment separately, including its code, focused tests,
build/CI configuration, and related documentation. Use a component scope in the
Conventional Commit message, and keep subsequent increments out of that commit.
The simulator and Kafka ingestion are the first implementation increments.
A local commit is a checkpoint, not a substitute for the pull request,
remote CI checks, and merge required by the Definition of Done.

Confirm unresolved software design decisions with the user before implementing
them. Continue within an already approved design without asking for the same
approval again. Preserve approved decisions and verification results in the
component documentation so later phases can resume from the saved checkpoint.

The priority is a credible hosted MVP. Keep the existing SDLC documents, feature
branches, focused commits, and relevant tests while making every increment
advance ingestion, persistence/current state, API, dashboard/alerts, ML, and
hosting. Keep design records concise and confirm material decisions without
delaying routine implementation.

## 4. Commit messages

Use Conventional Commits:

```text
<type>(<optional scope>): <imperative summary>
```

Use the applicable type, including `feat`, `fix`, `docs`, `test`, `refactor`,
`build`, or `chore`. Keep the summary concise and specific. Mark breaking changes
with `!` after the type/scope and explain the migration in the commit body, for
example `feat(telemetry)!: change event envelope`.

## 5. Definition of Done

A feature or fix is done only when all applicable items below are satisfied:

- Its behavior meets documented acceptance criteria, including relevant failure
  and boundary cases.
- Focused automated tests cover the changed behavior; related regression tests
  pass. Integration or contract tests are included when a service boundary,
  schema, persistence layer, or event contract changes.
- Formatting, linting, type/static checks, and the relevant build/test commands
  pass locally and in CI.
- Configuration, schema/migrations, operational behavior, and security controls
  are updated when affected. No credentials or sensitive sample data are added.
- Relevant documentation and setup instructions are updated, including version
  pins or environment-variable documentation when those change.
- The pull request is reviewed, required CI checks pass, and the change is merged
  to `main` using the agreed merge strategy.

If a check cannot reasonably apply, explain why in the pull request rather than
silently omitting it. A passing test suite is necessary but does not override an
unmet acceptance criterion or an unresolved security concern.
