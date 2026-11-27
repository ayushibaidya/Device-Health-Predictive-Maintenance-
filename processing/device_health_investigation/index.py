"""Rebuildable local JSON snapshots and exact cosine candidate search."""

import fcntl
import hashlib
import json
import math
import os
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

from .chunking import CHUNKER_VERSION, Chunk, ChunkingConfig, chunk_corpus
from .documents import load_corpus


class IndexInvalid(RuntimeError):
    """The index, vectors or fingerprints cannot be trusted for this corpus."""


class IndexUnavailable(IndexInvalid):
    """The local index cannot be read or published."""


class IndexBusy(IndexInvalid):
    """Another local process owns the index's writer lock."""


def _canonical(value):
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        raise IndexInvalid("Index metadata must be finite UTF-8 JSON") from error


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise IndexInvalid("Duplicate index JSON key")
        result[key] = value
    return result


def _invalid_constant(value):
    raise IndexInvalid("Non-finite index JSON value")


def _vectors(rows, count):
    """Convert encoder output or JSON into immutable, checked unit vectors."""
    try:
        if len(rows) != count:
            raise IndexInvalid("Index vector count does not match its chunks")
        result = []
        for row in rows:
            if len(row) != 384 or any(isinstance(value, (bool, str)) for value in row):
                raise IndexInvalid("Expected numeric 384-dimensional vectors")
            vector = tuple(float(value) for value in row)
            if not all(math.isfinite(value) for value in vector):
                raise IndexInvalid("Index vectors must be finite")
            norm = math.sqrt(math.fsum(value * value for value in vector))
            if not math.isclose(norm, 1.0, rel_tol=1e-5, abs_tol=1e-5):
                raise IndexInvalid("Index vectors must have unit length")
            result.append(vector)
        return tuple(result)
    except (TypeError, ValueError, OverflowError) as error:
        raise IndexInvalid("Malformed index vectors") from error


def _encoder_id(encoder):
    identity = _digest(encoder.profile)
    if identity != encoder.profile_id:
        raise IndexInvalid("Encoder profile fingerprint does not match its metadata")
    return identity


def _inputs(manifest_path, encoder, tokenizer, config):
    if (
        _digest(tokenizer.profile) != tokenizer.profile_id
        or encoder.profile.get("tokenizer_profile_id") != tokenizer.profile_id
    ):
        raise IndexInvalid("Chunk and encoder tokenizer profiles must match")
    manifest_path = Path(manifest_path)
    try:
        before = manifest_path.read_bytes()
        corpus = load_corpus(manifest_path)
        if before != manifest_path.read_bytes():
            raise IndexInvalid("Corpus manifest changed during validation")
    except OSError as error:
        raise IndexUnavailable("Cannot read the corpus manifest") from error
    chunks = chunk_corpus(corpus, tokenizer, config)
    if not chunks:
        raise IndexInvalid("Cannot build an index without chunks")
    context = {
        "corpus_manifest_sha256": hashlib.sha256(before).hexdigest(),
        "corpus": asdict(corpus),
        "embedding_profile": encoder.profile,
        "tokenizer_profile": tokenizer.profile,
        "chunking_profile": {"version": CHUNKER_VERSION, **asdict(config)},
    }
    fingerprints = {
        "model": _encoder_id(encoder),
        "tokenizer": _digest(tokenizer.profile),
        "chunking": _digest(context["chunking_profile"]),
        "documents": _digest({
            "manifest_sha256": context["corpus_manifest_sha256"], "corpus": context["corpus"],
        }),
    }
    expected = {
        "context": context, "fingerprints": fingerprints,
        "chunks": [asdict(chunk) for chunk in chunks],
    }
    # Freeze metadata as JSON now: later encoder mutations cannot alter the snapshot.
    return json.loads(_canonical(expected)), chunks


@dataclass(frozen=True)
class SearchHit:
    rank: int
    score: float
    chunk: Chunk


@dataclass(frozen=True)
class LocalIndex:
    index_id: str
    model_fingerprint: str
    document_fingerprint: str
    corpus_id: str
    review_status: str
    chunks: tuple[Chunk, ...]
    vectors: tuple[tuple[float, ...], ...]

    def search(self, question, encoder, limit=3):
        if type(limit) is not int or not 1 <= limit <= 3:
            raise IndexInvalid("Search limit must be an integer from one to three")
        if _encoder_id(encoder) != self.model_fingerprint:
            raise IndexInvalid("Query encoder differs from the indexed model/runtime")
        query = _vectors(encoder.encode([question]), 1)[0]
        query_norm = math.sqrt(math.fsum(value * value for value in query))
        scores = []
        for chunk, vector in zip(self.chunks, self.vectors, strict=True):
            norm = math.sqrt(math.fsum(value * value for value in vector))
            score = math.fsum(a * b for a, b in zip(query, vector, strict=True)) / (query_norm * norm)
            scores.append((max(-1.0, min(1.0, score)), chunk))
        scores.sort(key=lambda item: (-item[0], item[1].chunk_id))
        return tuple(SearchHit(rank, score, chunk) for rank, (score, chunk) in enumerate(
            scores[:limit], start=1,
        ))


def _read(path, expected, chunks):
    try:
        raw = Path(path).read_bytes()
    except OSError as error:
        raise IndexUnavailable("Cannot read local index; explicitly build it first") from error
    try:
        envelope = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_object, parse_constant=_invalid_constant,
        )
    except (ValueError, UnicodeError) as error:
        raise IndexInvalid("Invalid index JSON") from error
    if (
        not isinstance(envelope, dict)
        or set(envelope) != {"schema_version", "index_id", "payload"}
        or type(envelope["schema_version"]) is not int
        or envelope["schema_version"] != 1
    ):
        raise IndexInvalid("Unsupported index envelope/schema")
    payload = envelope["payload"]
    if not isinstance(payload, dict) or set(payload) != set(expected) | {"vectors"}:
        raise IndexInvalid("Invalid index payload")
    if envelope["index_id"] != _digest(payload):
        raise IndexInvalid("Index integrity checksum mismatch")
    if any(_canonical(payload[key]) != _canonical(value) for key, value in expected.items()):
        raise IndexInvalid("Index source/model/chunking profile is stale or incompatible; rebuild it")
    vectors = _vectors(payload["vectors"], len(chunks))
    corpus = payload["context"]["corpus"]
    return LocalIndex(
        envelope["index_id"], payload["fingerprints"]["model"],
        payload["fingerprints"]["documents"], corpus["corpus_id"], corpus["review_status"],
        chunks, vectors,
    )


def load_index(index_path, manifest_path, encoder, tokenizer, config=None):
    """Validate against current sources/profile; do not rebuild or encode."""
    expected, chunks = _inputs(manifest_path, encoder, tokenizer, config or ChunkingConfig())
    return _read(index_path, expected, chunks)


@contextmanager
def _writer_lock(path):
    descriptor = None
    try:
        descriptor = os.open(
            path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600,
        )
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise IndexBusy("Another process is building this index") from error
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)


def build_index(index_path, manifest_path, encoder, tokenizer, config=None):
    """Return (validated snapshot, reused); publish only a complete replacement."""
    path, config = Path(index_path), config or ChunkingConfig()
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _writer_lock(path.with_name(path.name + ".lock")):
            expected, chunks = _inputs(manifest_path, encoder, tokenizer, config)
            try:
                return _read(path, expected, chunks), True
            except IndexInvalid:
                pass  # Only an explicit build may replace a missing/invalid/stale artifact.
            vectors = _vectors(encoder.encode([chunk.model_input for chunk in chunks]), len(chunks))
            current, _ = _inputs(manifest_path, encoder, tokenizer, config)
            if current != expected:
                raise IndexInvalid("Corpus or encoding profile changed during the build")
            payload = {**expected, "vectors": vectors}
            envelope = {"schema_version": 1, "index_id": _digest(payload), "payload": payload}
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=path.parent, prefix="." + path.name + ".", suffix=".tmp", delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(_canonical(envelope) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            snapshot = _read(temporary, expected, chunks)
            os.replace(temporary, path)
            return snapshot, False
    except OSError as error:
        raise IndexUnavailable("Cannot lock, write or atomically publish the local index") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
