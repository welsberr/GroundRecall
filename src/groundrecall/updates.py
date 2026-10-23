"""Plan and apply non-destructive, versioned canonical-store updates."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from typing import Any

from .store import (
    GroundRecallStore,
    IncompatibleStoreVersionError,
    STORE_MANIFEST_NAME,
    STORE_MANIFEST_SCHEMA,
    SUPPORTED_STORE_FORMAT_VERSION,
    check_store_compatibility,
)
from .store_lock import store_lock
from .workspace import require_canonical_store_target, require_store_not_workspace_root


class UpdateError(RuntimeError):
    """Raised when a store cannot be safely planned or updated."""


INITIAL_UPDATE_ID = "store-format-manifest-v1"


def _software_version() -> str:
    try:
        return importlib.metadata.version("groundrecall")
    except importlib.metadata.PackageNotFoundError:
        return "source-checkout"


def _root(store_dir: str | Path) -> Path:
    store = Path(store_dir).expanduser().resolve(strict=True)
    if not store.is_dir():
        raise UpdateError(f"canonical store is not a directory: {store}")
    require_store_not_workspace_root(store)
    require_canonical_store_target(store)
    return store


def _tree_digest(root: Path, *, omit_manifest: bool = False) -> str:
    """Hash paths, entry types, modes and file bytes; reject special files."""

    digest = hashlib.sha256()
    entries: list[Path] = []
    for directory, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        base = Path(directory)
        entries.extend(base / name for name in dirnames)
        entries.extend(base / name for name in filenames)
    for path in sorted(entries, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if omit_manifest and relative == STORE_MANIFEST_NAME:
            continue
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise UpdateError(f"store contains an unsupported filesystem entry: {relative}")
        kind = b"d" if stat.S_ISDIR(mode) else b"f"
        digest.update(kind + b"\0" + relative.encode("utf-8", "surrogateescape") + b"\0")
        digest.update(f"{stat.S_IMODE(mode):04o}".encode("ascii") + b"\0")
        if stat.S_ISREG(mode):
            before = path.stat(follow_symlinks=False)
            file_digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
                    file_digest.update(chunk)
            after = path.stat(follow_symlinks=False)
            before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            if before_identity != after_identity:
                raise UpdateError(f"file changed during update verification: {relative}")
            digest.update(str(after.st_size).encode("ascii") + b"\0" + file_digest.digest())
    return digest.hexdigest()


_VALIDATION_METHODS = (
    "list_sources",
    "list_fragments",
    "list_artifacts",
    "list_scopes",
    "list_works",
    "list_decisions",
    "list_contributions",
    "list_contribution_review_receipts",
    "list_review_receipts",
    "list_federation_feedback",
    "list_stewardship",
    "list_custody_events",
    "list_observations",
    "list_claims",
    "list_contradiction_cases",
    "list_concepts",
    "list_relations",
    "list_review_candidates",
    "list_promotions",
    "list_adjudications",
    "list_snapshots",
)

_STORE_FAMILIES = tuple(method.removeprefix("list_") for method in _VALIDATION_METHODS)


def _validate_store(store_dir: Path, *, allow_partial: bool = False) -> dict[str, int]:
    present_families = {name for name in _STORE_FAMILIES if (store_dir / name).is_dir()}
    has_records = any(
        any((store_dir / name).glob("*.json"))
        for name in present_families
    )
    if len(present_families) != len(_STORE_FAMILIES) and not (allow_partial and has_records):
        raise UpdateError(
            "directory does not have the complete GroundRecall record-family layout; "
            "only use --allow-partial-store after verifying this is a legacy standalone canonical store"
        )
    store = GroundRecallStore(store_dir, create=False)
    counts: dict[str, int] = {}
    for method_name in _VALIDATION_METHODS:
        records = getattr(store, method_name)()
        counts[method_name.removeprefix("list_")] = len(records)
    return counts


def _read_format(store: Path) -> int:
    try:
        return check_store_compatibility(store)
    except IncompatibleStoreVersionError as exc:
        raise UpdateError(str(exc)) from exc


def _plan_unlocked(store: Path, *, allow_partial: bool = False) -> dict[str, Any]:
    version = _read_format(store)
    counts = _validate_store(store, allow_partial=allow_partial)
    migrations: list[dict[str, Any]] = []
    if version == 0:
        migrations.append({
            "id": INITIAL_UPDATE_ID,
            "target_store_format_version": 1,
            "description": (
                "Add a store-format manifest for future compatibility checks; "
                "typed records, relations and indexes are not rewritten."
            ),
        })
    return {
        "report_kind": "groundrecall_update_plan",
        "software_version": _software_version(),
        "store_path": str(store),
        "current_store_format_version": version,
        "supported_store_format_version": SUPPORTED_STORE_FORMAT_VERSION,
        "record_counts": counts,
        "pending_updates": migrations,
        "update_available": bool(migrations),
        "write_performed": False,
    }


def plan_update(store_dir: str | Path, *, allow_partial: bool = False) -> dict[str, Any]:
    """Read-only compatibility check and update plan."""

    store = _root(store_dir)
    with store_lock(store, exclusive=True):
        return _plan_unlocked(store, allow_partial=allow_partial)


def apply_update(
    store_dir: str | Path,
    backup_dir: str | Path,
    *,
    allow_partial: bool = False,
) -> dict[str, Any]:
    """Apply pending update steps after verifying an external store backup.

    The only registered step currently adds a version manifest. It is written
    atomically into the existing store directory; no directory is swapped and
    no existing store file is rewritten. The verified external backup is the
    rollback source and is retained permanently.
    """

    store = _root(store_dir)
    backup = Path(backup_dir).expanduser().resolve(strict=False)
    if backup == store or backup.is_relative_to(store) or store.is_relative_to(backup):
        raise UpdateError("backup path must be disjoint from the canonical store")

    with store_lock(store, exclusive=True):
        plan = _plan_unlocked(store, allow_partial=allow_partial)
        if not plan["update_available"]:
            return {
                "report_kind": "groundrecall_update_result",
                "store_path": str(store),
                "updated": False,
                "reason": "no pending updates",
                "backup_path": "",
                "write_performed": False,
            }

        if os.path.lexists(backup):
            raise UpdateError(f"backup already exists; choose a new path: {backup}")
        backup.parent.mkdir(parents=True, exist_ok=True)
        before_digest = _tree_digest(store)
        shutil.copytree(store, backup)
        try:
            backup.chmod(0o700)
        except OSError as exc:
            raise UpdateError(f"could not restrict backup directory permissions: {backup}") from exc
        backup_digest = _tree_digest(backup)
        if backup_digest != before_digest or _tree_digest(store) != before_digest:
            raise UpdateError(
                f"backup verification failed; original store was not modified; inspect {backup}"
            )

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{STORE_MANIFEST_NAME}.", suffix=".tmp", dir=store
        )
        temporary_manifest = Path(temporary_name)
        try:
            manifest = {
                "schema_version": STORE_MANIFEST_SCHEMA,
                "store_format_version": 1,
                "applied_updates": [INITIAL_UPDATE_ID],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(manifest, indent=2) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_manifest, store / STORE_MANIFEST_NAME)
            _fsync_directory(store)
            expected_counts = plan["record_counts"]
            actual_counts = _validate_store(store, allow_partial=allow_partial)
            if actual_counts != expected_counts:
                raise UpdateError("record-family counts changed during the update")
            check_store_compatibility(store)
            if _tree_digest(store, omit_manifest=True) != before_digest:
                raise UpdateError("existing store content changed during the update")

            return {
                "report_kind": "groundrecall_update_result",
                "store_path": str(store),
                "updated": True,
                "from_store_format_version": 0,
                "to_store_format_version": 1,
                "backup_path": str(backup),
                "record_counts": actual_counts,
                "canonical_records_rewritten": False,
                "write_performed": True,
            }
        finally:
            if temporary_manifest.exists():
                temporary_manifest.unlink()


def _fsync_directory(path: Path) -> None:
    if not hasattr(os, "O_DIRECTORY"):
        return
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def rollback_update(
    store_dir: str | Path,
    backup_dir: str | Path,
    *,
    allow_partial: bool = False,
) -> dict[str, Any]:
    """Remove this release's marker only when the external backup still matches."""

    store = _root(store_dir)
    backup = Path(backup_dir).expanduser().resolve(strict=True)
    if not backup.is_dir() or backup == store or backup.is_relative_to(store) or store.is_relative_to(backup):
        raise UpdateError("rollback backup must be a separate store directory outside STORE")
    with store_lock(store, exclusive=True):
        if _read_format(store) != 1:
            raise UpdateError("rollback requires a store at format version 1")
        if _read_format(backup) != 0:
            raise UpdateError("rollback backup is not an unversioned pre-update store")
        current_manifest = json.loads((store / STORE_MANIFEST_NAME).read_text(encoding="utf-8"))
        if current_manifest.get("applied_updates") != [INITIAL_UPDATE_ID]:
            raise UpdateError("refusing to remove a manifest with unrecognized applied updates")
        current_counts = _validate_store(store, allow_partial=allow_partial)
        backup_counts = _validate_store(backup, allow_partial=allow_partial)
        backup_digest = _tree_digest(backup)
        if current_counts != backup_counts or _tree_digest(store, omit_manifest=True) != backup_digest:
            raise UpdateError("store records changed since update; refusing rollback that could discard them")
        (store / STORE_MANIFEST_NAME).unlink()
        _fsync_directory(store)
        if _tree_digest(store) != backup_digest:
            raise UpdateError("rollback marker removal completed, but final verification differs from backup")
        return {
            "report_kind": "groundrecall_update_result",
            "store_path": str(store),
            "updated": False,
            "rolled_back": True,
            "backup_path": str(backup),
            "store_format_version": 0,
            "write_performed": True,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check or safely provision versioned GroundRecall store capabilities."
    )
    parser.add_argument("store", help="canonical store directory (not workspace root)")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="read-only compatibility and update plan (default)")
    action.add_argument("--apply", action="store_true", help="apply pending store updates")
    action.add_argument(
        "--rollback-from",
        metavar="BACKUP",
        help="remove this update's marker only if STORE still matches the verified pre-update backup",
    )
    parser.add_argument("--backup", help="new, protected backup directory outside STORE; required with --apply")
    parser.add_argument(
        "--confirm-stopped",
        action="store_true",
        help="confirm all GroundRecall writers/readers using STORE are stopped",
    )
    parser.add_argument(
        "--allow-partial-store",
        action="store_true",
        help="allow a legacy standalone store missing record-family directories after manual target verification",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.apply:
        if not args.backup:
            raise SystemExit("groundrecall update --apply requires --backup PATH")
        if not args.confirm_stopped:
            raise SystemExit("groundrecall update --apply requires --confirm-stopped")
    elif args.rollback_from:
        if args.backup:
            raise SystemExit("--backup is not valid with --rollback-from")
        if not args.confirm_stopped:
            raise SystemExit("groundrecall update --rollback-from requires --confirm-stopped")
    elif args.backup or args.confirm_stopped:
        raise SystemExit("--backup and --confirm-stopped are only valid with --apply")

    try:
        if args.apply:
            result = apply_update(args.store, args.backup, allow_partial=args.allow_partial_store)
        elif args.rollback_from:
            result = rollback_update(args.store, args.rollback_from, allow_partial=args.allow_partial_store)
        else:
            result = plan_update(args.store, allow_partial=args.allow_partial_store)
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"groundrecall update: {exc}") from exc
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
