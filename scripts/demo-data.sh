#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
bash scripts/demo-kafka.sh
docker compose run --rm --no-deps -T tests python demo_data.py
