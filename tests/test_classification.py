"""Classification and rules tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from linux_state.classification import (
    RuleError,
    XdgDirs,
    default_rule_files,
    load_ruleset,
)


def classify(ruleset, rel, xdg=None, root=None):
    return ruleset.classify(rel, xdg or XdgDirs(), root or Path("/scan-root"))


@pytest.fixture
def bundled():
    return load_ruleset(default_rule_files())


def write_rules(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body)
    return path


class TestRuleLoading:
    def test_bundled_rules_load(self, bundled):
        assert len(bundled) > 0

    def test_missing_rules_key_rejected(self, tmp_path):
        path = write_rules(tmp_path, "bad.yaml", "foo: bar\n")
        with pytest.raises(RuleError):
            load_ruleset([path])

    def test_invalid_category_rejected(self, tmp_path):
        path = write_rules(
            tmp_path,
            "bad.yaml",
            "rules:\n  - id: x\n    match: 'a'\n    category: bogus\n",
        )
        with pytest.raises(RuleError) as excinfo:
            load_ruleset([path])
        assert "category" in excinfo.value.reason

    def test_unreadable_yaml_rejected(self, tmp_path):
        path = write_rules(tmp_path, "bad.yaml", "rules: [unclosed\n")
        with pytest.raises(RuleError):
            load_ruleset([path])

    def test_empty_file_ok(self, tmp_path):
        path = write_rules(tmp_path, "empty.yaml", "")
        assert len(load_ruleset([path])) == 0


class TestPriority:
    def test_first_match_wins(self, tmp_path):
        first = write_rules(
            tmp_path,
            "first.yaml",
            "rules:\n"
            "  - id: winner\n    match: '~/.cache/**'\n"
            "    category: personal\n    portability: personal\n"
            "    restore: merge\n",
        )
        second = write_rules(
            tmp_path,
            "second.yaml",
            "rules:\n"
            "  - id: loser\n    match: '~/.cache/**'\n"
            "    category: cache\n    portability: cache\n    restore: never\n",
        )
        result = classify(load_ruleset([first, second]), ".cache/fonts")
        assert result.rule_id == "winner"

    def test_user_rule_beats_bundled(self, bundled, tmp_path):
        user = write_rules(
            tmp_path,
            "user.yaml",
            "rules:\n"
            "  - id: user-ssh-override\n    match: '~/.ssh/config'\n"
            "    category: shell\n    portability: portable\n"
            "    restore: backup-and-replace\n",
        )
        combined = load_ruleset([user, *default_rule_files()])
        result = classify(combined, ".ssh/config")
        assert result.rule_id == "user-ssh-override"


class TestBundledClassification:
    def test_ssh_is_secret(self, bundled):
        result = classify(bundled, ".ssh/id_ed25519")
        assert result.category == "secret"
        assert result.portability == "secret"

    def test_cache_never_restored(self, bundled):
        result = classify(bundled, ".cache/mozilla/firefox")
        assert result.category == "cache"
        assert result.restore_default == "never"

    def test_documents_personal_merge(self, bundled):
        result = classify(bundled, "Documents/notes.txt")
        assert result.category == "personal"
        assert result.restore_default == "merge"

    def test_gitconfig_identity_portable(self, bundled):
        result = classify(bundled, ".gitconfig")
        assert result.category == "identity"
        assert result.portability == "portable"

    def test_bashrc_shell(self, bundled):
        result = classify(bundled, ".bashrc")
        assert result.category == "shell"

    def test_nvim_development(self, bundled):
        result = classify(bundled, ".config/nvim/init.lua")
        assert result.category == "development"
        assert result.application == "neovim"

    def test_hyprland_desktop_isolation(self, bundled):
        result = classify(bundled, ".config/hypr/hyprland.conf")
        assert result.category == "desktop"
        assert result.environment == "hyprland"

    def test_kde_classified_as_kde_only(self, bundled):
        result = classify(bundled, ".config/plasma-org.kde.plasma.desktop-appletsrc")
        assert result.environment == "kde"
        # KDE must not leak into other environments.
        assert result.environment != "hyprland"
        assert result.environment != "gnome"

    def test_gnome_gtk3(self, bundled):
        result = classify(bundled, ".config/gtk-3.0/settings.ini")
        assert result.environment == "gnome"

    def test_unknown_conservative(self, bundled):
        result = classify(bundled, "some/random/file.xyz")
        assert result.category == "unknown"
        assert result.portability == "unknown"
        assert result.restore_default == "review"

    def test_explainable(self, bundled):
        result = classify(bundled, ".config/hypr/hyprland.conf")
        assert result.rule_id
        assert result.rule_source.endswith("hyprland.yaml")


class TestXdgFallback:
    def test_cache_dir_fallback(self, monkeypatch, tmp_path):
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "home" / ".cache"))
        xdg = XdgDirs(home=tmp_path / "home")
        result = classify(
            load_ruleset([]), ".cache/thumbnails", xdg, root=tmp_path / "home"
        )
        assert result.category == "cache"
        assert result.restore_default == "never"

    def test_state_dir_fallback_generated(self, tmp_path):
        xdg = XdgDirs(home=tmp_path)
        result = classify(
            load_ruleset([]), ".local/state/something", xdg, root=tmp_path
        )
        assert result.category == "generated"

    def test_outside_xdg_dirs_unknown(self, tmp_path):
        xdg = XdgDirs(home=tmp_path)
        result = classify(
            load_ruleset([]), "random/file", xdg, root=tmp_path
        )
        assert result.category == "unknown"

    def test_custom_cache_home_respected(self, monkeypatch, tmp_path):
        custom = tmp_path / "custom-cache"
        monkeypatch.setenv("XDG_CACHE_HOME", str(custom))
        xdg = XdgDirs(home=tmp_path / "home")
        rel = custom.relative_to(tmp_path).as_posix()
        result = classify(
            load_ruleset([]), f"{rel}/entry", xdg, root=tmp_path
        )
        assert result.category == "cache"
