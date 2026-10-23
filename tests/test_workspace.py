from __future__ import annotations

import json
from pathlib import Path

import pytest

from groundrecall.ingest import run_groundrecall_import
from groundrecall.models import ClaimRecord
from groundrecall.promotion import promote_import_to_store
from groundrecall.store import GroundRecallStore
from groundrecall.workspace import (
    WORKSPACE_MANIFEST_NAME,
    WorkspaceConfigurationError,
    load_workspace_layout,
    require_canonical_store_target,
    require_imports_root_target,
    workspace_manifest_payload,
)


def _write_manifest(workspace: Path, **overrides: object) -> Path:
    workspace.mkdir(parents=True, exist_ok=True)
    payload = workspace_manifest_payload(workspace_id="test-workspace")
    payload.update(overrides)
    path = workspace / WORKSPACE_MANIFEST_NAME
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def test_workspace_manifest_resolves_distinct_authority_paths(tmp_path: Path) -> None:
    workspace = tmp_path / "groundrecall"
    _write_manifest(workspace)

    layout = load_workspace_layout(workspace)

    assert layout.canonical_store == workspace / "store"
    assert layout.imports == workspace / "imports"
    assert layout.source_notes == workspace / "source-notes"
    assert layout.notes_index != layout.canonical_index != layout.unified_index


def test_workspace_manifest_rejects_paths_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "groundrecall"
    _write_manifest(workspace, canonical_store="../outside")

    with pytest.raises(WorkspaceConfigurationError, match="escapes the workspace"):
        load_workspace_layout(workspace)


def test_manifested_workspace_guards_import_and_canonical_targets(tmp_path: Path) -> None:
    workspace = tmp_path / "groundrecall"
    _write_manifest(workspace)

    assert require_canonical_store_target(workspace / "store") == (workspace / "store").resolve()
    assert require_imports_root_target(workspace / "imports") == (workspace / "imports").resolve()
    with pytest.raises(WorkspaceConfigurationError, match="Refusing canonical-store mutation"):
        require_canonical_store_target(workspace)
    with pytest.raises(WorkspaceConfigurationError, match="Refusing import output"):
        require_imports_root_target(workspace)


def test_promotion_rejects_workspace_root_before_creating_store_directories(tmp_path: Path) -> None:
    workspace = tmp_path / "groundrecall"
    _write_manifest(workspace)

    with pytest.raises(WorkspaceConfigurationError, match="configured canonical store"):
        promote_import_to_store(tmp_path / "missing-import", workspace)

    assert not (workspace / "claims").exists()
    assert not (workspace / "snapshots").exists()


def test_store_constructor_rejects_manifested_workspace_root(tmp_path: Path) -> None:
    workspace = tmp_path / "groundrecall"
    _write_manifest(workspace)

    with pytest.raises(WorkspaceConfigurationError, match="typed-store mutation at workspace root"):
        GroundRecallStore(workspace)

    assert not (workspace / "claims").exists()

    read_only_store = GroundRecallStore(workspace, create=False)
    with pytest.raises(WorkspaceConfigurationError, match="typed-store mutation at workspace root"):
        read_only_store.save_claim(ClaimRecord(claim_id="wrong_root", claim_text="Blocked"))


def test_import_rejects_workspace_root_before_writing_bundle(tmp_path: Path) -> None:
    workspace = tmp_path / "groundrecall"
    _write_manifest(workspace)
    source = tmp_path / "source"
    (source / "wiki").mkdir(parents=True)
    (source / "wiki" / "note.md").write_text("# Note\n\n- A claim.\n", encoding="utf-8")

    with pytest.raises(WorkspaceConfigurationError, match="configured imports root"):
        run_groundrecall_import(source, out_root=workspace, import_id="wrong-root")

    assert not (workspace / "wrong-root").exists()
