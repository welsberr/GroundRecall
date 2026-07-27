---
title: "ClaimWright Review Record for the Governed Memory Preprint Draft"
date: 2026-07-27
---

## Review Scope

Reviewed artifacts:

- `docs/preprint/preprint-draft.md`
- `docs/preprint/preprint-draft.html`
- `docs/preprint/claim-evidence-matrix.md`
- `docs/preprint/claim-evidence-matrix.html`

Applied ClaimWright materials:

- `MOU.md`
- `policies/principles.yaml`
- `policies/enforcement.yaml`
- `policies/claim_states.yaml`
- `checks/pre_action.yaml`
- `checks/post_action.yaml`
- `roles/claim-auditor.md`
- `roles/citation-reviewer.md`
- `roles/adversarial-reviewer.md`
- `roles/publication-gatekeeper.md`

## Pre-Action Check

| Check | Result |
| --- | --- |
| Action classification | Non-trivial review of public-facing draft artifacts. |
| Public/private status | Public-facing manuscript and appendix materials; local paths and private material require hard-gate screening. |
| Reversibility | Reversible through git. |
| Evidence standard | Implementation claims require code/test anchors; related-work claims require verified source or bibliography support; future-work claims require explicit limitation language. |
| Reputational risk | Moderate. Overclaiming implementation, comparative performance, or citation support would weaken the paper. |
| Adversarial review need | Required because the draft makes a design manifesto claim and uses local prototypes as evidence. |
| Model/tool suitability | Local repository inspection, grep, Pandoc rendering, and pytest are appropriate. |
| Capacity risk | Low. Full local test suite ran quickly. |
| Durable memory touch | Documentation and review artifacts only; no GroundRecall memory store changed. |
| Scientific virtues | Review emphasized veracity, skepticism, humility to evidence, provenance fairness, and public defensibility. |

## Claim Auditor Findings

| Claim area | State recommendation | Evidence | Required restraint |
| --- | --- | --- | --- |
| Governed memory as a necessary property set | `supported_but_contested` | Design argument, related-work comparison, and implemented governance features | Present as a normative/design thesis, not an empirical proof. |
| GroundRecall typed provenance-preserving record model | `supported_by_primary_evidence` | `src/groundrecall/models.py`, `src/groundrecall/store.py`, `tests/test_groundrecall_store.py` | Scope to current file-backed prototype. |
| Review-gated promotion | `supported_by_primary_evidence` | `src/groundrecall/promotion.py`, `tests/test_groundrecall_promotion.py` | Do not imply complete hosted review workflow. |
| Structured confidence and temporal applicability | `supported_by_primary_evidence` | `src/groundrecall/confidence.py`, `tests/test_confidence_profiles.py`, `tests/test_confidence_migration.py` | Do not claim full Bayesian calibration or empirical confidence validation. |
| Contradiction cases and adjudication | `supported_by_primary_evidence` | `src/groundrecall/contradictions.py`, `tests/test_contradictions.py` | State that semantic auto-detection is future work. |
| Release controls and federation quarantine | `supported_by_primary_evidence` | `src/groundrecall/federation.py`, `src/groundrecall/export_guardrails.py`, `tests/test_federation.py`, `tests/test_export_guardrails.py` | Do not present as enterprise IAM or complete DLP. |
| ClaimWright as policy framework | `supported_by_primary_evidence` for existence; `plausible_under_supported` for future integration | ClaimWright policy files and role/check documents | State that ClaimWright is an example and is not yet enforced inside GroundRecall. |
| CiteGeist bibliography support | `supported_by_primary_evidence` for seed artifacts | `docs/preprint/citegeist-memory-layer.sqlite3`, BibTeX export, bibliography notes | State that bibliography is seeded, not systematic or complete. |
| Epistemap confidence/graph layer | `supported_by_primary_evidence` for adapter surfaces | `src/groundrecall/epistemap_adapter.py`, `tests/test_epistemap_adapter.py` | Do not imply broad posterior validation. |

## Citation Reviewer Findings

| Citation set | Tier | Status | Notes |
| --- | --- | --- | --- |
| Generative Agents, MemGPT, HippoRAG, A-MEM, Mem0, MemoryOS, MemOS, AriGraph | A | Accepted | Directly supports the claim that recent systems foreground durable memory, retrieval, graph memory, production memory, and memory-OS abstractions. |
| KG/RAG alignment paper | B | Accepted | Supports the narrower point that graph representation and linearization affect downstream LLM use of graph knowledge. |
| ACM TOIS memory-mechanism survey | A | Accepted | Supports general framing that LLM-agent memory is an identifiable technical subsystem with sources, forms, operations, and evaluation concerns. |
| ClaimWright local policy substrate | A for example-policy claim | Accepted with access caveat | Supports the existence and contents of the example policy framework, not external validation of ClaimWright. |
| CiteGeist local bibliography artifacts | A for seed-bibliography claim | Accepted with completeness caveat | Supports that bibliography seeding exists; does not support systematic-review completeness. |
| Privacy, provenance governance, distributed systems, IAM, and security literature | Unresolved | Needed for later draft | The current paper acknowledges production identity/security limits but does not yet cite a broader governance/security literature. |

## Adversarial Review Memo

The strongest objections are predictable and should remain visible:

1. The paper could sound as if it proves safety benefits. The current evidence does not do that. The draft now confines itself to engineering evidence and design argument.
2. The related-work section could be criticized as selective. The bibliography is explicitly seeded and should be expanded before submission.
3. The phrase "memory layers should be governed" is normative. That is acceptable in manifesto mode, but the claim should not be disguised as a benchmark result.
4. GroundRecall’s implementation is local-first and file-backed. Claims about federation, policy, and trust should remain scoped to prototype mechanisms.
5. ClaimWright is not yet an enforcement engine inside GroundRecall. The draft states this directly.
6. Confidence support is structured and exportable, but not yet a validated Bayesian confidence system. The appendix explicitly blocks that overclaim.
7. Contradiction handling depends on explicit contradiction links. Automatic semantic contradiction detection remains future work.
8. Public-facing artifacts must avoid absolute local paths. The appendix previously contained local paths; those were replaced with repository-level references.

## Publication Gate Result

| Gate | Result | Notes |
| --- | --- | --- |
| Unresolved high-risk public claims | Pass with caveats | High-risk claims are either scoped, caveated, or listed as not made/future work. |
| Fabricated or unverified citations | Pass for current cited set | Current references have DOI/source links. Broader bibliography remains an expansion task. |
| Private material in public output | Pass after correction | Absolute local paths were removed from the appendix. |
| Destructive irreversible action | Pass | Documentation-only changes; git revertable. |
| Contradicted or stale claims | Pass with caveats | No known contradicted/stale claims relied on for public argument; future literature expansion may create revision duties. |

Release status: conditionally suitable for internal/public draft review, pending human publication approval. The draft is not final-public-safe because bibliography expansion, reproducible demonstrations, and external governance/security citations remain open.

## Post-Action Check

| Check | Result |
| --- | --- |
| Files changed | Added this review record; updated the draft and claim-evidence matrix; regenerated HTML outputs. |
| Claims introduced/modified | Test-suite claim changed from "latest implementation pass" to a dated concrete result: 171 tests passed on 2026-07-27. Appendix support references were changed from absolute local paths to repository-level descriptions. |
| Citations recorded | No new external citations were added in this pass. Citation-review status was recorded for existing source sets. |
| Assumptions visible | The review assumes the local ClaimWright repository represents the applicable review policy; it does not assert external validation of ClaimWright. |
| Unresolved risks | Bibliography is not systematic; reproducible demonstration artifacts remain missing; ClaimWright is not yet enforced inside GroundRecall; semantic contradiction detection remains future work. |
| Tasks opened | Demonstration and bibliography gaps remain in `docs/preprint/claim-evidence-matrix.md`. |
| Capacity used | Local inspection, Pandoc rendering, and pytest; no network or GPU use in this pass. |
| Branch outcome | Conservative/balanced branch chosen: keep manifesto framing but tighten evidence scope and gate overclaims. |
| Broader review trigger | Yes. Before submission, run a broader literature/security/governance review and add reproducible demonstrations. |
| Scientific virtues | The pass preserved veracity, skepticism, humility to evidence, public defensibility, and provenance fairness by weakening unsupported implications and making gaps explicit. |
