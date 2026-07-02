from __future__ import annotations

from typing import Any

from epistemap import Edge, GraphBundle, Node, ProvenanceRef


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
                    )
                )
        for target_id in claim.get("contradicts_claim_ids", []):
            edges.append(Edge(source=claim_id, target=str(target_id), type="contradicts"))
        for target_id in claim.get("supersedes_claim_ids", []):
            edges.append(Edge(source=claim_id, target=str(target_id), type="supersedes"))
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
                metadata={"source_role": observation.get("source_role", "")},
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


def _set_node(nodes: dict[str, Node], node: Node) -> None:
    if node.id:
        nodes[node.id] = node


def _provenance_from_row(row: dict[str, Any]) -> ProvenanceRef:
    return ProvenanceRef(
        artifact_id=str(row.get("origin_artifact_id", "")),
        origin_path=str(row.get("origin_path", "")),
        source_url=str(row.get("source_url", "")),
        support_kind=str(row.get("support_kind", "")),
        grounding_status=str(row.get("grounding_status", "")),
    )
