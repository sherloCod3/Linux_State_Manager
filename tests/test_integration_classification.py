"""Integration: classification flows into manifests and CLI output."""

from __future__ import annotations

import json

from linux_state.cli import main
from linux_state.discovery import discover
from linux_state.classification import XdgDirs, default_rule_files, load_ruleset
from linux_state.manifest import build_manifest


class TestManifestClassification:
    def test_manifest_carries_classification(self, rich_tree):
        ruleset = load_ruleset(default_rule_files())
        xdg = XdgDirs(home=rich_tree)
        manifest = build_manifest(
            rich_tree, discover(rich_tree), classifier=ruleset, xdg=xdg
        )
        records = {f["path"].rsplit("/", 1)[-1]: f for f in manifest["files"]}
        bashrc = records[".bashrc"]
        assert bashrc["classification"]["category"] == "shell"
        assert bashrc["classification"]["rule_id"]

    def test_manifest_without_classifier_unchanged(self, rich_tree):
        manifest = build_manifest(rich_tree, discover(rich_tree))
        for record in manifest["files"]:
            assert "classification" not in record

    def test_deterministic_with_classifier(self, rich_tree):
        ruleset = load_ruleset(default_rule_files())
        a = build_manifest(
            rich_tree, list(discover(rich_tree)), classifier=ruleset, xdg=XdgDirs()
        )
        b = build_manifest(
            rich_tree, list(discover(rich_tree)), classifier=ruleset, xdg=XdgDirs()
        )
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


class TestCliIntegration:
    def test_scan_json_includes_classification(self, capsys, rich_tree, tmp_path):
        out_path = tmp_path / "m.json"
        rc = main(["scan", "--root", str(rich_tree), "--json", str(out_path)])
        assert rc == 0
        data = json.loads(out_path.read_text())
        by_name = {f["path"].rsplit("/", 1)[-1]: f for f in data["files"]}
        assert by_name[".bashrc"]["classification"]["category"] == "shell"
        # Cache rule must mark cache as never-restore.
        cache_dir = by_name.get(".cache")
        if cache_dir:
            assert cache_dir["classification"]["restore"] == "never"

    def test_verbose_shows_category(self, capsys, rich_tree):
        rc = main(["scan", "--root", str(rich_tree), "-v"])
        assert rc == 0
        assert "[shell/" in capsys.readouterr().out

    def test_user_rules_override_bundled(self, capsys, rich_tree, tmp_path):
        user_rules = tmp_path / "myrules"
        user_rules.mkdir()
        (user_rules / "override.yaml").write_text(
            "rules:\n"
            "  - id: user-bashrc\n    match: '.bashrc'\n"
            "    category: personal\n    portability: personal\n"
            "    restore: merge\n"
        )
        out_path = tmp_path / "m.json"
        rc = main([
            "scan", "--root", str(rich_tree),
            "--rules", str(user_rules), "--json", str(out_path),
        ])
        assert rc == 0
        data = json.loads(out_path.read_text())
        bashrc = next(f for f in data["files"] if f["path"].endswith(".bashrc"))
        assert bashrc["classification"]["category"] == "personal"

    def test_snapshot_persists_classification(self, rich_tree, tmp_path):
        storage = tmp_path / "store"
        rc = main(["snapshot", "--root", str(rich_tree), "--storage", str(storage)])
        assert rc == 0
        from linux_state.storage import list_snapshots, manifest_file

        sid = list_snapshots(storage)[0]
        data = json.loads(manifest_file(storage, sid).read_text())
        gitconfig = next(f for f in data["files"] if f["path"].endswith(".gitconfig"))
        assert gitconfig["classification"]["portability"] == "portable"
