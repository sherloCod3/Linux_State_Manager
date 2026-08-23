# Project Status

## Objective

Build `linux-state`, a cross-distribution CLI that discovers, classifies,
snapshots and selectively restores user state safely
(plan → preview → approve → backup → apply → verify → rollback).

## Current Phase

MVP COMPLETE (MVP-01 … MVP-08) — all components implemented and validated.
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
| Restore plan | Validated   |
| Restore      | Validated   |
| Verification | Validated   |
| Rollback     | Validated   |
| CLI          | Validated   |

## Last Known Good State

Milestone:
MVP-08 - Documentation and publication review (MVP complete)

Validated:
- Full canonical workflow end-to-end: scan → snapshot → plan (dry run) →
  restore --approve → verification PASS → rollback --approve.
- Clean-install validation: `pip install .` into a fresh venv; `linux-state`
  runs with bundled rules resolved from package data.
- README documents only implemented commands and flags.
- CHANGELOG records the 0.1.0 MVP release.
- Publication review (AGENTS §46.19): no secrets, no personal paths, no
  temporary files, LICENSE present, status accurate.

Tests:
- 146 passing
- 0 failing

Last validation:
2026-08-23

## Current Work

Task: none active — MVP complete.

Next task: user decision on post-MVP direction.

Do not implement without an explicit request:
- GUI, cloud storage, incremental snapshots/dedup/compression/encryption,
  automatic package installation, config merging, interactive prompts,
  ACL/xattr preservation, distribution migration.

## Next Step

Await project owner's choice of next milestone. Candidate directions from
SPEC deferred list: compression (zstd), retention policy, or additional
classification rules/profiles for real-world environments.

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
