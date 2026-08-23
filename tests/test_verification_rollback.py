"""Verification and rollback tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from linux_state.cli import main as cli_main
from linux_state.discovery import discover
from linux_state.executor import execute_plan
from linux_state.manifest import build_manifest
from linux_state.planner import build_plan
from linux_state.profiles import ResolvedProfile, Selector
from linux_state.rollback import (
    latest_transaction,
    list_transactions,
    perform_rollback,
)
from linux_state.storage import transactions_dir
from linux_state.verification import verify_paths

from test_executor import permissive_rules

ALL = ResolvedProfile(name="__all__", selectors=tuple(
    Selector("category", c) for c in ("personal", "identity", "shell", "development")
))


def make_scenario(tmp_path: Path):
    """Snapshot tree, mutate it, return everything needed to plan/execute."""
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / ".bashrc").write_text("original\n")            # CONFLICT after mutation
    (tree / "Documents").mkdir()
    (tree / "Documents" / "notes.txt").write_text("v1\n")  # SAME
    (tree / "Documents" / "created.txt").write_text("new\n")  # NEW (deleted below)

    storage = tmp_path / "storage"
    storage.mkdir()
    ruleset = permissive_rules(tmp_path)
    manifest = build_manifest(
        tree, discover(tree), classifier=ruleset, xdg=None,
        snapshot_metadata={"id": "2026-01-01T00-00-00Z-cafe"},
    )
    from linux_state.storage import data_dir

    data = data_dir(storage, manifest["snapshot"]["id"])
    for entry in discover(tree):
        rel = entry.path.relative_to(tree)
        dest = data / rel
        if entry.kind.value == "directory":
            dest.mkdir(parents=True)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(entry.path, dest)

    (tree / ".bashrc").write_text("mutated\n")
    (tree / "Documents" / "created.txt").unlink()

    plan = build_plan(manifest, ALL, tree)
    tx = execute_plan(
        plan, tree, storage, data, manifest,
        approve=True, conflict_policy="replace",
    )
    return {
        "tree": tree, "storage": storage, "manifest": manifest,
        "plan": plan, "tx": tx,
    }


class TestExecutorRollbackInfo:
    def test_absent_marker_recorded_for_new(self, tmp_path):
        scenario = make_scenario(tmp_path)
        paths = {e["path"]: e["type"] for e in scenario["tx"].rollback}
        assert paths["Documents/created.txt"] == "absent"
        assert paths[".bashrc"] == "file"

    def test_transaction_stores_root(self, tmp_path):
        scenario = make_scenario(tmp_path)
        assert scenario["tx"].root == str((tmp_path / "tree").resolve())


class TestVerification:
    def test_passes_after_successful_restore(self, tmp_path):
        scenario = make_scenario(tmp_path)
        report = verify_paths(
            scenario["tree"], scenario["manifest"], scenario["tx"].executed
        )
        assert report["result"] == "PASS"
        assert report["checked"] == len(scenario["tx"].executed)

    def test_detects_missing_file(self, tmp_path):
        scenario = make_scenario(tmp_path)
        (scenario["tree"] / ".bashrc").unlink()
        report = verify_paths(
            scenario["tree"], scenario["manifest"], scenario["tx"].executed
        )
        assert report["result"] == "FAIL"
        assert any(f["check"] == "exists" for f in report["failures"])

    def test_report_attached_to_transaction(self, tmp_path):
        scenario = make_scenario(tmp_path)
        from linux_state.verification import attach_verification

        report = verify_paths(
            scenario["tree"], scenario["manifest"], scenario["tx"].executed
        )
        attach_verification(scenario["tx"].directory, report)
        record = json.loads(
            (scenario["tx"].directory / "transaction.json").read_text()
        )
        assert record["verification"]["result"] == "PASS"


class TestRollback:
    def test_restores_previous_state(self, tmp_path):
        scenario = make_scenario(tmp_path)
        perform_rollback(scenario["storage"], scenario["tx"].id, approve=True)

        tree = scenario["tree"]
        # Conflict file back to pre-restore content.
        assert (tree / ".bashrc").read_text() == "mutated\n"
        # Created file removed again.
        assert not (tree / "Documents" / "created.txt").exists()
        # SAME file untouched.
        assert (tree / "Documents" / "notes.txt").read_text() == "v1\n"

    def test_rollback_refused_without_approval(self, tmp_path):
        scenario = make_scenario(tmp_path)
        with pytest.raises(Exception, match="approval"):
            perform_rollback(scenario["storage"], scenario["tx"].id, approve=False)
        assert (scenario["tree"] / ".bashrc").read_text() == "original\n"

    def test_rollback_recorded_as_own_transaction(self, tmp_path):
        scenario = make_scenario(tmp_path)
        _original, rb_tx = perform_rollback(
            scenario["storage"], scenario["tx"].id, approve=True
        )
        assert rb_tx.status == "completed"
        ids = list_transactions(scenario["storage"])
        assert rb_tx.id in ids and scenario["tx"].id in ids
        assert latest_transaction(scenario["storage"]) == max(ids)

    def test_unknown_transaction_fails(self, tmp_path):
        scenario = make_scenario(tmp_path)
        with pytest.raises(Exception):
            perform_rollback(
                scenario["storage"],
                "2026-01-01T00-00-00Z-dead",
                approve=True,
            )

    def test_double_rollback_is_safe_noop_on_files(self, tmp_path):
        scenario = make_scenario(tmp_path)
        perform_rollback(scenario["storage"], scenario["tx"].id, approve=True)
        tree = scenario["tree"]
        state_after_first = (tree / ".bashrc").read_text()
        # A second rollback re-restores the same backup; content identical.
        perform_rollback(scenario["storage"], scenario["tx"].id, approve=True)
        assert (tree / ".bashrc").read_text() == state_after_first


class TestCliRollback:
    def test_restore_then_rollback_end_to_end(self, capsys, tmp_path):
        scenario = make_scenario(tmp_path)
        storage = str(scenario["storage"])
        root = str(scenario["tree"])

        # Rollback without approval must change nothing.
        rc = cli_main(["rollback", "--storage", storage])
        assert rc == 2
        assert (scenario["tree"] / ".bashrc").read_text() == "original\n"

        rc = cli_main(["rollback", "--storage", storage, "--approve"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "ROLLBACK" in out
        assert (scenario["tree"] / ".bashrc").read_text() == "mutated\n"

    def test_cli_restore_reports_verification(self, capsys, tmp_path):
        # Full CLI cycle: snapshot -> mutate -> restore -> verify.
        tree = tmp_path / "tree"
        tree.mkdir()
        (tree / ".bashrc").write_text("original\n")
        storage = tmp_path / "storage"

        assert cli_main(["snapshot", "--root", str(tree), "--storage", str(storage)]) == 0
        (tree / ".bashrc").write_text("mutated\n")

        from linux_state.storage import list_snapshots
        sid = list_snapshots(storage)[0]

        rc = cli_main([
            "restore", sid,
            "--root", str(tree), "--storage", str(storage),
            "--approve", "--conflict", "replace",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Verification: PASS" in out
        assert (tree / ".bashrc").read_text() == "original\n"
