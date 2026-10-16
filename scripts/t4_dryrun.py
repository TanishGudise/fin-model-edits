"""T4's cost gate (outputs/preregistration_v4.md), at $0: the worst case of one trial, from exact token
counts.

It builds the conversation a trial grows into: the instruction plus a real 1280x800 screenshot, then per turn
an assistant message as long as max_tokens allows (filler text measured in tokens) with one computer call, and
a tool result carrying another real screenshot. The free count_tokens endpoint measures it after 1, 2 and
MAX_TURNS turns. The worst case prices every turn's output at max_tokens; with prompt caching each request
reads the previous one's input (cache reads) and writes the new part, and without it every input token is paid
in full. Prints no secrets. Run with ANTHROPIC_API_KEY set (the count_tokens endpoint is free). Usage: python
scripts/t4_dryrun.py SCREENSHOT.png [--turns 80] [--max-tokens 2048] [--model claude-opus-5-5]"""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

import anthropic

from fin_model_edits.gui.agent import PRICES, TOOLSET
from fin_model_edits.gui.task import instruction

FILLER = (
    "The quarterly reconciliation lines tie to the filings; next I check the debt note and the cash balance. "
)


def conversation(turns: int, png: bytes, filler: str) -> list[dict]:
    image = {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(png).decode()},
    }
    messages = [{"role": "user", "content": [{"type": "text", "text": instruction()}, image]}]
    for i in range(turns - 1):
        tid = f"toolu_{i:06d}"
        messages.append(
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": filler},
                    {
                        "type": "tool_use",
                        "id": tid,
                        "name": "screenshot",
                        "input": {},
                        "toolset_name": "computer",
                    },
                ],
            }
        )
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tid,
                        "toolset_name": "computer",
                        "content": [image],
                    },
                ],
            }
        )
    return messages


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("screenshot", type=Path)
    parser.add_argument("--turns", type=int, default=80)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--model", default="claude-opus-5-5")
    args = parser.parse_args()
    client = anthropic.Anthropic(max_retries=1)
    png = args.screenshot.read_bytes()

    def count(turns: int, filler: str) -> int:
        return client.messages.count_tokens(
            model=args.model, tools=[TOOLSET], messages=conversation(turns, png, filler)
        ).input_tokens

    # filler as long as a full max_tokens output, measured in tokens
    base = count(2, "x")
    reps = 1
    while count(2, FILLER * reps) - base < args.max_tokens and reps < 4000:
        reps *= 2
    filler = FILLER * reps
    first, second, last = count(1, filler), count(2, filler), count(args.turns, filler)
    step = second - first
    p_in, p_out, read = PRICES[args.model]
    inputs = [first + step * (n - 1) for n in range(1, args.turns + 1)]
    output = args.turns * args.max_tokens * p_out / 1e6
    cached = (
        first * 1.25 * p_in
        + sum((inputs[n - 1] * read + step * 1.25) * p_in for n in range(2, args.turns + 1))
    ) / 1e6
    uncached = sum(i * p_in for i in inputs) / 1e6
    print(f"model {args.model}, {args.turns} turns, max_tokens {args.max_tokens}")
    print(
        f"tokens: first request {first:,}; each turn adds {step:,} (one screenshot and a full output); "
        f"request {args.turns} measured {last:,}, linear estimate {inputs[-1]:,}"
    )
    print(
        f"worst case with prompt caching: ${cached + output:.2f} (input ${cached:.2f}, output ${output:.2f})"
    )
    print(f"worst case if no request hit the cache: ${uncached * 1.25 + output:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
