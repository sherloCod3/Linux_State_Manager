# Project Status

## Objective

Build `linux-state`, a cross-distribution CLI that discovers, classifies,
snapshots and selectively restores user state safely
(plan → preview → approve → backup → apply → verify → rollback).

## Current Phase

MVP-04 — Profiles (COMPLETE, validated)
Next phase: MVP-05 — Restore Planner + Conflict Detection + Dry Run

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
| Restore plan | Not started |
| Restore      | Not started |
| Verification | Not started |
| Rollback     | Not started |

## Last Known Good State

Milestone:
MVP-04 - Profiles

Validated:
- YAML profiles with `extends` composition; nested extends resolved.
- Bare undefined names act as category selectors (`--profile shell` works
  without a definition file).
- Selector forms: bare category, `desktop:<env>`, `applications:<app>`.
- Circular extends detected and rejected (incl. self-reference).
- Desktop mutual exclusion: two different environments in one profile are
  rejected unless `allow_multiple_desktops: true`.
- Entry selection: hyprland profile excludes KDE state and vice versa
  (SPEC success cases 2 and 3); cache never selected unless explicitly
  requested; unknown never selected.
- CLI: `scan --profile NAME [--profiles-dir DIR]` filters output and reports
  selection counts; conflicts fail with explicit ERROR.

Tests:
- 107 passing
- 0 failing

Last validation:
2026-08-23

## Current Work

Task: none active — MVP-04 complete.

Next task: MVP-05 — Restore Planner + Conflict Detection + Dry Run.

Do not implement:
- Actual file replacement or restore execution (MVP-06).
- Rollback (MVP-07). Automatic merge.

## Next Step

Implement `linux_state.planner`: pure restore planning from a stored snapshot
manifest + resolved profile + current-state discovery, producing actions
NEW / SAME / MODIFIED / CONFLICT / SKIPPED. Add `linux-state plan --snapshot
<id> --profile <name>` as the dry-run surface (planning only; no writes).

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

- 107 pytest tests (discovery, manifest, snapshot, storage, classification,
  profiles, integration, CLI) — all passing (2026-08-23).
- End-to-end: hyprstation profile scan selects only Hyprland + shell entries
  from a mixed KDE/Hyprland tree.
