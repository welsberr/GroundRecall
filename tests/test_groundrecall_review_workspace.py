from __future__ import annotations

import json
from pathlib import Path

from groundrecall.ingest import run_groundrecall_import
from groundrecall.review_workspace import GroundRecallReviewWorkspace


def _build_citation_fixture(root: Path) -> Path:
    (root / "wiki").mkdir(parents=True)
    (root / "wiki" / "learning-theory.md").write_text(
        "# Learning Theory\n\n"
        "Matching-law style regularities can be compared with machine learning optimization.\n\n"
        "See \\\\cite{herrnstein1961matching} for the classic framing.\n",
        encoding="utf-8",
    )
    return root


def test_review_workspace_populates_and_persists_citation_reviews(tmp_path: Path) -> None:
    source_root = _build_citation_fixture(tmp_path / "llmwiki")
    import_result = run_groundrecall_import(source_root, out_root=tmp_path / "imports", mode="quick", import_id="review-fixture")

    workspace = GroundRecallReviewWorkspace(import_result.out_dir)
    payload = workspace.load_review_data()
    assert payload["citation_reviews"]
    citation_review_id = payload["citation_reviews"][0]["citation_review_id"]

    workspace.apply_updates(
        concept_updates=[
            {
                "concept_id": "learning-theory",
                "status": "trusted",
                "notes": ["Strong framing concept.", "Citation support looks plausible."],
            }
        ],
        citation_updates=[
            {
                "citation_review_id": citation_review_id,
                "status": "verified",
                "notes": ["Classic matching-law citation."],
            }
        ],
        reviewer="Unit Test Reviewer",
    )

    session = json.loads((import_result.out_dir / "review_session.json").read_text(encoding="utf-8"))
    concept = next(item for item in session["draft_pack"]["concepts"] if item["concept_id"] == "learning-theory")
    citation = next(item for item in session["citation_reviews"] if item["citation_review_id"] == citation_review_id)

    assert session["reviewer"] == "Unit Test Reviewer"
    assert concept["status"] == "trusted"
    assert citation["status"] == "verified"

    review_data = json.loads((import_result.out_dir / "review_data.json").read_text(encoding="utf-8"))
    assert any(item["citation_review_id"] == citation_review_id for item in review_data["citation_reviews"])


def test_review_workspace_resolves_citation_metadata_from_bibtex(tmp_path: Path) -> None:
    root = tmp_path / "llmwiki"
    (root / "wiki").mkdir(parents=True)
    (root / "wiki" / "matching.md").write_text(
        "# Matching\n\n"
        "The manuscript cites \\\\cite{baum1974generalized} here.\n",
        encoding="utf-8",
    )
    (root / "refs.bib").write_text(
        "@article{baum1974generalized,\n"
        "  author = {W. M. Baum},\n"
        "  title = {On two types of deviation from the matching law: Bias and undermatching},\n"
        "  journal = {Journal of the Experimental Analysis of Behavior},\n"
        "  year = {1974}\n"
        "}\n",
        encoding="utf-8",
    )

    import_result = run_groundrecall_import(root, out_root=tmp_path / "imports", mode="quick", import_id="bib-fixture")
    workspace = GroundRecallReviewWorkspace(import_result.out_dir)
    payload = workspace.load_review_data()

    entry = next(item for item in payload["citation_reviews"] if item["citation_key"] == "baum1974generalized")
    assert entry["title"] == "On two types of deviation from the matching law: Bias and undermatching"
    assert entry["source_bib_path"] == "refs.bib"
    assert entry["raw_bibtex"]
    assert payload["bibliography"]["entry_count"] >= 1
