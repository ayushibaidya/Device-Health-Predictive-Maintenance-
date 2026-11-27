"""Source-derived smoke expectations, frozen before observing model rankings."""

import json
import os

import pytest

from device_health_investigation.embeddings import MiniLMEncoder
from device_health_investigation.index import build_index, load_index
from device_health_investigation.tokenizer import MiniLMTokenizer

SUPPORTED_CASES = (
    ("Do rising temperature and power readings independently create alerts or prove thermal hardware failure?", "thermal-power"),
    ("Do CPU and memory percentages measure a real process or show a memory leak?", "cpu-memory"),
    ("Is error_count cumulative or can it fall during recovery?", "jitter-errors"),
    ("What does acknowledging an alert change and does it resolve the episode?", "alert-episodes"),
    ("Can I mix telemetry across run IDs after a FAILED device resets?", "lifecycle-firmware"),
    ("Does an old simulation timestamp prove the device is offline?", "telemetry-availability"),
)
UNSUPPORTED_QUESTION = "What are the recommended battery replacement intervals for this hardware?"


def test_real_six_document_index_and_candidate_retrieval(tmp_path, project_manifest):
    model_dir = os.getenv("MINILM_MODEL_DIR")
    if not model_dir:
        pytest.skip("Real retrieval requires explicit MINILM_MODEL_DIR and optional retrieval image")
    encoder = MiniLMEncoder(model_dir)
    tokenizer = MiniLMTokenizer(os.path.join(model_dir, "tokenizer.json"))
    path = tmp_path / "index.json"
    index, reused = build_index(path, project_manifest, encoder, tokenizer)
    assert not reused
    assert len({chunk.document_id for chunk in index.chunks}) == 6
    assert index.review_status == "source_checked_pending_owner_review"
    reloaded = load_index(path, project_manifest, encoder, tokenizer)
    assert reloaded == index
    rankings = []
    for question, expected_document in SUPPORTED_CASES:
        hits = index.search(question, encoder)
        assert 1 <= len(hits) <= 3
        document_ids = [hit.chunk.document_id for hit in hits]
        assert expected_document in document_ids, (question, expected_document, document_ids)
        assert reloaded.search(question, encoder) == hits
        for hit in hits:
            source = (project_manifest.parent / hit.chunk.source_path).read_text()
            assert source[hit.chunk.start_char:hit.chunk.end_char] == hit.chunk.text
            assert -1.0 <= hit.score <= 1.0
        rankings.append({"expected_document": expected_document, "candidates": document_ids})
    # No cutoff is claimed. Even an unsupported query gets candidates, not a diagnosis.
    unsupported = index.search(UNSUPPORTED_QUESTION, encoder)
    assert 1 <= len(unsupported) <= 3
    assert all(hit.chunk in index.chunks for hit in unsupported)
    reused_index, reused = build_index(path, project_manifest, encoder, tokenizer)
    assert reused and reused_index == index
    print(json.dumps({
        "retrieval_smoke": "passed", "documents": 6, "chunks": len(index.chunks),
        "supported_cases": rankings, "relevance": "uncalibrated", "index_id": index.index_id,
    }, sort_keys=True))
