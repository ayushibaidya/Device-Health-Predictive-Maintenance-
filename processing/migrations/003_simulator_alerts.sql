SET LOCAL lock_timeout = '5s';
LOCK TABLE telemetry_inbox IN SHARE ROW EXCLUSIVE MODE;

CREATE TABLE alerts (
    alert_id uuid PRIMARY KEY,
    alert_order bigint GENERATED ALWAYS AS IDENTITY UNIQUE NOT NULL,
    device_id text NOT NULL CHECK (device_id <> ''),
    run_id uuid NOT NULL,
    rule_id text NOT NULL CHECK (rule_id <> ''),
    source text NOT NULL CHECK (source = 'simulator'),
    severity text NOT NULL CHECK (severity IN ('WARNING', 'CRITICAL', 'FAILURE')),
    status text NOT NULL CHECK (status IN ('ACTIVE', 'ACKNOWLEDGED', 'RESOLVED')),
    message text NOT NULL,
    opening_event_id uuid NOT NULL REFERENCES telemetry_inbox(event_id) ON DELETE RESTRICT,
    last_event_id uuid NOT NULL REFERENCES telemetry_inbox(event_id) ON DELETE RESTRICT,
    resolved_event_id uuid REFERENCES telemetry_inbox(event_id) ON DELETE RESTRICT,
    opened_event_time timestamptz NOT NULL,
    last_event_time timestamptz NOT NULL,
    resolved_event_time timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    acknowledged_at timestamptz,
    resolved_at timestamptz,
    resolution_reason text CHECK (resolution_reason IN ('recovered', 'superseded', 'lifecycle_changed')),
    UNIQUE (rule_id, opening_event_id),
    CHECK (status <> 'ACKNOWLEDGED' OR acknowledged_at IS NOT NULL),
    CHECK (status <> 'ACTIVE' OR acknowledged_at IS NULL),
    CHECK (
        (status = 'RESOLVED' AND resolved_at IS NOT NULL AND resolved_event_id IS NOT NULL
         AND resolved_event_time IS NOT NULL AND resolution_reason IS NOT NULL)
        OR (status <> 'RESOLVED' AND resolved_at IS NULL AND resolved_event_id IS NULL
            AND resolved_event_time IS NULL AND resolution_reason IS NULL)
    )
);
CREATE UNIQUE INDEX alerts_one_open_episode_idx ON alerts (device_id, rule_id)
    WHERE status IN ('ACTIVE', 'ACKNOWLEDGED');
CREATE INDEX alerts_device_order_idx ON alerts (device_id, alert_order DESC);
CREATE INDEX alerts_status_order_idx ON alerts (status, alert_order DESC);

CREATE TABLE alert_evaluation_state (
    device_id text NOT NULL CHECK (device_id <> ''),
    rule_id text NOT NULL,
    last_ingestion_order bigint NOT NULL DEFAULT 0 CHECK (last_ingestion_order >= 0),
    last_run_id uuid,
    last_state text CHECK (last_state IN ('HEALTHY', 'WARNING', 'CRITICAL', 'FAILED')),
    open_alert_id uuid REFERENCES alerts(alert_id) ON DELETE RESTRICT,
    PRIMARY KEY (device_id, rule_id),
    CHECK ((last_ingestion_order = 0 AND last_run_id IS NULL AND last_state IS NULL)
        OR (last_ingestion_order > 0 AND last_run_id IS NOT NULL AND last_state IS NOT NULL))
);
