"""Deterministic local reminder evaluation and delivery (RB4)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, Field

from .review_backlog import BacklogDigest, _append_interaction_event, aggregate_backlog, read_interaction_events
from .reminder_state import load_reminder_state, save_reminder_state


class ReminderPolicy(BaseModel):
    schema_version: str = "groundrecall.review-reminders.v1"
    enabled: bool = True
    cadence: Literal["hourly", "daily", "weekly"] = "daily"
    quiet_hours: dict[str, str] = Field(default_factory=lambda: {"start": "21:00", "end": "08:00"})
    timezone: str = "UTC"
    digest: dict[str, Any] = Field(default_factory=lambda: {"max_items": 20, "include_content_previews": False})
    thresholds: dict[str, Any] = Field(default_factory=lambda: {"minimum_visible_items": 1, "urgent_immediate": True})
    fatigue_control: dict[str, Any] = Field(default_factory=lambda: {"unchanged_digest_suppression_hours": 72, "acknowledged_suppression_hours": 168, "maximum_reminders_per_day": 1})


class ReminderDecision(BaseModel):
    schema_version: str = "groundrecall.review-reminder-decision.v1"
    decision: Literal["emit", "emit_urgent", "suppress_empty", "suppress_unchanged", "suppress_quiet_hours", "suppress_rate_limit", "disabled"]
    reason_codes: list[str] = Field(default_factory=list)
    next_eligible_at: str = ""
    digest_hash: str = ""


def load_reminder_policy(path: str | Path | None) -> ReminderPolicy:
    if not path:
        return ReminderPolicy()
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return ReminderPolicy.model_validate(payload)


def _digest_hash(digest: BacklogDigest) -> str:
    payload = digest.model_dump(mode="json", exclude={"generated_at"})
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _quiet(now: datetime, policy: ReminderPolicy) -> bool:
    start = policy.quiet_hours.get("start", "21:00")
    end = policy.quiet_hours.get("end", "08:00")
    current = now.hour * 60 + now.minute
    begin = int(start[:2]) * 60 + int(start[3:5]); finish = int(end[:2]) * 60 + int(end[3:5])
    return current >= begin or current < finish if begin > finish else begin <= current < finish


def evaluate_reminder(workspace: str | Path, policy: ReminderPolicy, *, subject_id: str = "", policy_config: str | Path | None = None,
                      maximum_release_level: str = "private", now: datetime | None = None) -> tuple[ReminderDecision, BacklogDigest]:
    current = now or datetime.now(timezone.utc)
    try:
        current = current.astimezone(ZoneInfo(policy.timezone))
    except Exception:
        current = current.astimezone(timezone.utc)
    digest = aggregate_backlog(workspace, subject_id=subject_id, policy_config=policy_config, maximum_release_level=maximum_release_level, limit=int(policy.digest.get("max_items", 20)))
    digest_hash = _digest_hash(digest)
    # Validate/rebuild the derivative cache on every evaluation; the ledger
    # remains authoritative for event timestamps and decisions.
    load_reminder_state(workspace, active_backlog_ids={item.backlog_id for item in digest.items})
    if not policy.enabled: return ReminderDecision(decision="disabled", reason_codes=["policy_disabled"], digest_hash=digest_hash), digest
    if digest.visible_total < int(policy.thresholds.get("minimum_visible_items", 1)):
        return ReminderDecision(decision="suppress_empty", reason_codes=["below_minimum_visible_items"], digest_hash=digest_hash), digest
    events = read_interaction_events(workspace)
    hours = float(policy.fatigue_control.get("unchanged_digest_suppression_hours", 72))
    cadence_hours = {"hourly": 1, "daily": 24, "weekly": 168}[policy.cadence]
    for event in reversed(events):
        if event.event_type not in {"reminder_emitted", "reminder_failed"}: continue
        try:
            event_age = (current - datetime.fromisoformat(event.occurred_at.replace("Z", "+00:00"))).total_seconds() / 3600
        except ValueError:
            event_age = cadence_hours + 1
        if event_age < cadence_hours:
            return ReminderDecision(decision="suppress_unchanged", reason_codes=["cadence_interval"], digest_hash=digest_hash), digest
        if event.reason == digest_hash:
            try: age = (current - datetime.fromisoformat(event.occurred_at.replace("Z", "+00:00"))).total_seconds() / 3600
            except ValueError: age = hours + 1
            if age < hours: return ReminderDecision(decision="suppress_unchanged", reason_codes=["unchanged_digest"], digest_hash=digest_hash), digest
            break
    max_daily = int(policy.fatigue_control.get("maximum_reminders_per_day", 1))
    day = current.date().isoformat()
    sent_today = sum(event.event_type == "reminder_emitted" and event.occurred_at.startswith(day) for event in events)
    if sent_today >= max_daily and not (policy.thresholds.get("urgent_immediate") and digest.urgent_count):
        return ReminderDecision(decision="suppress_rate_limit", reason_codes=["maximum_reminders_per_day"], digest_hash=digest_hash), digest
    if _quiet(current, policy) and not (policy.thresholds.get("urgent_immediate") and digest.urgent_count):
        return ReminderDecision(decision="suppress_quiet_hours", reason_codes=["quiet_hours"], digest_hash=digest_hash), digest
    decision = "emit_urgent" if digest.urgent_count and policy.thresholds.get("urgent_immediate") else "emit"
    return ReminderDecision(decision=decision, reason_codes=["pending_review"], digest_hash=digest_hash), digest


def _render(digest: BacklogDigest) -> dict[str, Any]:
    return {"schema_version": "groundrecall.review-reminder-digest.v1", "generated_at": digest.generated_at, "workspace_id": digest.workspace_id, "visible_total": digest.visible_total, "urgent_count": digest.urgent_count, "maintenance_health": digest.maintenance_health, "items": [{"backlog_id": item.backlog_id, "source_kind": item.source_kind, "candidate_kind": item.candidate_kind, "priority_band": item.priority_band, "authoritative_status": item.authoritative_status} for item in digest.items]}


def deliver_reminder(workspace: str | Path, decision: ReminderDecision, digest: BacklogDigest, *, adapter: str = "stdout", path: str | Path | None = None, dry_run: bool = False) -> dict[str, Any]:
    payload = _render(digest)
    if dry_run or decision.decision not in {"emit", "emit_urgent"}:
        return payload
    try:
        if adapter == "stdout": print(json.dumps(payload, indent=2))
        elif adapter == "file":
            target = Path(path or Path(workspace) / ".review" / "latest-digest.json"); target.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(prefix=".reminder.", dir=target.parent, text=True)
            with os.fdopen(fd, "w", encoding="utf-8") as handle: json.dump(payload, handle, indent=2); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp_name, target)
        else: raise ValueError("unsupported reminder adapter")
        _append_interaction_event(workspace, event_type="reminder_emitted", backlog_id="__digest__", actor_subject_id="groundrecall.reminder", reason=decision.digest_hash)
        save_reminder_state(workspace)
        return payload
    except Exception:
        _append_interaction_event(workspace, event_type="reminder_failed", backlog_id="__digest__", actor_subject_id="groundrecall.reminder", reason=decision.digest_hash)
        save_reminder_state(workspace)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate and optionally deliver a GroundRecall review reminder.")
    parser.add_argument("workspace"); parser.add_argument("--config", default=None); parser.add_argument("--dry-run", action="store_true"); parser.add_argument("--deliver", action="store_true"); parser.add_argument("--adapter", choices=("stdout", "file"), default="stdout"); parser.add_argument("--path", default=None); parser.add_argument("--subject-id", default=""); parser.add_argument("--policy-config", default=None); parser.add_argument("--maximum-release-level", default="private")
    args = parser.parse_args(); policy = load_reminder_policy(args.config); decision, digest = evaluate_reminder(args.workspace, policy, subject_id=args.subject_id, policy_config=args.policy_config, maximum_release_level=args.maximum_release_level)
    payload = {"decision": decision.model_dump(mode="json"), "digest": _render(digest)}
    if args.deliver and not args.dry_run: deliver_reminder(args.workspace, decision, digest, adapter=args.adapter, path=args.path)
    print(json.dumps(payload, indent=2))
