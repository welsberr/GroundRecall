---
title: "Appendix A: Claim-To-Evidence Matrix"
date: 2026-07-27
---

This appendix substantiates the manuscript discipline that each substantive paper claim maps to one of five evidence classes:

1. implemented code;
2. test coverage;
3. reproducible demonstration;
4. bibliography or source analysis;
5. explicit future-work status.

The matrix is also a restraint mechanism. Claims with only normative support are stated as design recommendations. Claims about implementation are limited to current code and tests. Claims about comparative performance, production deployment, semantic contradiction detection, and broad safety outcomes are marked as future work or excluded.

## Evidence Classes

| Evidence class | Meaning in this paper | Acceptable manuscript use |
| --- | --- | --- |
| Implemented code | A feature exists in the GroundRecall, ClaimWright, CiteGeist, or Epistemap repositories. | Supports "the prototype implements" or "the system exposes" claims when scoped to the current repository state. |
| Test coverage | Automated tests exercise the behavior. | Supports engineering evidence claims, not broad empirical performance claims. |
| Reproducible demonstration | A command, example, or generated artifact can reproduce a paper-visible behavior. | Supports manuscript examples and appendix walkthroughs. |
| Bibliography/source analysis | External literature or source review supports the framing. | Supports related-work and comparative-positioning claims. |
| Future-work status | The repository or manuscript explicitly identifies a missing capability. | Supports limitation and roadmap claims only. |

## Core Manuscript Claims

| Manuscript claim | Evidence class | Supporting artifacts | Current status | Caveat / restraint |
| --- | --- | --- | --- | --- |
| Durable AI memory needs governance, not only retrieval. | Bibliography/source analysis; design argument | `docs/preprint/preprint-draft.md`; `docs/preprint/memory-layer-comparative-analysis.md`; `docs/preprint/memory-layer-bibliography.md`; `docs/preprint/memory-layer-citegeist-export.bib` | Supported as a normative/design thesis. | Not an empirical proof that governed memory improves productivity or safety outcomes. |
| Current memory-layer systems foreground persistence, retrieval, graph organization, personalization, and memory-OS abstractions. | Bibliography/source analysis | References to Generative Agents, MemGPT, HippoRAG, A-MEM, Mem0, MemoryOS, MemOS, AriGraph, KG/RAG alignment, and an ACM TOIS memory-mechanism survey in `docs/preprint/preprint-draft.md` | Supported for related-work framing. | Bibliography is seeded, not exhaustive. |
| Governed memory draws on adjacent governance, provenance, access-control, zero-trust, and supply-chain-security patterns. | Bibliography/source analysis | NIST AI RMF, NIST SP 800-53, NIST SP 800-207, W3C PROV, SLSA, Sigstore, The Update Framework, and distributed access-control survey entries in `docs/preprint/memory-layer-citegeist-export.bib` | Supported for initial adjacent-literature framing. | Still not a systematic review of all governance/security literature. |
| GroundRecall is complementary to performance-oriented memory layers. | Bibliography/source analysis; implemented code | `docs/preprint/preprint-draft.md`; `docs/preprint/memory-layer-comparative-analysis.md`; GroundRecall governance features listed below | Supported as comparative positioning. | No benchmark comparison against Mem0, HippoRAG, A-MEM, MemoryOS, or MemOS. |
| ClaimWright is one suitable policy framework, not a universal stance. | Implemented code; design argument | ClaimWright repository policy substrate; `docs/preprint/preprint-draft.md` policy-pluralism section | Supported as an example policy stance. | ClaimWright policy files are not yet enforced directly inside GroundRecall. |
| CiteGeist provides a source-review and bibliography workbench relevant to governed memory. | Implemented code; reproducible artifact; bibliography/source analysis | CiteGeist repository; `docs/preprint/citegeist-memory-layer.sqlite3`; `docs/preprint/memory-layer-citegeist-export.bib`; `docs/preprint/memory-layer-bibliography.md` | Supported for bibliography seeding and source-review framing. | The current bibliography is not comprehensive and does not yet include a formal systematic-review protocol. |
| Epistemap provides a confidence and knowledge-graph operation layer relevant to governed memory. | Implemented code; test coverage | Epistemap repository; `src/groundrecall/epistemap_adapter.py`; `tests/test_epistemap_adapter.py`; `tests/test_claim_evaluation_export.py` | Supported for adapter/export surfaces. | Broad confidence calibration and cross-repository posterior validation remain future work. |

## GroundRecall Implementation Claims

| Manuscript claim | Evidence class | Supporting code | Supporting tests / artifacts | Current status | Caveat / restraint |
| --- | --- | --- | --- | --- | --- |
| GroundRecall stores durable memory as typed records rather than raw chat history alone. | Implemented code; test coverage | `src/groundrecall/models.py`; `src/groundrecall/store.py`; `src/groundrecall/groundrecall_models.py`; `src/groundrecall/groundrecall_store.py` | `tests/test_groundrecall_store.py` | Supported. | File-backed local prototype, not a distributed database. |
| Observations, claims, concepts, relations, promotions, adjudications, contradiction cases, and snapshots are first-class record types. | Implemented code; test coverage | `src/groundrecall/models.py`; `src/groundrecall/store.py` | `tests/test_groundrecall_store.py`; `tests/test_groundrecall_promotion.py`; `tests/test_contradictions.py` | Supported. | The supported claim is limited to the implemented record set, not every possible governance object. |
| Provenance is preserved across source, observation, claim, query, and export flows. | Implemented code; test coverage | `src/groundrecall/store.py`; `src/groundrecall/query.py`; `src/groundrecall/export.py`; `src/groundrecall/review_export.py` | `tests/test_groundrecall_store.py`; `tests/test_groundrecall_query.py`; `tests/test_groundrecall_export.py`; `tests/test_export_guardrails.py` | Supported for stored/queryable/exportable provenance metadata. | Extraction correctness depends on upstream adapters and review; the store does not guarantee source interpretation quality. |
| Review-gated promotion prevents candidate material from silently becoming canonical memory. | Implemented code; test coverage | `src/groundrecall/promotion.py`; `src/groundrecall/groundrecall_promotion.py`; `src/groundrecall/lint.py` | `tests/test_groundrecall_promotion.py`; `tests/test_relation_review.py`; `tests/test_groundrecall_review_workspace.py` | Supported. | Review UI and workflow ergonomics are prototype-level. |
| GroundRecall can expose query bundles with supporting provenance, graph context, contradictions, and supersessions. | Implemented code; test coverage | `src/groundrecall/query.py`; `src/groundrecall/groundrecall_query.py`; `src/groundrecall/graph_augment.py` | `tests/test_groundrecall_query.py`; `tests/test_graph_augment.py`; `tests/test_graph_diagnostics.py` | Supported. | This is a retrieval and packaging claim, not a benchmark claim. |
| Confidence is structured and reviewable rather than only a scalar hint. | Implemented code; test coverage | `src/groundrecall/confidence.py`; `src/groundrecall/epistemap_adapter.py` | `tests/test_confidence_profiles.py`; `tests/test_confidence_migration.py`; `tests/test_epistemap_adapter.py` | Supported for confidence profiles, assessments, temporal blocks, and migration/readiness reports. | The paper must not claim Bayesian calibration unless Epistemap/GroundRecall implements and validates it explicitly. |
| Temporal validity and expiry affect current applicability without erasing historical support. | Implemented code; test coverage | `src/groundrecall/confidence.py`; `src/groundrecall/query.py`; model metadata fields | `tests/test_confidence_profiles.py`; `tests/test_groundrecall_query.py` | Supported for current-applicability handling. | Time-qualified contradiction handling and broader temporal benchmark coverage remain future work. |
| Ordinary epistemic maintenance is non-destructive. | Implemented code; test coverage; design argument | Supersession, retraction, expiry, contradiction, and adjudication fields across `src/groundrecall/models.py`, `src/groundrecall/confidence.py`, and `src/groundrecall/contradictions.py` | `tests/test_confidence_profiles.py`; `tests/test_contradictions.py`; `tests/test_groundrecall_promotion.py` | Supported as design and partial implementation. | Exceptional erasure remains separate and incomplete. |
| Contradictions can be represented as explicit reviewable cases. | Implemented code; test coverage | `src/groundrecall/contradictions.py`; contradiction case models in `src/groundrecall/models.py`; CLI routes in `src/groundrecall/cli.py` | `tests/test_contradictions.py` | Supported for explicit contradiction links and deterministic case generation. | Automatic semantic contradiction detection is not implemented. |
| Contradiction adjudication records decisions without rewriting underlying claims. | Implemented code; test coverage | `src/groundrecall/contradictions.py`; adjudication records in `src/groundrecall/models.py` | `tests/test_contradictions.py` | Supported. | Adjudication does not yet automatically re-rank every downstream query result. |
| Release-level classification constrains export and federation. | Implemented code; test coverage | `src/groundrecall/federation.py`; `src/groundrecall/export_guardrails.py` | `tests/test_federation.py`; `tests/test_export_guardrails.py` | Supported for `public < internal < confidential < privileged < private` controls and private/local-only behavior. | Correctness depends on accurate metadata and review classification. |
| Export guardrails prevent lower-release bundles from carrying higher-release records or private support references. | Implemented code; test coverage | `src/groundrecall/export_guardrails.py`; federation filtering in `src/groundrecall/federation.py` | `tests/test_export_guardrails.py`; `tests/test_federation.py` | Supported. | This is not a substitute for end-to-end data-loss-prevention tooling. |
| Federation bundles are signed and content-hashed. | Implemented code; test coverage | `src/groundrecall/federation.py` | `tests/test_federation.py` signature, hash, tampering, HMAC, and Ed25519 tests | Supported. | Key management is local prototype-level; no key transparency or enterprise PKI integration. |
| Imported federation bundles are quarantine-first. | Implemented code; test coverage | `import_federation_bundle_to_quarantine` and promotion functions in `src/groundrecall/federation.py` | `tests/test_federation.py` quarantine and promotion tests | Supported. | No hosted review UI or network polling layer. |
| Promotion from quarantine is local-policy-gated and conflict-aware. | Implemented code; test coverage | `src/groundrecall/federation.py` local policy, scoped grants, conflict planning, audit events | `tests/test_federation.py` policy, scoped grants, conflict, promotion, and audit tests | Supported. | No enterprise IAM integration. |
| A valid signature does not by itself create local authority. | Implemented code; test coverage; design argument | Local policy evaluation, accepted release levels, trust registries, scoped grants, role directory import caps in `src/groundrecall/federation.py` | `tests/test_federation.py` policy, trust-registry, keyset, and role-directory tests | Supported. | This is a local-authority design property, not a comprehensive security proof. |
| Trust registries record active, expired, revoked, and superseded key state. | Implemented code; test coverage | Trust registry functions in `src/groundrecall/federation.py` | `tests/test_federation.py` trust registry lifecycle tests | Supported. | Does not include a distributed revocation propagation mechanism. |
| Signed public keysets and signed role directories can be imported only with receiver-side caps. | Implemented code; test coverage | Public keyset and role-directory publication/import functions in `src/groundrecall/federation.py` | `tests/test_federation.py` signed keyset and role-directory tests | Supported. | Requires pinned signer keys and local policy decisions. |
| Federation of contradiction cases respects release and claim exportability constraints. | Implemented code; test coverage | Contradiction-case filtering in `src/groundrecall/federation.py` | `tests/test_federation.py`; `tests/test_contradictions.py` | Supported. | Cross-host semantic reconciliation remains future work. |
| Audit events are recorded for federation policy decisions. | Implemented code; test coverage | `append_federation_audit_event` and `build_federation_audit_event` in `src/groundrecall/federation.py` | `tests/test_federation.py` audit tests | Supported. | Audit storage is local file-backed; no tamper-evident external audit log. |

## Claims That Are Explicitly Not Made

| Excluded claim | Status | Reason |
| --- | --- | --- |
| GroundRecall outperforms Mem0, HippoRAG, A-MEM, MemoryOS, or MemOS on memory benchmarks. | Not claimed. | No comparative benchmark has been run. |
| Governed memory has been shown to improve user productivity or reduce all AI-agent risk. | Not claimed. | Current evidence is engineering evidence, not user-study or broad safety evidence. |
| GroundRecall automatically detects semantic contradictions. | Future work. | Current contradiction workflow starts from explicit contradiction links. |
| GroundRecall provides production identity management or enterprise access control. | Future work. | Current controls are local policy, key, role, and release-level mechanisms. |
| GroundRecall provides complete exceptional-erasure propagation. | Future work. | Ordinary epistemic maintenance is non-destructive; exceptional erasure remains a separate incomplete mechanism. |
| GroundRecall is a complete distributed memory platform. | Future work. | No network transport, polling layer, CRDT merge, hosted review UI, or release-pack publication workflow is implemented. |
| ClaimWright is the only acceptable policy framework. | Not claimed. | The manuscript treats ClaimWright as one suitable operational stance under policy pluralism. |
| GroundRecall confidence measures are fully Bayesian or empirically calibrated. | Not claimed. | Current implementation supports structured confidence profiles and Epistemap-compatible exports; validated Bayesian updating remains outside current evidence. |

## Demonstration Register

The current manuscript can cite implementation, tests, and a stable demonstration runner. The runner lives at `examples/preprint/run_preprint_demos.py` and writes JSON summaries under `examples/preprint/out/`.

| Demonstration | Evidence class | Artifact | Claim supported |
| --- | --- | --- | --- |
| Provenance and promotion walkthrough | Reproducible demonstration | `examples/preprint/out/provenance_promotion.json` | Candidate observations and claims can be reviewed, promoted, and queried with provenance. |
| Contradiction adjudication walkthrough | Reproducible demonstration | `examples/preprint/out/contradiction_adjudication.json` | Contradictions become explicit cases and can be adjudicated without rewriting claims. |
| Release filtering walkthrough | Reproducible demonstration | `examples/preprint/out/release_filtering.json` | Public export excludes internal/private records and reports findings. |
| Federation quarantine walkthrough | Reproducible demonstration | `examples/preprint/out/federation_quarantine.json` | Signed import verifies origin/integrity but still lands in quarantine before local promotion. |
| Local authority walkthrough | Reproducible demonstration | `examples/preprint/out/local_authority.json` | A valid signed bundle is insufficient for promotion without receiver-side local policy. |
| CiteGeist bibliography expansion | Reproducible artifact | `docs/preprint/citegeist-memory-layer.sqlite3`; `docs/preprint/memory-layer-citegeist-export.bib` | Source review and BibTeX export remain inspectable. |

## Appendix Use in the Manuscript

The main paper can cite this appendix when making engineering claims. The safest formulation is:

> Appendix A maps each substantive manuscript claim to code, tests, source analysis, reproducible artifacts, or future-work status.

That statement is stronger and more auditable than saying only that the project follows a claim-to-evidence discipline.
