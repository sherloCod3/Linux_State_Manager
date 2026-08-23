"""Rule-based, explainable classification.

Classification never relies on file extensions alone (SPEC §9). Entries are
matched against ordered rules; the first matching rule wins. Rule files
loaded earlier have higher priority, so user rule directories are passed
before bundled defaults.

Every classification records which rule matched and where it came from,
so the system can always answer: "why was this classified this way?"

Conservative defaults:
    unknown -> review (never treated as safe to restore)
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

CATEGORIES = frozenset(
    {
        "personal",
        "identity",
        "shell",
        "development",
        "application",
        "desktop",
        "distribution",
        "machine",
        "secret",
        "generated",
        "cache",
        "unknown",
    }
)

PORTABILITIES = frozenset(
    {
        "portable",
        "environment",
        "machine",
        "secret",
        "personal",
        "generated",
        "cache",
        "unknown",
    }
)


@dataclass(frozen=True)
class Classification:
    category: str
    portability: str
    restore_default: str  # backup-and-replace | merge | never | review
    environment: str | None = None
    application: str | None = None
    rule_id: str = "none"
    rule_source: str = "none"


@dataclass(frozen=True)
class Rule:
    id: str
    source: str
    pattern: str  # fnmatch pattern relative to the scan root
    category: str
    portability: str
    restore_default: str
    environment: str | None = None
    application: str | None = None


class RuleError(Exception):
    def __init__(self, source: str, reason: str):
        self.source = source
        self.reason = reason
        super().__init__(f"invalid rules in {source}: {reason}")


def _parse_rule_file(path: Path) -> list[Rule]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuleError(str(path), exc.strerror or str(exc)) from exc
    except yaml.YAMLError as exc:
        raise RuleError(str(path), f"YAML parse error: {exc}") from exc

    if not document:
        return []
    entries = document.get("rules")
    if not isinstance(entries, list):
        raise RuleError(str(path), "document must contain a 'rules' list")

    rules = []
    for index, item in enumerate(entries):
        if not isinstance(item, dict) or "match" not in item:
            raise RuleError(str(path), f"rule #{index} needs a 'match' key")
        match = item["match"]
        if isinstance(match, dict):
            pattern = match.get("path")
        else:
            pattern = match
        if not pattern:
            raise RuleError(str(path), f"rule #{index} has no match path")

        category = item.get("category", "unknown")
        portability = item.get("portability", "unknown")
        if category not in CATEGORIES:
            raise RuleError(str(path), f"rule #{index}: unknown category {category!r}")
        if portability not in PORTABILITIES:
            raise RuleError(str(path), f"rule #{index}: unknown portability {portability!r}")

        rules.append(
            Rule(
                id=item.get("id", f"{path.name}:{index}"),
                source=str(path),
                pattern=_normalize_pattern(pattern),
                category=category,
                portability=portability,
                restore_default=item.get("restore", "review"),
                environment=item.get("environment"),
                application=item.get("application"),
            )
        )
    return rules


def _normalize_pattern(pattern: str) -> str:
    """Accept both '~/...' and root-relative patterns."""
    pattern = pattern.strip()
    if pattern.startswith("~/"):
        pattern = pattern[2:]
    return pattern.lstrip("/")


class RuleSet:
    """Ordered rules; earlier rules and earlier files take precedence."""

    def __init__(self, rules: list[Rule]):
        self._rules = rules

    def __len__(self) -> int:
        return len(self._rules)

    def classify(
        self,
        relative_path: str,
        xdg: "XdgDirs",
        root: Path,
    ) -> Classification:
        for rule in self._rules:
            if fnmatch.fnmatch(relative_path, rule.pattern):
                return Classification(
                    category=rule.category,
                    portability=rule.portability,
                    restore_default=rule.restore_default,
                    environment=rule.environment,
                    application=rule.application,
                    rule_id=rule.id,
                    rule_source=rule.source,
                )
        return xdg.fallback(relative_path, root)


def load_ruleset(rule_files: list[Path]) -> RuleSet:
    """Load rule files in priority order (first file wins on conflicts)."""
    rules: list[Rule] = []
    for path in rule_files:
        rules.extend(_parse_rule_file(path))
    return RuleSet(rules)


def bundled_rules_dir() -> Path:
    return Path(__file__).parent / "rules"


def default_rule_files() -> list[Path]:
    """Bundled defaults in priority order."""
    base = bundled_rules_dir()
    return [
        base / "default.yaml",
        *sorted((base / "applications").glob("*.yaml")),
        *sorted((base / "desktop").glob("*.yaml")),
    ]


class XdgDirs:
    """XDG-aware fallback classification when no rule matches."""

    def __init__(self, home: Path | None = None):
        self.home = home or Path.home()
        self.cache_dir = Path(
            os.environ.get("XDG_CACHE_HOME", str(self.home / ".cache"))
        )
        self.state_dir = Path(
            os.environ.get("XDG_STATE_HOME", str(self.home / ".local" / "state"))
        )

    def _dir_relative_to(self, directory: Path, root: Path) -> str | None:
        """Relative form of an XDG dir inside the scan root, if applicable."""
        try:
            return directory.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return None

    def fallback(self, relative_path: str, root: Path) -> Classification:
        for directory, category, portability, rule_id in (
            (self.cache_dir, "cache", "cache", "builtin-xdg-cache"),
            (self.state_dir, "generated", "generated", "builtin-xdg-state"),
        ):
            base = self._dir_relative_to(directory, root)
            if base and (
                relative_path == base or relative_path.startswith(base + "/")
            ):
                return Classification(
                    category=category,
                    portability=portability,
                    restore_default="never",
                    rule_id=rule_id,
                    rule_source="builtin:xdg",
                )
        return Classification(
            category="unknown",
            portability="unknown",
            restore_default="review",
            rule_id="builtin-unknown",
            rule_source="builtin:fallback",
        )
