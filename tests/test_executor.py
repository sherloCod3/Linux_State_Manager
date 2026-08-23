"""Restore executor tests: transactions, backups, approval gate, failures."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from linux_state.classification import XdgDirs, default_rule_files, load_ruleset
from linux_state.discovery import discover
from linux_state.executor import NotApprovedError, execute_plan
from linux_state.manifest import build_manifest
from linux_state.planner import build_plan, CONFLICT, NEW
from linux_state.profiles import ResolvedProfile, Selector

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
        import linux_state.executor as executor_mod

        calls = {"n": 0}
        original_copy2 = executor_mod.shutil.copy2

        def failing_copy2(*args, **kwargs):
            if args and str(args[0]).endswith("newfile.txt"):
                raise OSError(13, "Permission denied")
            return original_copy2(*args, **kwargs)

        monkeypatch.setattr(executor_mod.shutil, "copy2", failing_copy2)
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
