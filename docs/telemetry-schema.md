# Phase 3 Telemetry and Core Data Schema Draft

Status: Draft for Phase 3 design

This document defines the initial schema contract for the simulator → Kafka message path and the durable PostgreSQL tables needed for the MVP. It is intentionally a design artifact and not implementation code.

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
| device_id | string | Yes | Stable device identifier |
| timestamp | datetime ISO 8601 UTC | Yes | Event time, not ingestion time |
| firmware_version | string | Yes | Current firmware version |
| temperature_c | float | Yes | Celsius |
| power_draw_w | float | Yes | Watts |
| cpu_utilization_pct | float | Yes | Percent |
| memory_utilization_pct | float | Yes | Percent |
| timing_jitter_ms | float | Yes | Milliseconds |
| error_count | integer | Yes | Count of errors since previous sample or window |
| device_state | enum | Yes | HEALTHY, WARNING, CRITICAL, FAILED |
| actuator_load_pct | float | No | Nullable when not applicable |
| position_error_mm | float | No | Nullable when not applicable |

### Validation rules

- `device_id` must be non-empty.
- `timestamp` must be valid ISO 8601 UTC.
- `device_state` must be one of `HEALTHY`, `WARNING`, `CRITICAL`, `FAILED`.
- Required numeric fields must be present and must not be null.
- Missing required values are rejected as invalid telemetry.
- Invalid events are logged and routed to an error/dead-letter path.
- `device_state` is simulator ground truth and should not be used directly as a model feature.

### Example valid event

```json
{
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

### 3.5 alerts

Purpose: durable alert lifecycle and acknowledgement state.

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| alert_id | uuid | PK | Unique alert id |
| device_id | varchar | FK -> devices.device_id | Affected device |
| severity | varchar | NOT NULL | WARNING, CRITICAL, FAILURE |
| status | varchar | NOT NULL | ACTIVE, ACKNOWLEDGED, RESOLVED |
| source | varchar | NOT NULL | simulator, ml, rule-based |
| created_at | timestamptz | NOT NULL | Alert creation time |
| acknowledged_at | timestamptz | NULL | When user acknowledged it |
| resolved_at | timestamptz | NULL | When resolved |
| message | text | NOT NULL | Human-readable alert summary |

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

The next actionable step is to convert this draft into an agreed Phase 3 schema review and then begin the simulator + Kafka ingestion implementation against this contract.
