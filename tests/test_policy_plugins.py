from __future__ import annotations

from pathlib import Path

from groundrecall.policy import (
    ClaimWrightPolicyProvider,
    PolicyDecision,
    PolicyRequest,
    StaticPolicyProvider,
    compose_policy_decisions,
    load_policy_plugins,
)

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
    return root


def test_static_policy_provider_returns_structured_decision() -> None:
    provider = StaticPolicyProvider(policy_id="test.allow.v1")

    decision = provider.evaluate(PolicyRequest(decision_point="read", subject_id="agent-1", action="query"))

    assert decision.decision == "allow"
    assert decision.allowed is True
    assert decision.policy_id == "test.allow.v1"
    assert decision.decision_point == "read"
    assert decision.subject_id == "agent-1"


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
