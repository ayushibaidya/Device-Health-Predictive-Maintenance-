#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."

# No pulls/builds/installs. Default is preparation only, never an Ollama generation.
task_mode=prepare
task_save=false
for task_option in "$@"; do
    case "$task_option" in
        --generate) task_mode=generate ;;
        --save-report) task_save=true ;;
        *) printf '%s\n' '{"status":"fail","counts":{"passed":0,"failed":0,"skipped":0,"errors":1},"timings_seconds":{"total":0},"error_categories":["invalid_request"]}'; exit 2 ;;
    esac
done
task_image="${AI_INVESTIGATION_IMAGE:-device-health-ai-investigation:test}"
task_postgres_image="postgres@sha256:edb0c08dc33befd0262ab3b5cf1c4f3f8cfd8b09e88c05b45adee29d6761ddb6"
task_network=""
task_postgres=""
cleanup() {
    if [[ -n "$task_postgres" ]]; then docker rm -f "$task_postgres" >/dev/null 2>&1; fi
    if [[ -n "$task_network" ]]; then docker network rm "$task_network" >/dev/null 2>&1; fi
}
trap cleanup EXIT
missing_runtime() {
    printf '%s\n' '{"status":"fail","counts":{"passed":0,"failed":0,"skipped":0,"errors":1},"timings_seconds":{"total":0},"error_categories":["missing_runtime"]}'
    exit 2
}
docker image inspect "$task_image" "$task_postgres_image" >/dev/null 2>&1 || missing_runtime
[[ -n "${MINILM_MODEL_DIR:-}" && -d "$MINILM_MODEL_DIR" ]] || missing_runtime
[[ "$task_save" == false || "$task_mode" == generate ]] || missing_runtime
task_model="$(cd -- "$MINILM_MODEL_DIR" && pwd -P 2>/dev/null)" || missing_runtime
task_database="ai_investigation_$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
task_project="ai-investigation-demo-$$-${RANDOM}"
task_network="$(docker network create --internal "$task_project" 2>/dev/null)" || missing_runtime
task_postgres="$(docker run -d --pull never --network "$task_network" --network-alias postgres \
    --tmpfs /var/lib/postgresql:rw --name "${task_project}-postgres" \
    -e POSTGRES_DB="$task_database" -e POSTGRES_USER=ai_investigation_demo \
    -e POSTGRES_PASSWORD=isolated-test-only "$task_postgres_image" 2>/dev/null)" || missing_runtime
task_ready=false
for task_attempt in {1..30}; do
    if docker exec "$task_postgres" pg_isready -U ai_investigation_demo -d "$task_database" >/dev/null 2>&1; then
        task_ready=true
        break
    fi
    sleep 1
done
[[ "$task_ready" == true ]] || missing_runtime
task_report_mount=()
task_report_args=()
if [[ "$task_save" == true ]]; then
    mkdir -p build/ai-investigation/reports
    task_report_mount=(--volume "$PWD/build/ai-investigation/reports:/reports:rw")
    task_report_args=(--report-file /reports/report.json)
fi
task_status=0
task_output="$(docker run --rm --pull never --network "$task_network" --read-only --tmpfs /tmp:rw,nosuid,nodev \
    --user "$(id -u):$(id -g)" \
    --volume "$PWD:/workspace:ro" --volume "$task_model:/models/minilm:ro" \
    "${task_report_mount[@]}" --workdir /workspace/processing \
    -e DATABASE_URL= -e PGHOST=postgres -e PGDATABASE="$task_database" \
    -e PGUSER=ai_investigation_demo -e PGPASSWORD=isolated-test-only \
    "$task_image" python -m device_health_investigation.verification "$task_mode" \
    --model-dir /models/minilm --ollama-url http://host.docker.internal:11434 \
    "${task_report_args[@]}" 2>/dev/null)" || task_status=$?
printf '%s' "$task_output" | PYTHONPATH=processing python3 -B -c \
    'import sys; from device_health_investigation.verification import relay; raise SystemExit(relay(sys.stdin.read(4097), int(sys.argv[1])))' "$task_status"
