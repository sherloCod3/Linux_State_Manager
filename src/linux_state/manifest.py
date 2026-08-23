"""Deterministic manifest generation.

A manifest is a complete, stable description of discovered state.
Serialization is deterministic: entries sorted by path, sorted JSON keys,
stable floats (mtime rounded) so identical trees produce byte-identical files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

from linux_state.classification import XdgDirs
from linux_state.discovery import Entry, Kind

if TYPE_CHECKING:
    from linux_state.classification import RuleSet

MANIFEST_VERSION = 1


def build_manifest(
    root: Path,
    entries: Iterable[Entry],
    *,
    snapshot_metadata: dict | None = None,
    include_hashes: bool = True,
    classifier: "RuleSet | None" = None,
    xdg: "XdgDirs | None" = None,
) -> dict:
    """Build a manifest dict from discovery entries.

    When a classifier is provided, each record carries its classification
    and the reason (matched rule) for explainability.
    """
    root = root.resolve()
    files = []
    for entry in sorted(entries, key=lambda e: e.relative_to(root)):
        record = {
            "path": entry.path.as_posix(),
            "type": entry.kind.value,
            "mode": entry.mode,
            "size": entry.size if entry.kind == Kind.FILE else 0,
            "uid": entry.uid,
            "gid": entry.gid,
        }
        if include_hashes and entry.sha256:
            record["sha256"] = entry.sha256
        if entry.kind == Kind.SYMLINK:
            record["symlink_target"] = entry.symlink_target
            record["broken_symlink"] = entry.broken_symlink
        if classifier is not None:
            relative = entry.relative_to(root)
            result = classifier.classify(relative, xdg or XdgDirs(), root)
            classification = {
                "category": result.category,
                "portability": result.portability,
                "restore": result.restore_default,
                "rule_id": result.rule_id,
                "rule_source": result.rule_source,
            }
            if result.environment:
                classification["environment"] = result.environment
            if result.application:
                classification["application"] = result.application
            record["classification"] = classification
        files.append(record)

    manifest = {
        "version": MANIFEST_VERSION,
        "root": root.as_posix(),
        "snapshot": snapshot_metadata or {},
        "files": files,
    }
    return manifest


def serialize_manifest(manifest: dict) -> str:
    """Deterministic JSON serialization."""
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def write_manifest(manifest: dict, output: Path) -> None:
    """Write the manifest to *output* (the only write this module performs)."""
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    tmp.write_text(serialize_manifest(manifest), encoding="utf-8")
    tmp.replace(output)


def entry_to_display(entry: Entry, home: Path) -> str:
    """Human-facing path with ~ abbreviation when under *home*."""
    try:
        return f"~/{entry.path.relative_to(home).as_posix()}"
    except ValueError:
        return str(entry.path)
