from __future__ import annotations

import argparse
import sys

from . import assistant_export, export, graph_augment, ingest, inspect, lint, promotion, protocol, query, review_server, search_index


COMMANDS = {
    "import": ingest.main,
    "lint": lint.main,
    "promote": promotion.main,
    "protocol-init": protocol.main,
    "query": query.main,
    "index": search_index.main,
    "export": export.main,
    "graph-augment": graph_augment.main,
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
