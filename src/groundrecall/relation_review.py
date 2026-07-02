from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .models import PromotionRecord
from .store import GroundRecallStore


REVIEWABLE_STATUSES = {"draft", "triaged", "reviewed", "promoted", "superseded", "archived", "rejected"}
APPROVAL_STATUSES = {"reviewed", "promoted"}


def list_relation_review_batch(
    store_dir: str | Path,
    *,
    relation_status: str = "triaged",
    relation_type: str = "",
    support_kind: str = "",
    grounding_status: str = "",
    concept_prefix: str = "",
    finding_code: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    store = GroundRecallStore(store_dir)
    concepts = {item.concept_id: item for item in store.list_concepts()}
    review_by_candidate = {
        item.candidate_id: item
        for item in store.list_review_candidates()
        if item.candidate_type == "relation" and item.current_status != "rejected"
    }
    rows = []
    for relation in store.list_relations():
        if relation_status and relation.current_status != relation_status:
            continue
        if relation_type and relation.relation_type != relation_type:
            continue
        if support_kind and relation.provenance.support_kind != support_kind:
            continue
        if grounding_status and relation.provenance.grounding_status != grounding_status:
            continue
        if concept_prefix and not (relation.source_id.startswith(concept_prefix) or relation.target_id.startswith(concept_prefix)):
            continue
        review = review_by_candidate.get(relation.relation_id)
        if finding_code and (review is None or finding_code not in review.finding_codes):
            continue
        source = concepts.get(relation.source_id)
        target = concepts.get(relation.target_id)
        rows.append(
            {
                "relation_id": relation.relation_id,
                "source_id": relation.source_id,
                "source_title": source.title if source else relation.source_id,
                "target_id": relation.target_id,
                "target_title": target.title if target else relation.target_id,
                "relation_type": relation.relation_type,
                "status": relation.current_status,
                "support_kind": relation.provenance.support_kind,
                "grounding_status": relation.provenance.grounding_status,
                "evidence_count": len(relation.evidence_ids),
                "evidence_ids": relation.evidence_ids[:10],
                "review_candidate_id": review.review_candidate_id if review else "",
                "review_priority": review.priority if review else 100,
                "finding_codes": review.finding_codes if review else [],
                "rationale": review.rationale if review else "",
            }
        )
    rows.sort(key=lambda item: (item["review_priority"], -item["evidence_count"], item["relation_type"], item["relation_id"]))
    selected = rows[: max(0, int(limit))]
    return {
        "operation": "relation_review_list",
        "store_dir": str(Path(store_dir)),
        "filters": {
            "relation_status": relation_status,
            "relation_type": relation_type,
            "support_kind": support_kind,
            "grounding_status": grounding_status,
            "concept_prefix": concept_prefix,
            "finding_code": finding_code,
            "limit": max(0, int(limit)),
        },
        "candidate_count": len(rows),
        "returned_count": len(selected),
        "relations": selected,
        "decision_file_schema": {
            "reviewer": "Reviewer name",
            "decisions": [
                {
                    "relation_id": "rel_store_xg_example",
                    "status": "reviewed|promoted|rejected|triaged",
                    "relation_type": "optional replacement relation type",
                    "notes": "short review note",
                }
            ],
        },
    }


def apply_relation_review_batch(store_dir: str | Path, decision_path: str | Path) -> dict[str, Any]:
    store = GroundRecallStore(store_dir)
    payload = json.loads(Path(decision_path).read_text(encoding="utf-8"))
    decisions = payload.get("decisions", [])
    if not isinstance(decisions, list):
        raise ValueError("decision file must contain a decisions list")
    reviewer = str(payload.get("reviewer", "") or "").strip()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    applied = []
    skipped = []
    review_by_candidate = {
        item.candidate_id: item
        for item in store.list_review_candidates()
        if item.candidate_type == "relation"
    }

    for index, decision in enumerate(decisions, start=1):
        if not isinstance(decision, dict):
            skipped.append({"index": index, "reason": "decision_not_object"})
            continue
        relation_id = str(decision.get("relation_id", "") or "").strip()
        if not relation_id:
            skipped.append({"index": index, "reason": "missing_relation_id"})
            continue
        relation = store.get_relation(relation_id)
        if relation is None:
            skipped.append({"index": index, "relation_id": relation_id, "reason": "relation_not_found"})
            continue
        old_status = relation.current_status
        old_relation_type = relation.relation_type
        new_status = str(decision.get("status", old_status) or old_status).strip()
        if new_status not in REVIEWABLE_STATUSES:
            skipped.append({"index": index, "relation_id": relation_id, "reason": "invalid_status", "status": new_status})
            continue
        new_relation_type = str(decision.get("relation_type", old_relation_type) or old_relation_type).strip()
        relation.current_status = new_status  # type: ignore[assignment]
        relation.relation_type = new_relation_type
        store.save_relation(relation)

        review = review_by_candidate.get(relation_id)
        if review is not None:
            review.current_status = new_status  # type: ignore[assignment]
            note = str(decision.get("notes", "") or "").strip()
            if note:
                review.rationale = f"{review.rationale} | review_note={note}" if review.rationale else f"review_note={note}"
            store.save_review_candidate(review)

        if new_status in APPROVAL_STATUSES or new_status == "rejected":
            verdict = "rejected" if new_status == "rejected" else "approved"
            store.save_promotion(
                PromotionRecord(
                    promotion_id=f"promotion_relation_review_{relation_id}_{now.replace(':', '').replace('-', '')}",
                    candidate_type="relation",
                    candidate_id=relation_id,
                    verdict=verdict,
                    reviewer=reviewer,
                    promoted_object_ids=[relation_id],
                    notes=str(decision.get("notes", "") or "").strip(),
                    promoted_at=now,
                )
            )

        applied.append(
            {
                "relation_id": relation_id,
                "old_status": old_status,
                "new_status": new_status,
                "old_relation_type": old_relation_type,
                "new_relation_type": new_relation_type,
            }
        )

    return {
        "operation": "relation_review_apply",
        "store_dir": str(Path(store_dir)),
        "decision_path": str(Path(decision_path)),
        "reviewer": reviewer,
        "applied_count": len(applied),
        "skipped_count": len(skipped),
        "applied": applied,
        "skipped": skipped,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="List or apply canonical-store relation review batches.")
    parser.add_argument("store_dir")
    parser.add_argument("--apply", dest="decision_path", default="", help="Apply a JSON relation review decisions file")
    parser.add_argument("--status", default="triaged", help="Relation lifecycle status to list")
    parser.add_argument("--relation-type", default="")
    parser.add_argument("--support-kind", default="")
    parser.add_argument("--grounding-status", default="")
    parser.add_argument("--concept-prefix", default="")
    parser.add_argument("--finding-code", default="")
    parser.add_argument("--limit", type=int, default=50)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.decision_path:
        payload = apply_relation_review_batch(args.store_dir, args.decision_path)
    else:
        payload = list_relation_review_batch(
            args.store_dir,
            relation_status=args.status,
            relation_type=args.relation_type,
            support_kind=args.support_kind,
            grounding_status=args.grounding_status,
            concept_prefix=args.concept_prefix,
            finding_code=args.finding_code,
            limit=args.limit,
        )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
