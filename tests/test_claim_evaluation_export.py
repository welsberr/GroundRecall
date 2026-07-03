from __future__ import annotations

import json
from pathlib import Path

from groundrecall.claim_evaluation_export import export_claim_evaluation_file, load_json_or_jsonl


def test_load_json_or_jsonl_accepts_list_and_wrapped_rows(tmp_path: Path) -> None:
    rows_path = tmp_path / "rows.json"
    wrapped_path = tmp_path / "wrapped.json"
    jsonl_path = tmp_path / "rows.jsonl"
    rows_path.write_text(json.dumps([{"claim_id": "clm_001"}]), encoding="utf-8")
    wrapped_path.write_text(json.dumps({"evaluations": [{"claim_id": "clm_002"}]}), encoding="utf-8")
    jsonl_path.write_text('{"claim_id": "clm_003"}\n', encoding="utf-8")

    assert load_json_or_jsonl(rows_path)[0]["claim_id"] == "clm_001"
    assert load_json_or_jsonl(wrapped_path)[0]["claim_id"] == "clm_002"
    assert load_json_or_jsonl(jsonl_path)[0]["claim_id"] == "clm_003"


def test_export_claim_evaluation_file_writes_g_package(tmp_path: Path) -> None:
    evaluations_path = tmp_path / "evaluations.json"
    claims_path = tmp_path / "claims.jsonl"
    out_dir = tmp_path / "out"
    evaluations_path.write_text(
        json.dumps(
            {
                "evaluations": [
                    {"claim_id": "clm_001", "y": 1, "p": 0.9, "env": "C", "condition": "plain"},
                    {"claim_id": "clm_001", "y": 1, "p": 0.8, "env": "K", "condition": "plain"},
                ]
            }
        ),
        encoding="utf-8",
    )
    claims_path.write_text(
        json.dumps(
            {
                "claim_id": "clm_001",
                "claim_text": "Channel capacity bounds reliable communication rate.",
                "concept_ids": ["concept::channel-capacity"],
                "provenance": {"origin_path": "wiki/channel-capacity.md", "grounding_status": "grounded"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    output = export_claim_evaluation_file(
        evaluations_path,
        out_dir,
        claims_path=claims_path,
        experiment_id="groundrecall-temporal-check",
        corpus="channel-capacity",
    )

    assert output["row_count"] == 2
    assert (out_dir / "groundrecall_g_rows.csv").exists()
    assert (out_dir / "groundrecall_g_manifest.json").exists()
    assert (out_dir / "groundrecall_g_summary.json").exists()
    manifest = json.loads((out_dir / "groundrecall_g_manifest.json").read_text(encoding="utf-8"))
    assert manifest["experiment_id"] == "groundrecall-temporal-check"
    assert manifest["corpus"] == "channel-capacity"
