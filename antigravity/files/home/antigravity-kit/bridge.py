"""Authenticated, text/function-only Gemini facade over Chat Completions."""

import hmac
import json
import secrets
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from provider import strict_json

MAX_BODY = 8 * 1024 * 1024


class BoundedServer(ThreadingHTTPServer):
    """Limit open worker threads before request parsing/authentication."""

    daemon_threads = True

    def __init__(self, *args):
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(*args)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


def translate(data):
    if set(data) - {"contents", "systemInstruction", "tools", "generationConfig", "toolConfig"}:
        raise ValueError("unsupported Gemini fields")
    config = data.get("generationConfig", {})
    if set(config) - {"temperature", "topP", "topK", "maxOutputTokens", "thinkingConfig"}:
        raise ValueError("unsupported generation settings")
    thinking = config.get("thinkingConfig", {})
    # agy 1.4.12 emits this automatic envelope for ALL custom models. The kit
    # explicitly operates in text/function mode, not Gemini reasoning mode.
    if thinking not in ({}, {"includeThoughts": True, "thinkingBudget": -1}, {"thinkingBudget": 0}):
        raise ValueError("thinking is unsupported")
    if data.get("toolConfig") not in (None, {}, {"functionCallingConfig": {"mode": "AUTO"}}):
        raise ValueError("unsupported tool selection")
    messages, tools = [], []
    pending = {}
    call_number = 0
    used = {
        part["functionCall"]["id"]
        for content in data.get("contents", [])
        for part in content.get("parts", [])
        if "functionCall" in part and part["functionCall"].get("id")
    }
    explicit = set()
    if data.get("systemInstruction"):
        messages.append({"role": "system", "content": "\n".join(p["text"] for p in data["systemInstruction"]["parts"])})
    for content in data.get("contents", []):
        if content.get("role") not in ("model", "user"):
            raise ValueError("invalid Gemini content role")
        role = "assistant" if content["role"] == "model" else "user"
        texts, calls, outputs = [], [], []
        for part in content["parts"]:
            if "text" in part:
                texts.append(part["text"])
            elif "functionCall" in part:
                call = part["functionCall"]
                call_number += 1
                identity = call.get("id")
                if identity:
                    if identity in explicit:
                        raise ValueError("duplicate function ID")
                    explicit.add(identity)
                else:
                    while f"call_{call_number}" in used:
                        call_number += 1
                    identity = f"call_{call_number}"
                    used.add(identity)
                pending.setdefault(call["name"], []).append(identity)
                calls.append(
                    {
                        "id": identity,
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": json.dumps(call.get("args", {})),
                        },
                    }
                )
            elif "functionResponse" in part:
                response = part["functionResponse"]
                if response.get("parts"):
                    raise ValueError("media tool results are unsupported")
                identities = pending.get(response["name"], [])
                identity = response.get("id")
                if identity is None:
                    if len(identities) != 1:
                        raise ValueError("ambiguous function response")
                    identity = identities[0]
                if identity not in identities:
                    raise ValueError("unpaired function response")
                identities.remove(identity)
                outputs.append(
                    {
                        "role": "tool",
                        "tool_call_id": identity,
                        "content": json.dumps(response["response"]),
                    }
                )
            else:
                raise ValueError("only text/function parts are supported")
        if texts or calls:
            message = {"role": role, "content": "\n".join(texts) or None}
            if calls:
                message["tool_calls"] = calls
            messages.append(message)
        messages.extend(outputs)
    for tool in data.get("tools", []):
        if set(tool) != {"functionDeclarations"}:
            raise ValueError("only ordinary function tools are supported")
        for function in tool["functionDeclarations"]:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": function["name"],
                        "description": function.get("description", ""),
                        "parameters": function.get(
                            "parametersJsonSchema", function.get("parameters", {"type": "object"})
                        ),
                    },
                }
            )
    return messages, tools


def output(message, names):
    parts = []
    if message.get("content"):
        if not isinstance(message["content"], str):
            raise ValueError("invalid upstream text")
        parts.append({"text": message["content"]})
    for call in message.get("tool_calls", []):
        function = call["function"]
        arguments = strict_json(function["arguments"])
        if function["name"] not in names or not isinstance(arguments, dict):
            raise ValueError("invalid upstream function call")
        parts.append({"functionCall": {"id": call["id"], "name": function["name"], "args": arguments}})
    if not parts:
        raise ValueError("empty upstream response")
    return {"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": "STOP"}]}


def start(facts, ids, key, token, small, transport=None):
    correlation = secrets.token_hex(16)

    def upstream(data):
        request = urllib.request.Request(  # noqa: S310 -- validated HTTPS facts, never request-body URLs
            facts["baseUrl"].rstrip("/") + "/chat/completions",
            data=json.dumps(data).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + key,
                "User-Agent": "acq-antigravity-bridge/1.0",
                "x-opencode-session": correlation,
            },
        )

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args):
                return None

        with urllib.request.build_opener(NoRedirect).open(request, timeout=120) as result:  # noqa: S310 -- validated HTTPS facts
            raw = result.read(MAX_BODY + 1)
            if len(raw) > MAX_BODY:
                raise ValueError("upstream response too large")
            return strict_json(raw)

    send = transport or upstream
    gate = threading.BoundedSemaphore(4)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def reply(self, status, payload, content_type="application/json"):
            raw = payload.encode() if isinstance(payload, str) else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self):
            if not hmac.compare_digest(self.headers.get("x-goog-api-key", ""), token):
                self.reply(401, {"error": {"code": 401, "message": "Bridge authentication required"}})
                return
            if not gate.acquire(blocking=False):
                self.reply(429, {"error": {"code": 429, "message": "Bridge concurrency limit reached"}})
                return
            try:
                if self.headers.get("Transfer-Encoding"):
                    raise ValueError("chunked requests unsupported")
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_BODY:
                    raise ValueError("invalid request size")
                raw = self.rfile.read(size)
                if len(raw) != size:
                    raise ValueError("truncated body")
                data = strict_json(raw)
                if not isinstance(data, dict):
                    raise ValueError("request must be an object")
                path = urlsplit(self.path).path
                if not path.startswith("/v1beta/models/") or not path.endswith(
                    (":generateContent", ":streamGenerateContent")
                ):
                    self.reply(404, {"error": {"code": 404, "message": "Unsupported bridge route"}})
                    return
                model = unquote(path[len("/v1beta/models/") :].rsplit(":", 1)[0])
                if model == "gemini-3.1-flash-lite-preview" and not data.get("tools"):
                    model = small
                if model not in ids:
                    raise ValueError("model is not configured")
                messages, tools = translate(data)
                params = {"model": model, "messages": messages, "stream": False}
                config = data.get("generationConfig", {})
                for source, target in [
                    ("temperature", "temperature"),
                    ("topP", "top_p"),
                    ("maxOutputTokens", "max_tokens"),
                ]:
                    if source in config:
                        params[target] = config[source]
                if "topK" in config:
                    raise ValueError("topK is unsupported by Chat Completions")
                if tools:
                    params["tools"] = tools
                result = send(params)
                payload = output(result["choices"][0]["message"], {t["function"]["name"] for t in tools})
                if path.endswith(":streamGenerateContent"):
                    self.reply(200, "data: " + json.dumps(payload) + "\n\n", "text/event-stream")
                else:
                    self.reply(200, payload)
            except (ValueError, TypeError, KeyError, IndexError):
                self.reply(400, {"error": {"code": 400, "message": "Unsupported request or configured model"}})
            except Exception:
                self.reply(502, {"error": {"code": 502, "message": "Upstream request failed"}})
            finally:
                gate.release()

    server = BoundedServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
