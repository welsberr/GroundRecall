from __future__ import annotations

import pytest
from pydantic import ValidationError

from groundrecall.application_contract import (
    ApplicationResult,
    CapabilityResponse,
    MatchReason,
    SearchRequest,
    SearchResponse,
    SourceReference,
    application_json_schema,
)


def _result() -> ApplicationResult:
    return ApplicationResult(
        stable_id="claim::migration",
        kind="claim",
        title="Migration has multiple causes",
        excerpt="A bounded synthetic fixture.",
        human_url="/records/claim%3A%3Amigration",
        source_references=[SourceReference(source_id="artifact::biology", authority="reviewed")],
        review_state="reviewed",
        freshness="current",
        match_reason=MatchReason(kind="lexical", detail="matched migration"),
        evidence_confidence="moderate",
    )


def test_search_contract_is_bounded_and_forbids_store_selection() -> None:
    request = SearchRequest(query=" migration ", limit=3)
    assert request.query == "migration"
    with pytest.raises(ValidationError):
        SearchRequest(query="ok", store_dir="/private/store")
    with pytest.raises(ValidationError):
        SearchRequest(query="x" * 513)


def test_search_response_preserves_generation_scope_and_unknowns() -> None:
    response = SearchResponse(
        request_id="req-1",
        index_generation="generation-7",
        effective_scope="private",
        results=[_result()],
    )
    payload = response.model_dump()
    assert payload["schema_version"].endswith("search_response.v1")
    assert payload["results"][0]["evidence_confidence"] == "moderate"
    assert payload["results"][0]["contradiction"] == ""


def test_capabilities_default_writes_and_changes_disabled() -> None:
    response = CapabilityResponse(request_id="req-2")
    assert response.operations == {"search": True, "record_read": True, "capture": False, "changes": False}


def test_schema_bundle_is_publishable() -> None:
    bundle = application_json_schema()
    assert bundle["schema_version"] == "groundrecall.application.v1"
    assert set(bundle["schemas"]) == {"SearchRequest", "SearchResponse", "RecordResponse", "CapabilityResponse"}
