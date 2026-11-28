#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."

# Standalone development experiment; never relaxes the automatic relevance gate.
task_mode="${1:-prepare}"
if [[ $# -gt 0 ]]; then shift; fi
task_flags=()
task_confirm=false
fail_summary() {
    printf '{"status":"fail","counts":{"passed":0,"failed":0,"skipped":0,"errors":1},"timings_seconds":{"total":0},"error_categories":["%s"]}\n' "$1"
    exit 2
}
case "$task_mode" in probe|prepare|generate) ;; *) fail_summary invalid_request ;; esac
for task_option in "$@"; do
    case "$task_option" in
        --confirm-manual-excerpts) task_confirm=true; task_flags+=("$task_option") ;;
        --save-report) task_flags+=("$task_option") ;;
        *) fail_summary invalid_request ;;
    esac
done
[[ "$task_mode" == generate || ${#task_flags[@]} -eq 0 ]] || fail_summary invalid_request
[[ "$task_mode" != generate || "$task_confirm" == true ]] || fail_summary invalid_request
task_backend="${AI_EVIDENCE_TEST_IMAGE:-device-health-kafka-tests:latest}"
task_retrieval="${AI_RETRIEVAL_TEST_IMAGE:-device-health-ai-retrieval:test}"
task_postgres_image="postgres@sha256:edb0c08dc33befd0262ab3b5cf1c4f3f8cfd8b09e88c05b45adee29d6761ddb6"
task_network=""
task_postgres=""
dispose_db() {
    if [[ -n "$task_postgres" ]]; then docker rm -f "$task_postgres" >/dev/null 2>&1; task_postgres=""; fi
    if [[ -n "$task_network" ]]; then docker network rm "$task_network" >/dev/null 2>&1; task_network=""; fi
}
trap dispose_db EXIT
run_container() {
    local task_output task_status=0
    task_output="$(docker run --rm --pull never --read-only --tmpfs /tmp:rw,nosuid,nodev \
        --user "$(id -u):$(id -g)" --volume "$PWD:/workspace:ro" \
        --workdir /workspace/processing "$@" 2>/dev/null)" || task_status=$?
    printf '%s' "$task_output" | PYTHONPATH=processing python3 -B -c \
        'import sys; from device_health_investigation.verification import relay; raise SystemExit(relay(sys.stdin.read(4097), int(sys.argv[1])))' "$task_status"
}
if [[ "$task_mode" == probe ]]; then
    docker image inspect "$task_retrieval" >/dev/null 2>&1 || fail_summary missing_runtime
    run_container --network bridge "$task_retrieval" python manual_investigation_smoke.py probe
    exit
fi
docker image inspect "$task_retrieval" >/dev/null 2>&1 || fail_summary missing_runtime
task_model="${MINILM_MODEL_DIR:-$PWD/build/knowledge/models/1110a243fdf4706b3f48f1d95db1a4f5529b4d41}"
[[ -d "$task_model" ]] || fail_summary missing_runtime
task_model="$(cd -- "$task_model" 2>/dev/null && pwd -P)" || fail_summary missing_runtime
task_requested_artifacts="${AI_MANUAL_RUN_DIR:-$PWD/build/ai-investigation/manual-smoke}"
task_artifacts="$(python3 -B - "$task_requested_artifacts" <<'PY'
import pathlib,sys
try:
    root=(pathlib.Path.cwd()/'build/ai-investigation').resolve()
    directory=pathlib.Path(sys.argv[1]).resolve()
    if not directory.is_relative_to(root) or directory==root:
        raise ValueError()
    directory.mkdir(parents=True,mode=0o700,exist_ok=True)
    if directory.stat().st_mode & 0o077:
        raise ValueError()
    print(directory)
except Exception:
    raise SystemExit(1)
PY
)" || fail_summary invalid_request
if [[ "$task_mode" == prepare ]]; then
    [[ ! -e "$task_artifacts/evidence.json" ]] || fail_summary invalid_request
    docker image inspect "$task_backend" "$task_postgres_image" >/dev/null 2>&1 || fail_summary missing_runtime
    task_database="ai_investigation_$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
    task_network="$(docker network create --internal "ai-manual-smoke-$$-${RANDOM}" 2>/dev/null)" || fail_summary setup_failed
    task_postgres="$(docker run -d --pull never --network "$task_network" --network-alias postgres \
        --tmpfs /var/lib/postgresql:rw -e POSTGRES_DB="$task_database" \
        -e POSTGRES_USER=ai_investigation_demo -e POSTGRES_PASSWORD=isolated-test-only \
        "$task_postgres_image" 2>/dev/null)" || fail_summary setup_failed
    task_ready=false
    for task_attempt in {1..30}; do
        if docker exec "$task_postgres" pg_isready -U ai_investigation_demo -d "$task_database" >/dev/null 2>&1; then
            task_ready=true
            break
        fi
        sleep 1
    done
    [[ "$task_ready" == true ]] || fail_summary setup_failed
    run_container --network "$task_network" --volume "$task_artifacts:/artifacts:rw" \
        -e DATABASE_URL= -e PGHOST=postgres -e PGDATABASE="$task_database" \
        -e PGUSER=ai_investigation_demo -e PGPASSWORD=isolated-test-only \
        "$task_backend" python manual_investigation_smoke.py packet
    dispose_db
    run_container --network none --volume "$task_artifacts:/artifacts:ro" \
        --volume "$task_model:/models/minilm:ro" \
        "$task_retrieval" python manual_investigation_smoke.py prepare
else
    [[ -f "$task_artifacts/evidence.json" ]] || fail_summary invalid_request
    # No database environment/network exists in this phase; only a local fixture mount.
    run_container --network bridge --volume "$task_artifacts:/artifacts:rw" \
        --volume "$task_model:/models/minilm:ro" \
        "$task_retrieval" python manual_investigation_smoke.py generate "${task_flags[@]}"
fi
