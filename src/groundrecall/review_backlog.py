"""Read-only aggregation of GroundRecall review work.

This module intentionally does not use :class:`GroundRecallStore`: opening a
store creates its typed-record directories.  Backlog inspection must be safe
to run from cron against an otherwise idle workspace.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from contextlib import contextmanager
from typing import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .policy import RELEASE_RANK, PolicyRequest, load_policy_plugins


ACTIVE_STATUSES = {"draft", "triaged", "needs_review", "open", "under_review"}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _age_seconds(value: str, now: datetime) -> int:
    if not value:
        return 0
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0, int((now - parsed.astimezone(timezone.utc)).total_seconds()))
    except ValueError:
        return 0


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
class BacklogItem(BaseModel):
    schema_version: str = "groundrecall.review-backlog-item.v1"
    backlog_id: str
    source_kind: str
    source_id: str
    source_path_hash: str = ""
    workspace_id: str
    store_id: str = ""
    candidate_kind: str
    candidate_id: str
    reason_codes: list[str] = Field(default_factory=list)
    required_actions: list[str] = Field(default_factory=list)
    authoritative_status: str
    triage_lane: str = "knowledge_capture"
    priority_band: Literal["urgent", "high", "normal", "low"] = "normal"
    priority_factors: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    age_seconds: int = 0
    due_at: str = ""
    scope_ids: list[str] = Field(default_factory=list)
    owner_subject_ids: list[str] = Field(default_factory=list)
    required_reviewer_roles: list[str] = Field(default_factory=list)
    release_level: str = "private"
    policy_obligations: list[str] = Field(default_factory=list)
    content_available: bool = False
    acknowledgement_state: str = "unacknowledged"
    assignment_state: str = "unassigned"
    deferral_until: str = ""


class BacklogDigest(BaseModel):
    schema_version: str = "groundrecall.review-backlog.v1"
    generated_at: str
    workspace_id: str
    subject_id: str = ""
    policy_context_hash: str = ""
    visible_total: int = 0
    new_since_last_digest: int = 0
    urgent_count: int = 0
    overdue_count: int = 0
    oldest_visible_age_seconds: int = 0
    counts_by_source_kind: dict[str, int] = Field(default_factory=dict)
    counts_by_candidate_kind: dict[str, int] = Field(default_factory=dict)
    counts_by_triage_lane: dict[str, int] = Field(default_factory=dict)
    counts_by_priority_band: dict[str, int] = Field(default_factory=dict)
    required_action_counts: dict[str, int] = Field(default_factory=dict)
    maintenance_health: dict[str, Any] = Field(default_factory=dict)
    reminder_recommendation: str = "suppress_empty"
    items: list[BacklogItem] = Field(default_factory=list)
    redaction_summary: dict[str, int] = Field(default_factory=dict)
    diagnostics: list[str] = Field(default_factory=list)


class BacklogInteractionEvent(BaseModel):
    schema_version: str = "groundrecall.review-backlog-event.v1"
    event_id: str
    event_type: Literal["acknowledged", "deferred", "assigned", "unassigned", "reminder_emitted", "reminder_failed", "policy_denied"]
    backlog_id: str
    actor_subject_id: str
    occurred_at: str
    reason: str = ""
    until: str = ""
    assignment: str = ""
    policy_decision_ids: list[str] = Field(default_factory=list)
    previous_event_hash: str = ""
    event_hash: str


class BacklogPolicyError(RuntimeError):
    """Raised when a policy plugin blocks an interaction-ledger action."""


def interaction_ledger_path(workspace: str | Path) -> Path:
    return Path(workspace) / ".review" / "backlog-events.jsonl"


@contextmanager
def _interaction_lock(path: Path) -> Iterator[None]:
    """Serialize hash-chain appenders; Unix uses an advisory sidecar lock."""
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        try:
            import fcntl  # type: ignore[import-not-found]
        except ImportError:  # pragma: no cover - non-Unix fallback
            yield
            return
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def read_interaction_events(workspace: str | Path) -> list[BacklogInteractionEvent]:
    path = interaction_ledger_path(workspace)
    if not path.exists():
        return []
    events: list[BacklogInteractionEvent] = []
    previous = ""
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = BacklogInteractionEvent.model_validate_json(line)
        except Exception as exc:
            raise ValueError(f"invalid backlog event at line {line_number}") from exc
        if event.previous_event_hash != previous:
            raise ValueError(f"backlog event hash chain break at line {line_number}")
        payload = event.model_dump(mode="json")
        actual = payload.pop("event_hash")
        expected = _hash(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        if actual != expected:
            raise ValueError(f"backlog event hash mismatch at line {line_number}")
        previous = event.event_hash
        events.append(event)
    return events


def reconstruct_interaction_state(workspace: str | Path) -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    for event in read_interaction_events(workspace):
        item = state.setdefault(event.backlog_id, {"acknowledgement_state": "unacknowledged", "assignment_state": "unassigned", "deferral_until": ""})
        if event.event_type == "acknowledged":
            item.update({"acknowledgement_state": "acknowledged", "acknowledged_by": event.actor_subject_id, "acknowledged_at": event.occurred_at})
        elif event.event_type == "deferred":
            item.update({"deferral_until": event.until, "deferred_by": event.actor_subject_id, "deferred_at": event.occurred_at})
        elif event.event_type == "assigned":
            item.update({"assignment_state": "assigned", "assigned_to": event.assignment, "assigned_by": event.actor_subject_id})
        elif event.event_type == "unassigned":
            item.update({"assignment_state": "unassigned", "assigned_to": "", "assigned_by": event.actor_subject_id})
    return state


def _append_interaction_event(workspace: str | Path, *, event_type: str, backlog_id: str, actor_subject_id: str,
                              reason: str = "", until: str = "", assignment: str = "", policy_decision_ids: list[str] | None = None) -> BacklogInteractionEvent:
    path = interaction_ledger_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _interaction_lock(path):
        events = read_interaction_events(workspace)
        previous = events[-1].event_hash if events else ""
        occurred = _now()
        payload = {
            "schema_version": "groundrecall.review-backlog-event.v1", "event_id": "", "event_type": event_type,
            "backlog_id": backlog_id, "actor_subject_id": actor_subject_id, "occurred_at": occurred,
            "reason": reason, "until": until, "assignment": assignment,
            "policy_decision_ids": sorted(policy_decision_ids or []), "previous_event_hash": previous,
        }
        payload["event_id"] = "backlog_event_" + _hash(json.dumps(payload, sort_keys=True, separators=(",", ":")))[:24]
        event_hash = _hash(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        event = BacklogInteractionEvent(**payload, event_hash=event_hash)
        line = event.model_dump_json() + "\n"
        # A single fsynced append preserves event order and durability for local cron/CLI use.
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
    return event


def record_interaction(workspace: str | Path, backlog_id: str, *, event_type: str, actor_subject_id: str,
                       until: str = "", assignment: str = "", reason: str = "", policy_config: str | Path | None = None) -> BacklogInteractionEvent:
    # Resolve the item from the local operational view first; the action policy
    # below is the authorization boundary and must be able to explain a denial.
    digest = aggregate_backlog(workspace, subject_id=actor_subject_id, limit=None)
    item = next((candidate for candidate in digest.items if candidate.backlog_id == backlog_id), None)
    if item is None:
        raise ValueError("backlog item is not visible or does not exist")
    decisions: list[str] = []
    if policy_config:
        decision = load_policy_plugins(policy_config).evaluate(PolicyRequest(
            decision_point="review", subject_id=actor_subject_id, action=f"review_backlog.{event_type}",
            record_kind=item.candidate_kind, record_id=item.candidate_id, release_level=item.release_level,
            metadata={"backlog_id": backlog_id},
        ))
        decisions = [decision.policy_id + ":" + decision.decision]
        if decision.decision in {"deny", "hard_gate"}:
            raise BacklogPolicyError(f"policy blocked review backlog {event_type}")
    return _append_interaction_event(workspace, event_type=event_type, backlog_id=backlog_id,
                                     actor_subject_id=actor_subject_id, until=until, assignment=assignment,
                                     reason=reason, policy_decision_ids=decisions)


def discover_workspace(
    workspace: str | Path,
    *,
    store: str | Path | None = None,
    imports_root: str | Path | None = None,
    source_notes_root: str | Path | None = None,
) -> dict[str, Any]:
    """Resolve explicit roots without creating directories or following backups."""
    root = Path(workspace)
    if root.is_file():
        raise ValueError(f"Workspace must be a directory: {root}")
    selected = {
        "workspace": root,
        "store": Path(store) if store else root / "store",
        "imports": Path(imports_root) if imports_root else root / "imports",
        "source_notes": Path(source_notes_root) if source_notes_root else root / "source-notes",
    }
    diagnostics: list[str] = []
    if not root.exists():
        diagnostics.append("workspace_missing")
    if not any(path.exists() for path in selected.values() if path != root):
        diagnostics.append("workspace_roots_missing")
    if selected["store"].exists() and not any((selected["store"] / name).is_dir() for name in ("claims", "concepts", "relations", "review_candidates")):
        diagnostics.append("store_not_typed_record_store")
    return {**selected, "workspace_id": _hash(str(root.resolve()))[:24], "diagnostics": diagnostics}


def _item_id(source_kind: str, source_id: str, reason: str) -> str:
    return "backlog_" + _hash(f"{source_kind}:{source_id}:{reason}")[:24]


def _band(priority: int) -> tuple[str, list[str]]:
    if priority <= 15:
        return "urgent", ["source_priority<=15"]
    if priority <= 35:
        return "high", ["source_priority<=35"]
    if priority >= 80:
        return "low", ["source_priority>=80"]
    return "normal", []


def _make_item(*, source_kind: str, source_id: str, candidate_kind: str, candidate_id: str,
               workspace_id: str, store_id: str, status: str, reason_codes: list[str],
               lane: str = "knowledge_capture", priority: int = 50, created_at: str = "",
               source_path: str = "", content_available: bool = False, release_level: str = "private", scope_ids: list[str] | None = None,
               owner_subject_ids: list[str] | None = None, due_at: str = "") -> BacklogItem:
    reason = reason_codes[0] if reason_codes else "needs_review"
    band, factors = _band(priority)
    factors.extend(f"reason:{code}" for code in sorted(set(reason_codes)))
    return BacklogItem(
        backlog_id=_item_id(source_kind, source_id, reason), source_kind=source_kind, source_id=source_id,
        source_path_hash=_hash(source_path) if source_path else "", workspace_id=workspace_id, store_id=store_id,
        candidate_kind=candidate_kind, candidate_id=candidate_id, reason_codes=sorted(set(reason_codes or [reason])),
        required_actions=["review"], authoritative_status=status, triage_lane=lane, priority_band=band,
        priority_factors=factors, created_at=created_at, updated_at=created_at, release_level=release_level,
        age_seconds=_age_seconds(created_at, datetime.now(timezone.utc)), content_available=content_available,
        scope_ids=list(scope_ids or []), owner_subject_ids=list(owner_subject_ids or []), due_at=due_at,
    )


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _aggregate_imports(imports_root: Path, workspace_id: str, store_id: str) -> tuple[list[BacklogItem], set[str]]:
    items: list[BacklogItem] = []
    imported_hashes: set[str] = set()
    if not imports_root.is_dir():
        return items, imported_hashes
    for import_dir in sorted(p for p in imports_root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        manifest = _read_json(import_dir / "manifest.json") or {}
        queue = _read_json(import_dir / "review_queue.json")
        for row in (queue or {}).get("items", []):
            status = str(row.get("status", "needs_review"))
            if status not in ACTIVE_STATUSES:
                continue
            queue_id = str(row.get("queue_id", row.get("candidate_id", import_dir.name)))
            # Queue ids are import-local; include the import id in the stable source identity.
            items.append(_make_item(source_kind="import_review", source_id=f"{import_dir.name}:{queue_id}",
                candidate_kind=str(row.get("candidate_type", "unknown")), candidate_id=str(row.get("candidate_id", "")),
                workspace_id=workspace_id, store_id=store_id, status=status,
                reason_codes=list(row.get("finding_codes", [])) or ["import_review"], lane=str(row.get("triage_lane", "knowledge_capture")),
                priority=int(row.get("priority", 50)), created_at=str(manifest.get("imported_at", "")), source_path=str(import_dir),
                release_level=str(row.get("release_level", manifest.get("release_level", "private"))), scope_ids=list(row.get("scope_ids", [])), owner_subject_ids=list(row.get("owner_subject_ids", [])), due_at=str(row.get("due_at", ""))))
        for artifact in _read_jsonl(import_dir / "artifacts.jsonl"):
            digest = str(artifact.get("sha256", ""))
            if digest:
                imported_hashes.add(digest)
    return items, imported_hashes


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict): rows.append(value)
        except json.JSONDecodeError:
            continue
    return rows


def aggregate_backlog(workspace: str | Path, *, store: str | Path | None = None,
                      imports_root: str | Path | None = None, source_notes_root: str | Path | None = None,
                      limit: int | None = 20, only: str | None = None, subject_id: str = "",
                      policy_config: str | Path | None = None, maximum_release_level: str = "private",
                      scope_ids: list[str] | None = None, owner_subject_ids: list[str] | None = None,
                      due_before: str | None = None, overdue: bool = False, statuses: list[str] | None = None,
                      triage_lanes: list[str] | None = None) -> BacklogDigest:
    discovered = discover_workspace(workspace, store=store, imports_root=imports_root, source_notes_root=source_notes_root)
    root, store_dir, imports_dir, notes_dir = discovered["workspace"], discovered["store"], discovered["imports"], discovered["source_notes"]
    wid = discovered["workspace_id"]
    # Portable identifiers must not disclose local absolute paths.
    store_id = _hash(str(store_dir.resolve()))[:24]
    all_items, imported_hashes = _aggregate_imports(imports_dir, wid, store_id)
    # Source notes are pending only when their content hash is not represented by an import artifact.
    if notes_dir.is_dir():
        for note in sorted(notes_dir.rglob("*")):
            if not note.is_file() or note.suffix.lower() not in {".md", ".markdown", ".txt"}: continue
            try: digest = hashlib.sha256(note.read_bytes()).hexdigest()
            except OSError: continue
            if digest in imported_hashes: continue
            all_items.append(_make_item(source_kind="source_note", source_id=note.relative_to(notes_dir).as_posix(), candidate_kind="source_note",
                candidate_id=note.relative_to(notes_dir).as_posix(), workspace_id=wid, store_id=store_id, status="needs_review",
                reason_codes=["source_not_imported"], lane="source_cleanup", priority=50, source_path=str(note)))
    # Read canonical review candidates directly to preserve read-only semantics.
    candidate_dir = store_dir / "review_candidates"
    if candidate_dir.is_dir():
        for path in sorted(candidate_dir.glob("*.json")):
            row = _read_json(path) or {}
            status = str(row.get("current_status", "draft"))
            if status not in ACTIVE_STATUSES: continue
            all_items.append(_make_item(source_kind="canonical_review_candidate", source_id=str(row.get("review_candidate_id", path.stem)),
                candidate_kind=str(row.get("candidate_type", "unknown")), candidate_id=str(row.get("candidate_id", "")), workspace_id=wid,
                store_id=store_id, status=status, reason_codes=list(row.get("finding_codes", [])) or ["canonical_review_candidate"],
                lane=str(row.get("triage_lane", "knowledge_capture")), priority=int(row.get("priority", 50)), source_path=str(path),
                release_level=str(row.get("release_level", (row.get("metadata") or {}).get("release_level", "private"))), scope_ids=list(row.get("scope_ids", [])), owner_subject_ids=list(row.get("owner_subject_ids", [])), due_at=str(row.get("due_at", ""))))
    policy_provider = load_policy_plugins(policy_config) if policy_config else None
    policy_bytes = Path(policy_config).read_bytes() if policy_config else b""
    denied_count = 0
    filtered_items: list[BacklogItem] = []
    for item in all_items:
        if RELEASE_RANK.get(item.release_level, RELEASE_RANK["private"]) > RELEASE_RANK.get(maximum_release_level, RELEASE_RANK["private"]):
            denied_count += 1
            continue
        if policy_provider is not None:
            decision = policy_provider.evaluate(PolicyRequest(
                decision_point="read", subject_id=subject_id, action="review_backlog.list",
                record_kind=item.candidate_kind, record_id=item.candidate_id,
                release_level=item.release_level, target_release_level=maximum_release_level,
                scope_id=item.scope_ids[0] if item.scope_ids else "",
                metadata={"source_kind": item.source_kind, "triage_lane": item.triage_lane},
            ))
            if decision.decision in {"deny", "hard_gate"}:
                denied_count += 1
                continue
            item.policy_obligations = sorted(set(decision.obligations + decision.required_reviewers))
            if decision.decision in {"soft_gate", "require_review"}:
                item.priority_factors = sorted(set(item.priority_factors + [f"policy:{decision.decision}"]))
        filtered_items.append(item)
    all_items = filtered_items
    filter_diagnostics: list[str] = []
    due_cutoff = None
    if due_before:
        try: due_cutoff = datetime.fromisoformat(due_before.replace("Z", "+00:00"))
        except ValueError: filter_diagnostics.append("invalid_due_before")
    now = datetime.now(timezone.utc)
    if scope_ids: all_items = [item for item in all_items if set(scope_ids) & set(item.scope_ids)]
    if owner_subject_ids: all_items = [item for item in all_items if set(owner_subject_ids) & set(item.owner_subject_ids)]
    if statuses: all_items = [item for item in all_items if item.authoritative_status in statuses]
    if triage_lanes: all_items = [item for item in all_items if item.triage_lane in triage_lanes]
    if due_cutoff: all_items = [item for item in all_items if item.due_at and _parse_timestamp(item.due_at) and _parse_timestamp(item.due_at) <= due_cutoff]
    if overdue: all_items = [item for item in all_items if item.due_at and _parse_timestamp(item.due_at) and _parse_timestamp(item.due_at) < now]
    interaction_state = reconstruct_interaction_state(workspace)
    for item in all_items:
        state = interaction_state.get(item.backlog_id)
        if state:
            item.acknowledgement_state = str(state.get("acknowledgement_state", item.acknowledgement_state))
            item.assignment_state = str(state.get("assignment_state", item.assignment_state))
            item.deferral_until = str(state.get("deferral_until", ""))
    if only:
        all_items = [item for item in all_items if item.priority_band == only]
    all_items.sort(key=lambda item: (0 if item.priority_band == "urgent" else 1 if item.priority_band == "high" else 2, -item.age_seconds, item.backlog_id))
    visible = all_items if limit is None else all_items[:max(0, limit)]
    digest = BacklogDigest(generated_at=_now(), workspace_id=wid, subject_id=subject_id,
        policy_context_hash=_hash(subject_id + ":" + maximum_release_level + ":" + policy_bytes.decode("utf-8", "replace"))[:24], visible_total=len(all_items),
        urgent_count=sum(item.priority_band == "urgent" for item in all_items), oldest_visible_age_seconds=max((item.age_seconds for item in all_items), default=0),
        items=visible, reminder_recommendation="emit" if all_items else "suppress_empty",
        redaction_summary={"policy_or_release_filtered": denied_count} if denied_count else {}, diagnostics=discovered["diagnostics"] + filter_diagnostics)
    digest.maintenance_health = _maintenance_health(store_dir)
    for item in all_items:
        for key, value in (("source_kind", item.source_kind), ("candidate_kind", item.candidate_kind), ("triage_lane", item.triage_lane), ("priority_band", item.priority_band)):
            target = {"source_kind": digest.counts_by_source_kind, "candidate_kind": digest.counts_by_candidate_kind, "triage_lane": digest.counts_by_triage_lane, "priority_band": digest.counts_by_priority_band}[key]
            target[value] = target.get(value, 0) + 1
        for action in item.required_actions: digest.required_action_counts[action] = digest.required_action_counts.get(action, 0) + 1
    return digest


def _maintenance_health(store_dir: Path) -> dict[str, Any]:
    """Read maintenance state without creating directories or exposing paths."""
    directory = store_dir / ".maintenance"
    states: list[dict[str, Any]] = []
    if directory.is_dir():
        for path in sorted(directory.glob("graph_maintenance_state__*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            states.append({"profile": payload.get("profile", path.stem), "updated_at": payload.get("updated_at", ""), "run_count": payload.get("run_count", 0), "last_run": payload.get("last_run", {})})
    return {"state_count": len(states), "states": states, "healthy": all(bool(item.get("updated_at")) for item in states) if states else True}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only GroundRecall review backlog status.")
    parser.add_argument("workspace")
    parser.add_argument("--store", default=None); parser.add_argument("--imports-root", default=None); parser.add_argument("--source-notes-root", default=None)
    parser.add_argument("--format", choices=("json", "text"), default="text"); parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--only", choices=("urgent", "high", "normal", "low"), default=None); parser.add_argument("--subject-id", default="")
    parser.add_argument("--policy-config", default=None, help="Policy-plugin YAML used to authorize backlog visibility")
    parser.add_argument("--maximum-release-level", choices=tuple(RELEASE_RANK), default="private")
    parser.add_argument("--scope-id", action="append", default=[]); parser.add_argument("--owner", action="append", default=[])
    parser.add_argument("--due-before", default=None); parser.add_argument("--overdue", action="store_true")
    parser.add_argument("--status", action="append", default=[]); parser.add_argument("--triage-lane", action="append", default=[])
    return parser


def main() -> None:
    args = build_parser().parse_args()
    digest = aggregate_backlog(args.workspace, store=args.store, imports_root=args.imports_root, source_notes_root=args.source_notes_root, limit=args.limit, only=args.only, subject_id=args.subject_id, policy_config=args.policy_config, maximum_release_level=args.maximum_release_level, scope_ids=args.scope_id, owner_subject_ids=args.owner, due_before=args.due_before, overdue=args.overdue, statuses=args.status, triage_lanes=args.triage_lane)
    if args.format == "json":
        print(digest.model_dump_json(indent=2)); return
    print(f"GroundRecall review backlog: {digest.visible_total} visible items ({digest.urgent_count} urgent); oldest {digest.oldest_visible_age_seconds}s")
    for item in digest.items:
        print(f"- {item.priority_band} {item.source_kind}/{item.candidate_kind} {item.backlog_id} ({item.authoritative_status})")
    for diagnostic in digest.diagnostics: print(f"diagnostic: {diagnostic}")


def _interaction_main(event_type: str) -> None:
    parser = argparse.ArgumentParser(description=f"Record a review backlog {event_type} interaction.")
    parser.add_argument("workspace"); parser.add_argument("backlog_id"); parser.add_argument("--actor", required=True)
    parser.add_argument("--reason", default=""); parser.add_argument("--until", default=""); parser.add_argument("--to", default="")
    parser.add_argument("--policy-config", default=None)
    args = parser.parse_args()
    if event_type == "deferred" and not args.until:
        parser.error("--until is required for review-defer")
    if event_type == "assigned" and not args.to:
        parser.error("--to is required for review-assign")
    event = record_interaction(args.workspace, args.backlog_id, event_type=event_type, actor_subject_id=args.actor,
                               until=args.until, assignment=args.to, reason=args.reason, policy_config=args.policy_config)
    print(event.model_dump_json(indent=2))


def acknowledge_main() -> None:
    _interaction_main("acknowledged")


def defer_main() -> None:
    _interaction_main("deferred")


def assign_main() -> None:
    _interaction_main("assigned")
