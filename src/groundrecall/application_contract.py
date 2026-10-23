"""Versioned, model-free contract for ordinary GroundRecall applications.

The contract is deliberately transport-neutral.  HTTP, browser, CLI, and MCP
adapters can validate the same shapes without exposing store paths or making
retrieval relevance look like evidence confidence.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


APPLICATION_SCHEMA_VERSION = "groundrecall.application.v1"
SEARCH_REQUEST_SCHEMA_VERSION = "groundrecall.application.search_request.v1"
SEARCH_RESPONSE_SCHEMA_VERSION = "groundrecall.application.search_response.v1"
RECORD_RESPONSE_SCHEMA_VERSION = "groundrecall.application.record_response.v1"
CAPABILITIES_SCHEMA_VERSION = "groundrecall.application.capabilities.v1"


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SearchRequest(_ContractModel):
    """Bounded search input; callers cannot select a store or identity."""

    schema_version: Literal[SEARCH_REQUEST_SCHEMA_VERSION] = SEARCH_REQUEST_SCHEMA_VERSION
    query: str = Field(min_length=1, max_length=512)
    scope: str = Field(default="private", min_length=1, max_length=128)
    kinds: list[str] = Field(default_factory=list, max_length=20)
    corpora: list[str] = Field(default_factory=list, max_length=20)
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str = Field(default="", max_length=2048)


class SourceReference(_ContractModel):
    source_id: str = Field(min_length=1, max_length=256)
    title: str = Field(default="", max_length=512)
    human_url: str = Field(default="", max_length=2048)
    authority: str = Field(default="unknown", max_length=128)
    retrieval_date: str = Field(default="", max_length=64)


class MatchReason(_ContractModel):
    kind: Literal["lexical", "exact_id", "filter"]
    detail: str = Field(min_length=1, max_length=512)


class ApplicationResult(_ContractModel):
    stable_id: str = Field(min_length=1, max_length=256)
    kind: str = Field(min_length=1, max_length=128)
    title: str = Field(default="", max_length=1024)
    excerpt: str = Field(default="", max_length=4096)
    human_url: str = Field(min_length=1, max_length=2048)
    source_references: list[SourceReference] = Field(default_factory=list, max_length=100)
    source_authority: str = Field(default="unknown", max_length=128)
    review_state: str = Field(default="unknown", max_length=128)
    freshness: str = Field(default="unknown", max_length=128)
    supersession: str = Field(default="", max_length=512)
    contradiction: str = Field(default="", max_length=512)
    record_version: str = Field(default="", max_length=128)
    match_reason: MatchReason
    evidence_confidence: str = Field(default="unknown", max_length=128)


class SearchResponse(_ContractModel):
    schema_version: Literal[SEARCH_RESPONSE_SCHEMA_VERSION] = SEARCH_RESPONSE_SCHEMA_VERSION
    request_id: str = Field(min_length=1, max_length=128)
    next_cursor: str = Field(default="", max_length=2048)
    index_generation: str = Field(min_length=1, max_length=256)
    effective_scope: str = Field(min_length=1, max_length=128)
    partial: bool = False
    degraded: bool = False
    results: list[ApplicationResult] = Field(default_factory=list, max_length=100)
    diagnostics: list[str] = Field(default_factory=list, max_length=20)


class RecordResponse(_ContractModel):
    schema_version: Literal[RECORD_RESPONSE_SCHEMA_VERSION] = RECORD_RESPONSE_SCHEMA_VERSION
    request_id: str = Field(min_length=1, max_length=128)
    index_generation: str = Field(min_length=1, max_length=256)
    effective_scope: str = Field(min_length=1, max_length=128)
    record: ApplicationResult
    relationships: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    history: list[dict[str, Any]] = Field(default_factory=list, max_length=200)


class CapabilityResponse(_ContractModel):
    schema_version: Literal[CAPABILITIES_SCHEMA_VERSION] = CAPABILITIES_SCHEMA_VERSION
    request_id: str = Field(min_length=1, max_length=128)
    api_versions: list[str] = Field(default_factory=lambda: ["v1"], max_length=20)
    operations: dict[str, bool] = Field(default_factory=lambda: {"search": True, "record_read": True, "capture": False, "changes": False})
    index_generations: list[str] = Field(default_factory=list, max_length=20)


def application_json_schema() -> dict[str, Any]:
    """Return a stable bundle of JSON schemas for contract publication."""
    return {
        "schema_version": APPLICATION_SCHEMA_VERSION,
        "schemas": {
            name: model.model_json_schema()
            for name, model in (
                ("SearchRequest", SearchRequest),
                ("SearchResponse", SearchResponse),
                ("RecordResponse", RecordResponse),
                ("CapabilityResponse", CapabilityResponse),
            )
        },
    }
