# Linux State Manager

Cross-distribution Linux state manager with selective, conflict-aware restoration.

`linux-state` captures, classifies, versions and restores the user's personal
state (configs, identity, shell, development environment) without treating all
files as equivalent. It never performs a naive `copy backup -> filesystem`:
every restore goes through

```
Discover → Classify → Snapshot → Plan → Preview → Approve → Apply → Verify → Rollback
```

## Status

Work in progress. See [docs/PROJECT-STATUS.md](docs/PROJECT-STATUS.md)
for the current validated state and next step.

## Development

```bash
python3 -m pip install -e .[dev]   # once dev extras exist; for now:
python3 -m pytest                  # run tests
linux-state --help                 # after editable install
```

The core is developed against isolated temporary directory trees.
It must never be tested against a real user home directory.

## Documentation

- `SPEC.md` — product specification (what we are building)
- `AGENTS.md` — engineering rules (how we work)
- `docs/PROJECT-STATUS.md` — current project state (where we are)
