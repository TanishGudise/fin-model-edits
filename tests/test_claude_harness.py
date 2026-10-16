"""The Claude single-turn program sends exactly one bounded Messages request, with automatic prompt
caching, and staggers identical requests so later ones can read the cache. Checked offline against a
loopback stand-in for the API."""

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fin_model_edits_claude.harness import PROGRAM_PATH


def test_program_sends_one_bounded_request(tmp_path):
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
            env={**os.environ, "CACHE_GATE_DIR": str(tmp_path)},
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
    assert body["cache_control"] == {"type": "ephemeral"}, "automatic caching, 5-minute TTL"


def _server(arrivals):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            arrivals.append((time.monotonic(), body["messages"][0]["content"]))
            reply = {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": body["model"],
                "content": [{"type": "text", "text": "ok"}],
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
    return server


def test_identical_requests_wait_for_the_first_to_write_the_cache(tmp_path):
    arrivals = []
    server = _server(arrivals)
    env = {**os.environ, "CACHE_GATE_DIR": str(tmp_path), "CACHE_GATE_SECONDS": "2"}

    def launch(prompt):
        return subprocess.Popen(
            [
                sys.executable,
                str(PROGRAM_PATH),
                f"--base-url=http://127.0.0.1:{server.server_port}",
                "--api-key=k",
                "--model=claude-haiku-5-5",
                f"--prompt={prompt}",
            ],
            env=env,
        )

    try:
        start = time.monotonic()
        procs = [launch("SAME"), launch("SAME"), launch("SAME"), launch("OTHER")]
        assert all(p.wait(timeout=60) == 0 for p in procs)
    finally:
        server.shutdown()
    same = sorted(t - start for t, prompt in arrivals if prompt == "SAME")
    other = [t - start for t, prompt in arrivals if prompt == "OTHER"]
    assert len(same) == 3 and len(other) == 1
    assert same[1] - same[0] >= 1.5 and same[2] - same[0] >= 1.5, "identical requests wait for the first"
    assert other[0] < same[1], "a different request doesn't wait"
