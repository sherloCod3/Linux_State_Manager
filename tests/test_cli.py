"""CLI smoke tests."""

from __future__ import annotations

import json

import pytest

from linux_state.cli import main


@pytest.fixture
def isolated_home(monkeypatch, fake_home):
    monkeypatch.setenv("HOME", str(fake_home))
    return fake_home


class TestScanCommand:
    def test_scan_summary(self, capsys, rich_tree):
        rc = main(["scan", "--root", str(rich_tree)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Scanned:" in out
        assert "files:" in out

    def test_scan_writes_manifest(self, capsys, rich_tree, tmp_path):
        out_path = tmp_path / "m.json"
        rc = main(["scan", "--root", str(rich_tree), "--json", str(out_path)])
        assert rc == 0
        data = json.loads(out_path.read_text())
        assert data["version"] == 1

    def test_scan_missing_root_fails(self, capsys, tmp_path):
        rc = main(["scan", "--root", str(tmp_path / "nope")])
        assert rc == 1
        assert "ERROR" in capsys.readouterr().err

    def test_scan_verbose_lists_entries(self, capsys, rich_tree):
        rc = main(["scan", "--root", str(rich_tree), "-v"])
        assert rc == 0
        assert ".bashrc" in capsys.readouterr().out

    def test_scan_does_not_modify_tree(self, rich_tree):
        from conftest import snapshot_tree_state

        before = snapshot_tree_state(rich_tree)
        main(["scan", "--root", str(rich_tree), "-v"])
        assert snapshot_tree_state(rich_tree) == before

    def test_version_flag(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 0
