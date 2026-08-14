import copy
import json
from pathlib import Path

import pytest

from groundrecall.library_argument_bundle_r5 import generate_r5_candidates
from groundrecall.library_argument_bundle_r6 import compile_knowledge_basis_manifest, preflight_library_argument_bundle


FIXTURE = Path(__file__).parents[1] / "docs/fixtures/library.argument_bundle.v1.golden.json"


def test_r6_manifest_is_deterministic_and_private_draft() -> None:
    bundle = json.loads(FIXTURE.read_text())
    r5 = generate_r5_candidates(bundle)
    original = copy.deepcopy(bundle)
    first = compile_knowledge_basis_manifest(bundle, r5=r5)
    second = compile_knowledge_basis_manifest(bundle, r5=r5)
    assert first == second
    assert bundle == original
    assert first["source_ids"] == ["source.article.example", "source.video.example"]
    assert first["evidence_card_ids"]
    assert first["release_level"] == "private"
    assert first["review_state"] == "draft"
    assert first["coverage"]["gaps"]


def test_r6_preflight_mechanically_reports_all_relevant_blockers() -> None:
    bundle = json.loads(FIXTURE.read_text())
    report = preflight_library_argument_bundle(bundle, r5=generate_r5_candidates(bundle), target="downstream")
    assert report["passed"] is False
    assert report["release_allowed"] is False
    assert {item["gate"] for item in report["findings"]} >= {"required_review", "provenance", "citation", "completeness", "private_records"}
    assert report["release_level"] == "private"
    assert report["review_state"] == "draft"


def test_r6_rejects_unknown_target() -> None:
    bundle = json.loads(FIXTURE.read_text())
    with pytest.raises(ValueError, match="target"):
        preflight_library_argument_bundle(bundle, target="publish")
