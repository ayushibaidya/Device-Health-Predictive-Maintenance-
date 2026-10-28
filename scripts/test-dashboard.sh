#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
task_project="device-health-dashboard-test-$$"
export COMPOSE_PROJECT_NAME="$task_project"
export KAFKA_PORT="${KAFKA_PORT:-39092}"
export API_PORT="${API_PORT:-38000}"
export FRONTEND_PORT="${FRONTEND_PORT:-33000}"
export KAFKA_FIXTURE_DIR="./build/${task_project}"
cleanup() {
    docker compose --profile tools down --volumes --remove-orphans >/dev/null
}
trap cleanup EXIT
mkdir -p "$KAFKA_FIXTURE_DIR"
docker compose build producer tests migrate api frontend frontend-tests
# Deterministic isolated UI states; this container starts its own fixture and Next servers.
docker compose run --rm --no-deps -T -e DASHBOARD_EXTERNAL_URL= frontend-tests
docker compose up -d --wait kafka postgres redis
docker compose run --rm -T migrate
docker compose run --rm -T kafka-init
docker compose up -d --no-deps --wait api
docker compose run --rm --no-deps -T producer --output kafka --steps 2 --reset-at-step 1 \
    > "$KAFKA_FIXTURE_DIR/producer-events.jsonl"
docker compose run --rm --no-deps -T tests python demo.py
docker compose up -d --no-deps --wait frontend
docker compose run --rm --no-deps -T -e DASHBOARD_EXTERNAL_URL=http://frontend:3000 \
    frontend-tests npm run test:real
printf 'Dashboard checks passed, including the real simulator-to-browser flow.\n'
