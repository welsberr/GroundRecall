from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Literal


WORKSPACE_MANIFEST_NAME = "workspace.json"
WORKSPACE_SCHEMA_VERSION = "groundrecall.workspace.v1"
SearchScopeName = Literal["notes", "canonical", "unified"]


class WorkspaceConfigurationError(ValueError):
    """Raised when a GroundRecall workspace or target violates its manifest."""


@dataclass(frozen=True)
class WorkspaceLayout:
    workspace: Path
    workspace_id: str
    canonical_store: Path
    imports: Path
    source_notes: Path
    notes_index: Path
    canonical_index: Path
    unified_index: Path
    private_runs: Path
    manifest_path: Path


def load_workspace_layout(workspace: str | Path) -> WorkspaceLayout:
    root = Path(workspace).resolve()
    manifest_path = root / WORKSPACE_MANIFEST_NAME
    if not manifest_path.is_file():
        raise WorkspaceConfigurationError(f"GroundRecall workspace manifest not found: {manifest_path}")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkspaceConfigurationError(f"Invalid GroundRecall workspace manifest: {manifest_path}") from exc
    if payload.get("schema_version") != WORKSPACE_SCHEMA_VERSION:
        raise WorkspaceConfigurationError(
            f"Unsupported GroundRecall workspace schema: {payload.get('schema_version')!r}"
        )
    workspace_id = str(payload.get("workspace_id", "")).strip()
    if not workspace_id:
        raise WorkspaceConfigurationError("GroundRecall workspace_id must be non-empty")
    indexes = payload.get("indexes")
    if not isinstance(indexes, dict):
        raise WorkspaceConfigurationError("GroundRecall workspace indexes must be an object")
    layout = WorkspaceLayout(
        workspace=root,
        workspace_id=workspace_id,
        canonical_store=_resolve_member(root, payload.get("canonical_store"), "canonical_store"),
        imports=_resolve_member(root, payload.get("imports"), "imports"),
        source_notes=_resolve_member(root, payload.get("source_notes"), "source_notes"),
        notes_index=_resolve_member(root, indexes.get("notes"), "indexes.notes"),
        canonical_index=_resolve_member(root, indexes.get("canonical"), "indexes.canonical"),
        unified_index=_resolve_member(root, indexes.get("unified"), "indexes.unified"),
        private_runs=_resolve_member(root, payload.get("private_runs"), "private_runs"),
        manifest_path=manifest_path,
    )
    if layout.canonical_store == root:
        raise WorkspaceConfigurationError("canonical_store must not be the workspace root")
    if layout.imports == root:
        raise WorkspaceConfigurationError("imports must not be the workspace root")
    if layout.source_notes == root:
        raise WorkspaceConfigurationError("source_notes must not be the workspace root")
    index_paths = {layout.notes_index, layout.canonical_index, layout.unified_index}
    if len(index_paths) != 3:
        raise WorkspaceConfigurationError("notes, canonical, and unified indexes must use distinct paths")
    return layout


def discover_workspace_layout(target: str | Path) -> WorkspaceLayout | None:
    path = Path(target).resolve()
    candidates = [path, *path.parents]
    for candidate in candidates:
        if (candidate / WORKSPACE_MANIFEST_NAME).is_file():
            return load_workspace_layout(candidate)
    return None


def require_canonical_store_target(store_dir: str | Path) -> Path:
    target = Path(store_dir).resolve()
    layout = discover_workspace_layout(target)
    if layout is not None and target != layout.canonical_store:
        raise WorkspaceConfigurationError(
            f"Refusing canonical-store mutation at {target}; configured canonical store is {layout.canonical_store}"
        )
    return target


def require_store_not_workspace_root(store_dir: str | Path) -> Path:
    target = Path(store_dir).resolve()
    layout = discover_workspace_layout(target)
    if layout is not None and target == layout.workspace:
        raise WorkspaceConfigurationError(
            f"Refusing typed-store mutation at workspace root {target}; use a declared store role"
        )
    return target


def require_imports_root_target(imports_root: str | Path) -> Path:
    target = Path(imports_root).resolve()
    layout = discover_workspace_layout(target)
    if layout is not None and target != layout.imports:
        raise WorkspaceConfigurationError(
            f"Refusing import output at {target}; configured imports root is {layout.imports}"
        )
    return target


def workspace_manifest_payload(
    *,
    workspace_id: str,
    canonical_store: str = "store",
    imports: str = "imports",
    source_notes: str = "source-notes",
    notes_index: str = ".index/groundrecall-notes.sqlite",
    canonical_index: str = "store/.index/groundrecall-search.sqlite",
    unified_index: str = ".index/groundrecall-unified.sqlite",
    private_runs: str = "logs",
) -> dict[str, Any]:
    return {
        "schema_version": WORKSPACE_SCHEMA_VERSION,
        "workspace_id": workspace_id,
        "canonical_store": canonical_store,
        "imports": imports,
        "source_notes": source_notes,
        "indexes": {
            "notes": notes_index,
            "canonical": canonical_index,
            "unified": unified_index,
        },
        "private_runs": private_runs,
    }


def _resolve_member(root: Path, value: Any, field: str) -> Path:
    text = str(value or "").strip()
    if not text:
        raise WorkspaceConfigurationError(f"GroundRecall workspace field {field} must be non-empty")
    candidate = Path(text)
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if not resolved.is_relative_to(root):
        raise WorkspaceConfigurationError(f"GroundRecall workspace field {field} escapes the workspace")
    return resolved
