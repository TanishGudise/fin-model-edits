"""The Claude single-turn program sends exactly one bounded Messages request. Checked offline
against a loopback stand-in for the API."""

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fin_model_edits_claude.harness import PROGRAM_PATH


def test_program_sends_one_bounded_request():
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append((self.path, self.headers.get("x-api-key"), body))
            reply = {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": body["model"],
                "content": [{"type": "text", "text": "```edits\n```"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
            data = json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(PROGRAM_PATH),
                f"--base-url=http://127.0.0.1:{server.server_port}",
                "--api-key=per-rollout-secret",
                "--model=claude-haiku-5-5",
                "--system-prompt=SYSTEM",
                "--prompt=PROMPT",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
    finally:
        server.shutdown()
    assert result.returncode == 0, result.stderr
    assert len(seen) == 1, "one request, no retries"
    path, key, body = seen[0]
    assert path == "/v1/messages" and key == "per-rollout-secret"
    assert body["model"] == "claude-haiku-5-5" and body["max_tokens"] == 16384
    assert body["system"] == "SYSTEM" and body["messages"] == [{"role": "user", "content": "PROMPT"}]
    assert "thinking" not in body and "tools" not in body, "model defaults, no tools"
