import json
import shutil

import pytest

from device_health_investigation.model_assets import (
    ModelAssetError,
    load_model_manifest,
    prepare_local_model,
    verify_prepared_model,
)
from device_health_investigation.tokenizer import MODEL_REVISION


def test_repository_model_manifest_pins_complete_profile():
    manifest = load_model_manifest()
    assert manifest["revision"] == MODEL_REVISION
    assert manifest["embedding_dimension"] == 384
    assert manifest["max_input_tokens"] == 256
    assert manifest["license"] == "Apache-2.0"
    assert len(manifest["files"]) == 11
    assert sum(entry["bytes"] for entry in manifest["files"]) == 91_578_415


def test_preparation_dereferences_allowlisted_files_and_reuses_destination(model_cache):
    source, destination, manifest_path = model_cache
    # Unrelated cached files are never published into the prepared model.
    (source / "unapproved.txt").write_text("not a model asset")
    prepared, created = prepare_local_model(source, destination, manifest_path)
    assert prepared == destination
    assert created is True
    assert not any(path.is_symlink() for path in prepared.rglob("*"))
    assert not (prepared / "unapproved.txt").exists()
    verify_prepared_model(prepared, manifest_path)
    timestamps = {path: path.stat().st_mtime_ns for path in prepared.rglob("*")}
    # A valid prepared directory remains usable after the original cache moves.
    reused, created = prepare_local_model(source / "missing", destination, manifest_path)
    assert reused == prepared and created is False
    assert timestamps == {path: path.stat().st_mtime_ns for path in prepared.rglob("*")}


@pytest.mark.parametrize("problem", ["missing", "altered"])
def test_missing_or_altered_cached_file_never_publishes_destination(model_cache, problem):
    source, destination, manifest_path = model_cache
    target = source / "model.safetensors"
    if problem == "missing":
        target.unlink()
    else:
        raw = target.read_bytes()
        target.write_bytes(b"X" + raw[1:])  # Same length: hash, not size, must reject it.
    with pytest.raises(ModelAssetError, match="Missing or wrong-size|hash mismatch"):
        prepare_local_model(source, destination, manifest_path)
    assert not destination.exists()


def test_incompatible_destination_is_preserved(model_cache):
    source, destination, manifest_path = model_cache
    destination.mkdir()
    sentinel = destination / "owner-file"
    sentinel.write_bytes(b"preserve me")
    with pytest.raises(ModelAssetError, match="missing or unexpected"):
        prepare_local_model(source, destination, manifest_path)
    assert sentinel.read_bytes() == b"preserve me"
    assert list(destination.iterdir()) == [sentinel]


def test_copy_failure_cleans_only_temporary_output(model_cache, monkeypatch):
    source, destination, manifest_path = model_cache
    copyfile = shutil.copyfile
    copied = []

    def fail_copy(source_file, destination_file, **kwargs):
        if copied:
            raise OSError("test-only interrupted copy")
        result = copyfile(source_file, destination_file, **kwargs)
        copied.append(destination_file)
        return result

    monkeypatch.setattr("device_health_investigation.model_assets.shutil.copyfile", fail_copy)
    with pytest.raises(ModelAssetError, match="Could not publish"):
        prepare_local_model(source, destination, manifest_path)
    assert len(copied) == 1
    assert not destination.exists()
    assert not list(destination.parent.glob(".minilm-*"))
    assert (source / "model.safetensors").is_file()


@pytest.mark.parametrize("problem", ["root_symlink", "file_symlink", "extra", "altered"])
def test_prepared_model_rejects_symlinks_extra_or_altered_files(model_cache, problem):
    source, destination, manifest_path = model_cache
    prepare_local_model(source, destination, manifest_path)
    if problem == "root_symlink":
        alias = destination.parent / "alias"
        alias.symlink_to(destination, target_is_directory=True)
        destination = alias
    elif problem == "file_symlink":
        target = destination / "config.json"
        target.unlink()
        target.symlink_to(source / "config.json")
    elif problem == "extra":
        (destination / "unexpected.py").write_text("unapproved")
    else:
        (destination / "config.json").write_text("altered")
    with pytest.raises(ModelAssetError):
        verify_prepared_model(destination, manifest_path)


@pytest.mark.parametrize("problem", [
    "revision", "dimensions", "limit", "traversal", "duplicate_path", "missing", "bad_hash",
])
def test_manifest_rejects_unapproved_profile_and_file_metadata(model_cache, problem):
    _, _, manifest_path = model_cache
    manifest = json.loads(manifest_path.read_text())
    if problem == "revision":
        manifest["revision"] = "unapproved-revision"
    elif problem == "dimensions":
        manifest["embedding_dimension"] = 768
    elif problem == "limit":
        manifest["max_input_tokens"] = 512
    elif problem == "traversal":
        manifest["files"][0]["path"] = "../outside"
    elif problem == "duplicate_path":
        manifest["files"][1] = manifest["files"][0]
    elif problem == "missing":
        manifest["files"].pop()
    else:
        manifest["files"][0]["sha256"] = "not-a-hash"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ModelAssetError):
        load_model_manifest(manifest_path)


def test_duplicate_manifest_keys_are_rejected(model_cache):
    _, _, manifest_path = model_cache
    valid = load_model_manifest(manifest_path)
    duplicate = '{"schema_version": 1, ' + manifest_path.read_text()[1:]
    assert json.loads(duplicate) == valid  # Only the repeated key makes this invalid.
    manifest_path.write_text(duplicate)
    with pytest.raises(ModelAssetError, match="Cannot read the model asset manifest") as caught:
        load_model_manifest(manifest_path)
    assert isinstance(caught.value.__cause__, ModelAssetError)
    assert str(caught.value.__cause__) == "Duplicate model manifest field"
