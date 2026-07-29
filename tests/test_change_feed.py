from __future__ import annotations

from pathlib import Path

import pytest

from groundrecall.change_feed import (
    FederationSubscription,
    acknowledge_change_bundle,
    build_incremental_change_bundle,
    import_incremental_change_bundle_to_quarantine,
    verify_incremental_change_bundle,
)
from groundrecall.federation import FederationPolicyError
from groundrecall.models import ScopeRecord, WorkRecord
from groundrecall.store import GroundRecallStore


KEY = "change feed signing secret"


def _seed(root: Path) -> None:
    store = GroundRecallStore(root)
    store.save_scope(ScopeRecord(scope_id="scope-public", scope_kind="project", title="Public", release_level="public", current_status="reviewed"))
    store.save_scope(ScopeRecord(scope_id="scope-internal", scope_kind="project", title="Internal", release_level="internal", current_status="reviewed"))
    store.save_work(WorkRecord(work_id="work-public", work_kind="technique", title="Public technique", scope_id="scope-public", release_level="public", current_status="reviewed"))
    store.save_work(WorkRecord(work_id="work-internal", work_kind="experiment", title="Internal experiment", scope_id="scope-internal", release_level="internal", current_status="reviewed"))


def test_incremental_bundle_filters_signs_and_acknowledges(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    _seed(store_dir)
    subscription = FederationSubscription(
        subscription_id="sub-1", producer_instance_id="host-a", scope_ids=["scope-public"],
        record_kinds=["work"], maximum_release_level="public", purpose="team project",
    )
    sub_path = tmp_path / "subscription.json"
    from groundrecall.change_feed import save_subscription
    save_subscription(sub_path, subscription)
    bundle_path = tmp_path / "bundle.json"
    bundle = build_incremental_change_bundle(store_dir, subscription, signing_key=KEY, key_id="k1", signature_algorithm="hmac-sha256", out_path=bundle_path, created_at="2026-07-29T00:00:00Z")
    assert [event.record_id for event in bundle.events] == ["work-public"]
    verify_incremental_change_bundle(bundle, verification_key=KEY, key_id="k1")
    result = import_incremental_change_bundle_to_quarantine(bundle_path, tmp_path / "quarantine", verification_key=KEY, subscription=subscription, key_id="k1")
    assert result.decision == "quarantined" and result.replayed is False
    replay = import_incremental_change_bundle_to_quarantine(bundle_path, tmp_path / "quarantine", verification_key=KEY, subscription=subscription, key_id="k1")
    assert replay.replayed is True
    updated = acknowledge_change_bundle(sub_path, bundle_path, verification_key=KEY, key_id="k1")
    assert updated.cursor == bundle.manifest.cursor_end
    with pytest.raises(FederationPolicyError, match="does not continue"):
        acknowledge_change_bundle(sub_path, bundle_path, verification_key=KEY, key_id="k1")


def test_change_feed_rejects_unknown_cursor_and_out_of_order_ack(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    _seed(store_dir)
    subscription = FederationSubscription(subscription_id="sub-1", producer_instance_id="host-a", record_kinds=["work"], purpose="test")
    with pytest.raises(FederationPolicyError, match="cursor is not present"):
        build_incremental_change_bundle(store_dir, subscription.model_copy(update={"cursor": "missing"}), signing_key=KEY, key_id="k1", signature_algorithm="hmac-sha256")
