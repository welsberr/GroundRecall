from __future__ import annotations

import pytest

from groundrecall.federation_review_source import FixtureFederationReviewSource, RemoteReviewItem, RemoteReviewSnapshot


def _source() -> FixtureFederationReviewSource:
    common = {"broker_id": "broker-a", "producer_instance_id": "host-a", "content_hash": "h", "version_hash": "v", "signature_status": "valid", "trust_status": "trusted", "state": "reviewable"}
    items = [
        RemoteReviewItem(item_id="public", release_level="public", **common),
        RemoteReviewItem(item_id="secret", release_level="private", **common),
        RemoteReviewItem(item_id="revoked", revocation_status="revoked", **common),
        RemoteReviewItem(item_id="quarantined", quarantine_status="quarantined", **common),
        RemoteReviewItem(item_id="invalid", **{**common, "signature_status": "invalid"}),
    ]
    return FixtureFederationReviewSource(RemoteReviewSnapshot(broker_id="broker-a", producer_instance_id="host-a", retrieved_at="2026-07-30T00:00:00Z", freshness_status="stale", items=items))


def test_fixture_source_filters_trust_release_and_quarantine_and_paginates() -> None:
    source = _source()
    first, cursor, snapshot = source.page(page_size=1, maximum_release_level="public")
    assert [item.item_id for item in first] == ["public"] and not cursor
    assert snapshot.offline is False and snapshot.freshness_status == "stale"
    online = FixtureFederationReviewSource(snapshot.model_copy(update={"offline": False, "freshness_status": "fresh"}))
    _, _, online_snapshot = online.page(maximum_release_level="public")
    assert online_snapshot.offline is False and online_snapshot.freshness_status == "fresh"
    offline = FixtureFederationReviewSource(snapshot.model_copy(update={"offline": True, "freshness_status": "stale"}))
    _, _, offline_snapshot = offline.page(maximum_release_level="public")
    assert offline_snapshot.offline is True and offline_snapshot.freshness_status == "stale"
    all_items, _, _ = source.page(maximum_release_level="private")
    assert [item.item_id for item in all_items] == ["public", "secret"]


def test_fixture_source_rejects_bad_cursor_and_page_size() -> None:
    source = _source()
    with pytest.raises(ValueError, match="cursor"):
        source.page(cursor="not-base64")
    with pytest.raises(ValueError, match="page_size"):
        source.page(page_size=101)
