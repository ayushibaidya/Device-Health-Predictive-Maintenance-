import hashlib
import json
import subprocess
import sys

import pytest

from device_health_investigation.__main__ import main
from device_health_investigation.documents import DocumentError, load_corpus


def update(path, change):
    manifest = json.loads(path.read_text())
    change(manifest)
    path.write_text(json.dumps(manifest))


def test_valid_document_preserves_exact_text_and_review_state(corpus_factory):
    text = "# Demo\r\n\r\n## Findings\r\nCafé and 中文 evidence.\r\n"
    corpus = load_corpus(corpus_factory(text))
    assert len(corpus.documents) == 1
    assert corpus.documents[0].text == text
    assert corpus.documents[0].document_version == hashlib.sha256(text.encode()).hexdigest()
    assert corpus.review_status == "source_checked_pending_owner_review"


def test_real_six_runbooks_validate_without_approving_them(project_manifest):
    corpus = load_corpus(project_manifest)
    assert len(corpus.documents) == 6
    assert corpus.review_status == "source_checked_pending_owner_review"
    assert {doc.document_id for doc in corpus.documents} == {
        "thermal-power", "cpu-memory", "jitter-errors", "alert-episodes",
        "lifecycle-firmware", "telemetry-availability",
    }


@pytest.mark.parametrize("action", ["alter", "remove"])
def test_altered_or_missing_document_is_rejected(corpus_factory, action):
    path = corpus_factory()
    source = path.parent / "runbooks/demo.md"
    if action == "alter":
        source.write_text(source.read_text() + "Unauthorized diagnosis.\n")
    else:
        source.unlink()
    with pytest.raises(DocumentError, match="hash mismatch|Cannot read"):
        load_corpus(path)


@pytest.mark.parametrize("name", ["document_id", "title", "path", "sha256", "implementation_refs"])
def test_required_document_metadata(corpus_factory, name):
    path = corpus_factory()
    update(path, lambda value: value["documents"][0].pop(name))
    with pytest.raises(DocumentError):
        load_corpus(path)


@pytest.mark.parametrize("name", ["corpus_id", "review_status", "implementation_baseline"])
def test_required_corpus_metadata(corpus_factory, name):
    path = corpus_factory()
    update(path, lambda value: value.pop(name))
    with pytest.raises(DocumentError):
        load_corpus(path)


@pytest.mark.parametrize("source", ["../outside.md", "/tmp/outside.md", "runbooks/../demo.md", "runbooks\\demo.md", "runbooks/demo.txt"])
def test_unauthorized_paths_are_rejected(corpus_factory, source):
    path = corpus_factory()
    update(path, lambda value: value["documents"][0].update(path=source))
    with pytest.raises(DocumentError, match="relative path|Markdown"):
        load_corpus(path)


def test_symlink_escape_is_rejected_before_reading_target(corpus_factory, tmp_path):
    path = corpus_factory()
    outside = tmp_path / "outside.md"
    outside.write_text("# Demo\nUnreviewed content")
    source = path.parent / "runbooks/demo.md"
    source.unlink()
    source.symlink_to(outside)
    with pytest.raises(DocumentError, match="escapes"):
        load_corpus(path)


def test_unlisted_file_never_becomes_an_ingestion_source(corpus_factory):
    path = corpus_factory()
    # Not UTF-8: loading/validating it would fail if the loader read arbitrary files.
    (path.parent / "runbooks/unlisted.md").write_bytes(b"\xff")
    corpus = load_corpus(path)
    assert [doc.source_path for doc in corpus.documents] == ["runbooks/demo.md"]


def test_duplicate_ids_or_paths_rejected(corpus_factory):
    path = corpus_factory()
    update(path, lambda value: value["documents"].append(dict(value["documents"][0])))
    with pytest.raises(DocumentError, match="Duplicate"):
        load_corpus(path)


@pytest.mark.parametrize("case", ["invalid_json", "duplicate_key", "bad_schema", "bad_hash", "bad_title", "invalid_utf8"])
def test_invalid_manifest_or_document_content(corpus_factory, case):
    path = corpus_factory()
    if case == "invalid_json":
        path.write_text("{")
    elif case == "duplicate_key":
        path.write_text(path.read_text().replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1'))
    elif case == "bad_schema":
        update(path, lambda value: value.update(schema_version=True))
    elif case == "bad_hash":
        update(path, lambda value: value["documents"][0].update(sha256="not-a-hash"))
    elif case == "bad_title":
        update(path, lambda value: value["documents"][0].update(title="Another title"))
    else:
        raw = b"# Demo\n\xff"
        (path.parent / "runbooks/demo.md").write_bytes(raw)
        update(path, lambda value: value["documents"][0].update(sha256=hashlib.sha256(raw).hexdigest()))
    with pytest.raises(DocumentError):
        load_corpus(path)


def test_cli_validation_and_invalid_corpus_exit_codes(corpus_factory, capsys):
    path = corpus_factory()
    assert main(["validate", "--manifest", str(path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["review_status"] == "source_checked_pending_owner_review"
    assert len(output["documents"]) == 1
    update(path, lambda value: value["documents"][0].update(sha256="0" * 64))
    assert main(["validate", "--manifest", str(path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["error"]["code"] == "invalid_corpus"


def test_cli_missing_tokenizer_is_explicit_operational_failure(corpus_factory, tmp_path, capsys):
    assert main(["chunk", "--manifest", str(corpus_factory()), "--tokenizer", str(tmp_path / "missing.json")]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["error"]["code"] == "tokenizer_unavailable"


def test_import_does_not_load_optional_model_runtime():
    result = subprocess.run([
        sys.executable, "-B", "-c",
        "import sys; import device_health_investigation.__main__; "
        "assert all(name not in sys.modules for name in ['tokenizers', 'torch', 'transformers'])",
    ], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
