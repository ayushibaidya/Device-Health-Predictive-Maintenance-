#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
export KAFKA_FIXTURE_DIR="${KAFKA_FIXTURE_DIR:-./build/alerts-demo}"
mkdir -p "$KAFKA_FIXTURE_DIR"
docker compose build producer consumer tests migrate api frontend
docker compose up -d --wait kafka postgres redis
# Approved upgrade window: stop old ingestion while migration 003 backfills its inbox.
docker compose stop consumer
docker compose run --rm -T migrate
docker compose run --rm -T kafka-init
docker compose up -d --no-deps --wait api
docker compose run --rm --no-deps -T producer --output kafka --steps 1200 \
    > "$KAFKA_FIXTURE_DIR/producer-events.jsonl"
printf 'Persisting the simulator run; per-event log: %s/ingestion.log\n' "$KAFKA_FIXTURE_DIR"
docker compose run --rm --no-deps -T tests python demo.py > "$KAFKA_FIXTURE_DIR/ingestion.log"
tail -n 1 "$KAFKA_FIXTURE_DIR/ingestion.log"
docker compose run --rm --no-deps -T tests python demo_alerts.py --acknowledge
docker compose up -d --no-deps --wait frontend
task_frontend_address="$(docker compose port frontend 3000)"
printf 'Alerts demo: http://%s/alerts\n' "$task_frontend_address"
printf 'Open: acknowledged device-002 failure. All/Resolved: severity changes and device-003 recovery.\n'
printf 'When finished: docker compose --profile tools down\n'
