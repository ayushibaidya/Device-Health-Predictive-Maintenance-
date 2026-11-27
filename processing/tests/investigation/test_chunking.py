import hashlib
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from device_health_investigation.chunking import ChunkingConfig, ChunkingError, chunk_corpus, chunk_document
from device_health_investigation.documents import load_corpus
from device_health_investigation.tokenizer import MiniLMTokenizer, TokenizerUnavailable
from device_health_investigation import tokenizer as tokenizer_module


def assert_source_spans(document, chunks):
    covered = set()
    for chunk in chunks:
        assert chunk.text == document.text[chunk.start_char:chunk.end_char]
        assert chunk.start_line == document.text.count("\n", 0, chunk.start_char) + 1
        assert chunk.end_line == document.text.count("\n", 0, chunk.end_char - 1) + 1
        assert chunk.document_version == document.document_version
        assert chunk.source_path == document.source_path
        covered.update(range(chunk.start_char, chunk.end_char))
    assert all(index in covered for index, value in enumerate(document.text) if not value.isspace())


def test_long_section_hits_target_and_preserves_overlap(document_factory, word_tokenizer):
    document = document_factory("# Demo\n\n## Findings\n" + "reading " * 700)
    chunks = chunk_document(document, word_tokenizer)
    assert_source_spans(document, chunks)
    assert any(chunk.input_token_count == 192 for chunk in chunks)
    assert all(chunk.input_token_count <= 192 for chunk in chunks)
    assert all(0 <= chunk.overlap_token_count <= 32 for chunk in chunks)
    assert any(chunk.overlap_token_count == 32 for chunk in chunks)
    for previous, current in zip(chunks, chunks[1:]):
        if previous.heading_path == current.heading_path:
            shared = document.text[current.start_char:previous.end_char]
            assert word_tokenizer.body_token_count(shared) == current.overlap_token_count


def test_heading_boundaries_do_not_share_overlap(document_factory, word_tokenizer):
    document = document_factory("# Demo\nIntro.\n## First\nAlpha.\n### Nested\nBeta.\n## Second\nGamma.\n")
    chunks = chunk_document(document, word_tokenizer)
    assert [chunk.heading_path for chunk in chunks] == [
        ("Demo",), ("Demo", "First"), ("Demo", "First", "Nested"), ("Demo", "Second"),
    ]
    assert all(chunk.overlap_token_count == 0 for chunk in chunks)
    assert_source_spans(document, chunks)


@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_heading_like_code_is_preserved_inside_its_section(document_factory, word_tokenizer, fence):
    document = document_factory(f"# Demo\n\n## Findings\n{fence}\n## Not a heading\n{fence}\nEvidence.\n")
    chunks = chunk_document(document, word_tokenizer)
    assert len(chunks) == 2
    assert "## Not a heading" in chunks[1].text
    assert chunks[1].heading_path == ("Demo", "Findings")
    assert_source_spans(document, chunks)


def test_unicode_crlf_and_missing_final_newline_preserve_locations(document_factory, word_tokenizer):
    document = document_factory("# Demo\r\n\r\n## Findings\r\n" + "Café cafe\u0301 中文 🛠 evidence. " * 100)
    chunks = chunk_document(document, word_tokenizer)
    assert_source_spans(document, chunks)


def test_repeatable_ids_and_profile_or_source_changes(document_factory, word_tokenizer):
    document = document_factory("# Demo\n\n## Findings\n" + "reading " * 400)
    first = chunk_document(document, word_tokenizer)
    assert first == chunk_document(document, word_tokenizer)
    assert len({chunk.chunk_id for chunk in first}) == len(first)
    changed = chunk_document(document_factory(document.text + "New evidence."), word_tokenizer)
    assert {chunk.chunk_id for chunk in first}.isdisjoint(chunk.chunk_id for chunk in changed)
    word_tokenizer.profile_id = "different-test-profile"
    assert {chunk.chunk_id for chunk in first}.isdisjoint(
        chunk.chunk_id for chunk in chunk_document(document, word_tokenizer)
    )


def test_complete_input_includes_context_and_special_tokens(document_factory, word_tokenizer):
    document = document_factory("# Demo\n\n## Findings\n" + "reading " * 400)
    chunks = chunk_document(document, word_tokenizer, ChunkingConfig(target_tokens=256))
    assert max(chunk.input_token_count for chunk in chunks) == 256
    assert all(chunk.input_token_count == word_tokenizer.input_token_count(chunk.model_input) for chunk in chunks)
    assert all(chunk.input_token_count <= 256 for chunk in chunks)


def test_zero_overlap_advances_without_losing_content(document_factory, word_tokenizer):
    document = document_factory("# Demo\n\n## Findings\n" + "reading " * 700)
    chunks = chunk_document(document, word_tokenizer, ChunkingConfig(overlap_tokens=0))
    assert all(chunk.overlap_token_count == 0 for chunk in chunks)
    assert_source_spans(document, chunks)


def test_oversized_context_and_invalid_limit_fail_without_truncation(document_factory, word_tokenizer):
    document = document_factory("# Demo\n\n## " + "heading " * 300 + "\nEvidence.\n")
    with pytest.raises(ChunkingError, match="context"):
        chunk_document(document, word_tokenizer)
    with pytest.raises(ChunkingError, match="Invalid"):
        ChunkingConfig(target_tokens=257, max_input_tokens=257)


def test_missing_and_unapproved_tokenizer_assets_fail(tmp_path):
    with pytest.raises(TokenizerUnavailable, match="Provide"):
        MiniLMTokenizer(tmp_path / "missing.json")
    path = tmp_path / "tokenizer.json"
    path.write_text("{}")
    with pytest.raises(TokenizerUnavailable, match="approved revision"):
        MiniLMTokenizer(path)


@pytest.mark.parametrize("case", ["missing_dependency", "native_failure"])
def test_tokenizer_runtime_failures_are_explicit(tmp_path, monkeypatch, case):
    path = tmp_path / "tokenizer.json"
    raw = b"test-only asset"
    path.write_bytes(raw)
    monkeypatch.setattr(tokenizer_module, "TOKENIZER_SHA256", hashlib.sha256(raw).hexdigest())
    if case == "missing_dependency":
        monkeypatch.setitem(sys.modules, "tokenizers", None)
    else:
        def broken_loader(_):
            raise Exception("Native tokenizer initialization failed")
        monkeypatch.setitem(sys.modules, "tokenizers", SimpleNamespace(
            __version__="0.23.3", Tokenizer=SimpleNamespace(from_str=broken_loader),
        ))
    with pytest.raises(TokenizerUnavailable, match="runtime|initialize"):
        MiniLMTokenizer(path)


def test_real_minilm_disables_saved_truncation_and_padding(real_tokenizer):
    assert real_tokenizer.input_token_count("hello " * 200) == 202
    assert real_tokenizer.input_token_count("hello") == 3
    assert real_tokenizer.profile["truncation"] is False
    assert real_tokenizer.profile["padding"] is False


def test_real_minilm_subword_unicode_spans_and_overlap(real_tokenizer, document_factory):
    document = document_factory("# Demo\n\n## Findings\n" + "electromechanical café cafe\u0301 中文 🛠 evidence. " * 160)
    chunks = chunk_document(document, real_tokenizer)
    assert chunks == chunk_document(document, real_tokenizer)
    assert_source_spans(document, chunks)
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)
    assert all(chunk.input_token_count <= 192 for chunk in chunks)
    assert all(chunk.input_token_count == real_tokenizer.input_token_count(chunk.model_input) for chunk in chunks)
    assert all(chunk.overlap_token_count <= 32 for chunk in chunks)
    assert any(chunk.overlap_token_count > 0 for chunk in chunks)


def test_real_runbooks_chunk_and_cli_repeat_exactly(real_tokenizer, project_manifest):
    corpus = load_corpus(project_manifest)
    chunks = chunk_corpus(corpus, real_tokenizer)
    assert {chunk.document_id for chunk in chunks} == {doc.document_id for doc in corpus.documents}
    for doc in corpus.documents:
        assert_source_spans(doc, [chunk for chunk in chunks if chunk.document_id == doc.document_id])
    assert all(chunk.input_token_count <= 192 for chunk in chunks)
    assert corpus.review_status == "source_checked_pending_owner_review"
    command = [sys.executable, "-B", "-m", "device_health_investigation", "chunk", "--manifest", str(project_manifest), "--tokenizer", os.environ["MINILM_TOKENIZER_PATH"]]
    first = subprocess.run(command, capture_output=True, text=True)
    second = subprocess.run(command, capture_output=True, text=True)
    assert first.returncode == second.returncode == 0, first.stderr + second.stderr
    assert first.stdout == second.stdout
    output = json.loads(first.stdout)
    assert output["review_status"] == "source_checked_pending_owner_review"
    assert len(output["chunks"]) == len(chunks)
