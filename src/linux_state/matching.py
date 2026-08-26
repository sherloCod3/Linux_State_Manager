"""Shared glob-matching for user-supplied exclude patterns.

Patterns are fnmatch globs relative to the scan/restore root (POSIX
separators, ``~`` and leading slashes stripped). ``dir/**`` also excludes
the directory itself — fnmatch alone does not provide that intuition.
"""

from __future__ import annotations

import fnmatch


def normalize_exclude_patterns(patterns: list[str] | None) -> list[str]:
    """Normalize raw user patterns into comparable relative globs."""
    normalized = []
    for pat in patterns or []:
        p = pat.strip()
        if p.startswith("~/"):
            p = p[2:]
        p = p.lstrip("/")
        if p:
            normalized.append(p)
    return normalized


def is_excluded(relative: str, patterns: list[str]) -> bool:
    """Return True when *relative* matches any normalized exclude glob."""
    for pat in patterns:
        if pat.endswith("/**"):
            base = pat[:-3]
            if relative == base or relative.startswith(base + "/"):
                return True
        if fnmatch.fnmatch(relative, pat):
            return True
    return False
