"""Manifest determinism and correctness tests."""

from __future__ import annotations

import json
from pathlib import Path

from linux_state.discovery import Kind, discover
from linux_state.manifest import (
    build_manifest,
    entry_to_display,
    serialize_manifest,
    write_manifest,
)


class TestManifest:
    def test_structure(self, rich_tree):
        entries = list(discover(rich_tree))
        manifest = build_manifest(rich_tree, entries, snapshot_metadata={"id": "s1"})
        assert manifest["version"] == 1
        assert manifest["root"] == str(rich_tree.resolve())
        assert manifest["snapshot"] == {"id": "s1"}
        paths = {f["path"] for f in manifest["files"]}
        assert (rich_tree / ".bashrc").as_posix() in paths

    def test_deterministic_serialization(self, rich_tree):
        a = serialize_manifest(build_manifest(rich_tree, discover(rich_tree)))
        b = serialize_manifest(build_manifest(rich_tree, discover(rich_tree)))
        assert a == b
        # Byte-identical across runs.
        assert a.encode() == b.encode()

    def test_files_sorted_by_relative_path(self, rich_tree):
        manifest = build_manifest(rich_tree, list(discover(rich_tree)))
        root = rich_tree.resolve()
        rel = [Path(f["path"]).relative_to(root).as_posix() for f in manifest["files"]]
        assert rel == sorted(rel)

    def test_symlink_fields_present(self, rich_tree):
        manifest = build_manifest(rich_tree, list(discover(rich_tree)))
        link = next(
            f for f in manifest["files"]
            if f["path"].endswith("broken-link")
        )
        assert link["type"] == Kind.SYMLINK.value
        assert link["broken_symlink"] is True
        assert "sha256" not in link

    def test_file_hash_present(self, rich_tree):
        manifest = build_manifest(rich_tree, list(discover(rich_tree)))
        bashrc = next(f for f in manifest["files"] if f["path"].endswith(".bashrc"))
        assert len(bashrc["sha256"]) == 64

    def test_write_manifest_is_atomic_and_valid_json(self, rich_tree, tmp_path):
        out = tmp_path / "nested" / "manifest.json"
        write_manifest(build_manifest(rich_tree, discover(rich_tree)), out)
        loaded = json.loads(out.read_text())
        assert loaded["version"] == 1
        assert not list(tmp_path.rglob("*.tmp"))

    def test_display_abbreviates_home(self, rich_tree):
        entry = next(iter(discover(rich_tree)))
        text = entry_to_display(entry, rich_tree)
        assert text.startswith("~")
