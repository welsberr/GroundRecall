from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
import uuid
from typing import Any

from .graph_augment import VALID_STRATEGIES, augment_store_relations_from_claims


DEFAULT_STRATEGIES = ["claim-cooccurrence", "claim-mentions", "observation-cooccurrence", "source-family"]
PROFILE_STRATEGIES = {
    "safe": DEFAULT_STRATEGIES,
    "support": ["claim-support-anchors", "observation-artifact-anchors"],
    "semantic": ["claim-links", "claim-contradiction-cues", "claim-mentions"],
    "all": [
        "claim-cooccurrence",
        "claim-links",
        "claim-mentions",
        "observation-cooccurrence",
        "source-family",
        "claim-support-anchors",
        "observation-artifact-anchors",
        "claim-contradiction-cues",
    ],
}
STATE_SCHEMA_VERSION = "groundrecall.graph_maintenance_state.v1"


class GraphMaintenanceLockError(RuntimeError):
    """Raised when a graph maintenance slice cannot acquire its lock."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_state_path(store_dir: str | Path, profile: str = "safe") -> Path:
    safe_profile = re.sub(r"[^A-Za-z0-9_.-]+", "-", profile).strip("-") or "safe"
    return Path(store_dir) / ".maintenance" / f"graph_maintenance_state__{safe_profile}.json"


def default_lock_path(state_path: str | Path) -> Path:
    path = Path(state_path)
    return path.with_name(f"{path.name}.lock")


def run_graph_maintenance_slice(
    store_dir: str | Path,
    *,
    state_path: str | Path | None = None,
    lock_path: str | Path | None = None,
    skip_if_locked: bool = True,
    stale_lock_seconds: int = 3600,
    strategies: list[str] | None = None,
    profile: str = "safe",
    concept_prefixes: list[str] | None = None,
    limit: int = 10,
    min_evidence: int = 2,
    max_pair_checks: int = 50000,
    apply: bool = False,
    advance_on_dry_run: bool = False,
) -> dict[str, Any]:
    active_strategies = _resolve_strategies(strategies=strategies, profile=profile)

    resolved_state_path = Path(state_path) if state_path is not None else default_state_path(store_dir, profile)
    resolved_lock_path = Path(lock_path) if lock_path is not None else default_lock_path(resolved_state_path)
    lock_token = uuid.uuid4().hex
    acquired_lock = _acquire_lock(
        resolved_lock_path,
        {
            "created_at": _now(),
            "pid": os.getpid(),
            "profile": profile,
            "store_dir": str(Path(store_dir)),
            "state_path": str(resolved_state_path),
            "token": lock_token,
        },
        stale_lock_seconds=stale_lock_seconds,
    )
    if not acquired_lock:
        if not skip_if_locked:
            raise GraphMaintenanceLockError(f"Graph maintenance lock is active: {resolved_lock_path}")
        return {
            "operation": "run_graph_maintenance_slice",
            "store_dir": str(Path(store_dir)),
            "state_path": str(resolved_state_path),
            "lock_path": str(resolved_lock_path),
            "locked": True,
            "skipped": True,
            "skip_reason": "lock_active",
            "state_advanced": False,
            "selected_strategy": "",
            "next_strategy": "",
            "profile": profile,
            "strategies": active_strategies,
            "run_record": {},
            "augmentation": {},
        }

    try:
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
                "profile": profile,
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
            "lock_path": str(resolved_lock_path),
            "locked": False,
            "skipped": False,
            "state_advanced": advanced,
            "selected_strategy": strategy,
            "next_strategy": active_strategies[next_strategy_index],
            "profile": profile,
            "strategies": active_strategies,
            "run_record": run_record,
            "augmentation": augmentation,
        }
    finally:
        _release_lock(resolved_lock_path, token=lock_token)


def _resolve_strategies(*, strategies: list[str] | None, profile: str) -> list[str]:
    active_strategies = [item for item in (strategies or []) if item]
    if not active_strategies:
        if profile not in PROFILE_STRATEGIES:
            raise ValueError(f"Unknown graph maintenance profile: {profile}")
        active_strategies = list(PROFILE_STRATEGIES[profile])
    invalid = sorted(set(active_strategies) - VALID_STRATEGIES)
    if invalid:
        raise ValueError(f"Unknown graph maintenance strategy: {', '.join(invalid)}")
    if not active_strategies:
        raise ValueError("At least one graph maintenance strategy is required.")
    return active_strategies


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


def _acquire_lock(path: Path, payload: dict[str, Any], *, stale_lock_seconds: int) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if _lock_is_stale(path, stale_lock_seconds=stale_lock_seconds):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    try:
        descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    return True


def _lock_is_stale(path: Path, *, stale_lock_seconds: int) -> bool:
    if stale_lock_seconds <= 0:
        return False
    try:
        age_seconds = time.time() - path.stat().st_mtime
    except FileNotFoundError:
        return False
    return age_seconds > stale_lock_seconds


def _release_lock(path: Path, *, token: str) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return
    if not isinstance(payload, dict) or payload.get("token") != token:
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one bounded, resumable GroundRecall graph maintenance slice.")
    parser.add_argument("store_dir")
    parser.add_argument("--state-path", default=None)
    parser.add_argument("--lock-path", default=None)
    parser.add_argument("--profile", choices=sorted(PROFILE_STRATEGIES), default="safe")
    parser.add_argument("--strategy", action="append", choices=sorted(VALID_STRATEGIES), default=[])
    parser.add_argument("--concept-prefix", action="append", default=[])
    parser.add_argument("--limit", type=int, default=10, help="Maximum candidate relations to process in this slice.")
    parser.add_argument("--min-evidence", type=int, default=2)
    parser.add_argument("--max-pair-checks", type=int, default=50000, help="Maximum claim-pair checks for semantic pair-scanning strategies.")
    parser.add_argument("--apply", action="store_true", help="Write triaged relations and review candidates, then advance state.")
    parser.add_argument("--advance-on-dry-run", action="store_true", help="Advance maintenance state even without writes.")
    parser.add_argument("--fail-if-locked", action="store_true", help="Raise an error instead of returning a skipped payload when another slice is active.")
    parser.add_argument("--stale-lock-seconds", type=int, default=3600, help="Remove an existing lock older than this many seconds. Use 0 to disable stale-lock recovery.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    payload = run_graph_maintenance_slice(
        args.store_dir,
        state_path=args.state_path,
        lock_path=args.lock_path,
        skip_if_locked=not args.fail_if_locked,
        stale_lock_seconds=args.stale_lock_seconds,
        strategies=list(args.strategy or []),
        profile=args.profile,
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
