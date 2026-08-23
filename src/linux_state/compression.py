"""Snapshot data compression codecs.

Supported algorithms:

    gzip : default; available everywhere (stdlib)
    zstd : optional; requires the stdlib `compression.zstd` module
           (Python 3.14+). Requesting it where unavailable is an explicit
           error, never a silent fallback: a zstd snapshot cannot be read
           on Pythons without the module, so pretending otherwise would
           create unrestorable backups.
    none : legacy reader only. Snapshots created before compression existed
           store plain files; they remain fully restorable but can no
           longer be created.

Stored layout: each regular file is stored individually as
`<relative-path><suffix>` inside the snapshot's data/ directory. Manifest
paths always refer to logical (uncompressed) names.
"""

from __future__ import annotations

import gzip
import shutil
from pathlib import Path

CHUNK_SIZE = 64 * 1024

CREATABLE = ("gzip", "zstd")
READABLE = ("none", "gzip", "zstd")

_SUFFIXES = {"gzip": ".gz", "zstd": ".zst", "none": ""}


class CompressionError(Exception):
    def __init__(self, algorithm: str, reason: str):
        self.algorithm = algorithm
        self.reason = reason
        super().__init__(f"compression {algorithm!r}: {reason}")


def is_available(algorithm: str) -> bool:
    if algorithm == "gzip":
        return True
    if algorithm == "zstd":
        try:
            import compression.zstd  # noqa: F401  (Python 3.14+)

            return True
        except ImportError:
            return False
    if algorithm == "none":
        return True
    return False


def require_available(algorithm: str) -> None:
    if algorithm not in READABLE:
        raise CompressionError(algorithm, "unknown algorithm")
    if not is_available(algorithm):
        raise CompressionError(
            algorithm,
            "not available on this Python; "
            "the stdlib module 'compression.zstd' requires Python 3.14+. "
            "Use --compression gzip instead.",
        )


def normalize(algorithm: str | None) -> str:
    """Map missing metadata fields to the legacy plain layout."""
    return algorithm or "none"


def stored_name(logical_name: str, algorithm: str) -> str:
    return logical_name + _SUFFIXES[algorithm]


def compress(source: Path, destination: Path, algorithm: str) -> None:
    """Compress *source* into *destination* (streaming)."""
    require_available(algorithm)
    try:
        with source.open("rb") as src, _open_write(destination, algorithm) as dst:
            shutil.copyfileobj(src, dst, CHUNK_SIZE)
    except OSError as exc:
        raise CompressionError(algorithm, exc.strerror or str(exc)) from exc


def decompress(source: Path, destination: Path, algorithm: str) -> None:
    """Decompress *source* into *destination* (streaming)."""
    require_available(algorithm)
    try:
        with _open_read(source, algorithm) as src, destination.open("wb") as dst:
            shutil.copyfileobj(src, dst, CHUNK_SIZE)
    except OSError as exc:
        raise CompressionError(algorithm, exc.strerror or str(exc)) from exc


def hash_content(source: Path, algorithm: str) -> str:
    """Hash the logical (decompressed) content of a stored file."""
    import hashlib

    digest = hashlib.sha256()
    require_available(algorithm)
    try:
        with _open_read(source, algorithm) as fh:
            while chunk := fh.read(CHUNK_SIZE):
                digest.update(chunk)
    except OSError as exc:
        raise CompressionError(algorithm, exc.strerror or str(exc)) from exc
    return digest.hexdigest()


def _open_write(path: Path, algorithm: str):
    if algorithm == "gzip":
        return gzip.open(path, "wb")
    if algorithm == "zstd":
        import compression.zstd

        return compression.zstd.open(path, "wb")
    raise CompressionError("none", "plain storage cannot be created")


def _open_read(path: Path, algorithm: str):
    if algorithm == "none":
        return path.open("rb")
    if algorithm == "gzip":
        return gzip.open(path, "rb")
    if algorithm == "zstd":
        import compression.zstd

        return compression.zstd.open(path, "rb")
    raise CompressionError(algorithm, "unknown algorithm")
