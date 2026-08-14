import copy
import json
from pathlib import Path

import pytest

from groundrecall.library_argument_bundle_r5 import generate_r5_candidates, record_r5_adjudication


FIXTURE = Path(__file__).parents[1] / "docs/fixtures/library.argument_bundle.v1.golden.json"


def test_r5_is_deterministic_private_and_does_not_mutate_bundle() -> None:
    bundle = json.loads(FIXTURE.read_text())
    original = copy.deepcopy(bundle)
    domains = [{"domain_id": "foundation.population", "label": "Population biology", "keywords": ["population", "population-level"]}]
    first = generate_r5_candidates(bundle, knowledge_domains=domains)
    second = generate_r5_candidates(bundle, knowledge_domains=domains)
    assert first == second
    assert bundle == original
    assert first["evidence_cards"]
    assert all(item["release_level"] == "private" and item["review_state"] == "draft" for item in first["evidence_cards"])
    assert first["foundation_dossiers"][0]["evidence_card_ids"]


def test_r5_cards_preserve_claim_and_citation_spans_and_limit_abstracts_to_triage() -> None:
    bundle = json.loads(FIXTURE.read_text())
    result = generate_r5_candidates(bundle, bibliography_entries={"source.article.example": {"fields": {"doi": "10/example", "abstract": "Population change is measured across populations."}}})
    card = next(item for item in result["evidence_cards"] if item["claim_id"] == "claim.article.premise")
    assert "span.article.lines.10-12" in card["source_span_ids"]
    assert card["source_quality_flags"]["abstract_triage_available"] is True
    assert card["source_quality_flags"]["quality_assessment"] == "not_assessed"
    assert card["truth_status"] == "not_assessed"


def test_r5_adjudication_is_explicit_review_scaffold_and_never_promotes() -> None:
    candidate = {"adjudication_id": "adj.x", "evidence_card_id": "card.x", "decision": "pending", "review_state": "draft", "release_level": "private"}
    result = record_r5_adjudication(candidate, reviewer_id="expert-1", decision="partially_supported", rationale="The cited span is narrower than the claim.", counterevidence_considered=["span.counter"], limitations_acknowledged=["scope"])
    assert result["decision"] == "partially_supported"
    assert result["review_state"] == "draft"
    assert result["release_level"] == "private"
    assert result["truth_status"] == "not_assessed"
    with pytest.raises(ValueError):
        record_r5_adjudication(candidate, reviewer_id="expert-1", decision="true", rationale="")
