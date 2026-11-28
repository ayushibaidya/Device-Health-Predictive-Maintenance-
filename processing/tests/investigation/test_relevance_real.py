import os
from dataclasses import replace
from pathlib import Path

import pytest

from device_health_investigation.embeddings import MiniLMEncoder
from device_health_investigation.index import build_index
from device_health_investigation.relevance import calibrate, load_evaluation
from device_health_investigation.tokenizer import MiniLMTokenizer


@pytest.mark.skipif(not os.getenv("MINILM_MODEL_DIR"), reason="Optional local model required")
def test_real_development_gate_stays_disabled_until_explicit_held_out_evaluation(tmp_path):
    root = Path(__file__).resolve().parents[3]
    model = Path(os.environ["MINILM_MODEL_DIR"])
    encoder, tokenizer = MiniLMEncoder(model), MiniLMTokenizer(model / "tokenizer.json")
    index, _ = build_index(tmp_path / "index.json", root / "knowledge/manifest.json", encoder, tokenizer)
    evaluation = load_evaluation(root / "knowledge/evaluation/relevance-v1.json",
                                 {chunk.document_id for chunk in index.chunks})
    # Regression runs must not inspect held-out scores while refining development policy.
    gate = calibrate(index, encoder, replace(evaluation, held_out=()))
    assert gate.evaluation_fingerprint == evaluation.fingerprint
    assert gate.index_id == index.index_id
    assert gate.held_out.passed == gate.held_out.failed == 0
    assert not gate.enabled
    candidates = index.search(evaluation.development[0].question, encoder)
    assert gate("question", candidates, index.index_id) == ()
