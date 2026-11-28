import os
import shutil
from pathlib import Path

import pytest

import manual_investigation_smoke as smoke
from device_health_investigation.reporting import AIUnavailable


@pytest.mark.skipif(not os.getenv("MINILM_MODEL_DIR"), reason="Explicit cached tokenizer required")
def test_manually_selected_original_excerpts_are_pinned_and_within_token_limit():
    root = Path(__file__).resolve().parents[3]
    chunks = smoke.selected_chunks(root / "knowledge/manifest.json",
                                   Path(os.environ["MINILM_MODEL_DIR"]) / "tokenizer.json")
    assert tuple((chunk.document_id, chunk.chunk_id) for chunk in chunks) == smoke.EXCERPTS
    for chunk in chunks:
        text = (root / "knowledge" / chunk.source_path).read_text()
        assert text[chunk.start_char:chunk.end_char] == chunk.text
        assert chunk.input_token_count <= 192


@pytest.mark.skipif(not os.getenv("MINILM_MODEL_DIR"), reason="Explicit cached tokenizer required")
def test_altered_source_excerpts_fail_closed_without_updating_corpus(tmp_path):
    root = Path(__file__).resolve().parents[3]
    target = tmp_path / "knowledge"
    shutil.copytree(root / "knowledge", target)
    path = target / "runbooks/thermal-power.md"
    path.write_text(path.read_text() + "\nUnreviewed change.\n")
    with pytest.raises(AIUnavailable):
        smoke.selected_chunks(target / "manifest.json", Path(os.environ["MINILM_MODEL_DIR"]) / "tokenizer.json")
