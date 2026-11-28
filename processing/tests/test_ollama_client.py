import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from device_health_investigation.ollama import OllamaClient
from device_health_investigation.reporting import (
    AIInvalidResponse, AITimeout, AIUnavailable, GenerationLimits, MODEL_TAG, OLLAMA_VERSION,
)
from test_investigation_reporting import valid_report

DIGEST = "a" * 64


@pytest.fixture
def local_provider():
    state = {"version": OLLAMA_VERSION, "digest": DIGEST, "missing": False,
             "status": 200, "raw": None, "stall": False, "drip": False, "requests": []}
    state["chat"] = {
        "model": MODEL_TAG, "done": True, "done_reason": "stop", "prompt_eval_count": 100,
        "eval_count": 20, "message": {"role": "assistant", "content": json.dumps(valid_report())},
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            state["requests"].append(("GET", self.path, None))
            if self.path == "/api/version":
                value = {"version": state["version"]}
            elif self.path == "/api/tags":
                digest = state.get("digest_after_chat", state["digest"]) if state.get("generated") else state["digest"]
                value = {"models": [] if state["missing"] else [{"name": MODEL_TAG, "digest": digest}]}
            else:
                self.send_error(404)
                return
            self.reply(json.dumps(value).encode())

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["requests"].append(("POST", self.path, request))
            if self.path == "/api/show":
                self.reply(json.dumps({"model_info": {"general.architecture": "qwen3",
                                                      "qwen3.context_length": state.get("capacity", 131072)},
                                       "details": {"quantization_level": "Q4_K_M"}}).encode())
                return
            if self.path != "/api/chat":
                self.send_error(404)
                return
            state["generated"] = True
            if state["stall"]:
                time.sleep(0.25)
            raw = state["raw"] if state["raw"] is not None else json.dumps(state["chat"]).encode()
            self.reply(raw)

        def reply(self, raw):
            try:
                self.send_response(state["status"])
                self.send_header("Content-Type", "application/json")
                extra = state.get("extra_length", 0) if self.path == "/api/chat" else 0
                self.send_header("Content-Length", str(len(raw) + extra))
                self.end_headers()
                if state["drip"] and self.path == "/api/chat":
                    for byte in raw:
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                        time.sleep(0.01)
                else:
                    self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield state, OllamaClient(DIGEST, f"http://127.0.0.1:{server.server_port}")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def generate(client, timeout=1):
    return client.generate([{"role": "user", "content": "test-only evidence"}],
                           {"type": "object"}, GenerationLimits(65536, 2048, 60000, timeout))


def test_pinned_local_http_request_and_response(local_provider, monkeypatch):
    state, client = local_provider
    monkeypatch.setenv("HTTP_PROXY", "http://invalid-proxy.example:1")
    reply = generate(client)
    assert reply.model_digest == "sha256:" + DIGEST
    assert reply.runtime_version == OLLAMA_VERSION
    assert json.loads(reply.content) == valid_report()
    requests = state["requests"]
    assert [item[1] for item in requests] == ["/api/version", "/api/tags", "/api/show", "/api/chat", "/api/tags"]
    payload = requests[3][2]
    assert payload["model"] == MODEL_TAG and payload["stream"] is False
    assert payload["format"] == {"type": "object"}
    assert payload["options"] == {"temperature": 0, "num_ctx": 65536, "num_predict": 2048}
    assert "tools" not in payload


@pytest.mark.parametrize("problem", ["version", "missing", "digest", "capacity"])
def test_missing_or_changed_runtime_model_fails_before_generation(local_provider, problem):
    state, client = local_provider
    if problem == "version":
        state["version"] = "0.0.0"
    elif problem == "missing":
        state["missing"] = True
    elif problem == "digest":
        state["digest"] = "b" * 64
    else:
        state["capacity"] = 1024
    with pytest.raises(AIUnavailable):
        generate(client)
    assert not any(path == "/api/chat" for _, path, _ in state["requests"])


@pytest.mark.parametrize("problem", [
    "unfinished", "length", "wrong_model", "tool_call", "missing_content", "prompt_count",
    "output_count", "duplicate_json", "not_json", "oversized", "http_truncated",
])
def test_invalid_or_truncated_responses_fail(local_provider, problem):
    state, client = local_provider
    if problem == "unfinished":
        state["chat"]["done"] = False
    elif problem == "length":
        state["chat"]["done_reason"] = "length"
    elif problem == "wrong_model":
        state["chat"]["model"] = "another-model"
    elif problem == "tool_call":
        state["chat"]["message"]["tool_calls"] = [{"name": "unapproved-tool"}]
    elif problem == "missing_content":
        state["chat"]["message"].pop("content")
    elif problem == "prompt_count":
        state["chat"]["prompt_eval_count"] = True
    elif problem == "output_count":
        state["chat"]["eval_count"] = 2049
    elif problem == "duplicate_json":
        state["raw"] = ('{"done":false,' + json.dumps(state["chat"])[1:]).encode()
        assert json.loads(state["raw"]) == state["chat"]
    elif problem == "not_json":
        state["raw"] = b"provider error text"
    elif problem == "http_truncated":
        state["extra_length"] = 5
    else:
        state["raw"] = b"x" * 1048577
    expected_stage = {
        "length": "provider_output_truncated", "prompt_count": "provider_token_budget",
        "output_count": "provider_token_budget", "duplicate_json": "provider_json",
        "not_json": "provider_json", "oversized": "provider_body_limit",
        "http_truncated": "provider_http_truncated",
    }.get(problem, "provider_envelope")
    with pytest.raises(AIInvalidResponse) as captured:
        generate(client)
    assert captured.value.stage == expected_stage
    assert captured.value.code == "ai_invalid_response"
    assert sum(path == "/api/chat" for _, path, _ in state["requests"]) == 1


def test_output_limit_is_reported_without_provider_text(local_provider):
    from device_health_investigation.verification import safe_error, summary

    state, client = local_provider
    state["chat"]["done_reason"] = "length"
    state["chat"]["eval_count"] = 2048
    state["chat"]["message"]["content"] = "CANARY_PROVIDER_RESPONSE"
    with pytest.raises(AIInvalidResponse) as captured:
        generate(client)
    category = safe_error(captured.value)
    assert category == "ai_invalid_response_provider_output_truncated"
    assert "CANARY" not in json.dumps(summary(errors=1, categories=[category]))


@pytest.mark.parametrize("mode", ["stall", "drip"])
def test_deadline_interrupts_stalled_or_dripping_response(local_provider, mode):
    state, client = local_provider
    state[mode] = True
    started = time.monotonic()
    with pytest.raises(AITimeout):
        generate(client, timeout=0.08)
    assert time.monotonic() - started < 1
    assert sum(path == "/api/chat" for _, path, _ in state["requests"]) == 1


def test_model_digest_change_during_request_rejects_provenance(local_provider):
    state, client = local_provider
    state["digest_after_chat"] = "b" * 64
    with pytest.raises(AIUnavailable, match="digest changed"):
        generate(client)


@pytest.mark.parametrize("address", [
    "https://example.com", "http://example.com", "http://user:password@localhost:11434",
    "http://127.0.0.1:11434/remote", "http://127.0.0.1:11434?target=cloud", "file:///tmp/model",
])
def test_nonlocal_or_ambiguous_service_addresses_are_rejected(address):
    with pytest.raises(ValueError):
        OllamaClient(DIGEST, address)


def test_configured_digest_is_required():
    with pytest.raises(AIUnavailable):
        OllamaClient("not-a-model-digest")
