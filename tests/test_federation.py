from __future__ import annotations

import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from groundrecall import federation
from groundrecall.federation import (
    FederationLocalPolicy,
    FederationPolicyError,
    FederationPolicyGrant,
    FederationRoleDefinition,
    FederationRoleDirectory,
    FederationRoleMembership,
    FederationTrustRegistry,
    add_federation_trust_key,
    compile_federation_role_directory_to_policy,
    evaluate_federation_policy,
    export_federation_bundle,
    export_federation_public_keyset,
    export_federation_role_directory_publication,
    export_federation_trust_metadata,
    federation_key_fingerprint,
    filter_federation_role_directory,
    import_federation_bundle_to_quarantine,
    import_federation_public_keyset_to_trust_registry,
    import_federation_role_directory_publication_to_policy,
    is_allowed_for_target,
    is_less_restrictive,
    list_quarantine_bundles,
    load_federation_trust_registry,
    plan_quarantine_promotion,
    promote_quarantined_bundle,
    resolve_trust_key,
    revoke_federation_trust_key,
    save_federation_trust_registry,
    verify_federation_bundle,
    verify_federation_public_keyset,
    verify_federation_role_directory_publication,
)
from groundrecall.models import (
    AdjudicationRecord,
    ArtifactRecord,
    ClaimRecord,
    ConceptRecord,
    ContradictionCaseRecord,
    ObservationRecord,
    ProvenanceRecord,
    SourceRecord,
)
from groundrecall.store import GroundRecallStore


SIGNING_KEY = "test federation signing key"


def _ed25519_key_pair() -> tuple[bytes, bytes]:
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def _seed_federation_store(store: GroundRecallStore) -> None:
    store.save_source(
        SourceRecord(
            source_id="src_public",
            title="Public source",
            metadata={"release_level": "public"},
            current_status="promoted",
        )
    )
    store.save_artifact(
        ArtifactRecord(
            artifact_id="art_public",
            artifact_kind="note",
            title="Public artifact",
            metadata={"release_level": "public"},
            current_status="reviewed",
        )
    )
    store.save_observation(
        ObservationRecord(
            observation_id="obs_public",
            artifact_id="art_public",
            role="claim",
            text="Public observation.",
            metadata={"release_level": "public"},
            provenance=ProvenanceRecord(support_kind="direct_source", grounding_status="grounded"),
            current_status="reviewed",
        )
    )
    store.save_concept(
        ConceptRecord(
            concept_id="concept::public",
            title="Public concept",
            metadata={"release_level": "public"},
            current_status="promoted",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="clm_public",
            claim_text="Public claim.",
            concept_ids=["concept::public"],
            source_observation_ids=["obs_public"],
            metadata={"release_level": "public"},
            current_status="promoted",
        )
    )
    store.save_source(
        SourceRecord(
            source_id="src_internal",
            title="Internal source",
            metadata={"release_level": "internal"},
            current_status="promoted",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="clm_internal",
            claim_text="Internal claim.",
            metadata={"release_level": "internal"},
            current_status="promoted",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="clm_private",
            claim_text="Private local claim.",
            metadata={"release_level": "private"},
            current_status="promoted",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="clm_unclassified",
            claim_text="Unclassified claim.",
            current_status="promoted",
        )
    )


def test_release_lattice_blocks_broadening() -> None:
    assert is_allowed_for_target("public", "public")
    assert is_allowed_for_target("public", "internal")
    assert is_allowed_for_target("internal", "internal")
    assert not is_allowed_for_target("internal", "public")
    assert not is_allowed_for_target("private", "privileged")
    assert is_less_restrictive("public", "confidential")
    assert not is_less_restrictive("confidential", "public")


def test_local_policy_grants_action_release_level_and_instance() -> None:
    policy = FederationLocalPolicy(
        policy_id="policy-test",
        grants=[
            FederationPolicyGrant(
                subject_id="alice",
                actions=["export", "import", "promote"],
                release_levels=["public", "internal"],
                instance_ids=["host-a"],
            )
        ],
    )

    allowed = evaluate_federation_policy(policy, subject_id="alice", action="export", release_level="internal", instance_id="host-a")
    assert allowed.allowed is True
    assert allowed.grant_index == 0

    wrong_instance = evaluate_federation_policy(policy, subject_id="alice", action="export", release_level="internal", instance_id="host-b")
    assert wrong_instance.allowed is False
    assert wrong_instance.reasons == ["no_matching_federation_grant"]

    missing_subject = evaluate_federation_policy(policy, subject_id="", action="import", release_level="public", instance_id="host-a")
    assert missing_subject.allowed is False
    assert missing_subject.reasons == ["missing_subject_id"]

    promote = evaluate_federation_policy(policy, subject_id="alice", action="promote", release_level="internal", instance_id="host-a")
    assert promote.allowed is True


def test_local_policy_enforces_scope_when_grant_is_scoped() -> None:
    policy = FederationLocalPolicy(
        grants=[
            FederationPolicyGrant(
                subject_id="alice",
                actions=["import"],
                release_levels=["internal"],
                instance_ids=["host-a"],
                scopes=["project-alpha"],
            )
        ]
    )

    missing_scope = evaluate_federation_policy(policy, subject_id="alice", action="import", release_level="internal", instance_id="host-a")
    wrong_scope = evaluate_federation_policy(
        policy,
        subject_id="alice",
        action="import",
        release_level="internal",
        instance_id="host-a",
        scope_id="project-beta",
    )
    matching_scope = evaluate_federation_policy(
        policy,
        subject_id="alice",
        action="import",
        release_level="internal",
        instance_id="host-a",
        scope_id="project-alpha",
    )

    assert missing_scope.allowed is False
    assert wrong_scope.allowed is False
    assert matching_scope.allowed is True
    assert matching_scope.scope_id == "project-alpha"


def test_role_directory_compiles_to_local_policy_grants() -> None:
    directory = FederationRoleDirectory(
        directory_id="project-alpha-roles",
        roles=[
            FederationRoleDefinition(
                role_id="reviewer",
                actions=["import", "promote"],
                release_levels=["public", "internal"],
                instance_ids=["host-a"],
                scopes=["project-alpha"],
            ),
            FederationRoleDefinition(
                role_id="publisher",
                actions=["export"],
                release_levels=["public"],
                instance_ids=["host-a"],
            ),
        ],
        memberships=[
            FederationRoleMembership(subject_id="alice", role_ids=["reviewer", "publisher"]),
            FederationRoleMembership(subject_id="bob", role_ids=["reviewer"]),
        ],
    )

    policy = compile_federation_role_directory_to_policy(directory, policy_id="compiled-policy")

    assert policy.policy_id == "compiled-policy"
    assert len(policy.grants) == 3
    assert evaluate_federation_policy(
        policy,
        subject_id="alice",
        action="promote",
        release_level="internal",
        instance_id="host-a",
        scope_id="project-alpha",
    ).allowed is True
    assert evaluate_federation_policy(policy, subject_id="alice", action="export", release_level="public", instance_id="host-a").allowed is True
    assert evaluate_federation_policy(policy, subject_id="bob", action="export", release_level="public", instance_id="host-a").allowed is False


def test_role_directory_rejects_unknown_role_reference() -> None:
    directory = FederationRoleDirectory(
        roles=[],
        memberships=[FederationRoleMembership(subject_id="alice", role_ids=["missing-role"])],
    )

    with pytest.raises(FederationPolicyError, match="unknown role"):
        compile_federation_role_directory_to_policy(directory)


def test_signed_role_directory_publication_imports_with_local_caps(tmp_path: Path) -> None:
    signer_private_pem, signer_public_pem = _ed25519_key_pair()
    directory = FederationRoleDirectory(
        directory_id="project-alpha-roles",
        roles=[
            FederationRoleDefinition(
                role_id="reviewer",
                actions=["import", "promote", "export"],
                release_levels=["public", "internal"],
                instance_ids=["*"],
                scopes=["project-alpha", "project-beta"],
            )
        ],
        memberships=[
            FederationRoleMembership(subject_id="alice", role_ids=["reviewer"]),
            FederationRoleMembership(subject_id="mallory", role_ids=["reviewer"]),
        ],
    )
    publication_path = tmp_path / "roles-publication.json"

    publication = export_federation_role_directory_publication(
        directory,
        publication_path,
        producer_instance_id="host-a",
        signing_key=signer_private_pem,
        signer_key_id="host-a-role-root",
        created_at="2026-07-27T00:00:00Z",
    )

    assert publication.manifest.signature is not None
    assert publication.manifest.signature.algorithm == "ed25519"
    verified = verify_federation_role_directory_publication(
        json.loads(publication_path.read_text(encoding="utf-8")),
        verification_key=signer_public_pem,
        signer_key_id="host-a-role-root",
    )
    policy = import_federation_role_directory_publication_to_policy(
        verified,
        verification_key=signer_public_pem,
        signer_key_id="host-a-role-root",
        policy_id="receiver-policy",
        allowed_subject_ids=["alice"],
        allowed_role_ids=["reviewer"],
        allowed_instance_ids=["host-a"],
        allowed_release_levels=["public"],
        allowed_actions=["import"],
        allowed_scopes=["project-alpha"],
    )

    assert len(policy.grants) == 1
    grant = policy.grants[0]
    assert grant.subject_id == "alice"
    assert grant.actions == ["import"]
    assert grant.release_levels == ["public"]
    assert grant.instance_ids == ["host-a"]
    assert grant.scopes == ["project-alpha"]
    assert evaluate_federation_policy(
        policy,
        subject_id="alice",
        action="import",
        release_level="public",
        instance_id="host-a",
        scope_id="project-alpha",
    ).allowed is True
    assert evaluate_federation_policy(
        policy,
        subject_id="alice",
        action="promote",
        release_level="public",
        instance_id="host-a",
        scope_id="project-alpha",
    ).allowed is False
    assert evaluate_federation_policy(
        policy,
        subject_id="mallory",
        action="import",
        release_level="public",
        instance_id="host-a",
        scope_id="project-alpha",
    ).allowed is False


def test_signed_role_directory_publication_rejects_tampering(tmp_path: Path) -> None:
    signer_private_pem, signer_public_pem = _ed25519_key_pair()
    directory = FederationRoleDirectory(
        roles=[
            FederationRoleDefinition(
                role_id="reviewer",
                actions=["import"],
                release_levels=["public"],
                instance_ids=["host-a"],
            )
        ],
        memberships=[FederationRoleMembership(subject_id="alice", role_ids=["reviewer"])],
    )
    publication_path = tmp_path / "roles-publication.json"
    export_federation_role_directory_publication(
        directory,
        publication_path,
        producer_instance_id="host-a",
        signing_key=signer_private_pem,
        signer_key_id="host-a-role-root",
    )
    tampered = json.loads(publication_path.read_text(encoding="utf-8"))
    tampered["directory"]["memberships"][0]["subject_id"] = "mallory"

    with pytest.raises(FederationPolicyError, match="signature verification failed"):
        verify_federation_role_directory_publication(tampered, verification_key=signer_public_pem, signer_key_id="host-a-role-root")


def test_role_directory_filter_can_impose_scope_on_unscoped_role() -> None:
    directory = FederationRoleDirectory(
        roles=[
            FederationRoleDefinition(
                role_id="reviewer",
                actions=["import"],
                release_levels=["public"],
                instance_ids=["host-a"],
            )
        ],
        memberships=[FederationRoleMembership(subject_id="alice", role_ids=["reviewer"])],
    )

    filtered = filter_federation_role_directory(directory, allowed_scopes=["project-alpha"])

    assert filtered.roles[0].scopes == ["project-alpha"]


def test_trust_registry_resolves_active_instance_key_for_allowed_actions(tmp_path: Path) -> None:
    registry = add_federation_trust_key(
        FederationTrustRegistry(registry_id="test-registry"),
        instance_id="host-a",
        key_id="test-key",
        key_material=SIGNING_KEY,
        release_levels=["public", "internal"],
        trusted_actions=["export", "import", "promote"],
    )
    registry_path = tmp_path / "trust.json"
    save_federation_trust_registry(registry_path, registry)
    loaded = load_federation_trust_registry(registry_path)

    assert resolve_trust_key(loaded, instance_id="host-a", key_id="test-key", release_level="internal", action="import") == SIGNING_KEY.encode("utf-8")

    with pytest.raises(FederationPolicyError, match="does not allow release level"):
        resolve_trust_key(loaded, instance_id="host-a", key_id="test-key", release_level="confidential", action="import")

    inactive = add_federation_trust_key(
        loaded,
        instance_id="host-b",
        key_id="inactive-key",
        key_material=SIGNING_KEY,
        release_levels=["public"],
        trusted_actions=["import"],
        active=False,
    )
    with pytest.raises(FederationPolicyError, match="inactive"):
        resolve_trust_key(inactive, instance_id="host-b", key_id="inactive-key", release_level="public", action="import")


def test_trust_registry_revokes_key_and_preserves_revocation_metadata() -> None:
    registry = add_federation_trust_key(
        FederationTrustRegistry(),
        instance_id="host-a",
        key_id="old-key",
        key_material=SIGNING_KEY,
        release_levels=["internal"],
        trusted_actions=["import", "promote"],
        created_at="2026-07-26T00:00:00Z",
    )

    revoked = revoke_federation_trust_key(
        registry,
        instance_id="host-a",
        key_id="old-key",
        revoked_at="2026-07-27T00:00:00Z",
        reason="rotation",
        superseded_by_key_id="new-key",
    )

    key = revoked.keys[0]
    assert key.active is False
    assert key.created_at == "2026-07-26T00:00:00Z"
    assert key.revoked_at == "2026-07-27T00:00:00Z"
    assert key.revocation_reason == "rotation"
    assert key.superseded_by_key_id == "new-key"
    with pytest.raises(FederationPolicyError, match="revoked"):
        resolve_trust_key(revoked, instance_id="host-a", key_id="old-key", release_level="internal", action="import")


def test_trust_registry_rejects_expired_key() -> None:
    registry = add_federation_trust_key(
        FederationTrustRegistry(),
        instance_id="host-a",
        key_id="expiring-key",
        key_material=SIGNING_KEY,
        release_levels=["internal"],
        trusted_actions=["import"],
        expires_at="2026-07-27T00:00:00Z",
    )

    assert (
        resolve_trust_key(
            registry,
            instance_id="host-a",
            key_id="expiring-key",
            release_level="internal",
            action="import",
            as_of="2026-07-26T23:59:59Z",
        )
        == SIGNING_KEY.encode("utf-8")
    )
    with pytest.raises(FederationPolicyError, match="expired"):
        resolve_trust_key(
            registry,
            instance_id="host-a",
            key_id="expiring-key",
            release_level="internal",
            action="import",
            as_of="2026-07-27T00:00:00Z",
        )


def test_trust_metadata_export_redacts_key_material_by_default() -> None:
    registry = add_federation_trust_key(
        FederationTrustRegistry(registry_id="local-registry"),
        instance_id="host-a",
        key_id="metadata-key",
        key_material=SIGNING_KEY,
        release_levels=["public", "internal"],
        trusted_actions=["import", "promote"],
        created_at="2026-07-26T00:00:00Z",
        expires_at="2026-10-24T00:00:00Z",
    )

    metadata = export_federation_trust_metadata(registry, exported_at="2026-07-27T00:00:00Z")
    exported = metadata.model_dump(mode="json")

    assert exported["registry_id"] == "groundrecall.federation_trust_metadata.v1"
    assert exported["source_registry_id"] == "local-registry"
    assert exported["exported_at"] == "2026-07-27T00:00:00Z"
    assert exported["keys"][0]["key_material_redacted"] is True
    assert exported["keys"][0]["key_fingerprint"] == ""
    assert "key_material" not in exported["keys"][0]
    assert SIGNING_KEY not in metadata.model_dump_json()


def test_trust_metadata_export_can_include_key_fingerprint() -> None:
    registry = add_federation_trust_key(
        FederationTrustRegistry(),
        instance_id="host-a",
        key_id="metadata-key",
        key_material=SIGNING_KEY,
        release_levels=["internal"],
        trusted_actions=["import"],
    )

    metadata = export_federation_trust_metadata(registry, include_key_fingerprints=True)

    assert metadata.keys[0].key_fingerprint == federation_key_fingerprint(SIGNING_KEY)
    assert metadata.keys[0].key_material_redacted is True
    assert SIGNING_KEY not in metadata.model_dump_json()


def test_signed_public_keyset_imports_ed25519_keys_with_local_caps(tmp_path: Path) -> None:
    signer_private_pem, signer_public_pem = _ed25519_key_pair()
    _, producer_public_pem = _ed25519_key_pair()
    source_registry = add_federation_trust_key(
        FederationTrustRegistry(registry_id="producer-registry"),
        instance_id="host-a",
        key_id="host-a-ed",
        key_material=producer_public_pem.decode("utf-8"),
        algorithm="ed25519",
        release_levels=["public", "internal"],
        trusted_actions=["import", "promote"],
        created_at="2026-07-26T00:00:00Z",
        expires_at="2026-10-24T00:00:00Z",
    )
    keyset_path = tmp_path / "public-keyset.json"

    keyset = export_federation_public_keyset(
        source_registry,
        keyset_path,
        producer_instance_id="host-a",
        signing_key=signer_private_pem,
        signer_key_id="host-a-root",
        created_at="2026-07-27T00:00:00Z",
    )

    assert keyset.manifest.signature is not None
    assert keyset.manifest.signature.algorithm == "ed25519"
    assert keyset.keys[0].public_key_pem == producer_public_pem.decode("utf-8")
    verified = verify_federation_public_keyset(json.loads(keyset_path.read_text(encoding="utf-8")), verification_key=signer_public_pem, signer_key_id="host-a-root")
    receiver_registry = import_federation_public_keyset_to_trust_registry(
        verified,
        FederationTrustRegistry(registry_id="receiver-registry"),
        verification_key=signer_public_pem,
        signer_key_id="host-a-root",
        allowed_release_levels=["public"],
        allowed_trusted_actions=["import"],
    )

    imported_key = receiver_registry.keys[0]
    assert imported_key.algorithm == "ed25519"
    assert imported_key.key_material == producer_public_pem.decode("utf-8")
    assert imported_key.release_levels == ["public"]
    assert imported_key.trusted_actions == ["import"]
    assert imported_key.expires_at == "2026-10-24T00:00:00Z"
    with pytest.raises(FederationPolicyError, match="does not allow release level"):
        resolve_trust_key(receiver_registry, instance_id="host-a", key_id="host-a-ed", release_level="internal", action="import", algorithm="ed25519")


def test_signed_public_keyset_rejects_tampering(tmp_path: Path) -> None:
    signer_private_pem, signer_public_pem = _ed25519_key_pair()
    _, producer_public_pem = _ed25519_key_pair()
    source_registry = add_federation_trust_key(
        FederationTrustRegistry(),
        instance_id="host-a",
        key_id="host-a-ed",
        key_material=producer_public_pem.decode("utf-8"),
        algorithm="ed25519",
        release_levels=["public"],
        trusted_actions=["import"],
    )
    keyset_path = tmp_path / "public-keyset.json"
    export_federation_public_keyset(
        source_registry,
        keyset_path,
        producer_instance_id="host-a",
        signing_key=signer_private_pem,
        signer_key_id="host-a-root",
    )
    tampered = json.loads(keyset_path.read_text(encoding="utf-8"))
    tampered["keys"][0]["key_id"] = "attacker-key"

    with pytest.raises(FederationPolicyError, match="signature verification failed"):
        verify_federation_public_keyset(tampered, verification_key=signer_public_pem, signer_key_id="host-a-root")


def test_signed_public_keyset_import_defaults_to_producer_instance_only(tmp_path: Path) -> None:
    signer_private_pem, signer_public_pem = _ed25519_key_pair()
    _, producer_public_pem = _ed25519_key_pair()
    source_registry = add_federation_trust_key(
        FederationTrustRegistry(),
        instance_id="host-b",
        key_id="host-b-ed",
        key_material=producer_public_pem.decode("utf-8"),
        algorithm="ed25519",
        release_levels=["public"],
        trusted_actions=["import"],
    )
    keyset_path = tmp_path / "public-keyset.json"
    keyset = export_federation_public_keyset(
        source_registry,
        keyset_path,
        producer_instance_id="host-a",
        signing_key=signer_private_pem,
        signer_key_id="host-a-root",
    )

    default_registry = import_federation_public_keyset_to_trust_registry(
        keyset,
        FederationTrustRegistry(),
        verification_key=signer_public_pem,
    )
    assert default_registry.keys == []

    allowed_registry = import_federation_public_keyset_to_trust_registry(
        keyset,
        FederationTrustRegistry(),
        verification_key=signer_public_pem,
        allowed_instance_ids=["host-b"],
    )
    assert allowed_registry.keys[0].instance_id == "host-b"


def test_public_federation_bundle_filters_nonpublic_and_unclassified_records(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    _seed_federation_store(store)

    bundle_path = tmp_path / "public-federation.json"
    bundle = export_federation_bundle(
        store.base_dir,
        bundle_path,
        target_release_level="public",
        producer_instance_id="host-a",
        owner_instance_id="owner-a",
        signing_key=SIGNING_KEY,
        key_id="test-key",
        snapshot_id="snap-public",
        created_at="2026-07-26T00:00:00Z",
    )

    assert bundle_path.exists()
    assert bundle.manifest.signature is not None
    assert bundle.manifest.target_release_level == "public"
    assert [claim.claim_id for claim in bundle.snapshot.claims] == ["clm_public"]
    reasons = {finding.reason for finding in bundle.policy_report.findings}
    assert "release_level_exceeds_target:internal" in reasons
    assert "private_never_federated" in reasons
    assert "missing_release_level" in reasons
    verify_federation_bundle(json.loads(bundle_path.read_text(encoding="utf-8")), signing_key=SIGNING_KEY, key_id="test-key")


def test_public_federation_bundle_includes_contradiction_cases_and_adjudications(tmp_path: Path) -> None:
    source_store = GroundRecallStore(tmp_path / "source")
    _seed_federation_store(source_store)
    source_store.save_claim(
        ClaimRecord(
            claim_id="clm_public_peer",
            claim_text="Public peer claim.",
            concept_ids=["concept::public"],
            contradicts_claim_ids=["clm_public"],
            metadata={"release_level": "public"},
            current_status="reviewed",
        )
    )
    source_store.save_contradiction_case(
        ContradictionCaseRecord(
            case_id="case_public",
            claim_ids=["clm_public", "clm_public_peer"],
            status="under_review",
            adjudication_id="adj_case_public",
            metadata={"release_level": "public"},
            current_status="triaged",
        )
    )
    source_store.save_adjudication(
        AdjudicationRecord(
            adjudication_id="adj_case_public",
            subject_id="case_public",
            subject_type="contradiction_case",
            rationale="Case is under review.",
            metadata={"release_level": "public"},
            decided_at="2026-07-26T00:00:00Z",
        )
    )
    receiver_store = GroundRecallStore(tmp_path / "receiver")
    bundle_path = tmp_path / "public-cases.json"

    bundle = export_federation_bundle(
        source_store.base_dir,
        bundle_path,
        target_release_level="public",
        producer_instance_id="host-a",
        owner_instance_id="owner-a",
        signing_key=SIGNING_KEY,
        key_id="test-key",
        snapshot_id="snap-public-cases",
        created_at="2026-07-26T00:00:00Z",
    )

    assert [case.case_id for case in bundle.snapshot.contradiction_cases] == ["case_public"]
    assert [item.adjudication_id for item in bundle.snapshot.adjudications] == ["adj_case_public"]
    assert bundle.policy_report.included_counts["contradiction_cases"] == 1
    assert bundle.manifest.record_count >= 1

    result = promote_quarantined_bundle(
        bundle_path,
        receiver_store.base_dir,
        signing_key=SIGNING_KEY,
        key_id="test-key",
        accepted_release_levels=["public"],
        apply=True,
    )

    assert result.decision == "promoted"
    assert receiver_store.get_contradiction_case("case_public") is not None
    assert receiver_store.get_adjudication("adj_case_public") is not None


def test_confidential_derivative_requires_redaction_policy_for_public_export(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_claim(
        ClaimRecord(
            claim_id="clm_bad_summary",
            claim_text="Public-looking summary derived from confidential notes.",
            metadata={"release_level": "public", "derived_from_release_levels": ["confidential"]},
            current_status="promoted",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="clm_redacted_summary",
            claim_text="Approved redacted public summary.",
            metadata={
                "release_level": "public",
                "derived_from_release_levels": ["confidential"],
                "redaction_policy_id": "redact-public-v1",
            },
            current_status="promoted",
        )
    )

    bundle = export_federation_bundle(
        store.base_dir,
        tmp_path / "derivatives.json",
        target_release_level="public",
        producer_instance_id="host-a",
        signing_key=SIGNING_KEY,
        key_id="test-key",
        snapshot_id="snap-derivatives",
        created_at="2026-07-26T00:00:00Z",
    )

    assert [claim.claim_id for claim in bundle.snapshot.claims] == ["clm_redacted_summary"]
    assert any(finding.record_id == "clm_bad_summary" and finding.reason == "derivative_requires_redaction_policy" for finding in bundle.policy_report.findings)


def test_hidden_basis_requires_redaction_policy_and_marks_partial_visibility(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_artifact(
        ArtifactRecord(
            artifact_id="art_confidential",
            artifact_kind="note",
            metadata={"release_level": "confidential"},
            current_status="reviewed",
        )
    )
    store.save_observation(
        ObservationRecord(
            observation_id="obs_confidential",
            artifact_id="art_confidential",
            role="claim",
            text="Confidential basis.",
            metadata={"release_level": "confidential"},
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="clm_hidden_without_policy",
            claim_text="Public claim based on hidden confidential evidence.",
            source_observation_ids=["obs_confidential"],
            metadata={"release_level": "public"},
            current_status="promoted",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="clm_hidden_with_policy",
            claim_text="Public claim with redacted confidential evidence.",
            source_observation_ids=["obs_confidential"],
            metadata={"release_level": "public", "redaction_policy_id": "redact-basis-v1"},
            current_status="promoted",
        )
    )

    bundle = export_federation_bundle(
        store.base_dir,
        tmp_path / "hidden-basis.json",
        target_release_level="public",
        producer_instance_id="host-a",
        signing_key=SIGNING_KEY,
        key_id="test-key",
        snapshot_id="snap-hidden",
        created_at="2026-07-26T00:00:00Z",
    )

    assert [claim.claim_id for claim in bundle.snapshot.claims] == ["clm_hidden_with_policy"]
    exported_claim = bundle.snapshot.claims[0]
    assert exported_claim.source_observation_ids == []
    assert exported_claim.metadata["assessment_basis_visibility"] == "partial"
    assert exported_claim.metadata["hidden_basis_count"] == 1
    assert any(finding.record_id == "clm_hidden_without_policy" and finding.reason == "hidden_basis_without_redaction_policy" for finding in bundle.policy_report.findings)


def test_import_verifies_signature_and_quarantines_without_promotion(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    _seed_federation_store(store)
    bundle_path = tmp_path / "internal-federation.json"
    export_federation_bundle(
        store.base_dir,
        bundle_path,
        target_release_level="internal",
        producer_instance_id="host-a",
        signing_key=SIGNING_KEY,
        key_id="test-key",
        snapshot_id="snap-internal",
        created_at="2026-07-26T00:00:00Z",
    )

    result = import_federation_bundle_to_quarantine(
        bundle_path,
        tmp_path / "receiver" / "quarantine",
        signing_key=SIGNING_KEY,
        key_id="test-key",
        accepted_release_levels=["public", "internal"],
    )

    assert result.decision == "quarantined"
    assert Path(result.quarantine_path).exists()
    assert not (tmp_path / "receiver" / "claims").exists()

    summaries = list_quarantine_bundles(tmp_path / "receiver" / "quarantine")
    assert len(summaries) == 1
    assert summaries[0].bundle_id == result.bundle_id


def test_ed25519_bundle_signature_verifies_with_public_key(tmp_path: Path) -> None:
    private_pem, public_pem = _ed25519_key_pair()
    store = GroundRecallStore(tmp_path / "store")
    _seed_federation_store(store)
    bundle_path = tmp_path / "ed25519-federation.json"

    bundle = export_federation_bundle(
        store.base_dir,
        bundle_path,
        target_release_level="internal",
        producer_instance_id="host-a",
        signing_key=private_pem,
        key_id="ed-key",
        signature_algorithm="ed25519",
        snapshot_id="snap-ed25519",
        created_at="2026-07-26T00:00:00Z",
    )

    assert bundle.manifest.signature is not None
    assert bundle.manifest.signature.algorithm == "ed25519"
    verified = verify_federation_bundle(json.loads(bundle_path.read_text(encoding="utf-8")), signing_key=public_pem, key_id="ed-key")
    assert verified.manifest.bundle_id == bundle.manifest.bundle_id

    with pytest.raises(FederationPolicyError, match="signature verification failed"):
        verify_federation_bundle(json.loads(bundle_path.read_text(encoding="utf-8")), signing_key=_ed25519_key_pair()[1], key_id="ed-key")


def test_policy_rejects_unauthorized_export_and_writes_audit(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    _seed_federation_store(store)
    policy = FederationLocalPolicy(
        policy_id="policy-test",
        grants=[
            FederationPolicyGrant(
                subject_id="alice",
                actions=["export"],
                release_levels=["public"],
                instance_ids=["host-a"],
            )
        ],
    )
    audit_log = tmp_path / "audit.jsonl"

    with pytest.raises(FederationPolicyError, match="no_matching_federation_grant"):
        export_federation_bundle(
            store.base_dir,
            tmp_path / "blocked.json",
            target_release_level="internal",
            producer_instance_id="host-a",
            signing_key=SIGNING_KEY,
            key_id="test-key",
            requester_id="alice",
            policy=policy,
            audit_log_path=audit_log,
        )

    audit_rows = [json.loads(line) for line in audit_log.read_text(encoding="utf-8").splitlines()]
    assert audit_rows[0]["action"] == "export"
    assert audit_rows[0]["decision"] == "rejected"
    assert audit_rows[0]["subject_id"] == "alice"
    assert audit_rows[0]["release_level"] == "internal"


def test_quarantine_promotion_plans_then_applies_without_overwriting(tmp_path: Path) -> None:
    source_store = GroundRecallStore(tmp_path / "source")
    _seed_federation_store(source_store)
    receiver_store = GroundRecallStore(tmp_path / "receiver")
    bundle_path = tmp_path / "bundle.json"
    export_federation_bundle(
        source_store.base_dir,
        bundle_path,
        target_release_level="internal",
        producer_instance_id="host-a",
        signing_key=SIGNING_KEY,
        key_id="test-key",
        snapshot_id="snap-promote",
        created_at="2026-07-26T00:00:00Z",
    )

    plan = plan_quarantine_promotion(
        bundle_path,
        receiver_store.base_dir,
        signing_key=SIGNING_KEY,
        key_id="test-key",
        accepted_release_levels=["internal"],
    )
    assert plan.promotable_counts["claim"] == 2
    assert plan.conflicts == []
    assert receiver_store.get_claim("clm_public") is None

    dry_run = promote_quarantined_bundle(
        bundle_path,
        receiver_store.base_dir,
        signing_key=SIGNING_KEY,
        key_id="test-key",
        accepted_release_levels=["internal"],
    )
    assert dry_run.decision == "planned"
    assert receiver_store.get_claim("clm_public") is None

    applied = promote_quarantined_bundle(
        bundle_path,
        receiver_store.base_dir,
        signing_key=SIGNING_KEY,
        key_id="test-key",
        accepted_release_levels=["internal"],
        apply=True,
    )
    assert applied.decision == "promoted"
    assert receiver_store.get_claim("clm_public") is not None
    assert receiver_store.get_claim("clm_internal") is not None

    repeat_plan = plan_quarantine_promotion(
        bundle_path,
        receiver_store.base_dir,
        signing_key=SIGNING_KEY,
        key_id="test-key",
        accepted_release_levels=["internal"],
    )
    assert repeat_plan.unchanged_counts["claim"] == 2
    assert repeat_plan.promotable_counts.get("claim", 0) == 0


def test_quarantine_promotion_rejects_conflicting_existing_record(tmp_path: Path) -> None:
    source_store = GroundRecallStore(tmp_path / "source")
    _seed_federation_store(source_store)
    receiver_store = GroundRecallStore(tmp_path / "receiver")
    receiver_store.save_claim(
        ClaimRecord(
            claim_id="clm_public",
            claim_text="Different local claim.",
            metadata={"release_level": "public"},
            current_status="promoted",
        )
    )
    bundle_path = tmp_path / "bundle.json"
    export_federation_bundle(
        source_store.base_dir,
        bundle_path,
        target_release_level="public",
        producer_instance_id="host-a",
        signing_key=SIGNING_KEY,
        key_id="test-key",
        snapshot_id="snap-conflict",
        created_at="2026-07-26T00:00:00Z",
    )

    result = promote_quarantined_bundle(
        bundle_path,
        receiver_store.base_dir,
        signing_key=SIGNING_KEY,
        key_id="test-key",
        accepted_release_levels=["public"],
        apply=True,
    )

    assert result.decision == "rejected"
    assert result.reasons == ["promotion_conflicts"]
    assert result.plan.conflict_counts["claim"] == 1
    assert receiver_store.get_claim("clm_public").claim_text == "Different local claim."


def test_policy_gates_promotion_and_writes_audit(tmp_path: Path) -> None:
    source_store = GroundRecallStore(tmp_path / "source")
    _seed_federation_store(source_store)
    receiver_store = GroundRecallStore(tmp_path / "receiver")
    bundle_path = tmp_path / "bundle.json"
    export_federation_bundle(
        source_store.base_dir,
        bundle_path,
        target_release_level="internal",
        producer_instance_id="host-a",
        signing_key=SIGNING_KEY,
        key_id="test-key",
        snapshot_id="snap-policy-promote",
        created_at="2026-07-26T00:00:00Z",
    )
    policy = FederationLocalPolicy(
        policy_id="policy-promote",
        grants=[
            FederationPolicyGrant(
                subject_id="reviewer",
                actions=["promote"],
                release_levels=["internal"],
                instance_ids=["host-a"],
            )
        ],
    )
    audit_log = tmp_path / "audit.jsonl"

    rejected = promote_quarantined_bundle(
        bundle_path,
        receiver_store.base_dir,
        signing_key=SIGNING_KEY,
        key_id="test-key",
        accepted_release_levels=["internal"],
        policy=policy,
        requester_id="observer",
        audit_log_path=audit_log,
        apply=True,
    )
    assert rejected.decision == "rejected"
    assert rejected.reasons == ["no_matching_federation_grant"]

    promoted = promote_quarantined_bundle(
        bundle_path,
        receiver_store.base_dir,
        signing_key=SIGNING_KEY,
        key_id="test-key",
        accepted_release_levels=["internal"],
        policy=policy,
        requester_id="reviewer",
        audit_log_path=audit_log,
        apply=True,
    )
    assert promoted.decision == "promoted"
    rows = [json.loads(line) for line in audit_log.read_text(encoding="utf-8").splitlines()]
    assert [row["decision"] for row in rows] == ["rejected", "promoted"]
    assert rows[1]["action"] == "promote"


def test_policy_allows_export_and_import_with_audit(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    _seed_federation_store(store)
    policy = FederationLocalPolicy(
        policy_id="policy-test",
        grants=[
            FederationPolicyGrant(
                subject_id="alice",
                actions=["export"],
                release_levels=["internal"],
                instance_ids=["host-a"],
            ),
            FederationPolicyGrant(
                subject_id="bob",
                actions=["import"],
                release_levels=["internal"],
                instance_ids=["host-a"],
            ),
        ],
    )
    audit_log = tmp_path / "audit.jsonl"
    bundle_path = tmp_path / "bundle.json"

    bundle = export_federation_bundle(
        store.base_dir,
        bundle_path,
        target_release_level="internal",
        producer_instance_id="host-a",
        signing_key=SIGNING_KEY,
        key_id="test-key",
        requester_id="alice",
        policy=policy,
        audit_log_path=audit_log,
        snapshot_id="snap-policy",
        created_at="2026-07-26T00:00:00Z",
    )
    result = import_federation_bundle_to_quarantine(
        bundle_path,
        tmp_path / "quarantine",
        signing_key=SIGNING_KEY,
        key_id="test-key",
        accepted_release_levels=["internal"],
        requester_id="bob",
        policy=policy,
        audit_log_path=audit_log,
    )

    assert bundle.manifest.target_release_level == "internal"
    assert result.decision == "quarantined"
    audit_rows = [json.loads(line) for line in audit_log.read_text(encoding="utf-8").splitlines()]
    assert [row["decision"] for row in audit_rows] == ["exported", "quarantined"]
    assert audit_rows[0]["policy_id"] == "policy-test"
    assert audit_rows[1]["bundle_id"] == bundle.manifest.bundle_id


def test_import_rejects_tampered_bundle(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    _seed_federation_store(store)
    bundle_path = tmp_path / "public-federation.json"
    export_federation_bundle(
        store.base_dir,
        bundle_path,
        target_release_level="public",
        producer_instance_id="host-a",
        signing_key=SIGNING_KEY,
        key_id="test-key",
        snapshot_id="snap-public",
        created_at="2026-07-26T00:00:00Z",
    )
    payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    payload["snapshot"]["claims"][0]["claim_text"] = "Tampered claim text."
    tampered_path = tmp_path / "tampered.json"
    tampered_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FederationPolicyError, match="signature verification failed"):
        import_federation_bundle_to_quarantine(
            tampered_path,
            tmp_path / "receiver" / "quarantine",
            signing_key=SIGNING_KEY,
            key_id="test-key",
            accepted_release_levels=["public"],
        )


def test_federation_cli_exports_and_imports_quarantine_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    store = GroundRecallStore(tmp_path / "store")
    _seed_federation_store(store)
    key_file = tmp_path / "federation.key"
    key_file.write_text(SIGNING_KEY, encoding="utf-8")
    bundle_path = tmp_path / "bundle.json"
    quarantine_dir = tmp_path / "quarantine"

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "export",
            str(store.base_dir),
            str(bundle_path),
            "--target-release-level",
            "internal",
            "--producer-instance-id",
            "host-a",
            "--key-file",
            str(key_file),
            "--key-id",
            "test-key",
            "--snapshot-id",
            "snap-cli",
        ],
    )
    federation.main()
    export_stdout = json.loads(capsys.readouterr().out)
    assert export_stdout["manifest"]["target_release_level"] == "internal"
    assert bundle_path.exists()

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "import",
            str(bundle_path),
            str(quarantine_dir),
            "--key-file",
            str(key_file),
            "--key-id",
            "test-key",
            "--accept-release-level",
            "internal",
        ],
    )
    federation.main()
    import_stdout = json.loads(capsys.readouterr().out)
    assert import_stdout["decision"] == "quarantined"
    assert Path(import_stdout["quarantine_path"]).exists()

    monkeypatch.setattr("sys.argv", ["groundrecall federation", "list-quarantine", str(quarantine_dir)])
    federation.main()
    list_stdout = json.loads(capsys.readouterr().out)
    assert len(list_stdout) == 1
    assert list_stdout[0]["bundle_id"] == import_stdout["bundle_id"]

    receiver_store = tmp_path / "receiver-store"
    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "promote",
            import_stdout["quarantine_path"],
            str(receiver_store),
            "--key-file",
            str(key_file),
            "--key-id",
            "test-key",
            "--accept-release-level",
            "internal",
        ],
    )
    federation.main()
    plan_stdout = json.loads(capsys.readouterr().out)
    assert plan_stdout["decision"] == "planned"
    assert not (receiver_store / "claims" / "clm_public.json").exists()

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "promote",
            import_stdout["quarantine_path"],
            str(receiver_store),
            "--key-file",
            str(key_file),
            "--key-id",
            "test-key",
            "--accept-release-level",
            "internal",
            "--apply",
        ],
    )
    federation.main()
    apply_stdout = json.loads(capsys.readouterr().out)
    assert apply_stdout["decision"] == "promoted"
    assert (receiver_store / "claims" / "clm_public.json").exists()


def test_federation_cli_enforces_policy_file_and_writes_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    store = GroundRecallStore(tmp_path / "store")
    _seed_federation_store(store)
    key_file = tmp_path / "federation.key"
    key_file.write_text(SIGNING_KEY, encoding="utf-8")
    policy_file = tmp_path / "policy.json"
    policy_file.write_text(
        FederationLocalPolicy(
            policy_id="cli-policy",
            grants=[
                FederationPolicyGrant(
                    subject_id="alice",
                    actions=["export"],
                    release_levels=["internal"],
                    instance_ids=["host-a"],
                    scopes=["project-alpha"],
                )
            ],
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    audit_log = tmp_path / "audit.jsonl"
    bundle_path = tmp_path / "bundle.json"

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "export",
            str(store.base_dir),
            str(bundle_path),
            "--target-release-level",
            "internal",
            "--producer-instance-id",
            "host-a",
            "--key-file",
            str(key_file),
            "--key-id",
            "test-key",
            "--policy-file",
            str(policy_file),
            "--requester-id",
            "alice",
            "--scope-id",
            "project-alpha",
            "--audit-log",
            str(audit_log),
        ],
    )
    federation.main()
    output = json.loads(capsys.readouterr().out)
    assert output["manifest"]["target_release_level"] == "internal"
    assert bundle_path.exists()
    audit_row = json.loads(audit_log.read_text(encoding="utf-8").splitlines()[0])
    assert audit_row["policy_id"] == "cli-policy"
    assert audit_row["scope_id"] == "project-alpha"


def test_federation_cli_compiles_policy_from_roles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    role_directory_path = tmp_path / "roles.json"
    policy_path = tmp_path / "policy.json"
    role_directory_path.write_text(
        FederationRoleDirectory(
            directory_id="team-roles",
            roles=[
                FederationRoleDefinition(
                    role_id="reviewer",
                    actions=["import", "promote"],
                    release_levels=["public", "internal"],
                    instance_ids=["host-a"],
                )
            ],
            memberships=[FederationRoleMembership(subject_id="alice", role_ids=["reviewer"])],
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "policy-from-roles",
            str(role_directory_path),
            str(policy_path),
            "--policy-id",
            "compiled-team-policy",
        ],
    )
    federation.main()
    output = json.loads(capsys.readouterr().out)
    written = json.loads(policy_path.read_text(encoding="utf-8"))

    assert output == written
    assert output["policy_id"] == "compiled-team-policy"
    assert output["grants"][0]["subject_id"] == "alice"
    policy = FederationLocalPolicy.model_validate(written)
    assert evaluate_federation_policy(policy, subject_id="alice", action="promote", release_level="internal", instance_id="host-a").allowed is True


def test_federation_cli_publishes_and_imports_signed_role_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    signer_private_pem, signer_public_pem = _ed25519_key_pair()
    signer_private_file = tmp_path / "role-signer-private.pem"
    signer_public_file = tmp_path / "role-signer-public.pem"
    signer_private_file.write_bytes(signer_private_pem)
    signer_public_file.write_bytes(signer_public_pem)
    role_directory_path = tmp_path / "roles.json"
    publication_path = tmp_path / "roles-publication.json"
    policy_path = tmp_path / "policy.json"
    role_directory_path.write_text(
        FederationRoleDirectory(
            directory_id="team-roles",
            roles=[
                FederationRoleDefinition(
                    role_id="reviewer",
                    actions=["import", "promote"],
                    release_levels=["public", "internal"],
                    instance_ids=["*"],
                    scopes=["project-alpha", "project-beta"],
                )
            ],
            memberships=[FederationRoleMembership(subject_id="alice", role_ids=["reviewer"])],
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "role-publish-directory",
            str(role_directory_path),
            str(publication_path),
            "--producer-instance-id",
            "host-a",
            "--signing-key-file",
            str(signer_private_file),
            "--signer-key-id",
            "host-a-role-root",
        ],
    )
    federation.main()
    publication_output = json.loads(capsys.readouterr().out)
    assert publication_output["manifest"]["signature"]["algorithm"] == "ed25519"

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "policy-import-roles",
            str(publication_path),
            str(policy_path),
            "--signer-key-file",
            str(signer_public_file),
            "--signer-key-id",
            "host-a-role-root",
            "--policy-id",
            "receiver-role-policy",
            "--allow-subject-id",
            "alice",
            "--allow-instance-id",
            "host-a",
            "--allow-release-level",
            "internal",
            "--allow-action",
            "import",
            "--allow-scope",
            "project-alpha",
        ],
    )
    federation.main()
    output = json.loads(capsys.readouterr().out)
    written = json.loads(policy_path.read_text(encoding="utf-8"))

    assert output == written
    assert output["policy_id"] == "receiver-role-policy"
    assert output["grants"][0]["actions"] == ["import"]
    assert output["grants"][0]["release_levels"] == ["internal"]
    assert output["grants"][0]["instance_ids"] == ["host-a"]
    assert output["grants"][0]["scopes"] == ["project-alpha"]


def test_federation_cli_trust_registry_can_sign_verify_and_promote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    store = GroundRecallStore(tmp_path / "store")
    _seed_federation_store(store)
    key_file = tmp_path / "federation.key"
    key_file.write_text(SIGNING_KEY, encoding="utf-8")
    trust_registry = tmp_path / "trust.json"
    bundle_path = tmp_path / "bundle.json"
    quarantine_dir = tmp_path / "quarantine"
    receiver_store = tmp_path / "receiver"

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "trust-add",
            str(trust_registry),
            "--instance-id",
            "host-a",
            "--key-id",
            "test-key",
            "--key-file",
            str(key_file),
            "--release-level",
            "internal",
            "--trusted-action",
            "export",
            "--trusted-action",
            "import",
            "--trusted-action",
            "promote",
        ],
    )
    federation.main()
    trust_add_output = json.loads(capsys.readouterr().out)
    assert trust_add_output["keys"][0]["instance_id"] == "host-a"

    monkeypatch.setattr("sys.argv", ["groundrecall federation", "trust-list", str(trust_registry)])
    federation.main()
    trust_list_output = json.loads(capsys.readouterr().out)
    assert trust_list_output["keys"][0]["key_id"] == "test-key"

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "export",
            str(store.base_dir),
            str(bundle_path),
            "--target-release-level",
            "internal",
            "--producer-instance-id",
            "host-a",
            "--trust-registry",
            str(trust_registry),
            "--key-id",
            "test-key",
            "--snapshot-id",
            "snap-trust",
        ],
    )
    federation.main()
    export_output = json.loads(capsys.readouterr().out)
    assert export_output["manifest"]["signature"]["key_id"] == "test-key"

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "import",
            str(bundle_path),
            str(quarantine_dir),
            "--trust-registry",
            str(trust_registry),
            "--accept-release-level",
            "internal",
        ],
    )
    federation.main()
    import_output = json.loads(capsys.readouterr().out)
    assert import_output["decision"] == "quarantined"

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "promote",
            import_output["quarantine_path"],
            str(receiver_store),
            "--trust-registry",
            str(trust_registry),
            "--accept-release-level",
            "internal",
            "--apply",
        ],
    )
    federation.main()
    promote_output = json.loads(capsys.readouterr().out)
    assert promote_output["decision"] == "promoted"
    assert (receiver_store / "claims" / "clm_public.json").exists()


def test_federation_cli_ed25519_export_and_registry_import(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    private_pem, public_pem = _ed25519_key_pair()
    store = GroundRecallStore(tmp_path / "store")
    _seed_federation_store(store)
    private_key_file = tmp_path / "ed25519-private.pem"
    public_key_file = tmp_path / "ed25519-public.pem"
    private_key_file.write_bytes(private_pem)
    public_key_file.write_bytes(public_pem)
    trust_registry = tmp_path / "trust.json"
    bundle_path = tmp_path / "bundle.json"
    quarantine_dir = tmp_path / "quarantine"

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "trust-add",
            str(trust_registry),
            "--instance-id",
            "host-a",
            "--key-id",
            "ed-key",
            "--key-file",
            str(public_key_file),
            "--algorithm",
            "ed25519",
            "--release-level",
            "internal",
            "--trusted-action",
            "import",
        ],
    )
    federation.main()
    trust_add_output = json.loads(capsys.readouterr().out)
    assert trust_add_output["keys"][0]["algorithm"] == "ed25519"

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "export",
            str(store.base_dir),
            str(bundle_path),
            "--target-release-level",
            "internal",
            "--producer-instance-id",
            "host-a",
            "--key-file",
            str(private_key_file),
            "--key-id",
            "ed-key",
            "--signature-algorithm",
            "ed25519",
        ],
    )
    federation.main()
    export_output = json.loads(capsys.readouterr().out)
    assert export_output["manifest"]["signature"]["algorithm"] == "ed25519"

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "import",
            str(bundle_path),
            str(quarantine_dir),
            "--trust-registry",
            str(trust_registry),
            "--accept-release-level",
            "internal",
        ],
    )
    federation.main()
    import_output = json.loads(capsys.readouterr().out)
    assert import_output["decision"] == "quarantined"


def test_federation_cli_publishes_and_imports_signed_public_keyset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    signer_private_pem, signer_public_pem = _ed25519_key_pair()
    producer_private_pem, producer_public_pem = _ed25519_key_pair()
    store = GroundRecallStore(tmp_path / "store")
    _seed_federation_store(store)
    signer_private_file = tmp_path / "signer-private.pem"
    signer_public_file = tmp_path / "signer-public.pem"
    producer_private_file = tmp_path / "producer-private.pem"
    producer_public_file = tmp_path / "producer-public.pem"
    signer_private_file.write_bytes(signer_private_pem)
    signer_public_file.write_bytes(signer_public_pem)
    producer_private_file.write_bytes(producer_private_pem)
    producer_public_file.write_bytes(producer_public_pem)
    source_registry = tmp_path / "source-trust.json"
    receiver_registry = tmp_path / "receiver-trust.json"
    keyset_path = tmp_path / "public-keyset.json"
    bundle_path = tmp_path / "bundle.json"

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "trust-add",
            str(source_registry),
            "--instance-id",
            "host-a",
            "--key-id",
            "producer-ed",
            "--key-file",
            str(producer_public_file),
            "--algorithm",
            "ed25519",
            "--release-level",
            "internal",
            "--trusted-action",
            "import",
        ],
    )
    federation.main()
    capsys.readouterr()

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "trust-publish-keyset",
            str(source_registry),
            str(keyset_path),
            "--producer-instance-id",
            "host-a",
            "--signing-key-file",
            str(signer_private_file),
            "--signer-key-id",
            "host-a-root",
        ],
    )
    federation.main()
    keyset_output = json.loads(capsys.readouterr().out)
    assert keyset_output["manifest"]["signature"]["algorithm"] == "ed25519"
    assert keyset_output["keys"][0]["public_key_pem"] == producer_public_pem.decode("utf-8").strip()

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "trust-import-keyset",
            str(keyset_path),
            str(receiver_registry),
            "--signer-key-file",
            str(signer_public_file),
            "--signer-key-id",
            "host-a-root",
            "--allow-release-level",
            "internal",
            "--allow-trusted-action",
            "import",
        ],
    )
    federation.main()
    receiver_output = json.loads(capsys.readouterr().out)
    assert receiver_output["keys"][0]["algorithm"] == "ed25519"
    assert receiver_output["keys"][0]["key_material"] == producer_public_pem.decode("utf-8").strip()

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "export",
            str(store.base_dir),
            str(bundle_path),
            "--target-release-level",
            "internal",
            "--producer-instance-id",
            "host-a",
            "--key-file",
            str(producer_private_file),
            "--key-id",
            "producer-ed",
            "--signature-algorithm",
            "ed25519",
        ],
    )
    federation.main()
    capsys.readouterr()

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "import",
            str(bundle_path),
            str(tmp_path / "quarantine"),
            "--trust-registry",
            str(receiver_registry),
            "--accept-release-level",
            "internal",
        ],
    )
    federation.main()
    import_output = json.loads(capsys.readouterr().out)
    assert import_output["decision"] == "quarantined"


def test_federation_cli_revoke_blocks_registry_verification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    store = GroundRecallStore(tmp_path / "store")
    _seed_federation_store(store)
    key_file = tmp_path / "federation.key"
    key_file.write_text(SIGNING_KEY, encoding="utf-8")
    trust_registry = tmp_path / "trust.json"
    bundle_path = tmp_path / "bundle.json"

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "trust-add",
            str(trust_registry),
            "--instance-id",
            "host-a",
            "--key-id",
            "old-key",
            "--key-file",
            str(key_file),
            "--release-level",
            "internal",
            "--trusted-action",
            "export",
            "--trusted-action",
            "import",
        ],
    )
    federation.main()
    capsys.readouterr()

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "export",
            str(store.base_dir),
            str(bundle_path),
            "--target-release-level",
            "internal",
            "--producer-instance-id",
            "host-a",
            "--trust-registry",
            str(trust_registry),
            "--key-id",
            "old-key",
        ],
    )
    federation.main()
    capsys.readouterr()

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "trust-revoke",
            str(trust_registry),
            "--instance-id",
            "host-a",
            "--key-id",
            "old-key",
            "--reason",
            "rotation",
            "--superseded-by-key-id",
            "new-key",
        ],
    )
    federation.main()
    revoke_output = json.loads(capsys.readouterr().out)
    assert revoke_output["keys"][0]["active"] is False
    assert revoke_output["keys"][0]["revocation_reason"] == "rotation"
    assert revoke_output["keys"][0]["superseded_by_key_id"] == "new-key"

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "import",
            str(bundle_path),
            str(tmp_path / "quarantine"),
            "--trust-registry",
            str(trust_registry),
            "--accept-release-level",
            "internal",
        ],
    )
    with pytest.raises(FederationPolicyError, match="revoked"):
        federation.main()


def test_federation_cli_expired_registry_key_blocks_import(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    store = GroundRecallStore(tmp_path / "store")
    _seed_federation_store(store)
    key_file = tmp_path / "federation.key"
    key_file.write_text(SIGNING_KEY, encoding="utf-8")
    active_registry = tmp_path / "active-trust.json"
    expired_registry = tmp_path / "expired-trust.json"
    bundle_path = tmp_path / "bundle.json"

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "trust-add",
            str(active_registry),
            "--instance-id",
            "host-a",
            "--key-id",
            "dated-key",
            "--key-file",
            str(key_file),
            "--release-level",
            "internal",
            "--trusted-action",
            "export",
            "--expires-at",
            "2999-01-01T00:00:00Z",
        ],
    )
    federation.main()
    capsys.readouterr()

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "export",
            str(store.base_dir),
            str(bundle_path),
            "--target-release-level",
            "internal",
            "--producer-instance-id",
            "host-a",
            "--trust-registry",
            str(active_registry),
            "--key-id",
            "dated-key",
        ],
    )
    federation.main()
    capsys.readouterr()

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "trust-add",
            str(expired_registry),
            "--instance-id",
            "host-a",
            "--key-id",
            "dated-key",
            "--key-file",
            str(key_file),
            "--release-level",
            "internal",
            "--trusted-action",
            "import",
            "--expires-at",
            "2000-01-01T00:00:00Z",
        ],
    )
    federation.main()
    expired_output = json.loads(capsys.readouterr().out)
    assert expired_output["keys"][0]["expires_at"] == "2000-01-01T00:00:00Z"

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "import",
            str(bundle_path),
            str(tmp_path / "quarantine"),
            "--trust-registry",
            str(expired_registry),
            "--accept-release-level",
            "internal",
        ],
    )
    with pytest.raises(FederationPolicyError, match="expired"):
        federation.main()


def test_federation_cli_exports_redacted_trust_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    key_file = tmp_path / "federation.key"
    key_file.write_text(SIGNING_KEY, encoding="utf-8")
    trust_registry = tmp_path / "trust.json"
    metadata_path = tmp_path / "trust-metadata.json"

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "trust-add",
            str(trust_registry),
            "--instance-id",
            "host-a",
            "--key-id",
            "metadata-key",
            "--key-file",
            str(key_file),
            "--release-level",
            "internal",
            "--trusted-action",
            "import",
        ],
    )
    federation.main()
    capsys.readouterr()

    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall federation",
            "trust-export-metadata",
            str(trust_registry),
            str(metadata_path),
            "--include-key-fingerprint",
        ],
    )
    federation.main()
    output = json.loads(capsys.readouterr().out)
    written = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert output == written
    assert output["keys"][0]["key_fingerprint"] == federation_key_fingerprint(SIGNING_KEY)
    assert "key_material" not in output["keys"][0]
    assert SIGNING_KEY not in metadata_path.read_text(encoding="utf-8")
