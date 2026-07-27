# GroundRecall Preprint Claim-To-Evidence Matrix

Date: 2026-07-26

This matrix maps paper claims to current implementation evidence and known caveats. It is intended to keep the preprint claims defensible.

| Preprint claim | Implementation artifact | Test / evidence | Caveat |
| --- | --- | --- | --- |
| GroundRecall stores durable memory as typed, provenance-linked records. | `src/groundrecall/models.py`, `src/groundrecall/store.py` | Store round-trip and snapshot tests. | File-backed prototype, not a distributed database. |
| GroundRecall preserves evidence rather than flattening memory into ungrounded summaries. | Observation/claim provenance fields; snapshot/export paths. | Query/export/store tests; deterministic JSON snapshots. | Extraction accuracy is not guaranteed by the store. |
| Confidence is structured and reviewable. | `src/groundrecall/confidence.py`; Epistemap integration. | Confidence profile and migration tests. | Full calibration/evaluation remains future work. |
| Ordinary forgetting is non-destructive lifecycle management. | Expiry/supersession/retraction/applicability metadata and confidence handling. | Confidence and temporal query behavior tests. | Exceptional erasure workflow not complete. |
| Contradictions are reviewable first-class objects. | `ContradictionCaseRecord`; `src/groundrecall/contradictions.py`. | `tests/test_contradictions.py`; query and diagnostics tests. | Depends on explicit contradiction links; no semantic auto-detection yet. |
| Contradiction adjudication preserves disagreement history. | `groundrecall contradictions adjudicate`; adjudication records with `subject_type="contradiction_case"`. | CLI/adjudication tests. | Does not rewrite or automatically re-rank underlying claims yet. |
| Export/federation enforces release-level constraints. | `src/groundrecall/federation.py`, `src/groundrecall/export_guardrails.py`. | Federation tests for public/internal/confidential/privileged/private behavior. | Correct classification still depends on input metadata and review. |
| Signed bundles detect tampering. | Federation bundle manifest, content hash, HMAC/Ed25519 verification. | Signature/hash verification tests. | Key management is local prototype level. |
| Imported memory is quarantine-first. | `import_federation_bundle_to_quarantine`; promotion planning/apply functions. | Quarantine and promotion tests. | No hosted review service. |
| Promotion is local-policy-gated. | `FederationLocalPolicy`, scoped grants, audit events. | Policy, scope, role-directory, and audit tests. | Not integrated with enterprise IAM. |
| Public-key trust distribution is locally capped. | Signed keysets and role-directory publication/import. | Ed25519 keyset and role-directory tests. | Requires pinned signer keys; no key transparency service. |
| GroundRecall aligns with memory-layer research but contributes governance controls. | Preprint memory-layer bibliography and architecture note. | CiteGeist-seeded bibliography; source-verified annotations. | Needs broader literature expansion before manuscript submission. |

## Immediate Evidence Gaps

- Reproducible demonstration scripts under `examples/preprint/`.
- A generated paper table mapping tests to claims.
- A manuscript-ready comparative table distilled from `docs/preprint/memory-layer-comparative-analysis.md`.
- Bibliography expansion into privacy/security/provenance governance literature.
