---
title: "ClaimWright Review Record for the Governed Memory Preprint Draft"
date: 2026-07-28
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
| Contradiction cases and adjudication | `supported_by_primary_evidence` | `src/groundrecall/contradictions.py`, `tests/test_contradictions.py`, `src/groundrecall/graph_augment.py`, `tests/test_graph_augment.py` | State that heuristic cue generation is review-gated and that robust semantic auto-detection/resolution remains future work. |
| Release controls and federation quarantine | `supported_by_primary_evidence` | `src/groundrecall/federation.py`, `src/groundrecall/export_guardrails.py`, `tests/test_federation.py`, `tests/test_export_guardrails.py` | Do not present as enterprise IAM or complete DLP. |
| ClaimWright as policy framework | `supported_by_primary_evidence` for existence and selected adapter enforcement | ClaimWright policy files and role/check documents; GroundRecall policy-plugin contract and ClaimWright-style directory adapter | State that ClaimWright is an example policy framework under GroundRecall's bounded plugin contract, not a mandatory dependency or complete policy engine. |
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
| Privacy, provenance governance, distributed systems, IAM, and security literature | B | Expanded source pass accepted with caveats | Added NIST AI RMF, NIST SP 800-53, NIST SP 800-207, W3C PROV, SLSA, Sigstore, The Update Framework, distributed access control, Permission-Aware RAG, information-flow control, decentralized labels, capability security, append-only transparency logs, and provenance-security sources. This supports adjacent-literature framing but remains short of a systematic review or security proof. |
| Long-memory and GraphRAG benchmark literature | B | Expansion accepted for evaluation framing | Added LongMemEval, LoCoMo, MemoryAgentBench, LoCoMo-Plus, GraphRAG, GraphRAG survey, GraphRAG-Bench, and Agentic GraphRAG sources. These support benchmark-target and related-work framing, not claims that GroundRecall has been benchmarked on them. |
| Persistent AI-memory privacy/security literature | B | Initial expansion accepted | Added Agent-Memory Protocol, CAMS, and Permission-Aware RAG. These support privacy, memory-injection, memory-extraction, purpose-bound memory, and retrieval-authorization framing, while leaving deeper privacy-leakage review as future bibliography work. |

## Adversarial Review Memo

The strongest objections are predictable and should remain visible:

1. The paper could sound as if it proves safety benefits. The current evidence does not do that. The draft now confines itself to engineering evidence and design argument.
2. The related-work section could be criticized as selective. The bibliography is explicitly seeded and should be expanded before submission.
3. The phrase "memory layers should be governed" is normative. That is acceptable in manifesto mode, but the claim should not be disguised as a benchmark result.
4. GroundRecall’s implementation is local-first and file-backed. Claims about federation, policy, and trust should remain scoped to prototype mechanisms.
5. ClaimWright-style policy content is now enforceable through GroundRecall's bounded policy-plugin adapter on selected surfaces. The draft should keep that claim scoped and avoid implying complete policy-engine or production-IAM coverage.
6. Confidence support is structured and exportable, but not yet a validated Bayesian confidence system. The appendix explicitly blocks that overclaim.
7. Contradiction handling depends primarily on explicit contradiction links. Heuristic contradiction cueing can propose review candidates, but robust automatic semantic contradiction detection and resolution remain future work.
8. Public-facing artifacts must avoid absolute local paths. The appendix previously contained local paths; those were replaced with repository-level references.

## Publication Gate Result

| Gate | Result | Notes |
| --- | --- | --- |
| Unresolved high-risk public claims | Pass with caveats | High-risk claims are either scoped, caveated, or listed as not made/future work. |
| Fabricated or unverified citations | Pass for current cited set | Current references have DOI/source links. Broader bibliography remains an expansion task. |
| Private material in public output | Pass after correction | Absolute local paths were removed from the appendix. |
| Destructive irreversible action | Pass | Documentation-only changes; git revertable. |
| Contradicted or stale claims | Pass with caveats | No known contradicted/stale claims relied on for public argument; future literature expansion may create revision duties. |

Release status: conditionally suitable for internal/public draft review, pending human publication approval. The draft is closer to final-public-safe after initial bibliography expansion and reproducible demonstrations, but it is not final-public-safe because the bibliography is still not systematic and final human publication approval remains open.

## Review Results Applied

| Review result | Applied change |
| --- | --- |
| Avoid implying proof of safety benefits. | Abstract and prototype sections now say the systems demonstrate implementable local controls, not validated safety outcomes. |
| Avoid overbroad claims about the literature. | Related-work language now refers to "the sources reviewed for this draft" and "within this reviewed set" rather than all memory-layer literature. |
| Keep GroundRecall claims local/prototype-scoped. | Abstract, prototype, evaluation, and limitations language now emphasizes local prototype evidence and incomplete production features. |
| Keep ClaimWright integration scoped. | Updated wording states that GroundRecall owns the policy-plugin contract and supports a ClaimWright-style directory adapter on selected enforcement surfaces. Limitations now keep policy coverage scoped rather than calling it absent. |
| Avoid Bayesian confidence overclaim. | Existing Epistemap/confidence caveats were retained; no Bayesian calibration claim was added. |
| Keep robust semantic contradiction detection as future work. | Contradiction caveats now distinguish implemented heuristic review-gated cueing from unclaimed robust semantic detection/resolution. |
| Expose final-public-safety status. | The evaluation section now states that the draft is suitable for internal/public draft review but not final-public-safe until bibliography scope and human publication approval are resolved. |
| Resolve public/private path issue. | Repository-level references remain in the appendix; no absolute local paths are used for public evidence references. |
| Broaden bibliography. | Added governance, provenance, access-control, zero-trust, and supply-chain-security entries to the seed BibTeX, CiteGeist database, exported BibTeX, bibliography notes, draft related-work text, and references. |
| Complete second bibliography expansion targets. | Added long-memory benchmarks, GraphRAG surveys/benchmarks, persistent AI-memory privacy/security sources, permission-aware retrieval, information-flow control, capability security, append-only transparency logs, and provenance-security entries to the seed bibliography, bibliography notes, draft related-work text, references, and claim-evidence matrix. |
| Add empirical demonstrations. | Added `examples/preprint/run_preprint_demos.py`, `examples/preprint/README.md`, and generated JSON outputs for provenance/promotion, contradiction adjudication, release filtering, federation quarantine, local authority, and the policy-plugin boundary. |
| Add search-mode timing indication. | Added `search_mode_timing.json` as an internal synthetic-store timing indication for indexed search versus indexed search plus graph expansion. The draft states that this is not a comparison with external memory-layer products or a recall-quality benchmark. |
| Update graph-maintenance evidence after knowledge-graph backfill work. | Added bounded graph backfill and maintenance language to the draft and claim-evidence matrix, including review-gated relation candidates, private/no-export screening, diagnostics, maintenance profiles, state files, locks, stale-lock recovery, and extractor-mode caveats. |

## Post-Action Check

| Check | Result |
| --- | --- |
| Files changed | Added this review record; updated the draft, bibliography, BibTeX exports, claim-evidence matrix, demonstration runner, generated demonstration outputs, and regenerated HTML outputs. |
| Claims introduced/modified | Test-suite claim changed to a dated concrete result: 234 tests passed on 2026-07-28. Appendix support references remain repository-level descriptions. Demonstration claims are backed by generated JSON outputs, including the policy-plugin boundary walkthrough and search-mode timing indication. Graph-maintenance claims are backed by current code/tests and are scoped to bounded, heuristic, review-gated backfill. |
| Citations recorded | Added governance/security/provenance citations: NIST AI RMF, NIST SP 800-53, NIST SP 800-207, W3C PROV Overview, W3C PROV-DM, SLSA provenance, Sigstore, The Update Framework, Golightly et al. distributed access-control survey, LongMemEval, LoCoMo, MemoryAgentBench, LoCoMo-Plus, GraphRAG, GraphRAG survey, GraphRAG-Bench, Agentic GraphRAG, Agent-Memory Protocol, CAMS, Permission-Aware RAG, decentralized IFC, decentralized label model, capabilities/confused deputy, RFC 9162, append-only authenticated dictionaries, and provenance-security survey. |
| Assumptions visible | The review assumes the local ClaimWright repository represents the applicable review policy; it does not assert external validation of ClaimWright. |
| Unresolved risks | Bibliography is broader but not systematic; privacy-leakage and distributed-revocation coverage should deepen before submission; policy-plugin enforcement covers selected surfaces but is not complete production IAM or all mutation paths; robust semantic contradiction detection/resolution remains future work; graph backfill uses heuristic candidates rather than validated semantic extraction; human publication approval remains open. |
| Tasks opened | Remaining gaps are now systematic-review scope, deeper privacy-leakage and distributed-revocation bibliography, benchmark evaluation design, final publication approval, and future feature work, not absence of initial demonstrations or absence of the review-requested expansion categories. |
| Capacity used | Local inspection, web source verification, CiteGeist ingest/export, Pandoc rendering, demo execution, and pytest; no GPU use. |
| Branch outcome | Conservative/balanced branch chosen: keep manifesto framing but tighten evidence scope and gate overclaims. |
| Broader review trigger | Yes. Before submission, run a broader literature/security/governance review and add reproducible demonstrations. |
| Scientific virtues | The pass preserved veracity, skepticism, humility to evidence, public defensibility, and provenance fairness by weakening unsupported implications and making gaps explicit. |
