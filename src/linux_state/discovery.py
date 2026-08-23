"""Read-only filesystem discovery.

Discovery never modifies the scanned tree. It streams entries in
deterministic (sorted) order and represents symlinks as symlinks,
never following them during traversal.
"""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterator, Optional

CHUNK_SIZE = 64 * 1024


class Kind(str, Enum):
    FILE = "file"
    DIRECTORY = "directory"
    SYMLINK = "symlink"
    OTHER = "other"


class DiscoveryError(Exception):
    """Raised when the filesystem cannot be read at a specific path."""

    def __init__(self, operation: str, path: Path, reason: str):
        self.operation = operation
        self.path = path
        self.reason = reason
        super().__init__(f"{operation} failed for {path}: {reason}")


@dataclass(frozen=True)
class Entry:
    path: Path
    kind: Kind
    mode: str  # octal permission bits, e.g. "0644"
    size: int  # 0 for non-files
    mtime: float
    uid: int
    gid: int
    sha256: Optional[str] = None  # regular files only
    symlink_target: Optional[str] = None  # symlinks only
    broken_symlink: bool = False

    def relative_to(self, root: Path) -> str:
        return self.path.relative_to(root).as_posix()


def hash_file(path: Path) -> str:
    """Stream-hash a file without loading it fully into memory."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            while chunk := fh.read(CHUNK_SIZE):
                digest.update(chunk)
    except OSError as exc:
        raise DiscoveryError("hash", path, exc.strerror or str(exc)) from exc
    return digest.hexdigest()


def _mode(st: os.stat_result) -> str:
    return format(stat.S_IMODE(st.st_mode), "04o")


def _symlink_entry(path: Path) -> Entry:
    try:
        target = os.readlink(path)
    except OSError as exc:
        raise DiscoveryError("readlink", path, exc.strerror or str(exc)) from exc
    broken = not os.path.exists(path)
    return Entry(
        path=path,
        kind=Kind.SYMLINK,
        mode="0777",
        size=0,
        mtime=0.0,
        uid=0,
        gid=0,
        symlink_target=target,
        broken_symlink=broken,
    )


def discover(
    root: Path,
    *,
    hash_files: bool = True,
    _dir: Optional[Path] = None,
) -> Iterator[Entry]:
    """Yield entries under *root* in deterministic sorted order.

    Read-only: no file is opened for writing, no symlink is followed,
    no directory is traversed through a symlink.
    """
    root = root.resolve()
    current = _dir if _dir is not None else root

    try:
        with os.scandir(current) as scanner:
            children = sorted(scanner, key=lambda e: e.name)
    except OSError as exc:
        raise DiscoveryError("scandir", current, exc.strerror or str(exc)) from exc

    for child in children:
        path = Path(child.path)
        try:
            st = child.stat(follow_symlinks=False)
        except OSError as exc:
            raise DiscoveryError("stat", path, exc.strerror or str(exc)) from exc

        if stat.S_ISLNK(st.st_mode):
            yield _symlink_entry(path)
            continue

        if stat.S_ISDIR(st.st_mode):
            yield Entry(
                path=path,
                kind=Kind.DIRECTORY,
                mode=_mode(st),
                size=0,
                mtime=st.st_mtime,
                uid=st.st_uid,
                gid=st.st_gid,
            )
            yield from discover(
                root,
                hash_files=hash_files,
                _dir=path,
            )
            continue

        if stat.S_ISREG(st.st_mode):
            sha256 = hash_file(path) if hash_files else None
            yield Entry(
                path=path,
                kind=Kind.FILE,
                mode=_mode(st),
                size=st.st_size,
                mtime=st.st_mtime,
                uid=st.st_uid,
                gid=st.st_gid,
                sha256=sha256,
            )
            continue

        yield Entry(
            path=path,
            kind=Kind.OTHER,
            mode=_mode(st),
            size=0,
            mtime=st.st_mtime,
            uid=st.st_uid,
            gid=st.st_gid,
        )
