# Synthetic temperature and power observations

Synthetic troubleshooting guidance for this project's simulator, not a hardware
service manual. Source-checked against baseline `2b919b7`.

## What the readings mean

The simulator generates `temperature_c` and `power_draw_w` from the same hidden
degradation value, with bounded random noise. Their values can rise together
during injected degradation. They are not measurements from physical sensors.

Device state is determined by hidden degradation and configured transition/
recovery rules. The state machine does not compare temperature or power readings
with operational thresholds. A noisy rise in either metric does not independently
create an alert or prove a thermal or electrical failure.

## Investigation checks

- Compare temperature and power across the selected alert's same-run evidence.
  Cite actual event IDs and distinguish a trend from a single noisy sample.
- Check the reported device states alongside the readings. If the window is
  short or capped, describe that limitation rather than infer earlier behavior.
- Compare recovery only within the same lifecycle. A reset begins another run;
  lower readings after it are not continuous recovery evidence for the old run.

## Limits

Temperature/power correlation is consistent with the synthetic degradation
mechanism. It does not identify blocked cooling, a damaged supply, a short
circuit or a failed component. The simulator has no physical diagnosis or
thermal/electrical remediation interface. The planned AI report must not perform
a reset.

## Implementation references

- [Metric generation and state machine](../../simulator/src/simulator.cpp)
- [Telemetry fields and configuration](../../simulator/include/device_health/simulator.hpp)
