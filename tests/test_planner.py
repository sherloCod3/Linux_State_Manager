"""Restore planner tests: conflict states, isolation, purity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from linux_state.classification import XdgDirs, default_rule_files, load_ruleset
from linux_state.cli import main as cli_main
from linux_state.discovery import discover
from linux_state.manifest import build_manifest
from linux_state.planner import (
    CONFLICT,
    MODIFIED,
    NEW,
    RestorePlan,
    SAME,
    SKIPPED,
    build_plan,
)
from linux_state.profiles import ProfileResolver, ResolvedProfile, Selector, load_profiles

ALL = ResolvedProfile(name="__all__", selectors=tuple(
    Selector("category", c) for c in
    ("personal", "identity", "shell", "development", "application", "desktop")
))


def manifest_for(tree: Path, ruleset=None, xdg=None) -> dict:
    return build_manifest(
        tree,
        discover(tree),
        classifier=ruleset,
        xdg=xdg,
        snapshot_metadata={"id": "test-snapshot"},
    )


def actions_by_path(plan: RestorePlan) -> dict:
    return {a.path: a for a in plan.actions}


@pytest.fixture
def ruleset():
    return load_ruleset(default_rule_files())


def permissive_rules(tmp_path: Path):
    """Rules classifying everything as restorable, for synthetic trees."""
    directory = tmp_path / "rules-permissive"
    directory.mkdir()
    (directory / "all.yaml").write_text(
        "rules:\n"
        "  - id: everything\n"
        "    match: '**'\n"
        "    category: shell\n"
        "    portability: portable\n"
        "    restore: backup-and-replace\n"
    )
    return load_ruleset([directory / "all.yaml"])


class TestConflictStates:
    def test_deleted_file_is_new(self, tmp_path):
        tree = tmp_path / "tree"
        tree.mkdir()
        (tree / "gone.txt").write_text("data\n")
        manifest = manifest_for(tree, permissive_rules(tmp_path), None)
        (tree / "gone.txt").unlink()
        plan = build_plan(manifest, ALL, tree)
        assert actions_by_path(plan)["gone.txt"].action == NEW

    def test_identical_file_is_same(self, tmp_path):
        tree = tmp_path / "tree"
        tree.mkdir()
        (tree / ".bashrc").write_text("hi\n")
        manifest = manifest_for(tree, permissive_rules(tmp_path), None)
        plan = build_plan(manifest, ALL, tree)
        assert actions_by_path(plan)[".bashrc"].action == SAME

    def test_modified_content_is_conflict(self, tmp_path):
        tree = tmp_path / "tree"
        tree.mkdir()
        (tree / ".bashrc").write_text("original\n")
        manifest = manifest_for(tree, permissive_rules(tmp_path), None)
        (tree / ".bashrc").write_text("modified\n")
        plan = build_plan(manifest, ALL, tree)
        assert actions_by_path(plan)[".bashrc"].action == CONFLICT

    def test_mode_only_change_is_modified(self, tmp_path):
        tree = tmp_path / "tree"
        tree.mkdir()
        target = tree / ".bashrc"
        target.write_text("hi\n")
        target.chmod(0o600)
        manifest = manifest_for(tree, permissive_rules(tmp_path), None)
        target.chmod(0o644)
        plan = build_plan(manifest, ALL, tree)
        assert actions_by_path(plan)[".bashrc"].action == MODIFIED

    def test_symlink_target_change_is_conflict(self, tmp_path):
        import os

        tree = tmp_path / "tree"
        tree.mkdir()
        (tree / "real.txt").write_text("data\n")
        os.symlink("real.txt", tree / "the-link")
        manifest = manifest_for(tree, permissive_rules(tmp_path), None)
        (tree / "the-link").unlink()
        os.symlink("other.txt", tree / "the-link")
        plan = build_plan(manifest, ALL, tree)
        entry = actions_by_path(plan)["the-link"]
        assert entry.action == CONFLICT

    def test_type_change_is_conflict(self, tmp_path):
        tree = tmp_path / "tree"
        tree.mkdir()
        (tree / "item").write_text("file-content\n")
        manifest = manifest_for(tree, permissive_rules(tmp_path), None)
        (tree / "item").unlink()
        (tree / "item").mkdir()
        plan = build_plan(manifest, ALL, tree)
        assert actions_by_path(plan)["item"].action == CONFLICT


class TestPoliciesAndIsolation:
    def test_cache_never_skipped(self, fake_home, ruleset):
        (fake_home / ".cache").mkdir()
        (fake_home / ".cache" / "blob").write_text("cached\n")
        manifest = manifest_for(fake_home, ruleset, XdgDirs(fake_home))
        resolved = ProfileResolver({}).resolve("cache")
        plan = build_plan(manifest, resolved, fake_home)
        entry = actions_by_path(plan)[".cache/blob"]
        assert entry.action == SKIPPED
        assert "never" in entry.reason

    def test_secrets_require_review(self, fake_home, ruleset):
        ssh_dir = fake_home / ".ssh"
        ssh_dir.mkdir()
        (ssh_dir / "id_ed25519").write_text("PRIVATE\n")
        manifest = manifest_for(fake_home, ruleset, XdgDirs(fake_home))
        resolved = ProfileResolver({}).resolve("secret")
        plan = build_plan(manifest, resolved, fake_home)
        entry = actions_by_path(plan)[".ssh/id_ed25519"]
        assert entry.action == SKIPPED
        assert "review" in entry.reason

    def test_hyprland_profile_excludes_kde(self, tmp_path, fake_home, ruleset):
        profiles = tmp_path / "profiles"
        profiles.mkdir()
        (profiles / "h.yaml").write_text(
            "profile: h\nextends: [desktop:hyprland]\n"
        )
        (fake_home / ".config/hypr").mkdir(parents=True)
        (fake_home / ".config/hypr/hyprland.conf").write_text("bind=X\n")
        (fake_home / ".config/plasma-org.kde.plasma.desktop-appletsrc").write_text(
            "[Plasma]\n"
        )
        manifest = manifest_for(fake_home, ruleset, XdgDirs(fake_home))
        resolved = ProfileResolver(load_profiles(profiles)).resolve("h")
        plan = build_plan(manifest, resolved, fake_home)
        paths = {a.path for a in plan.actions}
        assert ".config/hypr/hyprland.conf" in paths
        assert not any("plasma" in p for p in paths)


class TestPurityAndValidation:
    def test_planning_does_not_modify_tree(self, fake_home, ruleset):
        from conftest import snapshot_tree_state

        manifest = manifest_for(fake_home, ruleset, XdgDirs(fake_home))
        before = snapshot_tree_state(fake_home)
        build_plan(manifest, ALL, fake_home)
        assert snapshot_tree_state(fake_home) == before

    def test_root_mismatch_rejected(self, fake_home, tmp_path):
        manifest = manifest_for(fake_home, None, None)
        with pytest.raises(ValueError):
            build_plan(manifest, ALL, tmp_path / "elsewhere")


class TestCliPlan:
    @pytest.fixture
    def snapshotted(self, rich_tree, tmp_path):
        storage = tmp_path / "store"
        rc = cli_main([
            "snapshot", "--root", str(rich_tree), "--storage", str(storage),
        ])
        assert rc == 0
        from linux_state.storage import list_snapshots

        return storage, list_snapshots(storage)[0]

    def test_plan_dry_run_output(self, capsys, rich_tree, tmp_path, snapshotted):
        storage, sid = snapshotted
        rc = cli_main([
            "plan", sid, "--root", str(rich_tree),
            "--storage", str(storage),
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "SAME" in out
        assert "Plan summary" in out

    def test_plan_detects_modification(self, capsys, rich_tree, tmp_path, snapshotted):
        storage, sid = snapshotted
        bashrc = rich_tree / ".bashrc"
        original = bashrc.read_text()
        try:
            bashrc.write_text(original + "# changed\n")
            rc = cli_main(["plan", sid, "--root", str(rich_tree), "--storage", str(storage)])
            assert rc == 0
            assert "CONFLICT" in capsys.readouterr().out
        finally:
            bashrc.write_text(original)

    def test_plan_reports_new_files(self, capsys, rich_tree, tmp_path, snapshotted):
        storage, sid = snapshotted
        new_file = rich_tree.parent / f"{rich_tree.name}-copy"
        # Instead of copying the tree, create the file then re-plan against
        # a fresh identical root is complex; simpler: delete a file.
        missing = rich_tree / "Documents" / "notes.txt"
        missing.unlink()
        rc = cli_main(["plan", sid, "--root", str(rich_tree), "--storage", str(storage)])
        assert rc == 0
        assert "NEW" in capsys.readouterr().out

    def test_plan_never_writes_anything(self, rich_tree, tmp_path, snapshotted):
        from conftest import snapshot_tree_state

        storage, sid = snapshotted
        before_storage = snapshot_tree_state(storage)
        cli_main(["plan", sid, "--root", str(rich_tree), "--storage", str(storage)])
        assert snapshot_tree_state(storage) == before_storage

    def test_unknown_snapshot_fails_explicitly(self, capsys, rich_tree, tmp_path):
        rc = cli_main([
            "plan", "2099-01-01T00-00-00Z-dead",
            "--root", str(rich_tree),
            "--storage", str(tmp_path / "store"),
        ])
        assert rc == 1
        assert "ERROR" in capsys.readouterr().err


class TestExcludes:
    def _tree(self, tmp_path: Path) -> Path:
        tree = tmp_path / "tree"
        tree.mkdir()
        (tree / ".bashrc").write_text("hi\n")
        (tree / "Documents" / "notes.txt").parent.mkdir(parents=True)
        (tree / "Documents" / "notes.txt").write_text("data\n")
        (tree / "Documents" / "keep.txt").write_text("keep\n")
        return tree

    def test_exclude_single_file(self, tmp_path):
        tree = self._tree(tmp_path)
        manifest = manifest_for(tree, permissive_rules(tmp_path), None)
        plan = build_plan(manifest, ALL, tree, exclude=[".bashrc"])
        by_path = actions_by_path(plan)
        assert by_path[".bashrc"].action == SKIPPED
        assert by_path[".bashrc"].reason == "user exclude"
        assert by_path["Documents/notes.txt"].action == SAME

    def test_exclude_dir_glob_covers_dir_and_children(self, tmp_path):
        tree = self._tree(tmp_path)
        manifest = manifest_for(tree, permissive_rules(tmp_path), None)
        plan = build_plan(manifest, ALL, tree, exclude=["Documents/**"])
        by_path = actions_by_path(plan)
        assert by_path["Documents"].action == SKIPPED
        assert by_path["Documents/notes.txt"].action == SKIPPED
        assert by_path["Documents/keep.txt"].action == SKIPPED
        assert by_path[".bashrc"].action == SAME

    def test_exclude_fnmatch_pattern(self, tmp_path):
        tree = self._tree(tmp_path)
        manifest = manifest_for(tree, permissive_rules(tmp_path), None)
        plan = build_plan(manifest, ALL, tree, exclude=["Documents/*.txt"])
        by_path = actions_by_path(plan)
        assert by_path["Documents/notes.txt"].action == SKIPPED
        assert by_path["Documents/keep.txt"].action == SKIPPED
        # Only files match; the directory itself is kept.
        assert by_path["Documents"].action == SAME

    def test_excluded_entries_never_restored_by_executor(self, tmp_path):
        import os as _os
        import shutil as _shutil

        from linux_state.executor import execute_plan
        from linux_state.storage import data_dir

        tree = self._tree(tmp_path)
        storage = tmp_path / "storage"
        storage.mkdir()
        ruleset = permissive_rules(tmp_path)
        manifest = build_manifest(
            tree, discover(tree), classifier=ruleset, xdg=None,
            snapshot_metadata={"id": "2026-01-01T00-00-00Z-e101"},
        )
        data = data_dir(storage, "2026-01-01T00-00-00Z-e101")
        for entry in discover(tree):
            rel = entry.path.relative_to(tree)
            dest = data / rel
            if entry.kind.value == "directory":
                dest.mkdir(parents=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                _shutil.copy2(entry.path, dest)

        (tree / "Documents" / "notes.txt").unlink()
        (tree / ".bashrc").unlink()
        plan = build_plan(manifest, ALL, tree, exclude=[".bashrc"])
        result = execute_plan(plan, tree, storage, data, manifest, approve=True)
        assert result.status == "completed"
        # Excluded file stays absent; included file was restored.
        assert not (tree / ".bashrc").exists()
        assert (tree / "Documents" / "notes.txt").read_text() == "data\n"

    def test_cli_plan_passes_exclude_through(self, capsys, rich_tree, tmp_path):
        storage = tmp_path / "store"
        rc = cli_main(["snapshot", "--root", str(rich_tree), "--storage", str(storage)])
        assert rc == 0
        from linux_state.storage import list_snapshots

        sid = list_snapshots(storage)[0]
        rc = cli_main([
            "plan", sid,
            "--root", str(rich_tree),
            "--storage", str(storage),
            "--exclude", "Documents/**",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "user exclude" in out


class TestMatchingHelper:
    def test_normalize_strips_tilde_and_slashes(self):
        from linux_state.matching import normalize_exclude_patterns

        assert normalize_exclude_patterns(["~/x/**", "/y/**", "", "  "]) == [
            "x/**", "y/**",
        ]

    def test_is_excluded_double_star_semantics(self):
        from linux_state.matching import is_excluded

        pats = ["Documents/**"]
        assert is_excluded("Documents", pats)
        assert is_excluded("Documents/a/b.txt", pats)
        assert not is_excluded("Downloads/a", pats)

    def test_snapshot_and_planner_share_helper(self):
        import inspect

        from linux_state import matching, snapshot

        source = inspect.getsource(snapshot._filter_entries)
        assert "is_excluded" in source
