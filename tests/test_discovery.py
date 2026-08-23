"""Discovery safety and correctness tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from linux_state.discovery import DiscoveryError, Kind, discover

from conftest import snapshot_tree_state


def by_name(entries, name):
    return {e.path.name: e for e in entries}.get(name)


class TestDiscovery:
    def test_finds_regular_files(self, rich_tree):
        entries = list(discover(rich_tree))
        names = {e.path.name for e in entries}
        assert {".bashrc", "init.lua", ".gitconfig", "notes.txt"} <= names

    def test_kinds_are_correct(self, rich_tree):
        entries = list(discover(rich_tree))
        kinds = {e.path.name: e.kind for e in entries}
        assert kinds["init.lua"] == Kind.FILE
        assert kinds[".config"] == Kind.DIRECTORY
        assert kinds["link-to-file"] == Kind.SYMLINK
        assert kinds["broken-link"] == Kind.SYMLINK
        assert kinds["dir-link"] == Kind.SYMLINK

    def test_symlink_to_directory_is_not_traversed(self, rich_tree):
        entries = list(discover(rich_tree))
        linked = by_name(entries, "dir-link")
        assert linked.kind == Kind.SYMLINK
        # Nothing under Documents may appear twice via the symlink.
        doc_paths = [
            e.path.relative_to(rich_tree).as_posix() for e in entries
        ]
        assert doc_paths.count("Documents/notes.txt") == 1
        assert not any(p.startswith("dir-link/") for p in doc_paths)

    def test_broken_symlink_recorded_not_raised(self, rich_tree):
        entries = list(discover(rich_tree))
        broken = by_name(entries, "broken-link")
        assert broken is not None
        assert broken.broken_symlink is True
        assert broken.symlink_target.endswith("does-not-exist")

    def test_symlink_target_recorded(self, rich_tree):
        entry = by_name(list(discover(rich_tree)), "link-to-file")
        assert entry.symlink_target == str(rich_tree / ".gitconfig")

    def test_permissions_captured(self, rich_tree):
        entry = by_name(list(discover(rich_tree)), ".bashrc")
        assert entry.mode == "0600"

    def test_hash_matches_content(self, rich_tree):
        import hashlib

        entry = by_name(list(discover(rich_tree)), ".bashrc")
        expected = hashlib.sha256(b"export EDITOR=nvim\n").hexdigest()
        assert entry.sha256 == expected

    def test_no_hash_option(self, rich_tree):
        entries = list(discover(rich_tree, hash_files=False))
        files = [e for e in entries if e.kind == Kind.FILE]
        assert files
        assert all(e.sha256 is None for e in files)

    def test_deterministic_order(self, rich_tree):
        first = list(discover(rich_tree))
        second = list(discover(rich_tree))
        assert [e.path for e in first] == [e.path for e in second]

    def test_scan_is_read_only(self, rich_tree):
        before = snapshot_tree_state(rich_tree)
        list(discover(rich_tree))
        after = snapshot_tree_state(rich_tree)
        assert before == after

    def test_empty_directory_yields_nothing(self, fake_home):
        assert list(discover(fake_home)) == []

    def test_unreadable_directory_is_explicit_error(self, fake_home):
        secret_dir = fake_home / "secret"
        secret_dir.mkdir()
        (fake_home / "ok.txt").write_text("x")
        secret_dir.chmod(0o000)
        try:
            with pytest.raises(DiscoveryError) as excinfo:
                list(discover(fake_home))
            assert excinfo.value.operation == "scandir"
            assert excinfo.value.path == secret_dir.resolve()
        finally:
            secret_dir.chmod(0o755)

    def test_hidden_files_detected(self, rich_tree):
        names = {e.path.name for e in discover(rich_tree)}
        assert ".bashrc" in names
        assert ".config" in names
