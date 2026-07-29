from __future__ import annotations

from pathlib import Path

import pytest

from groundrecall.federation import FederationPolicyError
from groundrecall.institutional_release import (
    build_release_pack,
    build_withdrawal_notice,
    verify_release_pack,
    verify_withdrawal_notice,
)
from groundrecall.models import ClaimRecord, ProvenanceRecord, SourceRecord
from groundrecall.store import GroundRecallStore


KEY = "release signing secret"


def _seed_valid(store: GroundRecallStore) -> None:
    store.save_source(
        SourceRecord(
            source_id="source-a",
            title="Source A",
            url="https://example.test/source-a",
            license_id="CC-BY-4.0",
            attribution="Example Source",
            source_release_level="public",
            release_level="public",
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim-a",
            claim_text="A release-ready claim.",
            license_id="CC-BY-4.0",
            attribution="Example Source",
            source_release_level="public",
            metadata={"release_level": "public", "provenance_visibility": "redacted"},
            redaction_policy_id="redact-public-v1",
            derivative_source_ids=["source-a"],
            provenance=ProvenanceRecord(source_url="https://private.example.test/source", origin_path="/private/source.md"),
            current_status="reviewed",
        )
    )


def test_release_pack_hard_gates_missing_or_incompatible_license(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_claim(
        ClaimRecord(
            claim_id="claim-missing",
            claim_text="Missing license.",
            attribution="Someone",
            metadata={"release_level": "public"},
            current_status="reviewed",
        )
    )

    with pytest.raises(FederationPolicyError, match="missing_required_license"):
        build_release_pack(
            store.base_dir,
            target_release_level="public",
            allowed_license_ids=["CC-BY-4.0"],
            signing_key=KEY,
            key_id="k1",
        )
    store.save_claim(
        ClaimRecord(
            claim_id="claim-missing",
            claim_text="Bad license.",
            license_id="NOREDIST",
            attribution="Someone",
            metadata={"release_level": "public"},
            current_status="reviewed",
        )
    )
    with pytest.raises(FederationPolicyError, match="incompatible_license"):
        build_release_pack(
            store.base_dir,
            target_release_level="public",
            allowed_license_ids=["CC-BY-4.0"],
            signing_key=KEY,
            key_id="k1",
        )


def test_release_pack_is_deterministic_signed_and_redacts_protected_provenance(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    _seed_valid(store)

    kwargs = {
        "target_release_level": "public",
        "allowed_license_ids": ["CC-BY-4.0"],
        "signing_key": KEY,
        "key_id": "k1",
        "created_at": "2026-07-29T00:00:00Z",
        "pack_id": "pack-a",
        "review_receipt_ids": ["review-a"],
        "policy_id": "claimwright.release.v1",
    }
    first = build_release_pack(store.base_dir, out_dir=tmp_path / "pack1", **kwargs)
    second = build_release_pack(store.base_dir, out_dir=tmp_path / "pack2", **kwargs)

    assert first.manifest == second.manifest
    assert first.records == second.records
    assert first.manifest.license_ids == ["CC-BY-4.0"]
    assert first.manifest.attribution_count == 2
    assert first.manifest.redaction_policy_ids == ["redact-public-v1"]
    redacted = next(item for item in first.records if item["record_id"] == "claim-a")
    assert redacted["provenance"] == {"basis_visibility": "redacted", "redaction_policy_id": "redact-public-v1"}
    assert "/private/source.md" not in str(first.records)
    verified = verify_release_pack(first, verification_key=KEY, key_id="k1")
    assert verified.manifest.pack_id == "pack-a"


def test_withdrawal_notice_is_signed_distinct_from_erasure_and_blocks_reentry(tmp_path: Path) -> None:
    notice = build_withdrawal_notice(
        pack_id="pack-a",
        signing_key=KEY,
        key_id="k1",
        withdrawn_at="2026-07-29T01:00:00Z",
        reason="superseded evidence",
        superseded_by_pack_id="pack-b",
        authority="publication-gatekeeper",
        out_path=tmp_path / "withdrawal.json",
    )

    verified = verify_withdrawal_notice(notice, verification_key=KEY, key_id="k1")
    assert verified.distinct_from_erasure is True
    assert verified.preserve_historical_audit is True
    assert verified.superseded_by_pack_id == "pack-b"
    store = GroundRecallStore(tmp_path / "store")
    _seed_valid(store)
    with pytest.raises(FederationPolicyError, match="withdrawn"):
        build_release_pack(
            store.base_dir,
            target_release_level="public",
            allowed_license_ids=["CC-BY-4.0"],
            signing_key=KEY,
            key_id="k1",
            pack_id="pack-a",
            withdrawal_notice_paths=[tmp_path / "withdrawal.json"],
        )


def test_superseding_pack_relationship_is_visible(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    _seed_valid(store)

    pack = build_release_pack(
        store.base_dir,
        target_release_level="public",
        allowed_license_ids=["CC-BY-4.0"],
        signing_key=KEY,
        key_id="k1",
        pack_id="pack-b",
        supersedes_pack_ids=["pack-a"],
    )

    assert pack.manifest.supersedes_pack_ids == ["pack-a"]
