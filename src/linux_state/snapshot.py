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

import json
import os
import platform
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from linux_state import discovery as discovery_mod
from linux_state.compression import CompressionError
from linux_state.discovery import Entry, Kind
from linux_state.manifest import build_manifest, serialize_manifest

import fnmatch

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


def _materialize(
    entry: Entry,
    root: Path,
    destination_root: Path,
    compression: str = "none",
    compute_hash: bool = True,
) -> tuple[bool, Entry | None]:
    """Store one entry into data/, preserving structure.

    Regular files are stored compressed per *compression*; the manifest
    keeps referring to logical (uncompressed) paths.

    Returns (False, None) when a regular file vanished between discovery and
    capture (live tree); the caller records the skip. Other errors raise.
    When *compute_hash* is True a single read computes the SHA-256 while
    compressing, avoiding the pre-compression double-read.

    On success returns (True, entry) where entry may be a new Entry with
    an updated ``sha256`` when hashing was requested.
    """
    from dataclasses import replace

    from linux_state import compression as codec

    relative = entry.path.relative_to(root)
    if entry.kind == Kind.FILE:
        destination = destination_root / codec.stored_name(relative.as_posix(), compression)
    else:
        destination = destination_root / relative

    if entry.kind == Kind.DIRECTORY:
        destination.mkdir(parents=True, exist_ok=True)
        os.chmod(destination, int(entry.mode, 8))
        return True, entry
    elif entry.kind == Kind.FILE:
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            if compute_hash:
                digest = codec.compress_and_hash(entry.path, destination, compression)
                # Entry is frozen; create updated copy with hash.
                entry = replace(entry, sha256=digest)
            else:
                codec.compress(entry.path, destination, compression)
        except FileNotFoundError:
            return False, None
        except OSError as exc:
            raise SnapshotError(
                "copy", entry.path, exc.strerror or str(exc)
            ) from exc
        return True, entry
    elif entry.kind == Kind.SYMLINK:
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(entry.symlink_target, destination)
        except OSError as exc:
            raise SnapshotError(
                "symlink", entry.path, exc.strerror or str(exc)
            ) from exc
        return True, entry
    else:
        # Special files are recorded in the manifest but not copied.
        return True, entry


def _filter_entries(
    entries: list[Entry],
    root: Path,
    classifier,
    xdg,
    profile,
    exclude: list[str] | None,
) -> list[Entry]:
    """Apply profile selection and exclude globs to discovery entries.

    Profile filtering reuses the same Classifier + ProfileResolver logic as
    `plan`, so `snapshot --profile X` captures exactly what `plan --profile X`
    would consider. Exclude globs are applied after profile selection and
    match relative POSIX paths (fnmatch, `*` and `**`).
    """
    filtered = entries
    if profile is not None:
        if classifier is None:
            from linux_state.classification import XdgDirs, default_rule_files, load_ruleset

            classifier = load_ruleset(default_rule_files())
            if xdg is None:
                xdg = XdgDirs()
        from linux_state.profiles import select_entries

        # Build (relative, Classification) tuples for the selector.
        classified = []
        for entry in filtered:
            rel = entry.relative_to(root)
            result = classifier.classify(rel, xdg, root)
            classified.append((rel, result))
        selected = {path for path, _ in select_entries(classified, profile)}
        filtered = [e for e in filtered if e.relative_to(root) in selected]
    if exclude:
        normalized = []
        for pat in exclude:
            p = pat.strip()
            if p.startswith("~/"):
                p = p[2:]
            p = p.lstrip("/")
            if p:
                normalized.append(p)
        if normalized:
            kept: list[Entry] = []
            for entry in filtered:
                rel = entry.relative_to(root)
                # fnmatch alone does not make '**' semantics intuitive
                # (e.g. 'Documents' should be excluded by 'Documents/**').
                excluded = False
                for pat in normalized:
                    if pat.endswith("/**"):
                        base = pat[:-3]
                        if rel == base or rel.startswith(base + "/"):
                            excluded = True
                            break
                    if fnmatch.fnmatch(rel, pat):
                        excluded = True
                        break
                if excluded:
                    continue
                kept.append(entry)
            filtered = kept
    return filtered


def create_snapshot(
    root: Path,
    storage_root: Path,
    *,
    hash_files: bool = True,
    classifier=None,
    xdg=None,
    compression: str = "gzip",
    skipped: list[Path] | None = None,
    profile=None,
    exclude: list[str] | None = None,
) -> str:
    """Create a snapshot of *root* inside *storage_root*.

    By default a full snapshot is created. When *profile* is given only
    entries selected by that profile are captured; *exclude* globs are
    applied afterwards. This allows reduced-amplitude snapshots
    (e.g. configs-only) without shrinking partitions.

    Returns the new snapshot id. Raises SnapshotError on failure without
    leaving a partial snapshot behind.

    Regular files deleted by the running system between discovery and
    capture are reported via *skipped* (when given) instead of aborting;
    they are excluded from the manifest so it only describes stored data.
    """
    from linux_state import compression as codec

    codec.require_available(compression)
    root = root.resolve()
    if not root.is_dir():
        raise SnapshotError("snapshot", root, "not a directory")

    try:
        # Discover without hashing; hash is computed in a single pass while
        # compressing (snapshot.py: _materialize with compress_and_hash) to
        # avoid double-reading every file. This halves I/O for large trees.
        entries = list(discovery_mod.discover(root, hash_files=False))
    except discovery_mod.DiscoveryError as exc:
        raise SnapshotError(exc.operation, exc.path, exc.reason) from exc
    # Profile / exclude filtering (amplitude reduction) before materialization.
    if profile is not None or exclude:
        entries = _filter_entries(entries, root, classifier, xdg, profile, exclude)
    snapshot_id = new_snapshot_id()

    final_dir = storage_root / "snapshots" / snapshot_id
    staging_dir = final_dir.with_name(final_dir.name + ".tmp")
    if staging_dir.exists():  # pragma: no cover - uuid collision guard
        raise SnapshotError("snapshot", staging_dir, "staging directory already exists")

    try:
        (staging_dir / "data").mkdir(parents=True)

        metadata = collect_metadata(root)
        metadata["compression"] = compression
        if profile is not None:
            metadata["profile"] = getattr(profile, "name", str(profile))
        if exclude:
            metadata["exclude"] = list(exclude)
        # Streaming JSON dump avoids the 400 MB intermediate string that
        # OOM-kills large snapshots (750k entries).
        from linux_state.manifest import write_manifest_atomic

        write_manifest_atomic(metadata, staging_dir / "metadata.json")

        vanished: list[Path] = []
        captured: list[Entry] = []
        for entry in entries:
            ok, updated = _materialize(
                entry, root, staging_dir / "data", compression, compute_hash=hash_files
            )
            if not ok:
                vanished.append(entry.path)
            else:
                captured.append(updated if updated is not None else entry)
        entries = captured
        if vanished and skipped is not None:
            skipped.extend(vanished)

        # Sort once in-place and avoid the duplicate sorted() copy inside
        # build_manifest. This halves peak memory for the entry list.
        entries.sort(key=lambda e: e.relative_to(root))
        # Written after capture so the manifest describes only data that
        # is actually present in the snapshot.
        manifest = build_manifest(
            root,
            entries,
            include_hashes=hash_files,
            classifier=classifier,
            xdg=xdg,
            snapshot_metadata={"id": snapshot_id},
            already_sorted=True,
        )
        write_manifest_atomic(manifest, staging_dir / "manifest.json")

        # Only publish complete snapshots.
        staging_dir.rename(final_dir)
    except SnapshotError:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    except CompressionError as exc:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise SnapshotError("snapshot", staging_dir, str(exc)) from exc
    except OSError as exc:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise SnapshotError(
            "snapshot", staging_dir, exc.strerror or str(exc)
        ) from exc

    return snapshot_id


def verify_snapshot(storage_root: Path, snapshot_id: str) -> dict:
    """Re-hash stored files against the manifest. Read-only."""
    from linux_state import compression as codec
    from linux_state.storage import (
        data_dir as _data_dir,
        load_metadata,
        manifest_file as _manifest_file,
    )

    manifest_path = _manifest_file(storage_root, snapshot_id)
    if not manifest_path.is_file():
        raise SnapshotError("verify", manifest_path, "manifest not found")

    try:
        metadata = load_metadata(storage_root, snapshot_id)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise SnapshotError("verify", manifest_path, str(exc)) from exc
    algorithm = codec.normalize(metadata.get("compression"))

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stored = _data_dir(storage_root, snapshot_id)

    checked = 0
    mismatches: list[str] = []
    for record in manifest["files"]:
        if record["type"] != Kind.FILE.value or "sha256" not in record:
            continue
        relative = Path(record["path"]).relative_to(Path(manifest["root"]))
        path = stored / codec.stored_name(relative.as_posix(), algorithm)
        if not path.exists():
            mismatches.append(f"{record['path']}: missing stored data")
            continue
        try:
            digest = codec.hash_content(path, algorithm)
        except CompressionError as exc:
            mismatches.append(f"{record['path']}: {exc}")
            continue
        if digest != record["sha256"]:
            mismatches.append(record["path"])
        checked += 1

    return {"checked": checked, "mismatches": mismatches}
