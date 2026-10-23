"""Deterministic, content-addressed inventories for GroundRecall workspaces."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Any, Iterator


INVENTORY_SCHEMA = "groundrecall.workspace-inventory.v1"
SUMMARY_SCHEMA = "groundrecall.workspace-inventory-summary.v1"
READ_JSON_LIMIT = 16 * 1024 * 1024

FAMILY_ID_FIELDS = {
    "adjudications": "adjudication_id",
    "artifacts": "artifact_id",
    "claims": "claim_id",
    "concepts": "concept_id",
    "contradiction_cases": "case_id",
    "contribution_review_receipts": "receipt_id",
    "contributions": "contribution_id",
    "custody_events": "event_id",
    "decisions": "decision_id",
    "federation_feedback": "feedback_id",
    "fragments": "fragment_id",
    "observations": "observation_id",
    "promotions": "promotion_id",
    "relations": "relation_id",
    "review_candidates": "review_candidate_id",
    "review_receipts": "receipt_id",
    "scopes": "scope_id",
    "snapshots": "snapshot_id",
    "sources": "source_id",
    "stewardship": "stewardship_id",
    "works": "work_id",
}


class InventoryError(RuntimeError):
    """Raised when a stable inventory cannot be produced."""


@dataclass(frozen=True)
class InventoryResult:
    entry_count: int
    file_count: int
    directory_count: int
    symlink_count: int
    total_file_bytes: int
    inventory_sha256: str
    role_counts: dict[str, int]


def _canonical_line(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def _file_sha256(path: Path) -> tuple[str, int]:
    before = path.stat(follow_symlinks=False)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat(follow_symlinks=False)
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after:
        raise InventoryError(f"file changed while hashing: {path}")
    return digest.hexdigest(), after.st_size


def _load_small_json(path: Path) -> dict[str, Any] | None:
    try:
        if path.stat().st_size > READ_JSON_LIMIT:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _bundle_roots(root: Path) -> dict[Path, str]:
    bundles: dict[Path, str] = {}
    for manifest in root.rglob("manifest.json"):
        if manifest.is_symlink() or not manifest.is_file():
            continue
        payload = _load_small_json(manifest)
        import_id = str((payload or {}).get("import_id", "")).strip()
        if import_id:
            bundles[manifest.parent] = import_id
    return bundles


def _bundle_for(path: Path, bundles: dict[Path, str]) -> tuple[Path, str] | None:
    candidates = ((bundle, import_id) for bundle, import_id in bundles.items() if path.is_relative_to(bundle))
    return max(candidates, key=lambda item: len(item[0].parts), default=None)


def _family_for(relative: Path) -> tuple[str, str] | None:
    parts = relative.parts
    if not parts:
        return None
    if parts[0] in FAMILY_ID_FIELDS:
        return parts[0], "workspace_typed_record"
    if len(parts) > 1 and parts[0] == "store" and parts[1] in FAMILY_ID_FIELDS:
        return parts[1], "canonical_typed_record"
    return None


def _role_for(relative: Path, bundle: tuple[Path, str] | None, root: Path) -> str:
    parts = relative.parts
    if not parts:
        return "workspace_root"
    family = _family_for(relative)
    if family:
        return family[1]
    if bundle:
        bundle_relative = bundle[0].relative_to(root)
        bundle_parts = bundle_relative.parts
        if bundle_parts and bundle_parts[0] == "imports":
            return "registered_import_bundle"
        if bundle_parts and bundle_parts[0] == "store":
            return "store_legacy_import_bundle"
        return "workspace_root_import_bundle"
    first = parts[0]
    if first == ".index" or (first == "store" and len(parts) > 1 and parts[1] == ".index"):
        return "derived_index"
    if first == "exports":
        return "derived_export"
    if first.startswith("store-backup-"):
        return "dated_backup"
    if first == "notebook-seed-store":
        return "seed_store"
    if first == "source-notes":
        return "source_note"
    if first in {"local-inbox", "remote-inbox"}:
        return first.replace("-", "_")
    if first == "logs":
        return "private_run_log"
    if first == "store":
        return "canonical_store_support"
    if first == "imports":
        return "imports_support"
    if len(parts) == 1:
        return "workspace_configuration"
    return "unclassified_workspace_entry"


def _typed_metadata(path: Path, relative: Path, entry_type: str) -> tuple[str, str, str]:
    family = _family_for(relative)
    if not family or entry_type != "file" or path.suffix != ".json":
        return "", "", ""
    family_name = family[0]
    payload = None if family_name == "snapshots" else _load_small_json(path)
    stable_id = str((payload or {}).get(FAMILY_ID_FIELDS[family_name], "")).strip()
    if not stable_id:
        stable_id = path.stem
    status = str((payload or {}).get("current_status", "")).strip()
    return family_name, stable_id, status


def _walk(root: Path) -> Iterator[Path]:
    paths: list[Path] = []
    for directory, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        base = Path(directory)
        for name in directory_names:
            paths.append(base / name)
        for name in file_names:
            paths.append(base / name)
    yield from sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def inventory_workspace(root: Path, output: Path, summary_output: Path | None = None) -> InventoryResult:
    root = root.resolve()
    output = output.resolve()
    summary_output = summary_output.resolve() if summary_output else None
    if not root.is_dir():
        raise InventoryError(f"workspace is not a directory: {root}")
    for destination in (output, summary_output):
        if destination and destination.is_relative_to(root):
            raise InventoryError(f"inventory output must be outside the inventoried workspace: {destination}")

    bundles = _bundle_roots(root)
    counts: Counter[str] = Counter()
    roles: Counter[str] = Counter()
    total_bytes = 0
    inventory_digest = hashlib.sha256()
    output.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            for path in _walk(root):
                relative = path.relative_to(root)
                mode = path.lstat().st_mode
                if stat.S_ISLNK(mode):
                    entry_type = "symlink"
                    target = os.readlink(path)
                    content_hash = hashlib.sha256(target.encode("utf-8", errors="surrogateescape")).hexdigest()
                    size = len(target.encode("utf-8", errors="surrogateescape"))
                elif stat.S_ISDIR(mode):
                    entry_type = "directory"
                    content_hash = ""
                    size = 0
                elif stat.S_ISREG(mode):
                    entry_type = "file"
                    content_hash, size = _file_sha256(path)
                    total_bytes += size
                else:
                    entry_type = "other"
                    content_hash = ""
                    size = 0
                bundle = _bundle_for(path, bundles)
                family, stable_id, lifecycle_status = _typed_metadata(path, relative, entry_type)
                record = {
                    "schema_version": INVENTORY_SCHEMA,
                    "relative_path": relative.as_posix(),
                    "entry_type": entry_type,
                    "mode": format(stat.S_IMODE(mode), "04o"),
                    "byte_size": size,
                    "sha256": content_hash,
                    "role": _role_for(relative, bundle, root),
                    "record_family": family,
                    "stable_id": stable_id,
                    "lifecycle_status": lifecycle_status,
                    "import_id": bundle[1] if bundle else "",
                }
                line = _canonical_line(record)
                handle.write(line)
                inventory_digest.update(line)
                counts[entry_type] += 1
                roles[record["role"]] += 1
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, output)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise

    result = InventoryResult(
        entry_count=sum(counts.values()),
        file_count=counts["file"],
        directory_count=counts["directory"],
        symlink_count=counts["symlink"],
        total_file_bytes=total_bytes,
        inventory_sha256=inventory_digest.hexdigest(),
        role_counts=dict(sorted(roles.items())),
    )
    if summary_output:
        summary_output.parent.mkdir(parents=True, exist_ok=True)
        summary = {
            "schema_version": SUMMARY_SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "workspace_root": str(root),
            **result.__dict__,
        }
        _atomic_json(summary_output, summary)
    return result


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def compare_inventories(first: Path, second: Path) -> dict[str, Any]:
    def load(path: Path) -> dict[str, dict[str, Any]]:
        records: dict[str, dict[str, Any]] = {}
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                record = json.loads(line)
                relative_path = record["relative_path"]
                if relative_path in records:
                    raise InventoryError(f"duplicate path in {path}:{line_number}: {relative_path}")
                records[relative_path] = record
        return records

    left = load(first)
    right = load(second)
    left_paths = set(left)
    right_paths = set(right)
    changed = sorted(path for path in left_paths & right_paths if left[path] != right[path])
    return {
        "equal": not (left_paths ^ right_paths or changed),
        "first_entry_count": len(left),
        "second_entry_count": len(right),
        "only_in_first": sorted(left_paths - right_paths),
        "only_in_second": sorted(right_paths - left_paths),
        "changed": changed,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inventory = subparsers.add_parser("create", help="create a deterministic JSONL inventory")
    inventory.add_argument("root", type=Path)
    inventory.add_argument("output", type=Path)
    inventory.add_argument("--summary", type=Path)
    compare = subparsers.add_parser("compare", help="compare two inventory JSONL files")
    compare.add_argument("first", type=Path)
    compare.add_argument("second", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "create":
            result = inventory_workspace(arguments.root, arguments.output, arguments.summary)
            print(json.dumps(result.__dict__, sort_keys=True))
            return 0
        comparison = compare_inventories(arguments.first, arguments.second)
        print(json.dumps(comparison, indent=2, sort_keys=True))
        return 0 if comparison["equal"] else 1
    except (InventoryError, OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"workspace inventory error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
