from pathlib import Path

from groundrecall.application_contract import SearchRequest
from groundrecall.application_service import ApplicationReadService
from groundrecall.models import ArtifactRecord, ClaimRecord, ConceptRecord, ProvenanceRecord
from groundrecall.store import GroundRecallStore


def test_application_service_search_returns_contract_results(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path)
    store.save_claim(ClaimRecord(claim_id="migration", claim_text="Migration has multiple causes", concept_ids=["migration"]))
    store.save_concept(ConceptRecord(concept_id="migration", title="Migration"))

    service = ApplicationReadService(tmp_path)
    response = service.search(SearchRequest(query="multiple causes", limit=5), request_id="req-search")

    assert response.request_id == "req-search"
    assert response.index_generation.startswith("search-index-v1:")
    assert response.results[0].stable_id == "claim::migration"
    assert response.results[0].human_url == "/records/claim%3A%3Amigration"


def test_application_service_reads_record_and_relationships(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path)
    store.save_claim(ClaimRecord(claim_id="migration", claim_text="Migration has multiple causes", concept_ids=["migration"]))
    store.save_concept(ConceptRecord(concept_id="migration", title="Migration"))

    response = ApplicationReadService(tmp_path).read_record("claim::migration", request_id="req-record")
    assert response is not None
    assert response.request_id == "req-record"
    assert response.record.match_reason.kind == "exact_id"
    assert any(item["kind"] == "concept" for item in response.relationships)
    assert ApplicationReadService(tmp_path).read_record("claim::missing") is None


def test_capabilities_are_read_only_and_publish_generation(tmp_path: Path) -> None:
    response = ApplicationReadService(tmp_path).capabilities(request_id="req-cap")
    assert response.request_id == "req-cap"
    assert response.index_generations == []
    assert response.operations["capture"] is False


def test_application_results_do_not_expose_local_filesystem_paths(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path)
    store.save_artifact(
        ArtifactRecord(
            artifact_id="artifact-local-path",
            artifact_kind="note",
            title="Local path evidence",
            path=str(tmp_path / "private-note.md"),
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim-local-path",
            claim_text="A local path should stay private.",
            provenance=ProvenanceRecord(origin_path=str(tmp_path / "private-note.md")),
        )
    )

    response = ApplicationReadService(tmp_path).search(SearchRequest(query="local path", limit=10))
    serialized = response.model_dump_json()

    assert str(tmp_path) not in serialized
    assert "local path evidence" in serialized.lower()
