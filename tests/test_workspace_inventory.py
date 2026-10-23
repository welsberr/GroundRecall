from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from groundrecall.workspace_inventory import InventoryError, compare_inventories, inventory_workspace


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_inventory_is_deterministic_and_classifies_records_and_imports(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write_json(
        workspace / "claims" / "claim-1.json",
        {"claim_id": "claim-1", "current_status": "reviewed", "claim_text": "evidence"},
    )
    _write_json(workspace / "imports" / "bundle-1" / "manifest.json", {"import_id": "bundle-1"})
    (workspace / "imports" / "bundle-1" / "payload.txt").write_text("payload", encoding="utf-8")
    (workspace / "empty").mkdir()
    os.symlink("payload.txt", workspace / "imports" / "bundle-1" / "payload-link")

    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    summary = tmp_path / "summary.json"
    result = inventory_workspace(workspace, first, summary)
    inventory_workspace(workspace, second)

    assert result.inventory_sha256
    assert first.read_bytes() == second.read_bytes()
    assert compare_inventories(first, second)["equal"] is True
    records = [json.loads(line) for line in first.read_text(encoding="utf-8").splitlines()]
    claim = next(record for record in records if record["relative_path"] == "claims/claim-1.json")
    payload = next(
        record for record in records if record["relative_path"] == "imports/bundle-1/payload.txt"
    )
    assert claim["role"] == "workspace_typed_record"
    assert claim["record_family"] == "claims"
    assert claim["stable_id"] == "claim-1"
    assert claim["lifecycle_status"] == "reviewed"
    assert payload["role"] == "registered_import_bundle"
    assert payload["import_id"] == "bundle-1"
    assert json.loads(summary.read_text(encoding="utf-8"))["entry_count"] == len(records)
    assert oct(first.stat().st_mode & 0o777) == "0o600"


def test_compare_reports_changed_added_and_removed_paths(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "same").write_text("same", encoding="utf-8")
    (workspace / "changed").write_text("before", encoding="utf-8")
    (workspace / "removed").write_text("removed", encoding="utf-8")
    before = tmp_path / "before.jsonl"
    inventory_workspace(workspace, before)

    (workspace / "changed").write_text("after", encoding="utf-8")
    (workspace / "removed").unlink()
    (workspace / "added").write_text("added", encoding="utf-8")
    after = tmp_path / "after.jsonl"
    inventory_workspace(workspace, after)

    comparison = compare_inventories(before, after)
    assert comparison["equal"] is False
    assert comparison["only_in_first"] == ["removed"]
    assert comparison["only_in_second"] == ["added"]
    assert comparison["changed"] == ["changed"]


def test_inventory_rejects_output_inside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(InventoryError, match="outside"):
        inventory_workspace(workspace, workspace / "inventory.jsonl")
