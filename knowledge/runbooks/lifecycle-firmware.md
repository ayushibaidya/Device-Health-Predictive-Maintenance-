# Device lifecycle, reset and firmware evidence

Synthetic troubleshooting guidance for the current simulator's identities and
reset behavior. Source-checked against baseline `2b919b7`.

## What a reset changes

FAILED is absorbing in `Device::advance`: clearing a fault alone cannot recover
it. An explicit reset clears degradation, the fault and recovery tracking and
sets state to HEALTHY. It preserves the device ID, global simulation clock and
noise-generator state; it does not reseed that generator.

In Kafka output, the producer assigns a new run ID for device-002 at the explicit
reset tick. A new producer execution assigns new run IDs to its devices too.
Device ID remains the stable fleet identity; run ID separates lifecycles and
event ID identifies an individual event.

## Investigation checks

- Match every selected telemetry row to the alert's device ID and opening run ID.
- Use accepted ingestion order to locate lifecycle boundaries. Separate producer
  executions may restart their simulation clock; do not compare their times as
  one uninterrupted lifecycle.
- Treat next-run closing evidence on a `lifecycle_changed` alert as boundary
  metadata. Do not mix the next run's healthier metrics into the old report.
- The generated firmware version is currently `1.0.0`. Report that observed
  value without inventing a deployment, upgrade or rollback.

## Limits

The configurable fleet reset targets device-002; this is not a remotely exposed
reset API or a physical maintenance action. The planned AI investigation must
never execute it.
Firmware-update workflows, firmware causality and hardware repair history are
not implemented. A changed run ID alone does not distinguish a configured reset
from a newly launched producer; the report must acknowledge that ambiguity.

## Implementation references

- [Device reset and fleet progression](../../simulator/src/simulator.cpp)
- [Kafka run/event identities](../../simulator/src/main.cpp)
- [UUID serialization](../../kafka/src/event.cpp)
