"""Restore executor tests: transactions, backups, approval gate, failures."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from linux_state.classification import XdgDirs, default_rule_files, load_ruleset
from linux_state.discovery import discover
from linux_state.executor import NotApprovedError, execute_plan
from linux_state.manifest import build_manifest
from linux_state.planner import build_plan, CONFLICT, NEW
from linux_state.profiles import ResolvedProfile, Selector
from linux_state.rollback import perform_rollback

ALL = ResolvedProfile(name="__all__", selectors=tuple(
    Selector("category", c) for c in ("personal", "identity", "shell", "development")
))


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


def manifest_for(tree: Path, ruleset) -> dict:
    return build_manifest(
        tree, discover(tree), classifier=ruleset, xdg=None,
        snapshot_metadata={"id": "2026-01-01T00-00-00Z-bea1"},
    )


@pytest.fixture
def scenario(tmp_path):
    """Snapshot a tree, then mutate it to create NEW + CONFLICT + SAME."""
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / ".bashrc").write_text("original bashrc\n")          # -> CONFLICT
    (tree / ".gitconfig").write_text("[user]\n\tname = T\n")     # -> SAME
    sub = tree / "Documents"
    sub.mkdir()
    (sub / "notes.txt").write_text("notes v1\n")                 # -> CONFLICT
    (sub / "newfile.txt").write_text("brand new\n")              # -> NEW (deleted below)

    storage = tmp_path / "storage"
    storage.mkdir()
    ruleset = permissive_rules(tmp_path)
    manifest = build_manifest(
        tree, discover(tree), classifier=ruleset, xdg=None,
        snapshot_metadata={"id": "2026-01-01T00-00-00Z-bea1"},
    )
    # Simulate stored snapshot data dir.
    from linux_state.storage import data_dir as _dd
    data = _dd(storage, "2026-01-01T00-00-00Z-bea1")
    for entry in discover(tree):
        rel = entry.path.relative_to(tree)
        dest = data / rel
        if entry.kind.value == "directory":
            dest.mkdir(parents=True)
        elif entry.kind.value == "symlink":
            os.symlink(entry.symlink_target, dest)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(entry.path, dest)

    # Mutations after snapshot.
    (tree / ".bashrc").write_text("mutated bashrc\n")
    (sub / "notes.txt").write_text("notes v2\n")
    (sub / "newfile.txt").unlink()   # present in snapshot, missing now -> NEW
    assert not (sub / "newfile.txt").exists()

    plan = build_plan(manifest, ALL, tree)
    return {
        "root": tree,
        "storage": storage,
        "manifest": manifest,
        "data": data,
        "plan": plan,
        "tmp": tmp_path,
    }


class TestApprovalGate:
    def test_refuses_without_approval(self, scenario):
        with pytest.raises(NotApprovedError):
            execute_plan(
                scenario["plan"], scenario["root"], scenario["storage"],
                scenario["data"], scenario["manifest"], approve=False,
            )
        # Nothing changed.
        assert (scenario["root"] / ".bashrc").read_text() == "mutated bashrc\n"

    def test_no_transaction_left_behind_on_refusal(self, scenario):
        tx_dir = scenario["storage"] / "transactions"
        assert not tx_dir.exists() or list(tx_dir.iterdir()) == []


class TestExecution:
    def test_new_and_conflict_replaced(self, scenario):
        result = execute_plan(
            scenario["plan"], scenario["root"], scenario["storage"],
            scenario["data"], scenario["manifest"],
            approve=True, conflict_policy="replace",
        )
        assert result.status == "completed"
        assert (scenario["root"] / ".bashrc").read_text() == "original bashrc\n"
        assert (scenario["root"] / "Documents" / "newfile.txt").exists()

    def test_same_untouched(self, scenario):
        gitconfig = scenario["root"] / ".gitconfig"
        before_mtime = gitconfig.stat().st_mtime_ns
        execute_plan(
            scenario["plan"], scenario["root"], scenario["storage"],
            scenario["data"], scenario["manifest"],
            approve=True, conflict_policy="replace",
        )
        assert gitconfig.read_text() == "[user]\n\tname = T\n"
        assert gitconfig.stat().st_mtime_ns == before_mtime

    def test_conflict_skipped_by_default(self, scenario):
        execute_plan(
            scenario["plan"], scenario["root"], scenario["storage"],
            scenario["data"], scenario["manifest"],
            approve=True, conflict_policy="skip",
        )
        assert (scenario["root"] / ".bashrc").read_text() == "mutated bashrc\n"
        # NEW actions are not conflicts; they still apply.
        assert (scenario["root"] / "Documents" / "newfile.txt").exists()

    def test_backup_preserves_previous_state(self, scenario):
        result = execute_plan(
            scenario["plan"], scenario["root"], scenario["storage"],
            scenario["data"], scenario["manifest"],
            approve=True, conflict_policy="replace",
        )
        backups = list((result.directory / "backup").rglob("*"))
        backed_up = [p for p in backups if p.is_file()]
        contents = {p.read_text() for p in backed_up}
        assert "mutated bashrc\n" in contents
        assert "notes v2\n" in contents
        rollback_paths = [entry["path"] for entry in result.rollback]
        assert ".bashrc" in rollback_paths

    def test_transaction_record_complete(self, scenario):
        result = execute_plan(
            scenario["plan"], scenario["root"], scenario["storage"],
            scenario["data"], scenario["manifest"],
            approve=True, conflict_policy="replace",
        )
        record = json.loads((result.directory / "transaction.json").read_text())
        assert record["status"] == "completed"
        assert record["snapshot_id"] == "2026-01-01T00-00-00Z-bea1"
        assert ".bashrc" in record["executed"]
        assert record["failed"] == []
        assert record["rollback_info"]

    def test_modes_restored(self, tmp_path, scenario):
        tree = scenario["root"]
        private = tree / "secret-config"
        private.write_text("x\n")
        private.chmod(0o600)
        ruleset = permissive_rules(scenario["tmp"])
        manifest = build_manifest(
            tree, discover(tree), classifier=ruleset, xdg=None,
            snapshot_metadata={"id": "2026-01-01T00-00-00Z-bea2"},
        )
        from linux_state.storage import data_dir as _dd
        data = _dd(scenario["storage"], "2026-01-01T00-00-00Z-bea2")
        for entry in discover(tree):
            rel = entry.path.relative_to(tree)
            dest = data / rel
            if entry.kind.value == "directory":
                dest.mkdir(parents=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                import shutil
                shutil.copy2(entry.path, dest)

        private.unlink()
        plan = build_plan(manifest, ALL, tree)
        execute_plan(plan, tree, scenario["storage"], data, manifest, approve=True)
        assert (private.stat().st_mode & 0o777) == 0o600


class TestFailureHandling:
    def test_failure_stops_run_and_records_state(self, scenario, monkeypatch):
        import linux_state.compression as codec

        original_decompress = codec.decompress

        def failing_decompress(source, destination, algorithm):
            if str(source).endswith("newfile.txt"):
                raise OSError(13, "Permission denied")
            return original_decompress(source, destination, algorithm)

        monkeypatch.setattr(codec, "decompress", failing_decompress)
        result = execute_plan(
            scenario["plan"], scenario["root"], scenario["storage"],
            scenario["data"], scenario["manifest"],
            approve=True, conflict_policy="replace",
        )
        assert result.status == "failed"
        assert len(result.failed) == 1
        assert "Permission denied" in result.failed[0]["reason"]
        # Executed actions were recorded before the failure.
        assert isinstance(result.executed, list)

    def test_tampered_snapshot_data_aborts(self, scenario):
        target = scenario["data"] / ".bashrc"
        target.write_text("tampered snapshot content\n")
        result = execute_plan(
            scenario["plan"], scenario["root"], scenario["storage"],
            scenario["data"], scenario["manifest"],
            approve=True, conflict_policy="replace",
        )
        assert result.status == "failed"


class TestPathSafety:
    def test_symlink_escape_rejected(self, scenario):
        # Point Documents at an outside directory; restoring into it must fail.
        outside = scenario["tmp"] / "outside"
        outside.mkdir()
        docs = scenario["root"] / "Documents"
        import shutil as _shutil
        _shutil.rmtree(docs)
        os.symlink(outside, docs)
        result = execute_plan(
            scenario["plan"], scenario["root"], scenario["storage"],
            scenario["data"], scenario["manifest"],
            approve=True, conflict_policy="replace",
        )
        assert result.status == "failed"
        # The outside directory was never written.
        assert list(outside.iterdir()) == []


def build_tree_with_escaping_symlink(tmp_path: Path):
    """Tree containing a virtualenv-style symlink to an absolute outside
    path, snapshotted, then removed so restore must recreate it."""
    outside_file = tmp_path / "outside" / "interpreter"
    outside_file.parent.mkdir()
    outside_file.write_text("fake interpreter\n")

    tree = tmp_path / "tree"
    project = tree / "Documents" / "project"
    (project / ".venv" / "bin").mkdir(parents=True)
    link = project / ".venv" / "bin" / "python"
    os.symlink(outside_file, link)
    (project / "main.py").write_text("print('hi')\n")

    storage = tmp_path / "storage"
    storage.mkdir()
    ruleset = permissive_rules(tmp_path)
    manifest = build_manifest(
        tree, discover(tree), classifier=ruleset, xdg=None,
        snapshot_metadata={"id": "2026-01-01T00-00-00Z-0a11"},
    )
    from linux_state.storage import data_dir as _dd

    data = _dd(storage, "2026-01-01T00-00-00Z-0a11")
    for entry in discover(tree):
        rel = entry.path.relative_to(tree)
        dest = data / rel
        if entry.kind.value == "directory":
            dest.mkdir(parents=True)
        elif entry.kind.value == "symlink":
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(entry.symlink_target, dest)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry.path, dest)

    shutil.rmtree(tree / "Documents" / "project")
    plan = build_plan(manifest, ALL, tree)
    return {
        "tree": tree, "storage": storage, "manifest": manifest,
        "data": data, "plan": plan, "link": link,
        "outside_file": outside_file,
    }


class TestLeafSymlinkEscape:
    def test_restore_creates_out_of_root_symlink(self, tmp_path):
        s = build_tree_with_escaping_symlink(tmp_path)
        result = execute_plan(
            s["plan"], s["tree"], s["storage"],
            s["data"], s["manifest"], approve=True,
        )
        assert result.status == "completed"
        assert s["link"].is_symlink()
        assert os.readlink(s["link"]) == str(s["outside_file"])

    def test_rollback_removes_out_of_root_symlink(self, tmp_path):
        s = build_tree_with_escaping_symlink(tmp_path)
        result = execute_plan(
            s["plan"], s["tree"], s["storage"],
            s["data"], s["manifest"], approve=True,
        )
        assert result.status == "completed"
        _original, rb_tx = perform_rollback(s["storage"], result.id, approve=True)
        assert rb_tx.status == "completed"
        assert not os.path.lexists(s["link"])
        # The symlink target was never touched.
        assert s["outside_file"].read_text() == "fake interpreter\n"

    def test_file_restore_never_writes_through_leaf_symlink(self, tmp_path):
        canary = tmp_path / "outside" / "canary.txt"
        canary.parent.mkdir()
        canary.write_text("do not touch\n")

        tree = tmp_path / "tree"
        (tree / "Documents").mkdir(parents=True)
        config = tree / "Documents" / "app.conf"
        config.write_text("original\n")

        storage = tmp_path / "storage"
        storage.mkdir()
        ruleset = permissive_rules(tmp_path)
        manifest = build_manifest(
            tree, discover(tree), classifier=ruleset, xdg=None,
            snapshot_metadata={"id": "2026-01-01T00-00-00Z-1eaf"},
        )
        from linux_state.storage import data_dir as _dd

        data = _dd(storage, "2026-01-01T00-00-00Z-1eaf")
        for entry in discover(tree):
            rel = entry.path.relative_to(tree)
            dest = data / rel
            if entry.kind.value == "directory":
                dest.mkdir(parents=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(entry.path, dest)

        # Mutate: replace the regular file with an escaping symlink.
        config.unlink()
        os.symlink(canary, config)

        plan = build_plan(manifest, ALL, tree)
        result = execute_plan(
            plan, tree, storage, data, manifest,
            approve=True, conflict_policy="replace",
        )
        assert result.status == "completed"
        # Restored as a regular file, not through the symlink.
        assert not config.is_symlink()
        assert config.read_text() == "original\n"
        assert canary.read_text() == "do not touch\n"

    def test_rollback_restores_leaf_symlink_after_replace(self, tmp_path):
        canary = tmp_path / "outside" / "canary.txt"
        canary.parent.mkdir()
        canary.write_text("do not touch\n")

        tree = tmp_path / "tree"
        (tree / "Documents").mkdir(parents=True)
        config = tree / "Documents" / "app.conf"
        config.write_text("original\n")

        storage = tmp_path / "storage"
        storage.mkdir()
        ruleset = permissive_rules(tmp_path)
        manifest = build_manifest(
            tree, discover(tree), classifier=ruleset, xdg=None,
            snapshot_metadata={"id": "2026-01-01T00-00-00Z-b00c"},
        )
        from linux_state.storage import data_dir as _dd

        data = _dd(storage, "2026-01-01T00-00-00Z-b00c")
        for entry in discover(tree):
            rel = entry.path.relative_to(tree)
            dest = data / rel
            if entry.kind.value == "directory":
                dest.mkdir(parents=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(entry.path, dest)

        config.unlink()
        os.symlink(canary, config)

        plan = build_plan(manifest, ALL, tree)
        result = execute_plan(
            plan, tree, storage, data, manifest,
            approve=True, conflict_policy="replace",
        )
        assert result.status == "completed"
        _original, rb_tx = perform_rollback(storage, result.id, approve=True)
        assert rb_tx.status == "completed"
        # Pre-restore state (the escaping symlink) is back.
        assert config.is_symlink()
        assert os.readlink(config) == str(canary)
        assert canary.read_text() == "do not touch\n"
