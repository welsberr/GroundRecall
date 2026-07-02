import sys
from pathlib import Path

from groundrecall.cli import main as groundrecall_cli_main
from groundrecall.export import export_canonical_bundle
from groundrecall.ingest import run_groundrecall_import
from groundrecall.inspect import inspect_store
from groundrecall.models import ClaimRecord
from groundrecall.query import query_concept
from groundrecall.store import GroundRecallStore
from groundrecall.lint import lint_import_directory
from groundrecall.promotion import promote_import_to_store


def _build_llmwiki_fixture(root: Path) -> Path:
    (root / "wiki").mkdir(parents=True)
    (root / "raw").mkdir()
    (root / "wiki" / "channel-capacity.md").write_text(
        "# Channel Capacity\n\n"
        "- Reliable rate upper bound for a noisy channel.\n\n"
        "See also [[Shannon Entropy]].\n",
        encoding="utf-8",
    )
    (root / "raw" / "notes.md").write_text(
        "Speculation: Capacity may depend on constraints.\n",
        encoding="utf-8",
    )
    return root


def test_groundrecall_namespace_reexports_core_functions() -> None:
    assert run_groundrecall_import.__module__ == "groundrecall.ingest"
    assert query_concept.__module__ == "groundrecall.query"
    assert export_canonical_bundle.__module__ == "groundrecall.export"
    assert lint_import_directory.__module__ == "groundrecall.lint"
    assert promote_import_to_store.__module__ == "groundrecall.promotion"
    assert GroundRecallStore.__module__ == "groundrecall.store"
    assert ClaimRecord.__module__ == "groundrecall.models"


def test_groundrecall_inspect_summarizes_store(tmp_path: Path) -> None:
    source_root = _build_llmwiki_fixture(tmp_path / "llmwiki")
    import_result = run_groundrecall_import(source_root, out_root=tmp_path / "imports", mode="quick", import_id="fixture-import")
    store_dir = tmp_path / "store"
    promote_import_to_store(import_result.out_dir, store_dir)

    payload = inspect_store(store_dir, out_path=tmp_path / "inspect.json")

    assert (tmp_path / "inspect.json").exists()
    assert payload["claim_count"] >= 1
    assert payload["concept_count"] >= 1
    assert payload["snapshot_count"] >= 1


def test_groundrecall_inspect_can_include_graph_diagnostics(tmp_path: Path) -> None:
    source_root = _build_llmwiki_fixture(tmp_path / "llmwiki")
    import_result = run_groundrecall_import(source_root, out_root=tmp_path / "imports", mode="quick", import_id="fixture-import")
    store_dir = tmp_path / "store"
    promote_import_to_store(import_result.out_dir, store_dir)

    payload = inspect_store(store_dir, out_path=tmp_path / "inspect-graph.json", include_graph=True)

    assert (tmp_path / "inspect-graph.json").exists()
    assert "graph_diagnostics" in payload
    assert payload["graph_diagnostics"]["summary"]["concept_count"] == payload["concept_count"]
    assert payload["graph_diagnostics"]["summary"]["relation_count"] == payload["relation_count"]
    assert payload["graph_diagnostics"]["summary"]["connected_component_count"] >= 1


def test_groundrecall_cli_inspect_dispatches(tmp_path: Path, capsys) -> None:
    source_root = _build_llmwiki_fixture(tmp_path / "llmwiki")
    import_result = run_groundrecall_import(source_root, out_root=tmp_path / "imports", mode="quick", import_id="fixture-import")
    store_dir = tmp_path / "store"
    promote_import_to_store(import_result.out_dir, store_dir)

    original_argv = sys.argv
    try:
        sys.argv = ["groundrecall.cli", "inspect", str(store_dir)]
        groundrecall_cli_main()
    finally:
        sys.argv = original_argv

    output = capsys.readouterr().out
    assert '"claim_count"' in output
    assert '"concept_count"' in output


def test_groundrecall_cli_inspect_graph_dispatches(tmp_path: Path, capsys) -> None:
    source_root = _build_llmwiki_fixture(tmp_path / "llmwiki")
    import_result = run_groundrecall_import(source_root, out_root=tmp_path / "imports", mode="quick", import_id="fixture-import")
    store_dir = tmp_path / "store"
    promote_import_to_store(import_result.out_dir, store_dir)

    original_argv = sys.argv
    try:
        sys.argv = ["groundrecall.cli", "inspect", str(store_dir), "--graph"]
        groundrecall_cli_main()
    finally:
        sys.argv = original_argv

    output = capsys.readouterr().out
    assert '"graph_diagnostics"' in output
    assert '"connected_component_count"' in output


def test_groundrecall_cli_query_graph_dispatches(tmp_path: Path, capsys) -> None:
    source_root = _build_llmwiki_fixture(tmp_path / "llmwiki")
    import_result = run_groundrecall_import(source_root, out_root=tmp_path / "imports", mode="quick", import_id="fixture-import")
    store_dir = tmp_path / "store"
    promote_import_to_store(import_result.out_dir, store_dir)

    original_argv = sys.argv
    try:
        sys.argv = ["groundrecall.cli", "query", str(store_dir), "channel-capacity", "--kind", "graph"]
        groundrecall_cli_main()
    finally:
        sys.argv = original_argv

    output = capsys.readouterr().out
    assert '"bundle_kind": "groundrecall_graph_bundle"' in output
    assert '"nodes"' in output
    assert '"edges"' in output


def test_groundrecall_cli_export_graph_dispatches(tmp_path: Path, capsys) -> None:
    source_root = _build_llmwiki_fixture(tmp_path / "llmwiki")
    import_result = run_groundrecall_import(source_root, out_root=tmp_path / "imports", mode="quick", import_id="fixture-import")
    store_dir = tmp_path / "store"
    promote_import_to_store(import_result.out_dir, store_dir)
    out_dir = tmp_path / "exports"

    original_argv = sys.argv
    try:
        sys.argv = [
            "groundrecall.cli",
            "export",
            str(store_dir),
            str(out_dir),
            "--graph-concept",
            "channel-capacity",
            "--include-graph-diagnostics",
            "--include-graph-interchange",
        ]
        groundrecall_cli_main()
    finally:
        sys.argv = original_argv

    output = capsys.readouterr().out
    assert '"graph_bundles"' in output
    assert (out_dir / "graph_bundle__channel-capacity.json").exists()
    assert (out_dir / "graph_diagnostics.json").exists()
    assert (out_dir / "graph_interchange.json").exists()
