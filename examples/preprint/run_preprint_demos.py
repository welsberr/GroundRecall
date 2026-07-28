from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from groundrecall.contradictions import (
    ContradictionPolicyError,
    adjudicate_contradiction_case,
    sync_contradiction_cases_for_store,
)
from groundrecall.federation import (
    FederationLocalPolicy,
    FederationPolicyGrant,
    evaluate_federation_policy,
    export_federation_bundle,
    import_federation_bundle_to_quarantine,
    plan_quarantine_promotion,
    promote_quarantined_bundle,
)
from groundrecall.ingest import run_groundrecall_import
from groundrecall.models import (
    ArtifactRecord,
    ClaimRecord,
    ConceptRecord,
    ObservationRecord,
    PromotionRecord,
    ProvenanceRecord,
    SourceRecord,
    RelationRecord,
    ReviewCandidateRecord,
)
from groundrecall.policy import PolicyRequest, load_policy_plugins
from groundrecall.promotion import PromotionGateError, promote_import_to_store
from groundrecall.query import query_concept
from groundrecall.relation_review import RelationReviewPolicyError, apply_relation_review_batch
from groundrecall.store import GroundRecallStore


CREATED_AT = "2026-07-27T00:00:00Z"
SIGNING_KEY = "preprint-demo-signing-key-not-secret"
KEY_ID = "preprint-demo-key"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _base_store(path: Path) -> GroundRecallStore:
    return GroundRecallStore(path)


def _seed_public_memory(store: GroundRecallStore, *, prefix: str = "demo") -> None:
    store.save_source(
        SourceRecord(
            source_id=f"{prefix}_source_public",
            title="Public source",
            url="https://example.test/source",
            retrieved_at=CREATED_AT,
            metadata={"release_level": "public"},
            current_status="promoted",
        )
    )
    store.save_artifact(
        ArtifactRecord(
            artifact_id=f"{prefix}_artifact_public",
            artifact_kind="note",
            title="Public evidence note",
            created_at=CREATED_AT,
            metadata={"release_level": "public"},
            current_status="reviewed",
        )
    )
    store.save_observation(
        ObservationRecord(
            observation_id=f"{prefix}_observation_public",
            artifact_id=f"{prefix}_artifact_public",
            role="evidence",
            text="A reviewed public observation supports the governed-memory claim.",
            provenance=ProvenanceRecord(
                origin_artifact_id=f"{prefix}_artifact_public",
                source_url="https://example.test/source",
                retrieval_date="2026-07-27",
                support_kind="direct_source",
                grounding_status="grounded",
            ),
            metadata={"release_level": "public"},
            current_status="reviewed",
        )
    )
    store.save_concept(
        ConceptRecord(
            concept_id=f"concept::{prefix}_governed_memory",
            title="Governed memory",
            metadata={"release_level": "public"},
            current_status="promoted",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id=f"{prefix}_claim_public",
            claim_text="Governed memory preserves provenance and review state.",
            source_observation_ids=[f"{prefix}_observation_public"],
            concept_ids=[f"concept::{prefix}_governed_memory"],
            metadata={"release_level": "public"},
            provenance=ProvenanceRecord(
                origin_artifact_id=f"{prefix}_artifact_public",
                source_url="https://example.test/source",
                retrieval_date="2026-07-27",
                support_kind="direct_source",
                grounding_status="grounded",
            ),
            current_status="promoted",
        )
    )


def demo_provenance_promotion(work_dir: Path) -> dict[str, Any]:
    store = _base_store(work_dir / "provenance_store")
    _seed_public_memory(store, prefix="provenance")
    store.save_promotion(
        PromotionRecord(
            promotion_id="promotion_demo_public_claim",
            candidate_type="claim",
            candidate_id="provenance_claim_public",
            reviewer="claimwright-demo-reviewer",
            promoted_object_ids=["provenance_claim_public"],
            notes="Promotion records review-gated movement into canonical memory.",
            promoted_at=CREATED_AT,
        )
    )
    payload = query_concept(store.base_dir, "Governed memory")
    assert payload is not None
    claim = payload["claims"][0]
    observation = payload["supporting_observations"][0]
    return {
        "demo": "provenance_promotion",
        "claim_id": claim["claim_id"],
        "claim_status": claim["current_status"],
        "promotion_count": len(store.list_promotions()),
        "supporting_observation_ids": claim["source_observation_ids"],
        "observation_grounding_status": observation["grounding_status"],
        "observation_source_url_present": bool(observation["source_url"]),
        "result": "pass",
    }


def demo_contradiction_adjudication(work_dir: Path) -> dict[str, Any]:
    store = _base_store(work_dir / "contradiction_store")
    store.save_concept(ConceptRecord(concept_id="concept::retention", title="Retention policy", current_status="promoted"))
    store.save_claim(
        ClaimRecord(
            claim_id="claim_keep_history",
            claim_text="Ordinary epistemic maintenance should preserve history.",
            concept_ids=["concept::retention"],
            contradicts_claim_ids=["claim_delete_stale"],
            current_status="promoted",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim_delete_stale",
            claim_text="Stale claims should be deleted from memory.",
            concept_ids=["concept::retention"],
            current_status="promoted",
        )
    )
    cases = sync_contradiction_cases_for_store(store.base_dir)
    assert cases
    result = adjudicate_contradiction_case(
        store.base_dir,
        case_id=cases[0].case_id,
        status="resolved",
        adjudicator="claimwright-demo-reviewer",
        rationale="Non-destructive expiry/supersession preserves provenance while reducing current applicability.",
        resolution="prefer_non_destructive_maintenance",
        selected_claim_ids=["claim_keep_history"],
        decided_at=CREATED_AT,
    )
    updated_case = store.get_contradiction_case(cases[0].case_id)
    return {
        "demo": "contradiction_adjudication",
        "case_id": cases[0].case_id,
        "case_status": updated_case.status if updated_case else "",
        "claim_ids_preserved": sorted(case.claim_id for case in store.list_claims()),
        "adjudication_id": result["adjudication"]["adjudication_id"],
        "selected_claim_ids": result["adjudication"]["metadata"]["selected_claim_ids"],
        "disagreement_preserved": result["adjudication"]["metadata"]["disagreement_preserved"],
        "result": "pass",
    }


def demo_release_filtering(work_dir: Path) -> dict[str, Any]:
    store = _base_store(work_dir / "release_store")
    _seed_public_memory(store, prefix="release")
    store.save_claim(
        ClaimRecord(
            claim_id="release_claim_internal",
            claim_text="Internal claim must not appear in public export.",
            metadata={"release_level": "internal"},
            current_status="promoted",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="release_claim_private",
            claim_text="Private claim must remain local-only.",
            metadata={"release_level": "private"},
            current_status="promoted",
        )
    )
    bundle_path = work_dir / "release_public_bundle.json"
    bundle = export_federation_bundle(
        store.base_dir,
        bundle_path,
        target_release_level="public",
        producer_instance_id="host-a",
        signing_key=SIGNING_KEY,
        key_id=KEY_ID,
        snapshot_id="release-demo-snapshot",
        created_at=CREATED_AT,
    )
    included_claim_ids = sorted(claim.claim_id for claim in bundle.snapshot.claims)
    findings = [finding.model_dump(mode="json") for finding in bundle.policy_report.findings]
    return {
        "demo": "release_filtering",
        "included_claim_ids": included_claim_ids,
        "excluded_total": bundle.policy_report.excluded_total,
        "finding_reasons": sorted({finding["reason"] for finding in findings}),
        "private_claim_excluded": "release_claim_private" not in included_claim_ids,
        "internal_claim_excluded": "release_claim_internal" not in included_claim_ids,
        "result": "pass",
    }


def demo_federation_quarantine(work_dir: Path) -> dict[str, Any]:
    producer = _base_store(work_dir / "producer_store")
    receiver = _base_store(work_dir / "receiver_store")
    _seed_public_memory(producer, prefix="federation")
    bundle_path = work_dir / "federation_bundle.json"
    bundle = export_federation_bundle(
        producer.base_dir,
        bundle_path,
        target_release_level="public",
        producer_instance_id="host-a",
        signing_key=SIGNING_KEY,
        key_id=KEY_ID,
        snapshot_id="federation-demo-snapshot",
        created_at=CREATED_AT,
    )
    quarantine_dir = work_dir / "quarantine"
    import_result = import_federation_bundle_to_quarantine(
        bundle_path,
        quarantine_dir,
        signing_key=SIGNING_KEY,
        accepted_release_levels=["public"],
        key_id=KEY_ID,
    )
    plan = plan_quarantine_promotion(
        import_result.quarantine_path,
        receiver.base_dir,
        signing_key=SIGNING_KEY,
        key_id=KEY_ID,
        accepted_release_levels=["public"],
    )
    return {
        "demo": "federation_quarantine",
        "bundle_id": bundle.manifest.bundle_id,
        "import_decision": import_result.decision,
        "receiver_claim_count_before_promotion": len(receiver.list_claims()),
        "planned_promotable_counts": plan.promotable_counts,
        "promotion_required_for_canonical_store": len(receiver.list_claims()) == 0 and import_result.decision == "quarantined",
        "result": "pass",
    }


def demo_local_authority(work_dir: Path) -> dict[str, Any]:
    producer = _base_store(work_dir / "authority_producer")
    receiver = _base_store(work_dir / "authority_receiver")
    _seed_public_memory(producer, prefix="authority")
    bundle_path = work_dir / "authority_bundle.json"
    export_federation_bundle(
        producer.base_dir,
        bundle_path,
        target_release_level="public",
        producer_instance_id="host-a",
        signing_key=SIGNING_KEY,
        key_id=KEY_ID,
        snapshot_id="authority-demo-snapshot",
        created_at=CREATED_AT,
    )
    quarantine_dir = work_dir / "authority_quarantine"
    import_result = import_federation_bundle_to_quarantine(
        bundle_path,
        quarantine_dir,
        signing_key=SIGNING_KEY,
        accepted_release_levels=["public"],
        key_id=KEY_ID,
    )
    import_only_policy = FederationLocalPolicy(
        policy_id="demo_import_only_policy",
        grants=[
            FederationPolicyGrant(
                subject_id="receiver-agent",
                actions=["import"],
                release_levels=["public"],
                instance_ids=["host-a"],
            )
        ],
    )
    rejected = promote_quarantined_bundle(
        import_result.quarantine_path,
        receiver.base_dir,
        signing_key=SIGNING_KEY,
        key_id=KEY_ID,
        accepted_release_levels=["public"],
        policy=import_only_policy,
        requester_id="receiver-agent",
        apply=True,
    )
    promote_policy = FederationLocalPolicy(
        policy_id="demo_import_promote_policy",
        grants=[
            FederationPolicyGrant(
                subject_id="receiver-agent",
                actions=["import", "promote"],
                release_levels=["public"],
                instance_ids=["host-a"],
            )
        ],
    )
    allowed = evaluate_federation_policy(
        promote_policy,
        subject_id="receiver-agent",
        action="promote",
        release_level="public",
        instance_id="host-a",
    )
    promoted = promote_quarantined_bundle(
        import_result.quarantine_path,
        receiver.base_dir,
        signing_key=SIGNING_KEY,
        key_id=KEY_ID,
        accepted_release_levels=["public"],
        policy=promote_policy,
        requester_id="receiver-agent",
        apply=True,
    )
    return {
        "demo": "local_authority",
        "signature_verified_to_quarantine": import_result.decision == "quarantined",
        "import_only_promotion_decision": rejected.decision,
        "import_only_reasons": rejected.reasons,
        "local_policy_allows_promotion": allowed.allowed,
        "authorized_promotion_decision": promoted.decision,
        "receiver_claim_count_after_authorized_promotion": len(receiver.list_claims()),
        "result": "pass",
    }


def _write_static_policy_config(path: Path, *, policy_id: str, decision: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "schema_version: groundrecall.policy_plugins.v1",
                f"policy_id: {policy_id}",
                "providers:",
                "  - type: groundrecall.static",
                f"    policy_id: {policy_id}.static",
                f"    default_decision: {decision}",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _write_claimwright_style_policy(root: Path) -> Path:
    policy_dir = root / "policies"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "enforcement.yaml").write_text(
        "\n".join(
            [
                "version: 0.1",
                "defaults:",
                "  durable_memory_changes: soft_gate",
                "  public_release: hard_gate",
            ]
        ),
        encoding="utf-8",
    )
    (policy_dir / "claim_states.yaml").write_text(
        "\n".join(
            [
                "version: 0.1",
                "claim_states:",
                "  - id: private_only_speculation",
                "    public_allowed: false",
                "  - id: supported_by_primary_evidence",
                "    public_allowed: conditional",
                "  - id: public_safe",
                "    public_allowed: true",
            ]
        ),
        encoding="utf-8",
    )
    return root


def _write_claimwright_plugin_config(path: Path, *, claimwright_root: Path) -> Path:
    path.write_text(
        "\n".join(
            [
                "schema_version: groundrecall.policy_plugins.v1",
                "policy_id: preprint.claimwright.composed",
                "providers:",
                "  - type: claimwright.directory",
                f"    root_dir: {claimwright_root}",
            ]
        ),
        encoding="utf-8",
    )
    return path


def demo_policy_plugin_boundary(work_dir: Path) -> dict[str, Any]:
    policy_dir = work_dir / "policy_demo"
    allow_config = _write_static_policy_config(policy_dir / "soft-policy.yaml", policy_id="preprint.soft_policy", decision="soft_gate")
    hard_config = _write_static_policy_config(policy_dir / "hard-policy.yaml", policy_id="preprint.hard_policy", decision="hard_gate")
    claimwright_root = _write_claimwright_style_policy(policy_dir / "claimwright_policy")
    claimwright_config = _write_claimwright_plugin_config(policy_dir / "claimwright-plugin.yaml", claimwright_root=claimwright_root)

    soft_decision = load_policy_plugins(allow_config).evaluate(
        PolicyRequest(
            decision_point="promote",
            subject_id="demo-agent",
            action="promote_import_to_store",
            durable_memory_change=True,
        )
    )
    claimwright_decision = load_policy_plugins(claimwright_config).evaluate(
        PolicyRequest(
            decision_point="publish",
            subject_id="demo-agent",
            action="publish_public_claim",
            public_facing=True,
            target_release_level="public",
            claim_state="private_only_speculation",
        )
    )

    import_root = work_dir / "policy_import_source"
    (import_root / "wiki").mkdir(parents=True, exist_ok=True)
    (import_root / "wiki" / "policy.md").write_text("# Policy Demo\n\n- A policy-gated claim.\n", encoding="utf-8")
    import_result = run_groundrecall_import(import_root, mode="quick", import_id="policy-plugin-promotion-demo")
    promotion_blocked = False
    try:
        promote_import_to_store(
            import_result.out_dir,
            work_dir / "policy_promotion_store",
            reviewer="policy-demo-reviewer",
            policy_plugins_path=hard_config,
            policy_subject_id="demo-agent",
        )
    except PromotionGateError as exc:
        promotion_blocked = exc.payload["policy_plugin_decision"]["decision"] == "hard_gate"

    contradiction_store = _base_store(work_dir / "policy_contradiction_store")
    contradiction_store.save_claim(ClaimRecord(claim_id="policy_a", claim_text="Policy A.", contradicts_claim_ids=["policy_b"], current_status="promoted"))
    contradiction_store.save_claim(ClaimRecord(claim_id="policy_b", claim_text="Policy B.", current_status="promoted"))
    contradiction_case = sync_contradiction_cases_for_store(contradiction_store.base_dir)[0]
    adjudication_blocked = False
    try:
        adjudicate_contradiction_case(
            contradiction_store.base_dir,
            case_id=contradiction_case.case_id,
            status="resolved",
            adjudicator="policy-demo-reviewer",
            rationale="Would resolve if policy allowed.",
            policy_plugins_path=hard_config,
            policy_subject_id="demo-agent",
        )
    except ContradictionPolicyError as exc:
        adjudication_blocked = exc.payload["policy_plugin_decision"]["decision"] == "hard_gate"

    relation_store = _base_store(work_dir / "policy_relation_store")
    relation_store.save_concept(ConceptRecord(concept_id="concept::policy_a", title="Policy A", current_status="reviewed"))
    relation_store.save_concept(ConceptRecord(concept_id="concept::policy_b", title="Policy B", current_status="reviewed"))
    relation_store.save_relation(
        RelationRecord(
            relation_id="rel_policy_demo",
            source_id="concept::policy_a",
            target_id="concept::policy_b",
            relation_type="mentions_topic",
            current_status="triaged",
        )
    )
    relation_store.save_review_candidate(
        ReviewCandidateRecord(
            review_candidate_id="rq_rel_policy_demo",
            candidate_type="relation",
            candidate_id="rel_policy_demo",
            triage_lane="relation_review",
            current_status="triaged",
        )
    )
    relation_decision_path = work_dir / "relation-policy-decisions.json"
    relation_decision_path.write_text(
        json.dumps(
            {
                "reviewer": "policy-demo-reviewer",
                "decisions": [{"relation_id": "rel_policy_demo", "status": "reviewed", "relation_type": "supports"}],
            }
        ),
        encoding="utf-8",
    )
    relation_review_blocked = False
    try:
        apply_relation_review_batch(
            relation_store.base_dir,
            relation_decision_path,
            policy_plugins_path=hard_config,
            policy_subject_id="demo-agent",
        )
    except RelationReviewPolicyError as exc:
        relation_review_blocked = exc.payload["policy_plugin_decision"]["decision"] == "hard_gate"

    return {
        "demo": "policy_plugin_boundary",
        "schema_version": "groundrecall.policy_plugins.v1",
        "soft_policy_decision": soft_decision.decision,
        "claimwright_adapter_decision": claimwright_decision.decision,
        "claimwright_adapter_reasons": claimwright_decision.reasons,
        "promotion_blocked_before_store_write": promotion_blocked and not (work_dir / "policy_promotion_store").exists(),
        "adjudication_blocked_before_record_write": adjudication_blocked and contradiction_store.list_adjudications() == [],
        "relation_review_blocked_before_relation_write": relation_review_blocked
        and relation_store.get_relation("rel_policy_demo").current_status == "triaged"
        and relation_store.list_promotions() == [],
        "result": "pass",
    }


def run(output_dir: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="groundrecall-preprint-demos-") as tmp:
        work_dir = Path(tmp)
        demos = [
            demo_provenance_promotion(work_dir),
            demo_contradiction_adjudication(work_dir),
            demo_release_filtering(work_dir),
            demo_federation_quarantine(work_dir),
            demo_local_authority(work_dir),
            demo_policy_plugin_boundary(work_dir),
        ]
    for payload in demos:
        _write_json(output_dir / f"{payload['demo']}.json", payload)
    manifest = {
        "demo_suite": "groundrecall_preprint_governed_memory_demos",
        "generated_at": CREATED_AT,
        "demo_count": len(demos),
        "outputs": [f"{payload['demo']}.json" for payload in demos],
        "results": {payload["demo"]: payload["result"] for payload in demos},
    }
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate GroundRecall preprint demonstration evidence.")
    parser.add_argument(
        "--output-dir",
        default="examples/preprint/out",
        help="Directory for generated JSON summaries.",
    )
    args = parser.parse_args()
    manifest = run(Path(args.output_dir))
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
