# Simulator-state alert episodes and review

Synthetic troubleshooting guidance for the implemented alert workflow.
Source-checked against baseline `2b919b7`.

## What creates an episode

The `simulator_state_v1` rule maps reported WARNING to alert severity WARNING,
CRITICAL to CRITICAL, and FAILED to FAILURE. HEALTHY opens no alert. These are
simulator-state episodes, not predicted failures or metric-threshold diagnoses.

For the same device, rule and run, repeated identical unhealthy states refresh
the existing episode's last evidence and preserve acknowledgement. A severity
change, including de-escalation, resolves it as `superseded` and opens a fresh
ACTIVE episode. HEALTHY resolves an open episode as `recovered`. A run change
closes an open episode as `lifecycle_changed` before applying the new state.

## Investigation checks

- Read the selected episode's opening state, severity, status and resolution
  reason. Distinguish the telemetry state FAILED from alert severity FAILURE.
- Compare its bounded same-run readings. A closing same-run event may show
  recovery or the state that superseded the selected episode.
- For `lifecycle_changed`, closing evidence can be from the next run while the
  alert retains its opening run ID. Treat it as boundary metadata, not a reading
  from the old lifecycle.
- Distinguish simulation event times from wall-clock acknowledgement time.

## Limits and review behavior

ACTIVE and ACKNOWLEDGED are both unresolved; the database allows only one
unresolved episode per device/rule. Acknowledgement records review without
changing device health or clearing a fault. Repeating acknowledgement preserves
its first timestamp. A resolved episode cannot be acknowledged. A fresh episode
requires its own review; the previous acknowledgement does not carry forward.
No user identity, notification, escalation or predictive score is implemented.
The planned AI investigation must not acknowledge or resolve alerts.

## Implementation references

- [Rule transitions](../../processing/device_health_alerts/rules.py)
- [Evidence and lifecycle updates](../../processing/device_health_alerts/evaluator.py)
- [Acknowledgement](../../processing/device_health_alerts/store.py)
- [Database constraints](../../processing/migrations/003_simulator_alerts.sql)
