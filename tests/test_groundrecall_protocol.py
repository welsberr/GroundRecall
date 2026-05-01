from __future__ import annotations

from pathlib import Path

import pytest

from groundrecall.cli import COMMANDS
from groundrecall.protocol import initialize_protocol


def test_protocol_init_writes_host_profile_and_bootstraps(tmp_path: Path) -> None:
    result = initialize_protocol(
        tmp_path,
        host_id="local-dev",
        host_role="development",
        hostname="localbox",
        assistants=["codex", "claude_code"],
    )

    written = {path.name for path in result.written}
    assert "README.md" in written
    assert "ASSISTANT_PROJECT.md" in written
    assert "CODEX_PROJECT.md" in written
    assert "CLAUDE.md" in written
    assert (tmp_path / ".groundrecall" / "source-notes" / "host-profile-local-dev.md").exists()
    assert (tmp_path / ".groundrecall" / "local-inbox").is_dir()
    assert (tmp_path / ".groundrecall" / "remote-inbox").is_dir()

    host_profile = (tmp_path / ".groundrecall" / "source-notes" / "host-profile-local-dev.md").read_text()
    assert "host_id: local-dev" in host_profile
    assert "host_role: development" in host_profile
    assert "hostname: localbox" in host_profile
    assert "No-secrets rule" in host_profile

    codex = (tmp_path / "CODEX_PROJECT.md").read_text()
    claude = (tmp_path / "CLAUDE.md").read_text()
    assert "GroundRecall workspace" in codex
    assert "Claude Code export" in claude


def test_protocol_init_does_not_overwrite_without_force(tmp_path: Path) -> None:
    (tmp_path / "CODEX_PROJECT.md").write_text("existing\n", encoding="utf-8")

    result = initialize_protocol(
        tmp_path,
        host_id="remote-prod",
        host_role="production",
        assistants=["codex"],
    )

    assert (tmp_path / "CODEX_PROJECT.md").read_text() == "existing\n"
    assert tmp_path / "CODEX_PROJECT.md" in result.skipped


def test_protocol_init_force_overwrites_existing_bootstrap(tmp_path: Path) -> None:
    (tmp_path / "CODEX_PROJECT.md").write_text("existing\n", encoding="utf-8")

    initialize_protocol(
        tmp_path,
        host_id="remote-prod",
        host_role="production",
        assistants=["codex"],
        force=True,
    )

    assert "host role" in (tmp_path / "CODEX_PROJECT.md").read_text()


def test_protocol_init_rejects_unknown_host_role(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        initialize_protocol(tmp_path, host_id="x", host_role="laptop")


def test_cli_exposes_protocol_init_command() -> None:
    assert "protocol-init" in COMMANDS
