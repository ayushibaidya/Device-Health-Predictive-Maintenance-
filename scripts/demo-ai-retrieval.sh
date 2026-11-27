#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."

task_image="${AI_RETRIEVAL_TEST_IMAGE:-device-health-ai-retrieval:test}"
task_model="${MINILM_MODEL_DIR:-$PWD/build/knowledge/models/1110a243fdf4706b3f48f1d95db1a4f5529b4d41}"
task_index="${AI_INDEX_DIR:-$PWD/build/knowledge}"
if ! docker image inspect "$task_image" >/dev/null 2>&1; then
    printf '%s\n' 'The optional retrieval image must already be built; see docs/ai-investigation-design.md.' >&2
    exit 2
fi
task_model="$(python3 -c 'import pathlib, sys; print(pathlib.Path(sys.argv[1]).resolve(strict=True))' "$task_model")"
mkdir -p -- "$task_index"
task_index="$(python3 -c 'import pathlib, sys; print(pathlib.Path(sys.argv[1]).resolve(strict=True))' "$task_index")"
task_repository="$(pwd -P)"
task_question="${1:-}"
if [[ $# -eq 0 ]]; then
    IFS= read -r -p 'Troubleshooting question: ' task_question
fi
run_cli() {
    docker run --rm --pull never --network none --read-only --tmpfs /tmp:rw,nosuid,nodev \
        --user "$(id -u):$(id -g)" \
        --volume "${task_repository}:/workspace:ro" \
        --volume "${task_model}:/models/minilm:ro" \
        --volume "${task_index}:/index:rw" \
        "$task_image" python -m device_health_investigation "$@" \
        --manifest /workspace/knowledge/manifest.json \
        --model-dir /models/minilm --index /index/index.json
}
run_cli build-index
run_cli search --question "$task_question"
