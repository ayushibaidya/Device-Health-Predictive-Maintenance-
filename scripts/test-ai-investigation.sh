#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."

# Cached images only. Each Python invocation validates its aggregate before printing.
task_backend="${AI_EVIDENCE_TEST_IMAGE:-device-health-kafka-tests:latest}"
task_retrieval="${AI_RETRIEVAL_TEST_IMAGE:-device-health-ai-retrieval:test}"
task_postgres_image="postgres@sha256:edb0c08dc33befd0262ab3b5cf1c4f3f8cfd8b09e88c05b45adee29d6761ddb6"
task_network=""
task_postgres=""
task_fixture=""
cleanup() {
    if [[ -n "$task_postgres" ]]; then docker rm -f "$task_postgres" >/dev/null 2>&1; fi
    if [[ -n "$task_network" ]]; then docker network rm "$task_network" >/dev/null 2>&1; fi
    if [[ -n "$task_fixture" ]]; then
        python3 -B -c 'import shutil,sys; shutil.rmtree(sys.argv[1])' "$task_fixture" 2>/dev/null
    fi
}
trap cleanup EXIT
missing_runtime() {
    printf '%s\n' '{"status":"fail","counts":{"passed":0,"failed":0,"skipped":0,"errors":1},"timings_seconds":{"total":0},"error_categories":["missing_runtime"]}'
    exit 2
}
docker image inspect "$task_backend" "$task_retrieval" "$task_postgres_image" >/dev/null 2>&1 || missing_runtime
[[ -n "${MINILM_MODEL_DIR:-}" && -d "$MINILM_MODEL_DIR" ]] || missing_runtime
task_model="$(cd -- "$MINILM_MODEL_DIR" && pwd -P 2>/dev/null)" || missing_runtime
task_fixture="$(mktemp -d "${TMPDIR:-/tmp}/ai-investigation-fixture.XXXXXX" 2>/dev/null)" || missing_runtime
relay() {
    printf '%s' "$1" | PYTHONPATH=processing python3 -B -c \
        'import sys; from device_health_investigation.verification import relay; raise SystemExit(relay(sys.stdin.read(4097), int(sys.argv[1])))' "$2"
}
run_backend() {
    local task_output task_status=0
    task_output="$(docker run --rm --pull never --read-only --tmpfs /tmp:rw,nosuid,nodev \
        --user "$(id -u):$(id -g)" --volume "$task_fixture:/verification:rw" \
        -e AI_SYNTHETIC_EVIDENCE_PATH=/verification/evidence.json \
        --volume "$PWD:/workspace:ro" --workdir /workspace/processing \
        "$@" 2>/dev/null)" || task_status=$?
    relay "$task_output" "$task_status"
}
run_backend --network none "$task_backend" python -m device_health_investigation.verification backend
task_project="ai-investigation-verification-$$-${RANDOM}"
task_network="$(docker network create --internal "$task_project" 2>/dev/null)" || missing_runtime
task_postgres="$(docker run -d --pull never --network "$task_network" --network-alias postgres \
    --tmpfs /var/lib/postgresql:rw --name "${task_project}-postgres" \
    -e POSTGRES_DB=evidence_test -e POSTGRES_USER=evidence_test \
    -e POSTGRES_PASSWORD=isolated-test-only "$task_postgres_image" 2>/dev/null)" || missing_runtime
task_ready=false
for task_attempt in {1..30}; do
    if docker exec "$task_postgres" pg_isready -U evidence_test -d evidence_test >/dev/null 2>&1; then
        task_ready=true
        break
    fi
    sleep 1
done
[[ "$task_ready" == true ]] || missing_runtime
run_backend --network "$task_network" -e DATABASE_URL= -e PGHOST=postgres \
    -e PGDATABASE=evidence_test -e PGUSER=evidence_test -e PGPASSWORD=isolated-test-only \
    "$task_backend" python -m device_health_investigation.verification database
run_retrieval() {
    local task_output task_status=0
    task_output="$(docker run --rm --pull never --network none --read-only --tmpfs /tmp:rw,nosuid,nodev \
        --user "$(id -u):$(id -g)" --volume "$task_fixture:/verification:ro" \
        -e AI_SYNTHETIC_EVIDENCE_PATH=/verification/evidence.json \
        --volume "$PWD:/workspace:ro" --volume "$task_model:/models/minilm:ro" \
        --workdir /workspace/processing -e MINILM_MODEL_DIR=/models/minilm \
        -e MINILM_TOKENIZER_PATH=/models/minilm/tokenizer.json \
        "$task_retrieval" python -m device_health_investigation.verification "$@" 2>/dev/null)" || task_status=$?
    relay "$task_output" "$task_status"
}
run_retrieval retrieval
# A failed evaluation intentionally exits nonzero after the test phases above pass.
run_retrieval calibrate
