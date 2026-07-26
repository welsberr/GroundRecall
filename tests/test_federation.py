from __future__ import annotations

import json
from pathlib import Path

import pytest

from groundrecall import federation
from groundrecall.federation import (
    FederationLocalPolicy,
    FederationPolicyError,
    FederationPolicyGrant,
    FederationTrustRegistry,
    add_federation_trust_key,
    evaluate_federation_policy,
    export_federation_bundle,
    import_federation_bundle_to_quarantine,
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
)
from groundrecall.models import ArtifactRecord, ClaimRecord, ConceptRecord, ObservationRecord, ProvenanceRecord, SourceRecord
from groundrecall.store import GroundRecallStore


SIGNING_KEY = "test federation signing key"


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
            "--audit-log",
            str(audit_log),
        ],
    )
    federation.main()
    output = json.loads(capsys.readouterr().out)
    assert output["manifest"]["target_release_level"] == "internal"
    assert bundle_path.exists()
    assert json.loads(audit_log.read_text(encoding="utf-8").splitlines()[0])["policy_id"] == "cli-policy"


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
