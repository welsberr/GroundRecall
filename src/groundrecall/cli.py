from __future__ import annotations

import argparse
import sys

from . import (
    assistant_export,
    claim_evaluation_export,
    confidence,
    contradictions,
    export,
    erasure,
    federation,
    graph_augment,
    graph_maintenance,
    ingest,
    institutional_custody,
    institutional_records,
    institutional_release,
    institutional_review,
    institutional_views,
    catalog,
    change_feed,
    prior_work,
    inspect,
    lint,
    promotion,
    protocol,
    query,
    relation_review,
    review_backlog,
    review_backlog_reminders,
    review_backlog_benchmark,
    review_server,
    search_index,
)


COMMANDS = {
    "import": ingest.main,
    "institutional": institutional_records.main,
    "custody": institutional_custody.main,
    "release": institutional_release.main,
    "review": institutional_review.main,
    "views": institutional_views.main,
    "prior-work": prior_work.main,
    "catalog": catalog.main,
    "changes": change_feed.main,
    "lint": lint.main,
    "promote": promotion.main,
    "protocol-init": protocol.main,
    "query": query.main,
    "index": search_index.main,
    "export": export.main,
    "erasure": erasure.main,
    "federation": federation.main,
    "contradictions": contradictions.main,
    "graph-augment": graph_augment.main,
    "graph-backfill": graph_augment.main,
    "graph-maintenance": graph_maintenance.main,
    "relation-review": relation_review.main,
    "assistant-export": assistant_export.main,
    "claim-evaluation-export": claim_evaluation_export.main,
    "confidence-migrate": confidence.confidence_migrate_main,
    "confidence-readiness": confidence.confidence_readiness_main,
    "confidence-restore": confidence.confidence_restore_main,
    "inspect": inspect.main,
    "review-server": review_server.main,
    "review-status": review_backlog.main,
    "review-ack": review_backlog.acknowledge_main,
    "review-defer": review_backlog.defer_main,
    "review-assign": review_backlog.assign_main,
    "review-remind": review_backlog_reminders.main,
    "review-benchmark": review_backlog_benchmark.main,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GroundRecall command-line tools")
    parser.add_argument("command", nargs="?", choices=sorted(COMMANDS))
    return parser


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] in COMMANDS:
        command = argv[0]
        remainder = argv[1:]
    else:
        parser = build_parser()
        args, remainder = parser.parse_known_args(argv)
        if not args.command:
            parser.print_help()
            return
        command = args.command
    handler = COMMANDS[command]
    original_argv = sys.argv
    try:
        sys.argv = [f"groundrecall.cli {command}", *remainder]
        handler()
    finally:
        sys.argv = original_argv
