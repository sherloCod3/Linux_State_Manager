# Project Status

## Objective

Build `linux-state`, a cross-distribution CLI that discovers, classifies,
snapshots and selectively restores user state safely
(plan → preview → approve → backup → apply → verify → rollback).

## Current Phase

MVP-07 — Verification + Rollback (COMPLETE, validated)
Next phase: MVP-08 — Documentation polish and publication review

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
| Verification | Validated   |
| Rollback     | Validated   |

## Last Known Good State

Milestone:
MVP-07 - Verification and Rollback

Validated:
- Post-restore verification: existence, SHA-256, mode and symlink target
  checks against the manifest; report stored inside the transaction record.
- Restore is not reported complete until verification passes.
- Rollback restores pre-restore state from transaction backups: conflict
  files reverted to pre-restore content; created files removed; symlinks
  recreated from recorded targets; SAME files untouched.
- Rollback requires explicit approval; refusal changes nothing.
- Rollback writes its own completed transaction record.
- Unknown transactions fail explicitly.
- Transactions now record the restore root.
- CLI end-to-end validated: snapshot → mutate → restore --approve
  (Verification PASS) → rollback --approve (prior state recovered).

Tests:
- 146 passing
- 0 failing

Last validation:
2026-08-23

## Current Work

Task: none active — MVP-07 complete.

Next task: MVP-08 — Documentation polish and publication review.

Do not implement:
- Automatic merge of configuration files.
- Interactive conflict prompts (explicit flags only for now).

## Next Step

Final polish: accurate README usage documentation (real commands only),
CHANGELOG entry for the MVP, publication review per AGENTS §46.19.

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

## Tests Executed

- 146 pytest tests — all passing (2026-08-23).
- End-to-end CLI cycle: snapshot → mutate → restore --approve
  (Verification PASS) → rollback --approve (prior state recovered).
