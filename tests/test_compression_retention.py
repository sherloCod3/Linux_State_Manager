"""Compression and retention tests (MVP-09)."""

from __future__ import annotations

import gzip
import json
import os
from pathlib import Path

import pytest

from linux_state import compression as codec
from linux_state.classification import load_ruleset
from linux_state.cli import main as cli_main
from linux_state.compression import CompressionError
from linux_state.discovery import discover
from linux_state.executor import execute_plan
from linux_state.manifest import build_manifest
from linux_state.planner import build_plan
from linux_state.profiles import ResolvedProfile, Selector
from linux_state.snapshot import create_snapshot, verify_snapshot
from linux_state.storage import (
    data_dir,
    list_snapshots,
    metadata_file,
    prune_snapshots,
)

ALL = ResolvedProfile(name="__all__", selectors=tuple(
    Selector("category", c) for c in ("personal", "identity", "shell", "development")
))


@pytest.fixture
def storage(tmp_path):
    directory = tmp_path / "storage"
    directory.mkdir()
    return directory


def permissive_rules(tmp_path: Path):
    directory = tmp_path / "rules-permissive"
    directory.mkdir(exist_ok=True)
    (directory / "all.yaml").write_text(
        "rules:\n"
        "  - id: everything\n    match: '**'\n"
        "    category: shell\n    portability: portable\n"
        "    restore: backup-and-replace\n"
    )
    return load_ruleset([directory / "all.yaml"])


class TestCodec:
    def test_gzip_roundtrip(self, tmp_path):
        src = tmp_path / "a.txt"
        src.write_text("hello compressed world\n" * 100)
        dst = tmp_path / "a.txt.gz"
        out = tmp_path / "a.out"
        codec.compress(src, dst, "gzip")
        assert dst.read_bytes()[:2] == b"\x1f\x8b"  # gzip magic
        codec.decompress(dst, out, "gzip")
        assert out.read_text() == src.read_text()

    def test_none_reads_plain_only(self, tmp_path):
        src = tmp_path / "plain.txt"
        src.write_text("legacy\n")
        assert codec.hash_content(src, "none") == (
            __import__("hashlib").sha256(b"legacy\n").hexdigest()
        )

    def test_unknown_algorithm_rejected(self, tmp_path):
        with pytest.raises(CompressionError):
            codec.require_available("brotli")

    @pytest.mark.parametrize("algorithm", ["none", "brotli"])
    def test_creatable_algorithms_enforced(self, algorithm):
        assert algorithm not in codec.CREATABLE

    def test_stored_name_suffixes(self):
        assert codec.stored_name("x/y.conf", "gzip") == "x/y.conf.gz"
        assert codec.stored_name("x/y.conf", "zstd") == "x/y.conf.zst"
        assert codec.stored_name("x/y.conf", "none") == "x/y.conf"


class TestZstdGating:
    def test_unavailable_zstd_is_explicit_error(self, rich_tree, storage, monkeypatch):
        monkeypatch.setattr(codec, "is_available", lambda a: a != "zstd")
        with pytest.raises(Exception) as excinfo:
            create_snapshot(rich_tree, storage, compression="zstd")
        assert "Python 3.14" in str(excinfo.value)
        # No partial snapshot left behind.
        assert list_snapshots(storage) == []

    def test_available_zstd_creates_and_verifies(self, rich_tree, storage):
        if not codec.is_available("zstd"):
            pytest.skip("zstd module not available on this Python")
        sid = create_snapshot(rich_tree, storage, compression="zstd")
        meta = json.loads(metadata_file(storage, sid).read_text())
        assert meta["compression"] == "zstd"
        result = verify_snapshot(storage, sid)
        assert result["result"] if "result" in result else True
        assert result["mismatches"] == []


class TestCompressedRoundtrip:
    @pytest.fixture
    def restored(self, tmp_path):
        """Snapshot with default gzip, mutate tree, restore back."""
        from conftest import make_file

        tree = tmp_path / "tree"
        make_file(tree / ".bashrc", "bash content\n" * 50, 0o600)
        make_file(tree / ".gitconfig", "[user]\n\tname = T\n")
        (tree / "Documents").mkdir(parents=True)
        (tree / "Documents" / "notes.txt").write_text("notes\n")

        storage = tmp_path / "storage"
        sid = create_snapshot(tree, storage)

        # Manifest reflects the pre-mutation state.
        ruleset = permissive_rules(tmp_path)
        manifest = build_manifest(
            tree, discover(tree), classifier=ruleset, xdg=None,
            snapshot_metadata={"id": sid},
        )

        # Mutate after manifest capture.
        (tree / ".bashrc").write_text("mutated\n")
        (tree / ".gitconfig").unlink()

        plan = build_plan(manifest, ALL, tree)
        tx = execute_plan(
            plan, tree, storage, data_dir(storage, sid), manifest,
            approve=True, conflict_policy="replace",
        )
        return tree, storage, sid, tx

    def test_content_restored_from_compressed_data(self, restored):
        tree, _storage, _sid, tx = restored
        assert tx.status == "completed"
        assert (tree / ".bashrc").read_text() == "bash content\n" * 50
        assert (tree / ".gitconfig").read_text() == "[user]\n\tname = T\n"

    def test_mode_applied_after_decompression(self, restored):
        tree, *_rest = restored
        assert (tree / ".bashrc").stat().st_mode & 0o777 == 0o600

    def test_verify_passes_on_compressed_snapshot(self, restored):
        tree, storage, sid, _tx = restored
        result = verify_snapshot(storage, sid)
        assert result["mismatches"] == []
        assert result["checked"] > 0


class TestLegacySnapshots:
    def test_pre_compression_snapshot_remains_restorable(self, tmp_path):
        """Hand-built plain layout (no metadata field) still works."""
        from conftest import make_file

        tree = tmp_path / "tree"
        make_file(tree / ".bashrc", "legacy bash\n")
        storage = tmp_path / "storage"

        # Build a legacy-style snapshot manually: plain data files.
        sid = "2026-01-01T00-00-00Z-bea5"
        data = data_dir(storage, sid)
        data.mkdir(parents=True)
        (data / ".bashrc").write_text("legacy bash\n")
        ruleset = permissive_rules(tmp_path)
        manifest = build_manifest(
            tree, discover(tree), classifier=ruleset, xdg=None,
            snapshot_metadata={"id": sid},
        )
        # No metadata.json: executor must fall back to the 'none' reader.

        (tree / ".bashrc").write_text("changed\n")
        plan = build_plan(manifest, ALL, tree)
        tx = execute_plan(
            plan, tree, storage, data, manifest,
            approve=True, conflict_policy="replace",
        )
        assert tx.status == "completed"
        assert (tree / ".bashrc").read_text() == "legacy bash\n"


def four_snapshots(tmp_path: Path):
    storage = tmp_path / "storage"
    tree = tmp_path / "tiny-tree"
    tree.mkdir()
    ids = []
    for i in range(4):
        marker = tree / f"marker-{i}.txt"
        marker.unlink(missing_ok=True)
        marker.write_text(f"gen {i}\n")
        ids.append(create_snapshot(tree, storage))
    return storage, tree, ids


class TestRetention:
    def test_keep_prunes_oldest_keeps_newest(self, tmp_path):
        storage, _tree, ids = four_snapshots(tmp_path)
        pruned = prune_snapshots(storage, keep=2)
        remaining = list_snapshots(storage)
        assert set(pruned) == set(ids) - set(remaining)
        assert len(pruned) == 2
        assert len(remaining) == 2

    def test_no_pruning_without_excess(self, tmp_path):
        storage, _tree, _ids = four_snapshots(tmp_path)
        assert prune_snapshots(storage, keep=10) == []

    def test_keep_zero_prunes_everything(self, tmp_path):
        storage, _tree, ids = four_snapshots(tmp_path)
        pruned = prune_snapshots(storage, keep=0)
        assert sorted(pruned) == sorted(ids)
        assert list_snapshots(storage) == []

    def test_negative_keep_rejected(self, tmp_path):
        storage, _tree, _ids = four_snapshots(tmp_path)
        with pytest.raises(ValueError):
            prune_snapshots(storage, keep=-1)

    def test_transactions_never_touched(self, tmp_path):
        storage, _tree, _ids = four_snapshots(tmp_path)
        tx_root = storage / "transactions"
        tx_root.mkdir()
        (tx_root / "2026-08-23T00-00-00Z-beef").mkdir()
        prune_snapshots(storage, keep=1)
        assert (tx_root / "2026-08-23T00-00-00Z-beef").exists()


class TestCliFlags:
    def test_snapshot_with_compression_flag(self, capsys, rich_tree, tmp_path):
        storage = tmp_path / "store"
        rc = cli_main([
            "snapshot", "--root", str(rich_tree),
            "--storage", str(storage), "--compression", "gzip",
        ])
        assert rc == 0
        sid = list_snapshots(storage)[0]
        meta = json.loads(metadata_file(storage, sid).read_text())
        assert meta["compression"] == "gzip"

    def test_snapshot_reports_pruning(self, capsys, tmp_path):
        tree = tmp_path / "t"
        tree.mkdir()
        (tree / "f.txt").write_text("x\n")
        storage = tmp_path / "store"
        for _ in range(3):
            cli_main(["snapshot", "--root", str(tree), "--storage", str(storage)])
        rc = cli_main([
            "snapshot", "--root", str(tree),
            "--storage", str(storage), "--keep", "2",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Pruned:" in out
        assert len(list_snapshots(storage)) == 2

    def test_default_keeps_everything(self, tmp_path):
        storage, _tree, ids = four_snapshots(tmp_path)
        cli_main(["snapshot", "--root", str(tmp_path / "tiny-tree"), "--storage", str(storage)])
        assert len(list_snapshots(storage)) == 5
