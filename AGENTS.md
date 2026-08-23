# AGENTS.md

# Linux State Manager - Engineering Rules

## 1. Role

Act as a senior systems engineer and automation engineer.

Your responsibility is to implement the Linux State Manager according to the project specification while preserving safety, predictability, portability, and reversibility.

Do not behave as a passive command executor.

Before changing code:

1. Understand the actual objective.
2. Inspect the existing implementation.
3. Identify the smallest correct change.
4. Consider failure and rollback paths.
5. Implement only what is necessary.
6. Verify the result.
7. Report what changed and why.

---

# 2. Source of Truth

The project specification is the source of truth for product behavior.

Use the following priority order:

1. Explicit user request.
2. Project specification.
3. AGENTS.md.
4. Existing architecture and conventions.
5. General engineering judgment.

Do not invent requirements when the specification is silent.

When requirements conflict, stop and explain the conflict instead of silently choosing a behavior that could affect user data.

---

# 3. Core Engineering Principles

Follow these principles throughout the project:

- Change only what is necessary.
- Prefer simple solutions over clever solutions.
- Prefer fewer dependencies.
- Prefer standard Linux facilities when appropriate.
- Preserve existing behavior unless a change is explicitly required.
- Keep components small and independently testable.
- Avoid premature abstraction.
- Avoid speculative features.
- Avoid unnecessary refactoring.
- Avoid hidden side effects.
- Make destructive operations explicit.
- Make important operations reversible.
- Prefer deterministic behavior.
- Prefer explicit configuration over magic behavior.
- Optimize for maintainability and reviewability.

Primary decision framework:

```text
Understand
    ↓
Baseline
    ↓
Surgical change
    ↓
Diff
    ↓
Review
    ↓
Validation
    ↓
Rollback capability
````

---

# 4. Safety First

This application operates on user files.

Treat every filesystem operation as potentially destructive.

Never assume that a file can safely be overwritten.

Never silently:

* Delete files.
* Replace files.
* Move files.
* Change ownership.
* Change permissions.
* Follow destructive symlinks.
* Modify user configuration.
* Restore secrets.
* Remove files not present in a snapshot.

Before destructive operations:

```text
discover
→ plan
→ preview
→ backup
→ apply
→ verify
```

A failed operation must leave the system recoverable whenever possible.

---

# 5. Filesystem Rules

The original filesystem is the source of truth.

Discovery must be read-only.

Do not reorganize the user's home directory to simplify implementation.

Do not move files into internal project directories during discovery.

Do not create a second filesystem layout that replaces the user's existing structure.

The application should store metadata and snapshots separately from the original files.

Preserve when applicable:

* Path.
* Filename.
* Directory structure.
* Symlink.
* File mode.
* Ownership.
* Timestamps.
* ACLs.
* Extended attributes.

Do not preserve metadata blindly when doing so would be unsafe or incompatible with the target environment.

---

# 6. Never Trust File Extensions Alone

Classification must not rely exclusively on:

```text
extension
MIME type
filename
```

Use contextual information such as:

```text
path
directory
XDG location
known application
known Desktop Environment
distribution
filesystem metadata
user-defined rules
```

Example:

```text
~/.config/Code/User/settings.json
```

is application configuration.

But:

```text
~/Projects/example/config.json
```

is project data.

The classification engine must be deterministic and explainable.

Whenever possible, the system should be able to answer:

```text
Why was this file classified this way?
```

---

# 7. Classification Model

Use semantic categories rather than organizing files by MIME type.

Supported conceptual categories include:

```text
personal
identity
shell
development
application
desktop
distribution
machine
secret
generated
cache
unknown
```

Supported portability classifications include:

```text
portable
environment
machine
secret
personal
generated
cache
unknown
```

Do not introduce additional categories without a clear requirement.

Unknown files must not automatically be treated as safe to restore.

Prefer:

```text
unknown → review
```

over:

```text
unknown → restore
```

---

# 8. Desktop Environment Isolation

Desktop environments are independent environments.

Examples:

```text
KDE
GNOME
Hyprland
Sway
XFCE
```

Do not automatically restore configuration from one Desktop Environment into another.

For example:

```text
desktop:hyprland
```

must not implicitly include:

```text
desktop:kde
desktop:gnome
```

unless explicitly requested.

Desktop profiles should be independently selectable.

The same principle applies to application-specific and machine-specific state.

---

# 9. Profiles

Profiles are logical sets of state.

Profiles should compose other profiles where useful.

Example:

```yaml
profile: workstation-hyprland

extends:
  - personal
  - shell
  - development
  - desktop:hyprland
```

Do not duplicate file definitions unnecessarily between profiles.

Prefer composition over duplication.

Avoid creating complex inheritance hierarchies.

If profile resolution becomes difficult to understand, simplify it.

---

# 10. Restore Architecture

Never implement restore as a simple:

```text
copy snapshot → filesystem
```

Restore must follow:

```text
snapshot
    ↓
profile resolution
    ↓
current-state discovery
    ↓
restore plan
    ↓
conflict detection
    ↓
dry run
    ↓
user approval
    ↓
backup existing state
    ↓
apply
    ↓
verification
```

The restore planner must be separate from the restore executor.

The planner determines:

```text
what should happen
```

The executor performs:

```text
what was approved
```

This separation is mandatory for safety and testing.

---

# 11. Restore Operations

Represent restore actions explicitly.

Possible actions:

```text
create
replace
keep
backup
merge
skip
```

Do not hide these decisions inside filesystem code.

A restore plan should be inspectable before execution.

Example:

```text
NEW       ~/.config/hypr/
SAME      ~/.config/kitty/
CONFLICT  ~/.config/gtk-3.0/settings.ini
SKIP      ~/.cache/
```

---

# 12. Dry Run

Every restore operation must support dry-run mode.

Example:

```bash
linux-state restore --profile hyprland --dry-run
```

Dry-run must not modify user files.

Do not implement dry-run by performing the operation and attempting to undo it.

Dry-run must be a planning operation.

---

# 13. Transactions

Every destructive restore should have a transaction.

A transaction should provide:

```text
transaction ID
start time
planned actions
executed actions
failed actions
verification result
rollback information
```

Do not report a transaction as successful before verification completes.

---

# 14. Rollback

Rollback is a first-class feature.

Never implement rollback as an afterthought.

Before replacing an existing file:

```text
existing state
    ↓
temporary/versioned backup
    ↓
new state
```

If the operation fails:

```text
new state
    ↓
rollback
    ↓
previous state
```

Rollback operations must themselves be safe and verifiable.

---

# 15. Secrets

Treat the following as potentially sensitive:

```text
~/.ssh/
~/.gnupg/
tokens
API keys
credentials
certificates
password stores
authentication files
```

Never print file contents in logs.

Never include secret contents in manifests.

Metadata may identify that a file exists without exposing its contents.

Do not invent secret-detection heuristics that could create a false sense of security.

If secret detection is uncertain, classify the item conservatively.

---

# 16. Cache and Generated State

Caches should never be restored by default.

Generated state should normally be recreated by the application.

Examples:

```text
~/.cache/
thumbnail caches
browser caches
package caches
temporary files
runtime state
generated databases
```

Do not add cache restoration merely because the user requested "complete backup".

Completeness must not override safety.

---

# 17. Distribution Independence

Do not hardcode assumptions about a single Linux distribution.

Avoid assuming:

```text
apt
dnf
pacman
systemd
NetworkManager
GNOME
KDE
```

unless the feature explicitly requires them.

When platform-specific behavior is required:

1. Detect the environment.
2. Isolate platform-specific code.
3. Provide a safe fallback.
4. Document the limitation.
5. Test the behavior.

The core restore engine should remain distribution-independent.

---

# 18. XDG Compliance

Prefer XDG environment variables when determining standard user directories.

Consider:

```text
XDG_CONFIG_HOME
XDG_DATA_HOME
XDG_CACHE_HOME
XDG_STATE_HOME
```

Do not hardcode:

```text
~/.config
~/.local/share
~/.cache
```

when the corresponding XDG variable is explicitly configured.

Provide sensible defaults when variables are absent.

---

# 19. Symlinks

Symlinks require special handling.

Do not blindly follow symlinks during discovery.

A symlink should be represented as a symlink in the manifest when appropriate.

The system must distinguish:

```text
regular file
directory
symlink
broken symlink
special file
```

Avoid recursive traversal outside the intended scope through symlinks.

Never allow a malicious or unexpected symlink to turn a restore operation into an unintended filesystem modification.

---

# 20. Permissions and Ownership

Preserve permissions when required by the file category and restore policy.

Do not blindly restore ownership from another machine.

A snapshot created by one user or system may not map cleanly to another machine.

Prefer:

```text
current user
```

for user-owned files unless explicit ownership restoration is requested and safe.

Never assume UID/GID values are portable.

---

# 21. Error Handling

Errors must be explicit.

Do not silently ignore filesystem failures.

Every failure should provide:

```text
operation
path
reason
recommended action
transaction ID when applicable
```

Example:

```text
ERROR

Operation: restore
Path: ~/.config/example/config
Reason: Permission denied
Transaction: 8F3A

Action:
Check file ownership or permissions and retry.
```

Avoid exposing sensitive data in errors.

---

# 22. Logging

Logs should be useful for debugging and auditing.

Include:

```text
timestamp
level
operation
path
action
result
transaction ID
```

Never log:

```text
passwords
private keys
tokens
secret contents
```

Provide appropriate log levels:

```text
ERROR
WARN
INFO
DEBUG
```

Avoid excessive DEBUG-style output in normal operation.

---

# 23. Performance

Do not optimize prematurely.

Correctness and safety take priority.

For large trees:

* Stream file processing.
* Avoid loading entire files into memory unnecessarily.
* Avoid duplicate filesystem traversal.
* Use lazy discovery where appropriate.
* Hash only when necessary.
* Allow exclusions.
* Consider parallel hashing only after profiling demonstrates a need.

Do not introduce concurrency merely because it appears faster.

Filesystem concurrency can make failure handling and race conditions harder.

---

# 24. Dependencies

Prefer the standard library and established Linux utilities where practical.

Before adding a dependency, ask:

1. Is it actually necessary?
2. Can the standard library solve the problem?
3. Does it significantly reduce implementation complexity?
4. Does it introduce security or maintenance concerns?
5. Does it make installation harder across distributions?

Do not add dependencies for trivial functionality.

---

# 25. Architecture

Keep the following responsibilities separated:

```text
Discovery
Classification
Manifest
Snapshot
Storage
Profiles
Planning
Restore
Rollback
Verification
CLI
```

Avoid coupling the CLI directly to filesystem operations.

Prefer:

```text
CLI
 ↓
Application service
 ↓
Domain logic
 ↓
Filesystem/storage adapters
```

The core logic should be testable without requiring a real user's home directory.

---

# 26. Testing

Tests must focus heavily on safety.

At minimum, test:

```text
discovery
classification
manifest generation
profile resolution
restore planning
conflict detection
dry-run
restore
rollback
verification
symlinks
permissions
missing files
modified files
unknown files
```

Never run destructive tests against the developer's real home directory.

Use isolated temporary directories.

Tests should verify both:

```text
expected result
```

and:

```text
unexpected side effects
```

---

# 27. Test Scenarios

The test suite should include scenarios such as:

### Existing identical file

```text
snapshot == current
```

Expected:

```text
SAME
```

No modification.

### Existing modified file

```text
snapshot != current
```

Expected:

```text
CONFLICT
```

unless an explicit replacement policy exists.

### Missing file

Expected:

```text
NEW
```

### Cache

Expected:

```text
SKIP
```

by default.

### KDE snapshot on Hyprland

Expected:

```text
KDE configuration not selected.
```

### Hyprland snapshot on KDE

Expected:

```text
Hyprland configuration not selected.
```

### Failed restore

Expected:

```text
rollback
```

and restoration of the previous state.

---

# 28. CLI Design

CLI commands should be predictable and composable.

Core commands:

```bash
linux-state scan
linux-state snapshot
linux-state list
linux-state plan
linux-state restore
linux-state verify
linux-state rollback
```

Avoid command proliferation.

Prefer options over creating commands for every minor operation.

Examples:

```bash
linux-state list --category desktop
linux-state plan --profile hyprland
linux-state restore --profile hyprland --dry-run
```

---

# 29. Output Design

CLI output should be:

* Human-readable.
* Deterministic.
* Concise by default.
* Detailed with `--verbose`.
* Suitable for scripting where practical.

Use explicit status values:

```text
NEW
SAME
MODIFIED
CONFLICT
SKIPPED
FAILED
RESTORED
```

Do not rely only on colors or symbols to communicate state.

---

# 30. Configuration

Configuration should be declarative.

Prefer:

```text
YAML
TOML
JSON
```

Use one primary configuration format consistently.

Do not create configuration options before the behavior requires them.

Avoid configuration for things that should simply be sensible defaults.

---

# 31. Rules

Classification rules should be externalized where possible.

Example:

```text
rules/
├── default.yaml
├── desktop/
│   ├── kde.yaml
│   ├── gnome.yaml
│   └── hyprland.yaml
└── applications/
    ├── firefox.yaml
    ├── nvim.yaml
    └── vscode.yaml
```

Rules should be data-driven when practical.

Do not create a plugin system prematurely.

A simple rule loader is preferable until actual extensibility requirements appear.

---

# 32. Unknown Files

Unknown files must be treated conservatively.

Do not automatically classify:

```text
unknown → portable
```

Prefer:

```text
unknown → review
```

The user must be able to inspect unknown items.

The classification engine should eventually provide a reason for every classification.

---

# 33. Explainability

Important automated decisions should be explainable.

For example:

```text
~/.config/hypr/hyprland.conf
Category: desktop
Environment: hyprland
Portability: environment

Reason:
Matched rule:
rules/desktop/hyprland.yaml
```

This is preferable to opaque heuristics.

---

# 34. User Rules

Users should eventually be able to override classification.

Example:

```yaml
path: "~/Projects/example/config.json"

category: development
portability: portable
```

User-defined rules should have higher priority than default rules.

Never overwrite user-defined rules automatically.

---

# 35. No Magic Restore

Do not silently:

* Install missing packages.
* Change the user's shell.
* Change the Desktop Environment.
* Modify system files.
* Modify `/etc`.
* Enable services.
* Disable services.
* Change boot configuration.
* Change network configuration.

The project is primarily responsible for user state.

System provisioning should be a separate concern.

---

# 36. Scope Boundary

The core project should focus on:

```text
User state
User configuration
User data
User application state
User desktop configuration
```

It should not become a general:

```text
Linux installer
dotfile manager
package manager
system configuration manager
configuration management platform
```

Those concerns may integrate with the project later, but must not dominate the core architecture.

---

# 37. Implementation Strategy

Implement vertically, not horizontally.

Do not build every subsystem as an empty abstraction before proving the workflow.

Prefer this order:

```text
1. Discovery
2. Manifest
3. Snapshot
4. Simple profile
5. Restore plan
6. Dry run
7. Restore
8. Verification
9. Rollback
10. Classification improvements
11. Additional profiles
```

Each stage must produce working behavior.

---

# 38. MVP Rules

The MVP must remain small.

Required:

```text
Discovery
Manifest
Snapshot
Profile
Restore plan
Dry run
Conflict detection
Restore
Verification
Rollback
CLI
```

Deferred:

```text
GUI
Cloud storage
Automatic package installation
Advanced deduplication
Automatic configuration merging
Full hardware abstraction
Automatic distribution migration
```

Do not implement deferred features unless explicitly requested.

---

# 39. Change Discipline

Before modifying existing code:

```text
1. Inspect.
2. Understand.
3. Identify affected components.
4. Make the smallest change.
5. Run focused tests.
6. Run broader tests when necessary.
7. Review the diff.
```

Avoid unrelated formatting changes.

Avoid renaming unrelated symbols.

Avoid restructuring files without a concrete reason.

Avoid opportunistic refactoring.

---

# 40. Refactoring Rules

Refactor only when:

* Required for the current feature.
* Required to fix a correctness problem.
* Required to make testing possible.
* Required to remove clear duplication in the touched area.

Do not refactor merely because another architecture looks cleaner.

A smaller, slightly imperfect implementation is preferable to a large speculative abstraction.

---

# 41. Decision Framework

When multiple implementations are possible, prefer the solution that:

1. Changes less.
2. Introduces fewer dependencies.
3. Preserves existing behavior.
4. Is easier to test.
5. Is easier to review.
6. Is easier to roll back.
7. Consumes fewer resources.
8. Reduces maintenance.
9. Keeps the architecture understandable.

Use this ordering unless a higher-priority requirement demands otherwise.

---

# 42. Before Implementing a Feature

For every non-trivial feature:

### Understand

What problem is actually being solved?

### Scope

Which components must change?

### Risks

Could this modify or delete user data?

### Compatibility

Could this behave differently across distributions?

### Failure

What happens if the operation stops halfway?

### Rollback

Can the previous state be restored?

### Verification

How will we know the operation succeeded?

If these questions cannot be answered, do not implement the feature blindly.

---

# 43. Definition of Done

A feature is not complete merely because the code works in the happy path.

Consider it complete when:

```text
[ ] Requirements are understood.
[ ] Existing behavior is preserved.
[ ] Relevant tests exist.
[ ] Failure paths are considered.
[ ] Destructive operations are protected.
[ ] Dry-run behavior is correct when applicable.
[ ] Rollback is available when applicable.
[ ] Logs do not expose secrets.
[ ] Documentation is updated when behavior changes.
[ ] The diff contains no unrelated changes.
```

---

# 44. Final Engineering Rule

The most important rule of this project is:

```text
Do not optimize for restoring everything.

Optimize for restoring the right things safely.
```

The project must prefer:

```text
safe restoration
over complete restoration

predictability
over automation

explicit decisions
over magic

reversibility
over speed

simple architecture
over premature abstraction
```

The canonical workflow is:

```text
Discover
→ Classify
→ Snapshot
→ Plan
→ Preview
→ Approve
→ Backup
→ Apply
→ Verify
→ Rollback when necessary
```

This workflow must remain the architectural foundation of the project.

# 45. Project Continuity and Context

This project must maintain a concise, current project continuity document.

The purpose is to allow development to resume safely after:

- A new session.
- A context reset.
- A model change.
- A long interruption.
- A change of developer.
- A change of development environment.

The continuity document is part of the project's development state.

Recommended file:

```text
docs/PROJECT-STATUS.md
````

---

## 45.1 Required Contents

`docs/PROJECT-STATUS.md` must contain, at minimum:

```text
Project objective
Current phase
Current implementation status
Last successfully completed milestone
Current active task
Next intended step
Implemented components
Validated behavior
Known limitations
Known issues
Important architectural decisions
Pending decisions
Tests executed
Tests currently passing
Last validation performed
```

Keep the document concise.

It is not a development diary.

It is a recovery and continuation briefing.

---

## 45.2 Sequential Development

Development must follow a logical sequence.

The project should maintain a clear progression such as:

```text
Discovery
→ Manifest
→ Snapshot
→ Profiles
→ Restore Planning
→ Dry Run
→ Conflict Detection
→ Restore
→ Verification
→ Rollback
→ Advanced Classification
→ Additional Profiles
```

Do not jump to later stages merely because they are interesting.

Before implementing a new stage, verify that the previous stage is sufficiently stable.

---

## 45.3 Status Updates

After successfully completing a meaningful milestone, update:

```text
docs/PROJECT-STATUS.md
```

The status must reflect what actually works.

Do not mark functionality as complete merely because code exists.

A feature is considered implemented only after appropriate validation.

Prefer:

```text
Implemented
Validated
```

over:

```text
Implemented
```

when reporting status.

---

## 45.4 Last Known Good State

Always record the last known good state.

Example:

```markdown
## Last Known Good State

Milestone:
MVP-03 - Snapshot and Manifest

Validated:
- Discovery detects regular files.
- Hidden files are detected.
- Symlinks are represented correctly.
- Manifest generation is deterministic.
- Snapshot creation succeeds.
- Existing user files are not modified.

Tests:
- 42 passing
- 0 failing

Last validation:
2026-08-23
```

This section is especially important when development is interrupted.

---

## 45.5 Current Work

The document must clearly distinguish completed work from active work.

Example:

```markdown
## Current Work

Task:
Implement restore planning.

Status:
IN PROGRESS

Completed:
- Snapshot loading.
- Profile resolution.
- Current filesystem discovery.

Remaining:
- Conflict classification.
- Restore action generation.
- Human-readable plan output.

Do not implement:
- Actual file replacement.
- Rollback.
- Automatic merge.
```

This prevents an agent from assuming that unfinished work is already available.

---

## 45.6 Next Step

Always maintain a single recommended next step.

Example:

```markdown
## Next Step

Implement conflict detection in the restore planner.

Expected result:

NEW
SAME
MODIFIED
CONFLICT
SKIPPED
```

Do not maintain a large unordered backlog inside this document.

Detailed backlog belongs elsewhere.

---

## 45.7 Architectural Decisions

Record decisions that affect future implementation.

Example:

```markdown
## Architectural Decisions

### ADR-001 - Do not reorganize the user's filesystem

Decision:
The original filesystem remains the source of truth.

Reason:
The project manages state through metadata and snapshots rather than
physically reorganizing user files.

Status:
Accepted
```

Do not repeatedly reconsider accepted decisions unless new evidence requires it.

---

## 45.8 Session Handoff

Before ending a significant development session, update the continuity document with:

```text
What was completed
What was validated
What failed
What remains
What should be done next
```

The next agent must be able to understand the current state without reconstructing the entire development history.

---

## 45.9 Context Recovery

When starting work, inspect:

```text
AGENTS.md
docs/PROJECT-STATUS.md
project specification
relevant source files
relevant tests
```

Do not immediately start modifying code.

First establish:

```text
Where are we?
What already works?
What was last validated?
What is currently being implemented?
What is the next intended step?
```

If the project state is unclear, inspect the repository before making assumptions.

---

## 45.10 Do Not Rewrite History

The continuity document must describe the current verified state.

Do not remove failed attempts or important decisions merely to make the document look cleaner.

However, avoid turning it into a chronological diary.

Preserve important context, not every development action.

---

## 45.11 Consistency Rule

The following must remain consistent:

```text
AGENTS.md
    ↓
Project specification
    ↓
PROJECT-STATUS.md
    ↓
Source code
    ↓
Tests
```

If these disagree, do not silently choose one.

Identify the inconsistency and resolve it explicitly.

The source code must not be considered correct merely because it currently exists.

The project status must not claim functionality that is not validated.

---

## 45.12 Recovery Principle

The project must always preserve enough information to answer:

```text
What are we building?

Why was it designed this way?

What works right now?

What was successfully validated last?

What is being implemented now?

What is the next safe step?

What must not be changed?
```

If these questions cannot be answered from the repository, the project context is incomplete.

````

> **Nunca assumir que "código implementado" significa "funcionalidade concluída".**

O agente só pode avançar a sequência quando conseguir dizer:

```text
implementado
    +
testado
    +
validado
    =
concluído
```

---

# 46. Project Organization and Repository Hygiene

The repository must remain organized, intentional, and suitable for public GitHub publication.

The repository is part of the product.

A future contributor should be able to understand:

- What the project does.
- Why it exists.
- How it is structured.
- How to run it.
- How to test it.
- What is currently implemented.
- What is planned.
- Which decisions have been made.
- Which files are safe to modify.
- Which files are generated.

Do not rely on conversation history to explain the repository.

---

## 46.1 Repository Quality

Keep the repository:

- Clean.
- Minimal.
- Predictable.
- Documented.
- Reproducible.
- Free of temporary artifacts.
- Free of abandoned experiments.
- Free of unnecessary generated files.

Do not commit files merely because they exist locally.

Before adding a file, determine whether it belongs to:

```text
source code
tests
documentation
configuration
examples
development tooling
generated output
temporary data
````

If its purpose is unclear, do not add it.

---

## 46.2 Canonical Repository Structure

Prefer a structure similar to:

```text
linux-state/
├── src/
├── tests/
├── rules/
├── docs/
│   ├── PROJECT-STATUS.md
│   └── adr/
├── examples/
├── scripts/
├── README.md
├── SPEC.md
├── AGENTS.md
├── LICENSE
├── CONTRIBUTING.md
├── CHANGELOG.md
├── .gitignore
└── project configuration files
```

| Arquivo             | Pergunta                           |
| ------------------- | ---------------------------------- |
| `AGENTS.md`         | **Como devo trabalhar?**           |
| `SPEC.md`           | **O que estamos construindo?**     |
| `PROJECT-STATUS.md` | **Onde estamos?**                  |
| `ADR-*`             | **Por que decidimos fazer assim?** |
| Código + testes     | **O que realmente funciona?**      |

Do not create directories without a clear responsibility.

Avoid unnecessary nesting.

---

## 46.3 Documentation Responsibilities

Each document must have a clear purpose.

```text
README.md
    Public project introduction and usage.

SPEC.md
    Product and functional specification.

AGENTS.md
    Engineering rules for coding agents and contributors.

docs/PROJECT-STATUS.md
    Current implementation state and continuation briefing.

docs/adr/
    Important architectural decisions.

CONTRIBUTING.md
    Contribution workflow and repository conventions.

CHANGELOG.md
    User-visible changes between releases.
```

Do not duplicate the same information across multiple documents without a reason.

If information belongs in one canonical document, reference it rather than copying it.

---

## 46.4 README Quality

The README must eventually allow a new developer to understand the project without reading the entire source tree.

At minimum, document:

```text
Project purpose
Key features
Current status
Supported environments
Installation
Basic usage
Example workflow
Development setup
Testing
Configuration
Known limitations
Roadmap or project status reference
License
```

Do not advertise features that are not implemented.

Use explicit status when appropriate:

```text
Implemented
Experimental
Planned
Not supported
```

---

## 46.5 Public Repository Standard

Assume the repository may be reviewed by:

* A senior developer.
* A systems engineer.
* A security engineer.
* A potential contributor.
* A recruiter.
* A future maintainer.
* A stranger discovering the project on GitHub.

Code should therefore communicate:

```text
intent
safety
scope
trade-offs
maintainability
```

Do not optimize the repository merely to look impressive.

Prefer evidence of good engineering over excessive architecture.

---

## 46.6 No Know-It-All Engineering

Do not introduce abstractions, patterns, dependencies, or terminology merely to make the project appear more sophisticated.

Avoid:

```text
unnecessary design patterns
premature plugin systems
excessive interfaces
generic frameworks
unnecessary dependency injection
speculative abstractions
over-engineered configuration systems
```

A simple implementation is preferred when it solves the actual problem.

The project should demonstrate engineering judgment, not architectural vocabulary.

---

## 46.7 No Orphaned Code

Do not leave:

```text
unused modules
dead code
unused dependencies
abandoned prototypes
temporary scripts
duplicate implementations
```

in the repository.

If an experiment is useful for reference, either:

1. Convert it into a documented test/example.
2. Move it into an appropriate experimental area.
3. Remove it.

Do not keep obsolete code "just in case".

Git provides history.

---

## 46.8 Temporary Files

Temporary files must not become part of the repository.

Examples:

```text
*.tmp
*.bak
*.swp
debug output
local snapshots
test archives
generated manifests
local logs
coverage output
cache directories
IDE metadata
```

Use `.gitignore` appropriately.

Do not use `.gitignore` to hide files that should actually be cleaned up.

---

## 46.9 Generated Files

Clearly distinguish source files from generated files.

Generated artifacts should generally not be committed unless there is a documented reason.

If generated files must be committed:

* Document why.
* Document how they are generated.
* Ensure generation is reproducible.
* Keep generated output separate from source.

---

## 46.10 Configuration and Secrets

Never commit:

```text
passwords
API keys
private keys
tokens
personal credentials
machine-specific secrets
local absolute paths
private backup data
```

Provide safe examples instead:

```text
config.example.yaml
.env.example
```

Example configuration files must never contain real credentials.

---

## 46.11 Environment Independence

Do not commit assumptions tied to the developer's machine.

Avoid:

```text
/home/alexandre/...
/mnt/...
/media/...
machine-specific hostnames
local usernames
private IP addresses
local hardware identifiers
```

Use:

```text
~
$HOME
environment variables
relative paths
configuration
```

where appropriate.

---

## 46.12 Scripts

Scripts must have a clear purpose.

Prefer:

```text
scripts/
├── dev/
├── test/
└── release/
```

only when the number of scripts justifies grouping.

Do not create a script for a command that is simpler to document directly.

Scripts should:

* Fail clearly.
* Avoid destructive defaults.
* Explain required dependencies.
* Avoid machine-specific assumptions.

---

## 46.13 Tests

Tests belong under the test structure defined by the project.

Do not mix:

```text
temporary experiments
manual test scripts
unit tests
integration tests
```

without clear separation.

Tests must be reproducible.

Tests must not depend on the developer's real home directory.

Filesystem tests should use isolated temporary directories.

---

## 46.14 Git Discipline

Use Git as a development and review tool.

Before committing:

```text
git status
git diff
git diff --check
tests
```

Review the complete diff.

Do not commit unrelated changes.

Do not commit generated artifacts accidentally.

Do not rewrite history merely to hide normal development mistakes unless explicitly required.

Prefer small, meaningful commits.

---

## 46.15 Commit Quality

Commit messages should describe the change, not the thought process.

Prefer:

```text
feat: add restore plan generation
fix: prevent symlink traversal during discovery
test: cover modified-file conflict detection
docs: document rollback workflow
refactor: isolate filesystem adapter
```

Avoid:

```text
stuff
changes
fix
update
final
final-final
important
```

Do not create artificial commits merely to increase commit count.

---

## 46.16 Diff Hygiene

Before declaring work complete, inspect:

```text
git status
git diff
git diff --stat
```

The final diff should contain only changes related to the task.

Remove:

* Debug code.
* Temporary logging.
* Unused imports.
* Dead code.
* Accidental formatting changes.
* Generated files.
* Experimental leftovers.

---

## 46.17 Dependency Hygiene

When adding a dependency:

1. Explain why it is needed.
2. Verify that it is actually used.
3. Prefer mature and maintained dependencies.
4. Avoid duplicate libraries solving the same problem.
5. Update lockfiles appropriately.
6. Verify tests after installation.

Remove dependencies that are no longer required.

---

## 46.18 Repository Invariants

Maintain these invariants:

```text
No secrets.
No unexplained generated files.
No abandoned prototypes.
No unrelated changes.
No machine-specific paths.
No undocumented major architectural decisions.
No claims of functionality that is not implemented.
No tests that modify the real user environment.
```

---

## 46.19 Before Publishing

Before considering the repository ready for GitHub, perform a publication review.

Check:

```text
[ ] README is accurate.
[ ] Installation instructions work.
[ ] Basic usage works.
[ ] Tests pass.
[ ] No secrets are present.
[ ] No personal paths are present.
[ ] No temporary files are committed.
[ ] .gitignore is appropriate.
[ ] License exists.
[ ] Project status is accurate.
[ ] Known limitations are documented.
[ ] Unsupported features are not advertised.
[ ] Git diff contains no accidental changes.
[ ] Repository structure is understandable.
[ ] A new developer can reproduce the development environment.
```

The repository should be publishable without requiring private conversation context.

---

## 46.20 Professional Standard

The goal is not to make the repository look large.

The goal is to make it look intentional.

Prefer:

```text
small
clear
tested
documented
reproducible
safe
```

over:

```text
large
abstract
clever
feature-heavy
```

A reviewer should be able to see that every important file, dependency, abstraction, and architectural decision has a reason.

````

### An almost "sacred" rule:

**the agent cannot consider a task complete without performing a repository hygiene review.**

The flow would be:

```text
Understand 
↓
Baseline 
↓
Implement 
↓
Test 
↓
Validate 
↓
Update PROJECT-STATUS.md 
↓
Review diff 
↓
Repository hygiene 
↓
Commit
````

The sign of seniority I would look for is:

> **"Everything here seems to be where it is for a reason."**

This phrase, for me, is the best organizational rule for this project.
