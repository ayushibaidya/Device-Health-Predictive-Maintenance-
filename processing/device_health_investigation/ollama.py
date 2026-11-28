"""Pinned local Ollama HTTP transport; never install, pull, retry or use proxies."""

import http.client
import json
import re
import socket
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from .reporting import AIInvalidResponse, AITimeout, AIUnavailable, MODEL_TAG, OLLAMA_VERSION, strict_json


@dataclass(frozen=True)
class ProviderReply:
    content: str
    model_tag: str
    model_digest: str
    runtime_version: str


def _digest(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", value):
        raise AIUnavailable("The configured local model digest is invalid.")
    return "sha256:" + value.removeprefix("sha256:")


class OllamaClient:
    def __init__(self, expected_digest, base_url="http://127.0.0.1:11434"):
        address = urlsplit(base_url)
        if (
            address.scheme != "http"
            or address.hostname not in {"127.0.0.1", "localhost", "::1", "host.docker.internal"}
            or address.username is not None or address.password is not None
            or address.path not in {"", "/"} or address.query or address.fragment
        ):
            raise ValueError("Configure an explicit local Ollama HTTP address")
        self.host, self.port = address.hostname, address.port or 11434
        self.expected_digest = _digest(expected_digest)

    def _request(self, path, payload=None, timeout=5):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=timeout)
        expired = threading.Event()
        sockets = []

        def cancel():
            expired.set()
            active = sockets[0] if sockets else connection.sock
            if active is not None:
                try:
                    active.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

        timer = threading.Timer(timeout, cancel)
        timer.daemon = True
        started = time.monotonic()
        timer.start()
        response = None
        try:
            connection.connect()
            sockets.append(connection.sock)
            if expired.is_set():
                raise AITimeout("The local model request timed out.")
            body = None if payload is None else json.dumps(payload, allow_nan=False).encode()
            connection.request("GET" if payload is None else "POST", path, body, {
                "Content-Type": "application/json", "Accept": "application/json", "Connection": "close",
            })
            response = connection.getresponse()
            if response.status != 200:
                raise AIUnavailable("The selected local model service is unavailable.")
            chunks, size = [], 0
            while True:
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0 or expired.is_set():
                    raise AITimeout("The local model request timed out.")
                sockets[0].settimeout(remaining)
                chunk = response.read1(65536)
                if not chunk:
                    break
                size += len(chunk)
                if size > 1048576:
                    raise AIInvalidResponse("The local model response exceeded its size limit.", stage="provider_body_limit")
                chunks.append(chunk)
                if response.isclosed() or response.length == 0:
                    break
            if expired.is_set() or time.monotonic() - started >= timeout:
                raise AITimeout("The local model request timed out.")
            if response.length not in (None, 0):
                raise AIInvalidResponse("The local model response was truncated.", stage="provider_http_truncated")
            value = strict_json(b"".join(chunks).decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError("Expected a provider object")
            return value
        except (socket.timeout, TimeoutError):
            raise AITimeout("The local model request timed out.") from None
        except (OSError, http.client.HTTPException):
            if expired.is_set():
                raise AITimeout("The local model request timed out.") from None
            raise AIUnavailable("The selected local model service is unavailable.") from None
        except (ValueError, UnicodeError, RecursionError):
            if expired.is_set():
                raise AITimeout("The local model request timed out.") from None
            raise AIInvalidResponse("The local model returned an invalid response.", stage="provider_json") from None
        finally:
            timer.cancel()
            if response is not None:
                response.close()
            connection.close()
            if sockets:
                sockets[0].close()

    def _verify_digest(self):
        models = self._request("/api/tags").get("models")
        if not isinstance(models, list):
            raise AIUnavailable("The selected local model is not provisioned.")
        matching = [item for item in models if isinstance(item, dict) and item.get("name") == MODEL_TAG]
        if len(matching) != 1 or _digest(matching[0].get("digest")) != self.expected_digest:
            raise AIUnavailable("The selected local model is missing or its digest changed.")

    def verify(self, limits):
        try:
            if self._request("/api/version").get("version") != OLLAMA_VERSION:
                raise AIUnavailable("The local Ollama version does not match the reviewed pin.")
            self._verify_digest()
            details = self._request("/api/show", {"model": MODEL_TAG, "verbose": False})
            info = details.get("model_info", {})
            capacity = info.get("qwen3.context_length") if isinstance(info, dict) else None
            metadata = details.get("details", {})
            if (
                not isinstance(info, dict) or info.get("general.architecture") != "qwen3"
                or not isinstance(metadata, dict) or metadata.get("quantization_level") != "Q4_K_M"
                or type(capacity) is not int or capacity < limits.context_tokens
            ):
                raise AIUnavailable("The selected model cannot satisfy the configured context.")
        except (AITimeout, AIInvalidResponse):
            raise AIUnavailable("Cannot verify the pinned local model service.") from None

    def generate(self, messages, schema, limits):
        self.verify(limits)
        response = self._request("/api/chat", {
            "model": MODEL_TAG, "messages": messages, "stream": False, "format": schema,
            "options": {"temperature": 0, "num_ctx": limits.context_tokens, "num_predict": limits.output_tokens},
        }, timeout=limits.timeout_seconds)
        message = response.get("message")
        if response.get("done_reason") == "length":
            raise AIInvalidResponse("The local model response was output-truncated.", stage="provider_output_truncated")
        if (
            response.get("model") != MODEL_TAG or response.get("done") is not True
            or response.get("done_reason") != "stop" or not isinstance(message, dict)
            or message.get("role") != "assistant" or not isinstance(message.get("content"), str)
            or message.get("tool_calls") or response.get("error")
        ):
            raise AIInvalidResponse("The local model response was incomplete or invalid.", stage="provider_envelope")
        prompt_count, output_count = response.get("prompt_eval_count"), response.get("eval_count")
        if (
            type(prompt_count) is not int or not 0 < prompt_count < limits.context_tokens - limits.output_tokens
            or type(output_count) is not int or not 0 < output_count <= limits.output_tokens
        ):
            raise AIInvalidResponse("The local model response exceeded its token budget.", stage="provider_token_budget")
        self._verify_digest()
        return ProviderReply(message["content"], MODEL_TAG, self.expected_digest, OLLAMA_VERSION)
