import hashlib
import json
import os
import re
from pathlib import Path

import pytest

from device_health_investigation.documents import Document
from device_health_investigation.tokenizer import MiniLMTokenizer


@pytest.fixture
def corpus_factory(tmp_path):
    def create(text="# Demo\n\n## Findings\nRead the device evidence.\n"):
        root = tmp_path / "knowledge"
        sources = root / "runbooks"
        sources.mkdir(parents=True, exist_ok=True)
        raw = text.encode("utf-8")
        (sources / "demo.md").write_bytes(raw)
        manifest = {
            "schema_version": 1,
            "corpus_id": "test-corpus",
            "language": "en",
            "synthetic": True,
            "implementation_baseline": "2b919b72a19364079076a3950292ef92b4da4dcb",
            "review_status": "source_checked_pending_owner_review",
            "documents": [{
                "document_id": "demo", "title": "Demo", "path": "runbooks/demo.md",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "implementation_refs": ["simulator/src/simulator.cpp"],
            }],
        }
        path = root / "manifest.json"
        path.write_text(json.dumps(manifest))
        return path
    return create


@pytest.fixture
def document_factory():
    def create(text):
        return Document(
            "demo", "Demo", "runbooks/demo.md", hashlib.sha256(text.encode()).hexdigest(), text
        )
    return create


class WordTokenizer:
    """Logic-test fake only; production chunking requires the pinned MiniLM asset."""

    profile_id = "test-tokenizer-profile"
    profile = {"test_only": True}

    def token_spans(self, text):
        return [(m.start(), m.end()) for m in re.finditer(r"\w+|[^\w\s]", text)]

    def body_token_count(self, text):
        return len(self.token_spans(text))

    def input_token_count(self, text):
        return self.body_token_count(text) + 2


@pytest.fixture
def word_tokenizer():
    return WordTokenizer()


@pytest.fixture
def real_tokenizer():
    path = os.getenv("MINILM_TOKENIZER_PATH")
    if not path:
        pytest.skip("Real tokenizer requires explicit MINILM_TOKENIZER_PATH and optional tools")
    # An explicit opt-in must fail if provisioning is wrong; never silently skip it.
    return MiniLMTokenizer(path)


@pytest.fixture
def project_manifest():
    return Path(__file__).resolve().parents[3] / "knowledge" / "manifest.json"
