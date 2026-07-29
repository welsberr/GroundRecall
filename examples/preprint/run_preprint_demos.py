from __future__ import annotations

import argparse
import json
from statistics import median
import tempfile
from time import perf_counter_ns
from pathlib import Path
from typing import Any

from groundrecall.contradictions import (
    ContradictionPolicyError,
    accept_contradiction_candidate,
    adjudicate_contradiction_case,
    list_contradiction_candidate_batch,
    sync_contradiction_cases_for_store,
)
from groundrecall.catalog import build_federation_catalog, import_federation_catalog_to_quarantine, query_federation_catalog
from groundrecall.change_feed import (
    FederationSubscription,
    acknowledge_change_bundle,
    build_incremental_change_bundle,
    import_incremental_change_bundle_to_quarantine,
    save_subscription,
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
from groundrecall.institutional_custody import (
    CustodyPolicyError,
    orphan_stewardship_report,
    plan_instance_retirement,
    plan_tenancy_departure,
    record_custody_event,
)
from groundrecall.institutional_release import build_release_pack, build_withdrawal_notice, verify_release_pack, verify_withdrawal_notice
from groundrecall.institutional_review import (
    QuorumRule,
    build_feedback_bundle,
    evaluate_review_quorum,
    record_federation_feedback,
    record_review_receipt,
    unresolved_federation_disagreements,
    verify_feedback_bundle,
)
from groundrecall.institutional_write import InstitutionalWriteError, save_institutional_record, transition_contribution_with_policy
from groundrecall.ingest import run_groundrecall_import
from groundrecall.models import (
    ArtifactRecord,
    ClaimRecord,
    ContributionRecord,
    CustodyEventRecord,
    DecisionRecord,
    FederationFeedbackRecord,
    ConceptRecord,
    ObservationRecord,
    PromotionRecord,
    ProvenanceRecord,
    ReviewReceiptRecord,
    ScopeRecord,
    SourceRecord,
    RelationRecord,
    ReviewCandidateRecord,
    StewardshipRecord,
    WorkRecord,
)
from groundrecall.policy import PolicyRequest, StaticPolicyProvider, load_policy_plugins
from groundrecall.promotion import PromotionGateError, promote_import_to_store
from groundrecall.prior_work import prior_work_search
from groundrecall.query import query_concept
from groundrecall.query import build_graph_search_bundle, build_query_bundle_for_concept
from groundrecall.relation_review import RelationReviewPolicyError, apply_relation_review_batch
from groundrecall.search_index import build_search_index, search_index
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


def demo_contradiction_candidate_review(work_dir: Path) -> dict[str, Any]:
    store = _base_store(work_dir / "contradiction_candidate_store")
    store.save_concept(ConceptRecord(concept_id="concept::resilience", title="Resilience", current_status="promoted"))
    store.save_claim(
        ClaimRecord(
            claim_id="claim_resilience_history",
            claim_text="Resilient memory should preserve review history when claims are challenged.",
            concept_ids=["concept::resilience"],
            current_status="promoted",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim_resilience_rewrite",
            claim_text="Resilient memory should rewrite challenged claims in place.",
            concept_ids=["concept::resilience"],
            current_status="reviewed",
        )
    )
    store.save_relation(
        RelationRecord(
            relation_id="rel_candidate_resilience_conflict",
            source_id="claim_resilience_history",
            target_id="claim_resilience_rewrite",
            relation_type="claim_may_contradict_claim",
            current_status="triaged",
        )
    )
    candidate_batch = list_contradiction_candidate_batch(store.base_dir)
    audit_log = work_dir / "contradiction_candidate_audit.jsonl"
    accepted = accept_contradiction_candidate(
        store.base_dir,
        relation_id="rel_candidate_resilience_conflict",
        reviewer="claimwright-demo-reviewer",
        rationale="The two claims prescribe incompatible maintenance behavior in the same scope.",
        reviewed_at=CREATED_AT,
        audit_log_path=audit_log,
    )
    adjudicated = adjudicate_contradiction_case(
        store.base_dir,
        case_id=accepted["case"]["case_id"],
        status="resolved",
        adjudicator="claimwright-demo-reviewer",
        rationale="Preserve challenged claims and record review/adjudication state rather than rewriting in place.",
        resolution="prefer_non_destructive_review_history",
        selected_claim_ids=["claim_resilience_history"],
        decided_at=CREATED_AT,
    )
    query_bundle = build_query_bundle_for_concept(store.base_dir, "resilience")
    assert query_bundle is not None
    audit_events = [
        json.loads(line)
        for line in audit_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {
        "demo": "contradiction_candidate_review",
        "candidate_count_before_review": candidate_batch["candidate_count"],
        "candidate_relation_id": candidate_batch["candidates"][0]["relation_id"],
        "acceptance_decision": accepted["decision"],
        "case_id": accepted["case"]["case_id"],
        "case_status_after_adjudication": adjudicated["case"]["status"],
        "selected_claim_ids": adjudicated["adjudication"]["metadata"]["selected_claim_ids"],
        "claim_texts_preserved": {
            claim.claim_id: claim.claim_text
            for claim in store.list_claims()
        },
        "audit_event_count": len(audit_events),
        "audit_schema_version": audit_events[0]["schema_version"] if audit_events else "",
        "query_conflict_summary": query_bundle["conflict_summary"],
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


def demo_search_mode_timing(work_dir: Path) -> dict[str, Any]:
    store = _base_store(work_dir / "search_timing_store")
    topic_count = 24
    claims_per_topic = 3
    for index in range(topic_count):
        concept_id = f"concept::search_topic_{index:02d}"
        store.save_concept(
            ConceptRecord(
                concept_id=concept_id,
                title=f"Governed memory search topic {index:02d}",
                aliases=["governed memory", "policy search"] if index < 6 else [],
                description="Synthetic preprint benchmark concept for governed memory policy search.",
                current_status="promoted",
            )
        )
        if index > 0:
            store.save_relation(
                RelationRecord(
                    relation_id=f"rel_search_topic_{index - 1:02d}_{index:02d}",
                    source_id=f"concept::search_topic_{index - 1:02d}",
                    target_id=concept_id,
                    relation_type="supports",
                    current_status="reviewed",
                )
            )
        for claim_index in range(claims_per_topic):
            observation_id = f"obs_search_{index:02d}_{claim_index:02d}"
            store.save_observation(
                ObservationRecord(
                    observation_id=observation_id,
                    role="benchmark_evidence",
                    text=(
                        "Governed memory policy search preserves provenance, review state, "
                        f"and graph context for topic {index:02d} claim {claim_index:02d}."
                    ),
                    provenance=ProvenanceRecord(support_kind="direct_source", grounding_status="grounded"),
                    current_status="reviewed",
                )
            )
            store.save_claim(
                ClaimRecord(
                    claim_id=f"claim_search_{index:02d}_{claim_index:02d}",
                    claim_text=(
                        "Indexed search can find governed memory policy evidence while graph search "
                        f"adds neighborhood context for topic {index:02d}."
                    ),
                    source_observation_ids=[observation_id],
                    concept_ids=[concept_id],
                    current_status="promoted",
                )
            )

    index_payload = build_search_index(store.base_dir)
    query = "governed memory policy search"
    repetitions = 31

    def measure(callable_obj):
        durations: list[int] = []
        payload: dict[str, Any] = {}
        for _ in range(repetitions):
            start = perf_counter_ns()
            payload = callable_obj()
            durations.append(perf_counter_ns() - start)
        return durations, payload

    indexed_durations, indexed_payload = measure(lambda: search_index(store.base_dir, query, limit=12, expand=False))
    graph_durations, graph_payload = measure(lambda: build_graph_search_bundle(store.base_dir, query, limit=12, graph_limit=4, depth=1))
    indexed_median_ms = round(median(indexed_durations) / 1_000_000, 3)
    graph_median_ms = round(median(graph_durations) / 1_000_000, 3)
    graph_bundle_count = len(graph_payload.get("graph_bundles", []))
    graph_node_count = sum(len(bundle.get("nodes", [])) for bundle in graph_payload.get("graph_bundles", []))
    graph_edge_count = sum(len(bundle.get("edges", [])) for bundle in graph_payload.get("graph_bundles", []))

    return {
        "demo": "search_mode_timing",
        "measurement_scope": "local synthetic GroundRecall store; post-index query timing only; not comparable to external memory-layer products",
        "query": query,
        "document_count": index_payload["document_count"],
        "concept_count": topic_count,
        "claim_count": topic_count * claims_per_topic,
        "relation_count": max(0, topic_count - 1),
        "repetitions": repetitions,
        "indexed_search": {
            "median_ms": indexed_median_ms,
            "min_ms": round(min(indexed_durations) / 1_000_000, 3),
            "max_ms": round(max(indexed_durations) / 1_000_000, 3),
            "match_count": len(indexed_payload.get("matches", [])),
        },
        "indexed_plus_graph_search": {
            "median_ms": graph_median_ms,
            "min_ms": round(min(graph_durations) / 1_000_000, 3),
            "max_ms": round(max(graph_durations) / 1_000_000, 3),
            "match_count": len(graph_payload.get("matches", [])),
            "root_concept_count": len(graph_payload.get("root_concepts", [])),
            "graph_bundle_count": graph_bundle_count,
            "graph_node_count": graph_node_count,
            "graph_edge_count": graph_edge_count,
        },
        "median_graph_over_indexed_ratio": round(graph_median_ms / indexed_median_ms, 3) if indexed_median_ms else None,
        "interpretation": (
            "Indexed search is the lower-latency lookup path in this local fixture; indexed plus graph search "
            "adds graph neighborhoods and review context at additional query cost."
        ),
        "result": "pass",
    }


def demo_prior_work_discovery(work_dir: Path) -> dict[str, Any]:
    store = _base_store(work_dir / "prior_work_store")
    store.save_work(
        WorkRecord(
            work_id="work_graph_backfill_inconclusive",
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
            work_id="work_graph_backfill_confidential",
            work_kind="experiment",
            title="Graph backfill failed privately",
            summary="Confidential implementation details.",
            outcome="failed",
            release_level="confidential",
            current_status="reviewed",
        )
    )
    store.save_decision(
        DecisionRecord(
            decision_id="decision_graph_backfill_review",
            question="Should graph backfill be repeated?",
            outcome="Repeat only with new evidence and review.",
            rationale="The earlier approach lacked evidence.",
            release_level="public",
            current_status="reviewed",
        )
    )
    report = prior_work_search(store.base_dir, "graph backfill failed", maximum_release_level="public")
    return {
        "demo": "prior_work_discovery",
        "candidate_count": report.candidate_count,
        "top_candidate_id": report.candidates[0].candidate_id if report.candidates else "",
        "top_candidate_outcome": report.candidates[0].outcome if report.candidates else "",
        "review_required": report.candidates[0].review_required if report.candidates else False,
        "inaccessible_count": report.inaccessible_count,
        "inaccessible_by_release_level": report.inaccessible_by_release_level,
        "negative_or_inconclusive_result_found": any(item.outcome in {"failed", "inconclusive"} for item in report.candidates),
        "result": "pass",
    }


def demo_signed_catalog_discovery(work_dir: Path) -> dict[str, Any]:
    store = _base_store(work_dir / "catalog_store")
    store.save_scope(ScopeRecord(scope_id="scope-public", scope_kind="project", title="Public project", release_level="public", current_status="reviewed"))
    store.save_scope(ScopeRecord(scope_id="scope-internal", scope_kind="project", title="Internal project", release_level="internal", current_status="reviewed"))
    store.save_work(WorkRecord(work_id="work-public", work_kind="technique", title="Public graph technique", scope_id="scope-public", release_level="public", current_status="reviewed"))
    store.save_work(WorkRecord(work_id="work-internal", work_kind="experiment", title="Internal experiment", scope_id="scope-internal", release_level="internal", current_status="reviewed"))
    catalog_path = work_dir / "catalog.json"
    catalog = build_federation_catalog(
        store.base_dir,
        producer_instance_id="host-a",
        target_release_level="internal",
        detail_level="descriptive",
        signing_key=SIGNING_KEY,
        key_id=KEY_ID,
        signature_algorithm="hmac-sha256",
        out_path=catalog_path,
        created_at=CREATED_AT,
    )
    public_quarantine = import_federation_catalog_to_quarantine(
        catalog_path,
        work_dir / "catalog_quarantine",
        verification_key=SIGNING_KEY,
        key_id=KEY_ID,
        allowed_release_level="public",
        allowed_instance_ids=["host-a"],
    )
    matches = query_federation_catalog(public_quarantine.quarantine_path, "Public project")
    internal_matches = query_federation_catalog(public_quarantine.quarantine_path, "Internal project")
    return {
        "demo": "signed_catalog_discovery",
        "catalog_entry_count": len(catalog.entries),
        "catalog_content_hash_present": bool(catalog.manifest.content_hash),
        "catalog_signature_present": bool(catalog.manifest.signature),
        "receiver_accepted_entry_count": public_quarantine.accepted_entry_count,
        "receiver_excluded_entry_count": public_quarantine.excluded_entry_count,
        "public_query_scope_ids": [entry.scope_id for entry in matches],
        "internal_scope_hidden_by_receiver_cap": all(entry.scope_id != "scope-internal" for entry in internal_matches),
        "result": "pass",
    }


def demo_incremental_subscription(work_dir: Path) -> dict[str, Any]:
    store = _base_store(work_dir / "change_store")
    store.save_scope(ScopeRecord(scope_id="scope-public", scope_kind="project", title="Public", release_level="public", current_status="reviewed"))
    store.save_scope(ScopeRecord(scope_id="scope-internal", scope_kind="project", title="Internal", release_level="internal", current_status="reviewed"))
    store.save_work(WorkRecord(work_id="work-public", work_kind="technique", title="Public technique", scope_id="scope-public", release_level="public", current_status="reviewed"))
    store.save_work(WorkRecord(work_id="work-internal", work_kind="experiment", title="Internal experiment", scope_id="scope-internal", release_level="internal", current_status="reviewed"))
    subscription = FederationSubscription(
        subscription_id="sub-preprint",
        producer_instance_id="host-a",
        scope_ids=["scope-public"],
        record_kinds=["work"],
        maximum_release_level="public",
        purpose="preprint team project",
    )
    subscription_path = work_dir / "subscription.json"
    save_subscription(subscription_path, subscription)
    bundle_path = work_dir / "change_bundle.json"
    bundle = build_incremental_change_bundle(
        store.base_dir,
        subscription,
        signing_key=SIGNING_KEY,
        key_id=KEY_ID,
        signature_algorithm="hmac-sha256",
        out_path=bundle_path,
        created_at=CREATED_AT,
    )
    import_result = import_incremental_change_bundle_to_quarantine(
        bundle_path,
        work_dir / "change_quarantine",
        verification_key=SIGNING_KEY,
        subscription=subscription,
        key_id=KEY_ID,
    )
    replay = import_incremental_change_bundle_to_quarantine(
        bundle_path,
        work_dir / "change_quarantine",
        verification_key=SIGNING_KEY,
        subscription=subscription,
        key_id=KEY_ID,
    )
    acknowledged = acknowledge_change_bundle(subscription_path, bundle_path, verification_key=SIGNING_KEY, key_id=KEY_ID)
    return {
        "demo": "incremental_subscription",
        "event_record_ids": [event.record_id for event in bundle.events],
        "internal_work_excluded": "work-internal" not in [event.record_id for event in bundle.events],
        "import_decision": import_result.decision,
        "replay_detected": replay.replayed,
        "acknowledged_cursor": acknowledged.cursor,
        "cursor_matches_bundle": acknowledged.cursor == bundle.manifest.cursor_end,
        "result": "pass",
    }


def _review_receipt(receipt_id: str, reviewer: str, role: str, decision: str = "approve", reviewed_hash: str = "hash-current") -> ReviewReceiptRecord:
    return ReviewReceiptRecord(
        receipt_id=receipt_id,
        subject_type="claim",
        subject_id="claim-review-demo",
        reviewer_principal_id=reviewer,
        reviewer_role_id=role,
        decision=decision,
        rationale=f"{decision} by {reviewer}",
        reviewed_content_hash=reviewed_hash,
        policy_id="claimwright.review.v1",
        reviewed_at=CREATED_AT,
        release_level="internal",
    )


def demo_multi_party_review_feedback(work_dir: Path) -> dict[str, Any]:
    store = _base_store(work_dir / "review_store")
    receipts = [
        _review_receipt("review-author", "author", "group-reviewer"),
        _review_receipt("review-steward", "reviewer-b", "scope-steward"),
        _review_receipt("review-duplicate", "reviewer-b", "scope-steward"),
        _review_receipt("review-dissent", "reviewer-c", "adversarial-reviewer", decision="dissent"),
        _review_receipt("review-old", "reviewer-d", "group-reviewer", reviewed_hash="old-hash"),
    ]
    for receipt in receipts:
        record_review_receipt(store.base_dir, receipt)
    quorum = evaluate_review_quorum(
        receipts,
        subject_type="claim",
        subject_id="claim-review-demo",
        rule=QuorumRule(
            subject_type="claim",
            minimum_approvals=2,
            required_role_ids=["group-reviewer", "scope-steward"],
            independent_from_principal_ids=["author"],
        ),
        current_content_hash="hash-current",
    )
    record_federation_feedback(
        store.base_dir,
        FederationFeedbackRecord(
            feedback_id="feedback-dissent",
            origin_instance_id="receiver-a",
            target_instance_id="producer-a",
            subject_type="claim",
            subject_id="claim-review-demo",
            decision="dissent",
            rationale="Receiver preserves disagreement.",
            related_receipt_ids=["review-dissent"],
            release_level="internal",
        ),
    )
    disagreements = unresolved_federation_disagreements(store.base_dir)
    bundle = build_feedback_bundle(
        store.base_dir,
        origin_instance_id="receiver-a",
        target_instance_id="producer-a",
        signing_key=SIGNING_KEY,
        key_id=KEY_ID,
        out_path=work_dir / "feedback_bundle.json",
    )
    verified = verify_feedback_bundle(bundle, verification_key=SIGNING_KEY, key_id=KEY_ID)
    return {
        "demo": "multi_party_review_feedback",
        "quorum_satisfied": quorum.satisfied,
        "approval_count": quorum.approval_count,
        "duplicate_principal_ids": quorum.duplicate_principal_ids,
        "non_independent_principal_ids": quorum.non_independent_principal_ids,
        "dissent_receipt_ids": quorum.dissent_receipt_ids,
        "invalidated_receipt_ids": quorum.invalidated_receipt_ids,
        "unresolved_disagreement_count": len(disagreements),
        "feedback_bundle_verified": verified.content_hash == bundle.content_hash,
        "result": "pass",
    }


def demo_custody_planning(work_dir: Path) -> dict[str, Any]:
    store = _base_store(work_dir / "custody_store")
    store.save_scope(ScopeRecord(scope_id="scope-group", scope_kind="project", title="Group project", owner_principal_ids=["group-a"], release_level="internal", current_status="reviewed"))
    store.save_scope(ScopeRecord(scope_id="scope-private", scope_kind="project", title="Private notes", owner_principal_ids=["alice"], release_level="private", current_status="reviewed"))
    store.save_work(WorkRecord(work_id="work-group", work_kind="project", title="Reviewed group work", scope_id="scope-group", release_level="internal", current_status="reviewed"))
    store.save_work(WorkRecord(work_id="work-orphan", work_kind="lesson", title="Needs steward", scope_id="scope-group", release_level="internal", current_status="reviewed"))
    store.save_contribution(ContributionRecord(contribution_id="contrib-private", origin_instance_id="host-a", contributor_id="alice", destination_scope_id="scope-private", contribution_intent="personal note", proposed_release_level="private", release_level="private", state="proposed"))
    store.save_stewardship(StewardshipRecord(stewardship_id="steward-group", subject_type="work", subject_id="work-group", scope_id="scope-group", steward_principal_id="alice", status="active", release_level="internal", current_status="reviewed"))
    orphan_report = orphan_stewardship_report(store.base_dir)
    departure = plan_tenancy_departure(store.base_dir, departing_principal_id="alice", planned_at=CREATED_AT)
    retirement = plan_instance_retirement(store.base_dir, instance_id="host-a", planned_at=CREATED_AT, replacement_instance_id="host-new")
    return {
        "demo": "custody_planning",
        "orphan_count": orphan_report.orphan_count,
        "orphan_subject_ids": [item.subject_id for item in orphan_report.items],
        "departure_dry_run": departure.dry_run,
        "handoff_required_count": len(departure.handoff_required),
        "private_personal_record_ids": [item["record_id"] for item in departure.private_personal_records],
        "group_owned_record_ids_retained": [item["record_id"] for item in departure.group_owned_records_retained],
        "retirement_required_actions": retirement.required_actions,
        "retirement_pending_contribution_count": retirement.pending_contribution_count,
        "result": "pass",
    }


def demo_release_pack_withdrawal(work_dir: Path) -> dict[str, Any]:
    store = _base_store(work_dir / "release_pack_store")
    store.save_source(SourceRecord(source_id="source-a", title="Source A", url="https://example.test/source-a", license_id="CC-BY-4.0", attribution="Example Source", source_release_level="public", current_status="reviewed"))
    store.save_claim(
        ClaimRecord(
            claim_id="claim-release-a",
            claim_text="A release-ready claim.",
            license_id="CC-BY-4.0",
            attribution="Example Source",
            source_release_level="public",
            metadata={"release_level": "public", "provenance_visibility": "redacted"},
            redaction_policy_id="redact-public-v1",
            derivative_source_ids=["source-a"],
            provenance=ProvenanceRecord(source_url="https://private.example.test/source", origin_path="/private/source.md"),
            current_status="reviewed",
        )
    )
    pack = build_release_pack(
        store.base_dir,
        out_dir=work_dir / "release_pack",
        target_release_level="public",
        allowed_license_ids=["CC-BY-4.0"],
        signing_key=SIGNING_KEY,
        key_id=KEY_ID,
        created_at=CREATED_AT,
        pack_id="pack-preprint-a",
        review_receipt_ids=["review-release-a"],
        policy_id="claimwright.release.v1",
    )
    verified_pack = verify_release_pack(pack, verification_key=SIGNING_KEY, key_id=KEY_ID)
    notice = build_withdrawal_notice(
        pack_id="pack-preprint-a",
        signing_key=SIGNING_KEY,
        key_id=KEY_ID,
        withdrawn_at="2026-07-29T01:00:00Z",
        reason="superseded evidence",
        superseded_by_pack_id="pack-preprint-b",
        authority="publication-gatekeeper",
        out_path=work_dir / "withdrawal.json",
    )
    verified_notice = verify_withdrawal_notice(notice, verification_key=SIGNING_KEY, key_id=KEY_ID)
    return {
        "demo": "release_pack_withdrawal",
        "pack_verified": verified_pack.manifest.pack_id == "pack-preprint-a",
        "license_ids": pack.manifest.license_ids,
        "attribution_count": pack.manifest.attribution_count,
        "redaction_policy_ids": pack.manifest.redaction_policy_ids,
        "private_origin_path_redacted": "/private/source.md" not in str(pack.records),
        "withdrawal_verified": verified_notice.pack_id == "pack-preprint-a",
        "withdrawal_distinct_from_erasure": verified_notice.distinct_from_erasure,
        "withdrawal_preserves_historical_audit": verified_notice.preserve_historical_audit,
        "result": "pass",
    }


def demo_policy_gated_institutional_writes(work_dir: Path) -> dict[str, Any]:
    store = _base_store(work_dir / "institutional_write_store")
    allowed_scope = ScopeRecord(scope_id="scope-write-allowed", scope_kind="project", title="Allowed", release_level="internal", current_status="reviewed")
    allowed_result = save_institutional_record(store, allowed_scope)
    deny_provider = StaticPolicyProvider(default_decision="hard_gate", policy_id="preprint.write.hard_gate")
    blocked_write = False
    try:
        save_institutional_record(
            store,
            WorkRecord(work_id="work-write-blocked", work_kind="experiment", title="Blocked write", scope_id="scope-write-allowed", release_level="internal"),
            policy_provider=deny_provider,
        )
    except InstitutionalWriteError:
        blocked_write = store.get_work("work-write-blocked") is None
    contribution = ContributionRecord(
        contribution_id="contrib-write-demo",
        contributor_id="alice",
        destination_scope_id="scope-write-allowed",
        contribution_intent="share result",
        contributed_record_ids=["work-alpha"],
        contributed_content_hashes=["sha256:abc"],
        release_level="internal",
        proposed_release_level="internal",
    )
    store.save_contribution(contribution)
    transition_result = transition_contribution_with_policy(store, "contrib-write-demo", target_state="triaged", reviewer_id="bob", reviewer_role="group-reviewer", rationale="ready for review", receipt_id="receipt-write-demo")
    blocked_custody = False
    try:
        record_custody_event(
            store.base_dir,
            CustodyEventRecord(event_id="custody-write-blocked", event_kind="transfer", subject_type="scope", subject_id="scope-write-allowed", new_custodian_id="bob", release_level="internal"),
            authority="scope-steward",
            policy_provider=deny_provider,
        )
    except CustodyPolicyError:
        blocked_custody = store.get_custody_event("custody-write-blocked") is None
    return {
        "demo": "policy_gated_institutional_writes",
        "allowed_scope_write_performed": allowed_result.writes_performed,
        "blocked_work_write_left_no_record": blocked_write,
        "transition_written_record_ids": transition_result.written_record_ids,
        "contribution_state_after_transition": store.get_contribution("contrib-write-demo").state,
        "review_receipt_written": store.get_contribution_review_receipt("receipt-write-demo") is not None,
        "blocked_custody_event_left_no_record": blocked_custody,
        "result": "pass",
    }


def run(output_dir: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="groundrecall-preprint-demos-") as tmp:
        work_dir = Path(tmp)
        demos = [
            demo_provenance_promotion(work_dir),
            demo_contradiction_adjudication(work_dir),
            demo_contradiction_candidate_review(work_dir),
            demo_release_filtering(work_dir),
            demo_federation_quarantine(work_dir),
            demo_local_authority(work_dir),
            demo_policy_plugin_boundary(work_dir),
            demo_search_mode_timing(work_dir),
            demo_prior_work_discovery(work_dir),
            demo_signed_catalog_discovery(work_dir),
            demo_incremental_subscription(work_dir),
            demo_multi_party_review_feedback(work_dir),
            demo_custody_planning(work_dir),
            demo_release_pack_withdrawal(work_dir),
            demo_policy_gated_institutional_writes(work_dir),
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
