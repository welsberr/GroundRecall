from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from groundrecall.reconcile_imports import ImportReconciliationError, apply_plan, create_plan, verify_plan
from groundrecall.workspace import workspace_manifest_payload


def _json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _bundle(path: Path, import_id: str, fragment_id: str) -> None:
    _json(path / "manifest.json", {"import_id": import_id})
    (path / "fragments.jsonl").write_text(json.dumps({"fragment_id": fragment_id}) + "\n", encoding="utf-8")
    (path / "nested").mkdir()
    (path / "nested" / "payload.txt").write_text("payload", encoding="utf-8")


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _json(workspace / "workspace.json", workspace_manifest_payload(workspace_id="test-workspace"))
    for directory in ("store", "imports", "source-notes", "logs"):
        (workspace / directory).mkdir()
    _json(
        workspace / "store" / "claims" / "claim-1.json",
        {"claim_id": "claim-1", "supporting_fragment_ids": ["fragment-root", "fragment-store"]},
    )
    _bundle(workspace / "root-bundle", "root-bundle", "fragment-root")
    _bundle(workspace / "store" / "store-bundle", "store-bundle", "fragment-store")
    backup_workspace = tmp_path / "backup-workspace"
    shutil.copytree(workspace, backup_workspace)
    receipt = tmp_path / "backup-receipt.json"
    _json(
        receipt,
        {
            "backup_workspace": str(backup_workspace),
            "copy": {"source_after_equals_backup": True, "inventory_sha256": "digest"},
        },
    )
    return workspace, receipt


def test_plan_apply_verify_is_copy_first_and_idempotent(tmp_path: Path) -> None:
    workspace, backup_receipt = _workspace(tmp_path)
    plan = create_plan(workspace, backup_receipt)
    assert plan["bundle_count"] == 2
    assert plan["workspace_root_bundle_count"] == 1
    assert plan["canonical_store_bundle_count"] == 1
    plan_path = tmp_path / "plan.json"
    _json(plan_path, plan)

    receipt = apply_plan(workspace, plan_path)
    assert receipt["copied_count"] == 2
    assert receipt["source_bundles_preserved_and_verified"] is True
    assert receipt["fragment_coverage"]["missing_canonical_fragment_id_count"] == 0
    assert (workspace / "root-bundle").is_dir()
    assert (workspace / "store" / "store-bundle").is_dir()
    assert (workspace / "imports" / "root-bundle").is_dir()
    assert (workspace / "imports" / "store-bundle").is_dir()

    repeated = apply_plan(workspace, plan_path)
    assert repeated["copied_count"] == 0
    assert repeated["already_present_count"] == 2
    assert verify_plan(workspace, plan_path)["valid"] is True


def test_apply_preflight_rejects_changed_source_before_any_copy(tmp_path: Path) -> None:
    workspace, backup_receipt = _workspace(tmp_path)
    plan = create_plan(workspace, backup_receipt)
    plan_path = tmp_path / "plan.json"
    _json(plan_path, plan)
    (workspace / "root-bundle" / "nested" / "payload.txt").write_text("changed", encoding="utf-8")

    with pytest.raises(ImportReconciliationError, match="does not match plan"):
        apply_plan(workspace, plan_path)
    assert not (workspace / "imports" / "root-bundle").exists()
    assert not (workspace / "imports" / "store-bundle").exists()


def test_plan_rejects_divergent_existing_destination(tmp_path: Path) -> None:
    workspace, backup_receipt = _workspace(tmp_path)
    _bundle(workspace / "imports" / "root-bundle", "root-bundle", "different-fragment")
    with pytest.raises(ImportReconciliationError, match="divergent destination"):
        create_plan(workspace, backup_receipt)
