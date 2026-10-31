import hashlib
import importlib
import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "files/home/codex-kit"))
bridge = importlib.import_module("bridge")
provider = importlib.import_module("provider")
installer = importlib.import_module("install")
launch = importlib.import_module("launch")
catalog = importlib.import_module("catalog")


class KitTests(unittest.TestCase):
    def test_archive_integrity_and_member(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "cli.tgz"
            with tarfile.open(archive, "w:gz") as bundle:
                member = tarfile.TarInfo("cli")
                member.size = 3
                bundle.addfile(member, io.BytesIO(b"cli"))
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            installer.extract(archive, digest, "cli", root / "out")
            self.assertEqual((root / "out").stat().st_mode & 0o777, 0o755)
            with self.assertRaises(ValueError):
                installer.extract(archive, "0" * 64, "cli", root / "bad")
            with self.assertRaises(ValueError):
                installer.extract(archive, digest, "absent", root / "bad")

    def test_pin_lengths(self):
        self.assertEqual(set(installer.PINS), {"x86_64", "aarch64"})
        self.assertTrue(all(len(pin[1]) == 64 for pin in installer.PINS.values()))

    def test_strict_json(self):
        for raw in ['{"a":1,"a":2}', '{"a":NaN}', '{"a":1e999}']:
            with self.assertRaises(ValueError):
                provider.strict_json(raw)

    def test_provider_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "models/providers/test"
            path.mkdir(parents=True)
            facts = {
                "schemaVersion": "acq-provider-facts/v1",
                "providerId": "test",
                "apiProtocol": "openai-compatible",
                "host": "example.invalid",
                "baseUrl": "https://example.invalid/v1",
                "keyEnv": "TEST_MODEL_KEY",
            }
            snapshot = {
                "schemaVersion": "acq-neutral-model-catalog/v1",
                "providerId": "test",
                "models": [{"id": "exact.model_id"}],
                "recommendations": {"primary": "exact.model_id"},
            }
            (path / "facts.json").write_text(json.dumps(facts))
            (path / "snapshot.json").write_text(json.dumps(snapshot))
            env = {"ACQ_PROVIDER_INPUT_ROOT": str(root), "TEST_MODEL_KEY": "test-only"}
            self.assertEqual(provider.load("CODEX", env)[2], "exact.model_id")
            for field, value in [
                ("host", "other.invalid"),
                ("baseUrl", "http://example.invalid"),
                ("keyEnv", "GITHUB_TOKEN"),
            ]:
                (path / "facts.json").write_text(json.dumps({**facts, field: value}))
                with self.assertRaises(ValueError):
                    provider.load("CODEX", env)
            (path / "facts.json").write_text(json.dumps(facts))
            with self.assertRaises(ValueError):
                provider.load("CODEX", {**env, "ACQ_CODEX_MODEL": "unknown"})
            with self.assertRaises(ValueError):
                provider.load("CODEX", {"ACQ_PROVIDER_INPUT_ROOT": str(root)})

    def test_argument_boundary_and_routing(self):
        launch.check_args(["exec", "--", "--config=secret", "--model", "unknown"], ["exact"])
        for args in [
            ["--model", "unknown"],
            ["--model=unknown"],
            ["-c", "route=x"],
            ["--remote", "ws://example"],
            ["--search"],
        ]:
            with self.assertRaises(ValueError):
                launch.check_args(args, ["exact"])

    def test_environment_removes_credentials(self):
        with patch.dict(
            os.environ, {"TEST_MODEL_KEY": "sensitive", "GITHUB_TOKEN": "sensitive", "USAI_API_KEY": "sensitive"}
        ):
            result = launch.environment({"TEST_MODEL_KEY"}, Path("/state"), "local-token")
            self.assertNotIn("TEST_MODEL_KEY", result)
            self.assertNotIn("GITHUB_TOKEN", result)
            self.assertNotIn("USAI_API_KEY", result)
            self.assertEqual(result["ACQ_BRIDGE_TOKEN"], "local-token")

    def test_catalog_exact_ids(self):
        result = catalog.codex_catalog([{"id": "exact.model_id"}])
        self.assertEqual(result["models"][0]["slug"], "exact.model_id")
        self.assertEqual(result["models"][0]["supported_reasoning_levels"], [])

    def test_function_roundtrip(self):
        messages, tools, names = bridge.responses_request(
            {
                "input": [
                    {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "task"}]},
                    {
                        "type": "function_call",
                        "namespace": "ns",
                        "name": "write",
                        "arguments": "{}",
                        "call_id": "call_1",
                    },
                    {"type": "function_call_output", "call_id": "call_1", "output": "done"},
                ],
                "tools": [{"type": "namespace", "name": "ns", "tools": [{"type": "function", "name": "write"}]}],
            }
        )
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(tools[0]["function"]["name"], "ns__write")
        output = bridge.response_output(
            {"tool_calls": [{"id": "call_2", "function": {"name": "ns__write", "arguments": "{}"}}]}, names
        )
        self.assertEqual(output[0]["namespace"], "ns")
        self.assertEqual(output[0]["name"], "write")
        self.assertIn(
            "response.function_call_arguments.done", "".join(bridge.events({"status": "completed", "output": output}))
        )

    def test_unsupported_shapes(self):
        for data in [
            {"input": [{"type": "compaction"}]},
            {"tools": [{"type": "web_search"}]},
            {"previous_response_id": "resp_other"},
            {"input": [{"role": "user", "content": [{"type": "input_image"}]}]},
        ]:
            with self.assertRaises(ValueError):
                bridge.responses_request(data)

    def test_sse_initial_items_are_empty(self):
        item = {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": "ONCE", "annotations": []}],
        }
        frames = [json.loads(frame.split("data: ")[1]) for frame in bridge.events({"output": [item]})]
        added = next(frame for frame in frames if frame["type"] == "response.output_item.added")
        self.assertEqual(added["item"]["content"], [])
        self.assertEqual([f["sequence_number"] for f in frames], list(range(len(frames))))

    def test_rejects_behavior_constraints(self):
        for data in [
            {"tool_choice": "made-up"},
            {"text": {"format": {"type": "json_schema"}}},
            {"reasoning": {"effort": "high"}},
            {"stream": "true"},
        ]:
            with self.assertRaises(ValueError):
                bridge.responses_request(data)

    def test_parallel_calls_are_one_batch_and_strict_is_preserved(self):
        data = {
            "input": [
                {"type": "function_call", "name": "f", "call_id": "a", "arguments": "{}"},
                {"type": "function_call", "name": "f", "call_id": "b", "arguments": "{}"},
                {"type": "function_call_output", "call_id": "b", "output": "B"},
                {"type": "function_call_output", "call_id": "a", "output": "A"},
            ],
            "tools": [{"type": "function", "name": "f", "strict": True}],
        }
        messages, tools, _ = bridge.responses_request(data)
        self.assertEqual(len(messages), 3)
        self.assertEqual(len(messages[0]["tool_calls"]), 2)
        self.assertTrue(tools[0]["function"]["strict"])
        with self.assertRaises(ValueError):
            bridge.responses_request({"input": data["input"][:2]})

    def test_http_auth_model_and_fixed_errors(self):
        seen = []

        def transport(data):
            seen.append(data)
            return {"choices": [{"message": {"content": "OK"}}]}

        server = bridge.start(
            {"baseUrl": "https://example.invalid/v1"}, ["exact"], "upstream-only", "local", transport=transport
        )
        try:
            url = f"http://127.0.0.1:{server.server_port}/v1/responses"
            for token, model, expected in [("wrong", "exact", 401), ("local", "missing", 400), ("local", "exact", 200)]:
                request = urllib.request.Request(
                    url,
                    data=json.dumps({"model": model, "input": "task", "stream": True}).encode(),
                    headers={"Authorization": "Bearer " + token},
                )
                try:
                    with urllib.request.urlopen(request, timeout=5) as response:
                        self.assertEqual(response.status, expected)
                        self.assertIn(b"response.completed", response.read())
                except urllib.error.HTTPError as error:
                    self.assertEqual(error.code, expected)
                    self.assertNotIn(b"upstream-only", error.read())
                    error.close()
            self.assertEqual(len(seen), 1)
            self.assertEqual(set(seen[0]), {"model", "messages", "stream"})
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
