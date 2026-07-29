from __future__ import annotations

from pathlib import Path

import pytest

from groundrecall.catalog import (
    FEDERATION_CATALOG_SCHEMA_VERSION,
    FederationCatalog,
    build_federation_catalog,
    import_federation_catalog_to_quarantine,
    query_federation_catalog,
    verify_federation_catalog,
)
from groundrecall.federation import FederationPolicyError
from groundrecall.models import ScopeRecord, WorkRecord
from groundrecall.store import GroundRecallStore


KEY = "catalog test signing secret"


def _seed_catalog_store(root: Path) -> GroundRecallStore:
    store = GroundRecallStore(root)
    store.save_scope(ScopeRecord(scope_id="scope-public", scope_kind="project", title="Public project", release_level="public", current_status="reviewed"))
    store.save_scope(ScopeRecord(scope_id="scope-internal", scope_kind="project", title="Internal project", release_level="internal", current_status="reviewed"))
    store.save_work(WorkRecord(work_id="work-public", work_kind="technique", title="Public graph technique", scope_id="scope-public", release_level="public", current_status="reviewed"))
    store.save_work(WorkRecord(work_id="work-internal", work_kind="experiment", title="Internal experiment", scope_id="scope-internal", release_level="internal", current_status="reviewed"))
    return store


def test_signed_catalog_build_verify_and_query(tmp_path: Path) -> None:
    _seed_catalog_store(tmp_path / "store")
    catalog_path = tmp_path / "catalog.json"
    catalog = build_federation_catalog(
        tmp_path / "store",
        producer_instance_id="host-a",
        target_release_level="internal",
        detail_level="descriptive",
        signing_key=KEY,
        key_id="host-a-catalog",
        signature_algorithm="hmac-sha256",
        out_path=catalog_path,
        created_at="2026-07-29T00:00:00Z",
    )
    assert catalog.manifest.schema_version == FEDERATION_CATALOG_SCHEMA_VERSION
    assert len(catalog.entries) == 2
    verify_federation_catalog(catalog, verification_key=KEY, key_id="host-a-catalog")
    matches = query_federation_catalog(catalog_path, "Public project")
    assert matches[0].scope_id == "scope-public"


def test_catalog_import_applies_receiver_release_cap_in_quarantine(tmp_path: Path) -> None:
    _seed_catalog_store(tmp_path / "store")
    catalog_path = tmp_path / "catalog.json"
    build_federation_catalog(
        tmp_path / "store",
        producer_instance_id="host-a",
        target_release_level="internal",
        detail_level="descriptive",
        signing_key=KEY,
        key_id="host-a-catalog",
        signature_algorithm="hmac-sha256",
        out_path=catalog_path,
    )
    result = import_federation_catalog_to_quarantine(
        catalog_path,
        tmp_path / "quarantine",
        verification_key=KEY,
        key_id="host-a-catalog",
        allowed_release_level="public",
        allowed_instance_ids=["host-a"],
    )
    assert result.decision == "quarantined"
    assert result.accepted_entry_count == 1
    assert result.excluded_entry_count == 1
    assert result.quarantine_path
    entries = query_federation_catalog(result.quarantine_path, "Public project")
    assert [entry.scope_id for entry in entries] == ["scope-public"]
    assert all(entry.scope_id != "scope-internal" for entry in query_federation_catalog(result.quarantine_path, "Internal project"))


def test_opaque_catalog_retains_release_classification_for_receiver_caps(tmp_path: Path) -> None:
    _seed_catalog_store(tmp_path / "store")
    catalog = build_federation_catalog(
        tmp_path / "store",
        producer_instance_id="host-a",
        target_release_level="internal",
        detail_level="opaque",
        signing_key=KEY,
        key_id="host-a-catalog",
        signature_algorithm="hmac-sha256",
    )
    assert all(entry.release_levels for entry in catalog.entries)


def test_catalog_import_rejects_untrusted_producer_cap(tmp_path: Path) -> None:
    _seed_catalog_store(tmp_path / "store")
    catalog_path = tmp_path / "catalog.json"
    build_federation_catalog(
        tmp_path / "store",
        producer_instance_id="host-a",
        target_release_level="public",
        detail_level="aggregate",
        signing_key=KEY,
        key_id="host-a-catalog",
        signature_algorithm="hmac-sha256",
        out_path=catalog_path,
    )
    result = import_federation_catalog_to_quarantine(
        catalog_path,
        tmp_path / "quarantine",
        verification_key=KEY,
        allowed_release_level="public",
        allowed_instance_ids=["host-b"],
    )
    assert result.decision == "quarantined"
    assert result.accepted_entry_count == 0
    assert "producer_instance_not_allowed" in result.reasons


def test_catalog_policy_hard_gate_prevents_export(tmp_path: Path) -> None:
    _seed_catalog_store(tmp_path / "store")
    policy = tmp_path / "policy.yaml"
    policy.write_text(
        "\n".join(
            [
                "schema_version: groundrecall.policy_plugins.v1",
                "providers:",
                "  - type: static",
                "    policy_id: catalog-deny",
                "    default_decision: hard_gate",
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(FederationPolicyError, match="policy_plugin_hard_gate"):
        build_federation_catalog(
            tmp_path / "store",
            producer_instance_id="host-a",
            target_release_level="public",
            detail_level="aggregate",
            signing_key=KEY,
            key_id="host-a-catalog",
            signature_algorithm="hmac-sha256",
            out_path=tmp_path / "blocked.json",
            policy_plugins_path=policy,
            requester_id="alice",
        )
    assert not (tmp_path / "blocked.json").exists()


def test_catalog_tampering_is_detected(tmp_path: Path) -> None:
    _seed_catalog_store(tmp_path / "store")
    catalog = build_federation_catalog(
        tmp_path / "store",
        producer_instance_id="host-a",
        target_release_level="public",
        detail_level="descriptive",
        signing_key=KEY,
        key_id="host-a-catalog",
        signature_algorithm="hmac-sha256",
    )
    tampered = catalog.model_copy(update={"entries": []})
    with pytest.raises(FederationPolicyError, match="content hash"):
        verify_federation_catalog(tampered, verification_key=KEY)


def test_restricted_scope_absent_from_federation_catalog(tmp_path: Path) -> None:
    store = _seed_catalog_store(tmp_path / "store")
    store.save_scope(
        ScopeRecord(
            scope_id="scope-restricted",
            scope_kind="project",
            title="Restricted incident project",
            release_level="confidential",
            metadata={"restrictions": ["incident"], "restriction_policy_id": "incident-share-v1"},
            current_status="reviewed",
        )
    )
    store.save_work(
        WorkRecord(
            work_id="work-restricted",
            work_kind="incident",
            title="Restricted incident work",
            scope_id="scope-restricted",
            release_level="confidential",
            metadata={"restrictions": ["incident"], "restriction_policy_id": "incident-share-v1"},
            current_status="reviewed",
        )
    )

    catalog = build_federation_catalog(
        store.base_dir,
        producer_instance_id="host-a",
        target_release_level="confidential",
        detail_level="descriptive",
        signing_key=KEY,
        key_id="host-a-catalog",
        signature_algorithm="hmac-sha256",
    )

    serialized = catalog.model_dump_json()
    assert "scope-restricted" not in serialized
    assert "Restricted incident" not in serialized


def test_restricted_catalog_does_not_leak_counts_or_topics(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_scope(
        ScopeRecord(
            scope_id="scope-restricted",
            scope_kind="project",
            title="Restricted source project",
            release_level="confidential",
            metadata={"restricted": True, "restriction_policy_id": "restricted-catalog-v1"},
            current_status="reviewed",
        )
    )
    store.save_work(
        WorkRecord(
            work_id="work-restricted",
            work_kind="experiment",
            title="Restricted source technique",
            scope_id="scope-restricted",
            release_level="confidential",
            metadata={"restricted": True, "restriction_policy_id": "restricted-catalog-v1"},
            current_status="reviewed",
        )
    )

    catalog = build_federation_catalog(
        store.base_dir,
        producer_instance_id="host-a",
        target_release_level="confidential",
        detail_level="aggregate",
        signing_key=KEY,
        key_id="host-a-catalog",
        signature_algorithm="hmac-sha256",
    )

    assert catalog.entries == []
