from __future__ import annotations

from groundrecall.models import ContributionRecord, ScopeRecord, StewardshipRecord
from groundrecall.stewardship_dashboard import stewardship_digest
from groundrecall.store import GroundRecallStore


def test_stewardship_digest_reports_pending_orphans_and_release_filter(tmp_path):
    root = tmp_path / "store"; store = GroundRecallStore(root)
    store.save_scope(ScopeRecord(scope_id="s", scope_kind="project", title="S", release_level="public", current_status="reviewed"))
    store.save_scope(ScopeRecord(scope_id="private", scope_kind="project", title="P", release_level="private", current_status="reviewed"))
    store.save_contribution(ContributionRecord(contribution_id="c", contributor_id="a", destination_scope_id="s", contribution_intent="review", state="proposed", proposed_release_level="public"))
    store.save_stewardship(StewardshipRecord(stewardship_id="st", subject_type="scope", subject_id="s", scope_id="s", status="orphaned", release_level="public"))
    digest = stewardship_digest(root, maximum_release_level="public", page_size=1)
    assert digest.visible_total == 3 and digest.counts_by_origin == {"local": 3}
    assert digest.next_cursor
    assert str(root) not in digest.model_dump_json()
