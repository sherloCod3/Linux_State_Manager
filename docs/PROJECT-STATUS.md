# Project Status

## Objective

Build `linux-state`, a cross-distribution CLI that discovers, classifies,
snapshots and selectively restores user state safely
(plan → preview → approve → backup → apply → verify → rollback).

## Current Phase

MVP-06 — Restore Executor + Backup Before Replace (COMPLETE, validated)
Next phase: MVP-07 — Verification Report + Rollback Command

## Implementation Status

| Component    | Status      |
| ------------ | ----------- |
| Discovery    | Validated   |
| Manifest     | Validated   |
| CLI (scan)   | Validated   |
| Storage      | Validated   |
| Snapshot     | Validated   |
| CLI (snapshot, list) | Validated |
| Classification | Validated   |
| Profiles     | Validated   |
| Restore plan | Validated   |
| Restore      | Validated   |
| Verification | Not started |
| Rollback     | Not started |

## Last Known Good State

Milestone:
MVP-06 - Restore Executor and Backup Before Replace

Validated:
- Execution requires explicit approval; refusal changes nothing.
- Transactions recorded under storage/transactions/<id>/transaction.json
  (planned/executed/failed/status/rollback info).
- Backup-before-replace: previous file content preserved in transaction
  backup dir; symlink targets recorded for recreation.
- NEW actions create files/dirs/symlinks with snapshot modes.
- CONFLICT default policy = skip (nothing silently overwritten);
  replace only with explicit --conflict replace.
- SAME entries untouched (mtime preserved).
- Snapshot content verified against manifest hash before applying, and
  restored content verified after writing; mismatch aborts the run.
- First failure stops the run; failure recorded; no partial success
  reported as complete. Raw OSError converted to explicit ExecutionError.
- Symlink escape protection: restore target resolving outside the root is
  rejected before any write.
- CLI: `linux-state restore <id> --approve [--conflict replace]`.

Tests:
- 134 passing
- 0 failing

Last validation:
2026-08-23

## Current Work

Task: none active — MVP-06 complete.

Next task: MVP-07 — Verification Report + Rollback Command.

Do not implement:
- Automatic merge of configuration files.
- Interactive conflict prompts (explicit flags only for now).

## Next Step

Implement `linux_state.verification` (post-restore report: existence, hash,
mode, symlink checks) and `linux_state.rollback` + `linux-state rollback
[--transaction <id>]` using the transaction rollback info to restore the
pre-restore state safely.

## Architectural Decisions

See `docs/adr/`:

- ADR-001 — Filesystem is the source of truth (no reorganization).
- ADR-002 — Python 3 stdlib-first; PyYAML only external MVP dependency.
- ADR-003 — Restore planner/executor separation (accepted, not yet built).
- ADR-004 — Rules bundled inside the package; user dirs override by precedence.

## Known Limitations

- ACLs / extended attributes are not yet captured (Python stdlib support is
  partial); flagged as best-effort for later milestones.

## Tests Executed

- 134 pytest tests (discovery, manifest, snapshot, storage, classification,
  profiles, planner, executor, integration, CLI) — all passing (2026-08-23).
- End-to-end: restore without --approve refused; with approval, NEW file
  restored, SAME untouched, transaction recorded as completed.
