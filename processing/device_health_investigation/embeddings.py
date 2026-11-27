"""Minimal optional CPU MiniLM encoder; no index, retrieval or network fallback."""

import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path

from .model_assets import DEFAULT_MANIFEST, ModelAssetError, verify_prepared_model
from .tokenizer import MODEL_INPUT_LIMIT, MiniLMTokenizer, TokenizerUnavailable

RUNTIME_PINS = {
    "sentence-transformers": "6.3.0", "torch": "2.15.0+cpu",
    "transformers": "5.24.1", "numpy": "2.5.5", "tokenizers": "0.23.3",
}


class EmbeddingUnavailable(RuntimeError):
    """Explicit local model or optional runtime is missing/incompatible."""


class EmbeddingInputError(ValueError):
    """Text cannot be encoded without invalid input or silent truncation."""


class EmbeddingFailed(RuntimeError):
    """Local inference failed or produced invalid vectors."""


def _validate_texts(texts, tokenizer):
    if not isinstance(texts, (list, tuple)) or not texts:
        raise EmbeddingInputError("Provide a nonempty list/tuple of text strings")
    lengths = []
    for text in texts:
        if not isinstance(text, str) or not text.strip() or "\x00" in text:
            raise EmbeddingInputError("Embedding text must be a nonblank UTF-8 string")
        try:
            text.encode("utf-8")
        except UnicodeError as error:
            raise EmbeddingInputError("Embedding text must be valid UTF-8") from error
        length = tokenizer.input_token_count(text)
        if length > MODEL_INPUT_LIMIT:
            raise EmbeddingInputError("Embedding text exceeds the 256-token model input limit")
        lengths.append(length)
    return list(texts), lengths


class MiniLMEncoder:
    def __init__(self, model_dir, manifest_path=DEFAULT_MANIFEST):
        try:
            manifest = verify_prepared_model(model_dir, manifest_path)
            if platform.python_version() != "3.13.18":
                raise EmbeddingUnavailable("Use the pinned Python 3.13.18 retrieval image")
            versions = {name: importlib.metadata.version(name) for name in RUNTIME_PINS}
            if versions != RUNTIME_PINS:
                raise EmbeddingUnavailable("Embedding runtime does not match its reviewed pins")
            self._tokenizer = MiniLMTokenizer(Path(model_dir) / "tokenizer.json")
            import numpy as np
            import torch
            from sentence_transformers import SentenceTransformer

            torch.set_num_threads(2)
            self._model = SentenceTransformer(
                str(Path(model_dir).resolve()), device="cpu", backend="torch",
                local_files_only=True, trust_remote_code=False, token=False,
            )
            self._model.float()
            self._model.eval()
            if (
                self._model.get_embedding_dimension() != 384
                or self._model.max_seq_length != MODEL_INPUT_LIMIT
                or str(self._model.device) != "cpu"
            ):
                raise EmbeddingUnavailable("Local model does not match the approved MiniLM profile")
        except (ModelAssetError, TokenizerUnavailable, importlib.metadata.PackageNotFoundError) as error:
            raise EmbeddingUnavailable("Provide the prepared model and isolated retrieval runtime") from error
        except EmbeddingUnavailable:
            raise
        except Exception as error:
            raise EmbeddingUnavailable("Cannot initialize the approved local MiniLM encoder") from error
        self._np, self._torch = np, torch
        self.profile = {
            "model_id": manifest["model_id"], "revision": manifest["revision"],
            "files": {entry["path"]: entry["sha256"] for entry in manifest["files"]},
            "runtime": versions, "python": platform.python_version(),
            "platform": platform.system(), "architecture": platform.machine(),
            "device": "cpu", "precision": "float32", "dimensions": 384,
            "normalized": True, "batch_size": 16, "cpu_threads": 2,
            "max_input_tokens": MODEL_INPUT_LIMIT,
            "tokenizer_profile_id": self._tokenizer.profile_id,
        }
        self.profile_id = hashlib.sha256(
            json.dumps(self.profile, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def encode(self, texts):
        """Return normalized float32 NumPy rows, with no hidden input truncation."""
        texts, expected_lengths = _validate_texts(texts, self._tokenizer)
        try:
            with self._torch.inference_mode():
                for start in range(0, len(texts), 16):
                    features = self._model.preprocess(inputs=texts[start:start + 16])
                    actual = features["attention_mask"].sum(dim=1).tolist()
                    if actual != expected_lengths[start:start + 16]:
                        raise EmbeddingFailed("Model tokenizer differs from the verified 2A inputs")
                vectors = self._model.encode(
                    texts, batch_size=16, show_progress_bar=False, convert_to_numpy=True,
                    normalize_embeddings=True, precision="float32", device="cpu",
                )
            if (
                vectors.shape != (len(texts), 384)
                or vectors.dtype != self._np.dtype("float32")
                or not self._np.isfinite(vectors).all()
                or not self._np.allclose(self._np.linalg.norm(vectors, axis=1), 1.0, rtol=1e-5, atol=1e-5)
            ):
                raise EmbeddingFailed("MiniLM returned invalid or unnormalized 384-dimensional vectors")
            return vectors
        except EmbeddingFailed:
            raise
        except Exception as error:
            raise EmbeddingFailed("Local MiniLM encoding failed") from error
