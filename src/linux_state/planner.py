"""Restore planning (pure; no side effects).

The planner answers "what should happen": it compares a stored snapshot
against the current state of the same tree, restricted to entries selected
by a resolved profile. It never touches the filesystem.

Actions:
    NEW       target missing; snapshot content would be created
    SAME      target exists and is identical to the snapshot
    MODIFIED  target differs only in metadata (e.g. mode)
    CONFLICT  target exists with different content
    SKIPPED   excluded by policy (never / review) or not selected

Dry run == planning. Running the planner IS the dry run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from linux_state.classification import Classification
from linux_state.discovery import Entry, Kind, discover
from linux_state.profiles import ResolvedProfile, select_entries

NEW = "NEW"
SAME = "SAME"
MODIFIED = "MODIFIED"
CONFLICT = "CONFLICT"
SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class PlannedAction:
    path: str  # relative to root
    action: str
    reason: str = ""
    entry_kind: str = ""


@dataclass(frozen=True)
class RestorePlan:
    snapshot_id: str
    profile: str
    actions: tuple[PlannedAction, ...] = field(default_factory=tuple)

    def counts(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for action in self.actions:
            result[action.action] = result.get(action.action, 0) + 1
        return result


def classification_from_record(record: dict) -> Classification | None:
    """Rebuild a Classification from a manifest record."""
    info = record.get("classification")
    if info is None:
        return None
    return Classification(
        category=info.get("category", "unknown"),
        portability=info.get("portability", "unknown"),
        restore_default=info.get("restore", "review"),
        environment=info.get("environment"),
        application=info.get("application"),
        rule_id=info.get("rule_id", "none"),
        rule_source=info.get("rule_source", "none"),
    )


def _current_index(current_root: Path) -> dict[str, Entry]:
    return {
        entry.path.relative_to(current_root).as_posix(): entry
        for entry in discover(current_root, hash_files=True)
    }


def _mode_of(entry: Entry) -> int:
    try:
        return int(entry.mode, 8)
    except ValueError:  # pragma: no cover - defensive
        return 0


def _compare(record: dict, current: Entry | None) -> tuple[str, str]:
    """Compare one selected snapshot record against current state."""
    kind = record["type"]

    if current is None:
        return NEW, "target missing"

    if kind != current.kind.value:
        return CONFLICT, f"type changed ({kind} -> {current.kind.value})"

    if kind == Kind.DIRECTORY.value:
        return SAME, "directory present"

    if kind == Kind.SYMLINK.value:
        if record.get("symlink_target") == current.symlink_target:
            return SAME, "symlink identical"
        return CONFLICT, "symlink target differs"

    # Regular file.
    snapshot_hash = record.get("sha256")
    current_hash = current.sha256
    content_differs = (
        snapshot_hash is not None
        and current_hash is not None
        and snapshot_hash != current_hash
    )
    mode_differs = _mode_of(current) != int(record["mode"], 8)

    if content_differs:
        return CONFLICT, "content differs"
    if mode_differs:
        return MODIFIED, "metadata differs"
    if snapshot_hash is None or current_hash is None:
        # Hash unavailable on either side; treat conservative as conflict.
        return CONFLICT, "hash unavailable for comparison"
    return SAME, "file identical"


def build_plan(
    manifest: dict,
    resolved: ResolvedProfile,
    current_root: Path,
) -> RestorePlan:
    """Build a RestorePlan. Pure: reads the current tree, writes nothing."""
    current_root = Path(current_root).resolve()
    snapshot_root = Path(manifest["root"]).resolve()
    if snapshot_root != current_root:
        raise ValueError(
            f"snapshot root {snapshot_root} does not match target {current_root}"
        )

    records = []
    for record in manifest["files"]:
        relative = Path(record["path"]).relative_to(snapshot_root).as_posix()
        classification = classification_from_record(record)
        records.append((relative, record, classification))

    selected = select_entries(
        [(rel, cls) for rel, record, cls in records if cls is not None],
        resolved,
    )
    selected_paths = {path for path, _ in selected}

    current_state = _current_index(current_root)

    actions: list[PlannedAction] = []
    for relative, record, classification in sorted(records):
        if relative not in selected_paths:
            continue
        assert classification is not None

        if classification.restore_default == "never":
            actions.append(PlannedAction(
                relative, SKIPPED, "policy: never", record["type"],
            ))
            continue
        if classification.restore_default == "review":
            actions.append(PlannedAction(
                relative, SKIPPED, "policy: review required", record["type"],
            ))
            continue

        action, reason = _compare(record, current_state.get(relative))
        actions.append(PlannedAction(relative, action, reason, record["type"]))

    return RestorePlan(
        snapshot_id=manifest.get("snapshot", {}).get("id", ""),
        profile=resolved.name,
        actions=tuple(actions),
    )
