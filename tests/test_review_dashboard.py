from __future__ import annotations

import json
from pathlib import Path

import pytest

from groundrecall.review_dashboard import dashboard_digest, dashboard_item_detail


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    directory = root / "imports" / "i1"
    _write(directory / "manifest.json", {"import_id": "i1"})
    _write(directory / "review_queue.json", {"items": [
        {"queue_id": "a", "candidate_type": "claim", "candidate_id": "a", "status": "needs_review", "priority": 10},
        {"queue_id": "b", "candidate_type": "relation", "candidate_id": "b", "status": "needs_review", "priority": 50},
    ]})
    (directory / "artifacts.jsonl").write_text("", encoding="utf-8")
    return root


def test_dashboard_paginates_after_policy_filtered_counts(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    first = dashboard_digest(str(root), page_size=1)
    assert first.visible_total == 2 and len(first.items) == 1 and first.next_cursor
    second = dashboard_digest(str(root), page_size=1, cursor=first.next_cursor)
    assert second.visible_total == 2 and len(second.items) == 1
    assert second.items[0].backlog_id != first.items[0].backlog_id
    assert all(str(root) not in item.model_dump_json() for item in first.items)


def test_dashboard_cursor_context_is_bound_to_policy(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    first = dashboard_digest(str(root), page_size=1)
    with pytest.raises(ValueError, match="cursor context"):
        dashboard_digest(str(root), page_size=1, cursor=first.next_cursor, subject_id="different")


def test_dashboard_detail_is_metadata_only_and_authorized(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    digest = dashboard_digest(str(root), page_size=1)
    detail = dashboard_item_detail(str(root), digest.items[0].backlog_id)
    assert detail.item.content_available is False
    assert detail.provenance_available is False
    assert detail.item.local_only is True
    with pytest.raises(ValueError, match="not visible"):
        dashboard_item_detail(str(root), "backlog_missing")
