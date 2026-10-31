import importlib
import json
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "files/home/antigravity-kit"))
bridge = importlib.import_module("bridge")
provider = importlib.import_module("provider")
installer = importlib.import_module("install")


class KitTests(unittest.TestCase):
    def test_pins(self):
        self.assertEqual(set(installer.PINS), {"aarch64", "x86_64"})
        self.assertTrue(all(len(pin[1]) == 128 for pin in installer.PINS.values()))

    def test_json_rejects_duplicates_and_constants(self):
        for raw in ['{"key":1,"key":2}', '{"key":Infinity}', '{"key":1e999}']:
            with self.assertRaises(ValueError):
                provider.strict_json(raw)

    def test_function_translation(self):
        messages, tools = bridge.translate(
            {
                "contents": [
                    {
                        "role": "model",
                        "parts": [{"functionCall": {"id": "call", "name": "write", "args": {"path": "file"}}}],
                    },
                    {
                        "role": "user",
                        "parts": [
                            {"functionResponse": {"id": "call", "name": "write", "response": {"result": "done"}}}
                        ],
                    },
                ],
                "tools": [{"functionDeclarations": [{"name": "write", "parametersJsonSchema": {"type": "object"}}]}],
            }
        )
        self.assertEqual(messages[1]["tool_call_id"], "call")
        self.assertEqual(tools[0]["function"]["name"], "write")
        result = bridge.output(
            {"tool_calls": [{"id": "call", "function": {"name": "write", "arguments": "{}"}}]}, {"write"}
        )
        self.assertEqual(result["candidates"][0]["content"]["parts"][0]["functionCall"]["id"], "call")

    def test_rejects_media_and_native_tools(self):
        for data in [{"contents": [{"parts": [{"inlineData": {"data": "x"}}]}]}, {"tools": [{"googleSearch": {}}]}]:
            with self.assertRaises(ValueError):
                bridge.translate(data)
        with self.assertRaises(ValueError):
            bridge.output({"tool_calls": [{"id": "x", "function": {"name": "undeclared", "arguments": "{}"}}]}, set())

    def test_rejects_invalid_role_and_constraints(self):
        for data in [
            {"contents": [{"role": "admin", "parts": []}]},
            {"generationConfig": {"responseMimeType": "application/json"}},
            {"toolConfig": {"functionCallingConfig": {"mode": "NONE"}}},
            {"generationConfig": {"thinkingConfig": {"thinkingBudget": 100}}},
        ]:
            with self.assertRaises(ValueError):
                bridge.translate(data)

    def test_parallel_missing_ids_are_distinct_but_ambiguous_results_fail(self):
        content = {
            "role": "model",
            "parts": [{"functionCall": {"name": "read", "args": {}}}, {"functionCall": {"name": "read", "args": {}}}],
        }
        messages, _ = bridge.translate({"contents": [content]})
        self.assertEqual(len({c["id"] for c in messages[0]["tool_calls"]}), 2)
        response = {"role": "user", "parts": [{"functionResponse": {"name": "read", "response": {}}}]}
        with self.assertRaises(ValueError):
            bridge.translate({"contents": [content, response]})

    def test_generated_ids_do_not_collide_with_explicit_ids(self):
        content = {
            "role": "model",
            "parts": [
                {"functionCall": {"name": "read", "id": "call_2", "args": {}}},
                {"functionCall": {"name": "read", "args": {}}},
            ],
        }
        messages, _ = bridge.translate({"contents": [content]})
        self.assertEqual(len({c["id"] for c in messages[0]["tool_calls"]}), 2)

    def test_http_exact_id_and_housekeeping(self):
        seen = []

        def transport(data):
            seen.append(data)
            return {"choices": [{"message": {"content": "OK"}}]}

        server = bridge.start(
            {"baseUrl": "https://example.invalid/v1"},
            ["exact.model_id", "small"],
            "upstream",
            "local",
            "small",
            transport,
        )
        try:
            for model, token, expected in [
                ("exact.model_id", "local", 200),
                ("gemini-3.1-flash-lite-preview", "local", 200),
                ("native", "local", 400),
                ("exact.model_id", "wrong", 401),
            ]:
                url = f"http://127.0.0.1:{server.server_port}/v1beta/models/{model}:streamGenerateContent?alt=sse"
                request = urllib.request.Request(
                    url,
                    data=json.dumps({"contents": [{"role": "user", "parts": [{"text": "task"}]}]}).encode(),
                    headers={"x-goog-api-key": token},
                )
                try:
                    with urllib.request.urlopen(request, timeout=5) as response:
                        self.assertEqual(response.status, expected)
                        self.assertIn(b"OK", response.read())
                except urllib.error.HTTPError as error:
                    self.assertEqual(error.code, expected)
                    error.close()
            self.assertEqual([d["model"] for d in seen], ["exact.model_id", "small"])
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
