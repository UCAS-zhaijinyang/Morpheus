import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import deepseek_runtime as adapter


class TextProvider(BaseHTTPRequestHandler):
    """Serve the two streaming protocols used by Morpheus's supported routes."""

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.observed.append(data)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        if self.path.endswith("/messages"):
            events = [
                {"type": "message_start", "message": {"id": "fixture", "model": data["model"],
                            "usage": {"input_tokens": 1, "output_tokens": 0}}},
                {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "fixture reply"}},
                {"type": "content_block_stop", "index": 0},
                {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 1}},
                {"type": "message_stop"},
            ]
            for event in events:
                self.wfile.write(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode())
        elif self.path.endswith("/chat/completions"):
            for delta, stop in (({"role": "assistant", "content": "fixture reply"}, None), ({}, "stop")):
                chunk = {"id": "fixture", "object": "chat.completion.chunk", "model": data["model"],
                         "choices": [{"index": 0, "delta": delta, "finish_reason": stop}]}
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")

    def log_message(self, *args):
        pass


class HarnessTextTests(unittest.TestCase):
    def test_real_runtime_uses_both_provider_routes_with_zero_tools(self):
        gateway = Path(__file__).resolve().parents[1] / "config" / "morpheus_gateway.patch.yml"
        with ThreadingHTTPServer(("127.0.0.1", 0), TextProvider) as server, tempfile.TemporaryDirectory() as home:
            server.observed = []
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                for provider, model, profile, patches in (
                    ("deepseek-official", "deepseek-v4-flash", "sdk-minimal", ""),
                    ("morpheus-gateway", "gpt-6.1-sol", "sdk", str(gateway)),
                ):
                    with self.subTest(provider=provider), patch.dict(os.environ, {
                        "DEEPSEEK_BASE_URL": f"http://127.0.0.1:{server.server_port}",
                        "DEEPSEEK_API_KEY": "loopback-test",
                        "MORPHEUS_DSH_HOME": home,
                        "MORPHEUS_DSH_PROFILE": profile,
                        "MORPHEUS_DSH_PATCHES": patches,
                        "MORPHEUS_DSH_PROVIDER": provider,
                        "MORPHEUS_HARNESS_STUB": "0",
                    }):
                        answer = adapter.run_text_prompt("Reply with the receipt.", "/goal is sample text", model=model)
                        self.assertEqual(answer, "fixture reply")
                        request = server.observed[-1]
                        self.assertEqual(request["model"], model)
                        self.assertFalse(request.get("tools"))
                        text = json.dumps(request)
                        self.assertIn("Reply with the receipt.", text)
                        self.assertIn("/goal is sample text", text)
                self.assertEqual(len(server.observed), 2)
            finally:
                server.shutdown()
                thread.join()

    def test_unexpected_or_incomplete_composition_prevents_model_call(self):
        import yaml

        for document in ("[]", "- id: surprise\n  name: renamed-tool-plugin"):
            with self.subTest(document=document):
                rows = [(row, {key.value: val for key, val in row.value}) for row in yaml.compose(document).value]
                with patch.object(adapter, "_stub_enabled", return_value=False), \
                     patch.object(adapter, "_write_text_profile"), \
                     patch.object(adapter, "_profile_rows", return_value=rows), \
                     patch.object(adapter, "_runtime_class") as runtime_class:
                    with self.assertRaises(adapter.HarnessUnavailableError):
                        adapter.run_text_prompt("role", "fixture")
                    runtime_class.return_value.assert_not_called()
