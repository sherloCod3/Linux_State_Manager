"""Transactional restore executor.

Executes an approved RestorePlan. Every action that overwrites or removes
existing state first records a backup inside the transaction directory, so
the pre-restore state is always recoverable (rollback lands in MVP-07).

Safety gates:
    - Execution requires explicit approval (approve=True / --approve).
    - Conflicting files are skipped unless the conflict policy explicitly
      says "replace".
    - Target paths are validated against symlink escapes before writing.
    - The run stops at the first failure; the transaction record marks
      what was executed and what failed. No partial success is reported
      as complete.

Transaction layout:

    <storage>/transactions/<tx-id>/
        transaction.json   planned/executed/failed/status/rollback info
        backup/            pre-replace copies (relative paths preserved)
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from linux_state.snapshot import new_snapshot_id as _new_tx_suffix
from linux_state.discovery import CHUNK_SIZE, Kind

STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

RESTORED = "RESTORED"


class ExecutionError(Exception):
    def __init__(self, operation: str, path: Path | None, reason: str):
        self.operation = operation
        self.path = path
        self.reason = reason
        location = str(path) if path is not None else "<unknown>"
        super().__init__(f"{operation} failed for {location}: {reason}")


class NotApprovedError(ExecutionError):
    pass


@dataclass
class Transaction:
    id: str
    directory: Path
    started: str
    snapshot_id: str = ""
    profile: str = ""
    root: str = ""
    executed: list[str] | None = None
    failed: list[dict] | None = None
    status: str = STATUS_RUNNING
    rollback: list[dict] | None = None

    def __post_init__(self):
        if self.executed is None:
            self.executed = []
        if self.failed is None:
            self.failed = []
        if self.rollback is None:
            self.rollback = []

    def to_dict(self) -> dict:
        return {
            "transaction": self.id,
            "started": self.started,
            "status": self.status,
            "snapshot_id": self.snapshot_id,
            "profile": self.profile,
            "root": self.root,
            "executed": self.executed,
            "failed": self.failed,
            "rollback_info": self.rollback,
        }

    def save(self) -> None:
        import json

        path = self.directory / "transaction.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")
        tmp.replace(path)

    @classmethod
    def load(cls, directory: Path) -> "Transaction":
        import json

        record = json.loads((directory / "transaction.json").read_text())
        return cls(
            id=record["transaction"],
            directory=directory,
            started=record["started"],
            snapshot_id=record.get("snapshot_id", ""),
            profile=record.get("profile", ""),
            root=record.get("root", ""),
            executed=record.get("executed", []),
            failed=record.get("failed", []),
            status=record.get("status", STATUS_RUNNING),
            rollback=record.get("rollback_info", []),
        )


def new_transaction(
    storage_root: Path, snapshot_id: str, profile: str, root: Path
) -> Transaction:
    now = datetime.now(timezone.utc)
    tx_id = f"{now.strftime('%Y-%m-%dT%H-%M-%SZ')}-{_new_tx_suffix().split('-')[-1]}"
    directory = storage_root / "transactions" / tx_id
    directory.mkdir(parents=True)
    return Transaction(
        id=tx_id,
        directory=directory,
        started=now.isoformat(),
        snapshot_id=snapshot_id,
        profile=profile,
        root=str(root),
    )


def _ensure_within_root(target: Path, root: Path) -> None:
    """Reject paths that escape the root via traversal or parent symlinks."""
    resolved_target = target.resolve()
    resolved_root = root.resolve()
    try:
        resolved_target.relative_to(resolved_root)
    except ValueError:
        raise ExecutionError(
            "restore", target, "path escapes the restore root (symlink escape?)"
        ) from None


def _hash_of(path: Path, algorithm: str = "none") -> str:
    from linux_state import compression as codec

    if algorithm == "none":
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            while chunk := fh.read(CHUNK_SIZE):
                digest.update(chunk)
        return digest.hexdigest()
    return codec.hash_content(path, algorithm)


def execute_plan(
    plan,
    root: Path,
    storage_root: Path,
    snapshot_data_dir: Path,
    manifest: dict,
    *,
    approve: bool = False,
    conflict_policy: str = "skip",
) -> Transaction:
    """Execute *plan* transactionally and return the transaction record."""
    from linux_state.planner import CONFLICT, MODIFIED, NEW

    if not approve:
        raise NotApprovedError(
            "restore", root,
            "execution requires explicit approval (--approve)",
        )
    if conflict_policy not in ("skip", "replace"):
        raise ExecutionError("restore", root, f"unknown conflict policy {conflict_policy!r}")

    root = root.resolve()
    tx = new_transaction(storage_root, plan.snapshot_id, plan.profile, root)

    # Snapshot data may be stored compressed; the metadata decides decoding.
    from linux_state import compression as codec
    from linux_state.storage import load_metadata

    try:
        metadata = load_metadata(storage_root, plan.snapshot_id)
    except (FileNotFoundError, json.JSONDecodeError):
        metadata = {}  # legacy snapshot without metadata
    algorithm = codec.normalize(metadata.get("compression"))
    codec.require_available(algorithm)

    records_by_rel = {}
    for record in manifest["files"]:
        relative = Path(record["path"]).relative_to(Path(manifest["root"])).as_posix()
        records_by_rel[relative] = record

    try:
        for action in plan.actions:
            record = records_by_rel.get(action.path)
            if record is None:  # pragma: no cover - planner/manifest mismatch
                raise ExecutionError("restore", Path(action.path), "missing manifest record")

            if action.action in ("SAME", "SKIPPED"):
                continue
            if action.action == CONFLICT and conflict_policy == "skip":
                continue
            if action.action not in (NEW, MODIFIED, CONFLICT):
                continue  # unknown action: never guess

            target = root / action.path
            _ensure_within_root(target, root)
            source = snapshot_data_dir / codec.stored_name(action.path, algorithm)
            try:
                _apply_action(tx, record, source, target, root, action.path, algorithm)
            except ExecutionError:
                raise
            except OSError as exc:
                raise ExecutionError(
                    "restore", target, exc.strerror or str(exc)
                ) from exc
            tx.executed.append(action.path)
            tx.save()
    except ExecutionError as exc:
        tx.failed.append({
            "path": str(exc.path),
            "operation": exc.operation,
            "reason": exc.reason,
        })
        tx.status = STATUS_FAILED
        tx.save()
        return tx

    tx.status = STATUS_COMPLETED
    tx.save()
    return tx


def _backup_existing(tx: Transaction, target: Path, relative: str) -> None:
    """Preserve current target state inside the transaction backup area."""
    if not os.path.lexists(target):
        # Did not exist before the restore; rollback must remove it.
        tx.rollback.append({"path": relative, "type": "absent"})
        return
    if target.is_symlink():
        tx.rollback.append({
            "path": relative, "type": "symlink", "target": os.readlink(target),
        })
        return  # symlinks are recreated from recorded metadata, not copied
    if target.is_file():
        backup_path = tx.directory / "backup" / relative
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup_path, follow_symlinks=False)
        tx.rollback.append({"path": relative, "type": "file", "backup": str(backup_path)})
        return
    if target.is_dir():
        # Directories are only ever created, never replaced wholesale.
        tx.rollback.append({"path": relative, "type": "dir"})


def _apply_action(
    tx, record, source: Path, target: Path, root: Path, relative: str, algorithm: str = "none"
) -> None:
    from linux_state import compression as codec

    kind = record["type"]

    _backup_existing(tx, target, relative)

    if kind == Kind.DIRECTORY.value:
        target.mkdir(parents=True, exist_ok=True)
        os.chmod(target, int(record["mode"], 8))
        return

    if kind == Kind.SYMLINK.value:
        if os.path.lexists(target):
            target.unlink()
        target.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(record["symlink_target"], target)
        return

    if kind == Kind.FILE.value:
        stored_hash = record.get("sha256")
        if stored_hash and _hash_of(source, algorithm) != stored_hash:
            raise ExecutionError(
                "verify-snapshot", source,
                "stored snapshot content does not match manifest hash",
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        codec.decompress(source, target, algorithm)
        os.chmod(target, int(record["mode"], 8))
        applied_hash = _hash_of(target)
        if stored_hash and applied_hash != stored_hash:
            raise ExecutionError(
                "verify", target, "restored content does not match expected hash"
            )
        return

    raise ExecutionError("restore", target, f"unsupported entry type {kind!r}")
