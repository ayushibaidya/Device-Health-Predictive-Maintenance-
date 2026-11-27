#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."

task_image="${AI_RETRIEVAL_TEST_IMAGE:-device-health-ai-retrieval:test}"
if ! docker image inspect "$task_image" >/dev/null 2>&1; then
    printf '%s\n' 'Build the optional image yourself: docker build -f processing/Dockerfile.retrieval -t device-health-ai-retrieval:test .'
    exit 2
fi
if [[ -z "${MINILM_MODEL_DIR:-}" ]]; then
    printf '%s\n' 'Set MINILM_MODEL_DIR to the prepared, self-contained MiniLM directory.'
    exit 2
fi
task_model="$(python3 -c 'import pathlib, sys; print(pathlib.Path(sys.argv[1]).resolve(strict=True))' "$MINILM_MODEL_DIR")"
task_repository="$(pwd -P)"
run_tools() {
    docker run --rm --pull never --network none --read-only --tmpfs /tmp:rw,nosuid,nodev \
        --volume "${task_repository}:/workspace:ro" \
        --volume "${task_model}:/models/minilm:ro" \
        -e MINILM_MODEL_DIR=/models/minilm \
        -e MINILM_TOKENIZER_PATH=/models/minilm/tokenizer.json \
        "$task_image" "$@"
}
run_tools python -m pip --no-cache-dir check
run_tools python -m ruff check --no-cache device_health_investigation tests/investigation ../scripts/prepare-ai-model.py
run_tools python -m pytest --confcutdir=tests/investigation tests/investigation \
    -q -s -W error::FutureWarning -o cache_dir=/tmp/pytest-cache
