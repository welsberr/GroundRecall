from __future__ import annotations

import json
from pathlib import Path

from groundrecall.groundrecall_normalizer import standardize_concept_rows
from groundrecall.ingest import run_groundrecall_import
from groundrecall.graph_diagnostics import build_graph_diagnostics
from groundrecall.lint import lint_import_directory
from groundrecall.models import ConceptRecord
from groundrecall.store import GroundRecallStore


def _read_jsonl(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    return [json.loads(line) for line in text.splitlines()]


def _build_graph_extraction_fixture(root: Path) -> Path:
    (root / "wiki").mkdir(parents=True)
    (root / "wiki" / "concepts.md").write_text(
        "# Channel Capacity\n\n"
        "## Shannon Entropy\n\n"
        "- Channel capacity and Shannon entropy are compared in coding theorem examples.\n",
        encoding="utf-8",
    )
    return root


def _build_standardization_fixture(root: Path) -> Path:
    (root / "wiki").mkdir(parents=True)
    (root / "wiki" / "standardization.md").write_text(
        "# Signal Processing\n\n"
        "## The Signal Processing\n\n"
        "## Signal Processing Model\n\n"
        "- Signal processing and the signal processing model should be distinguished during review.\n",
        encoding="utf-8",
    )
    return root


def test_groundrecall_import_emits_normalized_artifacts(tmp_path: Path) -> None:
    root = tmp_path / "llmwiki"
    (root / "wiki").mkdir(parents=True)
    (root / "raw").mkdir()
    (root / "logs").mkdir()

    (root / "wiki" / "channel-capacity.md").write_text(
        "# Channel Capacity\n\n"
        "- Reliable rate upper bound for a noisy channel.\n\n"
        "See also [[Shannon Entropy]].\n",
        encoding="utf-8",
    )
    (root / "raw" / "notes.md").write_text(
        "Speculation: Capacity may depend on constraints.\n",
        encoding="utf-8",
    )
    (root / "logs" / "session.log").write_text(
        "Learner asked about entropy and communication limits.\n",
        encoding="utf-8",
    )

    result = run_groundrecall_import(root, mode="quick", import_id="import-test")

    assert result.out_dir == root / "imports" / "import-test"
    manifest = json.loads((result.out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_repo_kind"] == "llmwiki"
    assert manifest["artifact_count"] == 3
    assert manifest["claim_count"] >= 1

    artifacts = _read_jsonl(result.out_dir / "artifacts.jsonl")
    assert {item["artifact_kind"] for item in artifacts} == {"compiled_page", "raw_note", "session_log"}

    fragments = _read_jsonl(result.out_dir / "fragments.jsonl")
    assert len(fragments) >= 3
    assert all(item["source_id"].startswith("ia_") for item in fragments)

    claims = _read_jsonl(result.out_dir / "claims.jsonl")
    assert any("Reliable rate upper bound" in item["claim_text"] for item in claims)
    assert any(item["supporting_fragment_ids"] for item in claims)
    assert all("metadata" in item for item in claims)
    assert any(item["metadata"].get("analysis_lane") == "empirical" for item in claims)

    concepts = _read_jsonl(result.out_dir / "concepts.jsonl")
    concept_ids = {item["concept_id"] for item in concepts}
    assert "concept::channel-capacity" in concept_ids
    assert "concept::shannon-entropy" in concept_ids

    relations = _read_jsonl(result.out_dir / "relations.jsonl")
    assert any(item["target_id"] == "concept::shannon-entropy" for item in relations)
    graph_diagnostics = json.loads((result.out_dir / "graph_diagnostics.json").read_text(encoding="utf-8"))
    assert graph_diagnostics["summary"]["connected_component_count"] >= 1
    assert graph_diagnostics["summary"]["concept_count"] == len(concepts)

    lint_payload = json.loads((result.out_dir / "lint_findings.json").read_text(encoding="utf-8"))
    assert "summary" in lint_payload
    assert lint_payload["summary"]["warning_count"] >= 0

    review_queue = json.loads((result.out_dir / "review_queue.json").read_text(encoding="utf-8"))
    assert review_queue["queue_length"] >= 1
    assert any(item["candidate_type"] == "claim" for item in review_queue["items"])
    assert any(item["candidate_type"] == "concept" for item in review_queue["items"])
    review_session = json.loads((result.out_dir / "review_session.json").read_text(encoding="utf-8"))
    assert review_session["reviewer"] == "GroundRecall Import"
    assert review_session["draft_pack"]["pack"]["source_import_id"] == "import-test"
    assert any(item["concept_id"] == "channel-capacity" for item in review_session["draft_pack"]["concepts"])
    review_data = json.loads((result.out_dir / "review_data.json").read_text(encoding="utf-8"))
    assert review_data["reviewer"] == "GroundRecall Import"
    assert "field_specs" in review_data
    assert any(item["field"] == "status" for item in review_data["field_specs"])
    assert "review_guidance" in review_data
    assert "concept_reviews" in review_data
    assert "relation_reviews" in review_data
    assert "relation_field_specs" in review_data
    assert "citations" in review_data
    assert "citation_reviews" in review_data
    assert "analysis_lanes" in review_data["review_guidance"]


def test_graph_extraction_is_disabled_by_default(tmp_path: Path) -> None:
    root = _build_graph_extraction_fixture(tmp_path / "llmwiki")

    result = run_groundrecall_import(root, mode="quick", import_id="graph-default")

    manifest = json.loads((result.out_dir / "manifest.json").read_text(encoding="utf-8"))
    relations = _read_jsonl(result.out_dir / "relations.jsonl")
    candidates = json.loads((result.out_dir / "graph_extraction_candidates.json").read_text(encoding="utf-8"))

    assert manifest["graph_extraction"]["mode"] == "none"
    assert candidates["candidate_relation_count"] == 0
    assert not any(item["relation_type"] == "co_occurs_with" for item in relations)


def test_heuristic_graph_extraction_emits_reviewable_relation_candidates(tmp_path: Path) -> None:
    root = _build_graph_extraction_fixture(tmp_path / "llmwiki")

    result = run_groundrecall_import(root, mode="quick", import_id="graph-heuristic", extract_graph="heuristic")

    manifest = json.loads((result.out_dir / "manifest.json").read_text(encoding="utf-8"))
    relations = _read_jsonl(result.out_dir / "relations.jsonl")
    candidates = json.loads((result.out_dir / "graph_extraction_candidates.json").read_text(encoding="utf-8"))
    review_queue = json.loads((result.out_dir / "review_queue.json").read_text(encoding="utf-8"))

    extracted = [item for item in relations if item["relation_type"] == "co_occurs_with"]
    assert manifest["graph_extraction"]["mode"] == "heuristic"
    assert manifest["graph_extraction"]["candidate_relation_count"] == 1
    assert candidates["candidate_relation_count"] == 1
    assert len(extracted) == 1
    assert extracted[0]["source_id"] == "concept::channel-capacity"
    assert extracted[0]["target_id"] == "concept::shannon-entropy"
    assert extracted[0]["support_kind"] == "inferred"
    assert extracted[0]["grounding_status"] == "partially_grounded"
    assert extracted[0]["current_status"] == "draft"
    assert extracted[0]["evidence_ids"]

    relation_items = [item for item in review_queue["items"] if item["candidate_type"] == "relation"]
    assert len(relation_items) == 1
    assert relation_items[0]["candidate_id"] == extracted[0]["relation_id"]
    assert "relation_inferred" in relation_items[0]["finding_codes"]


def test_concept_standardization_merges_duplicate_titles_into_aliases() -> None:
    concept_rows = [
        {
            "concept_id": "concept::signal-processing",
            "title": "Signal Processing",
            "aliases": [],
            "description": "",
            "source_artifact_ids": ["ia_one"],
            "current_status": "triaged",
        },
        {
            "concept_id": "concept::signal-processing-variant",
            "title": "The Signal Processing",
            "aliases": ["DSP"],
            "description": "",
            "source_artifact_ids": ["ia_two"],
            "current_status": "triaged",
        },
    ]
    claim_rows = [
        {
            "claim_id": "clm_1",
            "concept_ids": ["concept::signal-processing-variant"],
        }
    ]
    relation_rows = [
        {
            "relation_id": "rel_1",
            "source_id": "concept::signal-processing-variant",
            "target_id": "concept::signal-processing",
        }
    ]

    concepts, claims, relations = standardize_concept_rows(concept_rows, claim_rows, relation_rows)

    assert len(concepts) == 1
    assert concepts[0]["concept_id"] == "concept::signal-processing"
    assert concepts[0]["aliases"] == ["DSP", "The Signal Processing"]
    assert concepts[0]["source_artifact_ids"] == ["ia_one", "ia_two"]
    assert claims[0]["concept_ids"] == ["concept::signal-processing"]
    assert relations[0]["source_id"] == "concept::signal-processing"


def test_import_writes_concept_standardization_report_and_review_codes(tmp_path: Path) -> None:
    root = _build_standardization_fixture(tmp_path / "llmwiki")

    result = run_groundrecall_import(root, mode="quick", import_id="standardization-test")

    manifest = json.loads((result.out_dir / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads((result.out_dir / "concept_standardization.json").read_text(encoding="utf-8"))
    review_queue = json.loads((result.out_dir / "review_queue.json").read_text(encoding="utf-8"))
    concept_items = {item["candidate_id"]: item for item in review_queue["items"] if item["candidate_type"] == "concept"}

    assert manifest["concept_standardization"]["deterministic_merge_group_count"] == 1
    assert manifest["concept_standardization"]["ambiguous_alias_candidate_count"] == 1
    assert report["deterministic_merge_groups"][0]["canonical_concept_id"] == "concept::signal-processing"
    assert report["ambiguous_alias_candidates"][0]["left_concept_id"] == "concept::signal-processing"
    assert report["ambiguous_alias_candidates"][0]["right_concept_id"] == "concept::signal-processing-model"
    assert "concept_deterministic_merge" in concept_items["concept::signal-processing"]["finding_codes"]
    assert "concept_alias_candidate" in concept_items["concept::signal-processing"]["finding_codes"]
    assert "concept_alias_candidate" in concept_items["concept::signal-processing-model"]["finding_codes"]


def test_import_can_align_claims_to_existing_seed_concepts(tmp_path: Path) -> None:
    seed_store = GroundRecallStore(tmp_path / "seed-store")
    seed_store.save_concept(
        ConceptRecord(
            concept_id="concept::evo-edu-notebook-allele-frequency-scaffold-pilot",
            title="Evo Edu Notebook Allele Frequency Scaffold Pilot",
            description="Reviewed Notebook scaffold pilot.",
            current_status="reviewed",
        )
    )

    root = tmp_path / "notes"
    root.mkdir()
    (root / "incoming.md").write_text(
        "# Incoming Note\n\n"
        "- The Notebook allele frequency scaffold pilot should guide future source-slot work.\n",
        encoding="utf-8",
    )

    result = run_groundrecall_import(
        root,
        mode="quick",
        import_id="alignment-test",
        concept_seed_store=seed_store.base_dir,
    )
    manifest = json.loads((result.out_dir / "manifest.json").read_text(encoding="utf-8"))
    claims = _read_jsonl(result.out_dir / "claims.jsonl")
    aligned_claim = next(item for item in claims if "source-slot work" in item["claim_text"])

    assert manifest["concept_alignment"]["aligned_claim_count"] == 1
    assert manifest["external_concept_ids"] == ["concept::evo-edu-notebook-allele-frequency-scaffold-pilot"]
    assert "concept::evo-edu-notebook-allele-frequency-scaffold-pilot" in aligned_claim["concept_ids"]
    assert aligned_claim["metadata"]["concept_seed_alignments"][0]["concept_id"] == (
        "concept::evo-edu-notebook-allele-frequency-scaffold-pilot"
    )

    lint_payload = json.loads((result.out_dir / "lint_findings.json").read_text(encoding="utf-8"))
    missing_concept_errors = [
        item for item in lint_payload["findings"] if item["code"] in {"claim_concept_missing", "relation_missing_target"}
    ]
    assert missing_concept_errors == []


def test_graph_diagnostics_detect_bridge_concepts() -> None:
    diagnostics = build_graph_diagnostics(
        concepts=[
            {"concept_id": "concept::a"},
            {"concept_id": "concept::b"},
            {"concept_id": "concept::c"},
            {"concept_id": "concept::d"},
        ],
        relations=[
            {"source_id": "concept::a", "target_id": "concept::b"},
            {"source_id": "concept::b", "target_id": "concept::c"},
            {"source_id": "concept::c", "target_id": "concept::d"},
        ],
    )

    assert diagnostics["summary"]["connected_component_count"] == 1
    assert diagnostics["summary"]["bridge_concept_count"] == 2
    assert [item["concept_id"] for item in diagnostics["bridge_concepts"]] == ["concept::b", "concept::c"]


def test_review_queue_uses_graph_diagnostics_for_concept_triage(tmp_path: Path) -> None:
    root = tmp_path / "llmwiki"
    (root / "wiki").mkdir(parents=True)
    (root / "wiki" / "a.md").write_text("# A\n\nSee also [[B]].\n", encoding="utf-8")
    (root / "wiki" / "b.md").write_text("# B\n\nSee also [[C]].\n", encoding="utf-8")
    (root / "wiki" / "c.md").write_text("# C\n", encoding="utf-8")
    (root / "wiki" / "isolated.md").write_text("# Isolated\n", encoding="utf-8")

    result = run_groundrecall_import(root, mode="quick", import_id="graph-queue-test")
    review_queue = json.loads((result.out_dir / "review_queue.json").read_text(encoding="utf-8"))
    concept_items = {item["candidate_id"]: item for item in review_queue["items"] if item["candidate_type"] == "concept"}

    assert concept_items["concept::b"]["triage_lane"] == "conflict_resolution"
    assert "bridge_concept" in concept_items["concept::b"]["graph_codes"]
    assert concept_items["concept::isolated"]["triage_lane"] == "conflict_resolution"
    assert "isolated_concept" in concept_items["concept::isolated"]["graph_codes"]
    assert concept_items["concept::b"]["priority"] < concept_items["concept::isolated"]["priority"]


def test_groundrecall_import_parses_explicit_claim_relations(tmp_path: Path) -> None:
    root = tmp_path / "llmwiki"
    (root / "wiki").mkdir(parents=True)
    (root / "wiki" / "notes.md").write_text(
        "# Notes\n\n"
        "- [claim_id: base] Channel capacity bounds reliable communication rate.\n"
        "- [claim_id: revised] [supersedes: base] Channel capacity bounds reliable communication rate for a specified channel model.\n"
        "- [claim_id: dissent] [contradicts: revised] Channel capacity has no stable interpretation.\n",
        encoding="utf-8",
    )

    result = run_groundrecall_import(root, mode="quick", import_id="relations-test")
    claims = _read_jsonl(result.out_dir / "claims.jsonl")
    by_id = {item["claim_id"]: item for item in claims}

    assert "clm_base" in by_id
    assert by_id["clm_revised"]["supersedes_claim_ids"] == ["clm_base"]
    assert by_id["clm_dissent"]["contradicts_claim_ids"] == ["clm_revised"]

    lint_payload = json.loads((result.out_dir / "lint_findings.json").read_text(encoding="utf-8"))
    codes = {item["code"] for item in lint_payload["findings"]}
    assert "unresolved_supersession_ref" not in codes
    assert "unresolved_contradiction_ref" not in codes


def test_groundrecall_lint_flags_orphan_concepts_and_missing_targets(tmp_path: Path) -> None:
    root = tmp_path / "llmwiki"
    (root / "wiki").mkdir(parents=True)
    (root / "wiki" / "solo.md").write_text(
        "# Solo Concept\n",
        encoding="utf-8",
    )
    (root / "wiki" / "broken.md").write_text(
        "# Broken\n\nSee also [[Missing Concept]].\n",
        encoding="utf-8",
    )

    result = run_groundrecall_import(root, mode="quick", import_id="lint-test")
    lint_payload = json.loads((result.out_dir / "lint_findings.json").read_text(encoding="utf-8"))
    codes = {item["code"] for item in lint_payload["findings"]}
    assert "orphan_concept" in codes


def test_groundrecall_lint_detects_relation_missing_target(tmp_path: Path) -> None:
    import_dir = tmp_path / "imports" / "broken-import"
    import_dir.mkdir(parents=True)
    (import_dir / "manifest.json").write_text(
        json.dumps({"import_id": "broken-import", "import_mode": "quick"}),
        encoding="utf-8",
    )
    (import_dir / "artifacts.jsonl").write_text("", encoding="utf-8")
    (import_dir / "observations.jsonl").write_text("", encoding="utf-8")
    (import_dir / "claims.jsonl").write_text("", encoding="utf-8")
    (import_dir / "concepts.jsonl").write_text(
        json.dumps(
            {
                "concept_id": "concept::existing",
                "title": "Existing",
                "current_status": "triaged",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (import_dir / "relations.jsonl").write_text(
        json.dumps(
            {
                "relation_id": "rel_1",
                "source_id": "concept::existing",
                "target_id": "concept::missing",
                "relation_type": "references",
                "current_status": "draft",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    payload = lint_import_directory(import_dir)
    codes = {item["code"] for item in payload["findings"]}
    assert "relation_missing_target" in codes
