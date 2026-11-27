"""Deterministic heading-aware chunks with exact, original source spans."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass

from .documents import Corpus, Document
from .tokenizer import MODEL_INPUT_LIMIT, MiniLMTokenizer

CHUNKER_VERSION = 1
_HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.+?)[ \t]*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


class ChunkingError(ValueError):
    """Source or context cannot be represented within the configured limits."""


@dataclass(frozen=True)
class ChunkingConfig:
    target_tokens: int = 192
    overlap_tokens: int = 32
    max_input_tokens: int = MODEL_INPUT_LIMIT

    def __post_init__(self):
        values = (self.target_tokens, self.overlap_tokens, self.max_input_tokens)
        if (
            any(type(value) is not int for value in values)
            or not 2 < self.target_tokens <= self.max_input_tokens <= MODEL_INPUT_LIMIT
            or not 0 <= self.overlap_tokens < self.target_tokens - 2
        ):
            raise ChunkingError("Invalid target, overlap or model input limit")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    document_version: str
    source_path: str
    title: str
    heading_path: tuple[str, ...]
    start_char: int
    end_char: int
    start_line: int
    end_line: int
    text: str
    model_input: str
    input_token_count: int
    overlap_token_count: int
    tokenizer_profile_id: str


def _sections(text):
    start, offset, headings, path, fence = 0, 0, [], (), None
    for line in text.splitlines(keepends=True):
        fence_match = _FENCE.match(line)
        if fence is not None:
            if (
                fence_match
                and fence_match[1][0] == fence[0]
                and len(fence_match[1]) >= fence[1]
                and not fence_match[2].strip()
            ):
                fence = None
        elif fence_match:
            fence = (fence_match[1][0], len(fence_match[1]))
        else:
            match = _HEADING.match(line)
            if match:
                if offset > start:
                    yield start, offset, path
                level = len(match[1])
                label = re.sub(r"[ \t]+#+[ \t]*$", "", match[2])
                headings = [(depth, title) for depth, title in headings if depth < level]
                headings.append((level, label))
                start, path = offset, tuple(title for _, title in headings)
        offset += len(line)
    if offset > start:
        yield start, offset, path


def _boundaries(text, tokenizer):
    # Keep overlapping normalization offsets together. Cutting at the next token
    # start also retains intervening original combining/control characters.
    boundaries, previous_end = [0], 0
    for start, end in tokenizer.token_spans(text):
        if not 0 <= start < end <= len(text):
            raise ChunkingError("Tokenizer produced an invalid source span")
        if start > boundaries[-1] and start >= previous_end:
            boundaries.append(start)
        previous_end = max(previous_end, end)
    if previous_end == 0:
        raise ChunkingError("Source section has no usable tokens")
    boundaries.append(len(text))
    return boundaries


def chunk_document(
    document: Document, tokenizer: MiniLMTokenizer, config: ChunkingConfig | None = None
) -> tuple[Chunk, ...]:
    config = config or ChunkingConfig()
    result = []
    for section_start, section_end, path in _sections(document.text):
        original = document.text[section_start:section_end]
        leading = len(original) - len(original.lstrip())
        section = original.strip()
        if not section:
            continue
        base = section_start + leading
        context = " > ".join(path)
        prefix = document.title + ("\n" + context if context != document.title else "") + "\n\n"
        points = _boundaries(section, tokenizer)
        units, start, previous_end = len(points) - 1, 0, 0
        estimate = max(1, config.target_tokens - tokenizer.input_token_count(prefix))

        def candidate(left, right):
            body = section[points[left]:points[right]].rstrip()
            return body, prefix + body

        while start < units:
            end = min(units, start + estimate)
            body, model_input = candidate(start, end)
            count = tokenizer.input_token_count(model_input)
            while count > config.target_tokens and end > start + 1:
                end -= 1
                body, model_input = candidate(start, end)
                count = tokenizer.input_token_count(model_input)
            if count > config.target_tokens:
                raise ChunkingError("Title/heading context leaves no room for a source chunk")
            while end < units:
                larger_body, larger_input = candidate(start, end + 1)
                larger_count = tokenizer.input_token_count(larger_input)
                if larger_count > config.target_tokens:
                    break
                end += 1
                body, model_input, count = larger_body, larger_input, larger_count
            if count > config.max_input_tokens:
                raise ChunkingError("Chunk exceeds the model input limit")
            low, high = base + points[start], base + points[start] + len(body)
            overlap = tokenizer.body_token_count(document.text[low:previous_end])
            if overlap > config.overlap_tokens:
                raise ChunkingError("Chunk overlap exceeds its token budget")
            identity = {
                "chunker_version": CHUNKER_VERSION,
                "config": asdict(config),
                "tokenizer_profile_id": tokenizer.profile_id,
                "document_id": document.document_id,
                "document_version": document.document_version,
                "source_path": document.source_path,
                "span": [low, high],
                "input_sha256": hashlib.sha256(model_input.encode()).hexdigest(),
            }
            chunk_id = hashlib.sha256(
                json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            result.append(
                Chunk(
                    chunk_id, document.document_id, document.document_version,
                    document.source_path, document.title, path, low, high,
                    document.text.count("\n", 0, low) + 1,
                    document.text.count("\n", 0, high - 1) + 1,
                    body, model_input, count, overlap, tokenizer.profile_id,
                )
            )
            previous_end = high
            if end == units:
                break
            following = end
            for index in range(end - 1, start, -1):
                shared = section[points[index]:points[start] + len(body)]
                if tokenizer.body_token_count(shared) > config.overlap_tokens:
                    break
                following = index
            start = following
    return tuple(result)


def chunk_corpus(corpus: Corpus, tokenizer: MiniLMTokenizer, config=None) -> tuple[Chunk, ...]:
    return tuple(
        chunk
        for document in corpus.documents
        for chunk in chunk_document(document, tokenizer, config)
    )
