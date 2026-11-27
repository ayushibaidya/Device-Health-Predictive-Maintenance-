"""Validate the manifest allowlist before returning any source documents."""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class DocumentError(ValueError):
    """The corpus or a declared source does not match its reviewed manifest."""


@dataclass(frozen=True)
class Document:
    document_id: str
    title: str
    source_path: str
    document_version: str
    text: str


@dataclass(frozen=True)
class Corpus:
    corpus_id: str
    review_status: str
    implementation_baseline: str
    documents: tuple[Document, ...]


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DocumentError("Manifest contains a duplicate JSON key")
        result[key] = value
    return result


def _text(value, name):
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise DocumentError(f"Invalid {name} metadata")
    try:
        value.encode("utf-8")
    except UnicodeError as error:
        raise DocumentError(f"Invalid Unicode {name} metadata") from error
    return value


def _relative(value, name):
    value = _text(value, name)
    path = PurePosixPath(value)
    if (
        not path.parts
        or path.is_absolute()
        or "\\" in value
        or ":" in value
        or ".." in path.parts
        or value != path.as_posix()
    ):
        raise DocumentError(f"{name} must be a normalized relative path")
    return path


def load_corpus(manifest_path: str | Path) -> Corpus:
    """Read only listed Markdown files; preserve pending review as metadata."""
    manifest_path = Path(manifest_path)
    try:
        manifest = json.loads(
            manifest_path.read_bytes().decode("utf-8"), object_pairs_hook=_object
        )
    except (OSError, UnicodeError, ValueError) as error:
        raise DocumentError("Cannot read a valid UTF-8 JSON manifest") from error
    if not isinstance(manifest, dict):
        raise DocumentError("Manifest must be an object")
    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise DocumentError("Unsupported manifest schema_version")
    if manifest.get("synthetic") is not True or manifest.get("language") != "en":
        raise DocumentError("Expected the English synthetic troubleshooting corpus")
    corpus_id = _text(manifest.get("corpus_id"), "corpus_id")
    review_status = _text(manifest.get("review_status"), "review_status")
    baseline = _text(manifest.get("implementation_baseline"), "implementation_baseline")
    if not re.fullmatch(r"[0-9a-f]{40}", baseline):
        raise DocumentError("Invalid implementation_baseline")
    entries = manifest.get("documents")
    if not isinstance(entries, list) or not entries:
        raise DocumentError("Manifest documents must be a nonempty list")

    # Validate every allowlist entry before reading any document content.
    declared = []
    identifiers, paths = set(), set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise DocumentError("Document metadata must be an object")
        identifier = _text(entry.get("document_id"), "document_id")
        if not re.fullmatch(r"[a-z][a-z0-9-]*", identifier):
            raise DocumentError("Invalid document_id")
        title = _text(entry.get("title"), "title")
        relative = _relative(entry.get("path"), "Document path")
        if relative.suffix != ".md":
            raise DocumentError("Only allowlisted Markdown documents are supported")
        digest = _text(entry.get("sha256"), "sha256")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise DocumentError("Invalid document sha256")
        references = entry.get("implementation_refs")
        if not isinstance(references, list) or not references:
            raise DocumentError("Missing implementation_refs metadata")
        for reference in references:
            _relative(reference, "Implementation reference")
        if identifier in identifiers or relative.as_posix() in paths:
            raise DocumentError("Duplicate document ID or path")
        identifiers.add(identifier)
        paths.add(relative.as_posix())
        declared.append((identifier, title, relative, digest))

    root = manifest_path.parent.resolve()
    documents, resolved_paths = [], set()
    for identifier, title, relative, digest in declared:
        try:
            source = (root / relative).resolve(strict=True)
            if not source.is_relative_to(root):
                raise DocumentError("Document path escapes the corpus root")
            if source in resolved_paths:
                raise DocumentError("Document paths alias the same source file")
            resolved_paths.add(source)
            raw = source.read_bytes()
        except (OSError, RuntimeError) as error:
            raise DocumentError(f"Cannot read declared document: {relative}") from error
        if hashlib.sha256(raw).hexdigest() != digest:
            raise DocumentError(f"Document hash mismatch: {relative}")
        try:
            text = raw.decode("utf-8")
        except UnicodeError as error:
            raise DocumentError(f"Document is not UTF-8: {relative}") from error
        first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
        if first_line != f"# {title}":
            raise DocumentError(f"Document title does not match manifest: {relative}")
        documents.append(Document(identifier, title, relative.as_posix(), digest, text))
    return Corpus(corpus_id, review_status, baseline, tuple(documents))
