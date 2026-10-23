"""Copy-first normalization of misplaced GroundRecall import bundles."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from typing import Any

from .workspace import WorkspaceConfigurationError, load_workspace_layout


PLAN_SCHEMA = "groundrecall.import-reconciliation-plan.v1"
RECEIPT_SCHEMA = "groundrecall.import-reconciliation-receipt.v1"


class ImportReconciliationError(RuntimeError):
    """Raised when import custody cannot be normalized without ambiguity."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> tuple[str, int]:
    before = path.stat(follow_symlinks=False)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat(follow_symlinks=False)
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise ImportReconciliationError(f"file changed while hashing: {path}")
    return digest.hexdigest(), after.st_size


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _tree_inventory(bundle: Path) -> tuple[list[dict[str, Any]], str]:
    entries: list[dict[str, Any]] = []
    for directory, directory_names, file_names in os.walk(bundle, topdown=True, followlinks=False):
        base = Path(directory)
        for name in [*directory_names, *file_names]:
            path = base / name
            relative = path.relative_to(bundle).as_posix()
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                entry_type = "symlink"
                target = os.readlink(path)
                encoded = target.encode("utf-8", errors="surrogateescape")
                size = len(encoded)
                digest = hashlib.sha256(encoded).hexdigest()
            elif stat.S_ISDIR(mode):
                entry_type = "directory"
                size = 0
                digest = ""
            elif stat.S_ISREG(mode):
                entry_type = "file"
                digest, size = _sha256_file(path)
            else:
                raise ImportReconciliationError(f"unsupported filesystem entry in bundle: {path}")
            entries.append(
                {
                    "relative_path": relative,
                    "entry_type": entry_type,
                    "mode": format(stat.S_IMODE(mode), "04o"),
                    "byte_size": size,
                    "sha256": digest,
                }
            )
    entries.sort(key=lambda entry: entry["relative_path"])
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(_canonical_bytes(entry) + b"\n")
    return entries, digest.hexdigest()


def _read_manifest(bundle: Path) -> dict[str, Any]:
    try:
        payload = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ImportReconciliationError(f"invalid import manifest: {bundle / 'manifest.json'}") from exc
    if not isinstance(payload, dict):
        raise ImportReconciliationError(f"import manifest must be an object: {bundle / 'manifest.json'}")
    return payload


def _validate_import_id(import_id: str, bundle: Path) -> None:
    if not import_id or import_id in {".", ".."} or Path(import_id).name != import_id:
        raise ImportReconciliationError(f"unsafe import_id {import_id!r} in {bundle}")
    if bundle.name != import_id:
        raise ImportReconciliationError(
            f"bundle directory {bundle.name!r} does not match manifest import_id {import_id!r}"
        )


def _source_bundles(workspace: Path, canonical_store: Path) -> list[tuple[str, Path]]:
    candidates: list[tuple[str, Path]] = []
    for child in workspace.iterdir():
        if child.is_dir() and not child.is_symlink() and (child / "manifest.json").is_file():
            candidates.append(("workspace_root", child))
    for child in canonical_store.iterdir():
        if child.is_dir() and not child.is_symlink() and (child / "manifest.json").is_file():
            candidates.append(("canonical_store", child))
    return sorted(candidates, key=lambda item: (item[0], item[1].name))


def create_plan(workspace: Path, backup_receipt: Path) -> dict[str, Any]:
    layout = load_workspace_layout(workspace)
    backup_receipt = backup_receipt.resolve()
    try:
        backup_payload = json.loads(backup_receipt.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ImportReconciliationError(f"invalid backup receipt: {backup_receipt}") from exc
    if not backup_payload.get("copy", {}).get("source_after_equals_backup"):
        raise ImportReconciliationError("backup receipt does not attest source/backup equality")
    backup_workspace_text = str(backup_payload.get("backup_workspace", "")).strip()
    backup_workspace = Path(backup_workspace_text).resolve() if backup_workspace_text else None
    if backup_workspace is None or not backup_workspace.is_dir():
        raise ImportReconciliationError("backup receipt does not resolve to an available backup workspace")

    bundles: list[dict[str, Any]] = []
    import_ids: set[str] = set()
    for source_role, source in _source_bundles(layout.workspace, layout.canonical_store):
        manifest = _read_manifest(source)
        import_id = str(manifest.get("import_id", "")).strip()
        _validate_import_id(import_id, source)
        if import_id in import_ids:
            raise ImportReconciliationError(f"duplicate reconciliation source import_id: {import_id}")
        import_ids.add(import_id)
        destination = layout.imports / import_id
        if not destination.resolve().is_relative_to(layout.imports):
            raise ImportReconciliationError(f"destination escapes imports root: {destination}")
        entries, tree_sha256 = _tree_inventory(source)
        backup_source = (backup_workspace / source.relative_to(layout.workspace)).resolve()
        if not backup_source.is_relative_to(backup_workspace):
            raise ImportReconciliationError(f"backup source path escapes backup workspace: {source}")
        if not backup_source.is_dir() or backup_source.is_symlink():
            raise ImportReconciliationError(f"bundle is absent from verified backup: {source}")
        backup_entries, backup_tree_sha256 = _tree_inventory(backup_source)
        if backup_entries != entries or backup_tree_sha256 != tree_sha256:
            raise ImportReconciliationError(f"live bundle differs from verified backup: {source}")
        destination_state = "absent"
        if destination.exists():
            if not destination.is_dir() or destination.is_symlink():
                raise ImportReconciliationError(f"destination is not a regular directory: {destination}")
            destination_entries, destination_hash = _tree_inventory(destination)
            if destination_entries != entries:
                raise ImportReconciliationError(f"divergent destination already exists: {destination}")
            if destination_hash != tree_sha256:
                raise ImportReconciliationError(f"destination digest mismatch: {destination}")
            destination_state = "identical_existing"
        bundles.append(
            {
                "import_id": import_id,
                "source_role": source_role,
                "source_relative": source.relative_to(layout.workspace).as_posix(),
                "destination_relative": destination.relative_to(layout.workspace).as_posix(),
                "destination_state": destination_state,
                "verified_against_backup": True,
                "tree_sha256": tree_sha256,
                "file_count": sum(entry["entry_type"] == "file" for entry in entries),
                "directory_count": sum(entry["entry_type"] == "directory" for entry in entries),
                "symlink_count": sum(entry["entry_type"] == "symlink" for entry in entries),
                "file_bytes": sum(entry["byte_size"] for entry in entries if entry["entry_type"] == "file"),
                "entries": entries,
            }
        )
    return {
        "schema_version": PLAN_SCHEMA,
        "created_at": _now(),
        "workspace_id": layout.workspace_id,
        "backup_receipt": str(backup_receipt),
        "backup_receipt_sha256": _sha256_file(backup_receipt)[0],
        "backup_inventory_sha256": backup_payload.get("copy", {}).get("inventory_sha256", ""),
        "backup_workspace": str(backup_workspace),
        "operation": "copy-first import custody normalization; preserve all sources",
        "bundle_count": len(bundles),
        "workspace_root_bundle_count": sum(bundle["source_role"] == "workspace_root" for bundle in bundles),
        "canonical_store_bundle_count": sum(bundle["source_role"] == "canonical_store" for bundle in bundles),
        "file_count": sum(bundle["file_count"] for bundle in bundles),
        "file_bytes": sum(bundle["file_bytes"] for bundle in bundles),
        "bundles": sorted(bundles, key=lambda bundle: bundle["import_id"]),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _load_plan(path: Path) -> dict[str, Any]:
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ImportReconciliationError(f"invalid reconciliation plan: {path}") from exc
    if not isinstance(plan, dict) or plan.get("schema_version") != PLAN_SCHEMA:
        raise ImportReconciliationError(f"unsupported reconciliation plan: {path}")
    return plan


def _planned_entries(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    entries = bundle.get("entries")
    if not isinstance(entries, list):
        raise ImportReconciliationError(f"plan bundle has no entry inventory: {bundle.get('import_id')}")
    return entries


def _resolve_planned_member(root: Path, relative: str, expected_parent: Path | None = None) -> Path:
    candidate = (root / relative).resolve()
    parent = expected_parent.resolve() if expected_parent else root.resolve()
    if not candidate.is_relative_to(parent):
        raise ImportReconciliationError(f"planned path escapes its authority root: {relative}")
    return candidate


def _verify_bundle(path: Path, planned: dict[str, Any]) -> None:
    if not path.is_dir() or path.is_symlink():
        raise ImportReconciliationError(f"bundle directory is missing or unsafe: {path}")
    entries, tree_sha256 = _tree_inventory(path)
    if entries != _planned_entries(planned) or tree_sha256 != planned.get("tree_sha256"):
        raise ImportReconciliationError(f"bundle does not match plan: {path}")


def _fragment_coverage(workspace: Path, canonical_store: Path, imports: Path) -> dict[str, Any]:
    available: set[str] = set()
    import_bundle_count = 0
    for bundle in sorted(imports.iterdir()):
        if not bundle.is_dir() or bundle.is_symlink() or not (bundle / "manifest.json").is_file():
            continue
        import_bundle_count += 1
        fragments = bundle / "fragments.jsonl"
        if not fragments.is_file():
            continue
        with fragments.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    fragment_id = str(json.loads(line).get("fragment_id", "")).strip()
                except json.JSONDecodeError as exc:
                    raise ImportReconciliationError(f"invalid fragment JSONL: {fragments}:{line_number}") from exc
                if fragment_id:
                    available.add(fragment_id)
    referenced: set[str] = set()
    for claim_path in sorted((canonical_store / "claims").glob("*.json")):
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        referenced.update(str(item) for item in claim.get("supporting_fragment_ids", []) if str(item))
    missing = sorted(referenced - available)
    return {
        "registered_import_bundle_count": import_bundle_count,
        "registered_fragment_id_count": len(available),
        "canonical_claim_fragment_id_count": len(referenced),
        "missing_canonical_fragment_ids": missing,
        "missing_canonical_fragment_id_count": len(missing),
    }


def apply_plan(workspace: Path, plan_path: Path) -> dict[str, Any]:
    layout = load_workspace_layout(workspace)
    plan_path = plan_path.resolve()
    plan = _load_plan(plan_path)
    if plan.get("workspace_id") != layout.workspace_id:
        raise ImportReconciliationError("plan workspace_id does not match the target workspace")
    backup_receipt = Path(str(plan.get("backup_receipt", ""))).resolve()
    if not backup_receipt.is_file() or _sha256_file(backup_receipt)[0] != plan.get("backup_receipt_sha256"):
        raise ImportReconciliationError("verified backup receipt is missing or changed")

    resolved: list[tuple[dict[str, Any], Path, Path, str]] = []
    seen_destinations: set[Path] = set()
    for bundle in plan.get("bundles", []):
        source = _resolve_planned_member(layout.workspace, str(bundle.get("source_relative", "")))
        destination = _resolve_planned_member(
            layout.workspace, str(bundle.get("destination_relative", "")), layout.imports
        )
        if destination in seen_destinations:
            raise ImportReconciliationError(f"plan repeats destination: {destination}")
        seen_destinations.add(destination)
        _verify_bundle(source, bundle)
        state = "absent"
        if destination.exists():
            _verify_bundle(destination, bundle)
            state = "identical_existing"
        resolved.append((bundle, source, destination, state))

    started_at = _now()
    actions: list[dict[str, Any]] = []
    layout.private_runs.mkdir(parents=True, exist_ok=True)
    for bundle, source, destination, state in resolved:
        action = "already_present"
        if state == "absent":
            staging_root = Path(tempfile.mkdtemp(prefix=".r0c-stage-", dir=layout.private_runs))
            staged_bundle = staging_root / str(bundle["import_id"])
            try:
                shutil.copytree(source, staged_bundle, symlinks=True, copy_function=shutil.copy2)
                _verify_bundle(staged_bundle, bundle)
                if destination.exists():
                    raise ImportReconciliationError(f"destination appeared during copy: {destination}")
                os.replace(staged_bundle, destination)
                _verify_bundle(destination, bundle)
                action = "copied"
            finally:
                shutil.rmtree(staging_root, ignore_errors=True)
        actions.append(
            {
                "import_id": bundle["import_id"],
                "action": action,
                "source_relative": bundle["source_relative"],
                "destination_relative": bundle["destination_relative"],
                "tree_sha256": bundle["tree_sha256"],
            }
        )

    for bundle, source, destination, _state in resolved:
        _verify_bundle(source, bundle)
        _verify_bundle(destination, bundle)
    coverage = _fragment_coverage(layout.workspace, layout.canonical_store, layout.imports)
    if coverage["missing_canonical_fragment_id_count"]:
        raise ImportReconciliationError("canonical claim fragment references remain unresolved")
    return {
        "schema_version": RECEIPT_SCHEMA,
        "started_at": started_at,
        "completed_at": _now(),
        "workspace_id": layout.workspace_id,
        "plan_path": str(plan_path),
        "plan_sha256": _sha256_file(plan_path)[0],
        "backup_receipt": str(backup_receipt),
        "bundle_count": len(actions),
        "copied_count": sum(action["action"] == "copied" for action in actions),
        "already_present_count": sum(action["action"] == "already_present" for action in actions),
        "source_bundles_preserved_and_verified": True,
        "destinations_verified": True,
        "fragment_coverage": coverage,
        "actions": actions,
        "scope_guardrail": "copy only; source bundles preserved; no typed records changed",
    }


def verify_plan(workspace: Path, plan_path: Path) -> dict[str, Any]:
    layout = load_workspace_layout(workspace)
    plan = _load_plan(plan_path)
    verified = 0
    for bundle in plan.get("bundles", []):
        source = _resolve_planned_member(layout.workspace, str(bundle.get("source_relative", "")))
        destination = _resolve_planned_member(
            layout.workspace, str(bundle.get("destination_relative", "")), layout.imports
        )
        _verify_bundle(source, bundle)
        _verify_bundle(destination, bundle)
        verified += 1
    coverage = _fragment_coverage(layout.workspace, layout.canonical_store, layout.imports)
    return {
        "verified_bundle_count": verified,
        "sources_preserved": True,
        "destinations_match": True,
        "fragment_coverage": coverage,
        "valid": coverage["missing_canonical_fragment_id_count"] == 0,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan", help="write a read-only itemized copy plan")
    plan.add_argument("workspace", type=Path)
    plan.add_argument("backup_receipt", type=Path)
    plan.add_argument("output", type=Path)
    apply = subparsers.add_parser("apply", help="apply an itemized plan without removing sources")
    apply.add_argument("workspace", type=Path)
    apply.add_argument("plan", type=Path)
    apply.add_argument("receipt", type=Path)
    verify = subparsers.add_parser("verify", help="verify sources, destinations, and fragment coverage")
    verify.add_argument("workspace", type=Path)
    verify.add_argument("plan", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "plan":
            payload = create_plan(arguments.workspace, arguments.backup_receipt)
            _write_json(arguments.output, payload)
        elif arguments.command == "apply":
            payload = apply_plan(arguments.workspace, arguments.plan)
            _write_json(arguments.receipt, payload)
        else:
            payload = verify_plan(arguments.workspace, arguments.plan)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload.get("valid", True) else 1
    except (ImportReconciliationError, WorkspaceConfigurationError, OSError, json.JSONDecodeError) as exc:
        print(f"import reconciliation error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
