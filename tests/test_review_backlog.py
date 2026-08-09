from __future__ import annotations

import hashlib
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest

from groundrecall.review_backlog import (
    BacklogPolicyError,
    aggregate_backlog,
    discover_workspace,
    read_interaction_events,
    reconstruct_interaction_state,
    record_interaction,
)


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_aggregate_backlog_covers_notes_imports_and_candidates_without_paths(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    note = workspace / "source-notes" / "pending.md"
    note.parent.mkdir(parents=True)
    note.write_text("unimported note", encoding="utf-8")
    import_dir = workspace / "imports" / "import-1"
    _write(import_dir / "manifest.json", {"import_id": "import-1", "imported_at": "2026-01-01T00:00:00Z"})
    _write(import_dir / "review_queue.json", {"items": [{"queue_id": "rq_claim", "candidate_type": "claim", "candidate_id": "c1", "status": "needs_review", "finding_codes": ["claim_ungrounded"], "priority": 20}]})
    (import_dir / "artifacts.jsonl").write_text("", encoding="utf-8")
    candidate = workspace / "store" / "review_candidates" / "candidate.json"
    _write(candidate, {"review_candidate_id": "rc1", "candidate_type": "relation", "candidate_id": "r1", "current_status": "triaged", "triage_lane": "relation_review", "priority": 10})

    digest = aggregate_backlog(workspace, limit=20)
    assert digest.visible_total == 3
    assert {item.source_kind for item in digest.items} == {"source_note", "import_review", "canonical_review_candidate"}
    assert digest.urgent_count == 1
    assert all(str(workspace) not in item.model_dump_json() for item in digest.items)
    assert all(item.source_path_hash for item in digest.items)


def test_imported_note_is_not_reported_again(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    note = workspace / "source-notes" / "pending.md"
    note.parent.mkdir(parents=True)
    note.write_text("same content", encoding="utf-8")
    digest = hashlib.sha256(note.read_bytes()).hexdigest()
    import_dir = workspace / "imports" / "import-1"
    _write(import_dir / "manifest.json", {"import_id": "import-1"})
    (import_dir / "review_queue.json").write_text(json.dumps({"items": []}), encoding="utf-8")
    (import_dir / "artifacts.jsonl").write_text(json.dumps({"sha256": digest}) + "\n", encoding="utf-8")
    result = aggregate_backlog(workspace)
    assert result.visible_total == 0


def test_discovery_reports_missing_roots_and_accepts_overrides(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    result = discover_workspace(workspace, store=tmp_path / "custom-store")
    assert result["store"] == tmp_path / "custom-store"
    assert "workspace_missing" in result["diagnostics"]


def test_policy_and_release_filters_apply_before_counts(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    queue_dir = workspace / "imports" / "import-1"
    _write(queue_dir / "manifest.json", {"import_id": "import-1"})
    _write(queue_dir / "review_queue.json", {"items": [
        {"queue_id": "public", "candidate_type": "claim", "candidate_id": "p", "status": "needs_review", "release_level": "public", "priority": 50},
        {"queue_id": "private", "candidate_type": "claim", "candidate_id": "s", "status": "needs_review", "release_level": "private", "priority": 10},
    ]})
    (queue_dir / "artifacts.jsonl").write_text("", encoding="utf-8")
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders:\n  - type: static\n    default_decision: deny\n", encoding="utf-8")
    denied = aggregate_backlog(workspace, policy_config=policy)
    assert denied.visible_total == 0
    assert denied.redaction_summary["policy_or_release_filtered"] == 2
    released = aggregate_backlog(workspace, maximum_release_level="public")
    assert released.visible_total == 1
    assert released.items[0].release_level == "public"


def test_priority_factors_are_explainable_and_stable(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    queue_dir = workspace / "imports" / "import-1"
    _write(queue_dir / "manifest.json", {"import_id": "import-1"})
    _write(queue_dir / "review_queue.json", {"items": [{"queue_id": "claim", "candidate_type": "claim", "candidate_id": "c", "status": "needs_review", "finding_codes": ["claim_ungrounded"], "priority": 10}]})
    (queue_dir / "artifacts.jsonl").write_text("", encoding="utf-8")
    item = aggregate_backlog(workspace).items[0]
    assert item.priority_band == "urgent"
    assert "source_priority<=15" in item.priority_factors
    assert "reason:claim_ungrounded" in item.priority_factors


def test_backlog_digest_includes_read_only_maintenance_health(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"; store = workspace / "store"; maintenance = store / ".maintenance"; maintenance.mkdir(parents=True)
    _write(maintenance / "graph_maintenance_state__safe.json", {"profile": "safe", "updated_at": "2026-07-30T00:00:00Z", "run_count": 2, "last_run": {"candidate_relation_count": 3}})
    digest = aggregate_backlog(workspace)
    assert digest.maintenance_health["state_count"] == 1
    assert str(workspace) not in digest.model_dump_json()


def _ledger_workspace(tmp_path: Path) -> tuple[Path, str]:
    workspace = tmp_path / "workspace"
    queue_dir = workspace / "imports" / "import-1"
    _write(queue_dir / "manifest.json", {"import_id": "import-1"})
    _write(queue_dir / "review_queue.json", {"items": [{"queue_id": "claim", "candidate_type": "claim", "candidate_id": "c", "status": "needs_review"}]})
    (queue_dir / "artifacts.jsonl").write_text("", encoding="utf-8")
    return workspace, aggregate_backlog(workspace).items[0].backlog_id


def test_interaction_ledger_reconstructs_state_and_preserves_canonical_files(tmp_path: Path) -> None:
    workspace, backlog_id = _ledger_workspace(tmp_path)
    event1 = record_interaction(workspace, backlog_id, event_type="acknowledged", actor_subject_id="alice")
    record_interaction(workspace, backlog_id, event_type="deferred", actor_subject_id="alice", until="2030-01-01T00:00:00Z", reason="needs review")
    record_interaction(workspace, backlog_id, event_type="assigned", actor_subject_id="alice", assignment="bob")
    events = read_interaction_events(workspace)
    assert events[0].event_hash == event1.event_hash
    assert events[1].previous_event_hash == events[0].event_hash
    state = reconstruct_interaction_state(workspace)[backlog_id]
    assert state["acknowledgement_state"] == "acknowledged"
    assert state["assignment_state"] == "assigned" and state["assigned_to"] == "bob"
    assert state["deferral_until"].startswith("2030-")
    assert aggregate_backlog(workspace).items[0].acknowledgement_state == "acknowledged"


def test_policy_denial_blocks_interaction_ledger_write(tmp_path: Path) -> None:
    workspace, backlog_id = _ledger_workspace(tmp_path)
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders:\n  - type: static\n    default_decision: deny\n", encoding="utf-8")
    with pytest.raises(BacklogPolicyError):
        record_interaction(workspace, backlog_id, event_type="acknowledged", actor_subject_id="alice", policy_config=policy)
    assert not (workspace / ".review" / "backlog-events.jsonl").exists()


def test_tampered_ledger_is_rejected(tmp_path: Path) -> None:
    workspace, backlog_id = _ledger_workspace(tmp_path)
    record_interaction(workspace, backlog_id, event_type="acknowledged", actor_subject_id="alice")
    path = workspace / ".review" / "backlog-events.jsonl"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["reason"] = "tampered"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        read_interaction_events(workspace)


def test_interaction_lookup_is_not_bounded_by_digest_limit(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    queue_dir = workspace / "imports" / "import-1"
    _write(queue_dir / "manifest.json", {"import_id": "import-1"})
    rows = [{"queue_id": f"q-{index}", "candidate_type": "claim", "candidate_id": f"c-{index}", "status": "needs_review"} for index in range(25)]
    _write(queue_dir / "review_queue.json", {"items": rows})
    (queue_dir / "artifacts.jsonl").write_text("", encoding="utf-8")
    backlog_id = aggregate_backlog(workspace, limit=None).items[-1].backlog_id
    record_interaction(workspace, backlog_id, event_type="acknowledged", actor_subject_id="alice")
    assert (workspace / ".review" / "backlog-events.jsonl.lock").exists()


def test_concurrent_interaction_appends_preserve_hash_chain(tmp_path: Path) -> None:
    workspace, backlog_id = _ledger_workspace(tmp_path)
    def append(index: int):
        return record_interaction(workspace, backlog_id, event_type="acknowledged", actor_subject_id=f"a-{index}")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(append, range(12)))
    events = read_interaction_events(workspace)
    assert len(events) == 12
    assert all(events[index].previous_event_hash == (events[index - 1].event_hash if index else "") for index in range(len(events)))


def test_symlinked_source_note_does_not_expose_target_path(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"; notes = workspace / "source-notes"; notes.mkdir(parents=True)
    target = tmp_path / "outside-secret.md"; target.write_text("private", encoding="utf-8")
    try:
        (notes / "linked.md").symlink_to(target)
    except OSError:
        return
    digest = aggregate_backlog(workspace)
    assert digest.visible_total == 1
    assert str(target) not in digest.model_dump_json()


def test_scope_owner_and_due_filters_apply_before_counts(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"; directory = workspace / "imports" / "i1"; directory.mkdir(parents=True)
    _write(directory / "manifest.json", {"import_id": "i1"})
    _write(directory / "review_queue.json", {"items": [
        {"queue_id": "a", "candidate_type": "claim", "candidate_id": "a", "status": "needs_review", "scope_ids": ["s1"], "owner_subject_ids": ["alice"], "due_at": "2020-01-01T00:00:00Z"},
        {"queue_id": "b", "candidate_type": "claim", "candidate_id": "b", "status": "triaged", "scope_ids": ["s2"], "owner_subject_ids": ["bob"], "due_at": "2030-01-01T00:00:00Z"},
    ]}); (directory / "artifacts.jsonl").write_text("", encoding="utf-8")
    digest = aggregate_backlog(workspace, scope_ids=["s1"], owner_subject_ids=["alice"], overdue=True)
    assert digest.visible_total == 1 and digest.items[0].candidate_id == "a"
    invalid = aggregate_backlog(workspace, due_before="not-a-time")
    assert "invalid_due_before" in invalid.diagnostics
