from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from groundrecall.institutional_conformance import build_institutional_conformance_report
from groundrecall.institutional_federation import build_institutional_federation_capability_report
from groundrecall.policy_coverage import build_policy_coverage_report


SCHEMA_VERSION = "groundrecall.preprint_revision_evidence.v1"
GENERATED_AT = "2026-07-29T00:00:00Z"


def build_revision_evidence(
    *,
    groundrecall_root: str | Path,
    claimwright_root: str | Path,
    demo_output_dir: str | Path,
) -> dict[str, Any]:
    groundrecall_root = Path(groundrecall_root)
    claimwright_root = Path(claimwright_root)
    demo_output_dir = Path(demo_output_dir)
    policy_coverage = build_policy_coverage_report()
    capability = build_institutional_federation_capability_report(compact=True)
    conformance = build_institutional_conformance_report(compact=True)
    demos = _demo_inventory(demo_output_dir)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": GENERATED_AT,
        "purpose": "preprint revision evidence snapshot",
        "claim_boundary": (
            "This artifact records engineering evidence from the local prototype. "
            "It is not production certification, benchmark superiority evidence, "
            "legal compliance evidence, or a complete security proof."
        ),
        "repositories": {
            "groundrecall": _repo_state(
                groundrecall_root,
                ignored_dirty_paths=[_relative_to(demo_output_dir / "revision_evidence_snapshot.json", groundrecall_root)],
            ),
            "claimwright": _repo_state(claimwright_root),
        },
        "groundrecall_reports": {
            "institutional_federation": capability,
            "policy_coverage": {
                "schema_version": policy_coverage["schema_version"],
                "summary": policy_coverage["summary"],
                "status_counts": policy_coverage["status_counts"],
                "surface_counts": policy_coverage["surface_counts"],
                "open_items": policy_coverage["open_items"],
            },
            "institutional_conformance": conformance,
        },
        "completed_preprint_readiness_steps": [
            "refresh institutional demonstrations for IF-06 through IF-14",
            "update implemented-feature summary through IF-14",
            "update claim-to-evidence matrix through IF-14",
            "align limitation language with policy coverage open items",
            "add compact IF-00 through IF-14 status table",
            "perform focused bibliography update without claiming systematic-review completeness",
        ],
        "demo_outputs": demos,
        "paper_ready_next_steps": [
            "run a fresh ClaimWright review against the updated draft and appendices",
            "apply actionable ClaimWright review findings before rendering the next revision",
        ],
        "non_goals_before_revision": [
            "network federation transport",
            "CRDT merge",
            "hosted review UI",
            "production IAM",
            "complete distributed revocation",
            "exceptional erasure execution",
            "comparative benchmark superiority claims",
        ],
    }


def write_revision_evidence(
    output_path: str | Path,
    *,
    groundrecall_root: str | Path,
    claimwright_root: str | Path,
    demo_output_dir: str | Path,
) -> dict[str, Any]:
    payload = build_revision_evidence(
        groundrecall_root=groundrecall_root,
        claimwright_root=claimwright_root,
        demo_output_dir=demo_output_dir,
    )
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _repo_state(root: Path, *, ignored_dirty_paths: list[str | None] | None = None) -> dict[str, Any]:
    ignored = {path for path in (ignored_dirty_paths or []) if path}
    dirty_lines = _dirty_lines(root, ignored_paths=ignored)
    return {
        "path": str(root),
        "head": _git(root, "rev-parse", "--short", "HEAD"),
        "head_subject": _git(root, "log", "-1", "--pretty=%s"),
        "dirty": bool(dirty_lines),
        "ignored_dirty_paths": sorted(ignored),
    }


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def _dirty_lines(root: Path, *, ignored_paths: set[str]) -> list[str]:
    lines = [line for line in _git(root, "status", "--short", "--untracked-files=all").splitlines() if line.strip()]
    return [line for line in lines if _status_path(line) not in ignored_paths]


def _status_path(line: str) -> str:
    path = line[3:].strip()
    if " -> " in path:
        path = path.split(" -> ", 1)[1]
    return path


def _relative_to(path: Path, root: Path) -> str | None:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return None


def _demo_inventory(output_dir: Path) -> dict[str, Any]:
    manifest_path = output_dir / "manifest.json"
    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = sorted(path.name for path in output_dir.glob("*.json") if path.is_file())
    return {
        "path": str(output_dir),
        "manifest_present": manifest_path.exists(),
        "manifest_demo_count": manifest.get("demo_count", 0),
        "manifest_outputs": manifest.get("outputs", []),
        "json_file_count": len(files),
        "json_files": files,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a GroundRecall preprint revision evidence snapshot.")
    parser.add_argument("--groundrecall-root", default=".")
    parser.add_argument("--claimwright-root", default="../ClaimWright")
    parser.add_argument("--demo-output-dir", default="examples/preprint/out")
    parser.add_argument("--output", default="examples/preprint/out/revision_evidence_snapshot.json")
    args = parser.parse_args()
    payload = write_revision_evidence(
        args.output,
        groundrecall_root=args.groundrecall_root,
        claimwright_root=args.claimwright_root,
        demo_output_dir=args.demo_output_dir,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
