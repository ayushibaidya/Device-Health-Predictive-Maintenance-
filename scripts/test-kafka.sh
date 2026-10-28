#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."

task_project="device-health-kafka-test-$$"
export KAFKA_PORT="${KAFKA_PORT:-29092}"
export API_PORT="${API_PORT:-28000}"
export KAFKA_FIXTURE_DIR="./build/${task_project}"
task_producer_pid=""
cleanup() {
    if [[ -n "$task_producer_pid" ]]; then kill "$task_producer_pid" 2>/dev/null || true; fi
    docker compose -p "$task_project" unpause kafka >/dev/null 2>&1 || true
    docker compose -p "$task_project" --profile tools down --volumes --remove-orphans >/dev/null
}
trap cleanup EXIT
mkdir -p "$KAFKA_FIXTURE_DIR"
docker compose -p "$task_project" build producer tests migrate api
docker compose -p "$task_project" run --rm --no-deps -T tests \
    python -m ruff check device_health_ingestion device_health_api tests demo.py demo_data.py demo_api.py
docker compose -p "$task_project" run --rm --no-deps -T tests \
    python -m pytest -m 'not integration' -q -o cache_dir=/tmp/pytest-cache
docker compose -p "$task_project" up -d --wait kafka postgres redis
docker compose -p "$task_project" run --rm -T migrate
docker compose -p "$task_project" up -d --no-deps --wait api
docker compose -p "$task_project" run --rm -T kafka-init
docker compose -p "$task_project" run --rm --no-deps -T producer \
    --output kafka --steps 2 --reset-at-step 1 > "$KAFKA_FIXTURE_DIR/producer-events.jsonl"
docker compose -p "$task_project" run --rm --no-deps -T tests \
    python -m pytest -m integration -q -o cache_dir=/tmp/pytest-cache

# Exercise a real temporary broker interruption, using only this test project's broker.
docker compose -p "$task_project" pause kafka
docker compose -p "$task_project" run --rm --no-deps -T producer \
    --output kafka --steps 0 --delivery-timeout-ms 10000 \
    > "$KAFKA_FIXTURE_DIR/retried-events.jsonl" &
task_producer_pid=$!
sleep 2
docker compose -p "$task_project" unpause kafka
wait "$task_producer_pid"
task_producer_pid=""
printf 'Ingestion, data-access, API, and broker-interruption checks passed.\n'
