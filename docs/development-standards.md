# Development Standards

This document defines the minimum reproducibility, security, collaboration, and
quality rules for implementation. The simulator, Kafka, data-access, and API baseline is
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
| HTTP API | FastAPI 0.162.0, Pydantic 2.14.1, Uvicorn 0.54.0; HTTPX 0.28.1 for tests/demo |

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
The read-only API uses the same Python image, existing psycopg query layer and
SQL migration runner. See [basic-api.md](basic-api.md) for its approved contract.
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
each increment's code, focused tests, and build/CI configuration in focused
implementation commits. Keep related documentation changes in a separate focused
commit before merge, following the documentation review below. Use a component
scope in the Conventional Commit message, and keep subsequent increments out of
that commit.
A local commit is a checkpoint, not a substitute for the pull request,
remote CI checks, and merge required by the Definition of Done.

The repository owner runs `git add`, `git commit`, and `git push`. Coding agents
leave implementation changes uncommitted and provide the exact commands after
verification; do not create commits on the owner's behalf.

Confirm unresolved software design decisions with the user before implementing
them. Continue within an already approved design without asking for the same
approval again. Preserve approved decisions and verification results in the
component documentation so later phases can resume from the saved checkpoint.

The priority is a credible hosted MVP. Keep the existing SDLC documents, feature
branches, focused commits, and relevant tests while making every increment
advance ingestion, persistence/current state, API, dashboard/alerts, ML, and
hosting. Keep design records concise and confirm material decisions without
delaying routine implementation.

### Documentation synchronization and pre-merge review

Keep project documentation synchronized with the implemented system as each
feature progresses. Update the relevant design or contract document when
implementation clarifies or changes an approved decision. Confirm any new design
decision with the owner under the existing approval rule before implementing it.
Distinguish implemented behavior from planned behavior and remove descriptions
that no longer match the system.

Update `README.md` only when user-facing setup, capabilities, the architecture
summary, or demo instructions change. Add or update an ADR only for a meaningful
architectural decision. Routine code changes do not justify unrelated document
rewrites or a new ADR.

Before merging each feature, check and record in the pull request:

1. Whether architecture, design, or contract documents need updates.
2. Whether `README.md` needs updates under the criteria above.
3. Whether a new or updated ADR is justified.
4. Whether implementation has resolved an existing TBD that can now be documented.

When documentation updates are needed, include them in a separate focused
`docs(<component>): ...` commit on the feature branch before it is merged. Coding
agents prepare the changes and provide separate implementation/documentation
commit commands for the owner to run. Do not create an empty documentation commit
when the review finds no changes are needed.

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
- The documentation pre-merge review is recorded in the pull request. Required
  documentation updates, including changed version pins and environment
  variables, are included in a separate focused documentation commit before merge.
- The pull request is reviewed, required CI checks pass, and the change is merged
  to `main` using the agreed merge strategy.

If a check cannot reasonably apply, explain why in the pull request rather than
silently omitting it. A passing test suite is necessary but does not override an
unmet acceptance criterion or an unresolved security concern.
