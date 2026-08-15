from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Protocol

import yaml
from pydantic import BaseModel, Field

from .decision_challenge import build_decision_challenge_receipt


PolicyDecisionPoint = Literal[
    "read",
    "query",
    "propose",
    "review",
    "promote",
    "revise",
    "supersede",
    "adjudicate",
    "export",
    "publish",
    "federate_import",
    "federate_export",
    "redact",
    "delete",
    "cite_publicly",
    "act",
]

PolicyDecisionValue = Literal["allow", "deny", "soft_gate", "hard_gate", "require_review"]
ReleaseLevel = Literal["public", "internal", "confidential", "privileged", "private"]

RELEASE_LEVELS: tuple[ReleaseLevel, ...] = (
    "public",
    "internal",
    "confidential",
    "privileged",
    "private",
)
RELEASE_RANK: dict[ReleaseLevel, int] = {level: index for index, level in enumerate(RELEASE_LEVELS)}
RELEASE_VALUE_ALIASES: dict[str, ReleaseLevel] = {
    "public": "public",
    "publish": "public",
    "published": "public",
    "released": "public",
    "internal": "internal",
    "team": "internal",
    "project": "internal",
    "organization": "internal",
    "organisation": "internal",
    "confidential": "confidential",
    "sensitive": "confidential",
    "nonpublic": "confidential",
    "non_public": "confidential",
    "privileged": "privileged",
    "legal_privileged": "privileged",
    "attorney_client": "privileged",
    "medical": "privileged",
    "security": "privileged",
    "hr": "privileged",
    "private": "private",
    "local": "private",
    "local_only": "private",
    "do_not_export": "private",
    "no_export": "private",
    "secret": "private",
}

DECISION_RANK: dict[PolicyDecisionValue, int] = {
    "allow": 0,
    "require_review": 1,
    "soft_gate": 2,
    "hard_gate": 3,
    "deny": 4,
}

POLICY_PLUGIN_SCHEMA_VERSION = "groundrecall.policy_plugins.v1"


class PolicyRequest(BaseModel):
    decision_point: PolicyDecisionPoint
    subject_id: str = ""
    action: str = ""
    record_kind: str = ""
    record_id: str = ""
    release_level: ReleaseLevel | None = None
    target_release_level: ReleaseLevel | None = None
    scope_id: str = ""
    claim_state: str = ""
    evidence_state: str = ""
    citation_state: str = ""
    contradiction_state: str = ""
    stale: bool = False
    destructive: bool = False
    public_facing: bool = False
    durable_memory_change: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyDecision(BaseModel):
    decision: PolicyDecisionValue
    policy_id: str
    policy_version: str = ""
    provider_id: str = ""
    decision_point: PolicyDecisionPoint
    subject_id: str = ""
    action: str = ""
    reasons: list[str] = Field(default_factory=list)
    obligations: list[str] = Field(default_factory=list)
    required_reviewers: list[str] = Field(default_factory=list)
    allowed_release_level: ReleaseLevel | None = None
    redactions: list[str] = Field(default_factory=list)
    confidence_effects: list[dict[str, Any]] = Field(default_factory=list)
    audit_tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.decision == "allow"


class PolicyDecisionProvider(Protocol):
    provider_id: str

    def evaluate(self, request: PolicyRequest) -> PolicyDecision:
        """Return one policy decision for a bounded GroundRecall decision point."""


class StaticPolicyProvider(BaseModel):
    provider_id: str = "groundrecall.static_policy_provider.v1"
    policy_id: str = "groundrecall.default_allow_policy.v1"
    policy_version: str = "1"
    default_decision: PolicyDecisionValue = "allow"

    def evaluate(self, request: PolicyRequest) -> PolicyDecision:
        return PolicyDecision(
            decision=self.default_decision,
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            provider_id=self.provider_id,
            decision_point=request.decision_point,
            subject_id=request.subject_id,
            action=request.action,
            reasons=[f"default_{self.default_decision}"],
            metadata={"request": request.model_dump(mode="json")},
        )


class ClaimWrightPolicyProvider(BaseModel):
    provider_id: str = "groundrecall.claimwright_policy_adapter.v1"
    policy_id: str = "claimwright.policy_directory"
    policy_version: str = ""
    root_dir: str
    enforcement: dict[str, Any] = Field(default_factory=dict)
    claim_states: dict[str, Any] = Field(default_factory=dict)
    collaboration: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_directory(cls, root_dir: str | Path) -> "ClaimWrightPolicyProvider":
        root = Path(root_dir)
        enforcement = _load_yaml(root / "policies" / "enforcement.yaml")
        claim_states = _load_yaml(root / "policies" / "claim_states.yaml")
        collaboration = _load_yaml(root / "policies" / "collaboration.yaml")
        version = str(enforcement.get("version", "") or claim_states.get("version", ""))
        return cls(
            root_dir=str(root),
            policy_version=version,
            enforcement=enforcement,
            claim_states=claim_states,
            collaboration=collaboration,
        )

    def evaluate(self, request: PolicyRequest) -> PolicyDecision:
        reasons: list[str] = []
        obligations: list[str] = []
        required_reviewers: list[str] = []
        audit_tags: list[str] = [self.provider_id]
        decision: PolicyDecisionValue = "allow"
        matched_collaboration_rules: list[str] = []
        decision_challenge_receipt: dict[str, Any] | None = None

        challenge_payload = request.metadata.get("decision_challenge")
        if challenge_payload is not None:
            try:
                receipt = build_decision_challenge_receipt(
                    challenge_payload,
                    policy_version=self.policy_version,
                    release_level=request.target_release_level or request.release_level or "private",
                )
                decision_challenge_receipt = receipt.model_dump(mode="json")
                audit_tags.append("groundrecall.decision_challenge_receipt.v1")
                if receipt.outcome in {"revise", "defer"}:
                    decision = _max_decision(decision, "soft_gate")
                    reasons.append(f"decision_challenge_{receipt.outcome}")
                elif receipt.outcome == "escalate" or receipt.review_state == "escalated":
                    decision = _max_decision(decision, "hard_gate")
                    reasons.append("decision_challenge_escalation_required")
                elif receipt.review_state == "draft":
                    decision = _max_decision(decision, "require_review")
                    reasons.append("decision_challenge_review_incomplete")
            except ValueError as exc:
                decision = _max_decision(decision, "hard_gate")
                reasons.append("decision_challenge_invalid")
                obligations.append("repair_decision_challenge_receipt")
                decision_challenge_receipt = {"error": str(exc)}

        collaboration_rules = self.collaboration.get("rules", [])
        if isinstance(collaboration_rules, list):
            for rule in collaboration_rules:
                if not isinstance(rule, dict):
                    continue
                decision_points = rule.get("decision_points", [])
                actions = rule.get("actions", [])
                if request.decision_point not in decision_points or request.action not in actions:
                    continue
                rule_id = str(rule.get("id", "unnamed"))
                if rule_id == "destination_scope_required" and request.scope_id:
                    continue
                matched_collaboration_rules.append(rule_id)
                decision = _max_decision(decision, _mode_to_decision(str(rule.get("default_decision", ""))))
                reasons.append(f"collaboration_rule:{rule_id}")
                obligations.extend(_string_list(rule.get("obligations")))
                required_reviewers.extend(_string_list(rule.get("required_reviewers")))
                if rule_id == "destination_scope_required" and not request.scope_id:
                    reasons.append("collaboration_missing_destination_scope")
        if matched_collaboration_rules:
            audit_tags.append(str(self.collaboration.get("policy_id", "claimwright.collaboration_policy")))

        if request.public_facing or request.decision_point in {"publish", "cite_publicly"}:
            default = _enforcement_default(self.enforcement, "public_release")
            decision = _max_decision(decision, _mode_to_decision(default))
            obligations.append("run_publication_gate")

        if request.durable_memory_change or request.decision_point in {"propose", "promote", "revise", "supersede", "adjudicate"}:
            default = _enforcement_default(self.enforcement, "durable_memory_changes")
            decision = _max_decision(decision, _mode_to_decision(default))
            obligations.append("record_durable_memory_review_state")

        if request.destructive or request.decision_point in {"delete", "redact"}:
            decision = _max_decision(decision, "hard_gate")
            reasons.append("destructive_irreversible_action")
            obligations.append("record_explicit_erasure_or_redaction_authority")

        if request.claim_state:
            public_allowed = _claim_state_public_allowed(self.claim_states, request.claim_state)
            if (request.public_facing or request.decision_point in {"publish", "cite_publicly"}) and public_allowed is False:
                decision = _max_decision(decision, "hard_gate")
                reasons.append(f"claim_state_not_public_allowed:{request.claim_state}")
            elif public_allowed == "conditional":
                decision = _max_decision(decision, "require_review")
                reasons.append(f"claim_state_conditionally_public:{request.claim_state}")
                required_reviewers.append("claim-auditor")

        if request.citation_state in {"fabricated", "unverified", "metadata_conflicted", "unresolved"}:
            if request.public_facing or request.decision_point in {"publish", "cite_publicly"}:
                decision = _max_decision(decision, "hard_gate")
                reasons.append("fabricated_or_unverified_citation")
                required_reviewers.append("citation-reviewer")

        if request.contradiction_state in {"contradicted", "open", "under_review"} or request.stale:
            if request.public_facing or request.decision_point in {"publish", "cite_publicly"}:
                decision = _max_decision(decision, "hard_gate")
                reasons.append("contradicted_or_stale_claim")
                required_reviewers.append("adversarial-reviewer")

        if request.release_level == "private" and request.target_release_level == "public":
            decision = _max_decision(decision, "hard_gate")
            reasons.append("private_material_publication")
            obligations.append("remove_or_declassify_private_material")

        if decision != "allow" and "publication-gatekeeper" not in required_reviewers:
            required_reviewers.append("publication-gatekeeper")

        return PolicyDecision(
            decision=decision,
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            provider_id=self.provider_id,
            decision_point=request.decision_point,
            subject_id=request.subject_id,
            action=request.action,
            reasons=_dedupe(reasons),
            obligations=_dedupe(obligations),
            required_reviewers=_dedupe(required_reviewers),
            allowed_release_level=_most_restrictive_release([request.release_level, request.target_release_level]),
            audit_tags=_dedupe(audit_tags),
            metadata={
                "claimwright_root": self.root_dir,
                "matched_collaboration_rules": _dedupe(matched_collaboration_rules),
                **(
                    {"decision_challenge_receipt": decision_challenge_receipt}
                    if decision_challenge_receipt is not None
                    else {}
                ),
            },
        )


class CompositePolicyProvider(BaseModel):
    provider_id: str = "groundrecall.composite_policy_provider.v1"
    policy_id: str = "groundrecall.composed_policy.v1"
    providers: list[Any] = Field(default_factory=list)

    def evaluate(self, request: PolicyRequest) -> PolicyDecision:
        decisions = [provider.evaluate(request) for provider in self.providers]
        return compose_policy_decisions(decisions, request=request, policy_id=self.policy_id, provider_id=self.provider_id)


def compose_policy_decisions(
    decisions: list[PolicyDecision],
    *,
    request: PolicyRequest | None = None,
    policy_id: str = "groundrecall.composed_policy.v1",
    provider_id: str = "groundrecall.composite_policy_provider.v1",
) -> PolicyDecision:
    if not decisions:
        if request is None:
            raise ValueError("request is required when composing an empty decision list")
        return PolicyDecision(
            decision="allow",
            policy_id=policy_id,
            provider_id=provider_id,
            decision_point=request.decision_point,
            subject_id=request.subject_id,
            action=request.action,
            reasons=["no_policy_plugins_configured"],
        )

    strictest = max((decision.decision for decision in decisions), key=lambda value: DECISION_RANK[value])
    first = decisions[0]
    return PolicyDecision(
        decision=strictest,
        policy_id=policy_id,
        provider_id=provider_id,
        decision_point=request.decision_point if request else first.decision_point,
        subject_id=request.subject_id if request else first.subject_id,
        action=request.action if request else first.action,
        reasons=_dedupe(reason for decision in decisions for reason in decision.reasons),
        obligations=_dedupe(obligation for decision in decisions for obligation in decision.obligations),
        required_reviewers=_dedupe(reviewer for decision in decisions for reviewer in decision.required_reviewers),
        allowed_release_level=_most_restrictive_release(decision.allowed_release_level for decision in decisions),
        redactions=_dedupe(redaction for decision in decisions for redaction in decision.redactions),
        confidence_effects=[effect for decision in decisions for effect in decision.confidence_effects],
        audit_tags=_dedupe(tag for decision in decisions for tag in [decision.policy_id, decision.provider_id, *decision.audit_tags] if tag),
        metadata={"component_decisions": [decision.model_dump(mode="json") for decision in decisions]},
    )


def load_policy_provider(config: dict[str, Any]) -> PolicyDecisionProvider:
    provider_type = str(config.get("type", "")).strip()
    if provider_type in {"static", "groundrecall.static"}:
        return StaticPolicyProvider(
            provider_id=str(config.get("provider_id", "groundrecall.static_policy_provider.v1")),
            policy_id=str(config.get("policy_id", "groundrecall.default_allow_policy.v1")),
            policy_version=str(config.get("policy_version", "1")),
            default_decision=config.get("default_decision", "allow"),
        )
    if provider_type in {"claimwright", "claimwright.directory"}:
        return ClaimWrightPolicyProvider.from_directory(config["root_dir"])
    raise ValueError(f"unsupported policy provider type: {provider_type}")


def load_policy_plugins(path: str | Path) -> CompositePolicyProvider:
    payload = _load_yaml(Path(path))
    schema_version = str(payload.get("schema_version", POLICY_PLUGIN_SCHEMA_VERSION))
    if schema_version != POLICY_PLUGIN_SCHEMA_VERSION:
        raise ValueError(f"unsupported policy plugin schema_version: {schema_version}")
    provider_configs = payload.get("providers", [])
    if not isinstance(provider_configs, list):
        raise ValueError("policy plugin config must contain a providers list")
    for index, config in enumerate(provider_configs):
        if not isinstance(config, dict):
            raise ValueError(f"policy provider config at index {index} must be a mapping")
        if not str(config.get("type", "")).strip():
            raise ValueError(f"policy provider config at index {index} is missing type")
    providers = [load_policy_provider(config) for config in provider_configs]
    return CompositePolicyProvider(
        policy_id=str(payload.get("policy_id", "groundrecall.composed_policy.v1")),
        providers=providers,
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"expected mapping in policy file: {path}")
    return payload


def _enforcement_default(enforcement: dict[str, Any], key: str) -> str:
    defaults = enforcement.get("defaults", {})
    if not isinstance(defaults, dict):
        return ""
    return str(defaults.get(key, ""))


def _mode_to_decision(mode: str) -> PolicyDecisionValue:
    if mode == "hard_gate":
        return "hard_gate"
    if mode == "soft_gate":
        return "soft_gate"
    if mode == "require_review":
        return "require_review"
    if mode == "advisory":
        return "allow"
    return "allow"


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _max_decision(left: PolicyDecisionValue, right: PolicyDecisionValue) -> PolicyDecisionValue:
    return left if DECISION_RANK[left] >= DECISION_RANK[right] else right


def _claim_state_public_allowed(claim_states: dict[str, Any], claim_state: str) -> bool | str | None:
    states = claim_states.get("claim_states", [])
    if not isinstance(states, list):
        return None
    for item in states:
        if isinstance(item, dict) and item.get("id") == claim_state:
            return item.get("public_allowed")
    return None


def _most_restrictive_release(values: Any) -> ReleaseLevel | None:
    levels: list[ReleaseLevel] = []
    for value in values:
        if value is None:
            continue
        level = normalize_release_level(str(value))
        if level is not None:
            levels.append(level)
    if not levels:
        return None
    return max(levels, key=lambda level: RELEASE_RANK[level])


def normalize_release_level(value: Any) -> ReleaseLevel | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    return RELEASE_VALUE_ALIASES.get(normalized)


def _dedupe(values: Any) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        marker = json_key(value)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(value)
    return result


def json_key(value: Any) -> str:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return repr(value)
    return repr(value)
