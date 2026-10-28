-- Preserve accepted-event order across lifecycle resets and duplicate replays.
-- The migration runner holds a transaction/advisory lock during this backfill.
CREATE SEQUENCE telemetry_ingestion_order_seq;
ALTER TABLE telemetry_inbox ADD COLUMN ingestion_order bigint;
WITH ordered AS (
    SELECT event_id, row_number() OVER (
        ORDER BY source_topic, source_partition, source_offset, event_id
    ) AS position FROM telemetry_inbox
)
UPDATE telemetry_inbox AS inbox SET ingestion_order = ordered.position
FROM ordered WHERE inbox.event_id = ordered.event_id;
SELECT setval('telemetry_ingestion_order_seq',
              COALESCE((SELECT max(ingestion_order) FROM telemetry_inbox), 0) + 1, false);
ALTER SEQUENCE telemetry_ingestion_order_seq OWNED BY telemetry_inbox.ingestion_order;
ALTER TABLE telemetry_inbox ALTER COLUMN ingestion_order
    SET DEFAULT nextval('telemetry_ingestion_order_seq');
ALTER TABLE telemetry_inbox ALTER COLUMN ingestion_order SET NOT NULL;
CREATE UNIQUE INDEX telemetry_ingestion_order_idx ON telemetry_inbox (ingestion_order);
CREATE INDEX telemetry_device_order_idx ON telemetry_inbox (device_id, ingestion_order DESC);
CREATE INDEX telemetry_device_time_idx ON telemetry_inbox (device_id, event_time);
CREATE INDEX telemetry_device_run_time_idx ON telemetry_inbox (device_id, run_id, event_time);
