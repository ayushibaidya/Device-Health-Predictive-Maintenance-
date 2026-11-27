import copy
import fcntl
import hashlib
import json
from dataclasses import replace

import pytest

from device_health_investigation.__main__ import main
from device_health_investigation.chunking import ChunkingConfig
from device_health_investigation.documents import DocumentError
from device_health_investigation.embeddings import EmbeddingFailed, EmbeddingInputError, _validate_texts
from device_health_investigation.index import (
    IndexBusy,
    IndexInvalid,
    IndexUnavailable,
    build_index,
    load_index,
)


def digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode()).hexdigest()


def unit_vector(index=0):
    return [float(position == index) for position in range(384)]


class FakeEncoder:
    """Deterministic test-only vectors, with controllable failures and queries."""

    def __init__(self, tokenizer):
        self.tokenizer = tokenizer
        self.profile = {"test_only": True, "tokenizer_profile_id": tokenizer.profile_id}
        self.profile_id = digest(self.profile)
        self.calls = []
        self.rows = None
        self.query = unit_vector()
        self.fail = False
        self.on_encode = lambda: None

    def encode(self, texts):
        _validate_texts(texts, self.tokenizer)
        self.calls.append(tuple(texts))
        self.on_encode()
        if self.fail:
            raise EmbeddingFailed("test-only encoder failure")
        if texts == ["question"]:
            return [self.query]
        if self.rows is not None:
            return self.rows
        return [unit_vector(index) for index in range(len(texts))]


@pytest.fixture
def local_setup(tmp_path, corpus_factory, word_tokenizer):
    manifest = corpus_factory(
        "# Demo\n\n## Alpha\nTemperature observation.\n\n"
        "## Beta\nCPU observation.\n\n## Gamma\nError observation.\n\n"
        "## Delta\nLifecycle observation.\n"
    )
    word_tokenizer.profile_id = digest(word_tokenizer.profile)
    return tmp_path / "index" / "index.json", manifest, FakeEncoder(word_tokenizer), word_tokenizer


def change_document(manifest):
    data = json.loads(manifest.read_text())
    source = manifest.parent / data["documents"][0]["path"]
    source.write_text(source.read_text() + "\nAdditional reviewed test guidance.\n")
    data["documents"][0]["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(data))


def rewrite_index(path, envelope):
    envelope["index_id"] = digest(envelope["payload"])
    path.write_text(json.dumps(envelope))


def test_build_reload_and_exact_original_sources(local_setup):
    path, manifest, encoder, tokenizer = local_setup
    index, reused = build_index(*local_setup)
    assert not reused
    assert len(index.chunks) == 5
    assert len(encoder.calls) == 1
    assert load_index(*local_setup) == index
    source = (manifest.parent / "runbooks/demo.md").read_text()
    for chunk in index.chunks:
        assert chunk.text == source[chunk.start_char:chunk.end_char]
        assert chunk.start_line == source.count("\n", 0, chunk.start_char) + 1
        assert chunk.end_line == source.count("\n", 0, chunk.end_char - 1) + 1
        assert chunk.source_path == "runbooks/demo.md"
        assert chunk.document_version == hashlib.sha256(source.encode()).hexdigest()
    assert path.is_file()
    assert not list(path.parent.glob(".index.json.*.tmp"))


def test_unchanged_build_reuses_without_encoding_or_rewriting(local_setup):
    path, _, encoder, _ = local_setup
    first, _ = build_index(*local_setup)
    content, modified = path.read_bytes(), path.stat().st_mtime_ns
    encoder.fail = True
    second, reused = build_index(*local_setup)
    assert reused and first == second
    assert len(encoder.calls) == 1
    assert (path.read_bytes(), path.stat().st_mtime_ns) == (content, modified)


@pytest.mark.parametrize("problem", [
    "json", "checksum", "schema", "duplicate", "snapshot", "coerced_metadata",
])
def test_corrupt_index_is_rejected_and_explicit_build_can_repair(local_setup, problem):
    path, _, _, _ = local_setup
    original, _ = build_index(*local_setup)
    envelope = json.loads(path.read_text())
    if problem == "json":
        path.write_text("{broken")
    elif problem == "checksum":
        envelope["payload"]["vectors"][0][0] = 0.25
        path.write_text(json.dumps(envelope))
    elif problem == "schema":
        envelope["schema_version"] = 2
        path.write_text(json.dumps(envelope))
    elif problem == "duplicate":
        duplicate = '{"schema_version": 1, ' + json.dumps(envelope)[1:]
        assert json.loads(duplicate) == envelope  # Otherwise complete and checksum-valid.
        path.write_text(duplicate)
    elif problem == "snapshot":
        envelope["payload"]["chunks"][0]["text"] = "invented source text"
        rewrite_index(path, envelope)
    else:
        envelope["payload"]["context"]["embedding_profile"]["test_only"] = 1
        rewrite_index(path, envelope)
    expected_error = "Duplicate index JSON key" if problem == "duplicate" else None
    with pytest.raises(IndexInvalid, match=expected_error):
        load_index(*local_setup)
    repaired, reused = build_index(*local_setup)
    assert not reused and repaired == original


@pytest.mark.parametrize("bad_row", [
    [1.0], [0.0] * 384, [float("nan")] * 384, [float("inf")] * 384,
    [True] + [False] * 383,  # Unit length if coerced: only boolean rejection should fail.
])
def test_invalid_saved_vectors_rejected_even_with_recomputed_checksum(local_setup, bad_row):
    path, _, _, _ = local_setup
    build_index(*local_setup)
    envelope = json.loads(path.read_text())
    envelope["payload"]["vectors"][0] = bad_row
    if any(isinstance(value, float) and value != value for value in bad_row) or float("inf") in bad_row:
        path.write_text(json.dumps(envelope))  # Non-finite JSON must fail before checksum validation.
    else:
        rewrite_index(path, envelope)
    expected_error = (
        "Expected numeric 384-dimensional vectors"
        if any(isinstance(value, bool) for value in bad_row) else None
    )
    with pytest.raises(IndexInvalid, match=expected_error):
        load_index(*local_setup)


def test_missing_index_fails_without_implicitly_encoding(local_setup):
    _, _, encoder, _ = local_setup
    with pytest.raises(IndexUnavailable):
        load_index(*local_setup)
    assert encoder.calls == []


def test_altered_unapproved_source_is_rejected(local_setup):
    _, manifest, _, _ = local_setup
    build_index(*local_setup)
    (manifest.parent / "runbooks/demo.md").write_text("# Demo\nAltered without approval.")
    with pytest.raises(DocumentError, match="hash mismatch"):
        load_index(*local_setup)


def test_updated_source_requires_rebuild_and_old_reader_remains_immutable(local_setup):
    path, manifest, encoder, tokenizer = local_setup
    old, _ = build_index(*local_setup)
    old_text = old.chunks[-1].text
    change_document(manifest)
    with pytest.raises(IndexInvalid, match="stale"):
        load_index(*local_setup)
    new, reused = build_index(*local_setup)
    assert not reused
    assert new.index_id != old.index_id
    assert new.document_fingerprint != old.document_fingerprint
    assert load_index(path, manifest, encoder, tokenizer) == new
    assert old.chunks[-1].text == old_text
    assert old.search("question", encoder)


@pytest.mark.parametrize("change", ["model", "tokenizer", "chunking", "review_status"])
def test_profile_or_manifest_metadata_changes_invalidate_reuse(local_setup, change):
    path, manifest, encoder, tokenizer = local_setup
    old, _ = build_index(*local_setup)
    config = None
    if change == "model":
        encoder.profile["model_revision"] = "different-test-model"
        encoder.profile_id = digest(encoder.profile)
    elif change == "tokenizer":
        tokenizer.profile = {"test_only": "changed"}
        tokenizer.profile_id = digest(tokenizer.profile)
        encoder.profile["tokenizer_profile_id"] = tokenizer.profile_id
        encoder.profile_id = digest(encoder.profile)
    elif change == "chunking":
        config = ChunkingConfig(target_tokens=128)
    else:
        metadata = json.loads(manifest.read_text())
        metadata["review_status"] = "test-only-status-change"
        manifest.write_text(json.dumps(metadata))
    with pytest.raises(IndexInvalid, match="stale"):
        load_index(path, manifest, encoder, tokenizer, config)
    new, reused = build_index(path, manifest, encoder, tokenizer, config)
    assert not reused and new.index_id != old.index_id


def test_chunk_and_encoder_tokenizer_must_match(local_setup):
    path, manifest, encoder, tokenizer = local_setup
    encoder.profile["tokenizer_profile_id"] = "unrelated"
    encoder.profile_id = digest(encoder.profile)
    with pytest.raises(IndexInvalid, match="tokenizer profiles"):
        build_index(path, manifest, encoder, tokenizer)
    assert not path.exists()


def test_writer_contention_fails_without_replacing_old_index(local_setup):
    path, _, _, _ = local_setup
    build_index(*local_setup)
    content = path.read_bytes()
    lock = path.with_name(path.name + ".lock")
    with lock.open("r+b") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(IndexBusy):
            build_index(*local_setup)
        assert path.read_bytes() == content
    assert lock.is_file()
    assert load_index(*local_setup)


@pytest.mark.parametrize("failure", ["encoder", "invalid_vectors", "replace", "source_changed"])
def test_failed_rebuild_preserves_old_artifact_and_cleans_temporary_files(local_setup, monkeypatch, failure):
    path, manifest, encoder, tokenizer = local_setup
    original, _ = build_index(*local_setup)
    old_bytes = path.read_bytes()
    encoder.profile["rebuild_test"] = True
    encoder.profile_id = digest(encoder.profile)
    if failure == "encoder":
        encoder.fail = True
        expected = EmbeddingFailed
    elif failure == "invalid_vectors":
        encoder.rows = [[0.0] * 384] * len(original.chunks)
        expected = IndexInvalid
    elif failure == "source_changed":
        encoder.on_encode = lambda: change_document(manifest)
        expected = IndexInvalid
    else:
        def fail_replace(source, destination):
            assert load_index(path, manifest, old_encoder, tokenizer) == original
            raise OSError("test-only failed atomic publish")

        old_encoder = copy.copy(encoder)
        old_encoder.profile = {"test_only": True, "tokenizer_profile_id": tokenizer.profile_id}
        old_encoder.profile_id = digest(old_encoder.profile)
        monkeypatch.setattr("device_health_investigation.index.os.replace", fail_replace)
        expected = IndexUnavailable
    with pytest.raises(expected):
        build_index(path, manifest, encoder, tokenizer)
    assert path.read_bytes() == old_bytes
    assert not list(path.parent.glob(".index.json.*.tmp"))


def test_exact_cosine_ranking_including_negative_scores(local_setup):
    _, _, encoder, _ = local_setup
    encoder.rows = [
        [0.0, 1.0] + [0.0] * 382, [0.6, 0.8] + [0.0] * 382,
        [0.8, 0.6] + [0.0] * 382, unit_vector(), [-1.0] + [0.0] * 383,
    ]
    index, _ = build_index(*local_setup)
    hits = index.search("question", encoder)
    assert [hit.chunk for hit in hits] == [index.chunks[i] for i in [3, 2, 1]]
    assert [hit.rank for hit in hits] == [1, 2, 3]
    assert [hit.score for hit in hits] == pytest.approx([1.0, 0.8, 0.6])
    # This tests cosine calculation, not just a dot product of exactly unit inputs.
    scaled = replace(index, vectors=tuple(tuple(v * 1.000001 for v in row) for row in index.vectors))
    assert [hit.score for hit in scaled.search("question", encoder)] == pytest.approx([1.0, 0.8, 0.6])
    assert len(index.search("question", encoder, 1)) == 1


def test_equal_scores_use_chunk_id_tie_break_and_short_corpus_returns_fewer(local_setup):
    _, _, encoder, _ = local_setup
    encoder.rows = [unit_vector()] * 5
    index, _ = build_index(*local_setup)
    hits = index.search("question", encoder)
    assert [hit.chunk.chunk_id for hit in hits] == sorted(c.chunk_id for c in index.chunks)[:3]
    short = replace(index, chunks=index.chunks[:1], vectors=index.vectors[:1])
    assert len(short.search("question", encoder)) == 1


@pytest.mark.parametrize("limit", [0, 4, -1, True, "3"])
def test_invalid_search_limits_rejected(local_setup, limit):
    _, _, encoder, _ = local_setup
    index, _ = build_index(*local_setup)
    with pytest.raises(IndexInvalid, match="limit"):
        index.search("question", encoder, limit)


def test_invalid_query_and_changed_encoder_fail_explicitly(local_setup):
    _, _, encoder, _ = local_setup
    index, _ = build_index(*local_setup)
    with pytest.raises(EmbeddingInputError):
        index.search("", encoder)
    encoder.query = [0.0] * 384
    with pytest.raises(IndexInvalid, match="unit length"):
        index.search("question", encoder)
    encoder.profile["query_model"] = "different"
    encoder.profile_id = digest(encoder.profile)
    with pytest.raises(IndexInvalid, match="differs"):
        index.search("question", encoder)


def test_cli_build_search_and_missing_index_error(local_setup, monkeypatch, capsys):
    path, manifest, encoder, tokenizer = local_setup
    monkeypatch.setattr("device_health_investigation.__main__.MiniLMEncoder", lambda p: encoder)
    monkeypatch.setattr("device_health_investigation.__main__.MiniLMTokenizer", lambda p: tokenizer)
    shared = ["--manifest", str(manifest), "--model-dir", "test-model", "--index", str(path)]
    assert main(["build-index", *shared]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "built"
    assert main(["search", *shared, "--question", "question"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["relevance"] == "uncalibrated"
    assert len(output["candidates"]) == 3
    assert output["candidates"][0]["chunk"]["source_path"] == "runbooks/demo.md"
    path.unlink()
    assert main(["search", *shared, "--question", "question"]) == 1
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "invalid_index"
