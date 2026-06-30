"""Shared ChromaDB client factory with telemetry disabled."""
from __future__ import annotations

import os
from pathlib import Path

# Must be set before chromadb is imported anywhere in the process.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

try:
    import posthog

    posthog.disabled = True
    posthog.capture = lambda *args, **kwargs: None  # chromadb/posthog API mismatch
except ImportError:
    pass

from chromadb.config import Settings as ChromaSettings  # noqa: E402


def chroma_settings() -> ChromaSettings:
    return ChromaSettings(anonymized_telemetry=False)


def persistent_client(path: str | Path):
    import chromadb

    return chromadb.PersistentClient(path=str(path), settings=chroma_settings())
