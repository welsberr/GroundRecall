from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .epistemap_adapter import export_claim_evaluation_g_package


def load_json_or_jsonl(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    text = source.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if source.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    payload = json.loads(text)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("evaluations", "claims", "rows"):
            if isinstance(payload.get(key), list):
                return payload[key]
    raise ValueError(f"Expected a JSON list or object containing evaluations/claims/rows: {source}")


def load_claims_by_id(path: str | Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    claims = load_json_or_jsonl(path)
    return {str(claim.get("claim_id", "")): claim for claim in claims if str(claim.get("claim_id", ""))}


def export_claim_evaluation_file(
    evaluations_path: str | Path,
    out_dir: str | Path,
    *,
    claims_path: str | Path | None = None,
    experiment_id: str = "groundrecall-claim-evaluation",
    evaluation_target: str = "groundrecall_claim_evaluation",
    corpus: str = "",
    group_by: str = "condition",
) -> dict[str, Any]:
    evaluations = load_json_or_jsonl(evaluations_path)
    return export_claim_evaluation_g_package(
        evaluations,
        out_dir,
        claims_by_id=load_claims_by_id(claims_path),
        experiment_id=experiment_id,
        evaluation_target=evaluation_target,
        corpus=corpus,
        group_by=group_by,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export explicit GroundRecall claim evaluations as Epistemap G files.")
    parser.add_argument("evaluations_json", help="JSON or JSONL explicit evaluation records.")
    parser.add_argument("out_dir")
    parser.add_argument("--claims-json", default=None, help="Optional JSON or JSONL claim records for context enrichment.")
    parser.add_argument("--experiment-id", default="groundrecall-claim-evaluation")
    parser.add_argument("--evaluation-target", default="groundrecall_claim_evaluation")
    parser.add_argument("--corpus", default="")
    parser.add_argument("--group-by", default="condition")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    payload = export_claim_evaluation_file(
        args.evaluations_json,
        args.out_dir,
        claims_path=args.claims_json,
        experiment_id=args.experiment_id,
        evaluation_target=args.evaluation_target,
        corpus=args.corpus,
        group_by=args.group_by,
    )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
