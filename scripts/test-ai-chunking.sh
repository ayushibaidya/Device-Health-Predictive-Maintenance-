#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."

task_image="${AI_CHUNKING_TEST_IMAGE:-device-health-ai-chunking:test}"
if ! docker image inspect "$task_image" >/dev/null 2>&1; then
    printf '%s\n' 'Build the optional image first: docker build -f processing/Dockerfile.chunking -t device-health-ai-chunking:test .'
    exit 2
fi
if [[ -z "${MINILM_TOKENIZER_PATH:-}" ]]; then
    printf '%s\n' 'Set MINILM_TOKENIZER_PATH to the approved local tokenizer.json. No assets are downloaded.'
    exit 2
fi
task_tokenizer="$(python3 -c 'import pathlib, sys; print(pathlib.Path(sys.argv[1]).resolve(strict=True))' "$MINILM_TOKENIZER_PATH")"
task_repository="$(pwd -P)"
run_tools() {
    docker run --rm --pull never --network none --read-only --tmpfs /tmp:rw,nosuid,nodev \
        --volume "${task_repository}:/workspace:ro" \
        --volume "${task_tokenizer}:/models/tokenizer.json:ro" \
        -e MINILM_TOKENIZER_PATH=/models/tokenizer.json \
        -e HF_HUB_OFFLINE=1 -e HF_HUB_DISABLE_TELEMETRY=1 \
        "$task_image" "$@"
}
run_tools python -m ruff check --no-cache device_health_investigation tests/investigation
run_tools python -m pytest --confcutdir=tests/investigation tests/investigation \
    -q -o cache_dir=/tmp/pytest-cache
