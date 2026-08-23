"""Shared fixtures: fake HOME trees in tmp_path.

Tests must never touch the developer's real home directory.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest


def make_file(path: Path, content: str = "hello\n", mode: int | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    if mode is not None:
        path.chmod(mode)
    return path


@pytest.fixture
def fake_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


@pytest.fixture
def rich_tree(fake_home: Path) -> Path:
    """A tree exercising every discovery case."""
    make_file(fake_home / ".bashrc", "export EDITOR=nvim\n", 0o600)
    make_file(fake_home / ".config" / "nvim" / "init.lua", "vim.cmd('hi')\n")
    make_file(fake_home / ".gitconfig", "[user]\n\tname = T\n")
    make_file(fake_home / "Documents" / "notes.txt")

    (fake_home / ".cache").mkdir()
    (fake_home / "emptydir").mkdir()

    os.symlink(
        fake_home / ".gitconfig",
        fake_home / "link-to-file",
    )
    os.symlink(
        fake_home / "does-not-exist",
        fake_home / "broken-link",
    )
    os.symlink(fake_home / "Documents", fake_home / "dir-link")
    return fake_home


def snapshot_tree_state(root: Path) -> dict[str, tuple]:
    """Capture mtimes/modes to assert a scan did not modify anything."""
    state = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in [*dirnames, *filenames]:
            p = Path(dirpath) / name
            st = p.lstat()
            state[str(p)] = (
                st.st_mtime_ns,
                stat.S_IMODE(st.st_mode),
                st.st_ino,
            )
    return state
