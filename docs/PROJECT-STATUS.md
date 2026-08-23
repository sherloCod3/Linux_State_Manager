# Project Status

## Objective

Build `linux-state`, a cross-distribution CLI that discovers, classifies,
snapshots and selectively restores user state safely
(plan → preview → approve → backup → apply → verify → rollback).

## Current Phase

MVP-09 — Compression + Retention (COMPLETE, validated)
Next phase: post-MVP backlog (deferred features per SPEC §36 require explicit
user request).

## Implementation Status

| Component    | Status      |
| ------------ | ----------- |
| Discovery    | Validated   |
| Manifest     | Validated   |
| Classification | Validated |
| Profiles     | Validated   |
| Storage      | Validated   |
| Snapshot     | Validated   |
| Snapshot compression (gzip/zstd) | Validated |
| Retention (--keep) | Validated |
| Restore plan | Validated   |
| Restore      | Validated   |
| Verification | Validated   |
| Rollback     | Validated   |
| CLI          | Validated   |

## Last Known Good State

Milestone:
MVP-09 - Snapshot compression and opt-in retention

Validated:
- Snapshots store regular files individually compressed; gzip is the
  default, zstd optional behind an explicit availability check (Python
  3.14+ stdlib `compression.zstd`); requesting zstd where unavailable is
  an explicit error, never a silent fallback.
- Algorithm recorded in snapshot metadata; manifest paths stay logical;
  pre-compression legacy snapshots remain restorable ('none' reader).
- Executor decompresses on restore and still verifies hashes before and
  after writing; modes applied from manifest after decompression.
- verify_snapshot hashes decompressed content and detects tampering.
- Retention: `--keep N` prunes oldest beyond newest N after creation,
  reports removed IDs, never touches transactions/; without the flag
  nothing is ever deleted.
- End-to-end CLI validated: gzip roundtrip with mode preservation,
  zstd snapshot creation + metadata, retention pruning to keep=2.

Tests:
- 168 passing
- 0 failing

Last validation:
2026-08-23

## Current Work

Task: none active — MVP-09 (compression + retention) complete.

Do not implement without an explicit request:
- GUI, cloud storage, incremental snapshots/dedup/encryption,
  automatic package installation, config merging, interactive prompts,
  ACL/xattr preservation, distribution migration, declarative config file.

## Next Step

Await project owner's choice of next milestone. Remaining deferred
candidates: incremental snapshots/deduplication, ACL/xattr support,
declarative config file, additional classification rules/profiles.

## Architectural Decisions

See `docs/adr/`:

- ADR-001 — Filesystem is the source of truth (no reorganization).
- ADR-002 — Python 3 stdlib-first; PyYAML only external MVP dependency.
- ADR-003 — Restore planner/executor separation (IMPLEMENTED, MVP-05/06).
- ADR-004 — Rules bundled inside the package; user dirs override by precedence.

## Known Limitations

- ACLs / extended attributes are not yet captured (Python stdlib support is
  partial); flagged as best-effort for later milestones.
- Ownership (uid/gid) is recorded but never restored; restored files belong
  to the current user.
- Conflict resolution offers skip/replace flags; interactive prompts and
  merge are not implemented.
- zstd snapshots require Python 3.14+ on both capture and restore machines.

## Tests Executed

- 168 pytest tests — all passing (2026-08-23).
- End-to-end CLI: gzip snapshot → mutate → restore (Verification PASS,
  mode 0600 preserved); --keep 2 pruned 4 snapshots down to 2; zstd
  snapshot created and verified on Python 3.14.
