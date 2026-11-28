"""Development-only threshold selection with a separate fail-closed evaluation."""

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

QUERY_VERSION = 1
POLICY_VERSION = 2

# Enforce the existing read-only boundary, independently of topical cosine scores.
# Deliberately narrow: a request form + command/script + mutating action, not
# arbitrary occurrences of firmware/reset vocabulary or capability questions.
_REQUEST = re.compile(
    r"^(?:please\s+)?(?:(?:what|which)\s+(?:(?:shell|terminal|cli)\s+)?(?:commands?|scripts?)\b"
    r"|(?:give|provide|show|write|generate|suggest|recommend|run|execute)\b"
    r"|how\s+(?:do|can|should|would)\s+i\b)", re.IGNORECASE,
)
_COMMAND = re.compile(r"\b(?:commands?|scripts?)\b", re.IGNORECASE)
_MUTATING = re.compile(
    r"\b(?:repair(?:s|ing)?|fix(?:es|ing)?|reset(?:s|ting)?|restart(?:s|ing)?"
    r"|reboot(?:s|ing)?|replac(?:e|es|ing)|flash(?:es|ing)?|updat(?:e|es|ing)"
    r"|upgrad(?:e|es|ing)|rollback|roll\s+back|clear(?:s|ing)?|delet(?:e|es|ing)|eras(?:e|es|ing))\b",
    re.IGNORECASE,
)


def requests_remediation_command(question):
    return bool(_REQUEST.search(question.strip()) and _COMMAND.search(question) and _MUTATING.search(question))


def _accepted(question, candidates, threshold):
    if threshold is None or requests_remediation_command(question):
        return ()
    return tuple(hit for hit in candidates if hit.score >= threshold)


class RelevanceInvalid(ValueError):
    """The explicit local evaluation or captured gate is incompatible."""


@dataclass(frozen=True)
class Case:
    question: str
    relevant_documents: frozenset[str]


@dataclass(frozen=True)
class Evaluation:
    fingerprint: str
    development: tuple[Case, ...]
    held_out: tuple[Case, ...]


@dataclass(frozen=True)
class Counts:
    passed: int = 0
    failed: int = 0
    skipped: int = 0


@dataclass(frozen=True)
class RelevanceGate:
    index_id: str
    evaluation_fingerprint: str
    query_version: int
    threshold: float | None
    development: Counts
    held_out: Counts
    policy_version: int = POLICY_VERSION

    @property
    def enabled(self):
        return (
            self.threshold is not None and self.development.failed == self.held_out.failed == 0
            and self.development.passed > 0 and self.held_out.passed > 0
            and self.held_out.skipped == 0 and self.query_version == QUERY_VERSION
            and self.policy_version == POLICY_VERSION
        )

    def __call__(self, query, candidates, index_id):
        if (index_id != self.index_id or self.query_version != QUERY_VERSION
                or self.policy_version != POLICY_VERSION):
            raise RelevanceInvalid("The gate does not match the retrieval snapshot")
        if not self.enabled:
            return ()
        if len(candidates) > 3 or any(
            type(hit.score) not in (float, int) or not math.isfinite(hit.score)
            or not -1 <= hit.score <= 1 for hit in candidates
        ):
            raise RelevanceInvalid("Invalid candidate scores")
        return _accepted(query, candidates, self.threshold)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RelevanceInvalid("Duplicate evaluation field")
        result[key] = value
    return result


def load_evaluation(path, document_ids):
    try:
        raw = Path(path).read_bytes()
        value = json.loads(raw, object_pairs_hook=_object)
        if (
            set(value) != {"schema_version", "query_version", "review_status", "development", "held_out"}
            or type(value["schema_version"]) is not int or value["schema_version"] != 1
            or type(value["query_version"]) is not int or value["query_version"] != QUERY_VERSION
            or value["review_status"] != "source_derived_pending_owner_review"
        ):
            raise ValueError()
        questions = set()
        splits = []
        for name in ("development", "held_out"):
            cases = []
            for entry in value[name]:
                if set(entry) != {"question", "relevant_document_ids"}:
                    raise ValueError()
                question, documents = entry["question"], entry["relevant_document_ids"]
                if (
                    not isinstance(question, str) or not question.strip() or len(question) > 2048
                    or question in questions or not isinstance(documents, list)
                    or any(not isinstance(doc, str) for doc in documents)
                    or len(documents) != len(set(documents)) or not set(documents) <= set(document_ids)
                ):
                    raise ValueError()
                questions.add(question)
                cases.append(Case(question, frozenset(documents)))
            if sum(bool(case.relevant_documents) for case in cases) < 6 or sum(
                not case.relevant_documents for case in cases
            ) < 6:
                raise ValueError()
            splits.append(tuple(cases))
        return Evaluation(hashlib.sha256(raw).hexdigest(), *splits)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        raise RelevanceInvalid("The local relevance evaluation is invalid") from None


def _count(scored, threshold):
    passed = 0
    for case, hits in scored:
        accepted = _accepted(case.question, hits, threshold)
        documents = {hit.chunk.document_id for hit in accepted}
        valid = (bool(documents) if case.relevant_documents else not documents)
        passed += bool(valid and documents <= case.relevant_documents)
    return Counts(passed, len(scored) - passed)


def calibrate(index, encoder, evaluation):
    # Only development scores/labels may choose the threshold. Never tune on held-out data.
    development = [(case, index.search(case.question, encoder, limit=3)) for case in evaluation.development]
    best_supported = [
        max((hit.score for hit in hits if hit.chunk.document_id in case.relevant_documents), default=None)
        for case, hits in development if case.relevant_documents
    ]
    threshold = None
    if best_supported and all(score is not None for score in best_supported):
        # Highest cutoff retaining at least one correct candidate for every supported case.
        threshold = min(best_supported)
    dev_counts = _count(development, threshold)
    if threshold is None or dev_counts.failed:
        return RelevanceGate(index.index_id, evaluation.fingerprint, QUERY_VERSION, threshold,
                             dev_counts, Counts(skipped=len(evaluation.held_out)))
    # This is the first access to held-out queries; threshold is already frozen.
    held_out = [(case, index.search(case.question, encoder, limit=3)) for case in evaluation.held_out]
    return RelevanceGate(index.index_id, evaluation.fingerprint, QUERY_VERSION, threshold,
                         dev_counts, _count(held_out, threshold))
