# ADR-003 - Restore planner and executor separation

Decision:
Restore planning must be a pure operation, separate from execution.

The planner consumes snapshot + profile + current-state discovery and produces
an inspectable plan (NEW / SAME / MODIFIED / CONFLICT / SKIPPED). The executor
performs only actions from an approved plan.

Reason:
Safety and testability (AGENTS §10). A plan that can be generated, inspected
and dry-run without side effects is the foundation of preview → approve →
apply → verify → rollback.

Status:
Accepted (not yet implemented)
