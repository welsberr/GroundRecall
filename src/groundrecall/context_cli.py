from __future__ import annotations

import argparse
import json

from .lede_brief_context import (
    ContextCheckpoint,
    ContextObservation,
    CoverageState,
    advise_context,
    load_ledebrief_package,
    write_checkpoint,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage GroundRecall lede-brief context packages and checkpoints")
    subparsers = parser.add_subparsers(dest="action", required=True)
    load = subparsers.add_parser("load")
    load.add_argument("package")
    load.add_argument("--required", action="append", default=[])
    load.add_argument("--loaded", action="append", default=[])
    load.add_argument("--delivery-status", default="unconfirmed")
    advise = subparsers.add_parser("advise")
    advise.add_argument("--observation", required=True, help="JSON observation file")
    advise.add_argument("--coverage", required=True, help="JSON coverage file")
    checkpoint = subparsers.add_parser("checkpoint")
    checkpoint.add_argument("--session-id", required=True)
    checkpoint.add_argument("--objective", required=True)
    checkpoint.add_argument("--out", required=True)
    checkpoint.add_argument("--task-id", default="")
    checkpoint.add_argument("--next-action", default="")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.action == "load":
        package, coverage = load_ledebrief_package(
            args.package,
            required_unit_ids=args.required,
            loaded_unit_ids=args.loaded,
            delivery_status=args.delivery_status,
        )
        print(json.dumps({"package": package.model_dump(), "coverage": coverage.model_dump()}, indent=2))
    elif args.action == "advise":
        observation = ContextObservation.model_validate(json.loads(open(args.observation, encoding="utf-8").read()))
        coverage = CoverageState.model_validate(json.loads(open(args.coverage, encoding="utf-8").read()))
        print(advise_context(observation, coverage).model_dump_json(indent=2))
    else:
        checkpoint = ContextCheckpoint(
            session_id=args.session_id,
            task_id=args.task_id,
            objective=args.objective,
            next_action=args.next_action,
        )
        print(write_checkpoint(checkpoint, args.out))
