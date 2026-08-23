# Project Status

## Objective

Build `linux-state`, a cross-distribution CLI that discovers, classifies,
snapshots and selectively restores user state safely
(plan → preview → approve → backup → apply → verify → rollback).

## Current Phase

MVP-01 — Discovery + Manifest

## Implementation Status

| Component    | Status      |
| ------------ | ----------- |
| Discovery    | IN PROGRESS |
| Manifest     | PENDING     |
| Snapshot     | Not started |
| Classification | Not started |
| Profiles     | Not started |
| Restore plan | Not started |
| Restore      | Not started |
| Verification | Not started |
| Rollback     | Not started |
| CLI          | SKELETON    |

## Last Known Good State

Milestone: none yet (project skeleton being created)

Validated:
- Nothing yet.

Tests:
- 0 passing / 0 failing

## Current Work

Task: MVP-01 — read-only discovery and deterministic manifest generation.

Completed:
- Project skeleton initialized (pyproject, package layout, git repo).

Remaining:
- discovery module (read-only traversal).
- manifest module (deterministic JSON output).
- CLI `scan` command.
- Test suite against temporary directory trees only.

Do not implement:
- Any file modification, restore, or snapshot write behavior in this milestone
  beyond writing the manifest to the storage location when explicitly requested.

## Next Step

Implement `linux_state.discovery`: streaming, read-only traversal that detects
regular files, directories, hidden entries, symlinks (never followed),
permissions, size and SHA-256 hashes.

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

- None yet.
