# Project Status

## Objective

Build `linux-state`, a cross-distribution CLI that discovers, classifies,
snapshots and selectively restores user state safely
(plan → preview → approve → backup → apply → verify → rollback).

## Current Phase

MVP-01 — Discovery + Manifest (COMPLETE, validated)
Next phase: MVP-02 — Snapshot + Storage

## Implementation Status

| Component    | Status      |
| ------------ | ----------- |
| Discovery    | Validated   |
| Manifest     | Validated   |
| CLI (scan)   | Validated   |
| Snapshot     | Not started |
| Classification | Not started |
| Profiles     | Not started |
| Restore plan | Not started |
| Restore      | Not started |
| Verification | Not started |
| Rollback     | Not started |

## Last Known Good State

Milestone:
MVP-01 - Discovery and Manifest

Validated:
- Read-only scan detects regular files, directories, hidden/dotfiles.
- Symlinks recorded as symlinks; directory symlinks never traversed.
- Broken symlinks detected and flagged, not raised.
- Permissions captured (e.g. 0600 preserved in manifest).
- SHA-256 streaming hashing of regular files (--no-hash supported).
- Manifest generation is deterministic (byte-identical across runs).
- Manifest written atomically via temp file + rename.
- Scan provably does not modify the scanned tree (mtime/mode/inode snapshot test).
- Unreadable directories raise explicit DiscoveryError with operation/path/reason.

Tests:
- 26 passing
- 0 failing

Last validation:
2026-08-23

## Current Work

Task: none active — MVP-01 complete.

Next task: MVP-02 — Snapshot + Storage.

Do not implement:
- Any file modification or restore behavior.
- Incremental snapshots, deduplication, compression beyond zstd default choice
  (deferred per SPEC §12/§35).

## Next Step

Implement `linux_state.snapshot` + `linux_state.storage`: full snapshot layout
(`snapshots/<id>/manifest.json`, `metadata.json`, `data/`) with snapshot
metadata (timestamp, hostname, distro, kernel, user) and integrity verification,
plus the `linux-state snapshot` CLI command.

## Architectural Decisions

### ADR-001 - Filesystem is the source of truth

Decision: The tool never reorganizes the user's filesystem; state is described
via manifests/metadata stored separately.

Status: Accepted

### ADR-002 - Python 3 stdlib-first implementation

Decision: Implement in Python 3.10+ using the standard library; PyYAML is the
only external dependency for MVP.

Status: Accepted

### ADR-003 - Planner/executor separation (future restore)

Decision: Restore planning must be pure and separate from execution.

Status: Accepted (not yet implemented)

## Known Limitations

- ACLs / extended attributes are not yet captured (Python stdlib support is
  partial); flagged as best-effort for later milestones.

## Tests Executed

- 26 pytest tests (discovery, manifest, CLI) — all passing (2026-08-23).
- End-to-end CLI run against a constructed temp tree: correct counts,
  verbose listing, manifest JSON verified.
