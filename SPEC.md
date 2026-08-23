# Linux State Manager

> Cross-distribution Linux state manager with selective, conflict-aware restoration.

## 1. Overview

The project aims to reduce the rework caused by system reinstallations, Linux distribution switches, Desktop Environment switches, and environment changes.

The tool must capture, classify, version, and restore the user's personal state without treating all files as equivalent.

The system must allow, for example:

- Restoring only personal files.
- Restoring shell configuration.
- Restoring the development environment.
- Restoring application configuration.
- Restoring KDE.
- Restoring GNOME.
- Restoring Hyprland.
- Restoring composite profiles.
- Restoring only selected files.
- Ignoring caches and generated files.
- Detecting conflicts before restoration.
- Backing up before replacing files.
- Reverting an unsuccessful restore.

The project must be distribution-independent and avoid excessive dependence on any particular desktop or application implementation.

---

# 2. Fundamental principle

The tool must NOT physically reorganize the user's original filesystem.

The existing filesystem must be treated as the source of truth.

Classification and organization must occur through:

- Manifests.
- Metadata.
- Rules.
- Profiles.
- Snapshots.
- Restore mappings.

The project must avoid moving user files merely to make backup easier.

The original structure must be preserved.

---

# 3. Problem the project solves

Users frequently switch:

- Linux distribution.
- Desktop Environment.
- Window Manager.
- Applications.
- Shell.
- Development environment.

Examples:

```text
KDE → Hyprland
Hyprland → GNOME
Ubuntu → Fedora
Fedora → Arch
Arch → Debian
GNOME → KDE
KDE → Hyprland
```

A naive restore of `~/.config` can introduce:

* Incompatible configurations.
* Files specific to another Desktop Environment.
* Distribution-specific configurations.
* Hardware-specific configurations.
* Stale cache.
* Automatically generated state.
* Conflicts between applications.
* Files that should not exist in the new environment.

Therefore:

```text
Backup ≠ Restore
```

The system must understand that restoring a Linux state is different from simply copying files.

---

# 4. Conceptual architecture

The main flow must be:

```text
Filesystem
    ↓
Discovery
    ↓
Classification
    ↓
Manifest
    ↓
Snapshot
    ↓
Profile
    ↓
Restore Plan
    ↓
Dry Run
    ↓
User Approval
    ↓
Transactional Restore
    ↓
Verification
    ↓
Rollback if necessary
```

---

# 5. State categories

Files must be classified semantically.

Do not rely solely on extension or MIME type.

Classification must consider:

* Path.
* Directory.
* Filename.
* Extension.
* MIME type.
* Symlink.
* Permissions.
* Owner.
* ACLs.
* Extended attributes when applicable.
* Related application.
* Related Desktop Environment.
* Related distribution.
* XDG variables.
* User-defined rules.

---

## 5.1 Personal

The user's personal data.

Examples:

```text
~/Documents/
~/Pictures/
~/Videos/
~/Music/
~/Projects/
~/Downloads/
```

Default behavior:

```text
restore: merge
```

These files must have low interference with restoration.

---

## 5.2 Identity

Files related to digital identity.

Examples:

```text
~/.ssh/
~/.gnupg/
~/.gitconfig
~/.config/git/
```

This category requires special handling.

The system must preserve:

* Permissions.
* Owner.
* Symlinks.
* ACLs when applicable.
* Extended attributes when applicable.

Operations involving secrets must require explicit confirmation when necessary.

---

## 5.3 Shell

Shell configuration.

Examples:

```text
~/.bashrc
~/.zshrc
~/.profile
~/.config/fish/
~/.config/starship.toml
```

This category must be independent of the Desktop Environment.

---

## 5.4 Development

Development-related configuration.

Examples:

```text
~/.config/nvim/
~/.config/Code/
~/.config/JetBrains/
~/.config/gh/
~/.cargo/
~/.npm/
```

The system must recognize that certain configurations may depend on installed software.

Example:

```json
{
  "path": "~/.config/nvim",
  "type": "config",
  "scope": "development",
  "dependencies": [
    "neovim"
  ]
}
```

The absence of an application must not automatically prevent the restoration of other categories.

---

# 5.5 Desktop

Graphical environment-specific configuration.

Examples:

```text
KDE
GNOME
Hyprland
Sway
XFCE
```

Each Desktop Environment must have its own profile.

Example:

```text
desktop:kde
desktop:gnome
desktop:hyprland
desktop:sway
```

By default, these profiles must be mutually exclusive.

Restoring:

```bash
linux-state restore --profile desktop:hyprland
```

must not automatically restore:

```text
~/.config/kdeglobals
~/.config/plasma-org.kde.plasma.desktop-appletsrc
```

Unless explicitly requested by the user.

---

# 5.6 Applications

Application-specific configuration.

Examples:

```text
Firefox
VS Code
Steam
Kitty
Alacritty
Obsidian
Discord
Neovim
```

Applications may have their own profiles.

Example:

```text
application:firefox
application:kitty
application:nvim
```

---

# 5.7 Machine-specific

Hardware or machine-dependent configuration.

Potential examples:

```text
GPU
Monitor
Touchpad
Keyboard
Audio
Network
Hardware-specific configuration
```

These files must not be considered portable by default.

---

# 5.8 Distribution-specific

Distribution-specific configuration.

Conceptual examples:

```text
Ubuntu
Fedora
Arch
Debian
openSUSE
```

These files must have their own classification and must not be restored automatically on another distribution.

---

# 5.9 Generated

Files that can be recreated automatically.

Examples:

```text
generated state
temporary state
application databases
runtime files
```

Default behavior:

```text
restore: never
```

---

# 5.10 Cache

Caches must not be restored by default.

Examples:

```text
~/.cache/
npm cache
thumbnail cache
browser cache
shader cache
application cache
```

Default behavior:

```text
restore: never
```

The user may explicitly request their inclusion.

---

# 6. Portability

Each item must have a portability classification.

```text
PORTABLE
ENVIRONMENT
MACHINE
SECRET
GENERATED
CACHE
PERSONAL
```

Example:

```text
~/.gitconfig
    → PORTABLE

~/.config/hypr/
    → ENVIRONMENT

GPU configuration
    → MACHINE

~/.ssh/
    → SECRET

~/.cache/
    → CACHE
```

This allows separating:

```text
"I want to take my environment"

from:

"I want to take my entire old machine."
```

---

# 7. Profiles

Profiles represent logical sets of configuration.

Example:

```text
profiles/
├── base/
├── personal/
├── shell/
├── development/
├── kde/
├── gnome/
├── hyprland/
└── applications/
```

Profiles can be composed.

Example:

```yaml
profile: workstation-hyprland

extends:
  - personal
  - shell
  - development
  - desktop:hyprland
  - applications:development
```

Another:

```yaml
profile: workstation-kde

extends:
  - personal
  - shell
  - development
  - desktop:kde
  - applications:development
```

This allows switching environments without duplicating all configuration.

---

# 8. Discovery

The discovery module must analyze the current environment.

It must detect:

```text
Files
Directories
Hidden files
Dotfiles
Symlinks
Permissions
Ownership
ACLs
Extended attributes
File size
Timestamps
Hash
MIME type
XDG directories
Known applications
Known Desktop Environments
Potential secrets
Potential cache
Potential generated files
```

Discovery must not modify files.

---

# 9. Classification

Classification must be rule-based.

Recommended priority:

```text
Explicit user rule
        ↓
Known application rule
        ↓
Known Desktop Environment rule
        ↓
Known system/location rule
        ↓
XDG classification
        ↓
Path classification
        ↓
MIME / extension
        ↓
Unknown
```

Never rely solely on extension as the source of truth.

Example:

```text
~/.config/Code/User/settings.json
```

must be recognized as VS Code configuration.

While:

```text
~/Projects/my-app/config.json
```

must be treated as a project file.

---

# 10. Manifest

The manifest is the primary mechanism for describing state.

Example:

```json
{
  "path": "~/.config/hypr/hyprland.conf",
  "type": "config",
  "scope": "desktop",
  "environment": "hyprland",
  "size": 1842,
  "mode": "0644",
  "owner": "user",
  "sha256": "...",
  "restore": {
    "default": "backup-and-replace",
    "conflict": "ask"
  },
  "dependencies": [
    "hyprland"
  ]
}
```

Example of a personal file:

```json
{
  "path": "~/Documents",
  "type": "personal",
  "scope": "user-data",
  "restore": {
    "default": "merge"
  }
}
```

Example of a cache:

```json
{
  "path": "~/.cache",
  "type": "cache",
  "scope": "generated",
  "restore": {
    "default": "never"
  }
}
```

---

# 11. Snapshot

A snapshot represents the known state of the user at a given moment.

Example:

```text
snapshots/
└── 2026-08-22/
    ├── manifest.json
    ├── metadata.json
    └── data/
```

Snapshots must contain:

```text
Timestamp
Hostname
Distribution
Kernel
Desktop Environment
Architecture
User
Hash information
Manifest version
Tool version
```

Sensitive information must be handled carefully.

---

# 12. Backup

The system must support:

```text
Full snapshots
Incremental snapshots
Deduplication
Compression
Encryption
Retention
Integrity verification
```

The initial implementation may use full snapshots to reduce complexity.

Deduplication and incremental backups can be added later.

---

# 13. Compression

The implementation must allow different algorithms.

Prioritize widely available and efficient formats.

Possible options:

```text
zstd
gzip
xz
```

The choice should be configurable.

For the MVP:

```text
zstd
```

can be the default.

---

# 14. Hashing

Files must have hashes to verify integrity.

Prefer:

```text
SHA-256
```

The hash must allow detecting:

```text
Same
Modified
Missing
Corrupted
```

---

# 15. Restore

Restore must never be just:

```text
copy backup → filesystem
```

The process must be:

```text
Snapshot
   ↓
Profile
   ↓
Discovery current state
   ↓
Conflict analysis
   ↓
Restore plan
   ↓
Dry run
   ↓
Approval
   ↓
Temporary backup
   ↓
Apply
   ↓
Verification
```

---

# 16. Conflict detection

Possible states:

```text
NEW
SAME
MODIFIED
CONFLICT
MISSING
SKIPPED
```

Example:

```text
Restore plan

NEW       ~/.config/hypr/
NEW       ~/.config/waybar/
SAME      ~/.config/kitty/
CONFLICT  ~/.config/gtk-3.0/settings.ini
```

---

# 17. Conflict resolution

The system must offer options such as:

```text
replace
keep
backup
merge
skip
```

Example:

```text
[r] Replace
[k] Keep existing
[b] Backup existing
[m] Merge
[s] Skip
```

The default option for important files must be safe.

Never silently overwrite existing files.

---

# 18. Dry run

Every restore operation must allow simulation.

Example:

```bash
linux-state restore --profile hyprland --dry-run
```

The command must show exactly what would be changed.

No file must be modified during the dry run.

---

# 19. Transactional restore

Before modifying an existing file:

```text
current file
     ↓
temporary backup
     ↓
apply new file
```

If any step fails:

```text
rollback
```

must restore the previous state.

The operation must be considered complete only after validation.

---

# 20. Rollback

Rollback must allow returning to the state prior to the restore.

Example:

```bash
linux-state rollback
```

or:

```bash
linux-state rollback --transaction <id>
```

Each restore must have a transaction identifier.

Example:

```text
transaction: 2026-08-22T22:30:11-03:00-8F3A
```

---

# 21. Verification

After a restore:

```text
Check existence
Check hash
Check permissions
Check ownership
Check symlinks
Check expected paths
Check skipped files
Check failed files
```

The system must generate a report.

Example:

```text
Restore completed.

Files restored: 142
Files skipped: 18
Conflicts: 3
Failed: 0

Integrity:
  PASS
```

---

# 22. CLI

The CLI must be the primary interface.

Examples:

```bash
linux-state scan
```

```bash
linux-state snapshot
```

```bash
linux-state list
```

```bash
linux-state list --category desktop
```

```bash
linux-state list --profile hyprland
```

```bash
linux-state plan --profile hyprland
```

```bash
linux-state restore --profile hyprland --dry-run
```

```bash
linux-state restore --profile hyprland
```

```bash
linux-state rollback
```

```bash
linux-state verify
```

---

# 23. Usage examples

## Backup before switching distributions

```bash
linux-state scan
linux-state snapshot
```

After installation:

```bash
linux-state scan
linux-state plan --profile personal
linux-state restore --profile personal
```

Then:

```bash
linux-state plan --profile shell
linux-state restore --profile shell
```

And finally:

```bash
linux-state plan --profile development
linux-state restore --profile development
```

---

# 24. Switching from KDE to Hyprland

Before switching:

```bash
linux-state snapshot
```

After installing Hyprland:

```bash
linux-state restore --profile desktop:hyprland --dry-run
```

The system must identify only Hyprland-related configuration.

It must not automatically restore:

```text
KDE
Plasma
KDE shortcuts
KDE-specific state
```

---

# 25. Switching from Hyprland to KDE

The reverse process must work the same way:

```bash
linux-state restore --profile desktop:kde --dry-run
```

The Hyprland profile must not be restored.

---

# 26. Composite profiles

Example:

```bash
linux-state restore --profile workstation-hyprland
```

The profile may represent:

```text
personal
shell
development
hyprland
selected applications
```

But not:

```text
KDE
GNOME
machine-specific state
cache
```

---

# 27. Safety rules

The system must follow these rules:

1. Never modify files during discovery.
2. Never silently overwrite files.
3. Never restore caches by default.
4. Never automatically restore configuration from another Desktop Environment.
5. Never assume a configuration is portable just because it is valid.
6. Never restore secrets without appropriate handling.
7. Always allow dry-run.
8. Always generate a plan before destructive operations.
9. Always allow rollback.
10. Always verify the result after restore.
11. Preserve permissions when necessary.
12. Preserve symlinks.
13. Never remove files simply because they are absent from the snapshot.
14. Destructive operations must require explicit confirmation.
15. The original filesystem must never be reorganized merely to make backup easier.

---

# 28. Configuration

Example:

```yaml
version: 1

storage:
  path: "~/.local/share/linux-state"
  compression: zstd
  hashing: sha256

backup:
  incremental: false
  encryption: false
  retention:
    snapshots: 10

restore:
  conflict: ask
  backup_before_replace: true
  verify_after_restore: true

categories:
  cache:
    restore: never

  generated:
    restore: never

  secrets:
    require_confirmation: true

desktop:
  exclusive: true

profiles:
  default:
    - personal
    - shell
    - development
```

---

# 29. Project structure

An initial implementation may use:

```text
linux-state/
├── src/
│   ├── discovery/
│   ├── classification/
│   ├── manifest/
│   ├── snapshot/
│   ├── storage/
│   ├── profiles/
│   ├── restore/
│   ├── rollback/
│   ├── verification/
│   └── cli/
│
├── rules/
│   ├── default.yaml
│   ├── desktop/
│   │   ├── kde.yaml
│   │   ├── gnome.yaml
│   │   └── hyprland.yaml
│   └── applications/
│
├── tests/
│
├── docs/
│
├── examples/
│
└── README.md
```

---

# 30. Main interfaces

The architecture must separate responsibilities.

Conceptual example:

```text
DiscoveryEngine
    ↓
ClassificationEngine
    ↓
ManifestBuilder
    ↓
SnapshotManager
    ↓
ProfileResolver
    ↓
RestorePlanner
    ↓
RestoreExecutor
    ↓
VerificationEngine
    ↓
RollbackManager
```

Each component must have a single responsibility.

---

# 31. Extensibility

New applications and Desktop Environments must be addable without modifying the core.

Example:

```text
rules/desktop/hyprland.yaml
rules/desktop/kde.yaml
rules/desktop/gnome.yaml
```

Or:

```text
rules/applications/neovim.yaml
rules/applications/vscode.yaml
rules/applications/firefox.yaml
```

This allows incremental evolution.

---

# 32. Sensitive data

The system must identify potentially sensitive data.

Examples:

```text
SSH keys
GPG keys
API tokens
Cloud credentials
Password stores
Authentication files
Certificates
```

These files must receive the classification:

```text
SECRET
```

and specific handling.

The system must not print sensitive content in logs.

---

# 33. Logs

Logs must record:

```text
Operation
Timestamp
File path
Action
Result
Error
Transaction ID
```

Never record:

```text
Passwords
Private keys
Tokens
Secret contents
```

---

# 34. Performance

The system must handle large directories without loading all content into memory.

Prioritize:

```text
Streaming
Lazy discovery
Incremental hashing
Parallel hashing when appropriate
Deduplication
Exclusion rules
```

Caches and directories known to contain large amounts of temporary files must have specific rules.

---

# 35. Trade-offs

## Simplicity vs. features

The MVP must prioritize:

```text
Correctness
Safety
Predictability
Rollback
```

before:

```text
GUI
Cloud storage
Deduplication
Automatic dependency installation
```

---

## Full vs incremental

Full snapshots:

```text
+ Simpler
+ Easy to recover
+ Easy to understand
- More space
```

Incremental:

```text
+ Lower storage consumption
- More complexity
- More complex restore
```

The MVP must start with full snapshots.

---

# 36. MVP

The MVP must contain only:

```text
[ ] Discovery
[ ] Basic classification
[ ] Manifest
[ ] Snapshot
[ ] Profiles
[ ] Dry run
[ ] Conflict detection
[ ] Restore
[ ] Backup before replace
[ ] Verification
[ ] Rollback
[ ] CLI
```

Do not implement initially:

```text
[ ] GUI
[ ] Cloud
[ ] Automatic package installation
[ ] Complex deduplication
[ ] Automatic merge of arbitrary configuration files
[ ] Full hardware detection
[ ] Automatic distribution migration
```

---

# 37. MVP workflow

Minimal flow:

```bash
linux-state scan
```

↓

```bash
linux-state snapshot
```

↓

```bash
linux-state list
```

↓

```bash
linux-state plan --profile hyprland
```

↓

```bash
linux-state restore --profile hyprland --dry-run
```

↓

```bash
linux-state restore --profile hyprland
```

↓

```bash
linux-state verify
```

↓

In case of problems:

```bash
linux-state rollback
```

---

# 38. Complete manifest example

```json
{
  "version": 1,
  "snapshot": {
    "id": "2026-08-22T22:30:00-03:00",
    "hostname": "workstation",
    "distribution": "example-linux",
    "desktop": "hyprland"
  },
  "files": [
    {
      "path": "~/.gitconfig",
      "category": "identity",
      "portability": "portable",
      "mode": "0644",
      "sha256": "..."
    },
    {
      "path": "~/.config/hypr/hyprland.conf",
      "category": "desktop",
      "environment": "hyprland",
      "portability": "environment",
      "mode": "0644",
      "sha256": "..."
    },
    {
      "path": "~/.config/nvim/",
      "category": "development",
      "application": "neovim",
      "portability": "portable",
      "sha256": "..."
    },
    {
      "path": "~/Documents/",
      "category": "personal",
      "portability": "personal",
      "restore": "merge"
    },
    {
      "path": "~/.cache/",
      "category": "cache",
      "portability": "generated",
      "restore": "never"
    }
  ]
}
```

---

# 39. Success criteria

The project will be considered successful when it is possible to:

### Case 1 - Distro hopping

Install a new distribution and recover the personal environment without manually copying the entire `home`.

### Case 2 - Desktop hopping

Switch:

```text
KDE → Hyprland
```

without restoring KDE-specific configuration.

### Case 3 - Return

Switch back:

```text
Hyprland → KDE
```

without losing previous configuration.

### Case 4 - Selective restore

Restore only:

```text
Personal
Shell
Development
```

without restoring:

```text
Desktop
Cache
Machine-specific
```

### Case 5 - Conflict

If a file already exists and has been modified:

```text
CONFLICT
```

must be detected before replacement.

### Case 6 - Failure

If a restore fails midway:

```bash
linux-state rollback
```

must return the system to its previous state.

---

# 40. Final principle

The goal of the project is not to transport an entire Linux installation.

The goal is to transport what is important to the user without automatically carrying over what belongs to the previous machine.

In other words:

```text
Do not restore the old machine.

Restore the user's state.
```

The tool must preserve:

```text
Identity
Personal data
Development environment
Shell preferences
Application preferences
Selected desktop configuration
```

and avoid automatically transporting:

```text
Cache
Generated state
Machine-specific configuration
Distribution-specific configuration
Unrelated desktop environments
Temporary files
```

The system must always favor:

```text
safe restoration
over
complete restoration
```

and:

```text
predictability
over
automation
```

The main rule is:

```text
Discover → Classify → Plan → Preview → Approve → Apply → Verify → Rollback
```

This flow must remain the architectural foundation of the project.
