"""Operator CLI for verifying GroundRecall MCP access audit chains."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .mcp_http import verify_audit_log


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="groundrecall-mcp-audit-verify",
        description="Verify a GroundRecall MCP JSONL audit hash chain.",
    )
    parser.add_argument("audit_log", help="path to the JSONL audit log")
    parser.add_argument("--json", action="store_true", dest="as_json", help="print a bounded JSON summary")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = verify_audit_log(args.audit_log)
    except (OSError, ValueError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    if args.as_json:
        print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    else:
        print("OK: records={records} chained_records={chained_records} last_hash={last_hash}".format(**summary))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
