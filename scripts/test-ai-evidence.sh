#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."

# Reuse the existing backend dependencies; never pull, build or install here.
task_image="${AI_EVIDENCE_TEST_IMAGE:-device-health-kafka-tests:latest}"
task_postgres_image="postgres@sha256:edb0c08dc33befd0262ab3b5cf1c4f3f8cfd8b09e88c05b45adee29d6761ddb6"
docker image inspect "$task_image" "$task_postgres_image" >/dev/null
task_repository="$(pwd -P)"
task_project="device-health-ai-evidence-test-$$-${RANDOM}"
task_network=""
task_postgres=""
cleanup() {
    if [[ -n "$task_postgres" ]]; then docker rm -f "$task_postgres" >/dev/null; fi
    if [[ -n "$task_network" ]]; then docker network rm "$task_network" >/dev/null; fi
}
trap cleanup EXIT
run_tools() {
    docker run --rm --pull never --read-only --tmpfs /tmp:rw,nosuid,nodev \
        --volume "${task_repository}:/workspace:ro" --workdir /workspace/processing \
        "$@"
}
run_tools --network none "$task_image" python -m pip --no-cache-dir check
run_tools --network none "$task_image" python -m ruff check --no-cache \
    device_health_investigation device_health_ingestion device_health_alerts device_health_api tests \
    demo.py demo_data.py demo_api.py demo_alerts.py
run_tools --network none "$task_image" python -m pytest -m 'not integration' \
    -q -o cache_dir=/tmp/pytest-cache

task_network="$(docker network create --internal "$task_project")"
task_postgres="$(docker run -d --pull never --network "$task_network" --network-alias postgres \
    --tmpfs /var/lib/postgresql:rw --name "${task_project}-postgres" \
    -e POSTGRES_DB=evidence_test -e POSTGRES_USER=evidence_test \
    -e POSTGRES_PASSWORD=isolated-test-only "$task_postgres_image")"
task_ready=false
for task_attempt in {1..30}; do
    if docker exec "$task_postgres" pg_isready -h 127.0.0.1 -U evidence_test -d evidence_test >/dev/null 2>&1; then
        task_ready=true
        break
    fi
    sleep 1
done
if [[ "$task_ready" != true ]]; then
    printf '%s\n' 'Disposable PostgreSQL did not become ready.' >&2
    exit 1
fi
run_tools --network "$task_network" \
    -e DATABASE_URL= -e PGHOST=postgres -e PGDATABASE=evidence_test \
    -e PGUSER=evidence_test -e PGPASSWORD=isolated-test-only \
    "$task_image" python -m pytest -m integration -q -o cache_dir=/tmp/pytest-cache \
    tests/test_investigation_evidence_integration.py tests/test_alerts_integration.py
printf '%s\n' 'Isolated evidence and existing alert verification passed.'
