"""Size-only cross-runtime check of a fresh synthetic PostgreSQL fixture."""

import json
import os
from pathlib import Path

import pytest

from device_health_investigation.embeddings import MiniLMEncoder
from device_health_investigation.index import build_index
from device_health_investigation.investigation import retrieval_query
from device_health_investigation.reporting import GenerationLimits, prepare_messages, prepare_sources
from device_health_investigation.tokenizer import MiniLMTokenizer


@pytest.mark.skipif(not (os.getenv("MINILM_MODEL_DIR") and os.getenv("AI_SYNTHETIC_EVIDENCE_PATH")),
                    reason="Requires the disposable synthetic database handoff and local model")
def test_two_reading_snapshot_and_real_top_three_candidates_fit_approved_budget(tmp_path):
    root = Path(__file__).resolve().parents[3]
    evidence = json.loads(Path(os.environ["AI_SYNTHETIC_EVIDENCE_PATH"]).read_text())
    assert evidence["device_id"] == "ai-local-demo" and evidence["evidence"]["reading_count"] == 2
    model = Path(os.environ["MINILM_MODEL_DIR"])
    encoder, tokenizer = MiniLMEncoder(model), MiniLMTokenizer(model / "tokenizer.json")
    index, _ = build_index(tmp_path / "index.json", root / "knowledge/manifest.json", encoder, tokenizer)
    candidates = index.search(retrieval_query(evidence), encoder, limit=3)
    assert len(candidates) == 3
    packet, _ = prepare_sources(evidence, candidates)
    messages, _ = prepare_messages(packet, GenerationLimits())
    assert len(json.dumps(messages, ensure_ascii=False).encode()) <= 12000
    # Size compatibility does not approve the candidates and never invokes a provider.
