# Project Status

## Objective

Build `linux-state`, a cross-distribution CLI that discovers, classifies,
snapshots and selectively restores user state safely
(plan → preview → approve → backup → apply → verify → rollback).

## Current Phase

MVP-02 — Snapshot + Storage (COMPLETE, validated)
Next phase: MVP-03 — Classification + Rules

## Implementation Status

| Component    | Status      |
| ------------ | ----------- |
| Discovery    | Validated   |
| Manifest     | Validated   |
| CLI (scan)   | Validated   |
| Storage      | Validated   |
| Snapshot     | Validated   |
| CLI (snapshot, list) | Validated |
| Classification | Not started |
| Profiles     | Not started |
| Restore plan | Not started |
| Restore      | Not started |
| Verification | Not started |
| Rollback     | Not started |

## Last Known Good State

Milestone:
MVP-02 - Snapshot and Storage

Validated:
- Full snapshots created under `$XDG_DATA_HOME/linux-state/snapshots/<id>/`.
- Snapshot layout: manifest.json, metadata.json, data/.
- Atomic creation: failures leave no partial snapshot (staging + rename).
- Source tree provably unmodified after snapshot.
- Modes preserved (e.g. 0600); symlinks recreated as symlinks, including
  broken ones; directory symlinks never traversed.
- Metadata: timestamp, hostname, distribution, kernel, architecture, user,
  tool version; no file contents or secrets included.
- verify_snapshot re-hashes stored data and detects tampering.
- `linux-state snapshot` and `linux-state list` CLI validated end-to-end.

Tests:
- 51 passing
- 0 failing

Last validation:
2026-08-23

## Current Work

Task: none active — MVP-02 complete.

Next task: MVP-03 — Classification + Rules.

Do not implement:
- Restore planning or any file replacement (MVP-05/06).
- Incremental snapshots, deduplication, encryption (deferred, SPEC §12).
- Secret-content detection heuristics (AGENTS §15).

## Next Step

Implement `linux_state.classification`: data-driven YAML rules
(`rules/default.yaml`, `rules/desktop/*.yaml`, `rules/applications/*.yaml`)
with priority ordering (user > application > DE > system > XDG > path >
unknown), explainable results (rule that matched), and conservative defaults
(cache/generated → never restore; unknown → review).

## Architectural Decisions

See `docs/adr/`:

- ADR-001 — Filesystem is the source of truth (no reorganization).
- ADR-002 — Python 3 stdlib-first; PyYAML only external MVP dependency.
- ADR-003 — Restore planner/executor separation (accepted, not yet built).

## Known Limitations

- ACLs / extended attributes are not yet captured (Python stdlib support is
  partial); flagged as best-effort for later milestones.

## Tests Executed

- 51 pytest tests (discovery, manifest, snapshot, storage, CLI) — all passing
  (2026-08-23).
- End-to-end CLI runs against constructed temp trees: scan, snapshot, list;
  layout, mode/symlink preservation and tampering detection verified.
