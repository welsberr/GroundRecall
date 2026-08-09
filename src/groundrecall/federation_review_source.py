"""Mockable, read-only broker review source for dashboard integration (RB6b)."""
from __future__ import annotations

import base64
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from .policy import RELEASE_RANK


class RemoteReviewItem(BaseModel):
    schema_version: str = "groundrecall.remote-review-item.v1"
    item_id: str
    broker_id: str
    producer_instance_id: str
    content_hash: str
    version_hash: str
    release_level: str = "private"
    scope_id: str = ""
    required_reviewer_roles: list[str] = Field(default_factory=list)
    signature_status: Literal["valid", "invalid", "missing", "unverified"] = "unverified"
    trust_status: Literal["trusted", "untrusted", "revoked", "unknown"] = "unknown"
    quarantine_status: Literal["none", "quarantined", "rejected"] = "none"
    revocation_status: Literal["active", "revoked"] = "active"
    supersession_status: Literal["current", "superseded"] = "current"
    freshness_status: Literal["fresh", "stale", "unknown"] = "unknown"
    state: Literal["discovery", "reviewable"] = "discovery"
    local_only: bool = False


class RemoteReviewSnapshot(BaseModel):
    schema_version: str = "groundrecall.remote-review-snapshot.v1"
    broker_id: str
    producer_instance_id: str
    retrieved_at: str
    generated_at: str = ""
    snapshot_hash: str = ""
    freshness_status: Literal["fresh", "stale", "unknown"] = "unknown"
    signature_status: str = "unverified"
    trust_status: str = "unknown"
    offline: bool = False
    items: list[RemoteReviewItem] = Field(default_factory=list)


class FederationReviewSource(Protocol):
    def page(self, *, page_size: int = 20, cursor: str = "", maximum_release_level: str = "private") -> tuple[list[RemoteReviewItem], str, RemoteReviewSnapshot]: ...


class FixtureFederationReviewSource:
    """Deterministic fixture adapter; it never imports or writes canonical records."""

    def __init__(self, snapshot: RemoteReviewSnapshot):
        self.snapshot = snapshot

    def page(self, *, page_size: int = 20, cursor: str = "", maximum_release_level: str = "private") -> tuple[list[RemoteReviewItem], str, RemoteReviewSnapshot]:
        if page_size < 1 or page_size > 100:
            raise ValueError("page_size must be between 1 and 100")
        try:
            offset = int(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()) if cursor else 0
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError("invalid federation cursor") from exc
        if offset < 0:
            raise ValueError("invalid federation cursor")
        allowed = RELEASE_RANK.get(maximum_release_level, RELEASE_RANK["private"])
        visible = [item for item in self.snapshot.items
                   if RELEASE_RANK.get(item.release_level, RELEASE_RANK["private"]) <= allowed
                   and item.signature_status == "valid" and item.trust_status == "trusted"
                   and item.revocation_status != "revoked" and item.quarantine_status == "none"
                   and item.supersession_status != "superseded"]
        page = visible[offset:offset + page_size]
        next_cursor = base64.urlsafe_b64encode(str(offset + page_size).encode()).decode().rstrip("=") if offset + page_size < len(visible) else ""
        return page, next_cursor, self.snapshot
