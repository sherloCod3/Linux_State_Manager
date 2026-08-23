"""Profile resolution and selection tests."""

from __future__ import annotations

import pytest

from linux_state.classification import Classification
from linux_state.profiles import (
    ProfileError,
    ProfileResolver,
    load_profiles,
    parse_selector,
    select_entries,
)


def cat(name: str) -> Classification:
    return Classification(category=name, portability=name, restore_default="merge")


def env(environment: str, category: str = "desktop") -> Classification:
    return Classification(
        category=category,
        portability="environment",
        restore_default="backup-and-replace",
        environment=environment,
    )


def app(application: str, category: str = "application") -> Classification:
    return Classification(
        category=category,
        portability="portable",
        restore_default="backup-and-replace",
        application=application,
    )


def write_profile(tmp_path, name: str, body: str):
    path = tmp_path / name
    path.write_text(body)
    return path


@pytest.fixture
def workstation_dir(tmp_path):
    write_profile(
        tmp_path,
        "workstation-hyprland.yaml",
        "profile: workstation-hyprland\n"
        "extends:\n  - personal\n  - shell\n  - development\n  - desktop:hyprland\n",
    )
    return tmp_path


class TestLoading:
    def test_loads_profile(self, workstation_dir):
        profiles = load_profiles(workstation_dir)
        assert "workstation-hyprland" in profiles
        assert profiles["workstation-hyprland"].extends == (
            "personal", "shell", "development", "desktop:hyprland",
        )

    def test_missing_key_rejected(self, tmp_path):
        write_profile(tmp_path, "bad.yaml", "name: x\n")
        with pytest.raises(ProfileError):
            load_profiles(tmp_path)

    def test_duplicate_names_rejected(self, tmp_path):
        body = "profile: dup\nextends: []\n"
        write_profile(tmp_path, "a.yaml", body)
        write_profile(tmp_path, "b.yaml", body)
        with pytest.raises(ProfileError) as excinfo:
            load_profiles(tmp_path)
        assert "duplicate" in excinfo.value.reason

    def test_extends_must_be_list(self, tmp_path):
        write_profile(tmp_path, "bad.yaml", "profile: p\nextends: shell\n")
        with pytest.raises(ProfileError):
            load_profiles(tmp_path)


class TestSelectors:
    def test_bare_category(self):
        selector = parse_selector("personal", "<test>")
        assert selector.kind == "category"
        assert selector.value == "personal"

    def test_desktop_prefix(self):
        selector = parse_selector("desktop:hyprland", "<test>")
        assert (selector.kind, selector.value) == ("environment", "hyprland")

    def test_applications_prefix(self):
        selector = parse_selector("applications:nvim", "<test>")
        assert (selector.kind, selector.value) == ("application", "nvim")

    def test_unknown_prefix_rejected(self):
        with pytest.raises(ProfileError):
            parse_selector("bogus:x", "<test>")

    def test_unknown_category_rejected(self):
        with pytest.raises(ProfileError):
            parse_selector("notacategory", "<test>")

    def test_empty_value_rejected(self):
        with pytest.raises(ProfileError):
            parse_selector("desktop:", "<test>")


class TestResolution:
    def test_undefined_name_is_category_selector(self, workstation_dir):
        resolver = ProfileResolver(load_profiles(workstation_dir))
        resolved = resolver.resolve("shell")
        assert resolved.selectors == (("category", "shell") and resolved.selectors)
        assert resolved.selectors[0].kind == "category"

    def test_composition_collects_selectors(self, workstation_dir):
        resolver = ProfileResolver(load_profiles(workstation_dir))
        resolved = resolver.resolve("workstation-hyprland")
        pairs = {(s.kind, s.value) for s in resolved.selectors}
        assert ("category", "personal") in pairs
        assert ("category", "shell") in pairs
        assert ("category", "development") in pairs
        assert ("environment", "hyprland") in pairs

    def test_nested_extends(self, tmp_path):
        write_profile(tmp_path, "base.yaml", "profile: base\nextends: [identity]\n")
        write_profile(
            tmp_path, "top.yaml", "profile: top\nextends: [base, shell]\n"
        )
        resolved = ProfileResolver(load_profiles(tmp_path)).resolve("top")
        kinds = {s.value for s in resolved.selectors}
        assert {"identity", "shell"} <= kinds

    def test_cycle_detected(self, tmp_path):
        write_profile(tmp_path, "a.yaml", "profile: a\nextends: [b]\n")
        write_profile(tmp_path, "b.yaml", "profile: b\nextends: [a]\n")
        with pytest.raises(ProfileError) as excinfo:
            ProfileResolver(load_profiles(tmp_path)).resolve("a")
        assert "circular" in excinfo.value.reason

    def test_self_cycle_detected(self, tmp_path):
        write_profile(tmp_path, "a.yaml", "profile: a\nextends: [a]\n")
        with pytest.raises(ProfileError):
            ProfileResolver(load_profiles(tmp_path)).resolve("a")

    def test_multiple_desktops_rejected_by_default(self, tmp_path):
        write_profile(
            tmp_path,
            "both.yaml",
            "profile: both\nextends: [desktop:kde, desktop:gnome]\n",
        )
        with pytest.raises(ProfileError) as excinfo:
            ProfileResolver(load_profiles(tmp_path)).resolve("both")
        assert "multiple desktop" in excinfo.value.reason

    def test_multiple_desktops_allowed_explicitly(self, tmp_path):
        write_profile(
            tmp_path,
            "both.yaml",
            "profile: both\nextends: [desktop:kde, desktop:gnome]\n"
            "allow_multiple_desktops: true\n",
        )
        resolved = ProfileResolver(load_profiles(tmp_path)).resolve("both")
        assert len(resolved.selectors) == 2


class TestSelection:
    def classified_items(self):
        return [
            (".bashrc", cat("shell")),
            (".gitconfig", cat("identity")),
            ("Documents/notes.txt", cat("personal")),
            (".cache/x", cat("cache")),
            (".config/hypr/hyprland.conf", env("hyprland")),
            (".config/kdeglobals", env("kde")),
            (".config/nvim/init.lua", app("neovim", category="development")),
            ("random.xyz", cat("unknown")),
        ]

    def test_single_category(self, workstation_dir):
        resolver = ProfileResolver(load_profiles(workstation_dir))
        selected = select_entries(self.classified_items(), resolver.resolve("shell"))
        assert [p for p, _ in selected] == [".bashrc"]

    def test_hyprland_excludes_kde(self, workstation_dir):
        """SPEC success case 2: KDE state is not selected on Hyprland."""
        resolver = ProfileResolver(load_profiles(workstation_dir))
        selected = select_entries(
            self.classified_items(), resolver.resolve("workstation-hyprland")
        )
        paths = [p for p, _ in selected]
        assert ".config/hypr/hyprland.conf" in paths
        assert ".config/kdeglobals" not in paths
        assert ".bashrc" in paths

    def test_kde_profile_excludes_hyprland(self, tmp_path):
        """SPEC success case 3: Hyprland state not restored into KDE."""
        write_profile(
            tmp_path,
            "wkde.yaml",
            "profile: wkde\nextends: [desktop:kde]\n",
        )
        resolver = ProfileResolver(load_profiles(tmp_path))
        selected = select_entries(self.classified_items(), resolver.resolve("wkde"))
        paths = [p for p, _ in selected]
        assert ".config/kdeglobals" in paths
        assert ".config/hypr/hyprland.conf" not in paths

    def test_cache_not_selected_unless_explicit(self, workstation_dir):
        resolver = ProfileResolver(load_profiles(workstation_dir))
        selected = select_entries(
            self.classified_items(), resolver.resolve("workstation-hyprland")
        )
        assert ".cache/x" not in [p for p, _ in selected]

        explicit = select_entries(
            self.classified_items(),
            ProfileResolver({}).resolve("cache"),
        )
        assert ".cache/x" in [p for p, _ in explicit]

    def test_unknown_never_selected(self, workstation_dir):
        resolver = ProfileResolver(load_profiles(workstation_dir))
        selected = select_entries(
            self.classified_items(), resolver.resolve("workstation-hyprland")
        )
        assert "random.xyz" not in [p for p, _ in selected]
