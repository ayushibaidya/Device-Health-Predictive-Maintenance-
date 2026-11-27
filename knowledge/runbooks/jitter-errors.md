# Synthetic timing jitter and error readings

Synthetic troubleshooting guidance for this project's simulator, not an
instrumented timing or fault log. Source-checked against baseline `2b919b7`.

## What the readings mean

`timing_jitter_ms` is computed from hidden degradation and bounded noise, with
a nonnegative floor. It is not measured scheduling delay, network latency or
Kafka consumer lag.

`error_count` is a synthetic per-sample integer: the simulator computes
`10 * degradation / 10000` using integer arithmetic. Its current generated
range is 0–10. It may decrease during recovery; it is neither a cumulative error
counter nor a count over a documented time window. Do not sum readings as total
faults or interpret a decrease as lost history. The validator itself only
requires a nonnegative integer; 0–10 is simulator behavior, not its upper bound.

## Investigation checks

- Compare jitter and error readings in accepted order within one run.
- Cite individual readings when describing increases, decreases or unchanged
  coarse integer values; bounded jitter noise can vary independently per sample.
- Check reported state transitions separately. The alert evaluator consumes
  `device_state`, not a jitter or error-count threshold.

## Limits

These values do not prove dropped packets, timing violations or physical fault
frequency. No packet-loss, scheduler or hardware error-code details are collected
by these fields. Acknowledgement does not clear either metric.

## Implementation references

- [Metric generation](../../simulator/src/simulator.cpp)
- [Validator bounds](../../processing/device_health_ingestion/validation.py)
- [Simulator-state alert rule](../../processing/device_health_alerts/rules.py)
