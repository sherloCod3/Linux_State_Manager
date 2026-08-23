# ADR-001 - Filesystem is the source of truth

Decision:
The tool never reorganizes the user's filesystem. State is described through
manifests, metadata and snapshots stored in a separate storage location
(`$XDG_DATA_HOME/linux-state` by default).

Reason:
The project manages state through metadata rather than physically moving user
files (SPEC §2). Discovery is read-only; snapshots copy content into the tool's
own storage, leaving original paths and structure untouched.

Status:
Accepted
