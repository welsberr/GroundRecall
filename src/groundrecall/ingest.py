from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import shutil
import socket
import subprocess
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .groundrecall_discovery import DiscoveredArtifact
from .graph_diagnostics import build_graph_diagnostics
from .graph_extraction import extract_heuristic_graph_relations
from .groundrecall_lint import lint_import_directory
from .confidence import apply_adapter_confidence_policy
from .groundrecall_normalizer import (
    ImportContext,
    build_artifact_record,
    build_claim_record,
    build_concept_records,
    build_fragment_record,
    build_observation_record,
    build_relation_records,
    build_concept_standardization_report,
    manifest_record,
    standardize_concept_rows,
)
from .concept_alignment import align_claim_rows_to_seed_concepts
from .groundrecall_review_bridge import export_review_bundle_from_import
from .groundrecall_review_queue import build_review_queue
from .groundrecall_segmenter import SegmentedPage, segment_markdown_artifact
from .groundrecall_source_adapters.base import detect_source_adapter
from .policy import PolicyDecision, PolicyRequest, load_policy_plugins
import groundrecall.groundrecall_source_adapters  # noqa: F401


VALID_MODES = {"archive", "quick", "grounded"}
VALID_GRAPH_EXTRACTION_MODES = {"none", "heuristic"}


class ImportPolicyError(RuntimeError):
    """Raised when a policy plugin blocks import proposal generation."""

    def __init__(self, message: str, *, payload: dict[str, Any]) -> None:
        super().__init__(message)
        self.payload = payload


@dataclass
class ImportResult:
    manifest: dict[str, Any]
    artifacts: list[dict[str, Any]]
    fragments: list[dict[str, Any]]
    observations: list[dict[str, Any]]
    claims: list[dict[str, Any]]
    concepts: list[dict[str, Any]]
    relations: list[dict[str, Any]]
    out_dir: Path


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_import_id(source_root: Path) -> str:
    stem = source_root.name.lower().replace("_", "-")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stem}-{stamp}"


def _portable_source_root_ref(source_path: Path, output_root: Path) -> tuple[str, str]:
    anchor = output_root.resolve().parent
    if source_path.is_relative_to(anchor):
        relative = source_path.relative_to(anchor)
        if relative == Path("."):
            return source_path.name, "source_label"
        return relative.as_posix(), "output_root_parent_relative"
    return source_path.name, "source_label"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    text = "\n".join(json.dumps(row, sort_keys=True) for row in rows)
    if text:
        text += "\n"
    path.write_text(text, encoding="utf-8")


def _append_import_policy_audit_event(
    audit_log_path: str | Path | None,
    *,
    action: str,
    decision: str,
    request: PolicyRequest,
    policy_decision: PolicyDecision,
) -> None:
    if audit_log_path is None:
        return
    recorded_at = _timestamp()
    basis = f"{action}:{decision}:{request.subject_id}:{request.decision_point}:{recorded_at}:{policy_decision.policy_id}"
    payload = {
        "schema_version": "groundrecall.import_policy_audit.v1",
        "event_id": f"import-policy-audit::{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}",
        "recorded_at": recorded_at,
        "action": action,
        "decision": decision,
        "subject_id": request.subject_id,
        "decision_point": request.decision_point,
        "durable_memory_change": request.durable_memory_change,
        "metadata": dict(request.metadata),
        "policy_plugin_decision": policy_decision.model_dump(mode="json"),
    }
    target = Path(audit_log_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _evaluate_import_policy(
    policy_plugins_path: str | Path | None,
    *,
    subject_id: str,
    import_id: str,
    mode: str,
    source_root: str,
    source_root_kind: str,
    source_adapter: str,
    import_intent: str,
    graph_extraction_mode: str,
    audit_log_path: str | Path | None = None,
) -> PolicyDecision | None:
    if policy_plugins_path is None:
        return None
    provider = load_policy_plugins(policy_plugins_path)
    request = PolicyRequest(
        decision_point="propose",
        subject_id=subject_id,
        action="run_groundrecall_import",
        record_kind="import",
        record_id=import_id,
        durable_memory_change=True,
        metadata={
            "import_id": import_id,
            "mode": mode,
            "source_root": source_root,
            "source_root_kind": source_root_kind,
            "source_adapter": source_adapter,
            "import_intent": import_intent,
            "graph_extraction_mode": graph_extraction_mode,
        },
    )
    decision = provider.evaluate(request)
    if decision.decision in {"deny", "hard_gate"}:
        _append_import_policy_audit_event(
            audit_log_path,
            action="run_groundrecall_import",
            decision="blocked",
            request=request,
            policy_decision=decision,
        )
        raise ImportPolicyError(
            "Policy plugin blocked import proposal generation.",
            payload={
                "operation": "run_groundrecall_import",
                "blocked_by_policy": True,
                "policy_plugin_decision": decision.model_dump(mode="json"),
            },
        )
    _append_import_policy_audit_event(
        audit_log_path,
        action="run_groundrecall_import",
        decision="preflight_allowed",
        request=request,
        policy_decision=decision,
    )
    return decision


def _dedupe_by_key(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    unique: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for row in rows:
        unique.setdefault(str(row[key]), row)
    return list(unique.values())


def _convert_tex_to_markdown(path: Path) -> str | None:
    pandoc = shutil.which("pandoc")
    if pandoc is None:
        return None
    result = subprocess.run(
        [pandoc, "-f", "latex", "-t", "gfm", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    markdown = result.stdout.strip()
    return markdown or None


def _segment_artifact(artifact: DiscoveredArtifact) -> SegmentedPage | None:
    if not artifact.is_text:
        return None
    suffix = artifact.path.suffix.lower()
    if suffix not in {".md", ".markdown", ".txt", ".tex", ".log"}:
        return None
    if suffix == ".tex":
        converted = _convert_tex_to_markdown(artifact.path)
        if converted is not None:
            return segment_markdown_artifact(artifact, text=converted)
    return segment_markdown_artifact(artifact)


def _normalize_graph_extraction_mode(value: str | bool | None) -> str:
    if value is True:
        return "heuristic"
    if value in {False, None, ""}:
        return "none"
    mode = str(value)
    if mode not in VALID_GRAPH_EXTRACTION_MODES:
        raise ValueError(f"Unsupported graph extraction mode: {mode}")
    return mode


def run_groundrecall_import(
    source_root: str | Path,
    out_root: str | Path | None = None,
    mode: str = "quick",
    import_id: str | None = None,
    machine_id: str | None = None,
    agent_id: str = "groundrecall.ingest",
    concept_seed_store: str | Path | None = None,
    concept_alignment_threshold: float = 0.55,
    extract_graph: str | bool | None = "none",
    policy_plugins_path: str | Path | None = None,
    policy_subject_id: str = "",
    audit_log_path: str | Path | None = None,
) -> ImportResult:
    source_path = Path(source_root).resolve()
    if mode not in VALID_MODES:
        raise ValueError(f"Unsupported import mode: {mode}")
    graph_extraction_mode = _normalize_graph_extraction_mode(extract_graph)
    adapter = detect_source_adapter(source_path)
    discovered = adapter.discover(source_path)
    artifacts = [
        DiscoveredArtifact(
            path=item.path,
            relative_path=item.relative_path,
            artifact_kind=item.artifact_kind,
            is_text=item.is_text,
        )
        for item in discovered
    ]
    actual_import_id = import_id or _default_import_id(source_path)
    output_root = Path(out_root) if out_root else source_path / "imports"
    source_root_ref, source_root_kind = _portable_source_root_ref(source_path, output_root)
    output_dir = output_root / actual_import_id
    policy_decision = _evaluate_import_policy(
        policy_plugins_path,
        subject_id=policy_subject_id or agent_id,
        import_id=actual_import_id,
        mode=mode,
        source_root=source_root_ref,
        source_root_kind=source_root_kind,
        source_adapter=adapter.name,
        import_intent=adapter.import_intent(),
        graph_extraction_mode=graph_extraction_mode,
        audit_log_path=audit_log_path,
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    context = ImportContext(
        import_id=actual_import_id,
        import_mode=mode,
        machine_id=machine_id or socket.gethostname(),
        agent_id=agent_id,
        source_root=source_root_ref,
        imported_at=_timestamp(),
    )

    artifact_rows: list[dict[str, Any]] = []
    fragment_rows: list[dict[str, Any]] = []
    observation_rows: list[dict[str, Any]] = []
    claim_rows: list[dict[str, Any]] = []
    concept_rows: list[dict[str, Any]] = []
    relation_rows: list[dict[str, Any]] = []
    build_rows_params = inspect.signature(adapter.build_rows).parameters
    if "root" in build_rows_params:
        structured_rows = adapter.build_rows(context, discovered, root=source_path)
    else:
        structured_rows = adapter.build_rows(context, discovered)
    if structured_rows is not None:
        artifact_rows.extend(structured_rows.artifact_rows)
        fragment_rows.extend(structured_rows.fragment_rows)
        observation_rows.extend(structured_rows.observation_rows)
        claim_rows.extend(structured_rows.claim_rows)
        concept_rows.extend(structured_rows.concept_rows)
        relation_rows.extend(structured_rows.relation_rows)
    else:
        for artifact in artifacts:
            page = _segment_artifact(artifact)
            artifact_row = build_artifact_record(context, artifact, page)
            artifact_rows.append(artifact_row)
            if page is None:
                continue

            concept_rows.extend(build_concept_records(context, artifact_row, page.concepts))
            relation_rows.extend(build_relation_records(context, artifact_row, page.concepts, page.links))

            for index, observation in enumerate(page.observations, start=1):
                fragment_row = build_fragment_record(context, artifact_row, observation, index)
                fragment_rows.append(fragment_row)
                observation_row = build_observation_record(context, artifact_row, observation, index)
                observation_rows.append(observation_row)
                if mode == "archive":
                    continue
                if observation.role not in {"claim", "summary"}:
                    continue
                claim_rows.append(
                    build_claim_record(
                        context,
                        observation_row,
                        observation,
                        page.concepts[:3],
                        index,
                        fragment_ids=[fragment_row["fragment_id"]],
                    )
                )

    fragment_rows = _dedupe_by_key(fragment_rows, "fragment_id")
    raw_concept_rows = [dict(row) for row in concept_rows]
    concept_rows, claim_rows, relation_rows = standardize_concept_rows(concept_rows, claim_rows, relation_rows)
    concept_alignment_summary: dict[str, Any] | None = None
    if concept_seed_store is not None:
        concept_alignment_summary = align_claim_rows_to_seed_concepts(
            claim_rows,
            concept_seed_store,
            threshold=concept_alignment_threshold,
        )
    concept_rows = _dedupe_by_key(concept_rows, "concept_id")
    artifact_rows = _dedupe_by_key(artifact_rows, "artifact_id")
    observation_rows = _dedupe_by_key(observation_rows, "observation_id")
    claim_rows = _dedupe_by_key(claim_rows, "claim_id")
    apply_adapter_confidence_policy(
        observation_rows,
        adapter_name=adapter.name,
        row_kind="observation",
        recorded_at=context.imported_at,
    )
    apply_adapter_confidence_policy(
        claim_rows,
        adapter_name=adapter.name,
        row_kind="claim",
        recorded_at=context.imported_at,
    )
    graph_extraction_summary: dict[str, Any] = {
        "mode": graph_extraction_mode,
        "candidate_relation_count": 0,
        "candidate_relations": [],
    }
    if graph_extraction_mode == "heuristic":
        extracted_relations, graph_extraction_summary = extract_heuristic_graph_relations(
            concept_rows,
            observation_rows,
            import_id=actual_import_id,
            machine_id=context.machine_id,
        )
        relation_rows.extend(extracted_relations)
    relation_rows = _dedupe_by_key(relation_rows, "relation_id")
    concept_standardization_report = build_concept_standardization_report(raw_concept_rows, concept_rows)

    manifest = manifest_record(context) | {
        "source_adapter": adapter.name,
        "import_intent": adapter.import_intent(),
        **({"policy_plugin_decision": policy_decision.model_dump(mode="json")} if policy_decision is not None else {}),
        "source_root_kind": source_root_kind,
        "artifact_count": len(artifact_rows),
        "fragment_count": len(fragment_rows),
        "observation_count": len(observation_rows),
        "claim_count": len(claim_rows),
        "concept_count": len(concept_rows),
        "relation_count": len(relation_rows),
        "concept_standardization": {
            "deterministic_merge_group_count": concept_standardization_report["deterministic_merge_group_count"],
            "ambiguous_alias_candidate_count": concept_standardization_report["ambiguous_alias_candidate_count"],
        },
        "graph_extraction": graph_extraction_summary,
    }
    if concept_alignment_summary is not None:
        manifest["concept_alignment"] = concept_alignment_summary
        manifest["external_concept_ids"] = concept_alignment_summary.get("external_concept_ids", [])

    _write_json(output_dir / "manifest.json", manifest)
    _write_jsonl(output_dir / "artifacts.jsonl", artifact_rows)
    _write_jsonl(output_dir / "fragments.jsonl", fragment_rows)
    _write_jsonl(output_dir / "observations.jsonl", observation_rows)
    _write_jsonl(output_dir / "claims.jsonl", claim_rows)
    _write_jsonl(output_dir / "concepts.jsonl", concept_rows)
    _write_jsonl(output_dir / "relations.jsonl", relation_rows)
    _write_json(output_dir / "concept_standardization.json", concept_standardization_report)
    _write_json(output_dir / "graph_extraction_candidates.json", graph_extraction_summary)
    _write_json(
        output_dir / "graph_diagnostics.json",
        build_graph_diagnostics(concept_rows, relation_rows, claims=claim_rows, observations=observation_rows),
    )
    lint_payload = lint_import_directory(output_dir)
    _write_json(output_dir / "lint_findings.json", lint_payload)
    review_queue = build_review_queue(output_dir)
    _write_json(output_dir / "review_queue.json", review_queue)
    export_review_bundle_from_import(output_dir)

    return ImportResult(
        manifest=manifest,
        artifacts=artifact_rows,
        fragments=fragment_rows,
        observations=observation_rows,
        claims=claim_rows,
        concepts=concept_rows,
        relations=relation_rows,
        out_dir=output_dir,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import an llmwiki-style repository into GroundRecall import artifacts.")
    parser.add_argument("source_root")
    parser.add_argument("--out-root", default=None)
    parser.add_argument("--mode", choices=sorted(VALID_MODES), default="quick")
    parser.add_argument("--import-id", default=None)
    parser.add_argument("--machine-id", default=None)
    parser.add_argument("--agent-id", default="groundrecall.ingest")
    parser.add_argument("--concept-seed-store", default=None)
    parser.add_argument("--concept-alignment-threshold", type=float, default=0.55)
    parser.add_argument("--extract-graph", choices=sorted(VALID_GRAPH_EXTRACTION_MODES), default="none")
    parser.add_argument("--policy-plugins", default=None, help="Optional GroundRecall policy plugin YAML config for import proposal gating.")
    parser.add_argument("--policy-subject-id", default="", help="Subject/principal id to evaluate against policy plugins.")
    parser.add_argument("--audit-log", default=None, help="Optional JSONL audit log for import policy preflight decisions.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = run_groundrecall_import(
        source_root=args.source_root,
        out_root=args.out_root,
        mode=args.mode,
        import_id=args.import_id,
        machine_id=args.machine_id,
        agent_id=args.agent_id,
        concept_seed_store=args.concept_seed_store,
        concept_alignment_threshold=args.concept_alignment_threshold,
        extract_graph=args.extract_graph,
        policy_plugins_path=args.policy_plugins,
        policy_subject_id=args.policy_subject_id,
        audit_log_path=args.audit_log,
    )
    print(f"Wrote import artifacts to {result.out_dir}")
