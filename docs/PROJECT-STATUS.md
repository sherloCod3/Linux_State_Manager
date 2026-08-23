# Project Status

## Objective

Build `linux-state`, a cross-distribution CLI that discovers, classifies,
snapshots and selectively restores user state safely
(plan → preview → approve → backup → apply → verify → rollback).

## Current Phase

MVP-05 — Restore Planner + Conflict Detection + Dry Run (COMPLETE, validated)
Next phase: MVP-06 — Restore Executor + Backup Before Replace

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
| Restore      | Not started |
| Verification | Not started |
| Rollback     | Not started |

## Last Known Good State

Milestone:
MVP-05 - Restore Planner, Conflict Detection, Dry Run

Validated:
- Pure planner: compares stored snapshot vs current state; writes nothing.
- Conflict states verified: NEW (missing), SAME (identical),
  MODIFIED (mode-only change), CONFLICT (content/symlink-target/type change).
- Policies honored: restore=never → SKIPPED; secrets (review) → SKIPPED.
- Profile restriction: hyprland profile excludes KDE entries in plans.
- Snapshot root must match plan target root (mismatch rejected explicitly).
- Planning provably does not modify the tree or storage.
- CLI dry run: `linux-state plan <id> --root R` prints deterministic actions
  and summary; unknown snapshot fails with explicit ERROR.
- Snapshot manifests now carry their own id.

Tests:
- 123 passing
- 0 failing

Last validation:
2026-08-23

## Current Work

Task: none active — MVP-05 complete.

Next task: MVP-06 — Restore Executor + Backup Before Replace.

Do not implement:
- Automatic merge of configuration files.
- Rollback command (MVP-07) — but the executor must record enough
  transaction information for rollback to be built on top.

## Next Step

Implement `linux_state.executor`: execute an approved plan transactionally.
Every replace is preceded by a backup of the existing file inside the
transaction directory; failures stop the run and leave recoverable state.
Requires explicit `--approve` (no silent destructive execution).

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

- 123 pytest tests (discovery, manifest, snapshot, storage, classification,
  profiles, planner, integration, CLI) — all passing (2026-08-23).
- End-to-end dry run: snapshot → mutate tree → plan reports
  CONFLICT (modified), NEW (deleted), SAME (untouched).
