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
from threading import Lock
from typing import Any, Literal

from pydantic import BaseModel, Field

from .policy import RELEASE_RANK, PolicyDecision, PolicyDecisionProvider, PolicyRequest, compose_policy_decisions

HANDOFF_SCHEMA_VERSION = "groundrecall.assistant_handoff.v1"
HandoffStatus = Literal["proposed", "accepted", "executing", "blocked", "completed"]
HandoffEventType = Literal["status", "progress", "result"]
_HANDOFF_LOCK = Lock()
_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "proposed": frozenset({"accepted", "blocked"}),
    "accepted": frozenset({"executing", "blocked"}),
    "executing": frozenset({"blocked", "completed"}),
    "blocked": frozenset({"accepted", "executing", "completed"}),
    "completed": frozenset(),
}


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


class HandoffEvent(BaseModel):
    """Append-only operational event linked to a governed handoff."""

    schema_version: str = "groundrecall.assistant_handoff_event.v1"
    event_id: str
    event_type: HandoffEventType
    handoff_id: str
    task_id: str
    subject_id: str = ""
    realm_id: str = ""
    release_level: str = "private"
    status: str = ""
    state: str = ""
    observations: list[str] = Field(default_factory=list)
    next_action: str = ""
    outcome: str = ""
    changes: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    next_safe_action: str = ""
    provenance: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = ""
    created_at: str


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


def _events_path(store_dir: str | Path, handoff_id: str) -> Path:
    safe = "".join(ch for ch in handoff_id if ch.isalnum() or ch in "-_.:")
    if not safe or safe != handoff_id:
        raise ValueError("handoff_id contains unsupported characters")
    return _directory(store_dir) / f"{safe}.events.jsonl"


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


def list_handoff_events(store_dir: str | Path, handoff_id: str, *, subject_id: str = "", realm_id: str = "", maximum_release_level: str = "private", limit: int = 100) -> list[HandoffEvent]:
    item = get_handoff(store_dir, handoff_id, subject_id=subject_id, realm_id=realm_id, maximum_release_level=maximum_release_level)
    if item is None:
        return []
    path = _events_path(store_dir, handoff_id)
    events: list[HandoffEvent] = []
    if not path.exists():
        return events
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = HandoffEvent.model_validate_json(line)
        except (ValueError, TypeError):
            continue
        if event.subject_id != item.subject_id or event.realm_id != item.realm_id:
            continue
        events.append(event)
        if len(events) >= max(1, min(limit, 500)):
            break
    return events


def _append_event(store_dir: str | Path, event: HandoffEvent) -> None:
    path = _events_path(store_dir, event.handoff_id)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(event.model_dump_json() + "\n")


def _event_idempotent(store_dir: str | Path, handoff_id: str, key: str, *, subject_id: str, realm_id: str) -> HandoffEvent | None:
    if not key:
        return None
    for event in list_handoff_events(store_dir, handoff_id, subject_id=subject_id, realm_id=realm_id, limit=500):
        if event.idempotency_key == key:
            return event
    return None


def _handoff_policy(policy_provider: PolicyDecisionProvider | None, *, action: str, handoff: AssistantHandoff, status: str = "") -> PolicyDecision:
    request = PolicyRequest(
        decision_point="act" if action == "handoff_update_status" else "propose",
        subject_id=handoff.subject_id, action=action, record_kind="assistant_handoff",
        record_id=handoff.handoff_id, scope_id=handoff.project,
        release_level=handoff.release_level, target_release_level=handoff.release_level,
        durable_memory_change=False,
        metadata={"groundrecall.realm_id": handoff.realm_id, "groundrecall.handoff_status": status},
    )
    return policy_provider.evaluate(request) if policy_provider else compose_policy_decisions([], request=request)


def update_handoff_status(store_dir: str | Path, handoff_id: str, status: str, *, policy_provider: PolicyDecisionProvider | None = None, subject_id: str = "", realm_id: str = "", maximum_release_level: str = "private", expected_status: str = "", idempotency_key: str = "", provenance: dict[str, Any] | None = None) -> HandoffResult:
    if status not in _STATUS_TRANSITIONS:
        raise ValueError(f"unsupported handoff status: {status}")
    with _HANDOFF_LOCK:
        item = get_handoff(store_dir, handoff_id, subject_id=subject_id, realm_id=realm_id, maximum_release_level=maximum_release_level)
        if item is None:
            raise ValueError("handoff not found")
        existing = _event_idempotent(store_dir, handoff_id, idempotency_key, subject_id=item.subject_id, realm_id=item.realm_id)
        decision = _handoff_policy(policy_provider, action="handoff_update_status", handoff=item, status=status)
        if decision.decision in {"deny", "hard_gate"}:
            raise PermissionError("policy blocked handoff status update")
        if existing is not None:
            return HandoffResult(handoff=item, policy_decision=decision)
        if expected_status and item.status != expected_status:
            raise ValueError(f"handoff status conflict: expected {expected_status}, found {item.status}")
        if status != item.status and status not in _STATUS_TRANSITIONS[item.status]:
            raise ValueError(f"invalid handoff status transition: {item.status} -> {status}")
        now = _now()
        event = HandoffEvent(event_id=f"event-{uuid.uuid4().hex[:16]}", event_type="status", handoff_id=item.handoff_id, task_id=item.task_id, subject_id=item.subject_id, realm_id=item.realm_id, release_level=item.release_level, status=status, provenance=dict(provenance or {}), idempotency_key=idempotency_key, created_at=now)
        item.status = status  # type: ignore[assignment]
        item.updated_at = now
        target = _path(store_dir, handoff_id)
        target.write_text(item.model_dump_json(indent=2) + "\n", encoding="utf-8")
        _append_event(store_dir, event)
        return HandoffResult(handoff=item, policy_decision=decision)


def append_handoff_progress(store_dir: str | Path, handoff_id: str, *, state: str = "", observations: list[str] | None = None, next_action: str = "", policy_provider: PolicyDecisionProvider | None = None, subject_id: str = "", realm_id: str = "", maximum_release_level: str = "private", idempotency_key: str = "", provenance: dict[str, Any] | None = None) -> HandoffEvent:
    return _append_handoff_event(store_dir, handoff_id, event_type="progress", policy_provider=policy_provider, subject_id=subject_id, realm_id=realm_id, maximum_release_level=maximum_release_level, idempotency_key=idempotency_key, state=state, observations=list(observations or []), next_action=next_action, provenance=dict(provenance or {}))


def propose_handoff_result(store_dir: str | Path, handoff_id: str, *, outcome: str = "", changes: list[str] | None = None, tests: list[str] | None = None, artifacts: list[str] | None = None, unresolved: list[str] | None = None, next_safe_action: str = "", policy_provider: PolicyDecisionProvider | None = None, subject_id: str = "", realm_id: str = "", maximum_release_level: str = "private", idempotency_key: str = "", provenance: dict[str, Any] | None = None) -> HandoffEvent:
    return _append_handoff_event(store_dir, handoff_id, event_type="result", policy_provider=policy_provider, subject_id=subject_id, realm_id=realm_id, maximum_release_level=maximum_release_level, idempotency_key=idempotency_key, outcome=outcome, changes=list(changes or []), tests=list(tests or []), artifacts=list(artifacts or []), unresolved=list(unresolved or []), next_safe_action=next_safe_action, provenance=dict(provenance or {}))


def _append_handoff_event(store_dir: str | Path, handoff_id: str, *, event_type: HandoffEventType, policy_provider: PolicyDecisionProvider | None, subject_id: str, realm_id: str, maximum_release_level: str, idempotency_key: str, **fields: Any) -> HandoffEvent:
    with _HANDOFF_LOCK:
        item = get_handoff(store_dir, handoff_id, subject_id=subject_id, realm_id=realm_id, maximum_release_level=maximum_release_level)
        if item is None:
            raise ValueError("handoff not found")
        existing = _event_idempotent(store_dir, handoff_id, idempotency_key, subject_id=item.subject_id, realm_id=item.realm_id)
        decision = _handoff_policy(policy_provider, action="progress_append" if event_type == "progress" else "result_propose", handoff=item)
        if decision.decision in {"deny", "hard_gate"}:
            raise PermissionError(f"policy blocked handoff {event_type} append")
        if existing is not None:
            return existing
        event = HandoffEvent(event_id=f"event-{uuid.uuid4().hex[:16]}", event_type=event_type, handoff_id=item.handoff_id, task_id=item.task_id, subject_id=item.subject_id, realm_id=item.realm_id, release_level=item.release_level, idempotency_key=idempotency_key, created_at=_now(), **fields)
        _append_event(store_dir, event)
        return event


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
