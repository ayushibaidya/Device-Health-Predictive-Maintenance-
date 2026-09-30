# Development Standards

This document defines the minimum reproducibility, security, collaboration, and
quality rules for implementation. The Phase 3 simulator and Kafka baseline is
pinned below. Other planned technologies remain unpinned until their component
implementation begins. Do not infer a version from a developer's machine or use
floating `latest` dependencies.

## 1. Toolchain and dependency versions

Before the first code for a component is merged, record its supported toolchain
and pin its runtime, framework, database/broker engine, and direct dependencies.
Use the repository's version files, build manifests, dependency lockfiles, and
container image tags as the executable source of truth. CI and local setup must
use those same pins.

### Phase 3: simulator and Kafka ingestion

| Component | Required baseline |
| --- | --- |
| Local hardware/architecture | MacBook Air M3, Apple Silicon `arm64` |
| C++ language | Standard C++20; standard C++ only unless an extension is justified and documented |
| Local C++ compiler | Apple Clang provided by the stable Xcode Command Line Tools |
| Reference/CI C++ compiler | GCC 16.2 on Linux |
| Build system | CMake 4.4.3 |
| Kafka client | `librdkafka` 2.16.0 |
| Kafka broker | Apache Kafka 4.3.1, official Docker image, KRaft mode; ZooKeeper is not used |

Local builds target `arm64`. Docker images and services must support Apple
Silicon where available. The same C++ project must compile with both the local
Apple Clang toolchain and the Linux/GCC reference toolchain. CI must include a
Linux build using GCC 16.2; retain a local Apple Clang build as a required
developer check, and add a macOS CI job if/when the project enables macOS runners.

The CMake project must require C++20, reject compiler extensions by default, and
consume the pinned `librdkafka` version. The local Kafka service must use the
explicit `apache/kafka:4.3.1` image tag and configure KRaft without ZooKeeper.
These pins must be reflected in build configuration and local-run configuration
as those files are introduced; this table is the reviewable baseline, not a
substitute for executable pins.

Before adding Python services, pin Python and FastAPI versions; before adding the
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