-- This is an ingestion inbox only, not the full historical telemetry schema.
CREATE TABLE IF NOT EXISTS telemetry_inbox (
    event_id uuid PRIMARY KEY,
    run_id uuid NOT NULL,
    device_id text NOT NULL CHECK (device_id <> ''),
    event_time timestamptz NOT NULL,
    payload jsonb NOT NULL,
    source_topic text NOT NULL,
    source_partition integer NOT NULL CHECK (source_partition >= 0),
    source_offset bigint NOT NULL CHECK (source_offset >= 0),
    persisted_at timestamptz NOT NULL DEFAULT now()
);
