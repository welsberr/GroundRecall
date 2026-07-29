from __future__ import annotations

import json
from pathlib import Path

from groundrecall.models import ClaimRecord, DecisionRecord, WorkRecord
from groundrecall.prior_work import PRIOR_WORK_SCHEMA_VERSION, prior_work_search
from groundrecall.store import GroundRecallStore


def _seed_store(root: Path) -> GroundRecallStore:
    store = GroundRecallStore(root)
    store.save_work(
        WorkRecord(
            work_id="work-public-failure",
            work_kind="experiment",
            title="Graph backfill failed",
            summary="The approach was inconclusive and should not be repeated without new evidence.",
            outcome="inconclusive",
            release_level="public",
            current_status="reviewed",
        )
    )
    store.save_work(
        WorkRecord(
            work_id="work-private-failure",
            work_kind="experiment",
            title="Graph backfill failed privately",
            summary="Confidential test details.",
            outcome="failed",
            release_level="confidential",
            current_status="reviewed",
        )
    )
    store.save_decision(
        DecisionRecord(
            decision_id="decision-public",
            question="Which graph approach?",
            outcome="Use bounded review",
            rationale="The earlier approach lacked evidence.",
            release_level="public",
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim-public",
            claim_text="Prior graph work requires review before reuse.",
            metadata={"release_level": "public"},
            current_status="reviewed",
        )
    )
    return store


def test_prior_work_search_surfaces_negative_results_and_hides_inaccessible_records(tmp_path: Path) -> None:
    _seed_store(tmp_path / "store")
    report = prior_work_search(tmp_path / "store", "graph backfill failed", maximum_release_level="public")
    assert report.schema_version == PRIOR_WORK_SCHEMA_VERSION
    assert report.candidate_count >= 1
    assert report.candidates[0].candidate_id == "work-public-failure"
    assert report.candidates[0].outcome == "inconclusive"
    assert report.candidates[0].review_required is True
    assert report.inaccessible_count == 1
    assert report.inaccessible_by_release_level == {"confidential": 1}
    assert all(item.candidate_id != "work-private-failure" for item in report.candidates)


def test_prior_work_search_includes_exact_identity_and_decisions(tmp_path: Path) -> None:
    store = _seed_store(tmp_path / "store")
    report = prior_work_search(store.base_dir, "decision-public", maximum_release_level="public")
    assert report.candidates[0].match_kind == "exact_identity"
    assert report.candidates[0].candidate_kind == "decision"


def test_prior_work_search_can_be_policy_blocked_without_store_access(tmp_path: Path) -> None:
    _seed_store(tmp_path / "store")
    policy = tmp_path / "policy.yaml"
    policy.write_text(
        "\n".join(
            [
                "schema_version: groundrecall.policy_plugins.v1",
                "providers:",
                "  - type: static",
                "    policy_id: prior-work-deny",
                "    default_decision: hard_gate",
            ]
        ),
        encoding="utf-8",
    )
    report = prior_work_search(
        tmp_path / "store",
        "graph",
        policy_plugins_path=policy,
        requester_id="alice",
    )
    assert report.candidates == []
    assert report.examined_count == 0
    assert report.policy_decision["decision"] == "hard_gate"


def test_prior_work_report_is_json_serializable(tmp_path: Path) -> None:
    report = prior_work_search(tmp_path / "store", "graph")
    payload = json.loads(report.model_dump_json())
    assert payload["schema_version"] == PRIOR_WORK_SCHEMA_VERSION
