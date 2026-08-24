# Project Status

## Objective

Build `linux-state`, a cross-distribution CLI that discovers, classifies,
snapshots and selectively restores user state safely
(plan → preview → approve → backup → apply → verify → rollback).

## Current Phase

MVP-10 — Amplitude-aware snapshot + streaming manifest (COMPLETE, validated)
Previous: MVP-09 — Compression + Retention (validated 2026-08-23).

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
| Snapshot amplitude (--profile/--exclude) | Validated |
| Snapshot streaming (single-pass hash, in-place sort) | Validated |
| Restore plan | Validated   |
| Restore      | Validated   |
| Verification | Validated   |
| Rollback     | Validated   |
| CLI          | Validated   |

## Last Known Good State

Milestone:
MVP-10 - Amplitude-aware snapshot + streaming manifest

Validated:
- Vanished-file tolerance: files deleted between discovery and capture
  are SKIPPED (WARN) and excluded from manifest; permission errors still
  abort atomically; manifest written after capture so it only describes
  stored data (`snapshot.py:103-224`).
- Amplitude reduction: `snapshot --profile NAME` captures only entries
  selected by the resolved profile (reuses `classification+profiles`
  logic, so it matches `plan --profile`); `--exclude PATTERN` (repeatable,
  fnmatch with `/**` dir semantics) applied afterwards; metadata records
  `profile`/`exclude` for traceability.
- Streaming manifest: `manifest.py:write_manifest_atomic` uses
  `json.dump` streaming instead of `json.dumps` 400 MB string; snapshot
  sorts entries in-place and passes `already_sorted=True` to
  `build_manifest` to halve peak copies.
- Single-pass I/O: `discovery` without pre-hash + `compression.compress_and_hash`
  computes SHA-256 while compressing, halving reads for large trees
  (`compression.py:96`, `snapshot.py:105`).
- Compression/retention unchanged: gzip default, zstd opt-in with
  availability check; `--keep N` prunes oldest beyond newest N.
- End-to-end CLI validated: filtered snapshot (shell-only, exclude
  `.cache/**`) roundtrip; gzip mode preserved; vanished-file capture.

Tests:
- 171 passing
- 0 failing

Last validation:
2026-08-24

## Current Work

Task: none active — MVP-10 complete. Awaiting owner decision on next
milestone; avoid partition-shrink workaround (full-disk distros impasse).

Do not implement without an explicit request:
- GUI, cloud storage, incremental snapshots/dedup/encryption,
  automatic package installation, config merging, interactive prompts,
  ACL/xattr preservation, distribution migration, declarative config file.

## Next Step

Choose between:
- Incremental/dedup backend (pluggable `borg`/`restic` adapter per `storage.py`
  isolation — avoids further reimplementing storage).
- Additional classification rules/profiles (e.g. `desktop:sway`, `applications:*`).
- Dedicated storage partition guidance (`examples/` + `README` already warns
  full-disk installs impede personal-data separation; prefer
  `snapshot --profile/--exclude` over shrinking partitions).

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

- 171 pytest tests — all passing (2026-08-24).
- End-to-end CLI: gzip snapshot → mutate → restore (Verification PASS,
  mode 0600 preserved); --keep 2 pruned 4 snapshots down to 2; filtered
  snapshot (`--profile shell`, `--exclude .cache/**`) verified and
  restorable; vanished-file skip path covered; zstd creation verified on
  Python 3.14.
