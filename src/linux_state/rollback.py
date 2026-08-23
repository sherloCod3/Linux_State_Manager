"""Rollback: return the filesystem to its pre-restore state.

Reads a transaction record and applies its rollback info in reverse order:
    absent  -> remove what was created
    file    -> restore the backup copy (mode preserved)
    symlink -> recreate the recorded target
    dir     -> nothing (directories are only created, never replaced)

Rollback is itself transactional: it writes its own record and never
touches anything outside the original restore root.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from linux_state.executor import (
    ExecutionError,
    Transaction,
    _ensure_within_root,
    new_transaction,
)
from linux_state.storage import transactions_dir


class RollbackError(ExecutionError):
    pass


def list_transactions(storage_root: Path) -> list[str]:
    directory = transactions_dir(storage_root)
    if not directory.is_dir():
        return []
    ids = []
    for entry in directory.iterdir():
        if entry.is_dir() and (entry / "transaction.json").is_file():
            ids.append(entry.name)
    return sorted(ids)


def latest_transaction(storage_root: Path) -> str | None:
    ids = list_transactions(storage_root)
    return ids[-1] if ids else None


def perform_rollback(
    storage_root: Path,
    tx_id: str,
    *,
    approve: bool = False,
) -> tuple[Transaction, Transaction]:
    """Undo transaction *tx_id*. Returns (original, rollback_transaction)."""
    if not approve:
        raise ExecutionError(
            "rollback", None,
            "rollback modifies files and requires explicit approval (--approve)",
        )

    directory = transactions_dir(storage_root) / tx_id
    if not (directory / "transaction.json").is_file():
        raise RollbackError("rollback", directory, "transaction not found")

    original = Transaction.load(directory)
    root = Path(original.root)
    if not original.root or not root.is_dir():
        raise RollbackError("rollback", root, "restore root no longer exists")

    rollback_tx = new_transaction(
        storage_root, f"rollback:{original.snapshot_id}", original.profile, root
    )
    # Rollback applies entries in reverse order of recording.
    try:
        for entry in sorted(original.rollback, key=lambda e: e["path"], reverse=True):
            target = root / entry["path"]
            _ensure_within_root(target, root)
            kind = entry.get("type")

            if kind == "absent":
                if target.is_symlink() or target.is_file():
                    target.unlink()
                    rollback_tx.executed.append(f"removed {entry['path']}")
            elif kind == "file":
                backup = Path(entry["backup"])
                if not backup.is_file():
                    raise RollbackError(
                        "rollback", backup, "backup copy missing; cannot restore previous state"
                    )
                if os.path.lexists(target):
                    target.unlink()
                shutil.copy2(backup, target, follow_symlinks=False)
                rollback_tx.executed.append(f"restored {entry['path']}")
            elif kind == "symlink":
                if os.path.lexists(target):
                    target.unlink()
                os.symlink(entry["target"], target)
                rollback_tx.executed.append(f"relinked {entry['path']}")
            elif kind == "dir":
                continue
            else:
                raise RollbackError(
                    "rollback", target, f"unknown rollback entry type {kind!r}"
                )
            rollback_tx.save()
    except ExecutionError:
        rollback_tx.status = "failed"
        rollback_tx.failed.append({
            "operation": "rollback",
            "reason": "aborted",
        })
        rollback_tx.save()
        raise

    rollback_tx.status = "completed"
    rollback_tx.save()
    return original, rollback_tx
