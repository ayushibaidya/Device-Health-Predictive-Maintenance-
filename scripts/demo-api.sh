#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
bash scripts/demo-data.sh
docker compose build api
docker compose up -d --no-deps --wait api
docker compose run --rm --no-deps -T tests python demo_api.py
task_api_address="$(docker compose port api 8000)"
printf 'Interactive API docs: http://%s/docs\n' "$task_api_address"
printf 'Stop local services with: docker compose down\n'
