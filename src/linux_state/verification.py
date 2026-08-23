"""Post-restore verification.

Checks executed restore actions against the snapshot manifest:
existence, content hash, mode and symlink targets. Produces an explicit
report that is stored in the transaction record. A restore is not
"complete" until verification passes (AGENTS §13).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from linux_state.discovery import CHUNK_SIZE, Kind


def _hash_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def verify_paths(
    root: Path,
    manifest: dict,
    relative_paths: list[str],
) -> dict:
    """Verify restored targets against manifest records. Read-only."""
    root = Path(root).resolve()
    records = {}
    for record in manifest["files"]:
        relative = Path(record["path"]).relative_to(Path(manifest["root"])).as_posix()
        records[relative] = record

    checked = 0
    failures: list[dict] = []
    for relative in relative_paths:
        record = records.get(relative)
        if record is None:
            continue  # not part of this manifest; nothing to verify
        checked += 1
        target = root / relative

        if not os.path.lexists(target):
            failures.append({"path": relative, "check": "exists", "reason": "missing"})
            continue

        kind = record["type"]
        if kind == Kind.SYMLINK.value:
            actual = os.readlink(target)
            if actual != record.get("symlink_target"):
                failures.append({
                    "path": relative, "check": "symlink_target",
                    "reason": f"{actual} != {record.get('symlink_target')}",
                })
            continue

        if kind == Kind.FILE.value:
            expected_hash = record.get("sha256")
            if expected_hash and _hash_of(target) != expected_hash:
                failures.append({"path": relative, "check": "sha256", "reason": "hash mismatch"})
                continue
            expected_mode = int(record["mode"], 8)
            if (target.stat().st_mode & 0o777) != expected_mode:
                failures.append({
                    "path": relative, "check": "mode",
                    "reason": f"{oct(target.stat().st_mode & 0o777)} != {record['mode']}",
                })

    return {
        "checked": checked,
        "failures": failures,
        "result": "PASS" if not failures else "FAIL",
    }


def attach_verification(transaction_dir: Path, report: dict) -> None:
    """Store the verification report inside the transaction record."""
    import json

    path = transaction_dir / "transaction.json"
    record = json.loads(path.read_text())
    record["verification"] = report
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)
