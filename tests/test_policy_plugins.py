from __future__ import annotations

from pathlib import Path

from groundrecall.policy import (
    ClaimWrightPolicyProvider,
    PolicyDecision,
    PolicyRequest,
    StaticPolicyProvider,
    compose_policy_decisions,
    load_policy_plugins,
    normalize_release_level,
)
from groundrecall.decision_challenge import build_decision_challenge_receipt

def write_claimwright_policy(root: Path) -> Path:
    (root / "policies").mkdir(parents=True)
    (root / "policies" / "enforcement.yaml").write_text(
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
    (root / "policies" / "claim_states.yaml").write_text(
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
    (root / "policies" / "collaboration.yaml").write_text(
        "\n".join(
            [
                "schema_version: claimwright.collaboration_policy.v1",
                "policy_id: claimwright.collaboration.test.v1",
                "rules:",
                "  - id: destination_scope_required",
                "    decision_points: [propose, promote]",
                "    actions: [propose_group_contribution, accept_group_contribution]",
                "    default_decision: hard_gate",
                "    obligations: [record_destination_scope]",
                "  - id: stewardship_required",
                "    decision_points: [promote, act]",
                "    actions: [accept_group_contribution, transfer_knowledge_custody]",
                "    default_decision: hard_gate",
                "    required_reviewers: [scope-steward, records-custodian]",
                "  - id: prior_work_review",
                "    decision_points: [query, propose]",
                "    actions: [prior_work_review, initiate_durable_work]",
                "    default_decision: require_review",
                "    obligations: [record_prior_work_query, preserve_negative_results]",
                "  - id: catalog_least_disclosure",
                "    decision_points: [federate_export, federate_import, read]",
                "    actions: [publish_federation_catalog, import_federation_catalog, read_federation_catalog_entry]",
                "    default_decision: require_review",
                "    obligations: [apply_receiver_release_cap, prevent_protected_topic_inference]",
                "    required_reviewers: [scope-steward]",
            ]
        ),
        encoding="utf-8",
    )
    return root


def test_static_policy_provider_returns_structured_decision() -> None:
    provider = StaticPolicyProvider(policy_id="test.allow.v1")

    decision = provider.evaluate(PolicyRequest(decision_point="read", subject_id="agent-1", action="query"))

    assert decision.decision == "allow"
    assert decision.allowed is True
    assert decision.policy_id == "test.allow.v1"
    assert decision.decision_point == "read"
    assert decision.subject_id == "agent-1"
    assert decision.metadata["request"]["metadata"] == {}


def test_policy_release_normalization_does_not_treat_restricted_as_confidential() -> None:
    assert normalize_release_level("restricted") is None
    assert normalize_release_level("confidential") == "confidential"


def test_composition_uses_conservative_decision_and_accumulates_obligations() -> None:
    request = PolicyRequest(decision_point="publish", subject_id="agent-1", action="publish")
    allow = PolicyDecision(
        decision="allow",
        policy_id="policy.allow",
        provider_id="provider.allow",
        decision_point="publish",
        obligations=["preserve_provenance"],
        allowed_release_level="public",
    )
    gate = PolicyDecision(
        decision="hard_gate",
        policy_id="policy.gate",
        provider_id="provider.gate",
        decision_point="publish",
        reasons=["private_material_publication"],
        obligations=["remove_private_material"],
        required_reviewers=["publication-gatekeeper"],
        allowed_release_level="private",
    )

    decision = compose_policy_decisions([allow, gate], request=request)

    assert decision.decision == "hard_gate"
    assert decision.allowed is False
    assert decision.allowed_release_level == "private"
    assert decision.reasons == ["private_material_publication"]
    assert decision.obligations == ["preserve_provenance", "remove_private_material"]
    assert decision.required_reviewers == ["publication-gatekeeper"]
    assert "policy.allow" in decision.audit_tags
    assert "policy.gate" in decision.audit_tags


def test_claimwright_adapter_hard_gates_private_publication(tmp_path: Path) -> None:
    provider = ClaimWrightPolicyProvider.from_directory(write_claimwright_policy(tmp_path))

    decision = provider.evaluate(
        PolicyRequest(
            decision_point="publish",
            subject_id="agent-1",
            action="publish",
            release_level="private",
            target_release_level="public",
            public_facing=True,
            claim_state="private_only_speculation",
        )
    )

    assert decision.decision == "hard_gate"
    assert "private_material_publication" in decision.reasons
    assert "claim_state_not_public_allowed:private_only_speculation" in decision.reasons
    assert "publication-gatekeeper" in decision.required_reviewers
    assert "run_publication_gate" in decision.obligations


def test_claimwright_adapter_requires_review_for_conditional_public_claim_state(tmp_path: Path) -> None:
    provider = ClaimWrightPolicyProvider.from_directory(write_claimwright_policy(tmp_path))

    decision = provider.evaluate(
        PolicyRequest(
            decision_point="cite_publicly",
            subject_id="agent-1",
            action="cite",
            public_facing=True,
            claim_state="supported_by_primary_evidence",
        )
    )

    assert decision.decision == "hard_gate"
    assert "claim_state_conditionally_public:supported_by_primary_evidence" in decision.reasons
    assert "claim-auditor" in decision.required_reviewers
    assert "publication-gatekeeper" in decision.required_reviewers


def test_claimwright_adapter_applies_institutional_collaboration_rules(tmp_path: Path) -> None:
    provider = ClaimWrightPolicyProvider.from_directory(write_claimwright_policy(tmp_path))

    missing_scope = provider.evaluate(
        PolicyRequest(
            decision_point="propose",
            subject_id="alice",
            action="propose_group_contribution",
            durable_memory_change=True,
        )
    )
    assert missing_scope.decision == "hard_gate"
    assert "collaboration_missing_destination_scope" in missing_scope.reasons
    assert "record_destination_scope" in missing_scope.obligations
    assert "claimwright.collaboration.test.v1" in missing_scope.audit_tags

    accepted = provider.evaluate(
        PolicyRequest(
            decision_point="promote",
            subject_id="reviewer",
            action="accept_group_contribution",
            scope_id="scope-alpha",
            durable_memory_change=True,
            metadata={"steward_role_ids": ["scope-steward"]},
        )
    )
    assert accepted.decision == "hard_gate"
    assert "stewardship_required" in accepted.metadata["matched_collaboration_rules"]
    assert {"scope-steward", "records-custodian"} <= set(accepted.required_reviewers)
    assert "steward_role_ids" not in accepted.required_reviewers

    prior_work = provider.evaluate(
        PolicyRequest(
            decision_point="query",
            subject_id="alice",
            action="prior_work_review",
            scope_id="scope-alpha",
        )
    )
    assert prior_work.decision == "require_review"
    assert "record_prior_work_query" in prior_work.obligations

    catalog = provider.evaluate(
        PolicyRequest(
            decision_point="federate_export",
            subject_id="alice",
            action="publish_federation_catalog",
            target_release_level="internal",
        )
    )
    assert catalog.decision == "require_review"
    assert "apply_receiver_release_cap" in catalog.obligations
    assert "scope-steward" in catalog.required_reviewers


def test_policy_plugin_loader_composes_claimwright_with_static_policy(tmp_path: Path) -> None:
    config = tmp_path / "policy-plugins.yaml"
    claimwright_root = write_claimwright_policy(tmp_path / "claimwright")
    config.write_text(
        "\n".join(
            [
                "policy_id: test.composed",
                "providers:",
                "  - type: static",
                "    policy_id: test.static",
                "    default_decision: allow",
                "  - type: claimwright.directory",
                f"    root_dir: {claimwright_root}",
            ]
        ),
        encoding="utf-8",
    )

    provider = load_policy_plugins(config)
    decision = provider.evaluate(
        PolicyRequest(
            decision_point="publish",
            subject_id="agent-1",
            action="publish",
            public_facing=True,
            citation_state="unverified",
        )
    )

    assert decision.policy_id == "test.composed"
    assert decision.decision == "hard_gate"
    assert "fabricated_or_unverified_citation" in decision.reasons
    assert "citation-reviewer" in decision.required_reviewers


def test_policy_plugin_loader_accepts_authoritative_schema_version(tmp_path: Path) -> None:
    config = tmp_path / "policy-plugins.yaml"
    config.write_text(
        "\n".join(
            [
                "schema_version: groundrecall.policy_plugins.v1",
                "policy_id: test.schema",
                "providers:",
                "  - type: static",
                "    policy_id: test.static",
            ]
        ),
        encoding="utf-8",
    )

    provider = load_policy_plugins(config)

    assert provider.policy_id == "test.schema"


def test_policy_plugin_loader_rejects_unknown_schema_version(tmp_path: Path) -> None:
    config = tmp_path / "policy-plugins.yaml"
    config.write_text(
        "\n".join(
            [
                "schema_version: other.policy_plugins.v99",
                "providers:",
                "  - type: static",
            ]
        ),
        encoding="utf-8",
    )

    try:
        load_policy_plugins(config)
    except ValueError as exc:
        assert "unsupported policy plugin schema_version" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected schema version validation failure")


def test_policy_plugin_loader_rejects_provider_without_type(tmp_path: Path) -> None:
    config = tmp_path / "policy-plugins.yaml"
    config.write_text(
        "\n".join(
            [
                "schema_version: groundrecall.policy_plugins.v1",
                "providers:",
                "  - policy_id: missing-type",
            ]
        ),
        encoding="utf-8",
    )

    try:
        load_policy_plugins(config)
    except ValueError as exc:
        assert "missing type" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected provider type validation failure")


def _decision_challenge_payload(*, outcome: str = "proceed", review_state: str = "reviewed") -> dict:
    return {
        "schema_version": "claimwright.decision_challenge.v1",
        "challenge_id": "dc-groundrecall-001",
        "decision_id": "promote-import-001",
        "decision_version": 1,
        "subject_id": "reviewer-1",
        "action": "promote_import_to_store",
        "review_level": "standard",
        "trigger_codes": ["durable_memory_change"],
        "decision_summary": "Promote reviewed import into durable memory.",
        "failure_modes": [
            {
                "failure_mode_id": "fm_unreviewed_claim",
                "hypothesis": "A claim may not have completed source review.",
                "plausibility_basis": "The import contains newly extracted claims.",
                "material_consequence": "Unsupported content could become durable.",
                "decision_changing": True,
                "discriminating_evidence": "Inspect the review ledger.",
                "cheapest_check": "Run the review-ledger check.",
                "check_status": "completed",
                "result_ref": "artifact:review-ledger-001",
                "result_summary": "All imported claims have a review entry.",
            }
        ],
        "outcome": outcome,
        "residual_uncertainty": [],
        "stop_reason": "one_pass_complete",
        "review_state": review_state,
        "authority": "Policy finding only; promotion authority remains separately configured.",
    }


def test_claimwright_adapter_emits_idempotent_decision_challenge_receipt(tmp_path: Path) -> None:
    provider = ClaimWrightPolicyProvider.from_directory(write_claimwright_policy(tmp_path))
    request = PolicyRequest(
        decision_point="promote",
        subject_id="reviewer-1",
        action="promote_import_to_store",
        durable_memory_change=True,
        metadata={"decision_challenge": _decision_challenge_payload()},
    )

    first = provider.evaluate(request)
    second = provider.evaluate(request)

    receipt = first.metadata["decision_challenge_receipt"]
    assert first.decision == "soft_gate"
    assert receipt["schema_version"] == "groundrecall.decision_challenge_receipt.v1"
    assert receipt["idempotency_key"] == "promote-import-001:1:0.1"
    assert receipt["receipt_id"] == second.metadata["decision_challenge_receipt"]["receipt_id"]


def test_claimwright_adapter_blocks_invalid_or_escalated_decision_challenge(tmp_path: Path) -> None:
    provider = ClaimWrightPolicyProvider.from_directory(write_claimwright_policy(tmp_path))

    invalid = provider.evaluate(
        PolicyRequest(
            decision_point="promote",
            subject_id="reviewer-1",
            action="promote_import_to_store",
            durable_memory_change=True,
            metadata={"decision_challenge": {"schema_version": "wrong"}},
        )
    )
    assert invalid.decision == "hard_gate"
    assert "decision_challenge_invalid" in invalid.reasons

    escalated = provider.evaluate(
        PolicyRequest(
            decision_point="promote",
            subject_id="reviewer-1",
            action="promote_import_to_store",
            durable_memory_change=True,
            metadata={"decision_challenge": _decision_challenge_payload(outcome="escalate", review_state="escalated")},
        )
    )
    assert escalated.decision == "hard_gate"
    assert "decision_challenge_escalation_required" in escalated.reasons


def test_decision_challenge_receipt_does_not_copy_private_evidence() -> None:
    payload = _decision_challenge_payload()
    payload["failure_modes"][0]["private_evidence_text"] = "secret source text"

    receipt = build_decision_challenge_receipt(payload, policy_version="0.1")

    serialized = receipt.model_dump(mode="json")
    assert "private_evidence_text" not in serialized
    assert serialized["failure_mode_ids"] == ["fm_unreviewed_claim"]
