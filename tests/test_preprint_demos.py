from __future__ import annotations

import json
import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "examples" / "preprint" / "run_preprint_demos.py"
spec = importlib.util.spec_from_file_location("run_preprint_demos", MODULE_PATH)
assert spec is not None
preprint_demos = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(preprint_demos)


def test_preprint_demo_runner_emits_institutional_federation_outputs(tmp_path: Path) -> None:
    manifest = preprint_demos.run(tmp_path / "out")
    expected = {
        "prior_work_discovery.json",
        "signed_catalog_discovery.json",
        "incremental_subscription.json",
        "multi_party_review_feedback.json",
        "custody_planning.json",
        "release_pack_withdrawal.json",
        "policy_gated_institutional_writes.json",
    }

    assert manifest["demo_count"] == 15
    assert expected.issubset(set(manifest["outputs"]))
    assert all(result == "pass" for result in manifest["results"].values())


def test_preprint_demo_outputs_capture_key_prr02_claims(tmp_path: Path) -> None:
    out = tmp_path / "out"
    preprint_demos.run(out)

    prior_work = json.loads((out / "prior_work_discovery.json").read_text(encoding="utf-8"))
    catalog = json.loads((out / "signed_catalog_discovery.json").read_text(encoding="utf-8"))
    subscription = json.loads((out / "incremental_subscription.json").read_text(encoding="utf-8"))
    review = json.loads((out / "multi_party_review_feedback.json").read_text(encoding="utf-8"))
    custody = json.loads((out / "custody_planning.json").read_text(encoding="utf-8"))
    release = json.loads((out / "release_pack_withdrawal.json").read_text(encoding="utf-8"))
    writes = json.loads((out / "policy_gated_institutional_writes.json").read_text(encoding="utf-8"))

    assert prior_work["negative_or_inconclusive_result_found"] is True
    assert catalog["internal_scope_hidden_by_receiver_cap"] is True
    assert subscription["replay_detected"] is True
    assert review["dissent_receipt_ids"] == ["review-dissent"]
    assert custody["departure_dry_run"] is True
    assert release["withdrawal_distinct_from_erasure"] is True
    assert writes["blocked_work_write_left_no_record"] is True
    assert writes["blocked_custody_event_left_no_record"] is True
