"""Atomic, bounded broker snapshot cache helpers (RB6e)."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .federation_review_source import RemoteReviewSnapshot, FixtureFederationReviewSource


CACHE_SCHEMA_VERSION = "groundrecall.remote-review-cache.v1"


def _content_hash(snapshot: RemoteReviewSnapshot) -> str:
    payload = snapshot.model_dump(mode="json", exclude={"snapshot_hash"})
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def save_snapshot_cache(path: str | Path, snapshot: RemoteReviewSnapshot, *, max_bytes: int = 5_000_000) -> Path:
    prepared = snapshot.model_copy(update={"schema_version": CACHE_SCHEMA_VERSION})
    payload = prepared.model_copy(update={"snapshot_hash": _content_hash(prepared)})
    encoded = payload.model_dump_json(indent=2).encode("utf-8")
    if len(encoded) > max_bytes:
        raise ValueError("snapshot exceeds cache size limit")
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".snapshot-cache.", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    return target


def load_snapshot_cache(path: str | Path, *, max_age_seconds: int = 86_400, now: datetime | None = None) -> tuple[RemoteReviewSnapshot | None, dict[str, Any]]:
    target = Path(path)
    if not target.exists(): return None, {"status": "missing", "diagnostics": ["cache_missing"]}
    try:
        payload = json.loads(target.read_text(encoding="utf-8")); snapshot = RemoteReviewSnapshot.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValueError):
        return None, {"status": "invalid", "diagnostics": ["cache_invalid"]}
    if snapshot.schema_version != CACHE_SCHEMA_VERSION or snapshot.snapshot_hash != _content_hash(snapshot):
        return None, {"status": "invalid", "diagnostics": ["cache_hash_or_schema_invalid"]}
    current = now or datetime.now(timezone.utc)
    try: retrieved = datetime.fromisoformat(snapshot.retrieved_at.replace("Z", "+00:00"))
    except ValueError: retrieved = current
    age = max(0, int((current - retrieved).total_seconds()))
    stale = age > max_age_seconds
    status = "stale" if stale else "fresh"
    diagnostics = ["cache_stale"] if stale else []
    return snapshot.model_copy(update={"offline": True, "freshness_status": "stale" if stale else snapshot.freshness_status}), {"status": status, "age_seconds": age, "diagnostics": diagnostics}


class CachedFederationReviewSource(FixtureFederationReviewSource):
    def __init__(self, path: str | Path, *, max_age_seconds: int = 86_400, now: datetime | None = None):
        snapshot, self.cache_health = load_snapshot_cache(path, max_age_seconds=max_age_seconds, now=now)
        if snapshot is None:
            snapshot = RemoteReviewSnapshot(broker_id="", producer_instance_id="", retrieved_at="", offline=True, freshness_status="unknown")
        super().__init__(snapshot)
