# Simulator Component Design

Status: Proposals A-C approved by the user on October 27, 2026 and implemented
in the first simulator increment. See [simulator.md](simulator.md) for commands,
exact generation rules, verification, and limitations.

## Existing decisions

- Use standard C++20, CMake 4.4.3, Apple Clang locally, and GCC 16.2 in Linux CI.
- The simulator owns ground truth; model outputs never change device state.
- Allowed state changes are HEALTHY <-> WARNING, WARNING <-> CRITICAL, and
  CRITICAL -> FAILED. FAILED requires an explicit new lifecycle to recover.
- Emit samples every five simulated seconds, with ISO 8601 UTC event time.
- Keep hidden degradation out of emitted telemetry and future ML inputs.

References: [architecture](architecture.md), [ADR-003](adr/ADR-003-simulator-owns-ground-truth.md),
[telemetry schema](telemetry-schema.md), and [development standards](development-standards.md).

## Proposal A: scope, execution, and event contract

- This increment is a local simulator executable. It emits one JSON event per
  line to standard output; diagnostics go to standard error. Kafka publication
  and its pinned librdkafka dependency are introduced in the following increment.
- Reuse the unit-qualified field names in telemetry-schema.md. Do not add event
  identity or lifecycle fields to the shared event contract in this increment.
  Those remain explicit design questions before Kafka/replay and dataset work.
- Simulate three generic, non-actuator devices on one simulated clock, with
  HEALTHY control, continuous degradation, and degradation-then-recovery
  scenarios. Actuator-only optional fields are omitted for these devices.
- Use a single-threaded simulation loop initially. Simulated time advances in
  five-second ticks independently of wall-clock execution.
- Expose seed, UTC starting time, number of ticks, wall-clock speed, and an
  optional explicit reset tick through the CLI. Default to accelerated execution
  without sleeps, a fixed seed/start time, and 1,200 ticks (100 simulated minutes).
  Repeating all inputs must produce byte-identical JSON output across supported
  toolchains. Use a specified integer PRNG-to-noise mapping rather than
  implementation-dependent standard-library probability distributions.

## Proposal B: synthetic degradation and recovery model

These values are configurable synthetic demonstration parameters, not physical
device calibration or measured failure thresholds.

| Parameter | Approved default |
| --- | --- |
| Hidden degradation | Starts at 0, clamped to [0, 1] |
| Active injected fault | Adds 0.002 degradation per five-second tick |
| Recovery after clearing a fault | Subtracts 0.001 per tick, down to 0 |
| HEALTHY -> WARNING | Degradation >= 0.40 |
| WARNING -> CRITICAL | Degradation >= 0.75 |
| CRITICAL -> FAILED | Degradation reaches 1.00 |
| CRITICAL -> WARNING | Degradation <= 0.65 for 30 simulated seconds |
| WARNING -> HEALTHY | Degradation <= 0.30 for 30 simulated seconds |
| Healthy control | No injected fault |
| Failing device | Inject fault from the start and leave active |
| Recovering device | Clear its fault after 2,000 simulated seconds |

Only these deterministic degradation conditions change state. Seeded bounded
noise affects observed metrics only. Use integer degradation units internally
to avoid floating-point drift at transition boundaries.

Generate bounded temperature, power, CPU, memory, jitter, and error-count values
from degradation plus noise. Approved baseline-to-degraded metric values:
temperature 40 to 100 Celsius, power 5 to 20 watts, CPU 20 to 90 percent,
memory 30 to 80 percent, jitter 1 to 21 milliseconds, and error count 0 to 10
per sample. Percentage fields stay within [0, 100]; nonnegative metrics stay
nonnegative. The exact generator and noise amplitudes are documented in
[simulator.md](simulator.md) and are not validated physical behavior.

Recovery additionally requires the fault to remain cleared throughout the
stability period; reintroducing it cancels the recovery timer.

A failed device continues to emit its terminal FAILED state on subsequent
sample ticks. Explicit reset clears its degradation, fault, and recovery timer,
starts it healthy, preserves device identity, and does not rewind the fleet
clock. Hidden state and future failure times are never emitted.

## Proposal C: dependencies and verification

- Add nlohmann/json 3.12.0 for JSON encoding and contract tests. Fetch the exact
  release with an archive checksum; do not use a floating branch or tag.
- Use CTest with small C++ test executables; no additional test framework.
- Keep the approved CMake and compiler baselines. Add Linux/GCC 16.2 CI and
  document the required local Apple Clang check. Verify the container/tool
  versions instead of substituting another compiler silently.
- Separate simulation logic from CLI and JSON output so a later Kafka producer
  can consume samples without changing the lifecycle model.

## Acceptance and demonstration plan

1. Build and run tests using CMake presets from a clean checkout.
2. Run three devices with accelerated time and parse every output line as JSON.
3. Confirm required fields, types, units, UTC times, and five-second cadence.
4. Confirm healthy control, degradation to failure, and recovery through the
   allowed states. Check exact threshold and recovery-duration boundaries.
5. Confirm repeated runs are identical and changing the seed affects telemetry
   noise without changing deterministic state-transition times.
6. Confirm FAILED stays terminal until explicit reset, with monotonic event time.
7. Reject malformed CLI/configuration without emitting invalid telemetry.
8. Document commands and limitations. This demonstrates the simulator component;
   the browser-based end-to-end feature remains a later milestone.

Approval covers this simulator increment only. Later Kafka transport,
event/lifecycle identity, persistence, and application design decisions must be
confirmed before implementation.

Official dependency references:
[nlohmann/json 3.12.0](https://nlohmann.github.io/json/home/releases/v3.12.0/),
[GCC releases](https://gcc.gnu.org/releases.html), and
[CTest integration](https://cmake.org/cmake/help/v4.4/command/add_test.html).
