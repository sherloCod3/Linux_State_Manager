"""Snapshot storage locations.

Storage lives under ``$XDG_DATA_HOME/linux-state`` by default, keeping
snapshots separate from the user's original files (ADR-001).

Layout:

    <storage>/
        config.json          (reserved; not created yet)
        snapshots/
            <snapshot-id>/
                manifest.json
                metadata.json
                data/
"""

from __future__ import annotations

import os
import re
from pathlib import Path

SNAPSHOT_ID_PATTERN = re.compile(r"^[0-9TzZ.\-]+-[0-9a-f]{4}$")


def default_storage_root() -> Path:
    """Resolve the default storage root honoring XDG_DATA_HOME."""
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return base / "linux-state"


def snapshots_dir(storage_root: Path) -> Path:
    return storage_root / "snapshots"


def list_snapshots(storage_root: Path) -> list[str]:
    """Return known snapshot IDs, sorted oldest first."""
    directory = snapshots_dir(storage_root)
    if not directory.is_dir():
        return []
    ids = [
        entry.name
        for entry in directory.iterdir()
        if entry.is_dir() and SNAPSHOT_ID_PATTERN.match(entry.name)
    ]
    return sorted(ids)


def snapshot_path(storage_root: Path, snapshot_id: str) -> Path:
    if not SNAPSHOT_ID_PATTERN.match(snapshot_id):
        raise ValueError(f"invalid snapshot id: {snapshot_id!r}")
    return snapshots_dir(storage_root) / snapshot_id


def manifest_file(storage_root: Path, snapshot_id: str) -> Path:
    return snapshot_path(storage_root, snapshot_id) / "manifest.json"


def metadata_file(storage_root: Path, snapshot_id: str) -> Path:
    return snapshot_path(storage_root, snapshot_id) / "metadata.json"


def data_dir(storage_root: Path, snapshot_id: str) -> Path:
    return snapshot_path(storage_root, snapshot_id) / "data"
