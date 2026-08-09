"""Read-only combined local/broker dashboard contract (RB6c)."""
from __future__ import annotations

import base64
from typing import Any

from pydantic import BaseModel, Field

from .federation_review_source import FederationReviewSource, RemoteReviewItem, RemoteReviewSnapshot
from .policy import PolicyRequest, RELEASE_RANK, load_policy_plugins
from .review_backlog import BacklogItem, aggregate_backlog
from .review_dashboard import _public_item


class CombinedDashboardItem(BaseModel):
    schema_version: str = "groundrecall.combined-review-dashboard-item.v1"
    item_id: str
    origin: str
    local_item: bool = False
    broker_id: str = ""
    producer_instance_id: str = ""
    release_level: str = "private"
    scope_id: str = ""
    candidate_kind: str = ""
    priority_band: str = "normal"
    state: str = "reviewable"
    freshness_status: str = ""
    quarantine_status: str = "none"
    revocation_status: str = "active"
    supersession_status: str = "current"
    action_origin: str = "local"
    content_available: bool = False
    local_only: bool = False


class CombinedDashboardDigest(BaseModel):
    schema_version: str = "groundrecall.combined-review-dashboard.v1"
    workspace_id: str
    generated_at: str
    visible_total: int
    local_total: int
    remote_total: int
    counts_by_origin: dict[str, int] = Field(default_factory=dict)
    counts_by_release_level: dict[str, int] = Field(default_factory=dict)
    items: list[CombinedDashboardItem] = Field(default_factory=list)
    next_cursor: str = ""
    broker_available: bool = False
    broker_results_truncated: bool = False
    broker_snapshot: RemoteReviewSnapshot | None = None
    diagnostics: list[str] = Field(default_factory=list)
    redaction_summary: dict[str, int] = Field(default_factory=dict)


def _cursor(offset: int, workspace_id: str, context: str) -> str:
    return base64.urlsafe_b64encode(f"{offset}:{workspace_id}:{context}".encode()).decode().rstrip("=")


def _offset(value: str, workspace_id: str, context: str) -> int:
    if not value:
        return 0
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode()
        offset, found_workspace, found_context = raw.split(":", 2)
        if found_workspace != workspace_id or found_context != context:
            raise ValueError("combined cursor context mismatch")
        return max(0, int(offset))
    except ValueError:
        raise
    except (TypeError, UnicodeDecodeError) as exc:
        raise ValueError("invalid combined cursor") from exc


def _local_item(item: BacklogItem) -> CombinedDashboardItem:
    public = _public_item(item)
    return CombinedDashboardItem(item_id=public.backlog_id, origin="local", local_item=True,
        release_level=public.release_level, candidate_kind=public.candidate_kind,
        priority_band=public.priority_band, state=public.authoritative_status,
        action_origin="local", content_available=False, local_only=True)


def _remote_item(item: RemoteReviewItem) -> CombinedDashboardItem:
    return CombinedDashboardItem(item_id=item.item_id, origin="broker", broker_id=item.broker_id,
        producer_instance_id=item.producer_instance_id, release_level=item.release_level,
        scope_id=item.scope_id, candidate_kind="remote_review", state=item.state,
        freshness_status=item.freshness_status, quarantine_status=item.quarantine_status,
        revocation_status=item.revocation_status, supersession_status=item.supersession_status,
        action_origin="broker", local_only=False)


def combined_dashboard_digest(workspace: str, source: FederationReviewSource, *, subject_id: str = "",
                              policy_config: str | None = None, maximum_release_level: str = "private",
                              page_size: int = 20, cursor: str = "", max_remote_items: int = 1000,
                              max_remote_pages: int = 20) -> CombinedDashboardDigest:
    if page_size < 1 or page_size > 100:
        raise ValueError("page_size must be between 1 and 100")
    if max_remote_items < 1 or max_remote_pages < 1:
        raise ValueError("remote bounds must be positive")
    local = aggregate_backlog(workspace, subject_id=subject_id, policy_config=policy_config,
                              maximum_release_level=maximum_release_level, limit=None)
    remote: list[RemoteReviewItem] = []
    snapshot = None
    diagnostics: list[str] = []
    broker_available = False
    truncated = False
    try:
        remote_cursor = ""
        pages = 0
        while True:
            page, remote_cursor, snapshot = source.page(page_size=100, cursor=remote_cursor, maximum_release_level=maximum_release_level)
            remote.extend(page)
            pages += 1
            if not remote_cursor:
                break
            if len(remote) >= max_remote_items or pages >= max_remote_pages:
                truncated = True
                break
        if len(remote) > max_remote_items:
            remote = remote[:max_remote_items]
        broker_available = True
    except Exception as exc:
        diagnostics.append("broker_unavailable")
    cache_health = getattr(source, "cache_health", None)
    if isinstance(cache_health, dict):
        diagnostics.extend(str(code) for code in cache_health.get("diagnostics", []))
        if cache_health.get("status") in {"missing", "invalid"}:
            broker_available = False
    if truncated:
        diagnostics.append("broker_results_truncated")
    if policy_config and remote:
        provider = load_policy_plugins(policy_config)
        allowed: list[RemoteReviewItem] = []
        for item in remote:
            decision = provider.evaluate(PolicyRequest(decision_point="read", subject_id=subject_id,
                action="review_dashboard.broker_list", record_kind="remote_review", record_id=item.item_id,
                release_level=item.release_level, target_release_level=maximum_release_level,
                scope_id=item.scope_id, metadata={"broker_id": item.broker_id, "producer_instance_id": item.producer_instance_id}))
            if decision.decision not in {"deny", "hard_gate"}:
                allowed.append(item)
        remote = allowed
    combined = [_local_item(item) for item in local.items] + [_remote_item(item) for item in remote]
    combined.sort(key=lambda item: (0 if item.origin == "local" else 1, item.item_id))
    context = f"{subject_id}:{maximum_release_level}:{policy_config or ''}"
    import hashlib
    context_hash = hashlib.sha256(context.encode()).hexdigest()[:24]
    offset = _offset(cursor, local.workspace_id, context_hash)
    page = combined[offset:offset + page_size]
    next_cursor = _cursor(offset + page_size, local.workspace_id, context_hash) if offset + page_size < len(combined) else ""
    counts_origin = {"local": len(local.items), "broker": len(remote)}
    counts_release: dict[str, int] = {}
    for item in combined:
        counts_release[item.release_level] = counts_release.get(item.release_level, 0) + 1
    return CombinedDashboardDigest(workspace_id=local.workspace_id, generated_at=local.generated_at,
        visible_total=len(combined), local_total=len(local.items), remote_total=len(remote), counts_by_origin=counts_origin,
        counts_by_release_level=counts_release, items=page, next_cursor=next_cursor, broker_available=broker_available,
        broker_snapshot=snapshot, broker_results_truncated=truncated, diagnostics=diagnostics, redaction_summary=local.redaction_summary)
