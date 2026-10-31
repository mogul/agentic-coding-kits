"""Offline boundaries and live opt-in checks for the Claude kit."""

import asyncio
import hashlib
import io
import json
import os
import sys
import tarfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

PAYLOAD = Path(__file__).resolve().parents[1] / "files/home/claude-code"
sys.path.insert(0, str(PAYLOAD))
from install import PINS, PIP_SHA256, bootstrap_venv, extract_binary  # noqa: E402 -- standalone kit payload
from launch import claude_environment, run_session  # noqa: E402
from provider import load_provider, strict_json  # noqa: E402
from proxy import arguments, make_app, sse  # noqa: E402
from stream import encode, normalize  # noqa: E402


@pytest.fixture
def inputs(tmp_path):
    directory = tmp_path / "models/providers/example"
    directory.mkdir(parents=True)
    facts = {
        "schemaVersion": "acq-provider-facts/v1",
        "providerId": "example",
        "apiProtocol": "openai-compatible",
        "host": "example.invalid",
        "baseUrl": "https://example.invalid/v1",
        "keyEnv": "EXAMPLE_MODEL_KEY",
    }
    catalog = {
        "schemaVersion": "acq-neutral-model-catalog/v1",
        "providerId": "example",
        "models": [{"id": "model-a"}, {"id": "model-b"}],
        "recommendations": {"primary": "model-a", "small": "model-b"},
    }
    (directory / "facts.json").write_text(json.dumps(facts))
    (directory / "snapshot.json").write_text(json.dumps(catalog))
    return tmp_path, directory, facts, catalog


def test_provider_recommendations_and_overrides(inputs):
    root, _, _, _ = inputs
    env = {"ACQ_PROVIDER_INPUT_ROOT": str(root), "EXAMPLE_MODEL_KEY": "synthetic"}
    facts, ids, roles = load_provider(env)
    assert facts["providerId"] == "example"
    assert ids == ["model-a", "model-b"]
    assert roles == {"primary": "model-a", "small": "model-b", "opus": "model-a"}
    env["ACQ_CLAUDE_MODEL"] = "model-b"
    assert load_provider(env)[2]["primary"] == "model-b"


@pytest.mark.parametrize("change", ["missing-key", "unknown-model", "symlink", "http", "identity", "duplicate"])
def test_provider_rejects_invalid_input(inputs, change):
    root, directory, facts, catalog = inputs
    env = {"ACQ_PROVIDER_INPUT_ROOT": str(root), "EXAMPLE_MODEL_KEY": "synthetic"}
    if change == "missing-key":
        env.pop("EXAMPLE_MODEL_KEY")
    elif change == "unknown-model":
        env["ACQ_CLAUDE_MODEL"] = "absent"
    elif change == "symlink":
        (directory / "facts.json").rename(directory / "original.json")
        (directory / "facts.json").symlink_to("original.json")
    elif change == "http":
        facts["baseUrl"] = "http://example.invalid/v1"
        (directory / "facts.json").write_text(json.dumps(facts))
    elif change == "identity":
        catalog["providerId"] = "other"
        (directory / "snapshot.json").write_text(json.dumps(catalog))
    else:
        (directory / "facts.json").write_text('{"schemaVersion":"x","schemaVersion":"y"}')
    with pytest.raises(ValueError):
        load_provider(env)


def test_missing_empty_and_ambiguous_providers(inputs):
    root, _, _, _ = inputs
    with pytest.raises(ValueError):
        load_provider({})
    (root / "models/providers/second").mkdir()
    with pytest.raises(ValueError):
        load_provider({"ACQ_PROVIDER_INPUT_ROOT": str(root)})


def test_child_environment_removes_credentials(inputs, monkeypatch):
    _, _, facts, _ = inputs
    monkeypatch.setenv("EXAMPLE_MODEL_KEY", "synthetic-provider")
    monkeypatch.setenv("GITHUB_TOKEN", "synthetic-github")
    env = claude_environment(
        facts, {"primary": "model-a", "small": "model-b", "opus": "model-a"}, 1234, "synthetic-local"
    )
    assert "EXAMPLE_MODEL_KEY" not in env and "GITHUB_TOKEN" not in env
    assert env["ANTHROPIC_AUTH_TOKEN"] == "synthetic-local"  # noqa: S105 -- synthetic test token
    assert env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:1234"
    assert env["MAX_THINKING_TOKENS"] == "0"


def test_proxy_routes_auth_validation_and_redaction(inputs, monkeypatch):
    _, _, facts, _ = inputs
    monkeypatch.setenv("EXAMPLE_MODEL_KEY", "synthetic-provider")
    mock = AsyncMock(return_value={"content": [{"type": "text", "text": "OK"}]})
    monkeypatch.setattr("proxy.litellm.anthropic.messages.acreate", mock)
    client = TestClient(make_app(facts, ["model-a"], "synthetic-local"))
    data = {"model": "model-a", "max_tokens": 32, "messages": [{"role": "user", "content": "hello"}]}
    headers = {"Authorization": "Bearer synthetic-local"}
    assert client.post("/v1/messages", json=data).status_code == 401
    assert client.post("/v1/messages", json={**data, "model": "unknown"}, headers=headers).status_code == 400
    rejected = client.post("/v1/messages", json={**data, "model": "unknown"}, headers=headers)
    assert "exact gateway model ID" in rejected.text
    assert "unknown" not in rejected.text
    data.update(api_base="https://attacker.invalid", api_key="untrusted", callbacks=["untrusted"])
    assert client.post("/v1/messages", json=data, headers=headers).status_code == 200
    assert mock.call_args.kwargs["api_base"] == facts["baseUrl"]
    assert "callbacks" not in mock.call_args.kwargs
    mock.side_effect = RuntimeError("synthetic-provider private prompt")
    result = client.post("/v1/messages", json=data, headers=headers)
    assert result.status_code == 502 and "private prompt" not in result.text
    assert client.get("/docs").status_code == 404
    assert client.post("/v1/messages/count_tokens", json=data, headers=headers).json()["input_tokens"] > 0


def test_server_tools_rejected(inputs, monkeypatch):
    _, _, facts, _ = inputs
    monkeypatch.setenv("EXAMPLE_MODEL_KEY", "synthetic")
    with pytest.raises(ValueError):
        arguments({"model": "a", "max_tokens": 1, "tools": [{"type": "web_search_20250305"}]}, facts)


@pytest.mark.parametrize("kind", ["regular", "symlink", "duplicate", "wrong-hash"])
def test_archive_validation(tmp_path, kind):
    archive = tmp_path / "archive.tgz"
    with tarfile.open(archive, "w:gz") as bundle:
        member = tarfile.TarInfo("package/claude")
        member.size = 4
        if kind == "symlink":
            member.type = tarfile.SYMTYPE
            member.linkname = "/etc/passwd"
        bundle.addfile(member, io.BytesIO(b"test") if member.isreg() else None)
        if kind == "duplicate":
            bundle.addfile(member, io.BytesIO(b"test"))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    destination = tmp_path / "claude"
    if kind == "regular":
        extract_binary(archive, digest, destination)
        assert destination.read_bytes() == b"test"
    else:
        with pytest.raises(ValueError):
            extract_binary(archive, "0" * 64 if kind == "wrong-hash" else digest, destination)
        assert not destination.exists()


def test_both_architectures_have_independent_pins():
    assert set(PINS) == {"x86_64", "aarch64"}
    assert PINS["x86_64"][0] == "x64"
    assert PINS["aarch64"][0] == "arm64"
    assert PINS["x86_64"][1] != PINS["aarch64"][1]


def test_bootstrap_without_ensurepip_rejects_wrong_wheel(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("install.subprocess.run", lambda argv, **kwargs: calls.append(argv))

    class Response(io.BytesIO):
        def geturl(self):
            from install import PIP_URL

            return PIP_URL

    monkeypatch.setattr("install.urllib.request.urlopen", lambda *a, **kw: Response(b"wrong wheel"))
    with pytest.raises(ValueError, match="pip wheel SHA-256 mismatch"):
        bootstrap_venv(tmp_path, tmp_path)
    assert len(calls) == 1
    assert "--without-pip" in calls[0]
    assert len(PIP_SHA256) == 64


def test_duplicate_json_rejected():
    with pytest.raises(ValueError):
        strict_json('{"a":1,"a":2}')


def test_claude_model_settings_preserve_sdk_hooks():
    from models import compose_settings

    ids = ["claude-sonnet-5.5", "claude_4_5_haiku"]
    roles = {"primary": ids[0]}
    args, settings = compose_settings(["-p", "ping", "--settings", '{"hooks":{"test":[]},"model":"fable"}'], ids, roles)
    assert args == ["-p", "ping"]
    assert settings["hooks"] == {"test": []}
    assert settings["model"] == ids[0]
    assert all(model in settings["availableModels"] for model in ids)
    assert settings["modelOverrides"]["claude-sonnet-5-5"] == "claude-sonnet-5.5"
    assert "fable" not in settings["availableModels"]
    assert settings["modelPicker"]["replaceBuiltInOptions"]
    with pytest.raises(ValueError, match="exact gateway ID"):
        compose_settings(["--model", "fable", "-p", "ping"], ids, roles)
    assert compose_settings(["--model", ids[0], "-p", "ping"], ids, roles)[0][1] == ids[0]
    assert compose_settings(["--model", "claude-sonnet-5-5"], ids, roles)[0][1] == "claude-sonnet-5-5"
    from models import settings_argv

    original = ["-p", "--", "--settings", '{"hooks":{"untrusted":[]}}']
    remaining, composed = compose_settings(original, ids, roles)
    assert remaining == original
    assert "hooks" not in composed
    assert settings_argv(remaining, "owned.json") == ["-p", "--settings", "owned.json", *original[1:]]


def test_canonical_mappings_never_replace_gateway_ids_or_missing_models():
    from models import model_overrides

    assert model_overrides([]) == {}
    assert model_overrides(["claude-sonnet-5.5"]) == {"claude-sonnet-5-5": "claude-sonnet-5.5"}
    assert model_overrides(["claude-sonnet-5.5", "claude-sonnet-5-5"]) == {}
    overrides = model_overrides(["claude_4_8_opus", "claude_4_5_haiku"])
    assert overrides == {"claude-opus-4-8": "claude_4_8_opus", "claude-haiku-4-5": "claude_4_5_haiku"}
    assert not any("fable" in key or "[1m]" in key for key in overrides)


def test_stream_holds_slot_until_close():
    async def run():
        gate = asyncio.Semaphore(4)
        closed = []

        class Stream:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

            async def aclose(self):
                closed.append(True)

        for _ in range(4):
            await gate.acquire()
        waiter = asyncio.create_task(gate.acquire())
        await asyncio.sleep(0)
        assert not waiter.done()
        async for _ in sse(Stream(), gate):
            pass
        await asyncio.wait_for(waiter, 1)
        assert closed == [True]

    asyncio.run(run())


def test_repeated_tool_id_fragments_form_one_call():
    async def source():
        for index, fragment in enumerate(['{"file_', 'path":"/tmp/probe.txt"}']):
            yield encode(
                {
                    "type": "content_block_start",
                    "index": index,
                    "content_block": {"type": "tool_use", "id": "same-call", "name": "Read", "input": {}},
                }
            )
            yield encode(
                {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": {"type": "input_json_delta", "partial_json": fragment},
                }
            )
            yield encode({"type": "content_block_stop", "index": index})
        yield encode({"type": "message_delta", "delta": {"stop_reason": "tool_use"}})
        yield encode({"type": "message_stop"})

    async def run():
        frames = [frame async for frame in normalize(source())]
        events = [json.loads(frame.split(b"data: ", 1)[1]) for frame in frames]
        assert sum(e["type"] == "content_block_start" for e in events) == 1
        assert sum(e["type"] == "content_block_stop" for e in events) == 1
        fragments = [e["delta"]["partial_json"] for e in events if e["type"] == "content_block_delta"]
        assert json.loads("".join(fragments)) == {"file_path": "/tmp/probe.txt"}  # noqa: S108 -- data only, no file IO
        assert all(e.get("index", 0) == 0 for e in events)

    asyncio.run(run())


@pytest.mark.skipif(os.environ.get("RUN_CLAUDE_LIVE") != "1", reason="explicit live opt-in required")
def test_live_translation():
    import litellm

    facts, ids, roles = load_provider()
    client = TestClient(make_app(facts, ids, "synthetic-local"))
    data = {
        "model": roles["small"],
        "max_tokens": 64,
        "messages": [{"role": "user", "content": "Reply exactly ACQ_OK"}],
    }
    headers = {"Authorization": "Bearer synthetic-local"}
    result = client.post("/v1/messages", json=data, headers=headers)
    assert result.status_code == 200, result.text
    assert "ACQ_OK" in result.text
    result = client.post("/v1/messages", json={**data, "stream": True}, headers=headers)
    assert "event: message_stop" in result.text and "event: error" not in result.text
    assert litellm.use_chat_completions_url_for_anthropic_messages

    async def tools():
        args = arguments(
            {
                **data,
                "messages": [{"role": "user", "content": "Call check with value ACQ_OK"}],
                "tools": [
                    {
                        "name": "check",
                        "description": "Return the value",
                        "input_schema": {
                            "type": "object",
                            "properties": {"value": {"type": "string"}},
                            "required": ["value"],
                        },
                    }
                ],
                "tool_choice": {"type": "tool", "name": "check"},
            },
            facts,
        )
        result = await litellm.anthropic.messages.acreate(**args)
        assert result["stop_reason"] == "tool_use"
        assert any(block["type"] == "tool_use" for block in result["content"])

    asyncio.run(tools())


@pytest.mark.skipif(
    os.environ.get("RUN_CLAUDE_LIVE") != "1" or not os.environ.get("ACQ_CLAUDE_TEST_BINARY"),
    reason="explicit live CLI opt-in required",
)
def test_live_claude_session(tmp_path, monkeypatch, capfd):
    import multiprocessing

    monkeypatch.setenv("ACQ_CLAUDE_MODEL", "claude_4_5_haiku")
    monkeypatch.chdir(tmp_path)
    code = run_session(
        Path(os.environ["ACQ_CLAUDE_TEST_BINARY"]),
        [
            "-p",
            "--tools",
            "",
            "--setting-sources",
            "",
            "--strict-mcp-config",
            "--no-session-persistence",
            "Reply exactly ACQ_OK",
        ],
    )
    output = capfd.readouterr()
    assert code == 0, output.out + output.err
    assert "ACQ_OK" in output.out
    assert not multiprocessing.active_children()


@pytest.mark.skipif(
    os.environ.get("RUN_CLAUDE_LIVE") != "1" or not os.environ.get("ACQ_CLAUDE_TEST_BINARY"),
    reason="explicit live CLI tool opt-in required",
)
def test_live_claude_reads_tool_result(tmp_path, monkeypatch, capfd):
    monkeypatch.setenv("ACQ_CLAUDE_MODEL", "claude_4_5_haiku")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "probe.txt").write_text("ACQ_TOOL_RESULT_7391")
    code = run_session(
        Path(os.environ["ACQ_CLAUDE_TEST_BINARY"]),
        [
            "-p",
            "--tools",
            "Read",
            "--allowedTools",
            "Read",
            "--setting-sources",
            "",
            "--strict-mcp-config",
            "--no-session-persistence",
            f"Use the Read tool to read {tmp_path / 'probe.txt'}. Reply exactly with the file contents.",
        ],
    )
    output = capfd.readouterr()
    assert code == 0, output.out + output.err
    assert "ACQ_TOOL_RESULT_7391" in output.out
