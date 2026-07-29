import json
import sys
from pathlib import Path

from groundrecall.cli import main as groundrecall_cli_main
from groundrecall.export import export_canonical_bundle
from groundrecall.ingest import run_groundrecall_import
from groundrecall.inspect import inspect_store
from groundrecall.models import ClaimRecord, ConceptRecord, ProvenanceRecord, RelationRecord
from groundrecall.policy_coverage import build_policy_coverage_report
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


def _write_static_policy_config(path: Path, *, decision: str, policy_id: str = "cli.query.policy.test") -> Path:
    path.write_text(
        "\n".join(
            [
                "schema_version: groundrecall.policy_plugins.v1",
                f"policy_id: {policy_id}",
                "providers:",
                "  - type: static",
                f"    policy_id: {policy_id}.provider",
                f"    default_decision: {decision}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


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
    store = GroundRecallStore(store_dir)
    store.save_concept(
        ConceptRecord(
            concept_id="concept::rejected-diagnostic-node",
            title="Rejected Diagnostic Node",
            current_status="rejected",
        )
    )
    store.save_relation(
        RelationRecord(
            relation_id="rel_rejected_diagnostic_edge",
            source_id="concept::rejected-diagnostic-node",
            target_id="concept::channel-capacity",
            relation_type="mentions_topic",
            provenance=ProvenanceRecord(support_kind="inferred", grounding_status="partially_grounded"),
            current_status="rejected",
        )
    )

    payload = inspect_store(store_dir, out_path=tmp_path / "inspect-graph.json", include_graph=True)

    assert (tmp_path / "inspect-graph.json").exists()
    assert "graph_diagnostics" in payload
    assert payload["graph_diagnostics"]["summary"]["concept_count"] == payload["concept_count"] - 1
    assert payload["graph_diagnostics"]["summary"]["relation_count"] == payload["relation_count"] - 1
    assert payload["graph_diagnostics"]["summary"]["connected_component_count"] >= 1


def test_policy_coverage_report_summarizes_enforcement_surfaces() -> None:
    payload = build_policy_coverage_report()

    assert payload["schema_version"] == "groundrecall.policy_coverage.v1"
    assert payload["summary"]["route_count"] >= 1
    assert payload["summary"]["covered_route_count"] >= 1
    assert payload["summary"]["partial_route_count"] == 15
    assert payload["summary"]["covered_durable_mutation_route_count"] >= 1
    assert not any(item["route_id"] == "cli.import" for item in payload["open_items"])
    assert not any(item["route_id"] == "cli.graph_augment.write_candidates" for item in payload["open_items"])
    assert any(item["route_id"] == "cli.review.quorum" and item["status"] == "partial" for item in payload["open_items"])
    assert any(item["route_id"] == "cli.review.feedback_bundle" and item["status"] == "partial" for item in payload["open_items"])
    assert any(item["route_id"] == "python_api.custody.record_event" and item["status"] == "partial" for item in payload["open_items"])
    assert any(item["route_id"] == "cli.views.orientation" and item["status"] == "partial" for item in payload["open_items"])
    assert any(item["route_id"] == "cli.views.impact" and item["status"] == "partial" for item in payload["open_items"])
    assert any(item["route_id"] == "cli.views.governance" and item["status"] == "partial" for item in payload["open_items"])
    assert any(item["route_id"] == "cli.views.stewardship" and item["status"] == "partial" for item in payload["open_items"])
    assert any(item["route_id"] == "cli.release.pack" and item["status"] == "partial" for item in payload["open_items"])
    assert any(item["route_id"] == "cli.release.withdraw" and item["status"] == "partial" for item in payload["open_items"])
    assert any(item["route_id"] == "mcp.prior_work_review" and item["status"] == "partial" for item in payload["open_items"])
    assert any(item["route_id"] == "mcp.catalog_discovery" and item["status"] == "partial" for item in payload["open_items"])
    assert any(item["route_id"] == "mcp.subscription_status" and item["status"] == "partial" for item in payload["open_items"])
    assert any(item["route_id"] == "mcp.impact_report" and item["status"] == "partial" for item in payload["open_items"])
    assert any(item["route_id"] == "mcp.stewardship_orphans" and item["status"] == "partial" for item in payload["open_items"])
    assert any(item["route_id"] == "mcp.propose_contribution" and item["status"] == "partial" for item in payload["open_items"])
    assert any(item["route_id"] == "cli.promote" and item["status"] == "covered" for item in payload["routes"])
    assert any(item["route_id"] == "cli.import" and item["status"] == "covered" for item in payload["routes"])
    assert any(item["route_id"] == "cli.graph_augment.write_candidates" and item["status"] == "covered" for item in payload["routes"])


def test_groundrecall_inspect_can_include_policy_coverage(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    GroundRecallStore(store_dir)

    payload = inspect_store(store_dir, out_path=tmp_path / "inspect-policy.json", include_policy_coverage=True)

    assert (tmp_path / "inspect-policy.json").exists()
    assert payload["policy_coverage"]["schema_version"] == "groundrecall.policy_coverage.v1"
    assert payload["policy_coverage"]["summary"]["covered_route_count"] >= 1


def test_groundrecall_inspect_can_include_compact_policy_coverage(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    GroundRecallStore(store_dir)

    payload = inspect_store(store_dir, compact_policy_coverage=True)

    assert payload["policy_coverage"]["summary"]["covered_route_count"] >= 1
    assert "routes" not in payload["policy_coverage"]


def test_graph_diagnostics_separate_source_family_from_semantic_edges(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_concept(
        ConceptRecord(
            concept_id="concept::alpha",
            title="Alpha",
            current_status="reviewed",
        )
    )
    store.save_concept(
        ConceptRecord(
            concept_id="concept::beta",
            title="Beta",
            current_status="reviewed",
        )
    )
    store.save_relation(
        RelationRecord(
            relation_id="rel_source_family",
            source_id="concept::alpha",
            target_id="concept::beta",
            relation_type="same_source_family",
            provenance=ProvenanceRecord(support_kind="inferred", grounding_status="partially_grounded"),
            current_status="triaged",
        )
    )
    store.save_relation(
        RelationRecord(
            relation_id="rel_observation_support",
            source_id="obs_alpha",
            target_id="claim_alpha",
            relation_type="observation_supports_claim",
            provenance=ProvenanceRecord(support_kind="inferred", grounding_status="partially_grounded"),
            current_status="triaged",
        )
    )
    store.save_relation(
        RelationRecord(
            relation_id="rel_artifact_observation",
            source_id="art_alpha",
            target_id="obs_alpha",
            relation_type="artifact_contains_observation",
            provenance=ProvenanceRecord(support_kind="inferred", grounding_status="partially_grounded"),
            current_status="triaged",
        )
    )
    store.save_relation(
        RelationRecord(
            relation_id="rel_source_fragment",
            source_id="src_alpha",
            target_id="frag_alpha",
            relation_type="source_contains_fragment",
            provenance=ProvenanceRecord(support_kind="inferred", grounding_status="partially_grounded"),
            current_status="triaged",
        )
    )
    store.save_relation(
        RelationRecord(
            relation_id="rel_fragment_claim",
            source_id="frag_alpha",
            target_id="claim_alpha",
            relation_type="fragment_supports_claim",
            provenance=ProvenanceRecord(support_kind="inferred", grounding_status="partially_grounded"),
            current_status="triaged",
        )
    )

    payload = inspect_store(store.base_dir, include_graph=True)
    summary = payload["graph_diagnostics"]["summary"]

    assert summary["total_relation_count"] == 5
    assert summary["provenance_relation_count"] == 5
    assert summary["relation_count"] == 0
    assert summary["candidate_provenance_relation_count"] == 5
    assert summary["candidate_semantic_relation_count"] == 0
    assert summary["connected_component_count"] == 2
    assert payload["graph_diagnostics"]["relation_quality"]["inferred_relation_count"] == 0
    assert payload["graph_diagnostics"]["provenance_relation_quality"]["inferred_relation_count"] == 5


def test_graph_diagnostics_separate_reviewed_and_candidate_semantic_edges(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_concept(ConceptRecord(concept_id="concept::alpha", title="Alpha", current_status="reviewed"))
    store.save_concept(ConceptRecord(concept_id="concept::beta", title="Beta", current_status="reviewed"))
    store.save_relation(
        RelationRecord(
            relation_id="rel_reviewed",
            source_id="concept::alpha",
            target_id="concept::beta",
            relation_type="related_topic",
            provenance=ProvenanceRecord(support_kind="direct_source", grounding_status="grounded"),
            current_status="reviewed",
        )
    )
    store.save_relation(
        RelationRecord(
            relation_id="rel_candidate",
            source_id="claim_definition",
            target_id="concept::alpha",
            relation_type="claim_defines_concept",
            provenance=ProvenanceRecord(support_kind="inferred", grounding_status="partially_grounded"),
            current_status="triaged",
        )
    )

    payload = inspect_store(store.base_dir, include_graph=True)
    summary = payload["graph_diagnostics"]["summary"]
    density = payload["graph_diagnostics"]["density"]

    assert summary["relation_count"] == 2
    assert summary["reviewed_semantic_relation_count"] == 1
    assert summary["candidate_semantic_relation_count"] == 1
    assert summary["provenance_relation_count"] == 0
    assert density["semantic_reviewed_relation_count"] == 1
    assert density["semantic_candidate_relation_count"] == 1


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


def test_groundrecall_cli_inspect_policy_coverage_dispatches(tmp_path: Path, capsys) -> None:
    store_dir = tmp_path / "store"
    GroundRecallStore(store_dir)

    original_argv = sys.argv
    try:
        sys.argv = ["groundrecall.cli", "inspect", str(store_dir), "--policy-coverage"]
        groundrecall_cli_main()
    finally:
        sys.argv = original_argv

    output = capsys.readouterr().out
    assert '"policy_coverage"' in output
    assert '"schema_version": "groundrecall.policy_coverage.v1"' in output
    assert '"routes"' in output


def test_groundrecall_cli_inspect_policy_coverage_summary_dispatches(tmp_path: Path, capsys) -> None:
    store_dir = tmp_path / "store"
    GroundRecallStore(store_dir)

    original_argv = sys.argv
    try:
        sys.argv = ["groundrecall.cli", "inspect", str(store_dir), "--policy-coverage-summary"]
        groundrecall_cli_main()
    finally:
        sys.argv = original_argv

    output = capsys.readouterr().out
    assert '"policy_coverage"' in output
    assert '"covered_route_count"' in output
    assert '"routes"' not in output


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


def test_groundrecall_cli_inspect_graph_summary_dispatches(tmp_path: Path, capsys) -> None:
    source_root = _build_llmwiki_fixture(tmp_path / "llmwiki")
    import_result = run_groundrecall_import(source_root, out_root=tmp_path / "imports", mode="quick", import_id="fixture-import")
    store_dir = tmp_path / "store"
    promote_import_to_store(import_result.out_dir, store_dir)

    original_argv = sys.argv
    try:
        sys.argv = ["groundrecall.cli", "inspect", str(store_dir), "--graph-summary"]
        groundrecall_cli_main()
    finally:
        sys.argv = original_argv

    output = capsys.readouterr().out
    assert '"graph_diagnostics"' in output
    assert '"largest_components"' in output
    assert '"components"' not in output


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


def test_groundrecall_cli_query_soft_policy_plugin_attaches_decision(tmp_path: Path, capsys) -> None:
    source_root = _build_llmwiki_fixture(tmp_path / "llmwiki")
    import_result = run_groundrecall_import(source_root, out_root=tmp_path / "imports", mode="quick", import_id="fixture-import")
    store_dir = tmp_path / "store"
    promote_import_to_store(import_result.out_dir, store_dir)
    policy_config = _write_static_policy_config(tmp_path / "policy.yaml", decision="soft_gate")

    original_argv = sys.argv
    try:
        sys.argv = [
            "groundrecall.cli",
            "query",
            str(store_dir),
            "channel-capacity",
            "--kind",
            "graph",
            "--policy-plugins",
            str(policy_config),
            "--policy-subject-id",
            "agent-1",
        ]
        groundrecall_cli_main()
    finally:
        sys.argv = original_argv

    payload = json.loads(capsys.readouterr().out)
    assert payload["bundle_kind"] == "groundrecall_graph_bundle"
    assert payload["policy_plugin_decision"]["decision"] == "soft_gate"
    assert payload["policy_plugin_decision"]["subject_id"] == "agent-1"


def test_groundrecall_cli_query_hard_policy_plugin_blocks_before_store_access(tmp_path: Path, capsys) -> None:
    policy_config = _write_static_policy_config(tmp_path / "policy.yaml", decision="hard_gate")
    missing_store = tmp_path / "missing-store"

    original_argv = sys.argv
    try:
        sys.argv = [
            "groundrecall.cli",
            "query",
            str(missing_store),
            "anything",
            "--kind",
            "graph",
            "--policy-plugins",
            str(policy_config),
            "--policy-subject-id",
            "agent-1",
        ]
        groundrecall_cli_main()
    finally:
        sys.argv = original_argv

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["blocked_by_policy"] is True
    assert payload["policy_plugin_decision"]["decision"] == "hard_gate"
    assert payload["policy_plugin_decision"]["subject_id"] == "agent-1"
    assert not missing_store.exists()


def test_groundrecall_cli_query_graph_search_dispatches(tmp_path: Path, capsys) -> None:
    source_root = _build_llmwiki_fixture(tmp_path / "llmwiki")
    import_result = run_groundrecall_import(source_root, out_root=tmp_path / "imports", mode="quick", import_id="fixture-import")
    store_dir = tmp_path / "store"
    promote_import_to_store(import_result.out_dir, store_dir)

    original_argv = sys.argv
    try:
        sys.argv = [
            "groundrecall.cli",
            "query",
            str(store_dir),
            "reliable rate",
            "--kind",
            "graph-search",
            "--graph-limit",
            "1",
        ]
        groundrecall_cli_main()
    finally:
        sys.argv = original_argv

    output = capsys.readouterr().out
    assert '"bundle_kind": "groundrecall_graph_search_bundle"' in output
    assert '"root_concepts"' in output
    assert '"graph_bundles"' in output


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
