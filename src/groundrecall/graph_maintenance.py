from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .graph_augment import VALID_STRATEGIES, augment_store_relations_from_claims


DEFAULT_STRATEGIES = ["claim-cooccurrence", "claim-mentions", "observation-cooccurrence", "source-family"]
STATE_SCHEMA_VERSION = "groundrecall.graph_maintenance_state.v1"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_state_path(store_dir: str | Path) -> Path:
    return Path(store_dir) / ".maintenance" / "graph_maintenance_state.json"


def run_graph_maintenance_slice(
    store_dir: str | Path,
    *,
    state_path: str | Path | None = None,
    strategies: list[str] | None = None,
    concept_prefixes: list[str] | None = None,
    limit: int = 10,
    min_evidence: int = 2,
    max_pair_checks: int = 50000,
    apply: bool = False,
    advance_on_dry_run: bool = False,
) -> dict[str, Any]:
    active_strategies = [item for item in (strategies or DEFAULT_STRATEGIES) if item]
    invalid = sorted(set(active_strategies) - VALID_STRATEGIES)
    if invalid:
        raise ValueError(f"Unknown graph maintenance strategy: {', '.join(invalid)}")
    if not active_strategies:
        raise ValueError("At least one graph maintenance strategy is required.")

    resolved_state_path = Path(state_path) if state_path is not None else default_state_path(store_dir)
    state = _load_state(resolved_state_path)
    strategy_index = int(state.get("next_strategy_index", 0)) % len(active_strategies)
    strategy = active_strategies[strategy_index]

    augmentation = augment_store_relations_from_claims(
        store_dir,
        concept_prefixes=list(concept_prefixes or []),
        min_evidence=min_evidence,
        strategy=strategy,
        limit=max(0, int(limit)),
        max_pair_checks=max(0, int(max_pair_checks)),
        apply=apply,
    )
    run_record = {
        "ran_at": _now(),
        "strategy": strategy,
        "applied": apply,
        "limit": max(0, int(limit)),
        "min_evidence": augmentation.get("min_evidence", min_evidence),
        "max_pair_checks": max(0, int(max_pair_checks)),
        "candidate_relation_count": augmentation.get("candidate_relation_count", 0),
        "relation_type_counts": augmentation.get("relation_type_counts", {}),
        "filter_summary": augmentation.get("filter_summary", {}),
        "write_summary": augmentation.get("write_summary", {}),
    }

    advanced = bool(apply or advance_on_dry_run)
    next_strategy_index = (strategy_index + 1) % len(active_strategies) if advanced else strategy_index
    if advanced:
        history = [*state.get("history", []), run_record][-20:]
        state = {
            "schema_version": STATE_SCHEMA_VERSION,
            "store_dir": str(Path(store_dir)),
            "updated_at": run_record["ran_at"],
            "run_count": int(state.get("run_count", 0)) + 1,
            "strategies": active_strategies,
            "next_strategy_index": next_strategy_index,
            "last_run": run_record,
            "history": history,
        }
        _save_state(resolved_state_path, state)

    return {
        "operation": "run_graph_maintenance_slice",
        "store_dir": str(Path(store_dir)),
        "state_path": str(resolved_state_path),
        "state_advanced": advanced,
        "selected_strategy": strategy,
        "next_strategy": active_strategies[next_strategy_index],
        "strategies": active_strategies,
        "run_record": run_record,
        "augmentation": augmentation,
    }


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "run_count": 0,
            "next_strategy_index": 0,
            "history": [],
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _save_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one bounded, resumable GroundRecall graph maintenance slice.")
    parser.add_argument("store_dir")
    parser.add_argument("--state-path", default=None)
    parser.add_argument("--strategy", action="append", choices=sorted(VALID_STRATEGIES), default=[])
    parser.add_argument("--concept-prefix", action="append", default=[])
    parser.add_argument("--limit", type=int, default=10, help="Maximum candidate relations to process in this slice.")
    parser.add_argument("--min-evidence", type=int, default=2)
    parser.add_argument("--max-pair-checks", type=int, default=50000, help="Maximum claim-pair checks for semantic pair-scanning strategies.")
    parser.add_argument("--apply", action="store_true", help="Write triaged relations and review candidates, then advance state.")
    parser.add_argument("--advance-on-dry-run", action="store_true", help="Advance maintenance state even without writes.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    payload = run_graph_maintenance_slice(
        args.store_dir,
        state_path=args.state_path,
        strategies=list(args.strategy or []),
        concept_prefixes=list(args.concept_prefix or []),
        limit=args.limit,
        min_evidence=args.min_evidence,
        max_pair_checks=args.max_pair_checks,
        apply=args.apply,
        advance_on_dry_run=args.advance_on_dry_run,
    )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
