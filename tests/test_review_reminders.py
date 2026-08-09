from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from groundrecall.review_backlog import read_interaction_events
from groundrecall.review_backlog_reminders import ReminderPolicy, deliver_reminder, evaluate_reminder


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"; directory = root / "imports" / "i1"; directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(json.dumps({"import_id": "i1"}), encoding="utf-8")
    (directory / "review_queue.json").write_text(json.dumps({"items": [{"queue_id": "c", "candidate_type": "claim", "candidate_id": "c", "status": "needs_review", "priority": 10}]}), encoding="utf-8")
    (directory / "artifacts.jsonl").write_text("", encoding="utf-8"); return root


def test_urgent_reminder_dry_run_and_atomic_file_delivery(tmp_path: Path) -> None:
    root = _workspace(tmp_path); policy = ReminderPolicy(fatigue_control={"unchanged_digest_suppression_hours": 72, "maximum_reminders_per_day": 1}, thresholds={"minimum_visible_items": 1, "urgent_immediate": True})
    decision, digest = evaluate_reminder(root, policy, now=datetime(2026, 7, 30, 12, tzinfo=timezone.utc))
    assert decision.decision == "emit_urgent"
    target = root / ".review" / "digest.json"; deliver_reminder(root, decision, digest, adapter="file", path=target)
    assert target.exists() and read_interaction_events(root)[0].event_type == "reminder_emitted"


def test_unchanged_and_quiet_suppression(tmp_path: Path) -> None:
    root = _workspace(tmp_path); policy = ReminderPolicy(quiet_hours={"start": "21:00", "end": "08:00"}, thresholds={"minimum_visible_items": 1, "urgent_immediate": False}, fatigue_control={"unchanged_digest_suppression_hours": 72, "maximum_reminders_per_day": 1})
    decision, digest = evaluate_reminder(root, policy, now=datetime(2026, 7, 30, 22, tzinfo=timezone.utc))
    assert decision.decision == "suppress_quiet_hours"
    policy.thresholds["urgent_immediate"] = True
    decision, digest = evaluate_reminder(root, policy, now=datetime(2026, 7, 30, 12, tzinfo=timezone.utc)); deliver_reminder(root, decision, digest, adapter="file", path=root / ".review" / "d.json")
    repeat, _ = evaluate_reminder(root, policy, now=datetime(2026, 7, 30, 13, tzinfo=timezone.utc))
    assert repeat.decision == "suppress_unchanged"

