# Telemetry coverage and simulation time

Synthetic troubleshooting guidance for the collected event stream, not a device
connectivity diagnosis. Source-checked against baseline `2b919b7`.

## What time and coverage mean

The simulator emits samples at five-second simulation intervals. It emits the
initial tick and each configured advance; the default three-device, 1,200-step
run therefore produces 3,603 events. Simulation can run without wall-clock waits.
A saved simulation timestamp is not a current heartbeat.

PostgreSQL's inbox retains accepted telemetry and ingestion order; Redis latest
state is derived and recoverable. The planned historical investigation must read
PostgreSQL.
Accepted order distinguishes replay/lifecycle progression when separate runs
reuse simulation timestamps. Identical event-ID replay is deduplicated, not a
new independent measurement.

## Investigation checks

- Inspect the selected device/run's observed timestamps and accepted orders.
  A five-minute window may contain only part of an alert's life.
- Report the window bounds, number of selected readings and cap/truncation flag.
  Do not fill missing timestamps or extrapolate unseen states.
- Check existing API liveness/readiness separately if reads fail. An unavailable
  API/database or expired Redis entry does not establish that a device failed.
- For the planned AI feature, no relevant troubleshooting guidance means
  insufficient evidence. Missing/corrupt model or index files are AI availability
  errors under its design, not evidence that the device is unhealthy.

## Limits

A sparse window cannot by itself prove a disconnected device, packet loss,
Kafka failure or downtime. A healthy/readiness endpoint concerns the application,
not simulated device health. Firmware/update events and physical connectivity
observations must not be fabricated. No investigation text changes an alert,
repairs the pipeline or creates missing telemetry.

## Implementation references

- [Cadence and fleet samples](../../simulator/src/simulator.cpp)
- [Five-second interval and default steps](../../simulator/include/device_health/simulator.hpp)
- [Inbox persistence and duplicate handling](../../processing/device_health_ingestion/store.py)
- [Recoverable latest-state cache](../../processing/device_health_ingestion/latest.py)
- [Application health endpoints](../../processing/device_health_api/app.py)
- [Planned AI behavior](../../docs/ai-investigation-design.md)
