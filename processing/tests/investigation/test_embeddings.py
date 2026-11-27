import importlib.metadata
import json
import os
import subprocess
import sys

import pytest

from device_health_investigation.embeddings import (
    RUNTIME_PINS,
    EmbeddingInputError,
    EmbeddingUnavailable,
    MiniLMEncoder,
    _validate_texts,
)
from device_health_investigation.tokenizer import MiniLMTokenizer


@pytest.mark.parametrize("texts", [
    None, "not a batch", [], [""], ["  \n"], [42], ["bad\x00text"], ["\ud800"],
])
def test_invalid_embedding_inputs_are_rejected(texts, word_tokenizer):
    with pytest.raises(EmbeddingInputError):
        _validate_texts(texts, word_tokenizer)


def test_embedding_token_limit_includes_special_tokens(word_tokenizer):
    at_limit = "word " * 254
    texts, lengths = _validate_texts((at_limit,), word_tokenizer)
    assert texts == [at_limit]
    assert lengths == [256]
    with pytest.raises(EmbeddingInputError, match="256-token"):
        _validate_texts(["word " * 255], word_tokenizer)


def test_missing_model_is_explicit_and_does_not_initialize_runtime(tmp_path):
    with pytest.raises(EmbeddingUnavailable, match="prepared model"):
        MiniLMEncoder(tmp_path / "missing")


def test_wrong_python_version_is_rejected_before_runtime_imports(model_cache, monkeypatch):
    source, destination, manifest_path = model_cache
    from device_health_investigation.model_assets import prepare_local_model

    prepare_local_model(source, destination, manifest_path)
    monkeypatch.setattr("device_health_investigation.embeddings.platform.python_version", lambda: "3.12.0")
    with pytest.raises(EmbeddingUnavailable, match="Python 3.13.18"):
        MiniLMEncoder(destination, manifest_path)


@pytest.mark.parametrize("problem", ["missing", "mismatched"])
def test_missing_or_wrong_runtime_is_explicit(model_cache, monkeypatch, problem):
    source, destination, manifest_path = model_cache
    from device_health_investigation.model_assets import prepare_local_model

    prepare_local_model(source, destination, manifest_path)
    monkeypatch.setattr("device_health_investigation.embeddings.platform.python_version", lambda: "3.13.18")

    def version(name):
        if name == "sentence-transformers":
            if problem == "missing":
                raise importlib.metadata.PackageNotFoundError(name)
            return "0.0.0"
        return RUNTIME_PINS[name]

    monkeypatch.setattr("device_health_investigation.embeddings.importlib.metadata.version", version)
    with pytest.raises(EmbeddingUnavailable):
        MiniLMEncoder(destination, manifest_path)


def test_importing_encoder_does_not_load_optional_heavy_libraries():
    result = subprocess.run(
        [sys.executable, "-B", "-c", (
            "import sys; import device_health_investigation.embeddings; "
            "assert not {'torch', 'numpy', 'sentence_transformers', 'transformers'} & sys.modules.keys()"
        )], capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_real_local_minilm_embedding_smoke():
    model_dir = os.getenv("MINILM_MODEL_DIR")
    if not model_dir:
        pytest.skip("Real embeddings require explicit MINILM_MODEL_DIR and optional retrieval image")
    # Explicit opt-in must fail for missing assets/dependencies, never silently skip.
    encoder = MiniLMEncoder(model_dir)
    import numpy as np

    texts = [
        "The simulator reports WARNING. Review error_count and the alert opening evidence.",
        "A FAILED device returns to HEALTHY in a new lifecycle; do not mix the two runs.",
        "hello " * 200,  # Longer than tokenizer.json's legacy 128-token truncation.
    ]
    first = encoder.encode(texts)
    second = encoder.encode(texts)
    assert first.shape == (3, 384)
    assert first.dtype == np.dtype("float32")
    assert np.isfinite(first).all()
    norms = np.linalg.norm(first, axis=1)
    assert np.allclose(norms, 1.0, rtol=1e-5, atol=1e-5)
    assert np.allclose(first, second, rtol=1e-5, atol=1e-6)
    assert np.allclose(first[:1], encoder.encode(texts[:1]), rtol=1e-5, atol=1e-6)
    tokenizer = MiniLMTokenizer(os.path.join(model_dir, "tokenizer.json"))
    features = encoder._model.preprocess(inputs=texts)
    for index, text in enumerate(texts):
        actual = features["input_ids"][index][features["attention_mask"][index].bool()].tolist()
        assert actual == tokenizer._tokenizer.encode(text, add_special_tokens=True).ids
    with pytest.raises(EmbeddingInputError, match="256-token"):
        encoder.encode(["hello " * 255])
    assert encoder.profile["runtime"] == RUNTIME_PINS
    assert encoder.profile["device"] == "cpu"
    print(json.dumps({
        "smoke": "passed", "shape": list(first.shape), "dtype": str(first.dtype),
        "norm_min": float(norms.min()), "norm_max": float(norms.max()),
        "profile_id": encoder.profile_id, "runtime": encoder.profile["runtime"],
    }, sort_keys=True))
