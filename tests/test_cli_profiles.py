"""CLI integration for profile-filtered scans."""

from __future__ import annotations

import pytest

from linux_state.cli import main


@pytest.fixture
def profiles_dir(tmp_path):
    directory = tmp_path / "profiles"
    directory.mkdir()
    (directory / "hyprstation.yaml").write_text(
        "profile: hyprstation\nextends: [shell, desktop:hyprland]\n"
    )
    return directory


class TestScanProfileFilter:
    def test_profile_summary_line(self, capsys, rich_tree, profiles_dir):
        rc = main([
            "scan", "--root", str(rich_tree),
            "--profiles-dir", str(profiles_dir),
            "--profile", "hyprstation",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Profile: hyprstation" in out

    def test_verbose_shows_only_selected(self, capsys, rich_tree, profiles_dir):
        rc = main([
            "scan", "--root", str(rich_tree), "-v",
            "--profiles-dir", str(profiles_dir),
            "--profile", "hyprstation",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert ".bashrc" in out          # shell category selected
        assert "notes.txt" not in out    # personal, not in profile

    def test_undefined_category_profile(self, capsys, rich_tree):
        rc = main(["scan", "--root", str(rich_tree), "-v", "--profile", "identity"])
        assert rc == 0
        assert ".gitconfig" in capsys.readouterr().out

    def test_conflicting_desktops_fail(self, capsys, rich_tree, tmp_path):
        profiles = tmp_path / "p"
        profiles.mkdir()
        (profiles / "both.yaml").write_text(
            "profile: both\nextends: [desktop:kde, desktop:gnome]\n"
        )
        rc = main([
            "scan", "--root", str(rich_tree),
            "--profiles-dir", str(profiles),
            "--profile", "both",
        ])
        assert rc == 2
        err = capsys.readouterr().err
        assert "multiple desktop" in err

    def test_missing_profiles_dir_fails(self, capsys, rich_tree, tmp_path):
        rc = main([
            "scan", "--root", str(rich_tree),
            "--profiles-dir", str(tmp_path / "nope"),
            "--profile", "x",
        ])
        assert rc == 2
