#!/usr/bin/env python3
"""Cross-platform wheel install/upgrade smoke check for GroundRecall.

Run from any directory with Python 3.10+:

    python scripts/install_upgrade_smoke.py

The script builds an older baseline wheel and a current wheel, upgrades the
baseline in a temporary virtual environment whose path contains spaces and
Unicode, checks every declared console entry point, and verifies that a
synthetic source note is discoverable in unified search but absent from
canonical-only search. All generated data is temporary and synthetic.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Sequence


CONSOLE_SCRIPTS = (
    "groundrecall",
    "groundrecall-federation-broker",
    "groundrecall-broker",
    "groundrecall-mcp",
    "groundrecall-mcp-http",
    "groundrecall-mcp-audit-verify",
    "groundrecall-mcp-audit-manifest",
    "groundrecall-mcp-audit-export",
    "groundrecall-handoff-promotion-operator",
    "groundrecall-handoff-discover",
    "groundrecall-workspace-inventory",
    "groundrecall-reconcile-imports",
)

SYNTHETIC_TOKEN = "groundrecall-smoke-synthetic-needle-7f9e"


def run(command: Sequence[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    printable = " ".join(repr(part) for part in command)
    print(f"+ {printable}")
    result = subprocess.run(
        list(command),
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=300,
    )
    if result.returncode:
        print(result.stdout, file=sys.stderr)
        raise RuntimeError(f"Command failed with exit code {result.returncode}: {printable}")
    if result.stdout.strip():
        print(result.stdout.rstrip())
    return result.stdout


def venv_paths(venv: Path) -> tuple[Path, Path, str]:
    if os.name == "nt":
        scripts_dir = venv / "Scripts"
        python = scripts_dir / "python.exe"
        path_prefix = str(scripts_dir)
    else:
        scripts_dir = venv / "bin"
        python = scripts_dir / "python"
        path_prefix = str(scripts_dir)
    if not python.is_file():
        raise RuntimeError(f"Virtual environment Python was not created: {python}")
    return scripts_dir, python, path_prefix


def console_path(name: str, scripts_dir: Path) -> Path:
    candidates = (scripts_dir / f"{name}.exe", scripts_dir / name, scripts_dir / f"{name}.cmd")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError(f"Installed console entry point is missing: {name}")


def workspace_manifest(workspace_id: str) -> dict[str, object]:
    return {
        "schema_version": "groundrecall.workspace.v1",
        "workspace_id": workspace_id,
        "canonical_store": "store",
        "imports": "imports",
        "source_notes": "source-notes",
        "indexes": {
            "notes": ".index/groundrecall-notes.sqlite",
            "canonical": "store/.index/groundrecall-search.sqlite",
            "unified": ".index/groundrecall-unified.sqlite",
        },
        "private_runs": "logs",
    }


def check_retrieval(groundrecall: Path, workspace: Path, *, cwd: Path, env: dict[str, str]) -> None:
    unified = run(
        [str(groundrecall), "index", str(workspace), SYNTHETIC_TOKEN, "--scope", "unified", "--limit", "10"],
        cwd=cwd,
        env=env,
    )
    unified_payload = json.loads(unified)
    unified_matches = unified_payload.get("matches", [])
    expected_note = str(workspace / "source-notes" / "smoke-project.md")
    if not any(
        match.get("kind") == "source_note"
        and match.get("metadata", {}).get("source_path") == expected_note
        for match in unified_matches
    ):
        raise RuntimeError("Unified search did not return the synthetic source note")

    canonical = run(
        [str(groundrecall), "index", str(workspace), SYNTHETIC_TOKEN, "--scope", "canonical", "--limit", "10"],
        cwd=cwd,
        env=env,
    )
    canonical_payload = json.loads(canonical)
    if any(match.get("kind") == "source_note" for match in canonical_payload.get("matches", [])):
        raise RuntimeError("Canonical-only search unexpectedly returned a source note")


def tree_snapshot(root: Path, *, omit_manifest: bool = False) -> tuple[set[str], dict[str, bytes]]:
    directories: set[str] = set()
    files: dict[str, bytes] = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if omit_manifest and relative == ".groundrecall-store.json":
            continue
        if path.is_dir():
            directories.add(relative)
        elif path.is_file():
            files[relative] = path.read_bytes()
        else:
            raise RuntimeError(f"Synthetic store contains an unexpected entry: {relative}")
    return directories, files


def check_store_upgrade(
    installed_cli: Path,
    venv_python: Path,
    workspace: Path,
    temp_root: Path,
    *,
    cwd: Path,
    env: dict[str, str],
) -> None:
    store = workspace / "store"
    manifest_path = store / ".groundrecall-store.json"
    backup = temp_root / "external verified backups" / "synthetic-store-before-update"

    create_synthetic_store = (
        "import sys; "
        "from groundrecall.models import ClaimRecord, RelationRecord; "
        "from groundrecall.store import GroundRecallStore; "
        "store = GroundRecallStore(sys.argv[1]); "
        "store.save_claim(ClaimRecord(claim_id='smoke-claim', "
        "claim_text='Synthetic store-format upgrade preservation record.', "
        "future_extension={'smoke': 'preserved'})); "
        "store.save_relation(RelationRecord(relation_id='smoke-relation', "
        "source_id='smoke-concept-a', target_id='smoke-concept-b', "
        "relation_type='related_to'))"
    )
    run([str(venv_python), "-c", create_synthetic_store, str(store)], cwd=cwd, env=env)

    if manifest_path.exists():
        raise RuntimeError("Synthetic legacy store unexpectedly has a format manifest")
    before = tree_snapshot(store)
    check_output = run(
        [str(installed_cli), "update", str(store), "--check"],
        cwd=cwd,
        env=env,
    )
    check_payload = json.loads(check_output)
    if (
        check_payload.get("current_store_format_version") != 0
        or check_payload.get("update_available") is not True
        or check_payload.get("write_performed") is not False
    ):
        raise RuntimeError("`groundrecall update --check` did not report a read-only pending update")
    if tree_snapshot(store) != before or manifest_path.exists():
        raise RuntimeError("`groundrecall update --check` modified the synthetic legacy store")

    apply_output = run(
        [
            str(installed_cli),
            "update",
            str(store),
            "--apply",
            "--backup",
            str(backup),
            "--confirm-stopped",
        ],
        cwd=cwd,
        env=env,
    )
    apply_payload = json.loads(apply_output)
    if (
        apply_payload.get("updated") is not True
        or apply_payload.get("canonical_records_rewritten") is not False
        or Path(apply_payload.get("backup_path", "")).resolve() != backup.resolve()
    ):
        raise RuntimeError("`groundrecall update --apply` did not report the expected verified update")
    if not backup.is_dir() or backup == store or backup.is_relative_to(store):
        raise RuntimeError("Store update did not create a separate external backup")
    if tree_snapshot(backup) != before:
        raise RuntimeError("External backup does not match the pre-update synthetic store")
    if tree_snapshot(store, omit_manifest=True) != before:
        raise RuntimeError("Store update changed pre-existing synthetic records or files")
    if not (store / "claims" / "smoke-claim.json").is_file():
        raise RuntimeError("Synthetic claim record is missing after update")
    if not (store / "relations" / "smoke-relation.json").is_file():
        raise RuntimeError("Synthetic relation record is missing after update")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "groundrecall.store-manifest.v1" or manifest.get("store_format_version") != 1:
        raise RuntimeError("Store update wrote an unexpected format manifest")

    rollback_output = run(
        [
            str(installed_cli),
            "update",
            str(store),
            "--rollback-from",
            str(backup),
            "--confirm-stopped",
        ],
        cwd=cwd,
        env=env,
    )
    rollback_payload = json.loads(rollback_output)
    if rollback_payload.get("rolled_back") is not True or rollback_payload.get("store_format_version") != 0:
        raise RuntimeError("`groundrecall update --rollback-from` did not report the expected rollback")
    if manifest_path.exists() or tree_snapshot(store) != before:
        raise RuntimeError("Rollback did not restore the exact pre-update synthetic store")
    if not backup.is_dir() or tree_snapshot(backup) != before:
        raise RuntimeError("Rollback removed or changed the external verified backup")


def build_wheel(python: Path, source: Path, wheel_dir: Path, *, cwd: Path) -> Path:
    wheel_dir.mkdir(parents=True, exist_ok=True)
    run(
        [
            str(python),
            "-m",
            "pip",
            "wheel",
            "--disable-pip-version-check",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheel_dir),
            str(source),
        ],
        cwd=cwd,
    )
    wheels = sorted(wheel_dir.glob("groundrecall-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"Expected one GroundRecall wheel in {wheel_dir}, found {len(wheels)}")
    return wheels[0]


def main() -> int:
    if sys.version_info < (3, 10):
        raise RuntimeError("GroundRecall requires Python 3.10 or newer")

    project_root = Path(__file__).resolve().parents[1]
    if not (project_root / "pyproject.toml").is_file():
        raise RuntimeError(f"Could not locate GroundRecall checkout at {project_root}")

    with tempfile.TemporaryDirectory(prefix="GroundRecall install smoke ") as temporary:
        temp_root = Path(temporary)
        install_parent = temp_root / "Venv with spaces and Unicode Ω"
        install_parent.mkdir()
        venv_dir = install_parent / "installed environment"
        wheel_dir = temp_root / "built wheels"
        baseline_source = temp_root / "baseline source"
        baseline_source.mkdir()
        for filename in ("pyproject.toml", "README.md"):
            shutil.copy2(project_root / filename, baseline_source / filename)
        shutil.copytree(
            project_root / "src",
            baseline_source / "src",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        baseline_pyproject_path = baseline_source / "pyproject.toml"
        baseline_pyproject = baseline_pyproject_path.read_text(encoding="utf-8")
        baseline_pyproject, replacements = re.subn(
            r'(?m)^version = "0\.1\.0a2"$',
            'version = "0.1.0a1"',
            baseline_pyproject,
            count=1,
        )
        if replacements != 1:
            raise RuntimeError("Could not create the synthetic 0.1.0a1 baseline package")
        baseline_pyproject_path.write_text(baseline_pyproject, encoding="utf-8")

        baseline_wheel = build_wheel(
            Path(sys.executable),
            baseline_source,
            temp_root / "baseline wheels",
            cwd=project_root,
        )
        current_wheel = build_wheel(
            Path(sys.executable),
            project_root,
            wheel_dir,
            cwd=project_root,
        )

        run(
            [sys.executable, "-m", "venv", "--system-site-packages", str(venv_dir)],
            cwd=project_root,
        )
        scripts_dir, venv_python, scripts_path = venv_paths(venv_dir)
        child_env = os.environ.copy()
        child_env["PATH"] = scripts_path + os.pathsep + child_env.get("PATH", "")
        child_env["PYTHONNOUSERSITE"] = "1"

        run(
            [
                str(venv_python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--ignore-installed",
                "--no-deps",
                str(baseline_wheel),
            ],
            cwd=project_root,
            env=child_env,
        )

        baseline_version = run(
            [
                str(venv_python),
                "-c",
                "from importlib.metadata import version; print(version('groundrecall'))",
            ],
            cwd=project_root,
            env=child_env,
        ).strip()
        if baseline_version != "0.1.0a1":
            raise RuntimeError(f"Synthetic baseline install ended at unexpected version: {baseline_version}")

        # Install the current wheel over an older package version.
        run(
            [
                str(venv_python),
                "-m",
                "pip",
                "install",
                "--upgrade",
                "--disable-pip-version-check",
                "--no-deps",
                str(current_wheel),
            ],
            cwd=project_root,
            env=child_env,
        )
        installed_version = run(
            [
                str(venv_python),
                "-c",
                "from importlib.metadata import version; print(version('groundrecall'))",
            ],
            cwd=project_root,
            env=child_env,
        ).strip()
        if installed_version != "0.1.0a2":
            raise RuntimeError(f"Package upgrade ended at unexpected version: {installed_version}")

        installed_cli = console_path("groundrecall", scripts_dir)
        run([str(installed_cli), "--help"], cwd=project_root, env=child_env)
        for entry_point in CONSOLE_SCRIPTS:
            run([str(console_path(entry_point, scripts_dir)), "--help"], cwd=project_root, env=child_env)

        workspace = temp_root / "Synthetic workspace"
        (workspace / "source-notes").mkdir(parents=True)
        (workspace / "store").mkdir()
        (workspace / "imports").mkdir()
        (workspace / "logs").mkdir()
        (workspace / "workspace.json").write_text(
            json.dumps(workspace_manifest("groundrecall-install-smoke"), indent=2) + "\n",
            encoding="utf-8",
        )
        (workspace / "source-notes" / "smoke-project.md").write_text(
            "# Synthetic smoke note\n\n"
            f"This synthetic install-check note contains {SYNTHETIC_TOKEN}.\n",
            encoding="utf-8",
        )
        check_retrieval(installed_cli, workspace, cwd=project_root, env=child_env)
        check_store_upgrade(installed_cli, venv_python, workspace, temp_root, cwd=project_root, env=child_env)

    print("GroundRecall install/upgrade smoke check passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.SubprocessError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
