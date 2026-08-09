from __future__ import annotations

import json
from pathlib import Path

import pytest

from groundrecall.combined_dashboard import combined_dashboard_digest
from groundrecall.federation_review_source import FixtureFederationReviewSource, RemoteReviewItem, RemoteReviewSnapshot


def _local(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"; directory = root / "imports" / "i1"
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(json.dumps({"import_id": "i1"}), encoding="utf-8")
    (directory / "review_queue.json").write_text(json.dumps({"items": [{"queue_id": "l", "candidate_type": "claim", "candidate_id": "l", "status": "needs_review", "release_level": "public"}]}), encoding="utf-8")
    (directory / "artifacts.jsonl").write_text("", encoding="utf-8")
    return root


def _source() -> FixtureFederationReviewSource:
    item = RemoteReviewItem(item_id="r", broker_id="b", producer_instance_id="p", content_hash="h", version_hash="v", release_level="public", signature_status="valid", trust_status="trusted", state="reviewable")
    return FixtureFederationReviewSource(RemoteReviewSnapshot(broker_id="b", producer_instance_id="p", retrieved_at="now", offline=False, freshness_status="fresh", items=[item]))


def test_combined_dashboard_separates_origins_and_paginates(tmp_path: Path) -> None:
    root = _local(tmp_path)
    digest = combined_dashboard_digest(str(root), _source(), page_size=1)
    assert digest.visible_total == 2 and digest.local_total == 1 and digest.remote_total == 1
    assert digest.items[0].origin == "local" and digest.next_cursor
    second = combined_dashboard_digest(str(root), _source(), page_size=1, cursor=digest.next_cursor)
    assert second.items[0].origin == "broker"


def test_broker_outage_keeps_local_dashboard_usable(tmp_path: Path) -> None:
    class Down:
        def page(self, **kwargs): raise RuntimeError("offline")
    digest = combined_dashboard_digest(str(_local(tmp_path)), Down(), page_size=10)
    assert digest.local_total == 1 and digest.remote_total == 0 and digest.broker_available is False
    assert "broker_unavailable" in digest.diagnostics


def test_combined_cursor_context_and_release_filter(tmp_path: Path) -> None:
    root = _local(tmp_path)
    digest = combined_dashboard_digest(str(root), _source(), maximum_release_level="public", page_size=1)
    assert digest.counts_by_origin == {"local": 1, "broker": 1}
    with pytest.raises(ValueError, match="context"):
        combined_dashboard_digest(str(root), _source(), subject_id="other", cursor=digest.next_cursor)


def test_remote_pages_are_followed_and_truncation_is_visible(tmp_path: Path) -> None:
    root = _local(tmp_path)
    base = _source().snapshot.items[0]
    source = FixtureFederationReviewSource(_source().snapshot.model_copy(update={
        "items": [base.model_copy(update={"item_id": f"r-{index}"}) for index in range(205)]
    }))
    digest = combined_dashboard_digest(str(root), source, page_size=10, max_remote_items=150, max_remote_pages=20)
    assert digest.remote_total == 150
    assert digest.broker_results_truncated is True
    assert "broker_results_truncated" in digest.diagnostics
