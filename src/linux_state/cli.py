"""CLI entry point.

The CLI is a thin layer: it parses arguments, calls services and prints
results. It never touches the filesystem directly.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from linux_state import __version__
from linux_state.classification import RuleSet, XdgDirs, default_rule_files, load_ruleset
from linux_state.discovery import DiscoveryError, Kind, discover
from linux_state.manifest import build_manifest, entry_to_display, write_manifest
from linux_state.snapshot import SnapshotError, create_snapshot, new_snapshot_id
from linux_state.storage import (
    default_storage_root,
    list_snapshots,
    manifest_file,
    metadata_file,
)


def _print_summary(entries, root: Path, verbose: bool, ruleset=None, xdg=None) -> None:
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
            relative = entry.path.relative_to(root)
            result = ruleset.classify(relative.as_posix(), xdg, root)
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

    _print_summary(entries, root, args.verbose, ruleset, xdg)

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

    try:
        snapshot_id = create_snapshot(
            root,
            storage_root,
            hash_files=not args.no_hash,
            classifier=ruleset,
            xdg=xdg,
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
    return 0


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
        "--rules",
        metavar="DIR",
        help="User rules directory; takes precedence over bundled defaults.",
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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
