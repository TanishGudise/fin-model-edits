# /// script
# requires-python = ">=3.11"
# dependencies = ["anthropic>=1.13,<2"]
# ///
"""Single-turn Claude program: the same system prompt and prompt as the default single-turn
harness, one Messages API call through the official SDK, no tools.

The interception endpoint and secret arrive through argv rather than the environment. The
eval's `--max-output-tokens` replaces `max_tokens` at the interception proxy, so the value here
only satisfies the API's required field. `thinking` is left unset, so each model runs with its own
default (adaptive thinking on the current Claude models); thinking tokens count toward
`max_tokens`, which bounds every response.

Prompt caching: the request sets top-level `cache_control` (automatic caching, 5-minute TTL), so the
breakpoint sits on the last block, the end of the prompt. The whole request is identical across a task's
rollouts, so every byte is shared and nothing per-call is cached. A cache entry is readable only once the
first response has started, so identical requests fired together would all pay full price. A gate (a lock
file per request, keyed by its hash, in CACHE_GATE_DIR) staggers them: the first rollout goes at once and
records its start; an identical one waits until CACHE_GATE_SECONDS (default 40) after that start, by when
the first request's prefill has written the cache, and then reads it. Requests with different prompts don't
wait for each other. CACHE_GATE_SECONDS=0 turns the gate off.
"""

import argparse
import asyncio
import fcntl
import hashlib
import json
import os
import tempfile
import time

import anthropic

GATE_FRESH = 240.0
"""A recorded start older than this (seconds) is past the 5-minute cache TTL's safe margin: start afresh."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--system-prompt", default="")
    parser.add_argument("--prompt", default="")
    return parser.parse_args()


def wait_for_cache(request: dict) -> float:
    """Block until an identical earlier request has had CACHE_GATE_SECONDS to write the cache; return seconds
    waited. The first of a group records its start and returns at once."""
    delay = float(os.environ.get("CACHE_GATE_SECONDS", "40"))
    if delay <= 0:
        return 0.0
    gate_dir = os.environ.get("CACHE_GATE_DIR") or os.path.join(
        tempfile.gettempdir(), "fin-model-edits-cache-gate"
    )
    os.makedirs(gate_dir, exist_ok=True)
    key = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()[:32]
    fd = os.open(os.path.join(gate_dir, key), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            raw = os.pread(fd, 64, 0).decode().strip()
            now = time.time()
            try:
                started = float(raw) if raw else 0.0
            except ValueError:  # a corrupt gate file counts as no earlier start
                started = 0.0
            if now - started > GATE_FRESH:
                os.ftruncate(fd, 0)
                os.pwrite(fd, f"{now:.3f}".encode(), 0)
                return 0.0
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
    wait = max(0.0, started + delay - time.time())
    time.sleep(wait)
    return wait


async def main() -> None:
    args = parse_args()
    client = anthropic.AsyncAnthropic(base_url=args.base_url, api_key=args.api_key, max_retries=0)
    kwargs = {"system": args.system_prompt} if args.system_prompt else {}
    request = {
        "model": args.model,
        "max_tokens": 16384,
        "messages": [{"role": "user", "content": args.prompt}],
        **kwargs,
    }
    wait_for_cache(request)
    await client.messages.create(**request, cache_control={"type": "ephemeral"})


if __name__ == "__main__":
    asyncio.run(main())
