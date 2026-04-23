from __future__ import annotations

import argparse
import sys

from . import assistant_export, export, ingest, inspect, lint, promotion, query, review_server


COMMANDS = {
    "import": ingest.main,
    "lint": lint.main,
    "promote": promotion.main,
    "query": query.main,
    "export": export.main,
    "assistant-export": assistant_export.main,
    "inspect": inspect.main,
    "review-server": review_server.main,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GroundRecall command-line tools")
    parser.add_argument("command", nargs="?", choices=sorted(COMMANDS))
    return parser


def main() -> None:
    argv = sys.argv[1:]
    parser = build_parser()
    args, remainder = parser.parse_known_args(argv)
    if not args.command:
        parser.print_help()
        return
    handler = COMMANDS[args.command]
    original_argv = sys.argv
    try:
        sys.argv = [f"groundrecall.cli {args.command}", *remainder]
        handler()
    finally:
        sys.argv = original_argv
