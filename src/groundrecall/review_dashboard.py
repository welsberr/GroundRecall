"""Framework-neutral, read-only local dashboard contract for review backlog."""
from __future__ import annotations

import base64

from pydantic import BaseModel, Field

from .review_backlog import BacklogDigest, BacklogItem, aggregate_backlog


class DashboardItem(BaseModel):
    schema_version: str = "groundrecall.review-dashboard-item.v1"
    backlog_id: str
    origin: str = "local"
    origin_scope: str = "workspace"
    source_kind: str
    candidate_kind: str
    authoritative_status: str
    priority_band: str
    triage_lane: str
    release_level: str
    acknowledgement_state: str
    assignment_state: str
    deferral_until: str = ""
    content_available: bool = False
    detail_available: bool = True
    local_only: bool = True


class DashboardDigest(BaseModel):
    schema_version: str = "groundrecall.review-dashboard.v1"
    generated_at: str
    workspace_id: str
    origin: str = "local"
    local_only: bool = True
    visible_total: int
    urgent_count: int
    counts_by_source_kind: dict[str, int] = Field(default_factory=dict)
    counts_by_candidate_kind: dict[str, int] = Field(default_factory=dict)
    counts_by_priority_band: dict[str, int] = Field(default_factory=dict)
    items: list[DashboardItem] = Field(default_factory=list)
    next_cursor: str = ""
    policy_context_hash: str = ""
    redaction_summary: dict[str, int] = Field(default_factory=dict)
    diagnostics: list[str] = Field(default_factory=list)


class DashboardDetail(BaseModel):
    schema_version: str = "groundrecall.review-dashboard-detail.v1"
    generated_at: str
    workspace_id: str
    origin: str = "local"
    local_only: bool = True
    item: DashboardItem
    reason_codes: list[str] = Field(default_factory=list)
    required_actions: list[str] = Field(default_factory=list)
    priority_factors: list[str] = Field(default_factory=list)
    policy_obligations: list[str] = Field(default_factory=list)
    provenance_available: bool = False


def _encode_cursor(offset: int, digest: BacklogDigest) -> str:
    raw = f"{offset}:{digest.workspace_id}:{digest.policy_context_hash}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str, digest: BacklogDigest) -> int:
    if not cursor:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        offset, workspace_id, context_hash = raw.split(":", 2)
        if workspace_id != digest.workspace_id or context_hash != digest.policy_context_hash:
            raise ValueError("cursor context mismatch")
        return max(0, int(offset))
    except ValueError as exc:
        if str(exc) == "cursor context mismatch":
            raise
        raise ValueError("invalid dashboard cursor") from exc
    except (TypeError, UnicodeDecodeError) as exc:
        raise ValueError("invalid dashboard cursor") from exc


def _public_item(item: BacklogItem) -> DashboardItem:
    return DashboardItem(
        backlog_id=item.backlog_id, source_kind=item.source_kind, candidate_kind=item.candidate_kind,
        authoritative_status=item.authoritative_status, priority_band=item.priority_band,
        triage_lane=item.triage_lane, release_level=item.release_level,
        acknowledgement_state=item.acknowledgement_state, assignment_state=item.assignment_state,
        deferral_until=item.deferral_until, content_available=False, detail_available=True,
    )


def dashboard_digest(workspace: str, *, subject_id: str = "", policy_config: str | None = None,
                     maximum_release_level: str = "private", page_size: int = 20, cursor: str = "", scope_ids: list[str] | None = None,
                     owner_subject_ids: list[str] | None = None, due_before: str | None = None, overdue: bool = False,
                     statuses: list[str] | None = None, triage_lanes: list[str] | None = None) -> DashboardDigest:
    if page_size < 1 or page_size > 100:
        raise ValueError("page_size must be between 1 and 100")
    full = aggregate_backlog(workspace, subject_id=subject_id, policy_config=policy_config,
                             maximum_release_level=maximum_release_level, limit=None, scope_ids=scope_ids,
                             owner_subject_ids=owner_subject_ids, due_before=due_before, overdue=overdue,
                             statuses=statuses, triage_lanes=triage_lanes)
    offset = _decode_cursor(cursor, full)
    page = full.items[offset:offset + page_size]
    next_cursor = _encode_cursor(offset + page_size, full) if offset + page_size < len(full.items) else ""
    return DashboardDigest(
        generated_at=full.generated_at, workspace_id=full.workspace_id, visible_total=full.visible_total,
        urgent_count=full.urgent_count, counts_by_source_kind=full.counts_by_source_kind,
        counts_by_candidate_kind=full.counts_by_candidate_kind, counts_by_priority_band=full.counts_by_priority_band,
        items=[_public_item(item) for item in page], next_cursor=next_cursor,
        policy_context_hash=full.policy_context_hash, redaction_summary=full.redaction_summary,
        diagnostics=full.diagnostics,
    )


def dashboard_item_detail(workspace: str, backlog_id: str, *, subject_id: str = "", policy_config: str | None = None,
                          maximum_release_level: str = "private") -> DashboardDetail:
    full = aggregate_backlog(workspace, subject_id=subject_id, policy_config=policy_config,
                             maximum_release_level=maximum_release_level, limit=None)
    item = next((candidate for candidate in full.items if candidate.backlog_id == backlog_id), None)
    if item is None:
        raise ValueError("dashboard item is not visible or does not exist")
    return DashboardDetail(
        generated_at=full.generated_at, workspace_id=full.workspace_id, item=_public_item(item),
        reason_codes=item.reason_codes, required_actions=item.required_actions,
        priority_factors=item.priority_factors, policy_obligations=item.policy_obligations,
    )
