"""Create and verify metadata-only manifests for rotated MCP audit logs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

SCHEMA_VERSION = "groundrecall.mcp_audit_manifest.v1"
DEFAULT_PATTERN = "mcp-access.jsonl*"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(directory: str | os.PathLike[str], *, pattern: str = DEFAULT_PATTERN) -> dict[str, Any]:
    """Return a deterministic metadata manifest for regular files in *directory*.

    File contents are represented only by size and SHA-256; no audit records are
    loaded into memory or copied into the manifest.
    """
    root = Path(directory)
    if not root.is_dir():
        raise ValueError(f"audit directory is not a directory: {root}")
    files = []
    for path in sorted(root.glob(pattern)):
        if path.is_file() and not path.is_symlink():
            files.append({
                "name": path.relative_to(root).as_posix(),
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            })
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "directory": root.name,
        "pattern": pattern,
        "files": files,
    }


def write_manifest(manifest: dict[str, Any], output: str | os.PathLike[str]) -> None:
    """Write a manifest atomically, creating parent directories as needed."""
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    os.replace(temporary, target)


def verify_manifest(manifest_path: str | os.PathLike[str], directory: str | os.PathLike[str]) -> dict[str, Any]:
    """Verify every listed file and the complete matching file set."""
    source = Path(manifest_path)
    root = Path(directory)
    try:
        manifest = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid manifest: {exc}") from exc
    if manifest.get("schema_version") != SCHEMA_VERSION or not isinstance(manifest.get("files"), list):
        raise ValueError("unsupported or malformed manifest")
    pattern = manifest.get("pattern", DEFAULT_PATTERN)
    expected: dict[str, dict[str, Any]] = {}
    for entry in manifest["files"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise ValueError("malformed manifest file entry")
        name = Path(entry["name"])
        if name.is_absolute() or ".." in name.parts or name.as_posix() in expected:
            raise ValueError("unsafe or duplicate manifest file name")
        expected[name.as_posix()] = entry
    actual = {p.relative_to(root).as_posix() for p in root.glob(pattern) if p.is_file() and not p.is_symlink()} if root.is_dir() else set()
    problems = []
    for name, entry in expected.items():
        path = root / name
        if not path.is_file() or path.is_symlink():
            problems.append(f"missing:{name}")
            continue
        if path.stat().st_size != entry.get("size") or _sha256(path) != entry.get("sha256"):
            problems.append(f"mismatch:{name}")
    problems.extend(f"unexpected:{name}" for name in sorted(actual - set(expected)))
    return {"valid": not problems, "files": len(expected), "problems": problems}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="groundrecall-mcp-audit-manifest")
    parser.add_argument("directory", help="directory containing rotated MCP audit logs")
    parser.add_argument("--pattern", default=DEFAULT_PATTERN, help="glob selecting audit files")
    parser.add_argument("--output", help="write a generated manifest to this path")
    parser.add_argument("--verify", metavar="MANIFEST", help="verify an existing manifest")
    parser.add_argument("--json", action="store_true", dest="as_json", help="print a bounded JSON summary")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.verify:
            result = verify_manifest(args.verify, args.directory)
        else:
            result = build_manifest(args.directory, pattern=args.pattern)
            if args.output:
                write_manifest(result, args.output)
            result = {"valid": True, "files": len(result["files"]), "output": args.output}
    except (OSError, ValueError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    if args.as_json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    elif args.verify:
        print("OK: files={files}".format(**result) if result["valid"] else "INVALID: " + ",".join(result["problems"]))
    else:
        print(f"OK: files={result['files']}" + (f" output={result['output']}" if result["output"] else ""))
    return 0 if result["valid"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
