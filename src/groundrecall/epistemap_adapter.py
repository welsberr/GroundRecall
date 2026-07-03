from __future__ import annotations

from typing import Any

from epistemap import Edge, GraphBundle, Node, ProvenanceRef, g_evaluation_row

_SOURCE_SIGNAL_KEYS = (
    "source_quality",
    "source_reliability",
    "trust_status",
    "source_stance",
    "stance",
    "adversarial_intent",
    "adversarial",
    "denialist",
    "access_scope",
    "availability_status",
)
_TEMPORAL_SIGNAL_KEYS = (
    "available_at",
    "validated_at",
    "published_at",
    "observed_at",
    "introduced_at",
    "created_at",
    "challenged_at",
    "superseded_at",
    "rejected_at",
    "timestep",
)


def graph_bundle_from_rows(
    concepts: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    *,
    graph_id: str = "groundrecall-import",
    title: str = "GroundRecall concept graph",
) -> GraphBundle:
    concept_ids = {str(item["concept_id"]) for item in concepts}
    nodes = [
        Node(
            id=str(concept["concept_id"]),
            type="concept",
            title=str(concept.get("title", "")),
            description=str(concept.get("description", "")),
            aliases=[str(alias) for alias in concept.get("aliases", [])],
            status=str(concept.get("current_status", "")),
            metadata={
                "source_artifact_ids": list(concept.get("source_artifact_ids", [])),
                **_temporal_metadata(concept),
            },
        )
        for concept in concepts
    ]
    edges: list[Edge] = []
    for relation in relations:
        source_id = str(relation.get("source_id", ""))
        target_id = str(relation.get("target_id", ""))
        if source_id not in concept_ids or target_id not in concept_ids:
            continue
        edges.append(
            Edge(
                id=str(relation.get("relation_id", "")),
                source=source_id,
                target=target_id,
                type=str(relation.get("relation_type", "references")),
                evidence_ids=[str(value) for value in relation.get("evidence_ids", [])],
                status=str(relation.get("current_status", "")),
                provenance=[_provenance_from_row(relation)],
                metadata=_temporal_metadata(relation),
            )
        )
    return GraphBundle(
        graph_id=graph_id,
        title=title,
        nodes=nodes,
        edges=edges,
        metadata={"source": "groundrecall"},
    )


def graph_bundle_from_query_payload(payload: dict[str, Any]) -> GraphBundle:
    nodes: dict[str, Node] = {}
    edges: list[Edge] = []
    concept = payload.get("concept", {})
    if concept:
        _set_node(
            nodes,
            Node(
                id=str(concept.get("concept_id", "")),
                type="concept",
                title=str(concept.get("title", "")),
                description=str(concept.get("description", "")),
                status=str(concept.get("current_status", "")),
                metadata=_temporal_metadata(concept),
            ),
        )
    for related in payload.get("related_concepts", []):
        _set_node(
            nodes,
            Node(
                id=str(related.get("concept_id", "")),
                type="concept",
                title=str(related.get("title", "")),
                description=str(related.get("description", "")),
                status=str(related.get("current_status", "")),
                metadata=_temporal_metadata(related),
            ),
        )
    for claim in payload.get("claims", []):
        claim_id = str(claim.get("claim_id", ""))
        _set_node(
            nodes,
            Node(
                id=claim_id,
                type="claim",
                title=str(claim.get("claim_text", ""))[:100],
                description=str(claim.get("claim_text", "")),
                status=str(claim.get("current_status", "")),
                confidence=float(claim.get("review_confidence") or claim.get("confidence_hint") or 0.0),
                provenance=[_provenance_from_row(claim)],
                metadata={
                    "claim_kind": claim.get("claim_kind", "statement"),
                    "source_roles": list(claim.get("source_roles", [])),
                    **_source_signal_metadata(claim),
                    **_temporal_metadata(claim),
                },
            ),
        )
        for concept_id in claim.get("concept_ids", []):
            if concept_id in nodes:
                edges.append(
                    Edge(
                        source=claim_id,
                        target=str(concept_id),
                        type="about_concept",
                        evidence_ids=list(claim.get("source_observation_ids", [])),
                        provenance=[_provenance_from_row(claim)],
                        metadata=_temporal_metadata(claim),
                    )
                )
        for target_id in claim.get("contradicts_claim_ids", []):
            edges.append(Edge(source=claim_id, target=str(target_id), type="contradicts", metadata={**_temporal_metadata(claim), **_source_signal_metadata(claim)}))
        for target_id in claim.get("supersedes_claim_ids", []):
            edges.append(Edge(source=claim_id, target=str(target_id), type="supersedes", metadata={**_temporal_metadata(claim), **_source_signal_metadata(claim)}))
    for observation in payload.get("supporting_observations", []):
        observation_id = str(observation.get("observation_id", ""))
        _set_node(
            nodes,
            Node(
                id=observation_id,
                type="observation",
                title=str(observation.get("role", "")),
                description=str(observation.get("text", "")),
                status=str(observation.get("grounding_status", "")),
                provenance=[_provenance_from_row(observation)],
                metadata={
                    "source_role": observation.get("source_role", ""),
                    **_source_signal_metadata(observation),
                    **_temporal_metadata(observation),
                },
            ),
        )
    observation_ids = set(nodes)
    for claim in payload.get("claims", []):
        for observation_id in claim.get("source_observation_ids", []):
            if observation_id in observation_ids:
                edges.append(
                    Edge(
                        source=str(observation_id),
                        target=str(claim.get("claim_id", "")),
                        type="supports_claim",
                        provenance=[_provenance_from_row(claim)],
                        metadata=_temporal_metadata(claim),
                    )
                )
    for relation in payload.get("relations", []):
        source_id = str(relation.get("source_id", ""))
        target_id = str(relation.get("target_id", ""))
        if source_id in nodes and target_id in nodes:
            edges.append(
                Edge(
                    id=str(relation.get("relation_id", "")),
                    source=source_id,
                    target=target_id,
                    type=str(relation.get("relation_type", "references")),
                    evidence_ids=list(relation.get("evidence_ids", [])),
                    provenance=[_provenance_from_row(relation)],
                    metadata=_temporal_metadata(relation),
                )
            )
    return GraphBundle(
        graph_id=f"groundrecall-query:{concept.get('concept_id', '')}",
        title=str(concept.get("title", "GroundRecall query graph")),
        description="GroundRecall concept, claim, evidence, and relation graph",
        nodes=[node for node in nodes.values() if node.id],
        edges=[edge for edge in edges if edge.source and edge.target],
        metadata={"source": "groundrecall", "bundle_kind": "groundrecall_query_epistemap"},
    )


def g_evaluation_row_from_claim_evaluation(
    evaluation: dict[str, Any],
    *,
    claim: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a canonical G row for an explicit GroundRecall claim evaluation.

    The evaluation supplies the observed label and probability. GroundRecall
    claim data only enriches identifiers, provenance, and temporal context.
    """

    claim = claim or {}
    provenance = claim.get("provenance", {})
    if not isinstance(provenance, dict):
        provenance = {}
    claim_metadata = claim.get("metadata", {})
    if not isinstance(claim_metadata, dict):
        claim_metadata = {}
    evaluation_metadata = evaluation.get("metadata", {})
    if not isinstance(evaluation_metadata, dict):
        evaluation_metadata = {}

    source_anchor = (
        str(evaluation.get("source_anchor", "")).strip()
        or str(provenance.get("origin_path", "")).strip()
        or str(provenance.get("source_url", "")).strip()
    )
    item_id = str(evaluation.get("item_id", "")).strip()
    if not item_id:
        item_id = "::".join(str(value) for value in claim.get("concept_ids", []) if str(value).strip())

    metadata = {
        "evaluation_target": evaluation.get("evaluation_target", "groundrecall_claim_evaluation"),
        "claim_text": claim.get("claim_text", ""),
        "claim_status": claim.get("current_status", ""),
        "grounding_status": claim.get("grounding_status", "") or provenance.get("grounding_status", ""),
        "support_kind": provenance.get("support_kind", ""),
        "confidence_hint": claim.get("confidence_hint", ""),
        "review_confidence": claim.get("review_confidence", ""),
        **_source_signal_metadata(claim),
        **_temporal_metadata(claim),
        **evaluation_metadata,
    }
    metadata = {key: value for key, value in metadata.items() if not _blank_metadata_value(value)}

    return g_evaluation_row(
        y=int(evaluation["y"]),
        p=float(evaluation["p"]),
        env=str(evaluation.get("env", "K")),
        run_id=str(evaluation.get("run_id", "")),
        subject_id=str(evaluation.get("subject_id", "")),
        condition=str(evaluation.get("condition", "")),
        phase=str(evaluation.get("phase", "")),
        item_id=item_id,
        claim_id=str(evaluation.get("claim_id", "") or claim.get("claim_id", "")),
        answer=str(evaluation.get("answer", "")),
        response=str(evaluation.get("response", "")),
        source_anchor=source_anchor,
        recognized_at=evaluation.get("recognized_at", ""),
        contradiction_available_at=evaluation.get(
            "contradiction_available_at",
            claim_metadata.get("challenged_at", ""),
        ),
        recognition_lag=evaluation.get("recognition_lag", ""),
        fair_play_rating=str(evaluation.get("fair_play_rating", "")),
        metadata=metadata,
    )


def _set_node(nodes: dict[str, Node], node: Node) -> None:
    if node.id:
        nodes[node.id] = node


def _blank_metadata_value(value: Any) -> bool:
    return value is None or value == "" or value == []


def _provenance_from_row(row: dict[str, Any]) -> ProvenanceRef:
    provenance = row.get("provenance", {})
    if not isinstance(provenance, dict):
        provenance = {}
    metadata = {
        **_temporal_metadata(row),
        **_temporal_metadata(provenance),
    }
    return ProvenanceRef(
        artifact_id=str(row.get("origin_artifact_id", "") or provenance.get("origin_artifact_id", "")),
        origin_path=str(row.get("origin_path", "") or provenance.get("origin_path", "")),
        source_url=str(row.get("source_url", "") or provenance.get("source_url", "")),
        support_kind=str(row.get("support_kind", "") or provenance.get("support_kind", "")),
        grounding_status=str(row.get("grounding_status", "") or provenance.get("grounding_status", "")),
        metadata=metadata,
    )


def _source_signal_metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata", {})
    values: dict[str, Any] = {}
    if isinstance(metadata, dict):
        values.update({key: metadata[key] for key in _SOURCE_SIGNAL_KEYS if key in metadata})
    values.update({key: row[key] for key in _SOURCE_SIGNAL_KEYS if key in row})
    return values


def _temporal_metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata", {})
    provenance = row.get("provenance", {})
    values: dict[str, Any] = {}
    if isinstance(metadata, dict):
        values.update({key: metadata[key] for key in _TEMPORAL_SIGNAL_KEYS if key in metadata and metadata[key] not in {"", None}})
    if isinstance(provenance, dict):
        values.update({key: provenance[key] for key in _TEMPORAL_SIGNAL_KEYS if key in provenance and provenance[key] not in {"", None}})
    values.update({key: row[key] for key in _TEMPORAL_SIGNAL_KEYS if key in row and row[key] not in {"", None}})
    retrieval_date = row.get("retrieval_date") or (provenance.get("retrieval_date") if isinstance(provenance, dict) else "")
    if retrieval_date:
        values.setdefault("available_at", retrieval_date)
    return values
