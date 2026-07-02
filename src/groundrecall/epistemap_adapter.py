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


def _provenance_from_row(row: dict[str, Any]) -> ProvenanceRef:
    return ProvenanceRef(
        artifact_id=str(row.get("origin_artifact_id", "")),
        origin_path=str(row.get("origin_path", "")),
        source_url=str(row.get("source_url", "")),
        support_kind=str(row.get("support_kind", "")),
        grounding_status=str(row.get("grounding_status", "")),
    )

