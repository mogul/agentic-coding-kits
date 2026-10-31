#!/usr/bin/env python3
"""Exercise a real CLI against a credential-free synthetic provider.

This proves protocol wiring and tool execution, not model quality, remote API
compatibility, or acq microVM creation. Run separately for each installed CLI.
"""

import argparse
import importlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def verify(kind, binary):
    root = Path(__file__).resolve().parents[1]
    folder = "codex-kit" if kind == "codex" else "antigravity-kit"
    sys.path.insert(0, str(root / kind / "files/home" / folder))
    bridge = importlib.import_module("bridge")
    seen = []
    with tempfile.TemporaryDirectory(prefix="native-cli-") as temporary:
        workspace = Path(temporary)
        output = workspace / "output.txt"

        def transport(data):
            seen.append(data)
            tools = {t["function"]["name"] for t in data.get("tools", [])}
            results = [m for m in data["messages"] if m.get("role") == "tool"]
            if not tools:
                return {"choices": [{"message": {"content": "Synthetic file task"}}]}
            if results:
                if not output.is_file() or output.read_text() != "FILE_MARKER":
                    raise ValueError("real tool did not write the expected marker")
                return {"choices": [{"message": {"content": "NATIVE_CLI_OK"}}]}
            if kind == "codex":
                name = "exec_command"
                args = {"cmd": "printf FILE_MARKER > output.txt", "max_output_tokens": 1000}
            else:
                name = "write_file"
                args = {"Path": str(output), "Content": "FILE_MARKER", "Overwrite": True}
            return {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_fixture",
                                    "type": "function",
                                    "function": {"name": name, "arguments": json.dumps(args)},
                                }
                            ],
                        }
                    }
                ]
            }

        facts = {"baseUrl": "https://example.invalid/v1"}
        if kind == "codex":
            server = bridge.start(facts, ["exact.test_model"], "synthetic", "local", transport=transport)
        else:
            server = bridge.start(facts, ["exact.test_model"], "synthetic", "local", "exact.test_model", transport)
        # No inherited credential values or daemon selectors enter the test CLI.
        env = {
            k: v
            for k, v in os.environ.items()
            if not any(s in k for s in ("KEY", "TOKEN", "CODEX", "PASEO", "GOOGLE", "GEMINI"))
        }
        env.update(HOME=str(workspace), NO_PROXY="localhost,127.0.0.1")
        if kind == "codex":
            catalog = workspace / "models.json"
            catalog.write_text(
                json.dumps(importlib.import_module("catalog").codex_catalog([{"id": "exact.test_model"}]))
            )
            env.update(CODEX_HOME=str(workspace), ACQ_BRIDGE_TOKEN="local")  # noqa: S106 -- synthetic credential-free fixture
            config = {
                "model_provider": "test",
                "model_providers.test.name": "Synthetic provider",
                "model_providers.test.base_url": f"http://127.0.0.1:{server.server_port}/v1",
                "model_providers.test.env_key": "ACQ_BRIDGE_TOKEN",
                "model_catalog_json": str(catalog),
                "features.code_mode": False,
                "web_search": "disabled",
            }
            args = [value for key, setting in config.items() for value in ("-c", key + "=" + json.dumps(setting))]
            args += [
                "exec",
                "--skip-git-repo-check",
                "--sandbox",
                "workspace-write",
                "-m",
                "exact.test_model",
                "Write output.txt containing FILE_MARKER, then report NATIVE_CLI_OK",
            ]
        else:
            env.update(GEMINI_API_KEY="local", GOOGLE_GEMINI_BASE_URL=f"http://127.0.0.1:{server.server_port}")
            config = {
                "modelProvider": "gemini",
                "customModelsConfig": {
                    "customModels": {
                        "exact.test_model": {"modelName": "exact.test_model", "apiProvider": "gemini"},
                    }
                },
            }
            args = [
                "--settings",
                json.dumps(config),
                "--model",
                "exact.test_model",
                "--add-dir",
                str(workspace),
                "--dangerously-skip-permissions",
                "-p",
                "Write output.txt then report NATIVE_CLI_OK",
                "--print-timeout",
                "30s",
            ]
        try:
            result = subprocess.run(  # noqa: S603 -- operator-selected installed CLI, argv only
                [str(binary), *args], cwd=workspace, env=env, capture_output=True, text=True, timeout=45
            )  # noqa: S603 -- operator-selected installed CLI, argv only
            if (
                result.returncode != 0
                or "NATIVE_CLI_OK" not in result.stdout
                or not output.exists()
                or output.read_text() != "FILE_MARKER"
            ):
                raise ValueError(f"native {kind} verification failed (exit {result.returncode}); inspect CLI locally")
            print(
                f"PASS: real {kind} exact-ID selection, function call, file write, tool result "
                f"and final response; {len(seen)} requests"
            )
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kit", choices=("codex", "antigravity"))
    parser.add_argument("--binary", required=True, type=Path)
    args = parser.parse_args()
    verify(args.kit, args.binary.resolve(strict=True))
