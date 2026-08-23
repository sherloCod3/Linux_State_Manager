"""Full snapshot creation.

A snapshot copies discovered state into the tool's own storage:

    <storage>/snapshots/<id>/
        manifest.json   deterministic manifest (see manifest module)
        metadata.json   environment description of the snapshot moment
        data/           file contents; symlinks recreated as symlinks

Creation is atomic: everything is built inside a temporary directory and
renamed into place only when complete. A failure leaves no partial snapshot.

The source tree is never modified.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from linux_state import discovery as discovery_mod
from linux_state.discovery import Entry, Kind
from linux_state.manifest import build_manifest, serialize_manifest

METADATA_VERSION = 1


class SnapshotError(Exception):
    def __init__(self, operation: str, path: Path | None, reason: str):
        self.operation = operation
        self.path = path
        self.reason = reason
        location = str(path) if path is not None else "<unknown>"
        super().__init__(f"{operation} failed for {location}: {reason}")


def new_snapshot_id(now: datetime | None = None) -> str:
    """Filesystem-safe ID: <UTC timestamp>-<4 hex suffix>."""
    now = now or datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"{timestamp}-{uuid.uuid4().hex[:4]}"


def collect_metadata(root: Path) -> dict:
    """Environment description at snapshot time. No sensitive contents."""
    return {
        "version": METADATA_VERSION,
        "created": datetime.now(timezone.utc).isoformat(),
        "root": root.resolve().as_posix(),
        "hostname": platform.node(),
        "distribution": _detect_distribution(),
        "kernel": platform.release(),
        "architecture": platform.machine(),
        "user": _detect_user(),
        "tool_version": _tool_version(),
    }


def _detect_user() -> str:
    import getpass

    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def _tool_version() -> str:
    from linux_state import __version__

    return __version__


def _detect_distribution() -> str:
    """Read PRETTY_NAME from /etc/os-release with a safe fallback."""
    for key in ("PRETTY_NAME", "NAME"):
        value = _os_release_field(key)
        if value:
            return value
    return "unknown"


def _os_release_field(key: str) -> str | None:
    path = Path("/etc/os-release")
    if not path.is_file():
        return None
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() == key:
                return value.strip().strip('"')
    except OSError:
        return None
    return None


def _materialize(entry: Entry, root: Path, destination_root: Path) -> None:
    """Copy one entry into data/, preserving structure."""
    relative = entry.path.relative_to(root)
    destination = destination_root / relative

    if entry.kind == Kind.DIRECTORY:
        destination.mkdir(parents=True, exist_ok=True)
        os.chmod(destination, int(entry.mode, 8))
    elif entry.kind == Kind.FILE:
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(entry.path, destination, follow_symlinks=False)
            os.chmod(destination, int(entry.mode, 8))
        except OSError as exc:
            raise SnapshotError(
                "copy", entry.path, exc.strerror or str(exc)
            ) from exc
    elif entry.kind == Kind.SYMLINK:
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(entry.symlink_target, destination)
        except OSError as exc:
            raise SnapshotError(
                "symlink", entry.path, exc.strerror or str(exc)
            ) from exc
    else:
        # Special files are recorded in the manifest but not copied.
        pass


def create_snapshot(
    root: Path,
    storage_root: Path,
    *,
    hash_files: bool = True,
) -> str:
    """Create a full snapshot of *root* inside *storage_root*.

    Returns the new snapshot id. Raises SnapshotError on failure without
    leaving a partial snapshot behind.
    """
    root = root.resolve()
    if not root.is_dir():
        raise SnapshotError("snapshot", root, "not a directory")

    try:
        entries = list(discovery_mod.discover(root, hash_files=hash_files))
    except discovery_mod.DiscoveryError as exc:
        raise SnapshotError(exc.operation, exc.path, exc.reason) from exc
    snapshot_id = new_snapshot_id()

    final_dir = storage_root / "snapshots" / snapshot_id
    staging_dir = final_dir.with_name(final_dir.name + ".tmp")
    if staging_dir.exists():  # pragma: no cover - uuid collision guard
        raise SnapshotError("snapshot", staging_dir, "staging directory already exists")

    try:
        (staging_dir / "data").mkdir(parents=True)

        manifest = build_manifest(
            root,
            entries,
            include_hashes=hash_files,
        )
        metadata = collect_metadata(root)
        (staging_dir / "manifest.json").write_text(
            serialize_manifest(manifest), encoding="utf-8"
        )
        (staging_dir / "metadata.json").write_text(
            serialize_manifest(metadata), encoding="utf-8"
        )

        for entry in entries:
            _materialize(entry, root, staging_dir / "data")

        # Only publish complete snapshots.
        staging_dir.rename(final_dir)
    except SnapshotError:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    except OSError as exc:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise SnapshotError(
            "snapshot", staging_dir, exc.strerror or str(exc)
        ) from exc

    return snapshot_id


def verify_snapshot(storage_root: Path, snapshot_id: str) -> dict:
    """Re-hash stored files against the manifest. Read-only."""
    from linux_state.storage import (
        data_dir as _data_dir,
        manifest_file as _manifest_file,
    )

    manifest_path = _manifest_file(storage_root, snapshot_id)
    if not manifest_path.is_file():
        raise SnapshotError("verify", manifest_path, "manifest not found")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stored = _data_dir(storage_root, snapshot_id)

    checked = 0
    mismatches: list[str] = []
    for record in manifest["files"]:
        if record["type"] != Kind.FILE.value or "sha256" not in record:
            continue
        path = stored / Path(record["path"]).relative_to(Path(manifest["root"]))
        digest = hashlib.sha256()
        try:
            with path.open("rb") as fh:
                while chunk := fh.read(discovery_mod.CHUNK_SIZE):
                    digest.update(chunk)
        except OSError as exc:
            mismatches.append(f"{record['path']}: {exc.strerror}")
            continue
        if digest.hexdigest() != record["sha256"]:
            mismatches.append(record["path"])
        checked += 1

    return {"checked": checked, "mismatches": mismatches}
