from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import (
    ArtifactRecord,
    ClaimRecord,
    ConceptRecord,
    ObservationRecord,
    PromotionRecord,
    ProvenanceRecord,
    RelationRecord,
    ReviewCandidateRecord,
)
from .review_schema import ReviewSession
from .store import GroundRecallStore


class PromotionGateError(RuntimeError):
    """Raised when an import is not eligible for promotion."""

    def __init__(self, message: str, payload: dict[str, Any]) -> None:
        super().__init__(message)
        self.payload = payload


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    return [json.loads(line) for line in text.splitlines()]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _review_status_map(status: str) -> str:
    return {
        "trusted": "promoted",
        "provisional": "reviewed",
        "rejected": "rejected",
        "needs_review": "triaged",
    }.get(status, "triaged")


def _provenance_from_payload(payload: dict[str, Any]) -> ProvenanceRecord:
    return ProvenanceRecord(
        origin_artifact_id=payload.get("origin_artifact_id", ""),
        origin_path=payload.get("origin_path", ""),
        origin_section=payload.get("origin_section", ""),
        source_url=payload.get("source_url", ""),
        retrieval_date=payload.get("retrieval_date", ""),
        machine_id=payload.get("machine_id", ""),
        session_id=payload.get("session_id", ""),
        support_kind=payload.get("support_kind", "unknown"),
        grounding_status=payload.get("grounding_status", "ungrounded"),
    )


def _review_candidate_rationale(item: dict[str, Any]) -> str:
    parts: list[str] = []
    title = str(item.get("title", "")).strip()
    if title:
        parts.append(title)
    parts.append(f"lane={item.get('triage_lane', 'knowledge_capture')}")
    parts.append(f"priority={int(item.get('priority', 50))}")
    finding_codes = [str(code) for code in item.get("finding_codes", []) if str(code).strip()]
    graph_codes = [str(code) for code in item.get("graph_codes", []) if str(code).strip()]
    if finding_codes:
        parts.append(f"findings={','.join(finding_codes)}")
    if graph_codes:
        parts.append(f"graph={','.join(graph_codes)}")
    return " | ".join(parts)


def _load_lint_payload(import_dir: Path) -> dict[str, Any]:
    lint_path = import_dir / "lint_findings.json"
    if not lint_path.exists():
        return {
            "summary": {"error_count": 0, "warning_count": 0},
            "findings": [],
            "missing_lint_file": True,
        }
    payload = _read_json(lint_path)
    payload.setdefault("summary", {})
    payload.setdefault("findings", [])
    return payload


def _lint_error_payload(lint_payload: dict[str, Any]) -> dict[str, Any]:
    findings = [item for item in lint_payload.get("findings", []) if item.get("severity") == "error"]
    return {
        "error_count": int(lint_payload.get("summary", {}).get("error_count", len(findings))),
        "warning_count": int(lint_payload.get("summary", {}).get("warning_count", 0)),
        "errors": findings,
    }


def _enforce_promotion_gate(import_dir: Path, allow_lint_errors: bool) -> dict[str, Any]:
    lint_payload = _load_lint_payload(import_dir)
    gate_payload = _lint_error_payload(lint_payload)
    if gate_payload["error_count"] > 0 and not allow_lint_errors:
        raise PromotionGateError(
            "Import has lint errors; review or repair the import before promotion, "
            "or pass allow_lint_errors=True / --allow-lint-errors to override.",
            gate_payload,
        )
    return gate_payload


def promote_import_to_store(
    import_dir: str | Path,
    store_dir: str | Path,
    reviewer: str | None = None,
    snapshot_id: str | None = None,
    allow_lint_errors: bool = False,
) -> dict[str, Any]:
    base = Path(import_dir)
    gate_payload = _enforce_promotion_gate(base, allow_lint_errors=allow_lint_errors)
    manifest = _read_json(base / "manifest.json")
    review_session = ReviewSession.model_validate_json((base / "review_session.json").read_text(encoding="utf-8"))
    queue_payload = _read_json(base / "review_queue.json")
    artifacts = _read_jsonl(base / "artifacts.jsonl")
    observations = _read_jsonl(base / "observations.jsonl")
    claims = _read_jsonl(base / "claims.jsonl")
    concepts = _read_jsonl(base / "concepts.jsonl")
    relations = _read_jsonl(base / "relations.jsonl")

    store = GroundRecallStore(store_dir)
    reviewed_by_concept = {entry.concept_id: entry for entry in review_session.draft_pack.concepts}
    reviewed_by_relation = {entry.relation_id: entry for entry in review_session.relation_reviews}
    promoted_claim_ids: list[str] = []
    promoted_concept_ids: list[str] = []
    promoted_relation_ids: list[str] = []

    for artifact in artifacts:
        store.save_artifact(
            ArtifactRecord(
                artifact_id=artifact["artifact_id"],
                artifact_kind=artifact["artifact_kind"],
                title=artifact.get("title", ""),
                path=artifact.get("path", ""),
                sha256=artifact.get("sha256", ""),
                created_at=artifact.get("created_at", ""),
                metadata=dict(artifact.get("metadata", {})),
                current_status="reviewed",
            )
        )

    for observation in observations:
        store.save_observation(
            ObservationRecord(
                observation_id=observation["observation_id"],
                artifact_id=observation.get("artifact_id", ""),
                role=observation.get("role", "summary"),
                text=observation.get("text", ""),
                provenance=_provenance_from_payload(observation),
                confidence_hint=float(observation.get("confidence_hint", 0.0)),
                current_status="reviewed",
            )
        )

    for concept in concepts:
        short_id = concept["concept_id"].replace("concept::", "", 1)
        review_entry = reviewed_by_concept.get(short_id)
        current_status = _review_status_map(review_entry.status if review_entry else concept.get("current_status", "triaged"))
        record = store.save_concept(
            ConceptRecord(
                concept_id=concept["concept_id"],
                title=review_entry.title if review_entry else concept.get("title", concept["concept_id"]),
                aliases=list(concept.get("aliases", [])),
                description=review_entry.description if review_entry else concept.get("description", ""),
                source_artifact_ids=list(concept.get("source_artifact_ids", [])),
                current_status=current_status,  # type: ignore[arg-type]
            )
        )
        if record.current_status in {"promoted", "reviewed"}:
            promoted_concept_ids.append(record.concept_id)

    reviewed_concept_ids = set(promoted_concept_ids)
    for claim in claims:
        concept_ids = list(claim.get("concept_ids", []))
        statuses = []
        for concept_id in concept_ids:
            short_id = concept_id.replace("concept::", "", 1)
            review_entry = reviewed_by_concept.get(short_id)
            statuses.append(_review_status_map(review_entry.status) if review_entry else "triaged")
        if statuses and all(status == "rejected" for status in statuses):
            current_status = "rejected"
        elif statuses and any(status == "promoted" for status in statuses):
            current_status = "promoted"
        elif statuses and any(status == "reviewed" for status in statuses):
            current_status = "reviewed"
        else:
            current_status = "triaged"
        record = store.save_claim(
            ClaimRecord(
                claim_id=claim["claim_id"],
                claim_text=claim.get("claim_text", ""),
                claim_kind=claim.get("claim_kind", "statement"),
                metadata=dict(claim.get("metadata", {})),
                source_observation_ids=list(claim.get("source_observation_ids", [])),
                supporting_fragment_ids=list(claim.get("supporting_fragment_ids", [])),
                concept_ids=concept_ids,
                contradicts_claim_ids=list(claim.get("contradicts_claim_ids", [])),
                supersedes_claim_ids=list(claim.get("supersedes_claim_ids", [])),
                confidence_hint=float(claim.get("confidence_hint", 0.0)),
                review_confidence=float(claim.get("review_confidence", 0.0)),
                last_confirmed_at=claim.get("last_confirmed_at", ""),
                provenance=_provenance_from_payload(claim),
                current_status=current_status,  # type: ignore[arg-type]
            )
        )
        if record.current_status in {"promoted", "reviewed"}:
            promoted_claim_ids.append(record.claim_id)

    for relation in relations:
        src_ok = relation.get("source_id") in reviewed_concept_ids
        tgt_ok = relation.get("target_id") in reviewed_concept_ids
        relation_review = reviewed_by_relation.get(relation["relation_id"])
        if relation_review is not None:
            current_status = _review_status_map(relation_review.status)
            if current_status in {"promoted", "reviewed"} and not (src_ok and tgt_ok):
                current_status = "triaged"
        else:
            current_status = "promoted" if src_ok and tgt_ok else "triaged"
        record = store.save_relation(
            RelationRecord(
                relation_id=relation["relation_id"],
                source_id=relation.get("source_id", ""),
                target_id=relation.get("target_id", ""),
                relation_type=relation.get("relation_type", "references"),
                evidence_ids=list(relation.get("evidence_ids", [])),
                provenance=_provenance_from_payload(relation),
                current_status=current_status,  # type: ignore[arg-type]
            )
        )
        if record.current_status in {"promoted", "reviewed"}:
            promoted_relation_ids.append(record.relation_id)

    for item in queue_payload.get("items", []):
        graph_codes = [str(code) for code in item.get("graph_codes", []) if str(code).strip()]
        finding_codes = [str(code) for code in item.get("finding_codes", []) if str(code).strip()]
        store.save_review_candidate(
            ReviewCandidateRecord(
                review_candidate_id=item["queue_id"],
                candidate_type=item["candidate_type"],
                candidate_id=item["candidate_id"],
                triage_lane=item.get("triage_lane", "knowledge_capture"),
                priority=int(item.get("priority", 50)),
                finding_codes=sorted(set(finding_codes + graph_codes)),
                rationale=_review_candidate_rationale(item),
                current_status="reviewed" if item["candidate_id"] in set(promoted_claim_ids + promoted_concept_ids + promoted_relation_ids) else "triaged",
            )
        )

    promotion = store.save_promotion(
        PromotionRecord(
            promotion_id=f"promotion-{manifest['import_id']}",
            candidate_type="concept",
            candidate_id=manifest["import_id"],
            promotion_target="groundrecall_store",
            verdict="approved",
            reviewer=reviewer or review_session.reviewer,
            promoted_object_ids=promoted_concept_ids + promoted_claim_ids + promoted_relation_ids,
            notes=f"Promoted import {manifest['import_id']} into GroundRecallStore.",
            promoted_at=_now(),
        )
    )

    built_snapshot = store.build_snapshot(
        snapshot_id=snapshot_id or f"snapshot-{manifest['import_id']}",
        created_at=_now(),
        metadata={
            "source_import_id": manifest["import_id"],
            "reviewer": reviewer or review_session.reviewer,
            "export_kind": "canonical",
        },
    )
    store.save_snapshot(built_snapshot)

    return {
        "import_id": manifest["import_id"],
        "store_dir": str(Path(store_dir)),
        "promotion_id": promotion.promotion_id,
        "promoted_concept_count": len(promoted_concept_ids),
        "promoted_claim_count": len(promoted_claim_ids),
        "promoted_relation_count": len(promoted_relation_ids),
        "lint_error_count": gate_payload["error_count"],
        "lint_warning_count": gate_payload["warning_count"],
        "lint_errors_allowed": allow_lint_errors,
        "snapshot_id": built_snapshot.snapshot_id,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Promote a GroundRecall import into canonical store objects.")
    parser.add_argument("import_dir")
    parser.add_argument("store_dir")
    parser.add_argument("--reviewer", default=None)
    parser.add_argument("--snapshot-id", default=None)
    parser.add_argument(
        "--allow-lint-errors",
        action="store_true",
        help="Promote even when lint_findings.json contains errors. Warnings do not block promotion.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        payload = promote_import_to_store(
            import_dir=args.import_dir,
            store_dir=args.store_dir,
            reviewer=args.reviewer,
            snapshot_id=args.snapshot_id,
            allow_lint_errors=args.allow_lint_errors,
        )
    except PromotionGateError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "gate": exc.payload}, indent=2), file=sys.stderr)
        raise SystemExit(2) from exc
    print(json.dumps(payload, indent=2))
