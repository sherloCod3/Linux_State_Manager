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
from linux_state.discovery import DiscoveryError, Kind, discover
from linux_state.manifest import build_manifest, entry_to_display, write_manifest


def _print_summary(entries, root: Path, verbose: bool) -> None:
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
            print(f"  {entry.kind.value:<9} {entry_to_display(entry, home)}")


def cmd_scan(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser()
    if not root.is_dir():
        print(f"ERROR: not a directory: {root}", file=sys.stderr)
        return 1

    try:
        entries = list(discover(root, hash_files=not args.no_hash))
    except DiscoveryError as exc:
        print(
            f"ERROR\nOperation: {exc.operation}\nPath: {exc.path}\n"
            f"Reason: {exc.reason}\nAction: check permissions and retry.",
            file=sys.stderr,
        )
        return 2

    _print_summary(entries, root, args.verbose)

    if args.json:
        manifest = build_manifest(root, entries)
        write_manifest(manifest, Path(args.json))
        print(f"Manifest written: {args.json}")
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
        "-v",
        "--verbose",
        action="store_true",
        help="List every discovered entry.",
    )
    scan.set_defaults(func=cmd_scan)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
