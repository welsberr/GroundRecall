"""Atomic rebuildable reminder-state cache derived from the interaction ledger."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .review_backlog import reconstruct_interaction_state, read_interaction_events


SCHEMA = "groundrecall.review-reminder-state.v1"


def state_cache_path(workspace: str | Path) -> Path:
    return Path(workspace) / ".review" / "backlog-reminder-state.json"


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def rebuild_reminder_state(workspace: str | Path, *, active_backlog_ids: set[str] | None = None) -> dict[str, Any]:
    states = reconstruct_interaction_state(workspace)
    if active_backlog_ids is not None:
        states = {key: value for key, value in states.items() if key in active_backlog_ids}
    events = read_interaction_events(workspace)
    payload: dict[str, Any] = {"schema_version": SCHEMA, "states": states, "last_event_hash": events[-1].event_hash if events else "", "event_count": len(events)}
    payload["content_hash"] = _hash(payload)
    return payload


def save_reminder_state(workspace: str | Path, *, active_backlog_ids: set[str] | None = None) -> Path:
    payload = rebuild_reminder_state(workspace, active_backlog_ids=active_backlog_ids)
    target = state_cache_path(workspace); target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".reminder-state.", dir=target.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    return target


def load_reminder_state(workspace: str | Path, *, active_backlog_ids: set[str] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    target = state_cache_path(workspace)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        content_hash = payload.pop("content_hash")
        if payload.get("schema_version") != SCHEMA or content_hash != _hash(payload): raise ValueError("cache hash/schema invalid")
        states = payload.get("states", {})
        if active_backlog_ids is not None: states = {key: value for key, value in states.items() if key in active_backlog_ids}
        payload["states"] = states; payload["content_hash"] = content_hash
        return payload, {"status": "cache", "diagnostics": []}
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        payload = rebuild_reminder_state(workspace, active_backlog_ids=active_backlog_ids)
        return payload, {"status": "replayed", "diagnostics": ["reminder_state_cache_rebuilt"]}
