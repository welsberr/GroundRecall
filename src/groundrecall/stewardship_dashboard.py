"""Read-only team/federation stewardship backlog view (RB7)."""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .models import ContributionRecord, ContributionReviewReceipt, FederationFeedbackRecord, ScopeRecord, StewardshipRecord
from .policy import RELEASE_RANK, PolicyRequest, load_policy_plugins


class StewardshipItem(BaseModel):
    schema_version: str = "groundrecall.stewardship-dashboard-item.v1"
    item_id: str
    item_kind: str
    origin: str = "local"
    release_level: str = "private"
    scope_id: str = ""
    state: str = ""
    assignee_role_ids: list[str] = Field(default_factory=list)
    assignee_subject_id: str = ""
    required_actions: list[str] = Field(default_factory=list)
    freshness_status: str = "local"
    local_only: bool = True


class StewardshipDigest(BaseModel):
    schema_version: str = "groundrecall.stewardship-dashboard.v1"
    generated_at: str
    store_id: str
    visible_total: int
    counts_by_kind: dict[str, int] = Field(default_factory=dict)
    counts_by_origin: dict[str, int] = Field(default_factory=dict)
    counts_by_release_level: dict[str, int] = Field(default_factory=dict)
    items: list[StewardshipItem] = Field(default_factory=list)
    next_cursor: str = ""
    diagnostics: list[str] = Field(default_factory=list)
    health: dict[str, Any] = Field(default_factory=dict)


def _load(directory: Path, model: type[BaseModel]) -> list[BaseModel]:
    rows = []
    if not directory.is_dir(): return rows
    for path in sorted(directory.glob("*.json")):
        try: rows.append(model.model_validate_json(path.read_text(encoding="utf-8")))
        except (OSError, ValueError): continue
    return rows


def stewardship_digest(store_dir: str | Path, *, subject_id: str = "", policy_config: str | Path | None = None,
                       maximum_release_level: str = "private", page_size: int = 20, cursor: str = "") -> StewardshipDigest:
    if page_size < 1 or page_size > 100: raise ValueError("page_size must be between 1 and 100")
    root = Path(store_dir); store_id = "store_" + __import__("hashlib").sha256(str(root.resolve()).encode()).hexdigest()[:24]
    scopes = {item.scope_id: item for item in _load(root / "scopes", ScopeRecord)}
    items: list[StewardshipItem] = []
    for contribution in _load(root / "contributions", ContributionRecord):
        if contribution.state not in {"proposed", "triaged", "under_review", "deferred"}: continue
        items.append(StewardshipItem(item_id=contribution.contribution_id, item_kind="contribution", release_level=contribution.proposed_release_level, scope_id=contribution.destination_scope_id, state=contribution.state, assignee_role_ids=contribution.assigned_steward_role_ids, required_actions=["review_contribution"], local_only=True))
    for feedback in _load(root / "federation_feedback", FederationFeedbackRecord):
        if feedback.decision not in {"accept", "reject", "dissent", "appeal", "needs_review"}: continue
        items.append(StewardshipItem(item_id=feedback.feedback_id, item_kind="feedback", origin="remote", release_level=feedback.release_level, scope_id="", state=feedback.decision, required_actions=["resolve_feedback"], freshness_status="remote", local_only=False))
    for stewardship in _load(root / "stewardship", StewardshipRecord):
        if stewardship.status not in {"orphaned", "expired", "declined"} and stewardship.steward_principal_id: continue
        items.append(StewardshipItem(item_id=stewardship.stewardship_id, item_kind="stewardship", release_level=stewardship.release_level, scope_id=stewardship.scope_id, state=stewardship.status, assignee_subject_id=stewardship.steward_principal_id, required_actions=["assign_steward"], local_only=True))
    for scope in scopes.values():
        if scope.current_status in {"rejected", "archived"} or scope.owner_principal_ids: continue
        items.append(StewardshipItem(item_id=scope.scope_id, item_kind="scope", release_level=scope.release_level, scope_id=scope.scope_id, state="unowned", required_actions=["assign_scope_steward"], local_only=True))
    provider = load_policy_plugins(policy_config) if policy_config else None; filtered = []; denied = 0
    for item in items:
        if RELEASE_RANK.get(item.release_level, 4) > RELEASE_RANK.get(maximum_release_level, 4): denied += 1; continue
        if provider:
            decision = provider.evaluate(PolicyRequest(decision_point="read", subject_id=subject_id, action="stewardship_dashboard.list", record_kind=item.item_kind, record_id=item.item_id, release_level=item.release_level, target_release_level=maximum_release_level, scope_id=item.scope_id))
            if decision.decision in {"deny", "hard_gate"}: denied += 1; continue
        filtered.append(item)
    items = sorted(filtered, key=lambda item: (item.origin, item.item_kind, item.item_id))
    context = f"{subject_id}:{maximum_release_level}:{policy_config or ''}"; import hashlib; context_hash = hashlib.sha256(context.encode()).hexdigest()[:24]
    offset = 0
    if cursor:
        try:
            raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode(); offset_text, found = raw.split(":", 1)
            if found != context_hash: raise ValueError("cursor context mismatch")
            offset = int(offset_text)
        except ValueError: raise
        except Exception as exc: raise ValueError("invalid stewardship cursor") from exc
    page = items[offset:offset + page_size]; next_cursor = base64.urlsafe_b64encode(f"{offset + page_size}:{context_hash}".encode()).decode().rstrip("=") if offset + page_size < len(items) else ""
    counts_kind: dict[str, int] = {}; counts_origin: dict[str, int] = {}; counts_release: dict[str, int] = {}
    for item in items:
        counts_kind[item.item_kind] = counts_kind.get(item.item_kind, 0) + 1; counts_origin[item.origin] = counts_origin.get(item.origin, 0) + 1; counts_release[item.release_level] = counts_release.get(item.release_level, 0) + 1
    return StewardshipDigest(generated_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), store_id=store_id, visible_total=len(items), counts_by_kind=counts_kind, counts_by_origin=counts_origin, counts_by_release_level=counts_release, items=page, next_cursor=next_cursor, diagnostics=[f"redacted:{denied}"] if denied else [], health={"freshness_status": "local", "source": "canonical_store"})
