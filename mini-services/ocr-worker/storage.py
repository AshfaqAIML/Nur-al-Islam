"""Original-file resolution — mirrors src/lib/book-import.ts conventions.

sourceRef values are stable RELATIVE references (books/{bookId}/original.pdf).
Absolute refs and `..` escapes are rejected (path traversal). STORAGE_ROOT env
(NUR_STORAGE) overrides the default ./storage (deployment volume).
"""
from __future__ import annotations

import os


def storage_root(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    return os.environ.get("NUR_STORAGE") or os.path.join(os.getcwd(), "storage")


def resolve_source_path(source_ref: str, root: str | None = None) -> str:
    """Absolute disk path for a sourceRef. Raises on abuse or missing file."""
    if not source_ref or os.path.isabs(source_ref):
        raise ValueError("absolute or empty sourceRef rejected")
    base = os.path.abspath(storage_root(root))
    candidate = os.path.normpath(os.path.join(base, source_ref))
    if os.path.commonpath([base, candidate]) != base:
        raise ValueError("sourceRef escapes storage root")
    if not os.path.isfile(candidate):
        raise FileNotFoundError(f"source file missing: {source_ref}")
    return candidate


def sha256_file(path: str) -> str:
    """Streaming sha256 (bounded 8MB chunks — never loads whole files)."""
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
