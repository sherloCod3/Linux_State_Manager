"""CLI tests for snapshot and list commands."""

from __future__ import annotations

import pytest

from linux_state.cli import main
from linux_state.storage import data_dir, list_snapshots


class TestSnapshotCommand:
    def test_creates_snapshot(self, capsys, rich_tree, tmp_path):
        storage = tmp_path / "store"
        rc = main(["snapshot", "--root", str(rich_tree), "--storage", str(storage)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Snapshot created:" in out
        assert len(list_snapshots(storage)) == 1

    def test_missing_root_fails(self, capsys, tmp_path):
        rc = main([
            "snapshot", "--root", str(tmp_path / "nope"),
            "--storage", str(tmp_path / "s"),
        ])
        assert rc == 1

    def test_failure_reports_error_explicitly(self, capsys, rich_tree, tmp_path):
        storage = tmp_path / "store"
        locked = rich_tree / ".config" / "nvim"
        locked.chmod(0o000)
        try:
            rc = main(["snapshot", "--root", str(rich_tree), "--storage", str(storage)])
        finally:
            locked.chmod(0o755)
        assert rc == 2
        err = capsys.readouterr().err
        assert "ERROR" in err
        assert "Operation:" in err
        assert "Reason:" in err
        assert "Action:" in err


class TestListCommand:
    def test_empty(self, capsys, tmp_path):
        rc = main(["list", "--storage", str(tmp_path / "empty")])
        assert rc == 0
        assert "No snapshots found." in capsys.readouterr().out

    def test_lists_snapshot_ids(self, capsys, rich_tree, tmp_path):
        storage = tmp_path / "store"
        main(["snapshot", "--root", str(rich_tree), "--storage", str(storage)])
        rc = main(["list", "--storage", str(storage), "-v"])
        assert rc == 0
        out = capsys.readouterr().out
        sid = list_snapshots(storage)[0]
        assert sid in out
        assert "manifest=yes" in out
