from __future__ import annotations

import json
from pathlib import Path

from groundrecall.groundrecall_normalizer import standardize_concept_rows
from groundrecall.ingest import run_groundrecall_import
from groundrecall.lint import lint_import_directory


def _read_jsonl(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    return [json.loads(line) for line in text.splitlines()]


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

    concepts = _read_jsonl(result.out_dir / "concepts.jsonl")
    concept_ids = {item["concept_id"] for item in concepts}
    assert "concept::channel-capacity" in concept_ids
    assert "concept::shannon-entropy" in concept_ids

    relations = _read_jsonl(result.out_dir / "relations.jsonl")
    assert any(item["target_id"] == "concept::shannon-entropy" for item in relations)

    lint_payload = json.loads((result.out_dir / "lint_findings.json").read_text(encoding="utf-8"))
    assert "summary" in lint_payload
    assert lint_payload["summary"]["warning_count"] >= 0

    review_queue = json.loads((result.out_dir / "review_queue.json").read_text(encoding="utf-8"))
    assert review_queue["queue_length"] >= 1
    assert any(item["candidate_type"] == "claim" for item in review_queue["items"])
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
    assert "citations" in review_data
    assert "citation_reviews" in review_data


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
