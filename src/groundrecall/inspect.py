from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .graph_diagnostics import build_graph_diagnostics
from .store import GroundRecallStore


def summarize_store(store_dir: str | Path, *, include_graph: bool = False) -> dict[str, Any]:
    store = GroundRecallStore(store_dir)
    snapshots = store.list_snapshots()
    latest_snapshot = max(snapshots, key=lambda item: item.created_at, default=None)
    payload: dict[str, Any] = {
        "store_dir": str(Path(store_dir)),
        "source_count": len(store.list_sources()),
        "artifact_count": len(store.list_artifacts()),
        "observation_count": len(store.list_observations()),
        "claim_count": len(store.list_claims()),
        "concept_count": len(store.list_concepts()),
        "relation_count": len(store.list_relations()),
        "review_candidate_count": len(store.list_review_candidates()),
        "promotion_count": len(store.list_promotions()),
        "snapshot_count": len(snapshots),
        "latest_snapshot_id": latest_snapshot.snapshot_id if latest_snapshot is not None else "",
    }
    if include_graph:
        payload["graph_diagnostics"] = build_graph_diagnostics(
            [item.model_dump() for item in store.list_concepts()],
            [item.model_dump() for item in store.list_relations()],
            claims=[item.model_dump() for item in store.list_claims()],
            observations=[item.model_dump() for item in store.list_observations()],
        )
    return payload


def inspect_store(
    store_dir: str | Path,
    out_path: str | Path | None = None,
    *,
    include_graph: bool = False,
) -> dict[str, Any]:
    payload = summarize_store(store_dir, include_graph=include_graph)
    if out_path is not None:
        Path(out_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect canonical GroundRecall store contents.")
    parser.add_argument("store_dir")
    parser.add_argument("--out", default=None)
    parser.add_argument("--graph", action="store_true", help="Include concept/relation graph diagnostics")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    payload = inspect_store(args.store_dir, out_path=args.out, include_graph=args.graph)
    print(json.dumps(payload, indent=2))
