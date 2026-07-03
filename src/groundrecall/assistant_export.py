from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import groundrecall.assistants  # noqa: F401
from .assistants.base import get_assistant_adapter
from .export_guardrails import filter_query_payload_for_public_export, filter_snapshot_for_public_export
from .query import build_query_bundle_for_concept
from .store import GroundRecallStore


def export_assistant_bundle(
    store_dir: str | Path,
    assistant: str,
    out_dir: str | Path,
    concept_refs: list[str] | None = None,
) -> dict[str, Any]:
    store = GroundRecallStore(store_dir)
    snapshot_model = store.build_snapshot(
        snapshot_id="assistant-export",
        created_at="",
        metadata={"export_kind": "assistant_adapter", "assistant": assistant},
    )
    snapshot_model, snapshot_guardrails = filter_snapshot_for_public_export(snapshot_model)
    snapshot_model.metadata["export_guardrails"] = snapshot_guardrails
    snapshot = snapshot_model.model_dump()
    query_bundles = []
    query_guardrails = []
    for concept_ref in concept_refs or []:
        payload = build_query_bundle_for_concept(store_dir, concept_ref)
        if payload is not None:
            payload, guardrail_report = filter_query_payload_for_public_export(payload)
            payload["export_guardrails"] = guardrail_report
            query_guardrails.append({"concept_ref": concept_ref, **guardrail_report})
            query_bundles.append(payload)
    adapter = get_assistant_adapter(assistant)
    paths = adapter.export_bundle(snapshot, query_bundles, out_dir)
    manifest = {
        "assistant": assistant,
        "output_paths": [str(path) for path in paths],
        "query_bundle_count": len(query_bundles),
        "export_guardrails": {
            "snapshot": snapshot_guardrails,
            "query_bundles": query_guardrails,
        },
    }
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / "assistant_export_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export assistant-specific GroundRecall bundles from canonical store data.")
    parser.add_argument("store_dir")
    parser.add_argument("assistant")
    parser.add_argument("out_dir")
    parser.add_argument("--concept", action="append", default=[])
    return parser


def main() -> None:
    args = build_parser().parse_args()
    payload = export_assistant_bundle(
        store_dir=args.store_dir,
        assistant=args.assistant,
        out_dir=args.out_dir,
        concept_refs=list(args.concept or []),
    )
    print(json.dumps(payload, indent=2))
