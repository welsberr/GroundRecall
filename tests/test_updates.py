from __future__ import annotations

import json
from pathlib import Path

import pytest

from groundrecall.cli import COMMANDS
from groundrecall.models import ClaimRecord, RelationRecord
from groundrecall.store import (
    GroundRecallStore,
    IncompatibleStoreVersionError,
    STORE_MANIFEST_NAME,
    STORE_MANIFEST_SCHEMA,
)
import groundrecall.updates as updates_module
from groundrecall.updates import UpdateError, apply_update, plan_update, rollback_update


def _store(tmp_path: Path) -> tuple[Path, GroundRecallStore]:
    path = tmp_path / "canonical-store"
    store = GroundRecallStore(path)
    store.save_claim(
        ClaimRecord(
            claim_id="claim-1",
            claim_text="A fact that must survive capability updates.",
            concept_ids=["concept-1"],
            future_extension={"retained": True},
        )
    )
    store.save_relation(
        RelationRecord(
            relation_id="relation-1",
            source_id="concept-1",
            target_id="concept-2",
            relation_type="related_to",
        )
    )
    return path, store


def _payloads(store_path: Path) -> dict[str, bytes]:
    return {
        path.relative_to(store_path).as_posix(): path.read_bytes()
        for path in sorted(store_path.rglob("*.json"))
        if path.name != STORE_MANIFEST_NAME
    }


def test_update_plan_is_read_only_and_reports_graph_families(tmp_path: Path) -> None:
    store_path, _ = _store(tmp_path)
    before = _payloads(store_path)

    plan = plan_update(store_path)

    assert plan["update_available"] is True
    assert plan["current_store_format_version"] == 0
    assert plan["record_counts"]["claims"] == 1
    assert plan["record_counts"]["relations"] == 1
    assert plan["write_performed"] is False
    assert _payloads(store_path) == before
    assert not (store_path / STORE_MANIFEST_NAME).exists()
    assert not list(tmp_path.glob(".*.groundrecall.lock"))


def test_update_apply_preserves_records_and_verified_backup(tmp_path: Path) -> None:
    store_path, store = _store(tmp_path)
    before = _payloads(store_path)
    backup_path = tmp_path / "protected-backup" / "canonical-store"

    result = apply_update(store_path, backup_path)

    assert result["updated"] is True
    assert result["canonical_records_rewritten"] is False
    assert result["record_counts"]["claims"] == 1
    assert result["record_counts"]["relations"] == 1
    assert _payloads(store_path) == before
    assert _payloads(backup_path) == before
    marker = json.loads((store_path / STORE_MANIFEST_NAME).read_text(encoding="utf-8"))
    assert marker["schema_version"] == STORE_MANIFEST_SCHEMA
    assert marker["store_format_version"] == 1
    assert store.get_claim("claim-1").model_extra["future_extension"] == {"retained": True}
    store.save_claim(store.get_claim("claim-1"))
    saved_claim = json.loads((store_path / "claims" / "claim-1.json").read_text(encoding="utf-8"))
    assert saved_claim["future_extension"] == {"retained": True}
    assert Path(result["backup_path"]).is_dir()
    assert plan_update(store_path)["update_available"] is False


def test_update_rollback_restores_unchanged_store_without_deleting_new_copy(tmp_path: Path) -> None:
    store_path, _ = _store(tmp_path)
    before = _payloads(store_path)
    backup_path = tmp_path / "external-backup"
    apply_update(store_path, backup_path)

    rollback = rollback_update(store_path, backup_path)

    assert rollback["rolled_back"] is True
    assert _payloads(store_path) == before
    assert not (store_path / STORE_MANIFEST_NAME).exists()
    assert backup_path.is_dir()


def test_update_rollback_refuses_to_discard_changes_made_after_update(tmp_path: Path) -> None:
    store_path, store = _store(tmp_path)
    backup_path = tmp_path / "external-backup"
    apply_update(store_path, backup_path)
    store.save_claim(ClaimRecord(claim_id="claim-2", claim_text="Added after update"))

    with pytest.raises(UpdateError, match="records changed since update"):
        rollback_update(store_path, backup_path)
    assert store.get_claim("claim-2") is not None
    assert backup_path.is_dir()


def test_update_commit_failure_leaves_original_store_untouched(tmp_path: Path, monkeypatch) -> None:
    store_path, _ = _store(tmp_path)
    before = _payloads(store_path)
    backup_path = tmp_path / "verified-backup"

    def fail_atomic_replace(*_args, **_kwargs):
        raise OSError("injected manifest commit failure")

    monkeypatch.setattr(updates_module.os, "replace", fail_atomic_replace)
    with pytest.raises(OSError, match="injected manifest commit failure"):
        apply_update(store_path, backup_path)

    assert _payloads(store_path) == before
    assert not (store_path / STORE_MANIFEST_NAME).exists()
    assert backup_path.is_dir()
    assert not list(store_path.glob(".*.tmp"))


def test_update_rejects_unrecognized_directory_without_touching_it(tmp_path: Path) -> None:
    unrecognized = tmp_path / "arbitrary"
    unrecognized.mkdir()
    (unrecognized / "notes.txt").write_text("not a GroundRecall store", encoding="utf-8")
    before = (unrecognized / "notes.txt").read_bytes()

    with pytest.raises(UpdateError, match="complete GroundRecall record-family layout"):
        plan_update(unrecognized)

    assert (unrecognized / "notes.txt").read_bytes() == before
    assert not (unrecognized / STORE_MANIFEST_NAME).exists()


def test_partial_legacy_store_requires_explicit_opt_in(tmp_path: Path) -> None:
    partial = tmp_path / "partial-store"
    (partial / "claims").mkdir(parents=True)
    (partial / "claims" / "claim-1.json").write_text(
        ClaimRecord(claim_id="claim-1", claim_text="Legacy").model_dump_json(),
        encoding="utf-8",
    )

    with pytest.raises(UpdateError, match="allow-partial-store"):
        plan_update(partial)

    assert plan_update(partial, allow_partial=True)["update_available"] is True


def test_persisted_assessments_keep_unknown_nested_fields(tmp_path: Path) -> None:
    _, store = _store(tmp_path)
    claim_path = store.claims_dir / "claim-1.json"
    payload = json.loads(claim_path.read_text(encoding="utf-8"))
    payload["assessments"] = [
        {
            "assessment_id": "assessment-1",
            "subject_id": "claim-1",
            "dimension": "extraction_fidelity",
            "recorded_at": "2026-09-20T12:00:00Z",
            "method": {
                "name": "test-method",
                "version": "1",
                "future_method_extension": {"preserve": True},
            },
            "future_assessment_extension": {"preserve": True},
        }
    ]
    claim_path.write_text(json.dumps(payload), encoding="utf-8")

    claim = store.get_claim("claim-1")
    store.save_claim(claim)
    saved = json.loads(claim_path.read_text(encoding="utf-8"))

    assert saved["assessments"][0]["future_assessment_extension"] == {"preserve": True}
    assert saved["assessments"][0]["method"]["future_method_extension"] == {"preserve": True}


def test_update_refuses_existing_backup_and_unknown_manifest_without_mutation(tmp_path: Path) -> None:
    store_path, _ = _store(tmp_path)
    backup_path = tmp_path / "already-there"
    backup_path.mkdir()
    before = _payloads(store_path)
    with pytest.raises(UpdateError, match="backup already exists"):
        apply_update(store_path, backup_path)
    assert _payloads(store_path) == before

    (store_path / STORE_MANIFEST_NAME).write_text(
        json.dumps({"schema_version": STORE_MANIFEST_SCHEMA, "store_format_version": 2}),
        encoding="utf-8",
    )
    with pytest.raises(IncompatibleStoreVersionError, match="newer than this release"):
        GroundRecallStore(store_path)


def test_update_plan_fails_closed_on_corrupt_records(tmp_path: Path) -> None:
    store_path, _ = _store(tmp_path)
    (store_path / "claims" / "claim-1.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(Exception):
        plan_update(store_path)
    assert not (store_path / STORE_MANIFEST_NAME).exists()


def test_update_command_is_registered() -> None:
    assert "update" in COMMANDS
