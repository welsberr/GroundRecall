from __future__ import annotations

import argparse
import json
from pathlib import Path

from .models import ScopeRecord, WorkRecord
from .store import GroundRecallStore


def _metadata(value: str) -> dict:
    if not value:
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("--metadata-json must contain a JSON object")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage institutional scope and work records.")
    subparsers = parser.add_subparsers(dest="record_type", required=True)
    for record_type in ("scope", "work"):
        record_parser = subparsers.add_parser(record_type)
        actions = record_parser.add_subparsers(dest="action", required=True)
        create = actions.add_parser("create")
        create.add_argument("store_dir")
        if record_type == "scope":
            create.add_argument("--scope-id", required=True)
            create.add_argument("--scope-kind", choices=("entity", "group", "project", "community"), required=True)
            create.add_argument("--title", required=True)
            create.add_argument("--description", default="")
            create.add_argument("--parent-scope-id", default="")
            create.add_argument("--owner-scope-id", default="")
            create.add_argument("--owner-principal-id", action="append", default=[])
            create.add_argument("--release-level", choices=("public", "internal", "confidential", "privileged", "private"), default="private")
            create.add_argument("--retention-class", default="")
        else:
            create.add_argument("--work-id", required=True)
            create.add_argument("--work-kind", choices=("project", "technique", "experiment", "prototype", "incident", "lesson"), required=True)
            create.add_argument("--title", required=True)
            create.add_argument("--summary", default="")
            create.add_argument("--scope-id", default="")
            create.add_argument("--work-status", default="active")
            create.add_argument("--outcome", choices=("unknown", "successful", "failed", "inconclusive", "superseded", "abandoned"), default="unknown")
            create.add_argument("--started-at", default="")
            create.add_argument("--completed-at", default="")
            create.add_argument("--review-due-at", default="")
            create.add_argument("--related-work-id", action="append", default=[])
            create.add_argument("--related-claim-id", action="append", default=[])
            create.add_argument("--related-artifact-id", action="append", default=[])
            create.add_argument("--release-level", choices=("public", "internal", "confidential", "privileged", "private"), default="private")
        create.add_argument("--status", choices=("draft", "triaged", "reviewed", "promoted", "superseded", "archived", "rejected"), default="draft")
        create.add_argument("--metadata-json", default="")

        list_parser = actions.add_parser("list")
        list_parser.add_argument("store_dir")
        show = actions.add_parser("show")
        show.add_argument("store_dir")
        show.add_argument("record_id")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    store = GroundRecallStore(args.store_dir)
    if args.action == "create":
        metadata = _metadata(args.metadata_json)
        if args.record_type == "scope":
            record = ScopeRecord(
                scope_id=args.scope_id,
                scope_kind=args.scope_kind,
                title=args.title,
                description=args.description,
                parent_scope_id=args.parent_scope_id,
                owner_scope_id=args.owner_scope_id,
                owner_principal_ids=args.owner_principal_id,
                release_level=args.release_level,
                retention_class=args.retention_class,
                current_status=args.status,
                metadata=metadata,
            )
            store.save_scope(record)
        else:
            record = WorkRecord(
                work_id=args.work_id,
                work_kind=args.work_kind,
                title=args.title,
                summary=args.summary,
                scope_id=args.scope_id,
                work_status=args.work_status,
                outcome=args.outcome,
                started_at=args.started_at,
                completed_at=args.completed_at,
                review_due_at=args.review_due_at,
                related_work_ids=args.related_work_id,
                related_claim_ids=args.related_claim_id,
                related_artifact_ids=args.related_artifact_id,
                release_level=args.release_level,
                current_status=args.status,
                metadata=metadata,
            )
            store.save_work(record)
        print(record.model_dump_json(indent=2))
        return
    if args.record_type == "scope":
        records = store.list_scopes() if args.action == "list" else [store.get_scope(args.record_id)]
    else:
        records = store.list_works() if args.action == "list" else [store.get_work(args.record_id)]
    records = [record for record in records if record is not None]
    print(json.dumps([record.model_dump(mode="json") for record in records], indent=2))

