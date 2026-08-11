"""Governed cross-assistant task handoff records.

Handoffs are durable proposals kept outside the canonical institutional record
set.  They provide a small, auditable contract between assistants without
granting either assistant unrestricted canonical writes or host execution.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .policy import RELEASE_RANK, PolicyDecision, PolicyDecisionProvider, PolicyRequest, compose_policy_decisions

HANDOFF_SCHEMA_VERSION = "groundrecall.assistant_handoff.v1"
HandoffStatus = Literal["proposed", "accepted", "executing", "blocked", "completed"]


class AssistantHandoff(BaseModel):
    schema_version: str = HANDOFF_SCHEMA_VERSION
    handoff_id: str
    task_id: str
    project: str
    objective: str
    constraints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    context_refs: list[str] = Field(default_factory=list)
    requested_action: str = ""
    status: HandoffStatus = "proposed"
    from_surface: str = ""
    to_surface: str = ""
    host_id: str = ""
    subject_id: str = ""
    realm_id: str = ""
    release_level: str = "private"
    provenance: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = ""
    created_at: str
    updated_at: str


class HandoffResult(BaseModel):
    schema_version: str = "groundrecall.assistant_handoff_result.v1"
    handoff: AssistantHandoff
    writes_performed: bool = True
    canonical_write: bool = False
    policy_decision: PolicyDecision


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _directory(store_dir: str | Path) -> Path:
    path = Path(store_dir) / "handoffs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _path(store_dir: str | Path, handoff_id: str) -> Path:
    safe = "".join(ch for ch in handoff_id if ch.isalnum() or ch in "-_.:")
    if not safe or safe != handoff_id:
        raise ValueError("handoff_id contains unsupported characters")
    return _directory(store_dir) / f"{safe}.json"


def _read(path: Path) -> AssistantHandoff:
    return AssistantHandoff.model_validate_json(path.read_text(encoding="utf-8"))


def list_handoffs(store_dir: str | Path, *, subject_id: str = "", realm_id: str = "", project: str = "", status: str = "", maximum_release_level: str = "private", limit: int = 20) -> list[AssistantHandoff]:
    records: list[AssistantHandoff] = []
    for path in sorted(_directory(store_dir).glob("*.json"), key=lambda p: p.name):
        try:
            item = _read(path)
        except (OSError, ValueError):
            continue
        if subject_id and item.subject_id != subject_id:
            continue
        if realm_id and item.realm_id != realm_id:
            continue
        if project and item.project != project:
            continue
        if status and item.status != status:
            continue
        if RELEASE_RANK.get(item.release_level, 99) > RELEASE_RANK.get(maximum_release_level, RELEASE_RANK["private"]):
            continue
        records.append(item)
        if len(records) >= max(1, min(limit, 100)):
            break
    return records


def get_handoff(store_dir: str | Path, handoff_id: str, *, subject_id: str = "", realm_id: str = "", maximum_release_level: str = "private") -> AssistantHandoff | None:
    path = _path(store_dir, handoff_id)
    if not path.exists():
        return None
    item = _read(path)
    if subject_id and item.subject_id != subject_id:
        return None
    if realm_id and item.realm_id != realm_id:
        return None
    if RELEASE_RANK.get(item.release_level, 99) > RELEASE_RANK.get(maximum_release_level, RELEASE_RANK["private"]):
        return None
    return item


def propose_handoff(store_dir: str | Path, *, policy_provider: PolicyDecisionProvider | None = None, **fields: Any) -> HandoffResult:
    subject_id = str(fields.get("subject_id", ""))
    realm_id = str(fields.get("realm_id", ""))
    release_level = str(fields.get("release_level", "private"))
    request = PolicyRequest(
        decision_point="propose", subject_id=subject_id, action="handoff_propose",
        record_kind="assistant_handoff", record_id=str(fields.get("task_id", "")),
        scope_id=str(fields.get("project", "")), target_release_level=release_level,
        durable_memory_change=False, metadata={"groundrecall.realm_id": realm_id},
    )
    decision = policy_provider.evaluate(request) if policy_provider else compose_policy_decisions([], request=request)
    if decision.decision in {"deny", "hard_gate"}:
        raise PermissionError("policy blocked handoff proposal")
    idem = str(fields.get("idempotency_key", ""))
    if idem:
        for existing in list_handoffs(store_dir, subject_id=subject_id, realm_id=realm_id, limit=100):
            if existing.idempotency_key == idem:
                return HandoffResult(handoff=existing, policy_decision=decision)
    now = _now()
    task_id = str(fields.get("task_id") or f"gr-task-{uuid.uuid4().hex[:12]}")
    handoff_id = str(fields.get("handoff_id") or f"handoff-{uuid.uuid4().hex[:16]}")
    item = AssistantHandoff(
        handoff_id=handoff_id, task_id=task_id, project=str(fields.get("project", "")),
        objective=str(fields.get("objective", "")), constraints=list(fields.get("constraints", []) or []),
        acceptance_criteria=list(fields.get("acceptance_criteria", []) or []), context_refs=list(fields.get("context_refs", []) or []),
        requested_action=str(fields.get("requested_action", "")), from_surface=str(fields.get("from_surface", "")),
        to_surface=str(fields.get("to_surface", "")), host_id=str(fields.get("host_id", "")), subject_id=subject_id,
        realm_id=realm_id, release_level=release_level, provenance=dict(fields.get("provenance", {}) or {}),
        idempotency_key=idem, created_at=now, updated_at=now,
    )
    target = _path(store_dir, handoff_id)
    target.write_text(item.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return HandoffResult(handoff=item, policy_decision=decision)
