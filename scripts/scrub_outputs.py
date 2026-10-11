"""Make eval outputs safe to publish. Run after every `uv run eval`, before committing.

Redacts in place the `X-Prime-Team-ID` header value, which v1 writes into config.toml and
eval.log whether it comes from `--client.headers` or the PRIME_TEAM_ID environment variable, and
replaces the inference base URL with <INFERENCE_URL>.
Then fails (exit 1) if any output still contains the inference API key, a bearer token or the
canary GUID (reference, alternate and cheat files carry it; a model reply can't legitimately).

Usage: uv run python scripts/scrub_outputs.py [outputs-dir]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from fin_model_edits.tasks import CANARY_GUID

BASE_URL = re.compile(r"""(base_url["']?\s*[=:]\s*["'])(https?://[^"'\s]+)""")
TEAM_HEADER = re.compile(r"""(X-Prime-Team-ID["']?\s*[=:]\s*["']?)([A-Za-z0-9_-]+)""")
TOKEN_PATTERNS = [re.compile(r"(?i)bearer\s+[a-z0-9._-]{16,}"), re.compile(r"\bsk-[A-Za-z0-9]{16,}")]


def _api_key() -> str:
    config = Path.home() / ".prime" / "config.json"
    if not config.exists():
        return ""
    return json.loads(config.read_text()).get("api_key", "") or ""


def scrub_text(path: Path) -> bool:
    text = path.read_text(errors="replace")
    redacted = TEAM_HEADER.sub(r"\1<redacted>", text)
    redacted = BASE_URL.sub(r"\1<INFERENCE_URL>", redacted)
    if redacted != text:
        path.write_text(redacted)
        return True
    return False


def leaks(path: Path, api_key: str) -> list[str]:
    text = path.read_text(errors="replace")
    found = []
    if api_key and api_key in text:
        found.append("API key")
    found += [f"token /{p.pattern}/" for p in TOKEN_PATTERNS if p.search(text)]
    if TEAM_HEADER.search(text.replace("<redacted>", "")):
        found.append("team id")
    if BASE_URL.search(text):
        found.append("inference base URL")
    if CANARY_GUID in text:
        found.append("canary GUID")
    return found


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outputs")
    api_key = _api_key()
    problems = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if path.suffix != ".jsonl" and scrub_text(path):
            print(f"redacted: {path}")
        problems += [f"{path}: {leak}" for leak in leaks(path, api_key)]
    if problems:
        print("LEAKS FOUND:\n  " + "\n  ".join(problems))
        return 1
    print(f"clean: {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
