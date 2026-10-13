"""Download the source documents of the reconciliation tasks from SEC EDGAR and check their hashes.

Usage: SEC_USER_AGENT="Your Name you@example.com" python scripts/fetch_sources.py hillman
SEC's fair-access policy requires a User-Agent with a contact address; files land in
FIN_MODEL_EDITS_SOURCES (default sources_cache/, which git ignores). Already-cached files with the
right SHA-256 are not downloaded again."""

from __future__ import annotations

import argparse
import os
import sys

from fin_model_edits.sources.fetch import SourceError, check, fetch, manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("company", help="a manifest name under sources/, e.g. hillman")
    parser.add_argument("--check", action="store_true", help="only report which files are cached and intact")
    args = parser.parse_args()
    docs = manifest(args.company)
    if args.check:
        bad = [d.id for d in docs if not check(d)]
        print(
            f"{len(docs) - len(bad)}/{len(docs)} documents cached and intact"
            + (f"; missing: {bad}" if bad else "")
        )
        return 1 if bad else 0
    agent = os.environ.get("SEC_USER_AGENT", "")
    try:
        fetch(docs, agent)
    except SourceError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"{len(docs)} documents cached and intact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
