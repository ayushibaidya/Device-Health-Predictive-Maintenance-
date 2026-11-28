"""Synchronous evidence/retrieval/report composition with explicit guidance selection."""

import re
import threading
from datetime import datetime, timezone

from .embeddings import EmbeddingFailed, EmbeddingUnavailable
from .index import IndexInvalid
from .ollama import ProviderReply
from .relevance import RelevanceInvalid
from .reporting import (
    AIBusy,
    AIInvalidResponse,
    AIUnavailable,
    ContextUnavailable,
    MODEL_TAG,
    OLLAMA_VERSION,
    PROMPT_VERSION,
    prepare_messages,
    prepare_sources,
    validate_report,
)

_ADMISSION = threading.Lock()


def retrieval_query(packet):
    snapshot = packet["sources"]["alert"]["snapshot"]
    # IDs/messages are not needed for semantic retrieval; keep encoder input bounded.
    return (
        f"Synthetic simulator reported {snapshot['severity']}; alert {snapshot['status']}; "
        f"resolution {snapshot['resolution_reason'] or 'unresolved'}. "
        "Review same lifecycle telemetry: temperature power CPU memory timing jitter error_count. "
        "Explain simulator state, lifecycle boundaries and telemetry coverage; no physical diagnosis."
    )


class InvestigationAdapter:
    def __init__(self, reader, index, encoder, provider, limits, select_guidance):
        if not callable(select_guidance):
            raise ValueError("An explicitly reviewed guidance-selection rule is required")
        self.reader, self.index, self.encoder = reader, index, encoder
        self.provider, self.limits, self.select_guidance = provider, limits, select_guidance

    def investigate(self, alert_id):
        if not _ADMISSION.acquire(blocking=False):
            raise AIBusy("Another investigation is in progress.")
        try:
            evidence = self.reader.get(alert_id)
            if getattr(self.reader, "connection", None) is not None:
                raise ContextUnavailable("Database resources must be released before model work.")
            validated, _ = prepare_sources(evidence, ())
            try:
                query = retrieval_query(validated)
                candidates = self.index.search(query, self.encoder, limit=3)
            except (IndexInvalid, EmbeddingUnavailable, EmbeddingFailed):
                raise AIUnavailable("The local retrieval assets are unavailable.") from None
            # No default threshold or automatic acceptance of uncalibrated candidates.
            try:
                selected = tuple(self.select_guidance(query, candidates, self.index.index_id))
            except RelevanceInvalid:
                raise AIUnavailable("The local relevance gate is incompatible.") from None
            if len(selected) > 3 or any(hit not in candidates for hit in selected):
                raise ContextUnavailable("Guidance selection must use the validated retrieval snapshot.")
            packet, source_ids = prepare_sources(evidence, selected)
            provenance = {
                "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "index_id": self.index.index_id, "profile_id": self.encoder.profile_id,
                "prompt_version": PROMPT_VERSION, "model_tag": None,
                "model_digest": None, "ollama_version": None,
            }
            if not selected:
                return {**packet, "status": "insufficient_evidence", "report": {
                    "observations": [], "possible_explanations": [], "suggested_checks": [],
                    "limitations": ["No relevant troubleshooting guidance was accepted; no model was called."],
                }, "provenance": provenance}
            messages, schema = prepare_messages(packet, self.limits)
            reply = self.provider.generate(messages, schema, self.limits)
            if (
                not isinstance(reply, ProviderReply)
                or reply.model_tag != MODEL_TAG or reply.runtime_version != OLLAMA_VERSION
                or not isinstance(reply.model_digest, str)
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", reply.model_digest)
            ):
                raise AIInvalidResponse("The model response has invalid provenance.")
            report = validate_report(reply.content, source_ids)
            limitations = [
                "Evidence is simulated; this report does not establish a physical hardware cause.",
                "AI-generated hypotheses require engineer review.",
            ]
            if self.index.review_status == "source_checked_pending_owner_review":
                limitations.append("Troubleshooting documents have not completed owner review.")
            if packet["evidence"]["truncated"]:
                limitations.append("The evidence window was capped at 100 readings.")
            if packet["evidence"]["reading_count"] < 2:
                limitations.append("Only one reading is available; a telemetry trend cannot be established.")
            report["limitations"] = list(dict.fromkeys(report["limitations"] + limitations))
            provenance.update(model_tag=reply.model_tag, model_digest=reply.model_digest,
                              ollama_version=reply.runtime_version)
            return {**packet, "status": "complete", "report": report, "provenance": provenance}
        finally:
            _ADMISSION.release()
