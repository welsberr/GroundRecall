import json
from pathlib import Path

from groundrecall.mcp_audit_manifest import build_manifest, main, verify_manifest, write_manifest


def test_manifest_contains_only_bounded_file_metadata(tmp_path: Path):
    (tmp_path / "mcp-access.jsonl").write_text('{"secret":"must not be copied"}\n', encoding="utf-8")
    (tmp_path / "mcp-access.jsonl-20260810.gz").write_bytes(b"compressed")
    manifest = build_manifest(tmp_path)
    assert len(manifest["files"]) == 2
    assert "secret" not in json.dumps(manifest)
    assert all(set(item) == {"name", "size", "sha256"} for item in manifest["files"])


def test_manifest_verifies_and_detects_changes_and_unexpected_files(tmp_path: Path):
    audit = tmp_path / "mcp-access.jsonl"
    audit.write_text("record\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    write_manifest(build_manifest(tmp_path), manifest_path)
    assert verify_manifest(manifest_path, tmp_path)["valid"]
    audit.write_text("tampered\n", encoding="utf-8")
    assert not verify_manifest(manifest_path, tmp_path)["valid"]
    audit.write_text("record\n", encoding="utf-8")
    (tmp_path / "mcp-access.jsonl-extra").write_text("new\n", encoding="utf-8")
    assert any(p.startswith("unexpected:") for p in verify_manifest(manifest_path, tmp_path)["problems"])


def test_manifest_cli_returns_nonzero_for_mismatch(tmp_path: Path, capsys):
    (tmp_path / "mcp-access.jsonl").write_text("record\n", encoding="utf-8")
    output = tmp_path / "manifest.json"
    assert main([str(tmp_path), "--output", str(output)]) == 0
    assert main([str(tmp_path), "--verify", str(output)]) == 0
    (tmp_path / "mcp-access.jsonl").write_text("changed\n", encoding="utf-8")
    assert main([str(tmp_path), "--verify", str(output)]) == 1
    assert "INVALID" in capsys.readouterr().out
