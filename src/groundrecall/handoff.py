"""Governed cross-assistant task handoff records.

Handoffs are durable proposals kept outside the canonical institutional record
set.  They provide a small, auditable contract between assistants without
granting either assistant unrestricted canonical writes or host execution.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from pydantic import BaseModel, Field

from .policy import RELEASE_RANK, PolicyDecision, PolicyDecisionProvider, PolicyRequest, compose_policy_decisions

HANDOFF_SCHEMA_VERSION = "groundrecall.assistant_handoff.v1"
HandoffStatus = Literal["proposed", "accepted", "executing", "blocked", "completed"]
HandoffEventType = Literal["status", "progress", "result", "lease", "review", "review_appeal", "promotion_request", "promotion_confirmation", "promotion_action", "promotion_operator_receipt"]
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
    lease_id: str = ""
    lease_subject_id: str = ""
    lease_host_id: str = ""
    lease_expires_at: str = ""


class HandoffResult(BaseModel):
    schema_version: str = "groundrecall.assistant_handoff_result.v1"
    handoff: AssistantHandoff
    writes_performed: bool = True
    canonical_write: bool = False
    policy_decision: PolicyDecision
    lease_id: str = ""
    lease_expires_at: str = ""
    lease_released: bool = False


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
    result_ref: str = ""
    reviewer_subject_id: str = ""
    review_decision: str = ""
    rationale: str = ""
    promotion_target: str = ""
    requester_subject_id: str = ""
    lease_id: str = ""
    lease_subject_id: str = ""
    lease_host_id: str = ""
    lease_expires_at: str = ""
    lease_action: str = ""
    provenance: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = ""
    created_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lease_is_active(item: AssistantHandoff, *, now: datetime | None = None) -> bool:
    if not item.lease_id or not item.lease_expires_at:
        return False
    try:
        expires = datetime.fromisoformat(item.lease_expires_at)
    except ValueError:
        return False
    current = now or datetime.now(timezone.utc)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires > current


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


def _transaction_path(store_dir: str | Path, handoff_id: str) -> Path:
    safe = "".join(ch for ch in handoff_id if ch.isalnum() or ch in "-_.:")
    if not safe or safe != handoff_id:
        raise ValueError("handoff_id contains unsupported characters")
    return _directory(store_dir) / f"{safe}.txn"


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        # Some filesystems (and test doubles) do not permit directory fsync;
        # file-level fsync and atomic replace still provide safe recovery.
        return


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _event_present(path: Path, event_id: str) -> bool:
    if not path.exists():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            if HandoffEvent.model_validate_json(line).event_id == event_id:
                return True
        except (ValueError, TypeError):
            continue
    return False


def _recover_pending(store_dir: str | Path, handoff_id: str) -> None:
    """Complete an interrupted status/lease transaction on the next read."""
    transaction = _transaction_path(store_dir, handoff_id)
    if not transaction.exists():
        return
    try:
        payload = json.loads(transaction.read_text(encoding="utf-8"))
        item = AssistantHandoff.model_validate(payload["handoff"])
        event_payload = payload.get("event")
        event = HandoffEvent.model_validate(event_payload) if event_payload else None
    except (OSError, ValueError, TypeError, KeyError):
        # Leave malformed journals in place for operator inspection; do not
        # turn a read into an unsafe destructive recovery operation.
        return
    _atomic_write(_path(store_dir, handoff_id), item.model_dump_json(indent=2) + "\n")
    if event is not None:
        events_path = _events_path(store_dir, handoff_id)
        if not _event_present(events_path, event.event_id):
            _append_event(store_dir, event)
    transaction.unlink(missing_ok=True)
    _fsync_directory(transaction.parent)


def _read(path: Path) -> AssistantHandoff:
    return AssistantHandoff.model_validate_json(path.read_text(encoding="utf-8"))


def list_handoffs(store_dir: str | Path, *, subject_id: str = "", realm_id: str = "", project: str = "", host_id: str = "", status: str = "", maximum_release_level: str = "private", limit: int = 20) -> list[AssistantHandoff]:
    records: list[AssistantHandoff] = []
    for transaction in _directory(store_dir).glob("*.txn"):
        _recover_pending(store_dir, transaction.name.removesuffix(".txn"))
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
        if host_id and item.host_id != host_id:
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
    _recover_pending(store_dir, handoff_id)
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
        stream.flush()
        os.fsync(stream.fileno())
    _fsync_directory(path.parent)


def _persist_mutation(store_dir: str | Path, item: AssistantHandoff, event: HandoffEvent) -> None:
    """Journal, atomically replace, and append one handoff mutation."""
    transaction = _transaction_path(store_dir, item.handoff_id)
    payload = json.dumps({"handoff": item.model_dump(mode="json"), "event": event.model_dump(mode="json")}, separators=(",", ":")) + "\n"
    _atomic_write(transaction, payload)
    _atomic_write(_path(store_dir, item.handoff_id), item.model_dump_json(indent=2) + "\n")
    events_path = _events_path(store_dir, item.handoff_id)
    if not _event_present(events_path, event.event_id):
        _append_event(store_dir, event)
    transaction.unlink(missing_ok=True)
    _fsync_directory(transaction.parent)


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
        _persist_mutation(store_dir, item, event)
        return HandoffResult(handoff=item, policy_decision=decision)


def accept_handoff(store_dir: str | Path, handoff_id: str, *, subject_id: str, host_id: str, project: str, policy_provider: PolicyDecisionProvider | None = None, realm_id: str = "", maximum_release_level: str = "private", expected_status: str = "proposed", idempotency_key: str = "", provenance: dict[str, Any] | None = None) -> HandoffResult:
    """Accept a proposed handoff only from its active, scoped lease owner."""
    with _HANDOFF_LOCK:
        item = get_handoff(store_dir, handoff_id, subject_id=subject_id, realm_id=realm_id, maximum_release_level=maximum_release_level)
        if item is None:
            raise ValueError("handoff not found")
        _validate_lease_scope(item, subject_id=subject_id, host_id=host_id, project=project)
        existing = _event_idempotent(store_dir, handoff_id, idempotency_key, subject_id=item.subject_id, realm_id=item.realm_id)
        decision = _handoff_policy(policy_provider, action="handoff_accept", handoff=item, status="accepted")
        if decision.decision in {"deny", "hard_gate"}:
            raise PermissionError("policy blocked handoff acceptance")
        if existing is not None and existing.event_type == "status" and existing.status == "accepted":
            return HandoffResult(handoff=item, policy_decision=decision, lease_id=item.lease_id, lease_expires_at=item.lease_expires_at)
        if item.status != expected_status:
            raise ValueError(f"handoff status conflict: expected {expected_status}, found {item.status}")
        if not _lease_is_active(item):
            raise PermissionError("handoff requires an active lease")
        if item.lease_subject_id != subject_id or item.lease_host_id != host_id:
            raise PermissionError("handoff lease owner does not match acceptance scope")
        now = _now()
        item.status = "accepted"
        item.updated_at = now
        event = HandoffEvent(event_id=f"event-{uuid.uuid4().hex[:16]}", event_type="status", handoff_id=item.handoff_id, task_id=item.task_id, subject_id=item.subject_id, realm_id=item.realm_id, release_level=item.release_level, status="accepted", lease_id=item.lease_id, lease_subject_id=subject_id, lease_host_id=host_id, lease_expires_at=item.lease_expires_at, provenance={**dict(provenance or {}), "accepted_by_host": host_id}, idempotency_key=idempotency_key, created_at=now)
        _persist_mutation(store_dir, item, event)
        return HandoffResult(handoff=item, policy_decision=decision, lease_id=item.lease_id, lease_expires_at=item.lease_expires_at)


def complete_handoff(store_dir: str | Path, handoff_id: str, *, subject_id: str, host_id: str, project: str, outcome: str = "", result_ref: str = "", policy_provider: PolicyDecisionProvider | None = None, realm_id: str = "", maximum_release_level: str = "private", expected_status: str = "executing", idempotency_key: str = "", provenance: dict[str, Any] | None = None) -> HandoffResult:
    """Complete a handoff with a lease-bound result reference or outcome."""
    if not outcome.strip() and not result_ref.strip():
        raise ValueError("handoff completion requires outcome or result_ref")
    if expected_status not in {"accepted", "executing"}:
        raise ValueError("handoff completion expected_status must be accepted or executing")
    with _HANDOFF_LOCK:
        item = get_handoff(store_dir, handoff_id, subject_id=subject_id, realm_id=realm_id, maximum_release_level=maximum_release_level)
        if item is None:
            raise ValueError("handoff not found")
        _validate_lease_scope(item, subject_id=subject_id, host_id=host_id, project=project)
        existing = _event_idempotent(store_dir, handoff_id, idempotency_key, subject_id=item.subject_id, realm_id=item.realm_id)
        decision = _handoff_policy(policy_provider, action="handoff_complete", handoff=item, status="completed")
        if decision.decision in {"deny", "hard_gate"}:
            raise PermissionError("policy blocked handoff completion")
        if existing is not None and existing.event_type == "status" and existing.status == "completed":
            return HandoffResult(handoff=item, policy_decision=decision, lease_id=item.lease_id, lease_expires_at=item.lease_expires_at)
        if item.status != expected_status:
            raise ValueError(f"handoff status conflict: expected {expected_status}, found {item.status}")
        if not _lease_is_active(item):
            raise PermissionError("handoff completion requires an active lease")
        if item.lease_subject_id != subject_id or item.lease_host_id != host_id:
            raise PermissionError("handoff lease owner does not match completion scope")
        now = _now()
        item.status = "completed"
        item.updated_at = now
        event = HandoffEvent(event_id=f"event-{uuid.uuid4().hex[:16]}", event_type="status", handoff_id=item.handoff_id, task_id=item.task_id, subject_id=item.subject_id, realm_id=item.realm_id, release_level=item.release_level, status="completed", outcome=outcome, result_ref=result_ref, lease_id=item.lease_id, lease_subject_id=subject_id, lease_host_id=host_id, lease_expires_at=item.lease_expires_at, provenance={**dict(provenance or {}), "completed_by_host": host_id}, idempotency_key=idempotency_key, created_at=now)
        _persist_mutation(store_dir, item, event)
        return HandoffResult(handoff=item, policy_decision=decision, lease_id=item.lease_id, lease_expires_at=item.lease_expires_at)


def review_handoff_result(store_dir: str | Path, handoff_id: str, *, reviewer_subject_id: str, project: str, decision: str, rationale: str = "", result_ref: str = "", policy_provider: PolicyDecisionProvider | None = None, realm_id: str = "", maximum_release_level: str = "private", expected_status: str = "completed", idempotency_key: str = "", provenance: dict[str, Any] | None = None) -> HandoffEvent:
    """Append a governed review decision without promoting canonical memory."""
    if decision not in {"accept", "reject", "defer"}:
        raise ValueError("review decision must be accept, reject, or defer")
    if not rationale.strip() and not result_ref.strip():
        raise ValueError("handoff review requires rationale or result_ref")
    with _HANDOFF_LOCK:
        item = get_handoff(store_dir, handoff_id, realm_id=realm_id, maximum_release_level=maximum_release_level)
        if item is None:
            raise ValueError("handoff not found")
        if not reviewer_subject_id or not project or project != item.project:
            raise PermissionError("handoff review scope does not match project")
        if item.realm_id != realm_id:
            raise PermissionError("handoff review scope does not match realm")
        existing = _event_idempotent(store_dir, handoff_id, idempotency_key, subject_id=item.subject_id, realm_id=item.realm_id)
        policy = _handoff_policy(policy_provider, action="handoff_review_result", handoff=item, status=item.status)
        if policy.decision in {"deny", "hard_gate"}:
            raise PermissionError("policy blocked handoff result review")
        if existing is not None and existing.event_type == "review":
            return existing
        if item.status != expected_status:
            raise ValueError(f"handoff status conflict: expected {expected_status}, found {item.status}")
        event = HandoffEvent(event_id=f"event-{uuid.uuid4().hex[:16]}", event_type="review", handoff_id=item.handoff_id, task_id=item.task_id, subject_id=item.subject_id, realm_id=item.realm_id, release_level=item.release_level, result_ref=result_ref, reviewer_subject_id=reviewer_subject_id, review_decision=decision, rationale=rationale, provenance=dict(provenance or {}), idempotency_key=idempotency_key, created_at=_now())
        _append_event(store_dir, event)
        return event


def request_handoff_promotion(store_dir: str | Path, handoff_id: str, *, requester_subject_id: str, project: str, promotion_target: str, rationale: str = "", result_ref: str = "", policy_provider: PolicyDecisionProvider | None = None, realm_id: str = "", maximum_release_level: str = "private", expected_status: str = "completed", idempotency_key: str = "", provenance: dict[str, Any] | None = None) -> HandoffEvent:
    """Request promotion after an accepted result review; never promotes itself."""
    if not promotion_target.strip():
        raise ValueError("promotion request requires promotion_target")
    if not rationale.strip() and not result_ref.strip():
        raise ValueError("promotion request requires rationale or result_ref")
    with _HANDOFF_LOCK:
        item = get_handoff(store_dir, handoff_id, realm_id=realm_id, maximum_release_level=maximum_release_level)
        if item is None:
            raise ValueError("handoff not found")
        if not requester_subject_id or not project or project != item.project or item.realm_id != realm_id:
            raise PermissionError("handoff promotion scope does not match")
        existing = _event_idempotent(store_dir, handoff_id, idempotency_key, subject_id=item.subject_id, realm_id=item.realm_id)
        policy = _handoff_policy(policy_provider, action="handoff_promotion_request", handoff=item, status=item.status)
        if policy.decision in {"deny", "hard_gate"}:
            raise PermissionError("policy blocked handoff promotion request")
        if existing is not None and existing.event_type == "promotion_request":
            return existing
        if item.status != expected_status:
            raise ValueError(f"handoff status conflict: expected {expected_status}, found {item.status}")
        events = list_handoff_events(store_dir, handoff_id, realm_id=realm_id, maximum_release_level=maximum_release_level, limit=500)
        if not any(event.event_type == "review" and event.review_decision == "accept" for event in events):
            raise PermissionError("handoff promotion requires an accepted result review")
        event = HandoffEvent(event_id=f"event-{uuid.uuid4().hex[:16]}", event_type="promotion_request", handoff_id=item.handoff_id, task_id=item.task_id, subject_id=item.subject_id, realm_id=item.realm_id, release_level=item.release_level, requester_subject_id=requester_subject_id, promotion_target=promotion_target, rationale=rationale, result_ref=result_ref, provenance=dict(provenance or {}), idempotency_key=idempotency_key, created_at=_now())
        _append_event(store_dir, event)
        return event


def confirm_handoff_promotion(store_dir: str | Path, handoff_id: str, *, requester_subject_id: str, project: str, promotion_target: str, confirm: bool, rationale: str = "", result_ref: str = "", policy_provider: PolicyDecisionProvider | None = None, realm_id: str = "", maximum_release_level: str = "private", expected_status: str = "completed", idempotency_key: str = "", provenance: dict[str, Any] | None = None) -> HandoffEvent:
    """Confirm a promotion request without performing canonical promotion."""
    if confirm is not True:
        raise PermissionError("explicit confirm=true is required")
    with _HANDOFF_LOCK:
        item = get_handoff(store_dir, handoff_id, realm_id=realm_id, maximum_release_level=maximum_release_level)
        if item is None:
            raise ValueError("handoff not found")
        if item.status != expected_status:
            raise ValueError(f"handoff status conflict: expected {expected_status}, found {item.status}")
        if not requester_subject_id or not project or project != item.project or item.realm_id != realm_id:
            raise PermissionError("handoff promotion confirmation scope does not match")
        events = list_handoff_events(store_dir, handoff_id, realm_id=realm_id, maximum_release_level=maximum_release_level, limit=500)
        if not any(event.event_type == "review" and event.review_decision == "accept" for event in events):
            raise PermissionError("promotion confirmation requires an accepted result review")
        requests = [event for event in events if event.event_type == "promotion_request" and event.requester_subject_id == requester_subject_id and event.promotion_target == promotion_target]
        if not requests:
            raise PermissionError("promotion confirmation requires a matching promotion request")
        existing = _event_idempotent(store_dir, handoff_id, idempotency_key, subject_id=item.subject_id, realm_id=item.realm_id)
        policy = _handoff_policy(policy_provider, action="handoff_promotion_confirm", handoff=item, status=item.status)
        if policy.decision in {"deny", "hard_gate"}:
            raise PermissionError("policy blocked handoff promotion confirmation")
        if existing is not None and existing.event_type == "promotion_confirmation":
            return existing
        event = HandoffEvent(event_id=f"event-{uuid.uuid4().hex[:16]}", event_type="promotion_confirmation", handoff_id=item.handoff_id, task_id=item.task_id, subject_id=item.subject_id, realm_id=item.realm_id, release_level=item.release_level, requester_subject_id=requester_subject_id, promotion_target=promotion_target, rationale=rationale, result_ref=result_ref, provenance={**dict(provenance or {}), "canonical_effect": "none"}, idempotency_key=idempotency_key, created_at=_now())
        _append_event(store_dir, event)
        return event


def apply_handoff_promotion_request(store_dir: str | Path, handoff_id: str, *, requester_subject_id: str, project: str, promotion_target: str, policy_provider: PolicyDecisionProvider | None = None, realm_id: str = "", maximum_release_level: str = "private", expected_status: str = "completed", idempotency_key: str = "", provenance: dict[str, Any] | None = None) -> HandoffEvent:
    """Record a bounded promotion action after explicit confirmation.

    This creates a quarantine/action receipt only; it does not mutate canonical
    records. A separate governed promotion API must consume the receipt.
    """
    with _HANDOFF_LOCK:
        item = get_handoff(store_dir, handoff_id, realm_id=realm_id, maximum_release_level=maximum_release_level)
        if item is None:
            raise ValueError("handoff not found")
        if item.status != expected_status or not requester_subject_id or project != item.project or item.realm_id != realm_id:
            raise PermissionError("handoff promotion action scope or status does not match")
        events = list_handoff_events(store_dir, handoff_id, realm_id=realm_id, maximum_release_level=maximum_release_level, limit=500)
        if not any(event.event_type == "promotion_confirmation" and event.requester_subject_id == requester_subject_id and event.promotion_target == promotion_target for event in events):
            raise PermissionError("promotion action requires a matching confirmation")
        existing = _event_idempotent(store_dir, handoff_id, idempotency_key, subject_id=item.subject_id, realm_id=item.realm_id)
        policy = _handoff_policy(policy_provider, action="handoff_promotion_apply", handoff=item, status=item.status)
        if policy.decision in {"deny", "hard_gate"}:
            raise PermissionError("policy blocked handoff promotion action")
        if existing is not None and existing.event_type == "promotion_action":
            return existing
        event = HandoffEvent(event_id=f"event-{uuid.uuid4().hex[:16]}", event_type="promotion_action", handoff_id=item.handoff_id, task_id=item.task_id, subject_id=item.subject_id, realm_id=item.realm_id, release_level=item.release_level, requester_subject_id=requester_subject_id, promotion_target=promotion_target, provenance={**dict(provenance or {}), "action_status": "quarantined", "canonical_effect": "none"}, idempotency_key=idempotency_key, created_at=_now())
        _append_event(store_dir, event)
        return event


def list_handoff_promotion_actions(store_dir: str | Path, *, subject_id: str = "", project: str = "", realm_id: str = "", maximum_release_level: str = "private", limit: int = 20) -> list[dict[str, Any]]:
    """Return bounded metadata-only promotion-action summaries."""
    summaries: list[dict[str, Any]] = []
    for item in list_handoffs(store_dir, realm_id=realm_id, project=project, maximum_release_level=maximum_release_level, limit=100):
        for event in list_handoff_events(store_dir, item.handoff_id, realm_id=realm_id, maximum_release_level=maximum_release_level, limit=500):
            if event.event_type != "promotion_action" or (subject_id and event.requester_subject_id != subject_id):
                continue
            summaries.append({"event_id": event.event_id, "handoff_id": event.handoff_id, "task_id": event.task_id, "project": item.project, "realm_id": event.realm_id, "release_level": event.release_level, "requester_subject_id": event.requester_subject_id, "promotion_target": event.promotion_target, "action_status": str(event.provenance.get("action_status", "quarantined")), "canonical_effect": str(event.provenance.get("canonical_effect", "none")), "created_at": event.created_at})
            if len(summaries) >= max(1, min(limit, 100)):
                return summaries
    return summaries


def consume_handoff_promotion_action(store_dir: str | Path, handoff_id: str, *, action_id: str, requester_subject_id: str, project: str, promotion_target: str, confirm: bool, policy_provider: PolicyDecisionProvider, realm_id: str = "", maximum_release_level: str = "private", idempotency_key: str = "", provenance: dict[str, Any] | None = None) -> HandoffEvent:
    """Operator-only consumption receipt; canonical promotion remains separate."""
    if not confirm:
        raise PermissionError("explicit confirm=true is required")
    with _HANDOFF_LOCK:
        item = get_handoff(store_dir, handoff_id, realm_id=realm_id, maximum_release_level=maximum_release_level)
        if item is None or item.project != project or item.realm_id != realm_id:
            raise PermissionError("promotion action scope does not match")
        events = list_handoff_events(store_dir, handoff_id, realm_id=realm_id, maximum_release_level=maximum_release_level, limit=500)
        action = next((event for event in events if event.event_type == "promotion_action" and event.event_id == action_id and event.requester_subject_id == requester_subject_id and event.promotion_target == promotion_target), None)
        if action is None:
            raise PermissionError("matching quarantined promotion action is required")
        if not any(event.event_type == "promotion_confirmation" and event.requester_subject_id == requester_subject_id and event.promotion_target == promotion_target for event in events):
            raise PermissionError("promotion action requires confirmation")
        existing = _event_idempotent(store_dir, handoff_id, idempotency_key, subject_id=item.subject_id, realm_id=item.realm_id)
        decision = _handoff_policy(policy_provider, action="handoff_promotion_consume", handoff=item, status=item.status)
        if decision.decision in {"deny", "hard_gate"}:
            raise PermissionError("policy blocked operator promotion consumption")
        if existing is not None and existing.event_type == "promotion_operator_receipt":
            return existing
        receipt = HandoffEvent(event_id=f"event-{uuid.uuid4().hex[:16]}", event_type="promotion_operator_receipt", handoff_id=item.handoff_id, task_id=item.task_id, subject_id=item.subject_id, realm_id=item.realm_id, release_level=item.release_level, requester_subject_id=requester_subject_id, promotion_target=promotion_target, provenance={**dict(provenance or {}), "action_id": action_id, "canonical_effect": "none", "operator_receipt": True}, idempotency_key=idempotency_key, created_at=_now())
        _append_event(store_dir, receipt)
        return receipt


def appeal_handoff_review(store_dir: str | Path, handoff_id: str, *, requester_subject_id: str, project: str, target_review_event_id: str, rationale: str = "", result_ref: str = "", policy_provider: PolicyDecisionProvider | None = None, realm_id: str = "", maximum_release_level: str = "private", idempotency_key: str = "", provenance: dict[str, Any] | None = None) -> HandoffEvent:
    """Append an appeal/correction request for an existing review decision."""
    if not rationale.strip() and not result_ref.strip():
        raise ValueError("review appeal requires rationale or result_ref")
    with _HANDOFF_LOCK:
        item = get_handoff(store_dir, handoff_id, realm_id=realm_id, maximum_release_level=maximum_release_level)
        if item is None or not requester_subject_id or project != item.project or item.realm_id != realm_id:
            raise PermissionError("review appeal scope does not match")
        events = list_handoff_events(store_dir, handoff_id, realm_id=realm_id, maximum_release_level=maximum_release_level, limit=500)
        target = next((event for event in events if event.event_type == "review" and event.event_id == target_review_event_id), None)
        if target is None:
            raise ValueError("target review decision not found")
        existing = _event_idempotent(store_dir, handoff_id, idempotency_key, subject_id=item.subject_id, realm_id=item.realm_id)
        policy = _handoff_policy(policy_provider, action="handoff_review_appeal", handoff=item, status=item.status)
        if policy.decision in {"deny", "hard_gate"}:
            raise PermissionError("policy blocked handoff review appeal")
        if existing is not None and existing.event_type == "review_appeal":
            return existing
        event = HandoffEvent(event_id=f"event-{uuid.uuid4().hex[:16]}", event_type="review_appeal", handoff_id=item.handoff_id, task_id=item.task_id, subject_id=item.subject_id, realm_id=item.realm_id, release_level=item.release_level, requester_subject_id=requester_subject_id, result_ref=result_ref, rationale=rationale, provenance={**dict(provenance or {}), "target_review_event_id": target_review_event_id}, idempotency_key=idempotency_key, created_at=_now())
        _append_event(store_dir, event)
        return event


def _validate_lease_scope(item: AssistantHandoff, *, subject_id: str, host_id: str, project: str) -> None:
    """Require a claim to stay inside the handoff's explicit target scope."""
    if not subject_id or subject_id != item.subject_id:
        raise PermissionError("handoff claim subject does not match target scope")
    if not host_id or not item.host_id or host_id != item.host_id:
        raise PermissionError("handoff claim host does not match target scope")
    if not project or project != item.project:
        raise PermissionError("handoff claim project does not match target scope")


def claim_handoff(
    store_dir: str | Path,
    handoff_id: str,
    *,
    subject_id: str,
    host_id: str,
    project: str,
    lease_seconds: int = 900,
    policy_provider: PolicyDecisionProvider | None = None,
    realm_id: str = "",
    maximum_release_level: str = "private",
    expected_status: str = "",
    idempotency_key: str = "",
    provenance: dict[str, Any] | None = None,
) -> HandoffResult:
    """Claim a handoff for a bounded period; this grants no execution authority."""
    if not expected_status:
        raise ValueError("expected_status is required for a handoff claim")
    if lease_seconds < 1 or lease_seconds > 3600:
        raise ValueError("lease_seconds must be between 1 and 3600")
    with _HANDOFF_LOCK:
        item = get_handoff(store_dir, handoff_id, subject_id=subject_id, realm_id=realm_id, maximum_release_level=maximum_release_level)
        if item is None:
            raise ValueError("handoff not found")
        _validate_lease_scope(item, subject_id=subject_id, host_id=host_id, project=project)
        if item.status != expected_status:
            raise ValueError(f"handoff status conflict: expected {expected_status}, found {item.status}")
        existing = _event_idempotent(store_dir, handoff_id, idempotency_key, subject_id=item.subject_id, realm_id=item.realm_id)
        decision = _handoff_policy(policy_provider, action="handoff_claim", handoff=item, status=item.status)
        if decision.decision in {"deny", "hard_gate"}:
            raise PermissionError("policy blocked handoff claim")
        if existing is not None and existing.event_type == "lease" and existing.lease_action == "claimed":
            return HandoffResult(handoff=item, policy_decision=decision, lease_id=item.lease_id, lease_expires_at=item.lease_expires_at)
        if _lease_is_active(item):
            raise ValueError("handoff already has an active lease")
        now = datetime.now(timezone.utc)
        expires = (now.timestamp() + lease_seconds)
        expires_at = datetime.fromtimestamp(expires, tz=timezone.utc).isoformat()
        lease_id = f"lease-{uuid.uuid4().hex[:16]}"
        prior_lease = item.lease_id
        item.lease_id = lease_id
        item.lease_subject_id = subject_id
        item.lease_host_id = host_id
        item.lease_expires_at = expires_at
        item.updated_at = now.isoformat()
        _persist_mutation(store_dir, item, HandoffEvent(
            event_id=f"event-{uuid.uuid4().hex[:16]}", event_type="lease", handoff_id=item.handoff_id,
            task_id=item.task_id, subject_id=item.subject_id, realm_id=item.realm_id,
            release_level=item.release_level, lease_id=lease_id, lease_subject_id=subject_id,
            lease_host_id=host_id, lease_expires_at=expires_at, lease_action="claimed",
            provenance={**dict(provenance or {}), **({"previous_lease_id": prior_lease} if prior_lease else {})},
            idempotency_key=idempotency_key, created_at=now.isoformat(),
        ))
        return HandoffResult(handoff=item, policy_decision=decision, lease_id=lease_id, lease_expires_at=expires_at)


def release_handoff(
    store_dir: str | Path,
    handoff_id: str,
    *,
    subject_id: str,
    host_id: str,
    project: str,
    lease_id: str = "",
    policy_provider: PolicyDecisionProvider | None = None,
    realm_id: str = "",
    maximum_release_level: str = "private",
    expected_status: str = "",
    idempotency_key: str = "",
    provenance: dict[str, Any] | None = None,
) -> HandoffResult:
    """Release a caller-owned lease, including an expired lease, without changing status."""
    with _HANDOFF_LOCK:
        item = get_handoff(store_dir, handoff_id, subject_id=subject_id, realm_id=realm_id, maximum_release_level=maximum_release_level)
        if item is None:
            raise ValueError("handoff not found")
        _validate_lease_scope(item, subject_id=subject_id, host_id=host_id, project=project)
        if expected_status and item.status != expected_status:
            raise ValueError(f"handoff status conflict: expected {expected_status}, found {item.status}")
        decision = _handoff_policy(policy_provider, action="handoff_release", handoff=item, status=item.status)
        if decision.decision in {"deny", "hard_gate"}:
            raise PermissionError("policy blocked handoff release")
        existing = _event_idempotent(store_dir, handoff_id, idempotency_key, subject_id=item.subject_id, realm_id=item.realm_id)
        if existing is not None and existing.event_type == "lease" and existing.lease_action == "released":
            return HandoffResult(handoff=item, policy_decision=decision, lease_released=True)
        if not item.lease_id:
            raise ValueError("handoff has no active lease")
        if lease_id and lease_id != item.lease_id:
            raise PermissionError("handoff lease does not match supplied lease_id")
        if item.lease_subject_id != subject_id or item.lease_host_id != host_id:
            raise PermissionError("handoff lease owner does not match release scope")
        old_lease_id = item.lease_id
        old_expires_at = item.lease_expires_at
        now = _now()
        item.lease_id = item.lease_subject_id = item.lease_host_id = item.lease_expires_at = ""
        item.updated_at = now
        _persist_mutation(store_dir, item, HandoffEvent(
            event_id=f"event-{uuid.uuid4().hex[:16]}", event_type="lease", handoff_id=item.handoff_id,
            task_id=item.task_id, subject_id=item.subject_id, realm_id=item.realm_id,
            release_level=item.release_level, lease_id=old_lease_id, lease_subject_id=subject_id,
            lease_host_id=host_id, lease_expires_at=old_expires_at, lease_action="released",
            provenance=dict(provenance or {}), idempotency_key=idempotency_key, created_at=now,
        ))
        return HandoffResult(handoff=item, policy_decision=decision, lease_id=old_lease_id, lease_expires_at=old_expires_at, lease_released=True)


def append_handoff_progress(store_dir: str | Path, handoff_id: str, *, state: str = "", observations: list[str] | None = None, next_action: str = "", policy_provider: PolicyDecisionProvider | None = None, subject_id: str = "", realm_id: str = "", maximum_release_level: str = "private", idempotency_key: str = "", provenance: dict[str, Any] | None = None, lease_id: str = "", host_id: str = "", project: str = "", expected_status: str = "executing", require_lease: bool = False) -> HandoffEvent:
    return _append_handoff_event(store_dir, handoff_id, event_type="progress", policy_provider=policy_provider, subject_id=subject_id, realm_id=realm_id, maximum_release_level=maximum_release_level, idempotency_key=idempotency_key, lease_id=lease_id, host_id=host_id, project=project, expected_status=expected_status, require_lease=require_lease, state=state, observations=list(observations or []), next_action=next_action, provenance=dict(provenance or {}))


def propose_handoff_result(store_dir: str | Path, handoff_id: str, *, outcome: str = "", changes: list[str] | None = None, tests: list[str] | None = None, artifacts: list[str] | None = None, unresolved: list[str] | None = None, next_safe_action: str = "", policy_provider: PolicyDecisionProvider | None = None, subject_id: str = "", realm_id: str = "", maximum_release_level: str = "private", idempotency_key: str = "", provenance: dict[str, Any] | None = None, lease_id: str = "", host_id: str = "", project: str = "", expected_status: str = "executing", require_lease: bool = False) -> HandoffEvent:
    return _append_handoff_event(store_dir, handoff_id, event_type="result", policy_provider=policy_provider, subject_id=subject_id, realm_id=realm_id, maximum_release_level=maximum_release_level, idempotency_key=idempotency_key, lease_id=lease_id, host_id=host_id, project=project, expected_status=expected_status, require_lease=require_lease, outcome=outcome, changes=list(changes or []), tests=list(tests or []), artifacts=list(artifacts or []), unresolved=list(unresolved or []), next_safe_action=next_safe_action, provenance=dict(provenance or {}))


def _append_handoff_event(store_dir: str | Path, handoff_id: str, *, event_type: HandoffEventType, policy_provider: PolicyDecisionProvider | None, subject_id: str, realm_id: str, maximum_release_level: str, idempotency_key: str, lease_id: str = "", host_id: str = "", project: str = "", expected_status: str = "", require_lease: bool = False, **fields: Any) -> HandoffEvent:
    with _HANDOFF_LOCK:
        item = get_handoff(store_dir, handoff_id, subject_id=subject_id, realm_id=realm_id, maximum_release_level=maximum_release_level)
        if item is None:
            raise ValueError("handoff not found")
        if require_lease:
            if not lease_id or lease_id != item.lease_id or not _lease_is_active(item):
                raise PermissionError("handoff event requires an active lease")
            if not host_id or host_id != item.lease_host_id or subject_id != item.lease_subject_id:
                raise PermissionError("handoff event lease owner does not match scope")
            if not project or project != item.project:
                raise PermissionError("handoff event project does not match scope")
            if expected_status and item.status != expected_status:
                raise ValueError(f"handoff status conflict: expected {expected_status}, found {item.status}")
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
    _atomic_write(_path(store_dir, handoff_id), item.model_dump_json(indent=2) + "\n")
    return HandoffResult(handoff=item, policy_decision=decision)
