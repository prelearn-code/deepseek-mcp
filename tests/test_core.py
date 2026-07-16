import json
import unittest
from unittest.mock import patch

from deepseek_worker import core


class FakeHeaders:
    def get(self, name, default=""):
        return "text/event-stream; charset=utf-8" if name.lower() == "content-type" else default


class FakeStreamResponse:
    headers = FakeHeaders()

    def __init__(self, lines):
        self.lines = [line.encode("utf-8") for line in lines]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter(self.lines)


class PatchValidationTests(unittest.TestCase):
    def test_accepts_patch_for_allowed_path(self):
        candidate = "diff --git a/src/app.py b/src/app.py\n--- a/src/app.py\n+++ b/src/app.py\n@@ -1 +1 @@\n-old\n+new\n"
        core._validate_patch(candidate, {"src/app.py"})

    def test_rejects_path_outside_allowlist(self):
        candidate = "diff --git a/.env b/.env\n--- a/.env\n+++ b/.env\n@@ -1 +1 @@\n-old\n+secret\n"
        with self.assertRaisesRegex(core.DeepSeekError, "outside allowed_paths"):
            core._validate_patch(candidate, {"src/app.py"})

    def test_rejects_binary_patch(self):
        with self.assertRaisesRegex(core.DeepSeekError, "binary"):
            core._validate_patch("diff --git a/a b/a\nGIT binary patch\n", {"a"})


class StreamingTests(unittest.TestCase):
    def test_collects_content_and_ignores_reasoning(self):
        candidate = {"summary": "ok", "patch": "", "tests": [], "assumptions": [], "risks": []}
        text = json.dumps(candidate)
        lines = [
            'data: {"model":"deepseek-v4-pro","choices":[{"delta":{"reasoning_content":"private"},"finish_reason":null}]}\n',
            "data: " + json.dumps({"choices": [{"delta": {"content": text[:20]}, "finish_reason": None}]}) + "\n",
            "data: " + json.dumps({"choices": [{"delta": {"content": text[20:]}, "finish_reason": "stop"}]}) + "\n",
            'data: {"choices":[],"usage":{"total_tokens":10}}\n',
            "data: [DONE]\n",
        ]
        events = []
        with patch.object(core.urllib.request, "urlopen", return_value=FakeStreamResponse(lines)):
            result = core._post_stream("https://example.test/chat/completions", "secret", {}, 30, progress=lambda *args: events.append(args))
        self.assertEqual(json.loads(result["content"])["summary"], "ok")
        self.assertEqual(result["usage"]["total_tokens"], 10)
        self.assertTrue(any(event[0] == "reasoning_delta" for event in events))

    @patch("deepseek_worker.core._post_stream")
    def test_generate_patch_uses_stream(self, post_stream):
        candidate = {"summary": "ok", "patch": "", "tests": [], "assumptions": [], "risks": []}
        post_stream.return_value = {"content": json.dumps(candidate), "model": "deepseek-v4-pro", "usage": {"total_tokens": 10}}
        result = core.generate_patch("Change greeting", "FILE app.py\nold", ["app.py"], api_key="test-key")
        self.assertEqual(result["worker"], "deepseek")
        self.assertEqual(post_stream.call_args.args[3], 1500.0)
        payload = post_stream.call_args.args[2]
        self.assertNotIn("stream", payload)
        self.assertEqual(payload["response_format"], {"type": "json_object"})

    def test_requires_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(core.DeepSeekError, "DEEPSEEK_API_KEY"):
                core.generate_patch("task", "FILE app.py", ["app.py"])


if __name__ == "__main__":
    unittest.main()
