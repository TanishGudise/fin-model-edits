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
"""

import argparse
import asyncio

import anthropic


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--system-prompt", default="")
    parser.add_argument("--prompt", default="")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    client = anthropic.AsyncAnthropic(base_url=args.base_url, api_key=args.api_key, max_retries=0)
    kwargs = {"system": args.system_prompt} if args.system_prompt else {}
    await client.messages.create(
        model=args.model,
        max_tokens=16384,
        messages=[{"role": "user", "content": args.prompt}],
        **kwargs,
    )


if __name__ == "__main__":
    asyncio.run(main())
