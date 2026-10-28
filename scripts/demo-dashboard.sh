#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
bash scripts/demo-api.sh
docker compose build frontend
docker compose up -d --no-deps --wait frontend
task_frontend_address="$(docker compose port frontend 3000)"
printf 'Dashboard: http://%s\n' "$task_frontend_address"
printf 'Select a device to inspect its telemetry and history.\n'
printf 'When finished: docker compose --profile tools down\n'
