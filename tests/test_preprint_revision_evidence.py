from __future__ import annotations

import json
import importlib.util
import subprocess
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "examples" / "preprint" / "generate_revision_evidence.py"
spec = importlib.util.spec_from_file_location("generate_revision_evidence", MODULE_PATH)
assert spec is not None
revision_evidence = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(revision_evidence)


def _init_repo(path: Path, message: str) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)
    (path / "README.md").write_text(message + "\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def test_build_revision_evidence_summarizes_current_reports_and_demos(tmp_path: Path) -> None:
    groundrecall = tmp_path / "GroundRecall"
    claimwright = tmp_path / "ClaimWright"
    _init_repo(groundrecall, "groundrecall fixture")
    _init_repo(claimwright, "claimwright fixture")
    demo_out = tmp_path / "out"
    demo_out.mkdir()
    (demo_out / "manifest.json").write_text(
        json.dumps({"demo_count": 1, "outputs": ["example.json"]}),
        encoding="utf-8",
    )
    (demo_out / "example.json").write_text("{}", encoding="utf-8")

    payload = revision_evidence.build_revision_evidence(
        groundrecall_root=groundrecall,
        claimwright_root=claimwright,
        demo_output_dir=demo_out,
    )

    assert payload["schema_version"] == revision_evidence.SCHEMA_VERSION
    assert payload["repositories"]["groundrecall"]["dirty"] is False
    assert payload["repositories"]["claimwright"]["head_subject"] == "claimwright fixture"
    assert payload["groundrecall_reports"]["policy_coverage"]["summary"]["route_count"] >= 1
    assert payload["groundrecall_reports"]["policy_coverage"]["summary"]["future_route_count"] == 1
    assert payload["groundrecall_reports"]["institutional_conformance"]["summary"]["scenario_count"] == 6
    assert payload["demo_outputs"]["manifest_demo_count"] == 1
    assert "production certification" in payload["claim_boundary"]


def test_write_revision_evidence_creates_json_file(tmp_path: Path) -> None:
    groundrecall = tmp_path / "GroundRecall"
    claimwright = tmp_path / "ClaimWright"
    _init_repo(groundrecall, "groundrecall fixture")
    _init_repo(claimwright, "claimwright fixture")
    demo_out = tmp_path / "out"
    demo_out.mkdir()
    output = tmp_path / "snapshot.json"

    payload = revision_evidence.write_revision_evidence(
        output,
        groundrecall_root=groundrecall,
        claimwright_root=claimwright,
        demo_output_dir=demo_out,
    )

    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8")) == payload


def test_revision_evidence_ignores_its_own_output_path_for_groundrecall_dirty_state(tmp_path: Path) -> None:
    groundrecall = tmp_path / "GroundRecall"
    claimwright = tmp_path / "ClaimWright"
    _init_repo(groundrecall, "groundrecall fixture")
    _init_repo(claimwright, "claimwright fixture")
    demo_out = groundrecall / "examples" / "preprint" / "out"
    demo_out.mkdir(parents=True)
    output = demo_out / "revision_evidence_snapshot.json"
    output.write_text("{}\n", encoding="utf-8")

    payload = revision_evidence.build_revision_evidence(
        groundrecall_root=groundrecall,
        claimwright_root=claimwright,
        demo_output_dir=demo_out,
    )

    assert payload["repositories"]["groundrecall"]["dirty"] is False
    assert payload["repositories"]["groundrecall"]["ignored_dirty_paths"] == [
        "examples/preprint/out/revision_evidence_snapshot.json"
    ]
