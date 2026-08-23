# ADR-002 - Python 3 stdlib-first implementation

Decision:
Implement in Python 3.10+ using the standard library. PyYAML is the only
external dependency for the MVP.

Reason:
pathlib/os/stat cover discovery needs; SHA-256 is in hashlib; JSON manifests
need no extra dependency. This keeps installation easy across distributions
(SPEC §17) and dependencies minimal (AGENTS §24).

Consequence:
ACL/xattr support is partial (stdlib limits); recorded as a known limitation
rather than solved with platform-specific dependencies prematurely.

Status:
Accepted
