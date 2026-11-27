"""Local-only loading of the approved MiniLM serialized tokenizer, not weights."""

import hashlib
import json
from pathlib import Path

MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
TOKENIZER_SHA256 = "be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037"
TOKENIZERS_VERSION = "0.23.3"
MODEL_INPUT_LIMIT = 256


class TokenizerUnavailable(RuntimeError):
    """Optional tokenizer dependencies or approved local assets are unavailable."""


class MiniLMTokenizer:
    def __init__(self, tokenizer_path: str | Path):
        try:
            raw = Path(tokenizer_path).read_bytes()
        except OSError as error:
            raise TokenizerUnavailable("Provide the approved local tokenizer.json") from error
        if hashlib.sha256(raw).hexdigest() != TOKENIZER_SHA256:
            raise TokenizerUnavailable("Tokenizer asset does not match the approved revision")
        try:
            import tokenizers
        except (ImportError, OSError) as error:
            raise TokenizerUnavailable("Install the isolated chunking tools runtime") from error
        if tokenizers.__version__ != TOKENIZERS_VERSION:
            raise TokenizerUnavailable(f"Expected tokenizers=={TOKENIZERS_VERSION}")
        try:
            self._tokenizer = tokenizers.Tokenizer.from_str(raw.decode("utf-8"))
            # The published asset saves 128-token truncation/padding. Neither is
            # appropriate when checking the full 256-token sentence-model input.
            self._tokenizer.no_truncation()
            self._tokenizer.no_padding()
        except Exception as error:
            raise TokenizerUnavailable("Cannot initialize the approved local tokenizer") from error
        self.profile = {
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "asset_sha256": TOKENIZER_SHA256,
            "tokenizers_version": TOKENIZERS_VERSION,
            "truncation": False,
            "padding": False,
            "model_input_limit": MODEL_INPUT_LIMIT,
        }
        self.profile_id = hashlib.sha256(
            json.dumps(self.profile, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def token_spans(self, text: str) -> list[tuple[int, int]]:
        return self._tokenizer.encode(text, add_special_tokens=False).offsets

    def body_token_count(self, text: str) -> int:
        return len(self._tokenizer.encode(text, add_special_tokens=False).ids)

    def input_token_count(self, text: str) -> int:
        return len(self._tokenizer.encode(text, add_special_tokens=True).ids)
