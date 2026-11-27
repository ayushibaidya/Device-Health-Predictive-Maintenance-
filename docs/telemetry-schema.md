# Phase 3 Telemetry and Core Data Schema Draft

Status: Kafka identity fields and the narrow PostgreSQL ingestion inbox were
approved October 27, 2026 and are implemented. Approved app-ready data access
adds indexed queries and recoverable latest state to that inbox. Broader
historical PostgreSQL tables remain a design draft. Simulator-state `alerts` and
`alert_evaluation_state` were approved October 29, 2026 and are implemented.

This document defines the initial schema contract for the simulator → Kafka message path and the durable PostgreSQL tables needed for the MVP. It is intentionally a design artifact and not implementation code.

Kafka mode emits the full ingestion contract below. The legacy stdout simulator
emits metric samples without transport identities. See
[kafka-ingestion.md](kafka-ingestion.md) for acknowledgement and replay behavior.

## 1. Design principles

- Keep Kafka event payload and database tables separate but consistent.
- Use one canonical event schema for telemetry ingestion.
- Keep devices, telemetry, predictions, and alerts in distinct tables.
- Keep simulator ground truth separate from ML risk fields.
- Treat invalid telemetry as a tracked validation failure, not as a silent success.
- Apply SOLID design constraints at the schema and service boundary level: clear component responsibilities, stable contracts, and low coupling between event generation and downstream processing.

## 2. Kafka event schema (MVP)

The simulator publishes one telemetry event per device sample. This is the canonical input contract for the processing pipeline.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| event_id | UUID string | Yes | Globally unique sample identity, retained during retries/replay |
| run_id | UUID string | Yes | Current device lifecycle; changes on explicit reset |
| device_id | string | Yes | Stable device identifier |
| timestamp | datetime ISO 8601 UTC | Yes | Event time, not ingestion time |
| firmware_version | string | Yes | Current firmware version |
| temperature_c | float | Yes | Celsius |
| power_draw_w | float | Yes | Watts |
| cpu_utilization_pct | float | Yes | Percent |
| memory_utilization_pct | float | Yes | Percent |
| timing_jitter_ms | float | Yes | Milliseconds |
| error_count | integer | Yes | Synthetic per-sample value derived from degradation; currently 0–10 and may decrease during recovery. No cumulative/windowed aggregation is implemented. |
| device_state | enum | Yes | HEALTHY, WARNING, CRITICAL, FAILED |
| actuator_load_pct | float | No | Nullable when not applicable |
| position_error_mm | float | No | Nullable when not applicable |

### Validation rules

- `device_id` must be non-empty.
- `event_id` and `run_id` are canonical nonzero UUIDs; the Kafka key equals `device_id`.
- `timestamp` must be valid ISO 8601 UTC.
- `device_state` must be one of `HEALTHY`, `WARNING`, `CRITICAL`, `FAILED`.
- Required numeric fields must be present and must not be null.
- Missing required values are rejected as invalid telemetry.
- Invalid events are logged and routed to an error/dead-letter path.
- `device_state` is simulator ground truth and should not be used directly as a model feature.

### Example valid event

```json
{
  "event_id": "11111111-1111-4111-8111-111111111111",
  "run_id": "22222222-2222-4222-8222-222222222222",
  "device_id": "device-042",
  "timestamp": "2026-09-29T18:30:00Z",
  "firmware_version": "1.0.0",
  "temperature_c": 72.4,
  "power_draw_w": 11.8,
  "cpu_utilization_pct": 64.2,
  "memory_utilization_pct": 48.1,
  "timing_jitter_ms": 2.4,
  "error_count": 3,
  "device_state": "WARNING",
  "actuator_load_pct": 71.0,
  "position_error_mm": 0.18
}
```

## 3. PostgreSQL schema draft

The implemented `telemetry_inbox` is defined in
[001_telemetry_inbox.sql](../processing/migrations/001_telemetry_inbox.sql). It
stores unique event identity, lifecycle/device identity, event time, validated
JSON, Kafka coordinates, and persistence time. It provides durable deduplication
before offset commits. [002_data_access.sql](../processing/migrations/002_data_access.sql)
adds a durable accepted-event order and history/latest query indexes. See
[persistence.md](persistence.md) for lifecycle ordering, pagination, and cache
recovery. The broader historical tables below are still drafts.

[003_simulator_alerts.sql](../processing/migrations/003_simulator_alerts.sql)
adds alert episodes and durable rule progress. Its Python migration hook backfills
existing inbox history atomically using the live evaluator. See [alerts.md](alerts.md).
Only section 3.5 below describes implemented application tables; the remaining
broader tables are still drafts.

### 3.0 Schema decision summary

The schema is intentionally split into multiple tables instead of a single `devices` table. This separation reflects the architecture's data ownership and scalability goals:

- `devices` stores durable device identity and state metadata.
- `telemetry_events` stores high-volume time-series telemetry.
- `device_state_history` preserves state transitions and investigation history.
- `predictions` stores model outputs separately from raw telemetry.
- `alerts` stores operational alert lifecycle and acknowledgement state.
- `model_versions` tracks model lineage separately from the runtime event stream.

This split keeps the system scalable, makes time-series growth manageable, and separates operational state from durable historical records in line with the architecture's SOLID-aligned responsibilities.


### 3.1 devices

Purpose: durable device metadata and current lifecycle state.

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| device_id | varchar | PK | Stable identifier |
| device_type | varchar | NOT NULL | Example: pump, motor, controller |
| firmware_version | varchar | NOT NULL | Current firmware version |
| current_state | varchar | NOT NULL | HEALTHY, WARNING, CRITICAL, FAILED |
| created_at | timestamptz | NOT NULL | Device registration time |
| updated_at | timestamptz | NOT NULL | Last update time |
| is_active | boolean | DEFAULT true | Whether device is active in the fleet |

### 3.2 telemetry_events

Purpose: durable historical telemetry records.

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| event_id | uuid | PK | Unique event identifier |
| device_id | varchar | FK -> devices.device_id | Related device |
| timestamp | timestamptz | NOT NULL | Event time |
| firmware_version | varchar | NOT NULL | Snapshot at ingestion time |
| temperature_c | numeric(8,2) | NOT NULL | Celsius |
| power_draw_w | numeric(8,2) | NOT NULL | Watts |
| cpu_utilization_pct | numeric(5,2) | NOT NULL | Percent |
| memory_utilization_pct | numeric(5,2) | NOT NULL | Percent |
| timing_jitter_ms | numeric(6,3) | NOT NULL | Milliseconds |
| error_count | integer | NOT NULL | Error count |
| device_state | varchar | NOT NULL | Simulator ground truth |
| actuator_load_pct | numeric(5,2) | NULL | Optional |
| position_error_mm | numeric(8,3) | NULL | Optional |
| validation_status | varchar | NOT NULL | valid, invalid |
| ingested_at | timestamptz | NOT NULL | Ingestion time |

### 3.3 device_state_history

Purpose: durable timeline of device state transitions.

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| state_history_id | uuid | PK | State record id |
| device_id | varchar | FK -> devices.device_id | Device |
| timestamp | timestamptz | NOT NULL | Change time |
| state | varchar | NOT NULL | HEALTHY, WARNING, CRITICAL, FAILED |
| source | varchar | NOT NULL | simulator, alert, manual |
| reason | text | NULL | Optional explanation |

### 3.4 predictions

Purpose: durable ML result history.

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| prediction_id | uuid | PK | Unique prediction record |
| device_id | varchar | FK -> devices.device_id | Device |
| prediction_time | timestamptz | NOT NULL | Prediction generation time |
| model_version | varchar | NOT NULL | Version or tag |
| anomaly_score | numeric(6,4) | NULL | Optional anomaly result |
| failure_probability | numeric(5,4) | NOT NULL | 0.0 to 1.0 |
| prediction_horizon_minutes | integer | NOT NULL | Example: 30 |
| observation_window_minutes | integer | NOT NULL | Example: 5 |
| created_at | timestamptz | NOT NULL | Record creation time |

### 3.5 alerts (implemented)

Purpose: durable alert lifecycle and acknowledgement state.

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| alert_id | uuid | PK | Deterministic v5 from rule/opening event |
| alert_order | bigint identity | UNIQUE, NOT NULL | Creation-order cursor |
| device_id | text | NOT NULL, nonempty | Inbox identity; no draft devices registry FK |
| run_id | uuid | NOT NULL | Opening lifecycle |
| rule_id | text | NOT NULL, nonempty | simulator_state_v1 |
| source | text | NOT NULL | simulator only |
| severity | text | NOT NULL | WARNING, CRITICAL, FAILURE |
| status | text | NOT NULL | ACTIVE, ACKNOWLEDGED, RESOLVED |
| message | text | NOT NULL | Simulator-reported condition |
| opening_event_id, last_event_id | uuid | NOT NULL, FK inbox | Evidence; deletion restricted |
| resolved_event_id | uuid | NULL, FK inbox | Closing evidence; deletion restricted |
| opened_event_time, last_event_time | timestamptz | NOT NULL | Simulation times |
| resolved_event_time | timestamptz | NULL | Closing simulation time |
| created_at, updated_at | timestamptz | NOT NULL | PostgreSQL wall clock |
| acknowledged_at, resolved_at | timestamptz | NULL | Wall clock, no actor identity |
| resolution_reason | text | NULL | recovered, superseded, lifecycle_changed |

`run_id` identifies the opening lifecycle. Resolution records the closing event
in both `last_event_id`/`last_event_time` and the `resolved_event_*` fields.
For `lifecycle_changed`, that closing event may belong to the new lifecycle;
the alert retains its original `run_id`. Evidence foreign keys reference inbox
events and do not enforce a same-run relationship. Simulation clocks may restart
between runs; accepted ingestion order determines the transition.

Unique `(rule_id, opening_event_id)` prevents duplicate episode creation. A partial
unique `(device_id, rule_id)` index covers ACTIVE and ACKNOWLEDGED together.
Status/null consistency checks and device/order and status/order indexes are in
migration 003. `alert_evaluation_state` has primary key `(device_id, rule_id)`,
nonnegative `last_ingestion_order`, nullable `last_run_id`/`last_state` before the
first reading, and nullable `open_alert_id` referencing `alerts`. Accepted progress
and episode changes commit with the inbox. [alerts-design.md](alerts-design.md)
defines lifecycle, locking and bootstrap semantics; no broader schema is introduced.

### 3.6 model_versions

Purpose: trace the active model lineage and artifact metadata.

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| model_version_id | uuid | PK | Unique model id |
| model_name | varchar | NOT NULL | Example: failure_predictor |
| version | varchar | NOT NULL | Semver or tag |
| training_run_id | varchar | NULL | Training job identifier |
| trained_at | timestamptz | NOT NULL | Training timestamp |
| artifact_path | varchar | NOT NULL | Artifact location |
| precision | numeric(6,4) | NULL | Optional evaluation metric |
| recall | numeric(6,4) | NULL | Optional evaluation metric |
| f1_score | numeric(6,4) | NULL | Optional evaluation metric |
| pr_auc | numeric(6,4) | NULL | Optional evaluation metric |
| is_active | boolean | DEFAULT false | Selected active model |

### 3.7 validation_errors (recommended)

Purpose: durable list of invalid input events.

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| error_id | uuid | PK | Unique error id |
| device_id | varchar | NULL | Device if available |
| raw_payload | jsonb | NOT NULL | The rejected payload |
| error_message | text | NOT NULL | Validation or parse error |
| received_at | timestamptz | NOT NULL | Error capture time |

## 4. Relationship summary

- one `devices` row per physical device
- many `telemetry_events` per `devices.device_id`
- many `device_state_history` rows per device
- many `predictions` per device
- many `alerts` per device
- many model metadata rows in `model_versions`
- invalid payloads can be stored separately in `validation_errors`

## 5. Phase 3 scope for this draft

This schema is intentionally sufficient for:

- simulator emission
- telemetry validation
- Kafka ingestion contract
- durable storage of telemetry, predictions, alerts, and model metadata
- a basic MVP relational structure

It intentionally does not decide:

- exact database performance tuning
- detailed indexing strategy
- retention policy
- exact AWS storage architecture
- user auth model
- production-scale dashboards

## 6. Next step

Kafka ingestion, queryable telemetry, and recoverable latest-state views are
implemented against the inbox contract. FastAPI and the dashboard expose this
data plus durable simulator alerts and acknowledgement. ML remains planned.
See [frontend.md](frontend.md) for the implemented views.
