# Changelog

All notable, user-visible changes are documented here.

## Unreleased

### Added

- `--exclude GLOB` for `plan` and `restore` (repeatable fnmatch relative
  to root, `**` supported; `DIR/**` also excludes `DIR` itself). Excluded
  entries appear in the plan as `SKIPPED (user exclude)`. Uses the same
  matching semantics as `snapshot --exclude`.
- Snapshot data compression: `gzip` by default, optional `zstd`
  (`--compression zstd`, requires Python 3.14+ on both capturing and
  restoring machines). The algorithm used is recorded per snapshot;
  pre-compression snapshots remain restorable.
- Opt-in retention: `linux-state snapshot --keep N` prunes all but the
  newest N snapshots after creating a new one. Without the flag nothing
  is ever deleted.

### Fixed

- Rollback no longer aborts with a false "path escapes the restore root"
  when undoing restores that created symlinks pointing outside the root
  (e.g. virtualenv `bin/python -> /usr/bin/python3`). Only the parent
  chain of a target is resolved now; the leaf component is never
  followed, so escaping leaf symlinks can always be unlinked.
- Restoring a file over a pre-existing symlink no longer writes through
  it: the leaf symlink is removed (after being recorded for rollback)
  before content is written, so replacements stay inside the restore root.
- Test-suite isolation: XDG fallback tests no longer depend on the
  developer's real `XDG_CACHE_HOME`/`XDG_STATE_HOME`.

## 0.1.0 - 2026-08-23

Initial MVP release.

### Added

- Read-only discovery: regular files, directories, dotfiles, symlinks
  (never followed), permissions and streaming SHA-256 hashing.
- Deterministic manifests with per-entry classification and the rule that
  matched (explainable classification).
- Full snapshots stored under `$XDG_DATA_HOME/linux-state/snapshots/`,
  created atomically; source trees are never modified.
- Bundled classification rules (secrets, cache, personal, shell, identity,
  desktop environments, applications) with user-rule override by precedence.
- Composable YAML profiles (`extends`) with desktop-environment mutual
  exclusion by default.
- Restore planning as a dry run: NEW / SAME / MODIFIED / CONFLICT / SKIPPED.
- Transactional restore with explicit approval gate
  (`--approve`), backup-before-replace, conflict policy flags
  (`skip` default, `replace` opt-in) and symlink-escape protection.
- Post-restore verification (existence, hash, mode, symlinks) recorded in
  the transaction record.
- Rollback of restore transactions restoring the previous state.
- CLI: `scan`, `snapshot`, `list`, `plan`, `restore`, `rollback`.
