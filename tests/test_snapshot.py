"""Snapshot and storage tests.

All snapshots are created inside tmp_path storage; the source tree is a
temporary fake home. The real user environment is never touched.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from linux_state.discovery import discover
from linux_state.snapshot import (
    SnapshotError,
    collect_metadata,
    create_snapshot,
    new_snapshot_id,
    verify_snapshot,
)
from linux_state.storage import (
    data_dir,
    default_storage_root,
    list_snapshots,
    manifest_file,
    metadata_file,
    snapshot_path,
)

from conftest import make_file, snapshot_tree_state


@pytest.fixture
def storage(tmp_path: Path) -> Path:
    root = tmp_path / "storage"
    root.mkdir()
    return root


class TestStorage:
    def test_default_root_uses_xdg(self, monkeypatch, tmp_path):
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        assert default_storage_root() == tmp_path / "data" / "linux-state"

    def test_default_root_fallback(self, monkeypatch):
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        assert default_storage_root() == Path.home() / ".local" / "share" / "linux-state"

    def test_list_empty_storage(self, storage):
        assert list_snapshots(storage) == []

    def test_list_returns_sorted_ids(self, storage):
        (snapshot_path(storage, "2026-01-01T00-00-00Z-aaaa")).mkdir(parents=True)
        (snapshot_path(storage, "2026-02-01T00-00-00Z-bbbb")).mkdir(parents=True)
        # Non-snapshot directories are ignored.
        (storage / "snapshots" / "garbage").mkdir(parents=True)
        assert list_snapshots(storage) == [
            "2026-01-01T00-00-00Z-aaaa",
            "2026-02-01T00-00-00Z-bbbb",
        ]

    def test_invalid_id_rejected(self, storage):
        with pytest.raises(ValueError):
            snapshot_path(storage, "../escape")
        with pytest.raises(ValueError):
            snapshot_path(storage, "not-an-id")


class TestSnapshotId:
    def test_format_is_filesystem_safe(self):
        sid = new_snapshot_id()
        assert "/" not in sid and ":" not in sid
        assert len(sid) == 25  # 20 timestamp chars + dash + 4 hex

    def test_ids_are_unique(self):
        assert new_snapshot_id() != new_snapshot_id()


class TestMetadata:
    def test_required_fields(self, rich_tree):
        metadata = collect_metadata(rich_tree)
        for field in (
            "version", "created", "root", "hostname", "distribution",
            "kernel", "architecture", "user", "tool_version",
        ):
            assert field in metadata
        assert metadata["root"] == str(rich_tree.resolve())

    def test_no_sensitive_content_leak(self, rich_tree):
        """Metadata must not include file contents or secret material."""
        metadata = json.dumps(collect_metadata(rich_tree))
        assert "EDITOR=nvim" not in metadata
        assert "[user]" not in metadata


class TestCreateSnapshot:
    def test_layout_created(self, rich_tree, storage):
        sid = create_snapshot(rich_tree, storage)
        assert manifest_file(storage, sid).is_file()
        assert metadata_file(storage, sid).is_file()
        assert data_dir(storage, sid).is_dir()

    def test_data_matches_source(self, rich_tree, storage):
        import gzip

        sid = create_snapshot(rich_tree, storage)
        stored = data_dir(storage, sid)
        assert gzip.open(stored / ".bashrc.gz", "rt").read() == "export EDITOR=nvim\n"
        assert gzip.open(stored / ".config/nvim/init.lua.gz", "rt").read() == (
            "vim.cmd('hi')\n"
        )

    def test_compression_recorded_in_metadata(self, rich_tree, storage):
        sid = create_snapshot(rich_tree, storage)
        meta = json.loads(metadata_file(storage, sid).read_text())
        assert meta["compression"] == "gzip"

    def test_zstd_snapshot_when_available(self, rich_tree, storage):
        from linux_state import compression as codec
        import json as _json

        if not codec.is_available("zstd"):
            pytest.skip("zstd module not available on this Python")
        sid = create_snapshot(rich_tree, storage, compression="zstd")
        meta = _json.loads(metadata_file(storage, sid).read_text())
        assert meta["compression"] == "zstd"
        assert (data_dir(storage, sid) / ".bashrc.zst").is_file()
        result = verify_snapshot(storage, sid)
        assert result["mismatches"] == []

    def test_modes_recorded_and_restorable(self, rich_tree, storage):
        """Modes live in the manifest now; restore applies them (see executor tests)."""
        sid = create_snapshot(rich_tree, storage)
        manifest = json.loads(manifest_file(storage, sid).read_text())
        bashrc = next(f for f in manifest["files"] if f["path"].endswith(".bashrc"))
        assert bashrc["mode"] == "0600"

    def test_symlinks_preserved_as_symlinks(self, rich_tree, storage):
        sid = create_snapshot(rich_tree, storage)
        stored = data_dir(storage, sid)
        link = stored / "link-to-file"
        assert link.is_symlink()
        broken = stored / "broken-link"
        assert broken.is_symlink()
        assert not os.path.exists(broken)

    def test_manifest_lists_all_entries(self, rich_tree, storage):
        sid = create_snapshot(rich_tree, storage)
        manifest = json.loads(manifest_file(storage, sid).read_text())
        source_names = {e.path.name for e in discover(rich_tree)}
        stored_names = {Path(f["path"]).name for f in manifest["files"]}
        assert source_names == stored_names

    def test_source_tree_unmodified(self, rich_tree, storage):
        before = snapshot_tree_state(rich_tree)
        create_snapshot(rich_tree, storage)
        assert snapshot_tree_state(rich_tree) == before

    def test_atomic_no_partial_snapshot_on_failure(self, rich_tree, storage):
        locked = rich_tree / ".config" / "nvim"
        locked.chmod(0o000)
        try:
            with pytest.raises(SnapshotError):
                create_snapshot(rich_tree, storage)
        finally:
            locked.chmod(0o755)
        assert list_snapshots(storage) == []
        # Nothing at all may be created when discovery fails.
        assert not (storage / "snapshots").exists()

    def test_missing_root_rejected(self, storage, tmp_path):
        with pytest.raises(SnapshotError):
            create_snapshot(tmp_path / "nope", storage)

    def test_verify_detects_tampering(self, rich_tree, storage):
        sid = create_snapshot(rich_tree, storage)
        result = verify_snapshot(storage, sid)
        assert result["mismatches"] == []
        target = data_dir(storage, sid) / ".bashrc.gz"
        target.write_bytes(b"corrupted gzip payload")
        result = verify_snapshot(storage, sid)
        assert len(result["mismatches"]) == 1
        assert result["mismatches"][0].startswith(str(rich_tree.resolve() / ".bashrc"))

    def test_verify_missing_manifest_fails(self, storage):
        sid = new_snapshot_id()
        with pytest.raises(SnapshotError):
            verify_snapshot(storage, sid)


class TestVanishedDuringCapture:
    """Files deleted by the running system between discovery and capture."""

    @staticmethod
    def _delete_on_compress(victim: Path, monkeypatch):
        """Make codec.compress delete one specific source before reading it."""
        from linux_state import compression as codec

        original = codec.compress
        target = victim.resolve()

        def vanishing(source, destination, algorithm):
            if source.resolve() == target:
                source.unlink()
            return original(source, destination, algorithm)

        monkeypatch.setattr(codec, "compress", vanishing)

    def test_snapshot_succeeds_and_reports_skip(self, rich_tree, storage, monkeypatch):
        victim = rich_tree / "Documents" / "notes.txt"
        self._delete_on_compress(victim, monkeypatch)
        skipped: list[Path] = []
        sid = create_snapshot(rich_tree, storage, skipped=skipped)
        assert skipped == [victim.resolve()]
        # Snapshot is published despite the vanished file.
        assert list_snapshots(storage) == [sid]

    def test_manifest_excludes_vanished_file(self, rich_tree, storage, monkeypatch):
        victim = rich_tree / "Documents" / "notes.txt"
        self._delete_on_compress(victim, monkeypatch)
        sid = create_snapshot(rich_tree, storage)
        manifest = json.loads(manifest_file(storage, sid).read_text())
        paths = [record["path"] for record in manifest["files"]]
        assert str(victim.resolve()) not in paths
        assert str((rich_tree / ".bashrc").resolve()) in paths

    def test_unreadable_file_still_fails_atomically(self, rich_tree, storage, monkeypatch):
        """Only ENOENT is tolerated; permission errors keep aborting."""
        from linux_state import compression as codec

        original = codec.compress

        def refusing(source, destination, algorithm):
            if source.name == "init.lua":
                raise PermissionError(13, "Permission denied")
            return original(source, destination, algorithm)

        monkeypatch.setattr(codec, "compress", refusing)
        with pytest.raises(SnapshotError) as excinfo:
            create_snapshot(rich_tree, storage)
        assert excinfo.value.operation == "copy"
        assert list_snapshots(storage) == []


class TestMultipleSnapshots:
    def test_two_snapshots_coexist(self, rich_tree, storage):
        first = create_snapshot(rich_tree, storage)
        make_file(rich_tree / "newfile.txt", "new\n")
        second = create_snapshot(rich_tree, storage)
        assert first != second
        assert list_snapshots(storage) == sorted([first, second])
        assert not (data_dir(storage, first) / "newfile.txt.gz").exists()
        assert (data_dir(storage, second) / "newfile.txt.gz").is_file()
