"""GroundRecall session integration for portable lede-brief packages.

The module is intentionally provider-neutral.  It records what was prepared and
requested for delivery; an assistant adapter must provide evidence that content
was actually loaded or compacted.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class CoverageState(BaseModel):
    collection_unit_ids: list[str] = Field(default_factory=list)
    required_unit_ids: list[str] = Field(default_factory=list)
    loaded_unit_ids: list[str] = Field(default_factory=list)
    loaded_status: str = "unconfirmed"
    inventory_id: str = ""
    package_id: str = ""


class ContextObservation(BaseModel):
    current_input_tokens: int | None = None
    context_capacity_tokens: int | None = None
    projected_next_turn_tokens: int | None = None
    estimated_continuation_cost: float | None = None
    estimated_prepare_cost: float | None = None
    estimated_reload_cost: float | None = None
    pressure: bool = False
    quality: str = "unknown"


class ContextAdvice(BaseModel):
    action: str
    reason: str
    projected_headroom_tokens: int | None = None
    expected_savings: float | None = None
    coverage: CoverageState
    assumptions: list[str] = Field(default_factory=list)


class ContextCheckpoint(BaseModel):
    schema_version: str = "groundrecall.context-checkpoint.v1"
    checkpoint_id: str = Field(default_factory=lambda: f"checkpoint-{uuid.uuid4().hex}")
    session_id: str
    task_id: str = ""
    workspace_binding: dict[str, Any] = Field(default_factory=dict)
    objective: str
    constraints: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    file_references: list[str] = Field(default_factory=list)
    verification_results: list[str] = Field(default_factory=list)
    pending_work: list[str] = Field(default_factory=list)
    next_action: str = ""
    coverage: CoverageState = Field(default_factory=CoverageState)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class LoadedBriefPackage(BaseModel):
    package_id: str
    package_path: str
    inventory_id: str
    source_id: str
    source_version: str = ""
    collection_unit_ids: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    coverage_status: str = "candidate"


def load_ledebrief_package(
    package_dir: str | Path,
    *,
    required_unit_ids: list[str] | None = None,
    loaded_unit_ids: list[str] | None = None,
    delivery_status: str = "unconfirmed",
) -> tuple[LoadedBriefPackage, CoverageState]:
    root = Path(package_dir).expanduser().resolve(strict=True)
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"lede-brief manifest not found: {manifest_path}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    inventory = payload.get("inventory") if isinstance(payload, dict) else None
    if not isinstance(inventory, dict):
        raise ValueError("lede-brief manifest has no inventory")
    units = inventory.get("units") or []
    collection_ids = sorted(str(unit.get("unit_id")) for unit in units if isinstance(unit, dict) and unit.get("unit_id"))
    artifacts: list[str] = []
    for artifact in payload.get("artifacts", []) or []:
        if not isinstance(artifact, dict):
            continue
        document_id = str(artifact.get("document_id", ""))
        if not document_id:
            continue
        target = (root / f"{document_id}.md").resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise ValueError(f"lede-brief artifact is missing or escapes package: {document_id}")
        artifacts.append(str(target))
    package_id = f"{payload.get('source_id', '')}:{payload.get('source_version', '')}:{inventory.get('inventory_id', '')}"
    package = LoadedBriefPackage(
        package_id=package_id,
        package_path=str(root),
        inventory_id=str(inventory.get("inventory_id", "")),
        source_id=str(payload.get("source_id", "")),
        source_version=str(payload.get("source_version", "")),
        collection_unit_ids=collection_ids,
        artifacts=artifacts,
        coverage_status=str(payload.get("status", "candidate")),
    )
    required = sorted(set(required_unit_ids or collection_ids))
    missing = sorted(set(required) - set(collection_ids))
    if missing:
        raise ValueError(f"required lede-brief units are absent from package: {', '.join(missing)}")
    loaded = sorted(set(loaded_unit_ids or []))
    coverage = CoverageState(
        collection_unit_ids=collection_ids,
        required_unit_ids=required,
        loaded_unit_ids=loaded,
        loaded_status=delivery_status,
        inventory_id=package.inventory_id,
        package_id=package.package_id,
    )
    return package, coverage


def advise_context(observation: ContextObservation, coverage: CoverageState) -> ContextAdvice:
    headroom = None
    if observation.context_capacity_tokens is not None and observation.current_input_tokens is not None:
        projected = observation.projected_next_turn_tokens or 0
        headroom = observation.context_capacity_tokens - observation.current_input_tokens - projected
    pressure = observation.pressure or (headroom is not None and headroom < 0)
    prepare = observation.estimated_prepare_cost
    reload = observation.estimated_reload_cost or 0.0
    continuation = observation.estimated_continuation_cost
    expected = None
    if continuation is not None and prepare is not None:
        expected = continuation - prepare - reload
    assumptions = ["loaded coverage is based only on supplied delivery evidence"]
    if observation.quality == "unknown":
        assumptions.append("provider occupancy or billing data is incomplete")
    if pressure:
        return ContextAdvice(
            action="checkpoint-and-reduce",
            reason="projected context headroom is insufficient or the runtime reports pressure",
            projected_headroom_tokens=headroom,
            expected_savings=expected,
            coverage=coverage,
            assumptions=assumptions,
        )
    if expected is not None and expected > 0:
        return ContextAdvice(
            action="prepare-context-package",
            reason="estimated continuation cost exceeds preparation and reload cost",
            projected_headroom_tokens=headroom,
            expected_savings=expected,
            coverage=coverage,
            assumptions=assumptions,
        )
    return ContextAdvice(
        action="continue",
        reason="no measured pressure or positive preparation break-even signal",
        projected_headroom_tokens=headroom,
        expected_savings=expected,
        coverage=coverage,
        assumptions=assumptions,
    )


def write_checkpoint(checkpoint: ContextCheckpoint, destination: str | Path) -> Path:
    path = Path(destination).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(checkpoint.model_dump_json(indent=2))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return path
