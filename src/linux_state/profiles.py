"""Profile definition, resolution and entry selection.

Profiles are logical sets of state (SPEC §7). A profile composes other
profiles or category selectors via ``extends``:

    profile: workstation-hyprland
    extends:
      - personal
      - shell
      - development
      - desktop:hyprland

Selector forms:
    name              -> category selector (must be a known category)
    desktop:<env>     -> environment selector
    applications:<app>-> application selector

Rules:
    - Resolution is recursive with cycle detection.
    - Desktop environments are mutually exclusive by default; resolving a
      profile containing two different desktop environments is an error
      unless the profile sets ``allow_multiple_desktops: true``.
    - Composition, never duplication: selectors are deduplicated.

Selection maps resolved selectors onto classifications produced by the
classification engine. Cache/generated entries are only selected when a
selector explicitly references their category (explicit user decision).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from linux_state.classification import CATEGORIES, Classification


class ProfileError(Exception):
    def __init__(self, source: str, reason: str):
        self.source = source
        self.reason = reason
        super().__init__(f"profile error in {source}: {reason}")


@dataclass(frozen=True)
class Selector:
    kind: str  # "category" | "environment" | "application"
    value: str

    def matches(self, classification: Classification) -> bool:
        if self.kind == "category":
            return classification.category == self.value
        if self.kind == "environment":
            return classification.environment == self.value
        if self.kind == "application":
            return classification.application == self.value
        return False


@dataclass(frozen=True)
class Profile:
    name: str
    source: str
    extends: tuple[str, ...]
    allow_multiple_desktops: bool = False


@dataclass(frozen=True)
class ResolvedProfile:
    name: str
    selectors: tuple[Selector, ...] = field(default_factory=tuple)


def parse_selector(token: str, source: str) -> Selector:
    """Parse 'name', 'desktop:x' or 'applications:x' into a Selector."""
    prefix, sep, value = token.partition(":")
    if not sep:
        if prefix not in CATEGORIES:
            raise ProfileError(
                source,
                f"unknown category {prefix!r} in selector {token!r}",
            )
        return Selector("category", prefix)
    mapping = {"desktop": "environment", "applications": "application"}
    kind = mapping.get(prefix)
    if kind is None:
        raise ProfileError(
            source,
            f"unknown selector prefix {prefix!r} in {token!r} "
            "(expected 'desktop:' or 'applications:')",
        )
    if not value:
        raise ProfileError(source, f"empty value in selector {token!r}")
    return Selector(kind, value)


def load_profiles(profiles_dir: Path) -> dict[str, Profile]:
    """Load all YAML profiles from a directory."""
    profiles_dir = Path(profiles_dir)
    if not profiles_dir.is_dir():
        raise ProfileError(str(profiles_dir), "profiles directory not found")

    profiles: dict[str, Profile] = {}
    for path in sorted(profiles_dir.glob("*.yaml")):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ProfileError(str(path), f"YAML parse error: {exc}") from exc
        if not document:
            continue
        name = document.get("profile")
        if not name:
            raise ProfileError(str(path), "missing 'profile' key")
        if name in profiles:
            raise ProfileError(str(path), f"duplicate profile name {name!r}")
        extends = document.get("extends", [])
        if not isinstance(extends, list):
            raise ProfileError(str(path), "'extends' must be a list")
        profiles[name] = Profile(
            name=name,
            source=str(path),
            extends=tuple(str(item) for item in extends),
            allow_multiple_desktops=bool(document.get("allow_multiple_desktops", False)),
        )
    return profiles


class ProfileResolver:
    def __init__(self, profiles: dict[str, Profile]):
        self._profiles = profiles

    def resolve(self, name: str) -> ResolvedProfile:
        profile = self._profiles.get(name)
        if profile is None:
            # A bare, undefined name is accepted as a pure category selector,
            # enabling `--profile shell` without defining a file for it.
            return ResolvedProfile(
                name=name,
                selectors=(parse_selector(name, "<inline>"),),
            )

        tokens: list[str] = []
        self._collect(profile, tokens, visiting=set())
        selectors = []
        seen = set()
        for token in tokens:
            # Tokens naming other profiles are composition links, not
            # selectors; their own selectors were collected recursively.
            if token in self._profiles:
                continue
            selector = parse_selector(token, profile.source)
            key = (selector.kind, selector.value)
            if key not in seen:
                seen.add(key)
                selectors.append(selector)

        self._check_desktop_exclusivity(profile, selectors)
        return ResolvedProfile(name=profile.name, selectors=tuple(selectors))

    def _collect(self, profile: Profile, tokens: list, visiting: set) -> None:
        if profile.name in visiting:
            chain = " -> ".join(sorted(visiting))
            raise ProfileError(profile.source, f"circular extends involving {chain}")
        visiting.add(profile.name)
        for token in profile.extends:
            tokens.append(token)
            dependency = self._profiles.get(token)
            if dependency is not None:
                self._collect(dependency, tokens, set(visiting))
        visiting.discard(profile.name)

    @staticmethod
    def _check_desktop_exclusivity(profile: Profile, selectors: list[Selector]) -> None:
        if profile.allow_multiple_desktops:
            return
        environments = sorted({s.value for s in selectors if s.kind == "environment"})
        if len(environments) > 1:
            raise ProfileError(
                profile.source,
                f"multiple desktop environments selected ({', '.join(environments)}); "
                "set 'allow_multiple_desktops: true' to override explicitly",
            )


def select_entries(
    classified: list[tuple[str, Classification]],
    resolved: ResolvedProfile,
) -> list[tuple[str, Classification]]:
    """Select (relative_path, classification) pairs matching the profile."""
    return [
        (path, classification)
        for path, classification in classified
        if any(selector.matches(classification) for selector in resolved.selectors)
    ]
