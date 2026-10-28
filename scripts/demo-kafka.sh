#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
export KAFKA_FIXTURE_DIR=./build/kafka-integration

mkdir -p build/kafka-integration
docker compose build producer tests migrate
docker compose up -d --wait kafka postgres redis
docker compose run --rm -T migrate
docker compose run --rm -T kafka-init
docker compose run --rm --no-deps -T producer --output kafka --steps 2 --reset-at-step 1 \
    > build/kafka-integration/producer-events.jsonl
docker compose run --rm --no-deps -T tests python demo.py
printf 'Services remain available. Stop them with: docker compose --profile tools down\n'
