"""Source documents for the reconciliation tasks: public SEC filings listed in a manifest
(sources/<company>.toml) with their accession numbers, URLs and SHA-256 hashes.

The documents are not stored in the repository. `fetch` downloads them from EDGAR into a local
cache (FIN_MODEL_EDITS_SOURCES, default `sources_cache/` in the repository), politely: SEC's
fair-access rules ask for a User-Agent naming the requester with a contact address, and at most
10 requests a second (this sends one a second). Every file is checked against its hash, so a
changed filing is caught instead of silently changing the tasks."""

from __future__ import annotations

import hashlib
import os
import time
import tomllib
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from fin_model_edits.sources.convert import html_to_text

REPO = Path(__file__).resolve().parent.parent.parent
MANIFESTS = REPO / "sources"


@dataclass(frozen=True)
class Document:
    company: str
    id: str
    title: str
    form: str
    filed: str
    accession: str
    file: str
    url: str
    sha256: str
    bytes: int
    blackline: bool


def manifest(company: str) -> list[Document]:
    data = tomllib.loads((MANIFESTS / f"{company}.toml").read_text())
    return [Document(company=company, **d) for d in data["documents"]]


def cache_dir() -> Path:
    return Path(os.environ.get("FIN_MODEL_EDITS_SOURCES", REPO / "sources_cache"))


def path_of(doc: Document) -> Path:
    return cache_dir() / doc.company / doc.file


class SourceError(RuntimeError):
    pass


def check(doc: Document) -> bool:
    p = path_of(doc)
    return p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == doc.sha256


def fetch(docs: list[Document], user_agent: str, log=print) -> None:
    """Download every document not already cached with the right hash."""
    missing = [d for d in docs if not check(d)]
    if missing and "@" not in user_agent:
        raise SourceError("SEC asks for a User-Agent with a contact email, e.g. 'Name name@example.com'")
    for doc in missing:
        time.sleep(1.0)
        req = urllib.request.Request(
            doc.url, headers={"User-Agent": user_agent, "Accept-Encoding": "identity"}
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
        except OSError as exc:  # HTTPError and URLError are OSErrors
            raise SourceError(f"{doc.id}: download failed: {exc}") from exc
        digest = hashlib.sha256(data).hexdigest()
        if digest != doc.sha256:
            raise SourceError(f"{doc.id}: SHA-256 {digest} does not match the manifest ({doc.sha256})")
        path_of(doc).parent.mkdir(parents=True, exist_ok=True)
        path_of(doc).write_bytes(data)
        log(f"fetched {doc.id} ({len(data):,} bytes)")


def text(doc: Document) -> str:
    """The document as plain text (blackline markers kept for marked-up copies)."""
    if not check(doc):
        raise SourceError(f"{doc.id} is missing or changed; run scripts/fetch_sources.py first")
    return html_to_text(path_of(doc).read_text(encoding="utf-8", errors="replace"), blackline=doc.blackline)
