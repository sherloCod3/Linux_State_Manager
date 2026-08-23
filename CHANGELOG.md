# Changelog

All notable, user-visible changes are documented here.

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
