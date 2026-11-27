# Running the device simulator

The first implementation increment is a C++20 simulator with automated tests and
a repeatable terminal demo. Its [design](simulator-design.md) was approved on
October 27, 2026. Kafka publishing has since been implemented in the
[Kafka ingestion increment](kafka-ingestion.md).

## Build and test

Use CMake 4.4.3 and the Apple Clang compiler supplied by the stable Xcode Command
Line Tools on macOS. No broker, credentials, environment file, or service
installation is needed for this component. Linux CI uses GCC 16.2.0.

From the repository root:

```sh
cmake --preset dev
cmake --build --preset dev --parallel 4
ctest --preset dev --parallel 4
```

The first configure downloads nlohmann/json 3.12.0 from its official release and
verifies its SHA-256. Subsequent builds reuse the downloaded source. In a
restricted-network environment, obtain the official `json.tar.xz` archive and use:

```sh
cmake --preset dev -DDEVICE_HEALTH_JSON_ARCHIVE=/absolute/path/to/json.tar.xz
```

The same checksum is enforced for local archives. To return to the normal
download URL, configure with `-DDEVICE_HEALTH_JSON_ARCHIVE=`. Build output,
downloaded dependencies, and generated demo JSON Lines remain under ignored
`build/` directories.

## Demonstrate the feature

```sh
cmake --build --preset dev --target simulator_demo
```

This runs the real executable twice, verifies byte-identical output, and parses
all 3,603 JSON events. It prints the observed state changes and checks a healthy
control, progression to failure, recovery, required fields, and five-second UTC
cadence. The complete output is saved in `build/dev/simulator/demo/first.jsonl`.

Default scenario transition times, relative to the initial sample:

| Device | Scenario | Expected observations |
| --- | --- | --- |
| device-001 | Healthy control | Remains HEALTHY throughout |
| device-002 | Continuous fault | WARNING at 16:40; CRITICAL at 31:15; FAILED at 41:40 |
| device-003 | Fault cleared at 33:20 | WARNING at 16:40; CRITICAL at 31:15; WARNING at 46:20; HEALTHY at 75:30 |

Times above are elapsed simulated minutes:seconds, not wall-clock durations or
measured physical-device behavior. The default run covers 100 simulated minutes
without wall-clock waits. The initial time is deliberately fixed for replay;
pass `--start-time` to use another canonical UTC starting time.

## Run directly

```sh
# Three devices, seed 42, fixed UTC start, initial samples plus 1200 ticks.
./build/dev/simulator/device_simulator > build/dev/telemetry.jsonl

# Six JSON lines: initial samples plus one tick, including a UTC year rollover.
./build/dev/simulator/device_simulator --steps 1 --start-time 2026-12-31T23:59:55Z

# 60 simulated seconds per wall-clock second; use --speed 1 for real time.
./build/dev/simulator/device_simulator --steps 12 --speed 60

# Explicitly reset the failed device at tick 700; preserve the global clock.
./build/dev/simulator/device_simulator --steps 705 --reset-at-step 700

./build/dev/simulator/device_simulator --help
```

Output is one compact JSON object per line on stdout. Diagnostics go to stderr;
invalid configuration exits with status 1 before emitting telemetry. `--steps 0`
emits only the three initial samples. `--speed 0` runs without sleeps; other
supported speed values are finite and at least 1.

## Model and configuration

Hidden degradation uses integer units from 0 to 10,000. An active fault adds 20
units per tick; clearing it removes 10 units per tick. State thresholds and
recovery defaults are recorded in the approved design, and CLI options expose
the rates, thresholds, recovery hold, and fault-clearance tick.

Recovery requires the fault to be cleared and the degradation to stay below its
recovery threshold for six complete five-second intervals. Reintroducing the
fault or crossing back above the threshold cancels that stability timer.
FAILED cannot recover by clearing a fault: an explicit reset is required. Reset
clears the fault and degradation without changing the device ID, rewinding the
clock, or reseeding its noise generator.

Rates must be positive. Thresholds must satisfy:

```text
0 <= warning recovery < warning < critical recovery < critical < 10000
```

The degradation increment cannot exceed the smallest gap between progression
thresholds, ensuring a sample never skips an intermediate state. Recovery hold
ticks must be positive. UTC input accepts `YYYY-MM-DDTHH:MM:SSZ`, years 0001 to
9999, with valid calendar dates and no leap seconds. Runs that would overflow
that calendar are rejected before output.

Telemetry uses a specified `std::mt19937` integer sequence and integer-to-noise
mapping. Noise is added in hundredths before converting to JSON numeric values:

| Metric | Baseline to fully degraded value | Bounded noise |
| --- | --- | --- |
| Temperature | 40 to 100 Celsius | +/- 1 Celsius |
| Power | 5 to 20 watts | +/- 0.10 watt |
| CPU | 20 to 90 percent | +/- 2 percentage points |
| Memory | 30 to 80 percent | +/- 1 percentage point |
| Timing jitter | 1 to 21 milliseconds | +/- 0.20 millisecond |
| Error count | 0 to 10 per sample | None |

Noise never changes ground-truth state. Percentage fields are clamped to
[0, 100], and nonnegative metrics remain nonnegative. Failed devices continue
to emit their FAILED state with noisy metrics at the fully degraded baseline.
These are synthetic generation rules, not calibrated physical distributions.

## Scope and next integration

The original stdout build remains independent of Kafka and databases. The
optional Kafka build now publishes identified events to the validated ingestion
pipeline in [kafka-ingestion.md](kafka-ingestion.md). Its telemetry follows the
accepted unit-qualified event fields, without hidden
degradation or future failure information. These generic devices have no
actuators, so optional actuator fields are omitted.

The Kafka increment now supplies event/lifecycle identity, the approved topics
and key, producer delivery checks, DLQ routing, and durable deduplication. Kafka
records distinguish reset lifecycle boundaries; ML dataset preparation remains
part of the ML increment.

## Verification recorded on October 27, 2026

| Environment | Build | Result |
| --- | --- | --- |
| macOS / Apple Clang 21.0.0 / arm64 | Debug, CMake 4.4.3 | 37 of 37 CTest checks passed; demo passed |
| Linux / GCC 16.2.0 / pinned GCC container | Release, CMake 4.4.3 | 37 of 37 CTest checks passed; demo passed |

The default run produced 3,603 events with identical bytes in both environments.
Its SHA-256 was:

```text
ccaae8a592840a2c7e0f9218bf2731e7ea019b3fe5b81a29a412efa7a6727add
```

Both the approved local-archive configuration and the normal upstream download
configuration were exercised. The GitHub Actions workflow is prepared; these
results come from local execution, including the actual Linux container, rather
than a GitHub-hosted workflow run.
