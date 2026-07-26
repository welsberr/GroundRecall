from __future__ import annotations

import json
from pathlib import Path

import pytest

from groundrecall import federation
from groundrecall.federation import (
    FederationLocalPolicy,
    FederationPolicyError,
    FederationPolicyGrant,
    evaluate_federation_policy,
    export_federation_bundle,
    import_federation_bundle_to_quarantine,
    is_allowed_for_target,
    is_less_restrictive,
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
                actions=["export", "import"],
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
