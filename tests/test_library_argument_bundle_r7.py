import copy
import json
import shutil
import subprocess
from pathlib import Path

from groundrecall.library_argument_bundle_r7 import evaluate_library_argument_bundle


FIXTURE = Path(__file__).parents[1] / "docs/fixtures/library.argument_bundle.v1.golden.json"
R5_FIXTURE = Path(__file__).parent / "fixtures/library_argument_bundle_r7_r5_packet.json"


def test_r7_is_deterministic_read_only_and_reports_the_complete_chain() -> None:
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    original = copy.deepcopy(bundle)
    first = evaluate_library_argument_bundle(bundle)
    second = evaluate_library_argument_bundle(bundle)

    assert first == second
    assert bundle == original
    assert [item["phase"] for item in first["phase_status"]] == [
        "R0-contract", "R1-handoff", "R2-adapter-coverage", "R3-audit",
        "R4-lineage", "R5-evidence", "R6-preflight",
    ]
    assert first["ready"] is False
    assert first["artifact_summary"]["r4"]["lineage_candidates"]["count"] == 1
    assert first["artifact_summary"]["r5"]["evidence_cards"]["count"] == 2
    assert first["release_blockers"]
    assert first["coverage"]["automated"]
    assert first["coverage"]["corpus_specific_work_required"]
    assert "database write" in first["boundary"]


def test_r7_accepts_a_supplied_r5_packet_without_mutating_it() -> None:
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    packet = json.loads(R5_FIXTURE.read_text(encoding="utf-8"))
    original = copy.deepcopy(packet)
    report = evaluate_library_argument_bundle(bundle, r5=packet, target="downstream")

    assert packet == original
    assert report["target"] == "downstream"
    assert report["artifact_summary"]["r6"]["manifest_id"].startswith("knowledge-basis.")


def test_r7_cli_registration_emits_report_without_strict_failure(tmp_path: Path) -> None:
    output = tmp_path / "r7.json"
    result = subprocess.run(
        [shutil.which("groundrecall") or "groundrecall", "argument-bundle-r7", str(FIXTURE), str(output)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["schema_version"].endswith("r7.e2e-readiness.v1")
    assert report["release_allowed"] is False
