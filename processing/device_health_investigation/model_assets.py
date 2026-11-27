"""Verify/copy a pinned local model without any network or model runtime."""

import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath

from .tokenizer import MODEL_ID, MODEL_INPUT_LIMIT, MODEL_REVISION

DEFAULT_MANIFEST = Path(__file__).resolve().parents[2] / "knowledge/model-manifest.json"
REQUIRED_FILES = frozenset({
    "README.md", "config.json", "config_sentence_transformers.json", "modules.json",
    "model.safetensors", "sentence_bert_config.json", "special_tokens_map.json",
    "tokenizer.json", "tokenizer_config.json", "vocab.txt", "1_Pooling/config.json",
})


class ModelAssetError(ValueError):
    """The explicit local model does not match the repository's asset manifest."""


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ModelAssetError("Duplicate model manifest field")
        result[key] = value
    return result


def load_model_manifest(path=DEFAULT_MANIFEST):
    try:
        manifest = json.loads(Path(path).read_bytes().decode("utf-8"), object_pairs_hook=_object)
    except (OSError, UnicodeError, ValueError) as error:
        raise ModelAssetError("Cannot read the model asset manifest") from error
    if not isinstance(manifest, dict) or (
        type(manifest.get("schema_version")) is not int
        or manifest["schema_version"] != 1
        or manifest.get("model_id") != MODEL_ID
        or manifest.get("revision") != MODEL_REVISION
        or type(manifest.get("embedding_dimension")) is not int
        or manifest["embedding_dimension"] != 384
        or type(manifest.get("max_input_tokens")) is not int
        or manifest["max_input_tokens"] != MODEL_INPUT_LIMIT
        or manifest.get("weight_format") != "safetensors"
    ):
        raise ModelAssetError("Unsupported model manifest identity or profile")
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != len(REQUIRED_FILES):
        raise ModelAssetError("Model manifest must declare the 11 approved files")
    seen = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise ModelAssetError("Invalid model file metadata")
        name, size, digest = entry.get("path"), entry.get("bytes"), entry.get("sha256")
        if not isinstance(name, str) or name not in REQUIRED_FILES or name in seen:
            raise ModelAssetError("Unauthorized or duplicate model file path")
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or name != relative.as_posix():
            raise ModelAssetError("Invalid model file path")
        if type(size) is not int or size <= 0 or not isinstance(digest, str):
            raise ModelAssetError("Invalid model file size/hash")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ModelAssetError("Invalid model file hash")
        seen.add(name)
    return manifest


def _verify_files(root, manifest):
    for entry in manifest["files"]:
        path = root / entry["path"]
        try:
            if not path.is_file() or path.stat().st_size != entry["bytes"]:
                raise ModelAssetError(f"Missing or wrong-size model file: {entry['path']}")
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
        except OSError as error:
            raise ModelAssetError(f"Cannot read model file: {entry['path']}") from error
        if digest != entry["sha256"]:
            raise ModelAssetError(f"Model file hash mismatch: {entry['path']}")


def verify_prepared_model(model_dir, manifest_path=DEFAULT_MANIFEST):
    manifest = load_model_manifest(manifest_path)
    root = Path(model_dir)
    if root.is_symlink() or not root.is_dir():
        raise ModelAssetError("Provide an existing self-contained local model directory")
    actual = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ModelAssetError("Prepared model files/directories must not be symlinks")
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    if actual != REQUIRED_FILES:
        raise ModelAssetError("Prepared model contains missing or unexpected files")
    _verify_files(root, manifest)
    return manifest


def prepare_local_model(source_dir, destination_dir, manifest_path=DEFAULT_MANIFEST):
    """Dereference only allowlisted cached assets; never replace invalid data."""
    manifest = load_model_manifest(manifest_path)
    source, destination = Path(source_dir), Path(destination_dir)
    if destination.exists() or destination.is_symlink():
        verify_prepared_model(destination, manifest_path)
        return destination, False
    # Source symlinks are intentional in Hugging Face's snapshot/blob layout.
    _verify_files(source, manifest)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".minilm-", dir=destination.parent) as temporary:
            staging = Path(temporary) / "model"
            staging.mkdir()
            for entry in manifest["files"]:
                target = staging / entry["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / entry["path"], target, follow_symlinks=True)
            verify_prepared_model(staging, manifest_path)
            if destination.exists() or destination.is_symlink():
                verify_prepared_model(destination, manifest_path)
                return destination, False
            staging.rename(destination)
    except OSError as error:
        raise ModelAssetError("Could not publish the prepared local model directory") from error
    return destination, True
