"""T4's per-trial table (outputs/preregistration_v4.md): pass or fail, how the trial stopped, turns, cut-off
turns, requests, metered cost, minutes, screenshots, and the failed checks with their cells, from each trial's
result.json, trajectory.jsonl and meter ledger. No model calls. The failure point and the interface-or-finance
call come from reading the trajectory and screenshots by hand; this only gathers the numbers.

Usage: python scripts/t4_report.py JOBS_DIR TRIAL [TRIAL ...]"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def trial_row(jobs: Path, name: str) -> dict:
    out = jobs / name
    result = json.loads((out / "result.json").read_text())
    turns = [json.loads(line) for line in (out / "trajectory.jsonl").read_text().splitlines() if line.strip()]
    ledger = jobs / f"ledger-{name}.jsonl"
    metered = (
        sum(json.loads(line)["cost"] for line in ledger.read_text().splitlines()) if ledger.exists() else None
    )
    times = [t["t"] for t in turns if "t" in t]
    actions: dict[str, int] = {}
    for t in turns:
        for c in t.get("calls", []):
            actions[c["name"]] = actions.get(c["name"], 0) + 1
    errors = sum(1 for t in turns for r in t.get("results", []) if r.get("is_error"))
    return {
        "trial": name,
        "score": result.get("score"),
        "stop": result.get("stop"),
        "harness_stop": result.get("harness_stop"),
        "turns": result.get("turns"),
        "truncated": result.get("truncated_turns"),
        "requests": result.get("requests"),
        "metered": round(metered, 4) if metered is not None else None,
        "minutes": round((times[-1] - times[0]) / 60, 1) if len(times) > 1 else None,
        "screenshots": len(list((out / "screenshots").glob("*.png"))),
        "actions": dict(sorted(actions.items(), key=lambda kv: -kv[1])),
        "action_errors": errors,
        "failed": result.get("failed"),
        "issues": result.get("issues"),
        "details": result.get("details"),
        "last_text": next((t["text"][-1] for t in reversed(turns) if t.get("text")), None),
    }


def main() -> int:
    jobs = Path(sys.argv[1])
    for name in sys.argv[2:]:
        print(json.dumps(trial_row(jobs, name), indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
