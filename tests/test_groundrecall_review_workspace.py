from __future__ import annotations

import json
from pathlib import Path

from groundrecall.ingest import run_groundrecall_import
from groundrecall.promotion import promote_import_to_store
from groundrecall.review_workspace import GroundRecallReviewWorkspace
from groundrecall.store import GroundRecallStore


def _build_citation_fixture(root: Path) -> Path:
    (root / "wiki").mkdir(parents=True)
    (root / "wiki" / "learning-theory.md").write_text(
        "# Learning Theory\n\n"
        "Matching-law style regularities can be compared with machine learning optimization.\n\n"
        "See \\\\cite{herrnstein1961matching} for the classic framing.\n",
        encoding="utf-8",
    )
    return root


def _build_relation_fixture(root: Path) -> Path:
    (root / "wiki").mkdir(parents=True)
    (root / "wiki" / "relations.md").write_text(
        "# Channel Capacity\n\n"
        "## Shannon Entropy\n\n"
        "- Channel capacity and Shannon entropy are co-mentioned in coding theorem discussions.\n",
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
    assert "graph_diagnostics" in review_data
    assert "graph_summary" in review_data["import_context"]
    assert "top_queue_items" in review_data["import_context"]
    assert review_data["graph_diagnostics"]["summary"]["concept_count"] >= 1
    concept_review = next(item for item in review_data["concept_reviews"] if item["concept_id"] == "learning-theory")
    assert "review_priority" in concept_review
    assert "triage_lane" in concept_review
    assert "finding_codes" in concept_review
    assert "graph_codes" in concept_review


def test_review_workspace_populates_persists_and_promotes_relation_reviews(tmp_path: Path) -> None:
    source_root = _build_relation_fixture(tmp_path / "llmwiki")
    import_result = run_groundrecall_import(
        source_root,
        out_root=tmp_path / "imports",
        mode="quick",
        import_id="relation-review-fixture",
        extract_graph="heuristic",
    )

    workspace = GroundRecallReviewWorkspace(import_result.out_dir)
    payload = workspace.load_review_data()
    assert payload["relation_reviews"]
    relation_review = payload["relation_reviews"][0]

    assert relation_review["provenance_class"] == "inferred"
    assert relation_review["evidence_previews"]
    assert "relation_field_specs" in payload
    assert "relation_guidance" in payload["review_guidance"]

    workspace.apply_updates(
        concept_updates=[
            {"concept_id": "channel-capacity", "status": "trusted"},
            {"concept_id": "shannon-entropy", "status": "trusted"},
        ],
        relation_updates=[
            {
                "relation_review_id": relation_review["relation_review_id"],
                "status": "rejected",
                "notes": ["Co-mention alone is not enough for this graph edge."],
            }
        ],
        reviewer="Unit Test Reviewer",
    )

    session = json.loads((import_result.out_dir / "review_session.json").read_text(encoding="utf-8"))
    relation_session = next(
        item for item in session["relation_reviews"] if item["relation_review_id"] == relation_review["relation_review_id"]
    )
    assert relation_session["status"] == "rejected"
    assert session["ledger"][-1]["action"]["action_type"] == "edit_relation"

    store_dir = tmp_path / "store"
    promote_import_to_store(import_result.out_dir, store_dir, reviewer="Unit Test Reviewer")
    store = GroundRecallStore(store_dir)
    relation = store.get_relation(relation_session["relation_id"])
    assert relation is not None
    assert relation.current_status == "rejected"


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
        "  year = {1974},\n"
        "  doi = {10.1901/jeab.1974.22-231},\n"
        "  abstract = {Classic analysis of deviations from the matching law in operant choice experiments.}\n"
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
    assert payload["bibliography"]["abstract_entry_count"] == 1
    assert payload["bibliography"]["doi_entry_count"] == 1
    assert payload["bibliography"]["year_range"] == [1974, 1974]
    concept_review = next(item for item in payload["concept_reviews"] if item["concept_id"] == "matching")
    assert "analysis_lanes" in concept_review
    citation_support = concept_review["top_claims"][0]["citation_support"][0]
    assert concept_review["top_claims"][0]["analysis_lane"] == "empirical"
    assert concept_review["top_claims"][0]["argument_role"] in {"premise", "context"}
    assert citation_support["resolved_entry_count"] == 1
    assert citation_support["abstract_entry_count"] == 1
    assert "matching law" in citation_support["abstract_snippets"][0].lower()
    suggestions = concept_review["top_claims"][0]["support_suggestions"]
    assert suggestions == []


def test_review_workspace_surfaces_local_bibliography_support_suggestions(tmp_path: Path) -> None:
    root = tmp_path / "llmwiki"
    (root / "wiki").mkdir(parents=True)
    (root / "wiki" / "drift.md").write_text(
        "# Drift\n\n"
        "- Random genetic drift can dominate allele-frequency change in small populations.\n",
        encoding="utf-8",
    )
    (root / "refs.bib").write_text(
        "@article{kimura1968evolutionary,\n"
        "  author = {Motoo Kimura},\n"
        "  title = {Evolutionary Rate at the Molecular Level},\n"
        "  journal = {Nature},\n"
        "  year = {1968},\n"
        "  abstract = {The rate of molecular evolution is compatible with neutral changes driven by random genetic drift in populations.}\n"
        "}\n",
        encoding="utf-8",
    )

    import_result = run_groundrecall_import(root, out_root=tmp_path / "imports", mode="quick", import_id="support-suggestions")
    workspace = GroundRecallReviewWorkspace(import_result.out_dir)
    payload = workspace.load_review_data()

    concept_review = next(item for item in payload["concept_reviews"] if item["concept_id"] == "drift")
    suggestions = concept_review["top_claims"][0]["support_suggestions"]
    assert concept_review["analysis_lanes"]["empirical"] >= 1
    assert concept_review["source_role_summary"]
    assert suggestions
    assert suggestions[0]["citation_key"] == "kimura1968evolutionary"
    assert "abstract" in suggestions[0]["reason"].lower() or "title" in suggestions[0]["reason"].lower()


def test_review_workspace_surfaces_source_roles_and_distinctions(tmp_path: Path) -> None:
    root = tmp_path / "llmwiki"
    (root / "wiki").mkdir(parents=True)
    (root / "wiki" / "selection.md").write_text(
        "# Selection\n\n"
        "- Natural selection does not imply adaptation.\n",
        encoding="utf-8",
    )

    import_result = run_groundrecall_import(root, out_root=tmp_path / "imports", mode="quick", import_id="distinction-review")
    workspace = GroundRecallReviewWorkspace(import_result.out_dir)
    payload = workspace.load_review_data()

    concept_review = next(item for item in payload["concept_reviews"] if item["concept_id"] == "selection")
    claim = concept_review["top_claims"][0]
    assert claim["source_roles"] == ["overview"]
    assert claim["distinction"]["distinction_type"] == "non_implication"
    assert claim["supporting_observations"][0]["source_role"] == "overview"
    assert concept_review["key_distinctions"][0]["distinction_type"] == "non_implication"


def test_review_workspace_can_use_separate_bibliography_root(tmp_path: Path) -> None:
    root = tmp_path / "pilot"
    source_root = root / "source"
    bib_root = root / "bibliography"
    (source_root / "wiki").mkdir(parents=True)
    bib_root.mkdir(parents=True)
    (source_root / "wiki" / "drift.md").write_text(
        "# Drift\n\n"
        "- Random genetic drift can dominate allele-frequency change in small populations.\n",
        encoding="utf-8",
    )
    (bib_root / "refs.bib").write_text(
        "@article{kimura1968evolutionary,\n"
        "  author = {Motoo Kimura},\n"
        "  title = {Evolutionary Rate at the Molecular Level},\n"
        "  journal = {Nature},\n"
        "  year = {1968},\n"
        "  abstract = {The rate of molecular evolution is compatible with neutral changes driven by random genetic drift in populations.}\n"
        "}\n",
        encoding="utf-8",
    )

    import_result = run_groundrecall_import(source_root, out_root=tmp_path / "imports", mode="quick", import_id="separate-bib-root")
    manifest_path = import_result.out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["bibliography_root"] = str(bib_root)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    workspace = GroundRecallReviewWorkspace(import_result.out_dir)
    payload = workspace.load_review_data()
    concept_review = next(item for item in payload["concept_reviews"] if item["concept_id"] == "drift")
    suggestions = concept_review["top_claims"][0]["support_suggestions"]
    assert payload["bibliography"]["entry_count"] == 1
    assert suggestions
    assert suggestions[0]["citation_key"] == "kimura1968evolutionary"
