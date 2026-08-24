"""CLI entry point.

The CLI is a thin layer: it parses arguments, calls services and prints
results. It never touches the filesystem directly.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

from linux_state import __version__
from linux_state.classification import RuleSet, XdgDirs, default_rule_files, load_ruleset
from linux_state.discovery import DiscoveryError, Kind, discover
from linux_state.manifest import build_manifest, entry_to_display, write_manifest
from linux_state.profiles import ProfileError, ProfileResolver, load_profiles, select_entries
from linux_state.snapshot import SnapshotError, create_snapshot, new_snapshot_id
from linux_state.storage import (
    default_storage_root,
    list_snapshots,
    manifest_file,
    metadata_file,
)


def _print_summary(entries, root: Path, verbose: bool, ruleset=None, xdg=None,
                   selected=None) -> None:
    counts = Counter(e.kind for e in entries)
    print(f"Scanned: {root}")
    print(f"  files:      {counts.get(Kind.FILE, 0)}")
    print(f"  directories:{counts.get(Kind.DIRECTORY, 0)}")
    print(f"  symlinks:   {counts.get(Kind.SYMLINK, 0)}")
    broken = sum(1 for e in entries if e.broken_symlink)
    if broken:
        print(f"  broken links: {broken}")
    others = counts.get(Kind.OTHER, 0)
    if others:
        print(f"  special:    {others}")

    if verbose:
        home = Path.home()
        for entry in entries:
            relative = entry.path.relative_to(root).as_posix()
            result = ruleset.classify(relative, xdg, root)
            if selected is not None and (relative, result) not in selected:
                continue
            tag = f" [{result.category}/{result.rule_id}]"
            print(f"  {entry.kind.value:<9} {entry_to_display(entry, home)}{tag}")


def _build_classifier(rules_dir: str | None) -> tuple[RuleSet, XdgDirs] | None:
    """User rules first (higher priority), then bundled defaults."""
    files = []
    if rules_dir:
        user_dir = Path(rules_dir).expanduser()
        if not user_dir.is_dir():
            return None
        files.extend(sorted(user_dir.glob("*.yaml")))
    files.extend(default_rule_files())
    xdg = XdgDirs()
    ruleset = load_ruleset(files)
    return ruleset, xdg


def _resolve_profile(name: str, profiles_dir: str | None):
    if profiles_dir:
        directory = Path(profiles_dir).expanduser()
        profiles = load_profiles(directory)
    else:
        default_dir = (
            Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
            / "linux-state"
            / "profiles"
        )
        profiles = load_profiles(default_dir) if default_dir.is_dir() else {}
    return ProfileResolver(profiles).resolve(name)


def cmd_scan(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser()
    if not root.is_dir():
        print(f"ERROR: not a directory: {root}", file=sys.stderr)
        return 1

    classifier_pair = _build_classifier(args.rules)
    if classifier_pair is None:
        print(f"ERROR: rules directory not found: {args.rules}", file=sys.stderr)
        return 1
    ruleset, xdg = classifier_pair

    try:
        entries = list(discover(root, hash_files=not args.no_hash))
    except DiscoveryError as exc:
        print(
            f"ERROR\nOperation: {exc.operation}\nPath: {exc.path}\n"
            f"Reason: {exc.reason}\nAction: check permissions and retry.",
            file=sys.stderr,
        )
        return 2

    selected = None
    if args.profile:
        try:
            resolved = _resolve_profile(args.profile, args.profiles_dir)
        except ProfileError as exc:
            print(
                f"ERROR\nOperation: profile resolution\nPath: {exc.source}\n"
                f"Reason: {exc.reason}\nAction: fix the profile definition and retry.",
                file=sys.stderr,
            )
            return 2
        classified = [
            (e.path.relative_to(root).as_posix(), ruleset.classify(
                e.path.relative_to(root).as_posix(), xdg, root
            ))
            for e in entries
        ]
        selected = set(select_entries(classified, resolved))
        print(f"Profile: {resolved.name} ({len(selected)} of {len(entries)} entries)")

    _print_summary(entries, root, args.verbose, ruleset, xdg, selected)

    if args.json:
        manifest = build_manifest(root, entries, classifier=ruleset, xdg=xdg)
        write_manifest(manifest, Path(args.json))
        print(f"Manifest written: {args.json}")
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser()
    if not root.is_dir():
        print(f"ERROR: not a directory: {root}", file=sys.stderr)
        return 1

    storage_root = Path(args.storage).expanduser() if args.storage else default_storage_root()
    classifier_pair = _build_classifier(args.rules)
    if classifier_pair is None:
        print(f"ERROR: rules directory not found: {args.rules}", file=sys.stderr)
        return 1
    ruleset, xdg = classifier_pair
    skipped: list[Path] = []
    resolved_profile = None
    if args.profile:
        try:
            resolved_profile = _resolve_profile(args.profile, args.profiles_dir)
        except ProfileError as exc:
            print(
                f"ERROR\nOperation: profile resolution\nPath: {exc.source}\n"
                f"Reason: {exc.reason}\nAction: fix the profile definition and retry.",
                file=sys.stderr,
            )
            return 2

    try:
        snapshot_id = create_snapshot(
            root,
            storage_root,
            hash_files=not args.no_hash,
            classifier=ruleset,
            xdg=xdg,
            compression=args.compression,
            skipped=skipped,
            profile=resolved_profile,
            exclude=args.exclude,
        )
    except DiscoveryError as exc:
        print(
            f"ERROR\nOperation: {exc.operation}\nPath: {exc.path}\n"
            f"Reason: {exc.reason}\nAction: check permissions and retry.",
            file=sys.stderr,
        )
        return 2
    except SnapshotError as exc:
        print(
            f"ERROR\nOperation: {exc.operation}\nPath: {exc.path}\n"
            f"Reason: {exc.reason}\nAction: fix the issue and retry.",
            file=sys.stderr,
        )
        return 2

    print(f"Snapshot created: {snapshot_id}")
    print(f"Storage: {storage_root / 'snapshots' / snapshot_id}")
    for path in skipped:
        print(f"WARN: vanished during capture, skipped: {path}")
    if skipped:
        print(f"Skipped {len(skipped)} file(s) that disappeared during capture.")

    if args.keep is not None:
        from linux_state.storage import prune_snapshots

        try:
            pruned = prune_snapshots(storage_root, args.keep)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        for removed in pruned:
            print(f"Pruned: {removed}")
        if pruned:
            print(f"Pruned {len(pruned)} snapshot(s); kept the newest {args.keep}.")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    from linux_state.planner import build_plan
    from linux_state.profiles import ProfileResolver, load_profiles
    from linux_state.storage import load_manifest

    root = Path(args.root).expanduser()
    if not root.is_dir():
        print(f"ERROR: not a directory: {root}", file=sys.stderr)
        return 1

    storage_root = Path(args.storage).expanduser() if args.storage else default_storage_root()

    try:
        manifest = load_manifest(storage_root, args.snapshot)
    except (FileNotFoundError, ValueError) as exc:
        print(
            f"ERROR\nOperation: plan\nPath: {storage_root / 'snapshots' / args.snapshot}\n"
            f"Reason: {exc}\nAction: check the snapshot id with 'linux-state list'.",
            file=sys.stderr,
        )
        return 1

    if args.profile:
        try:
            resolved = _resolve_profile(args.profile, args.profiles_dir)
        except ProfileError as exc:
            print(
                f"ERROR\nOperation: profile resolution\nPath: {exc.source}\n"
                f"Reason: {exc.reason}\nAction: fix the profile definition and retry.",
                file=sys.stderr,
            )
            return 2
    else:
        # No profile given: select all restorable categories; policies
        # (never/review) still apply inside the planner.
        from linux_state.profiles import ResolvedProfile, Selector

        resolved = ResolvedProfile(name="__all__", selectors=tuple(
            Selector("category", category)
            for category in ("personal", "identity", "shell", "development",
                             "application", "desktop")
        ))

    try:
        plan = build_plan(manifest, resolved, root)
    except ValueError as exc:
        print(
            f"ERROR\nOperation: plan\nPath: {root}\n"
            f"Reason: {exc}\nAction: pass --root matching the snapshot root.",
            file=sys.stderr,
        )
        return 1

    home = Path.home()
    for action in plan.actions:
        suffix = f" ({action.reason})" if action.action == "SKIPPED" and action.reason else ""
        print(f"{action.action:<9} {action.path}{suffix}")

    counts = plan.counts()
    summary = ", ".join(f"{name}: {count}" for name, count in sorted(counts.items()))
    print(f"\nPlan summary -> {summary or 'no actions'}")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    from linux_state.executor import ExecutionError, execute_plan
    from linux_state.planner import build_plan
    from linux_state.profiles import ResolvedProfile, Selector
    from linux_state.storage import data_dir, load_manifest

    root = Path(args.root).expanduser()
    if not root.is_dir():
        print(f"ERROR: not a directory: {root}", file=sys.stderr)
        return 1

    storage_root = Path(args.storage).expanduser() if args.storage else default_storage_root()

    try:
        manifest = load_manifest(storage_root, args.snapshot)
        snapshot_data = data_dir(storage_root, args.snapshot)
    except (FileNotFoundError, ValueError) as exc:
        print(
            f"ERROR\nOperation: restore\nPath: {storage_root / 'snapshots' / args.snapshot}\n"
            f"Reason: {exc}\nAction: check the snapshot id with 'linux-state list'.",
            file=sys.stderr,
        )
        return 1

    if args.profile:
        try:
            resolved = _resolve_profile(args.profile, args.profiles_dir)
        except ProfileError as exc:
            print(
                f"ERROR\nOperation: profile resolution\nPath: {exc.source}\n"
                f"Reason: {exc.reason}\nAction: fix the profile definition and retry.",
                file=sys.stderr,
            )
            return 2
    else:
        resolved = ResolvedProfile(name="__all__", selectors=tuple(
            Selector("category", category)
            for category in ("personal", "identity", "shell", "development",
                             "application", "desktop")
        ))

    try:
        plan = build_plan(manifest, resolved, root)
    except ValueError as exc:
        print(
            f"ERROR\nOperation: restore\nPath: {root}\n"
            f"Reason: {exc}\nAction: pass --root matching the snapshot root.",
            file=sys.stderr,
        )
        return 1

    try:
        tx = execute_plan(
            plan,
            root,
            storage_root,
            snapshot_data,
            manifest,
            approve=args.approve,
            conflict_policy=args.conflict,
        )
    except ExecutionError as exc:
        print(
            f"ERROR\nOperation: {exc.operation}\nPath: {exc.path}\n"
            f"Reason: {exc.reason}\nAction: review the plan and retry.",
            file=sys.stderr,
        )
        return 2

    home = Path.home()
    for path in tx.executed:
        try:
            display = f"~/{Path(path).relative_to(home)}"
        except ValueError:
            display = path
        print(f"RESTORED  {display}")

    # A restore is only complete once verification passes (AGENTS §13).
    from linux_state.verification import attach_verification, verify_paths

    report = verify_paths(root, manifest, tx.executed)
    attach_verification(tx.directory, report)
    print(
        f"\nVerification: {report['result']} "
        f"(checked {report['checked']}, failures {len(report['failures'])})"
    )
    for failure in report["failures"]:
        print(f"  FAILED {failure['path']}: {failure['check']} - {failure['reason']}")

    counts = plan.counts()
    summary = ", ".join(f"{name}: {count}" for name, count in sorted(counts.items()))
    print(f"\nTransaction: {tx.id} ({tx.status})")
    print(f"Executed: {len(tx.executed)}  Failed: {len(tx.failed)}")
    print(f"Plan summary -> {summary or 'no actions'}")
    if tx.status == "failed" or report["result"] == "FAIL":
        print("Rollback available: linux-state rollback --transaction " + tx.id)
        return 2
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    from linux_state.rollback import latest_transaction, perform_rollback
    from linux_state.storage import transactions_dir

    storage_root = Path(args.storage).expanduser() if args.storage else default_storage_root()
    tx_id = args.transaction or latest_transaction(storage_root)
    if not tx_id:
        print("ERROR\nOperation: rollback\nReason: no transactions found.\n"
              "Action: pass --transaction <id>.", file=sys.stderr)
        return 1

    try:
        original, rb_tx = perform_rollback(storage_root, tx_id, approve=args.approve)
    except Exception as exc:
        operation = getattr(exc, "operation", "rollback")
        path = getattr(exc, "path", None)
        reason = exc
        print(
            f"ERROR\nOperation: {operation}\nPath: {path}\n"
            f"Reason: {reason}\nAction: inspect the transaction record and retry.",
            file=sys.stderr,
        )
        return 2

    for entry in rb_tx.executed:
        print(f"ROLLBACK  {entry}")
    print(f"\nRolled back transaction: {original.id}")
    print(f"Rollback transaction: {rb_tx.id} ({rb_tx.status})")
    return 0 if rb_tx.status == "completed" else 2


def cmd_list(args: argparse.Namespace) -> int:
    storage_root = Path(args.storage).expanduser() if args.storage else default_storage_root()
    ids = list_snapshots(storage_root)
    if not ids:
        print("No snapshots found.")
        return 0
    for snapshot_id in ids:
        if args.verbose:
            manifest = manifest_file(storage_root, snapshot_id)
            metadata = metadata_file(storage_root, snapshot_id)
            print(f"{snapshot_id}  manifest={'yes' if manifest.is_file() else 'MISSING'}  "
                  f"metadata={'yes' if metadata.is_file() else 'MISSING'}")
        else:
            print(snapshot_id)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="linux-state",
        description="Cross-distribution Linux state manager.",
    )
    parser.add_argument("--version", action="version", version=__version__)

    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Read-only discovery of a directory tree.")
    scan.add_argument(
        "--root",
        default=str(Path.home()),
        help="Directory to scan (default: $HOME).",
    )
    scan.add_argument(
        "--json",
        metavar="PATH",
        help="Write the manifest JSON to PATH.",
    )
    scan.add_argument(
        "--no-hash",
        action="store_true",
        help="Skip SHA-256 hashing of regular files.",
    )
    scan.add_argument(
        "--rules",
        metavar="DIR",
        help="User rules directory; takes precedence over bundled defaults.",
    )
    scan.add_argument(
        "--profile",
        metavar="NAME",
        help="Only consider entries selected by this profile.",
    )
    scan.add_argument(
        "--profiles-dir",
        metavar="DIR",
        help="Profiles directory (default: $XDG_CONFIG_HOME/linux-state/profiles).",
    )
    scan.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="List every discovered entry with its classification.",
    )
    scan.set_defaults(func=cmd_scan)

    snapshot = sub.add_parser(
        "snapshot",
        help="Create a full snapshot of a directory tree.",
    )
    snapshot.add_argument(
        "--root",
        default=str(Path.home()),
        help="Directory to capture (default: $HOME).",
    )
    snapshot.add_argument(
        "--storage",
        metavar="PATH",
        help="Storage root (default: $XDG_DATA_HOME/linux-state).",
    )
    snapshot.add_argument(
        "--no-hash",
        action="store_true",
        help="Skip SHA-256 hashing.",
    )
    snapshot.add_argument(
        "--compression",
        choices=("gzip", "zstd"),
        default="gzip",
        help="Snapshot data compression (default: gzip).",
    )
    snapshot.add_argument(
        "--keep",
        type=int,
        metavar="N",
        help="After creating the snapshot, prune all but the newest N snapshots.",
    )
    snapshot.add_argument(
        "--rules",
        metavar="DIR",
        help="User rules directory; takes precedence over bundled defaults.",
    )
    snapshot.add_argument(
        "--profile",
        metavar="NAME",
        help="Only snapshot entries selected by this profile (e.g. shell, desktop:hyprland). "
             "When omitted the whole tree is captured.",
    )
    snapshot.add_argument(
        "--profiles-dir",
        metavar="DIR",
        help="Profiles directory (default: $XDG_CONFIG_HOME/linux-state/profiles).",
    )
    snapshot.add_argument(
        "--exclude",
        metavar="PATTERN",
        action="append",
        default=None,
        help="Exclude paths matching PATTERN (fnmatch, relative to --root). "
             "Repeatable. Example: --exclude '.cache/**' --exclude 'Downloads/**'.",
    )
    snapshot.set_defaults(func=cmd_snapshot)

    list_cmd = sub.add_parser("list", help="List stored snapshots.")
    list_cmd.add_argument(
        "--storage",
        metavar="PATH",
        help="Storage root (default: $XDG_DATA_HOME/linux-state).",
    )
    list_cmd.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show per-snapshot file presence.",
    )
    list_cmd.set_defaults(func=cmd_list)

    plan_cmd = sub.add_parser(
        "plan",
        help="Dry-run: plan a restore from a snapshot (no changes made).",
    )
    plan_cmd.add_argument("snapshot", metavar="SNAPSHOT_ID", help="Snapshot to restore.")
    plan_cmd.add_argument(
        "--root",
        default=str(Path.home()),
        help="Target directory; must match the snapshot root.",
    )
    plan_cmd.add_argument(
        "--profile",
        metavar="NAME",
        help="Restrict the plan to a profile (default: all restorable categories).",
    )
    plan_cmd.add_argument(
        "--profiles-dir",
        metavar="DIR",
        help="Profiles directory (default: $XDG_CONFIG_HOME/linux-state/profiles).",
    )
    plan_cmd.add_argument(
        "--storage",
        metavar="PATH",
        help="Storage root (default: $XDG_DATA_HOME/linux-state).",
    )
    plan_cmd.set_defaults(func=cmd_plan)

    restore_cmd = sub.add_parser(
        "restore",
        help="Execute a restore plan from a snapshot (requires --approve).",
    )
    restore_cmd.add_argument("snapshot", metavar="SNAPSHOT_ID")
    restore_cmd.add_argument("--root", default=str(Path.home()),
                             help="Target directory; must match the snapshot root.")
    restore_cmd.add_argument("--profile", metavar="NAME",
                             help="Restrict the restore to a profile.")
    restore_cmd.add_argument("--profiles-dir", metavar="DIR",
                             help="Profiles directory override.")
    restore_cmd.add_argument("--storage", metavar="PATH",
                             help="Storage root (default: $XDG_DATA_HOME/linux-state).")
    restore_cmd.add_argument(
        "--conflict",
        choices=("skip", "replace"),
        default="skip",
        help="Policy for conflicting files (default: skip).",
    )
    restore_cmd.add_argument(
        "--approve",
        action="store_true",
        help="Explicitly approve execution. Without this flag nothing is modified.",
    )
    restore_cmd.set_defaults(func=cmd_restore)

    rollback_cmd = sub.add_parser(
        "rollback",
        help="Undo a restore transaction, restoring the previous state.",
    )
    rollback_cmd.add_argument(
        "--transaction",
        metavar="ID",
        help="Transaction to undo (default: the most recent one).",
    )
    rollback_cmd.add_argument("--storage", metavar="PATH",
                              help="Storage root (default: $XDG_DATA_HOME/linux-state).")
    rollback_cmd.add_argument(
        "--approve",
        action="store_true",
        help="Explicitly approve. Without this flag nothing is modified.",
    )
    rollback_cmd.set_defaults(func=cmd_rollback)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
