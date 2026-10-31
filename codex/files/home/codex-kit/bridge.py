"""Bounded, authenticated Responses/Gemini facade over Chat Completions.

Upstream responses are buffered. SSE is generated only after validation; this is
not token-by-token streaming. No SDK, callbacks, remote tool execution, or URLs
from request bodies are passed to the upstream transport.
"""

import hmac
import json
import secrets
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

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


def text(parts):
    if isinstance(parts, str):
        return parts
    if not isinstance(parts, list):
        raise ValueError("invalid text content")
    result = []
    for part in parts:
        if not isinstance(part, dict) or part.get("type") not in ("input_text", "output_text", "text"):
            raise ValueError("only text content is supported")
        if not isinstance(part.get("text"), str):
            raise ValueError("invalid text content")
        result.append(part["text"])
    return "\n".join(result)


def responses_request(data):
    allowed = {
        "model",
        "input",
        "instructions",
        "tools",
        "tool_choice",
        "parallel_tool_calls",
        "stream",
        "store",
        "client_metadata",
        "include",
        "prompt_cache_key",
        "reasoning",
        "text",
    }
    if set(data) - allowed:
        raise ValueError("unsupported Responses fields")
    if "stream" in data and type(data["stream"]) is not bool:
        raise ValueError("stream must be boolean")
    if "parallel_tool_calls" in data and type(data["parallel_tool_calls"]) is not bool:
        raise ValueError("parallel_tool_calls must be boolean")
    if data.get("tool_choice", "auto") not in ("auto", "none", "required"):
        raise ValueError("unsupported tool selection")
    if data.get("reasoning", {}).get("effort") not in (None, "none"):
        raise ValueError("reasoning effort is unsupported")
    if data.get("reasoning", {}).get("summary") not in (None, "none", "auto"):
        raise ValueError("reasoning summaries are unsupported")
    if data.get("text") not in (None, {}, {"format": {"type": "text"}}):
        raise ValueError("structured output is unsupported")
    messages = []
    if data.get("instructions"):
        messages.append({"role": "system", "content": text(data["instructions"])})
    items = data.get("input", [])
    if isinstance(items, str):
        items = [{"role": "user", "content": items}]
    if not isinstance(items, list):
        raise ValueError("input must be an array or text")
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("invalid input item")
        kind = item.get("type", "message")
        if kind == "message":
            role = item.get("role")
            if role not in ("system", "developer", "user", "assistant"):
                raise ValueError("unsupported message role")
            messages.append(
                {"role": "system" if role == "developer" else role, "content": text(item.get("content", []))}
            )
        elif kind == "function_call":
            name = item.get("name", "")
            if item.get("namespace"):
                name = item["namespace"] + "__" + name
            call = {
                "id": item["call_id"],
                "type": "function",
                "function": {"name": name, "arguments": item["arguments"]},
            }
            if messages and messages[-1].get("tool_calls") and messages[-1]["role"] == "assistant":
                messages[-1]["tool_calls"].append(call)
            else:
                messages.append({"role": "assistant", "content": None, "tool_calls": [call]})
        elif kind == "function_call_output":
            messages.append({"role": "tool", "tool_call_id": item["call_id"], "content": text(item["output"])})
        elif kind == "reasoning" and not item.get("encrypted_content"):
            continue
        else:
            raise ValueError("unsupported Responses input item")
    tools, names = [], {}
    for tool in data.get("tools", []):
        if tool.get("type") == "namespace":
            namespace, nested = tool["name"], tool["tools"]
        else:
            namespace, nested = None, [tool]
        for definition in nested:
            if definition.get("type") != "function":
                raise ValueError("only ordinary function tools are supported")
            original = definition["name"]
            name = namespace + "__" + original if namespace else original
            if name in names:
                raise ValueError("duplicate function tool")
            names[name] = (original, namespace)
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": definition.get("description", ""),
                        "parameters": definition.get("parameters", {"type": "object", "properties": {}}),
                    },
                }
            )
            if "strict" in definition:
                if type(definition["strict"]) is not bool:
                    raise ValueError("strict must be boolean")
                tools[-1]["function"]["strict"] = definition["strict"]
    pending, used = set(), set()
    for message in messages:
        if message["role"] == "tool":
            identity = message["tool_call_id"]
            if identity not in pending:
                raise ValueError("unpaired function result")
            pending.remove(identity)
        else:
            if pending:
                raise ValueError("function results must immediately follow their call batch")
            for call in message.get("tool_calls", []):
                identity = call["id"]
                if not isinstance(identity, str) or identity in used:
                    raise ValueError("invalid or duplicate function ID")
                used.add(identity)
                pending.add(identity)
    if pending:
        raise ValueError("missing function results")
    return messages, tools, names


def response_output(message, names):
    output = []
    if message.get("content"):
        output.append(
            {
                "id": "msg_" + secrets.token_hex(12),
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text(message["content"]), "annotations": []}],
            }
        )
    for call in message.get("tool_calls", []):
        function = call["function"]
        name, namespace = names[function["name"]]
        arguments = function["arguments"]
        if not isinstance(strict_json(arguments), dict):
            raise ValueError("invalid upstream function arguments")
        item = {
            "id": "fc_" + secrets.token_hex(12),
            "type": "function_call",
            "status": "completed",
            "call_id": call["id"],
            "name": name,
            "arguments": arguments,
        }
        if namespace:
            item["namespace"] = namespace
        output.append(item)
    if not output:
        raise ValueError("empty upstream response")
    return output


def events(response):
    sequence = 0

    def event(kind, **fields):
        nonlocal sequence
        sequence += 1
        return (
            "event: "
            + kind
            + "\ndata: "
            + json.dumps({"type": kind, "sequence_number": sequence - 1, **fields})
            + "\n\n"
        )

    pending = {**response, "status": "in_progress", "output": []}
    yield event("response.created", response=pending)
    yield event("response.in_progress", response=pending)
    for index, item in enumerate(response["output"]):
        initial = {**item, "status": "in_progress"}
        if item["type"] == "message":
            initial["content"] = []
        else:
            initial["arguments"] = ""
        yield event("response.output_item.added", output_index=index, item=initial)
        if item["type"] == "message":
            part = item["content"][0]
            yield event(
                "response.content_part.added",
                item_id=item["id"],
                output_index=index,
                content_index=0,
                part={**part, "text": ""},
            )
            yield event(
                "response.output_text.delta",
                item_id=item["id"],
                output_index=index,
                content_index=0,
                delta=part["text"],
            )
            yield event(
                "response.output_text.done", item_id=item["id"], output_index=index, content_index=0, text=part["text"]
            )
            yield event(
                "response.content_part.done", item_id=item["id"], output_index=index, content_index=0, part=part
            )
        else:
            yield event(
                "response.function_call_arguments.delta",
                item_id=item["id"],
                output_index=index,
                delta=item["arguments"],
            )
            yield event(
                "response.function_call_arguments.done",
                item_id=item["id"],
                output_index=index,
                arguments=item["arguments"],
            )
        yield event("response.output_item.done", output_index=index, item=item)
    yield event("response.completed", response=response)


def start(facts, ids, key, token, *, transport=None):
    correlation = secrets.token_hex(16)

    def upstream(data):
        request = urllib.request.Request(  # noqa: S310 -- validated HTTPS facts, never request-body URLs
            facts["baseUrl"].rstrip("/") + "/chat/completions",
            data=json.dumps(data).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + key,
                "User-Agent": "acq-cli-bridge/1.0",
                "x-opencode-session": correlation,
            },
        )

        # No redirects: credentials must never follow a different endpoint.
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
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            return

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def reply(self, status, payload, content_type="application/json"):
            body = payload.encode() if isinstance(payload, str) else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

        def do_POST(self):
            auth = self.headers.get("Authorization", "")
            if not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], token):
                self.reply(401, {"error": {"message": "Bridge authentication required"}})
                return
            if not gate.acquire(blocking=False):
                self.reply(429, {"error": {"message": "Bridge concurrency limit reached"}})
                return
            try:
                if self.headers.get("Transfer-Encoding"):
                    raise ValueError("chunked requests unsupported")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    raise ValueError("invalid request size")
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError("truncated body")
                data = strict_json(raw)
                if not isinstance(data, dict):
                    raise ValueError("request must be an object")
                path = urlsplit(self.path).path
                if path == "/v1/responses":
                    model = data.get("model")
                    messages, tools, names = responses_request(data)
                else:
                    self.reply(404, {"error": {"message": "Unsupported bridge route"}})
                    return
                if not isinstance(model, str) or model not in ids:
                    raise ValueError("model is not configured")
                params = {"model": model, "messages": messages, "stream": False}
                if tools:
                    params["tools"] = tools
                    params["tool_choice"] = data.get("tool_choice", "auto")
                    params["parallel_tool_calls"] = data.get("parallel_tool_calls", False)
                upstream_result = send(params)
                message = upstream_result["choices"][0]["message"]
                output = response_output(message, names)
                result = {
                    "id": "resp_" + secrets.token_hex(12),
                    "object": "response",
                    "status": "completed",
                    "model": model,
                    "output": output,
                    "usage": None,
                }
                if data.get("stream"):
                    self.reply(200, "".join(events(result)), "text/event-stream")
                else:
                    self.reply(200, result)
            except (ValueError, KeyError, TypeError, IndexError):
                self.reply(
                    400,
                    {
                        "error": {
                            "message": "Unsupported request or model; use a configured model and text/function tools"
                        }
                    },
                )
            except Exception:
                self.reply(502, {"error": {"message": "Upstream request failed"}})
            finally:
                gate.release()

    server = BoundedServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
