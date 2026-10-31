"""Authenticated session-local Anthropic Messages facade over LiteLLM."""

import asyncio
import hmac
import json
import logging
import os

os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

import litellm
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

litellm.use_chat_completions_url_for_anthropic_messages = True
litellm.suppress_debug_info = True
litellm.set_verbose = False
litellm.turn_off_message_logging = True
logging.getLogger("LiteLLM").setLevel(logging.CRITICAL)

MAX_BODY = 8 * 1024 * 1024
FIELDS = {
    "messages",
    "max_tokens",
    "system",
    "stop_sequences",
    "stream",
    "temperature",
    "top_p",
    "top_k",
    "tools",
    "tool_choice",
}


class RequestValidationError(ValueError):
    """Only fixed, kit-authored messages may be returned to the caller."""


def error(status, message):
    return JSONResponse(
        status_code=status, content={"type": "error", "error": {"type": "api_error", "message": message}}
    )


async def body(request, token, ids):
    auth = request.headers.get("authorization", "")
    candidate = auth.removeprefix("Bearer ") if auth.startswith("Bearer ") else request.headers.get("x-api-key", "")
    if not hmac.compare_digest(candidate, token):
        raise PermissionError("proxy authentication required")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_BODY:
            raise RequestValidationError("Request body exceeds the proxy size limit")
    from provider import strict_json

    data = strict_json(raw)
    if not isinstance(data, dict):
        raise RequestValidationError("Messages request must be a JSON object")
    if not isinstance(data.get("model"), str) or data["model"] not in ids:
        raise RequestValidationError(
            "Model is not in the selected acq provider snapshot; choose an exact gateway model ID"
        )
    if not isinstance(data.get("messages"), list):
        raise RequestValidationError("Messages must be an array")
    return data


def arguments(data, facts):
    # Client-supplied routing, credentials, callbacks, MCP gateways, and logging
    # options NEVER reach LiteLLM. Only ordinary function tools are supported.
    tools = data.get("tools", [])
    if not isinstance(tools, list) or any(
        not isinstance(t, dict) or t.get("type", "custom") != "custom" for t in tools
    ):
        raise RequestValidationError("Only ordinary function tools are supported; disable Anthropic server-side tools")
    params = {key: data[key] for key in FIELDS if key in data}
    params.update(
        model="openai/" + data["model"],
        api_base=facts["baseUrl"],
        api_key=os.environ[facts["keyEnv"]],
        timeout=600,
        num_retries=0,
        drop_params=True,
        _skip_mcp_handler=True,
    )
    if type(params.get("max_tokens")) is not int or not 1 <= params["max_tokens"] <= 128000:
        raise RequestValidationError("max_tokens must be an integer between 1 and 128000")
    if "stream" in params and type(params["stream"]) is not bool:
        raise RequestValidationError("stream must be boolean")
    return params


async def sse(response, gate):
    from stream import normalize

    try:
        async with asyncio.timeout(600):
            async for chunk in normalize(response):
                yield chunk
    except Exception:
        yield (
            b'event: error\ndata: {"type":"error","error":{"type":"api_error","message":"Upstream stream failed"}}\n\n'
        )
    finally:
        try:
            close = getattr(response, "aclose", None)
            if close:
                await close()
        finally:
            gate.release()


def make_app(facts, ids, token):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    gate = asyncio.Semaphore(4)

    @app.post("/v1/messages")
    async def messages(request: Request):
        leased = False
        try:
            data = await body(request, token, ids)
            params = arguments(data, facts)
            async with asyncio.timeout(600):
                await gate.acquire()
                leased = True
                response = await litellm.anthropic.messages.acreate(**params)
            if data.get("stream"):
                result = StreamingResponse(sse(response, gate), media_type="text/event-stream")
                leased = False  # Streaming iterator owns release, including disconnect/cancellation.
                return result
            return JSONResponse(response)
        except PermissionError:
            return error(401, "Proxy authentication required")
        except RequestValidationError as exc:
            return error(400, str(exc))
        except (ValueError, TypeError, json.JSONDecodeError):
            return error(400, "Invalid Messages request")
        except Exception:
            # Upstream exceptions may contain headers, keys, or prompt text.
            return error(502, "Upstream request failed; check provider availability and credentials")
        finally:
            if leased:
                gate.release()

    @app.post("/v1/messages/count_tokens")
    async def count_tokens(request: Request):
        try:
            data = await body(request, token, ids)
            # Offline estimate, not Anthropic's exact tokenizer. No tokenizer
            # downloads, provider calls, or claims of exact context accounting.
            payload = {key: data[key] for key in ("messages", "system", "tools") if key in data}
            estimate = max(1, len(json.dumps(payload, ensure_ascii=False).encode("utf-8")))
            return JSONResponse({"input_tokens": estimate})
        except PermissionError:
            return error(401, "Proxy authentication required")
        except RequestValidationError as exc:
            return error(400, str(exc))
        except (ValueError, TypeError):
            return error(400, "Invalid token-count request")

    return app
