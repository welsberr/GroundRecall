"""Create bounded, redacted operator exports of MCP audit chains."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

from .mcp_http import verify_audit_log

SCHEMA_VERSION = "groundrecall.mcp_audit_export.v1"
DEFAULT_MAX_RECORDS = 1000
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
_SAFE_FIELDS = (
    "event_id", "recorded_at", "correlation_id", "method", "tool", "decision",
    "result_class", "http_status", "maximum_release_level", "hash_algorithm",
    "previous_hash", "record_hash",
)
_IDENTITY_FIELDS = ("subject_id", "realm_id")


def export_audit(path: str | os.PathLike[str], output: str | os.PathLike[str], *, max_records: int = DEFAULT_MAX_RECORDS, max_bytes: int = DEFAULT_MAX_BYTES, include_identities: bool = False) -> dict[str, Any]:
    """Verify and atomically export a bounded whitelist projection.

    The source is never modified or deleted. Request content, credentials,
    reasons, and filesystem paths are intentionally excluded.
    """
    if max_records < 1 or max_records > 100_000:
        raise ValueError("max_records must be between 1 and 100000")
    if max_bytes < 1024 or max_bytes > 100 * 1024 * 1024:
        raise ValueError("max_bytes must be between 1024 and 104857600")
    source = Path(path)
    verify_audit_log(source)
    rows: list[dict[str, Any]] = []
    consumed = 0
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError("audit record must be an object")
        exported = {key: row[key] for key in _SAFE_FIELDS if key in row}
        if include_identities:
            exported.update({key: row[key] for key in _IDENTITY_FIELDS if key in row})
        encoded = json.dumps(exported, sort_keys=True, separators=(",", ":"))
        if rows and (len(rows) >= max_records or consumed + len(encoded.encode("utf-8")) + 1 > max_bytes):
            break
        if not rows and len(encoded.encode("utf-8")) + 1 > max_bytes:
            raise ValueError("max_bytes is too small for one audit record")
        rows.append(exported)
        consumed += len(encoded.encode("utf-8")) + 1
    payload = {"schema_version": SCHEMA_VERSION, "records": rows, "truncated": len(rows) < verify_audit_log(source)["records"]}
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    os.replace(temporary, target)
    return {"records": len(rows), "truncated": payload["truncated"], "output": str(target)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="groundrecall-mcp-audit-export")
    parser.add_argument("audit_log")
    parser.add_argument("output")
    parser.add_argument("--max-records", type=int, default=DEFAULT_MAX_RECORDS)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--include-identities", action="store_true", help="Include subject/realm fields; omitted by default.")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = export_audit(args.audit_log, args.output, max_records=args.max_records, max_bytes=args.max_bytes, include_identities=args.include_identities)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    if args.as_json:
        print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    else:
        print(f"OK: records={summary['records']} truncated={summary['truncated']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
