from __future__ import annotations

import json
from pathlib import Path

from groundrecall.reminder_state import load_reminder_state, save_reminder_state
from groundrecall.review_backlog import record_interaction


def _workspace(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "workspace"; directory = root / "imports" / "i1"; directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(json.dumps({"import_id": "i1"}), encoding="utf-8")
    (directory / "review_queue.json").write_text(json.dumps({"items": [{"queue_id": "c", "candidate_type": "claim", "candidate_id": "c", "status": "needs_review"}]}), encoding="utf-8")
    (directory / "artifacts.jsonl").write_text("", encoding="utf-8")
    from groundrecall.review_backlog import aggregate_backlog
    return root, aggregate_backlog(root).items[0].backlog_id


def test_state_cache_roundtrip_reconciles_and_replays_corruption(tmp_path: Path) -> None:
    root, backlog_id = _workspace(tmp_path); record_interaction(root, backlog_id, event_type="acknowledged", actor_subject_id="a")
    path = save_reminder_state(root, active_backlog_ids={backlog_id}); payload, health = load_reminder_state(root, active_backlog_ids={backlog_id})
    assert health["status"] == "cache" and backlog_id in payload["states"]
    path.write_text("{}", encoding="utf-8")
    rebuilt, fallback = load_reminder_state(root, active_backlog_ids=set())
    assert fallback["status"] == "replayed" and rebuilt["states"] == {}
    assert str(path.parent.parent) not in json.dumps(rebuilt)
