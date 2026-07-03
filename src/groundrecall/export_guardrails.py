from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from typing import Any, Iterable

from pydantic import BaseModel
from epistemap import GraphBundle, epistemic_summary

from .graph_diagnostics import build_graph_diagnostics
from .models import (
    ClaimRecord,
    GroundRecallSnapshot,
    PromotionRecord,
    RelationRecord,
)


PUBLIC_EXPORT_STATUSES = {"reviewed", "promoted"}

PRIVATE_METADATA_VALUES = {
    "confidential",
    "credential",
    "credentials",
    "do_not_export",
    "no_export",
    "nonpublic",
    "private",
    "privileged",
    "restricted",
    "secret",
    "sensitive",
}

PRIVATE_METADATA_KEYS = {
    "access",
    "access_level",
    "classification",
    "confidentiality",
    "contains_secret",
    "contains_secrets",
    "export",
    "export_policy",
    "privacy",
    "private",
    "privileged",
    "public",
    "release",
    "release_status",
    "secret",
    "sensitivity",
    "share",
    "sharing",
    "visibility",
}

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\baws_access_key_id\s*[:=]\s*['\"]?[A-Z0-9]{16,}", re.IGNORECASE),
    re.compile(r"\baws_secret_access_key\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{32,}", re.IGNORECASE),
    re.compile(r"\bapi[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_.-]{16,}", re.IGNORECASE),
    re.compile(r"\bpassword\s*[:=]\s*['\"]?[^'\"\s]{6,}", re.IGNORECASE),
    re.compile(r"\btoken\s*[:=]\s*['\"]?[A-Za-z0-9_.-]{20,}", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}"),
]


@dataclass(frozen=True)
class GuardrailFinding:
    record_kind: str
    record_id: str
    reason: str
    field_path: str = ""

    def manifest_payload(self) -> dict[str, str]:
        payload = {
            "record_kind": self.record_kind,
            "reason": self.reason,
        }
        if self.field_path:
            payload["field_path"] = self.field_path
        return payload


def export_guardrail_report(findings: Iterable[GuardrailFinding]) -> dict[str, Any]:
    finding_list = list(findings)
    counts = Counter(finding.record_kind for finding in finding_list)
    return {
        "enabled": True,
        "policy": "groundrecall_public_export_guardrails.v1",
        "excluded_total": len(finding_list),
        "excluded_counts": dict(sorted(counts.items())),
        "findings": [finding.manifest_payload() for finding in finding_list],
    }


def is_public_exportable_record(record: BaseModel, record_kind: str, record_id: str) -> tuple[bool, GuardrailFinding | None]:
    status = str(getattr(record, "current_status", "") or "")
    if status and status not in PUBLIC_EXPORT_STATUSES:
        return False, GuardrailFinding(record_kind, record_id, f"status:{status}")

    payload = record.model_dump()
    metadata_reason = _private_metadata_reason(payload)
    if metadata_reason is not None:
        return False, GuardrailFinding(record_kind, record_id, metadata_reason)

    secret_path = _secret_field_path(payload)
    if secret_path is not None:
        return False, GuardrailFinding(record_kind, record_id, "secret_like_content", secret_path)

    return True, None


def filter_snapshot_for_public_export(snapshot: GroundRecallSnapshot) -> tuple[GroundRecallSnapshot, dict[str, Any]]:
    findings: list[GuardrailFinding] = []

    sources = _filter_records(snapshot.sources, "source", lambda item: item.source_id, findings)
    allowed_source_ids = {item.source_id for item in sources}

    fragments = [
        item
        for item in _filter_records(snapshot.fragments, "fragment", lambda item: item.fragment_id, findings)
        if _keep_dependency("fragment", item.fragment_id, item.source_id, allowed_source_ids, "source", findings)
    ]
    allowed_fragment_ids = {item.fragment_id for item in fragments}

    artifacts = _filter_records(snapshot.artifacts, "artifact", lambda item: item.artifact_id, findings)
    allowed_artifact_ids = {item.artifact_id for item in artifacts}

    observations = [
        item
        for item in _filter_records(snapshot.observations, "observation", lambda item: item.observation_id, findings)
        if not item.artifact_id
        or _keep_dependency("observation", item.observation_id, item.artifact_id, allowed_artifact_ids, "artifact", findings)
    ]
    allowed_observation_ids = {item.observation_id for item in observations}

    concepts = _filter_records(snapshot.concepts, "concept", lambda item: item.concept_id, findings)
    allowed_concept_ids = {item.concept_id for item in concepts}
    pruned_concepts = []
    for item in concepts:
        source_artifact_ids = [artifact_id for artifact_id in item.source_artifact_ids if artifact_id in allowed_artifact_ids]
        if item.source_artifact_ids and not source_artifact_ids:
            findings.append(GuardrailFinding("concept", item.concept_id, "no_exportable_artifacts"))
            continue
        pruned_concepts.append(
            item.model_copy(
                update={
                    "source_artifact_ids": source_artifact_ids,
                }
            )
        )
    concepts = pruned_concepts
    allowed_concept_ids = {item.concept_id for item in concepts}

    claims: list[ClaimRecord] = []
    for item in _filter_records(snapshot.claims, "claim", lambda claim: claim.claim_id, findings):
        source_observation_ids = [value for value in item.source_observation_ids if value in allowed_observation_ids]
        supporting_fragment_ids = [value for value in item.supporting_fragment_ids if value in allowed_fragment_ids]
        concept_ids = [value for value in item.concept_ids if value in allowed_concept_ids]
        if item.source_observation_ids and not source_observation_ids:
            findings.append(GuardrailFinding("claim", item.claim_id, "no_exportable_observations"))
            continue
        if item.supporting_fragment_ids and not supporting_fragment_ids:
            findings.append(GuardrailFinding("claim", item.claim_id, "no_exportable_fragments"))
            continue
        if item.concept_ids and not concept_ids:
            findings.append(GuardrailFinding("claim", item.claim_id, "no_exportable_concepts"))
            continue
        claims.append(
            item.model_copy(
                update={
                    "source_observation_ids": source_observation_ids,
                    "supporting_fragment_ids": supporting_fragment_ids,
                    "concept_ids": concept_ids,
                    "contradicts_claim_ids": [],
                    "supersedes_claim_ids": [],
                }
            )
        )
    allowed_claim_ids = {item.claim_id for item in claims}
    claims = [
        item.model_copy(
            update={
                "contradicts_claim_ids": [value for value in item.contradicts_claim_ids if value in allowed_claim_ids],
                "supersedes_claim_ids": [value for value in item.supersedes_claim_ids if value in allowed_claim_ids],
            }
        )
        for item in claims
    ]

    relations: list[RelationRecord] = []
    for item in _filter_records(snapshot.relations, "relation", lambda relation: relation.relation_id, findings):
        if item.source_id not in allowed_concept_ids or item.target_id not in allowed_concept_ids:
            findings.append(GuardrailFinding("relation", item.relation_id, "non_exportable_relation_endpoint"))
            continue
        relations.append(
            item.model_copy(update={"evidence_ids": [value for value in item.evidence_ids if value in allowed_observation_ids]})
        )

    promotions = _filter_promotions(snapshot.promotions, allowed_claim_ids, allowed_concept_ids, {item.relation_id for item in relations}, findings)

    sanitized = snapshot.model_copy(
        update={
            "sources": sources,
            "fragments": fragments,
            "artifacts": artifacts,
            "observations": observations,
            "claims": claims,
            "concepts": concepts,
            "relations": relations,
            "promotions": promotions,
        }
    )
    return sanitized, export_guardrail_report(findings)


def filter_query_payload_for_public_export(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    findings: list[GuardrailFinding] = []
    sanitized = _filter_payload_value(payload, findings)
    if not isinstance(sanitized, dict):
        sanitized = {}
    _prune_query_payload_references(sanitized, findings)
    return sanitized, export_guardrail_report(findings)


def _filter_records(records: list[Any], record_kind: str, record_id_fn, findings: list[GuardrailFinding]) -> list[Any]:
    kept = []
    for record in records:
        record_id = str(record_id_fn(record))
        keep, finding = is_public_exportable_record(record, record_kind, record_id)
        if keep:
            kept.append(record)
        elif finding is not None:
            findings.append(finding)
    return kept


def _filter_promotions(
    promotions: list[PromotionRecord],
    allowed_claim_ids: set[str],
    allowed_concept_ids: set[str],
    allowed_relation_ids: set[str],
    findings: list[GuardrailFinding],
) -> list[PromotionRecord]:
    allowed_by_type = {
        "claim": allowed_claim_ids,
        "concept": allowed_concept_ids,
        "relation": allowed_relation_ids,
    }
    kept: list[PromotionRecord] = []
    for item in promotions:
        secret_path = _secret_field_path(item.model_dump())
        if secret_path is not None:
            findings.append(GuardrailFinding("promotion", item.promotion_id, "secret_like_content", secret_path))
            continue
        allowed_ids = allowed_by_type.get(item.candidate_type, set())
        if item.candidate_id not in allowed_ids:
            findings.append(GuardrailFinding("promotion", item.promotion_id, "non_exportable_promoted_object"))
            continue
        kept.append(item.model_copy(update={"promoted_object_ids": [value for value in item.promoted_object_ids if value in allowed_ids]}))
    return kept


def _keep_dependency(
    record_kind: str,
    record_id: str,
    dependency_id: str,
    allowed_dependency_ids: set[str],
    dependency_kind: str,
    findings: list[GuardrailFinding],
) -> bool:
    if dependency_id in allowed_dependency_ids:
        return True
    findings.append(GuardrailFinding(record_kind, record_id, f"non_exportable_{dependency_kind}"))
    return False


def _private_metadata_reason(value: Any, path: str = "") -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = str(key).strip().lower()
            child_path = f"{path}.{key}" if path else str(key)
            if normalized_key in PRIVATE_METADATA_KEYS:
                reason = _private_value_reason(child, child_path)
                if reason is not None:
                    return reason
            nested = _private_metadata_reason(child, child_path)
            if nested is not None:
                return nested
    elif isinstance(value, list):
        for index, child in enumerate(value):
            nested = _private_metadata_reason(child, f"{path}[{index}]")
            if nested is not None:
                return nested
    return None


def _private_value_reason(value: Any, path: str) -> str | None:
    if isinstance(value, bool):
        if path.lower().endswith(".public") and value is False:
            return f"metadata:{path}:false"
        if value is True and any(token in path.lower() for token in ("private", "privileged", "secret")):
            return f"metadata:{path}:true"
        return None
    if isinstance(value, str):
        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in PRIVATE_METADATA_VALUES:
            return f"metadata:{path}:{normalized}"
    if isinstance(value, list):
        for child in value:
            reason = _private_value_reason(child, path)
            if reason is not None:
                return reason
    return None


def _secret_field_path(value: Any, path: str = "") -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            secret_path = _secret_field_path(child, child_path)
            if secret_path is not None:
                return secret_path
    elif isinstance(value, list):
        for index, child in enumerate(value):
            secret_path = _secret_field_path(child, f"{path}[{index}]")
            if secret_path is not None:
                return secret_path
    elif isinstance(value, str):
        for pattern in SECRET_PATTERNS:
            if pattern.search(value):
                return path
    return None


def _filter_payload_value(value: Any, findings: list[GuardrailFinding], path: str = "") -> Any:
    if isinstance(value, dict):
        record_kind, record_id = _payload_record_identity(value)
        if record_kind and record_id:
            status = str(value.get("current_status", "") or "")
            if status and status not in PUBLIC_EXPORT_STATUSES:
                findings.append(GuardrailFinding(record_kind, record_id, f"status:{status}"))
                return None
            metadata_reason = _private_metadata_reason(value)
            if metadata_reason is not None:
                findings.append(GuardrailFinding(record_kind, record_id, metadata_reason))
                return None
            secret_path = _secret_field_path(value)
            if secret_path is not None:
                findings.append(GuardrailFinding(record_kind, record_id, "secret_like_content", secret_path))
                return None
        sanitized = {}
        for key, child in value.items():
            child_value = _filter_payload_value(child, findings, f"{path}.{key}" if path else str(key))
            if child_value is not None:
                sanitized[key] = child_value
        return sanitized
    if isinstance(value, list):
        sanitized_items = []
        for index, child in enumerate(value):
            child_value = _filter_payload_value(child, findings, f"{path}[{index}]")
            if child_value is not None:
                sanitized_items.append(child_value)
        return sanitized_items
    return value


def _prune_query_payload_references(payload: dict[str, Any], findings: list[GuardrailFinding]) -> None:
    artifacts = payload.get("source_artifacts")
    if isinstance(artifacts, list):
        allowed_artifact_ids = {
            item.get("artifact_id")
            for item in artifacts
            if isinstance(item, dict) and isinstance(item.get("artifact_id"), str)
        }
    else:
        allowed_artifact_ids = set()

    observations = payload.get("supporting_observations")
    if isinstance(observations, list):
        kept_observations = []
        for item in observations:
            if not isinstance(item, dict):
                continue
            observation_id = str(item.get("observation_id", ""))
            artifact_id = str(item.get("artifact_id", ""))
            if artifact_id and artifact_id not in allowed_artifact_ids:
                findings.append(GuardrailFinding("observation", observation_id, "non_exportable_artifact"))
                continue
            kept_observations.append(item)
        payload["supporting_observations"] = kept_observations
        allowed_observation_ids = {
            item.get("observation_id")
            for item in kept_observations
            if isinstance(item, dict) and isinstance(item.get("observation_id"), str)
        }
    else:
        allowed_observation_ids = set()

    claims = payload.get("relevant_claims")
    if isinstance(claims, list):
        kept_claims = []
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            claim_id = str(claim.get("claim_id", ""))
            original_observation_ids = [value for value in claim.get("source_observation_ids", []) if isinstance(value, str)]
            source_observation_ids = [value for value in original_observation_ids if value in allowed_observation_ids]
            if original_observation_ids and not source_observation_ids:
                findings.append(GuardrailFinding("claim", claim_id, "no_exportable_observations"))
                continue
            claim["source_observation_ids"] = source_observation_ids
            claim["supporting_fragment_ids"] = []
            claim["contradicts_claim_ids"] = []
            claim["supersedes_claim_ids"] = []
            kept_claims.append(claim)
        payload["relevant_claims"] = kept_claims
        allowed_claim_ids = {item.get("claim_id") for item in kept_claims if isinstance(item.get("claim_id"), str)}
    else:
        allowed_claim_ids = set()

    relations = payload.get("relations")
    if isinstance(relations, list):
        kept_relations = []
        for relation in relations:
            if not isinstance(relation, dict):
                continue
            evidence_ids = [value for value in relation.get("evidence_ids", []) if isinstance(value, str) and value in allowed_observation_ids]
            relation["evidence_ids"] = evidence_ids
            kept_relations.append(relation)
        payload["relations"] = kept_relations

    if isinstance(payload.get("contradictions"), list):
        payload["contradictions"] = [
            item for item in payload["contradictions"] if isinstance(item, dict) and item.get("claim_id") in allowed_claim_ids
        ]
    if isinstance(payload.get("supersessions"), list):
        payload["supersessions"] = [
            item for item in payload["supersessions"] if isinstance(item, dict) and item.get("claim_id") in allowed_claim_ids
        ]
    if isinstance(payload.get("source_artifacts"), list):
        payload["source_artifacts"] = [
            item for item in payload["source_artifacts"] if isinstance(item, dict) and item.get("artifact_id") in allowed_artifact_ids
        ]
    concept = payload.get("concept")
    allowed_concept_ids: set[str] = set()
    if isinstance(concept, dict) and isinstance(concept.get("source_artifact_ids"), list):
        concept["source_artifact_ids"] = [
            value for value in concept["source_artifact_ids"] if isinstance(value, str) and value in allowed_artifact_ids
        ]
        if isinstance(concept.get("concept_id"), str):
            allowed_concept_ids.add(concept["concept_id"])
    if isinstance(payload.get("related_concepts"), list):
        allowed_related = []
        for related in payload["related_concepts"]:
            if not isinstance(related, dict):
                continue
            concept_id = related.get("concept_id")
            if isinstance(concept_id, str):
                allowed_concept_ids.add(concept_id)
                allowed_related.append(related)
        payload["related_concepts"] = allowed_related
    _prune_epistemap_graph_payload(
        payload,
        allowed_concept_ids=allowed_concept_ids,
        allowed_claim_ids=allowed_claim_ids,
        allowed_observation_ids=allowed_observation_ids,
        findings=findings,
    )
    _prune_temporal_summary_payload(payload, allowed_claim_ids)
    _prune_graph_payload_references(payload, allowed_artifact_ids, allowed_observation_ids, findings)
    _refresh_query_assessment_surfaces(payload, findings)


def _prune_temporal_summary_payload(payload: dict[str, Any], allowed_claim_ids: set[str]) -> None:
    temporal = payload.get("temporal_summary")
    if not isinstance(temporal, dict):
        return
    for field_name in ("claim_windows", "first_contradictions"):
        field = temporal.get(field_name)
        if isinstance(field, dict):
            temporal[field_name] = {
                claim_id: value
                for claim_id, value in field.items()
                if isinstance(claim_id, str) and claim_id in allowed_claim_ids
            }
    if isinstance(temporal.get("stale_claims"), list):
        temporal["stale_claims"] = [
            item
            for item in temporal["stale_claims"]
            if isinstance(item, dict) and item.get("claim_id") in allowed_claim_ids
        ]
    fair_play = temporal.get("fair_play_diagnostic")
    if isinstance(fair_play, dict) and isinstance(fair_play.get("claims"), list):
        fair_play["claims"] = [
            item
            for item in fair_play["claims"]
            if isinstance(item, dict) and item.get("claim_id") in allowed_claim_ids
        ]


def _prune_epistemap_graph_payload(
    payload: dict[str, Any],
    *,
    allowed_concept_ids: set[str],
    allowed_claim_ids: set[str],
    allowed_observation_ids: set[str],
    findings: list[GuardrailFinding],
) -> None:
    graph = payload.get("epistemap_graph")
    if not isinstance(graph, dict):
        return
    allowed_node_ids = set(allowed_concept_ids) | set(allowed_claim_ids) | set(allowed_observation_ids)
    kept_nodes = []
    for node in graph.get("nodes", []) if isinstance(graph.get("nodes"), list) else []:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id", ""))
        node_type = str(node.get("type", "") or "node")
        secret_path = _secret_field_path(node)
        if secret_path is not None:
            findings.append(GuardrailFinding(node_type, node_id or "unknown", "secret_like_content", f"epistemap_graph.nodes.{secret_path}"))
            continue
        if node_id not in allowed_node_ids:
            findings.append(GuardrailFinding(node_type, node_id or "unknown", "non_exportable_epistemap_node"))
            continue
        kept_nodes.append(node)
    graph["nodes"] = kept_nodes
    allowed_node_ids = {str(node.get("id", "")) for node in kept_nodes if isinstance(node, dict)}

    kept_edges = []
    for edge in graph.get("edges", []) if isinstance(graph.get("edges"), list) else []:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        edge_id = str(edge.get("id", "") or f"{source}->{target}")
        secret_path = _secret_field_path(edge)
        if secret_path is not None:
            findings.append(GuardrailFinding("edge", edge_id, "secret_like_content", f"epistemap_graph.edges.{secret_path}"))
            continue
        if source not in allowed_node_ids or target not in allowed_node_ids:
            findings.append(GuardrailFinding("edge", edge_id, "non_exportable_epistemap_endpoint"))
            continue
        edge["evidence_ids"] = [
            value for value in edge.get("evidence_ids", []) if isinstance(value, str) and value in allowed_observation_ids
        ]
        kept_edges.append(edge)
    graph["edges"] = kept_edges
    graph["summary"] = {
        **(graph.get("summary", {}) if isinstance(graph.get("summary"), dict) else {}),
        "node_count": len(kept_nodes),
        "edge_count": len(kept_edges),
    }


def _refresh_query_assessment_surfaces(payload: dict[str, Any], findings: list[GuardrailFinding]) -> None:
    graph = payload.get("epistemap_graph")
    concept = payload.get("concept")
    if not isinstance(graph, dict) or not isinstance(concept, dict):
        return
    concept_id = concept.get("concept_id")
    if not isinstance(concept_id, str) or not concept_id:
        return
    try:
        bundle = GraphBundle.model_validate(graph)
        summary = epistemic_summary(bundle, concept_id)
    except Exception as exc:  # pragma: no cover - defensive guardrail fallback
        findings.append(GuardrailFinding("epistemap_graph", concept_id, "epistemic_summary_refresh_failed", type(exc).__name__))
        payload.pop("epistemic_summary", None)
        payload.pop("assessment_summary", None)
        return
    payload["epistemic_summary"] = summary
    payload["assessment_summary"] = _query_assessment_summary(summary, payload.get("temporal_summary", {}))


def _query_assessment_summary(epistemic: dict[str, Any], temporal_summary: Any) -> dict[str, Any]:
    bayesian = epistemic.get("bayesian_reliability", {}) if isinstance(epistemic, dict) else {}
    classification = bayesian.get("classification", {}) if isinstance(bayesian, dict) else {}
    posterior = bayesian.get("posterior", {}) if isinstance(bayesian, dict) else {}
    sensitivity = bayesian.get("prior_sensitivity", {}) if isinstance(bayesian, dict) else {}
    reliability = epistemic.get("reliability", {}) if isinstance(epistemic, dict) else {}
    fair_play = temporal_summary.get("fair_play_diagnostic", {}) if isinstance(temporal_summary, dict) else {}
    return {
        "reliability_band": reliability.get("band", ""),
        "bayesian_label": classification.get("label", ""),
        "bayesian_flags": list(classification.get("flags", []) or []),
        "bayesian_posterior_mean": posterior.get("mean"),
        "prior_sensitivity_range": sensitivity.get("mean_range"),
        "temporal_rating": fair_play.get("rating", ""),
    }


def _prune_graph_payload_references(
    payload: dict[str, Any],
    allowed_artifact_ids: set[str],
    allowed_observation_ids: set[str],
    findings: list[GuardrailFinding],
) -> None:
    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        return

    kept_nodes = []
    allowed_concept_ids: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("node_id", ""))
        record = node.get("record")
        if not isinstance(record, dict) or record.get("concept_id") != node_id:
            findings.append(GuardrailFinding("concept", node_id or "unknown", "non_exportable_graph_node"))
            continue
        source_artifact_ids = [value for value in record.get("source_artifact_ids", []) if isinstance(value, str)]
        exportable_source_artifact_ids = [value for value in source_artifact_ids if value in allowed_artifact_ids]
        if source_artifact_ids and not exportable_source_artifact_ids:
            findings.append(GuardrailFinding("concept", node_id or "unknown", "no_exportable_artifacts"))
            continue
        record["source_artifact_ids"] = exportable_source_artifact_ids
        node["title"] = str(record.get("title", ""))
        node["status"] = str(record.get("current_status", ""))
        kept_nodes.append(node)
        allowed_concept_ids.add(node_id)
    payload["nodes"] = kept_nodes

    root = payload.get("root_concept")
    if isinstance(root, dict):
        root_id = str(root.get("concept_id", ""))
        if root_id not in allowed_concept_ids:
            findings.append(GuardrailFinding("concept", root_id or "unknown", "non_exportable_graph_root"))
            payload.pop("root_concept", None)

    kept_edges = _filter_graph_edges(
        payload,
        "edges",
        allowed_concept_ids=allowed_concept_ids,
        allowed_observation_ids=allowed_observation_ids,
        findings=findings,
    )
    kept_provenance_edges = _filter_graph_edges(
        payload,
        "provenance_edges",
        allowed_concept_ids=allowed_concept_ids,
        allowed_observation_ids=allowed_observation_ids,
        findings=findings,
    )

    payload["graph_diagnostics"] = build_graph_diagnostics(
        [node["record"] for node in kept_nodes if isinstance(node.get("record"), dict)],
        [
            edge["record"]
            for edge in [*kept_edges, *kept_provenance_edges]
            if isinstance(edge.get("record"), dict)
        ],
        claims=[claim for claim in payload.get("relevant_claims", []) if isinstance(claim, dict)],
        observations=[observation for observation in payload.get("supporting_observations", []) if isinstance(observation, dict)],
    )


def _filter_graph_edges(
    payload: dict[str, Any],
    field_name: str,
    *,
    allowed_concept_ids: set[str],
    allowed_observation_ids: set[str],
    findings: list[GuardrailFinding],
) -> list[dict[str, Any]]:
    edges = payload.get(field_name)
    kept_edges: list[dict[str, Any]] = []
    if isinstance(edges, list):
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            edge_id = str(edge.get("edge_id", ""))
            source_id = str(edge.get("source_id", ""))
            target_id = str(edge.get("target_id", ""))
            record = edge.get("record")
            if source_id not in allowed_concept_ids or target_id not in allowed_concept_ids:
                findings.append(GuardrailFinding("relation", edge_id or "unknown", "non_exportable_relation_endpoint"))
                continue
            if not isinstance(record, dict) or record.get("relation_id") != edge_id:
                findings.append(GuardrailFinding("relation", edge_id or "unknown", "non_exportable_graph_edge"))
                continue
            evidence_ids = [
                value
                for value in edge.get("evidence_ids", [])
                if isinstance(value, str) and value in allowed_observation_ids
            ]
            edge["evidence_ids"] = evidence_ids
            record["evidence_ids"] = evidence_ids
            kept_edges.append(edge)
        payload[field_name] = kept_edges
    return kept_edges


def _payload_record_identity(value: dict[str, Any]) -> tuple[str, str]:
    for key, kind in (
        ("source_id", "source"),
        ("fragment_id", "fragment"),
        ("artifact_id", "artifact"),
        ("observation_id", "observation"),
        ("claim_id", "claim"),
        ("concept_id", "concept"),
        ("relation_id", "relation"),
        ("review_candidate_id", "review_candidate"),
        ("promotion_id", "promotion"),
    ):
        record_id = value.get(key)
        if isinstance(record_id, str) and record_id:
            return kind, record_id
    return "", ""
