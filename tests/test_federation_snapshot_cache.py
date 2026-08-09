from __future__ import annotations

from datetime import datetime, timezone

import pytest

from groundrecall.federation_review_source import RemoteReviewItem, RemoteReviewSnapshot
from groundrecall.federation_snapshot_cache import CachedFederationReviewSource, load_snapshot_cache, save_snapshot_cache


def _snapshot(retrieved="2026-07-30T00:00:00Z"):
    return RemoteReviewSnapshot(broker_id="b", producer_instance_id="p", retrieved_at=retrieved, freshness_status="fresh", items=[RemoteReviewItem(item_id="r", broker_id="b", producer_instance_id="p", content_hash="h", version_hash="v", signature_status="valid", trust_status="trusted")])


def test_cache_atomic_roundtrip_and_stale_offline(tmp_path):
    path = tmp_path / "cache" / "snapshot.json"; save_snapshot_cache(path, _snapshot())
    loaded, health = load_snapshot_cache(path, now=datetime(2026, 7, 30, 1, tzinfo=timezone.utc), max_age_seconds=7200)
    assert loaded and health["status"] == "fresh"
    stale, stale_health = load_snapshot_cache(path, now=datetime(2026, 8, 2, tzinfo=timezone.utc), max_age_seconds=7200)
    assert stale and stale.offline and stale.freshness_status == "stale" and stale_health["status"] == "stale"
    source = CachedFederationReviewSource(path, now=datetime(2026, 8, 2, tzinfo=timezone.utc), max_age_seconds=7200)
    assert source.cache_health["status"] == "stale"


def test_cache_corruption_and_size_bound_do_not_leak_path(tmp_path):
    path = tmp_path / "cache.json"; save_snapshot_cache(path, _snapshot())
    path.write_text("{}", encoding="utf-8")
    loaded, health = load_snapshot_cache(path)
    assert loaded is None and health["status"] == "invalid" and str(path) not in str(health)
    with pytest.raises(ValueError, match="size"):
        save_snapshot_cache(path, _snapshot(), max_bytes=10)
