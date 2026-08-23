# Project Status

## Objective

Build `linux-state`, a cross-distribution CLI that discovers, classifies,
snapshots and selectively restores user state safely
(plan → preview → approve → backup → apply → verify → rollback).

## Current Phase

MVP-03 — Classification + Rules (COMPLETE, validated)
Next phase: MVP-04 — Profiles

## Implementation Status

| Component    | Status      |
| ------------ | ----------- |
| Discovery    | Validated   |
| Manifest     | Validated   |
| CLI (scan)   | Validated   |
| Storage      | Validated   |
| Snapshot     | Validated   |
| CLI (snapshot, list) | Validated |
| Classification | Validated |
| Profiles     | Not started |
| Restore plan | Not started |
| Restore      | Not started |
| Verification | Not started |
| Rollback     | Not started |

## Last Known Good State

Milestone:
MVP-03 - Classification and Rules

Validated:
- Rule engine: ordered YAML rules, first match wins, deterministic.
- Priority: user rules directory beats bundled defaults (AGENTS §34).
- Explainability: every classification records rule id + source file.
- Conservative defaults: unknown → review (never auto-restorable).
- Cache/generated → never; secrets (ssh, gnupg) → secret/review.
- Desktop isolation: hyprland.conf → hyprland only; plasma files → kde only,
  never cross-classified into other environments.
- XDG fallback: cache/state dirs classified even without explicit rules;
  custom XDG_CACHE_HOME respected.
- Classification persisted in scan manifests and snapshot manifests.
- Invalid rules rejected explicitly (missing match key, unknown category).

Tests:
- 80 passing
- 0 failing

Last validation:
2026-08-23

## Current Work

Task: none active — MVP-03 complete.

Next task: MVP-04 — Profiles.

Do not implement:
- Restore planning or any file replacement (MVP-05/06).
- Automatic merging of configuration files.
- Secret-content detection heuristics (AGENTS §15).

## Next Step

Implement `linux_state.profiles`: YAML profiles with composition via
`extends` (e.g. `workstation-hyprland` extends personal + shell + development +
desktop:hyprland), desktop profile mutual exclusion by default, and a
`profile resolve` path usable by the future restore planner.

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

- 80 pytest tests (discovery, manifest, snapshot, storage, classification,
  integration, CLI) — all passing (2026-08-23).
- End-to-end: snapshot of mixed KDE+Hyprland+secret+cache tree; every entry
  classified correctly with DE isolation and conservative defaults.
