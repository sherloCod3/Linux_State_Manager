# Linux State Manager

Cross-distribution Linux state manager with selective, conflict-aware
restoration.

`linux-state` captures, classifies and restores the user's personal state
(configs, identity, shell, development environment) without treating all
files as equivalent. It never performs a naive `copy backup -> filesystem`:

```
Discover → Classify → Snapshot → Plan → Preview → Approve → Apply → Verify → Rollback
```

> Do not restore the old machine. Restore the user's state.

## Status

MVP-10 complete. All core commands are implemented **and validated**
by the test suite (171 tests). See
[docs/PROJECT-STATUS.md](docs/PROJECT-STATUS.md) for details.

Implemented: discovery, classification, manifests, snapshots (streaming
manifest + single-pass hash, amplitude reduction via `--profile/--exclude`),
profiles, restore planning, dry run, conflict detection, transactional
restore, verification, rollback, CLI.

Not implemented: GUI, cloud storage, package installation, config merging,
ACL/xattr preservation (see [Known limitations](#known-limitations)).

## Requirements

- Linux with Python 3.10+
- [PyYAML](https://pyyaml.org/) (only runtime dependency)

## Installation

```bash
python3 -m pip install .
linux-state --help
```

## Usage

### Capture state (read-only)

```bash
# Scan a tree; every entry is classified and the rule that matched is shown.
linux-state scan --root ~ -v

# Create a full snapshot under $XDG_DATA_HOME/linux-state/snapshots/.
# Data is gzip-compressed by default; --compression zstd requires Python 3.14+.
linux-state snapshot --root ~

# Reduced amplitude without repartitioning (configs-only, skip caches):
linux-state snapshot --root ~ --profile shell --exclude ".cache/**"
linux-state snapshot --root ~ --profile development --exclude "Downloads/**"

# Opt-in retention: after snapshotting, prune all but the newest 10 snapshots.
linux-state snapshot --root ~ --keep 10
```

Snapshots preserve file modes and symlinks (including broken ones) and store
a manifest with SHA-256 hashes plus environment metadata. File data is stored
compressed per file (`gzip` or `zstd`); the algorithm used is recorded in each
snapshot's metadata, and pre-compression legacy snapshots remain restorable.
`--profile` reuses the same classification as `plan --profile`, so a
`snapshot --profile shell` contains exactly what a restore with that profile
would consider; `--exclude` is repeatable fnmatch (`**` supported) relative
to `--root`. Live files that vanish between discovery and capture are SKIPPED
with a warning and excluded from the manifest; permission errors still abort
atomically.

### Browse stored snapshots

```bash
linux-state list [-v]
```

### Plan a restore (dry run — nothing is modified)

```bash
# Show what would happen for a specific profile:
linux-state plan <snapshot-id> --root ~ --profile desktop:hyprland

# Or across all restorable categories:
linux-state plan <snapshot-id> --root ~
```

The plan reports each entry as `NEW`, `SAME`, `MODIFIED`, `CONFLICT` or
`SKIPPED`. Caches are always skipped (`never`). Secrets are skipped until
explicitly reviewed.

### Restore (requires explicit approval)

```bash
# Conflicting files are SKIPPED unless you pass --conflict replace.
linux-state restore <snapshot-id> --root ~ --profile shell --approve

# Replace conflicting files after they are backed up:
linux-state restore <snapshot-id> --root ~ --conflict replace --approve
```

Every restore runs as a transaction: previous versions of replaced files are
backed up, restored content is verified against the manifest hash, and the
run stops at the first failure.

### Rollback

```bash
# Undo the most recent restore transaction (or pass --transaction <id>).
linux-state rollback --approve
```

## Profiles

Profiles are YAML files composing categories and environments:

```yaml
profile: workstation-hyprland
extends:
  - personal
  - shell
  - development
  - desktop:hyprland
```

Place them in `$XDG_CONFIG_HOME/linux-state/profiles/`
(default `~/.config/linux-state/profiles/`). See
[examples/profiles/](examples/profiles/).

Desktop environments are mutually exclusive by default: a profile selecting
two different `desktop:` environments is rejected unless it sets
`allow_multiple_desktops: true`.

## Classification rules

Bundled rules classify paths into semantic categories (`secret`, `cache`,
`personal`, `shell`, `identity`, `desktop`, ...). Every classification is
explainable: `scan -v` shows which rule matched.

User rules in a directory passed via `--rules DIR` take precedence over the
bundled defaults. Conservative by design: unknown files are marked for
review and are never restored automatically; caches and generated state are
never restored.

## Development

```bash
python3 -m pytest        # 171 tests; all use isolated temp directories
```

The test suite never touches a real user home directory.

Project documents:

| File | Purpose |
| ---- | ------- |
| `SPEC.md` | What we are building |
| `AGENTS.md` | How we work |
| `docs/PROJECT-STATUS.md` | Where we are |
| `docs/adr/` | Why we decided this way |

## Known limitations

- ACLs and extended attributes are not captured yet (partial stdlib support).
- Ownership is recorded but never restored; restored files belong to the
  current user.
- Conflict handling offers skip/replace flags only; no interactive prompts
  or automatic merging.
- Snapshots are full copies with per-file compression; incremental
  snapshots and deduplication are not implemented.
- `zstd` snapshots require Python 3.14+ on **both** the capturing and the
  restoring machine (stdlib `compression.zstd`); `gzip` works everywhere.

## License

[MIT](LICENSE)
