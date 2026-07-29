---
title: "ClaimWright Review Record for the Governed Memory Preprint Draft"
date: 2026-07-29
review_id: "PRR-08"
---

## Review Scope

Review path: `docs/preprint/claimwright-review.md`

Reviewed artifacts:

- `docs/preprint/2026-elsberry-governed-memory-layer-principles-r01-source.md`
- `docs/preprint/2026-elsberry-governed-memory-layer-principles-r01-source.html`
- `docs/preprint/2026-elsberry-governed-memory-layer-principles-r01.md`
- `docs/preprint/2026-elsberry-governed-memory-layer-principles-r01.html`
- `docs/preprint/2026-elsberry-governed-memory-layer-principles-r01.pdf`
- `docs/preprint/claim-evidence-matrix.md`
- `docs/preprint/memory-layer-bibliography.md`
- `docs/preprint/memory-layer-citegeist-export.bib`
- `docs/preprint/citegeist-memory-layer.sqlite3`
- `docs/preprint/threat-model.md`
- `examples/preprint/out/revision_evidence_snapshot.json`

Applied ClaimWright materials from `/home/netuser/bin/ClaimWright` at commit
`6d85ff7`:

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

This review evaluates the updated draft after PRR-07 bibliography expansion.
It does not treat ClaimWright policy findings as external validation of
ClaimWright itself.

## Pre-Action Check

| Check | Result |
| --- | --- |
| Action classification | Non-trivial review of public-facing draft, appendices, evidence matrix, bibliography, and threat model. |
| Public/private status | Public-facing manuscript artifacts; local absolute paths may be mentioned only as review provenance, not as public evidence URLs. |
| Reversibility | Reversible through git. |
| Evidence standard | Implementation claims require code/test/demo anchors; related-work claims require source or bibliography support; limitations require explicit future-work status. |
| Reputational risk | Moderate. The draft argues a normative manifesto thesis and connects it to local prototypes. |
| Adversarial review need | Required because the draft makes governance/security claims and discusses memory-layer risks. |
| Model/tool suitability | Local repository inspection, ClaimWright role/check files, CiteGeist artifacts, rendered draft review, Pandoc, and pytest are appropriate. |
| Durable memory touch | Documentation and review artifacts only; no GroundRecall memory store changed. |
| Scientific virtues | Review emphasized veracity, skepticism, humility to evidence, public defensibility, provenance fairness, and explicit uncertainty. |

## Claim Auditor Findings

| Claim area | Recommendation | Evidence | Required restraint |
| --- | --- | --- | --- |
| Governed memory as required property set | `supported_but_contested` | Design argument; related-work comparison; claim-evidence matrix | Keep as manifesto/design thesis, not empirical proof. |
| GroundRecall prototype controls | `supported_by_primary_evidence` | Current code, tests, demos, IF status table, revision evidence snapshot | Scope to local file-backed prototype; avoid production platform language. |
| Institutional federation IF-00 through IF-14 table | `supported_by_primary_evidence` | `docs/institutional-federation-implementation-roadmap.md`; `docs/implemented-features-summary.md`; `docs/preprint/claim-evidence-matrix.md` | "Partial" rows must remain partial; do not imply completed network transport, IAM, or publication gating. |
| Policy-plugin and ClaimWright adapter claim | `supported_by_primary_evidence` for selected surfaces | `src/groundrecall/policy.py`; `tests/test_policy_plugins.py`; ClaimWright fixtures | ClaimWright is example policy content under GroundRecall's contract, not mandatory dependency or complete policy authority. |
| MCP governance claim | `supported_with_caveat` | `src/groundrecall/mcp.py`; `tests/test_mcp.py`; policy coverage open items | MCP policy remains caller-supplied; no mandatory server-side policy claim. |
| Contradiction/adjudication claim | `supported_by_primary_evidence` | `src/groundrecall/contradictions.py`; `tests/test_contradictions.py`; graph cue tests | Robust automatic semantic contradiction detection remains future work. |
| Bibliography/source-review claim | `supported_with_completeness_caveat` | CiteGeist SQLite database; seed/export BibTeX; bibliography notes | Focused bibliography only; not a systematic review. |
| Security/privacy risk framing | `supported_for_problem_framing` | Agent-Memory Protocol, CAMS, Permission-Aware RAG, AgentPoison, MEXTRA, MSA, FragFuse | Sources support risk framing and design motivation, not GroundRecall production security effectiveness. |
| Evaluation and demo claims | `requires_revision` | Manuscript Section 9 and Section 10; demo manifest with 15 outputs | The prose is stale: it still says demos/bibliography are future needs and lists only early demo outputs. |

## Citation Reviewer Findings

| Citation set | Tier | Status | Notes |
| --- | --- | --- | --- |
| Memory-layer systems and surveys | A/B | Accepted | Generative Agents, MemGPT, HippoRAG, A-MEM, Mem0, MemoryOS, MemOS, AriGraph, KG/RAG alignment, and ACM TOIS memory survey support related-work framing. |
| Governance, provenance, access-control, zero-trust, and supply-chain sources | A/B | Accepted | NIST, W3C PROV, SLSA, Sigstore, TUF, IFC, decentralized labels, capability/confused-deputy, transparency logs, and provenance-security sources support adjacent-pattern framing. |
| Long-memory and GraphRAG benchmark sources | B | Accepted for evaluation-target framing | LongMemEval, LoCoMo, MemoryAgentBench, LoCoMo-Plus, GraphRAG, GraphRAG survey, GraphRAG-Bench, and Agentic GraphRAG do not support any GroundRecall benchmark-result claim. |
| Persistent-memory privacy/security additions from PRR-07 | B | Accepted for risk framing | AgentPoison, MEXTRA, MSA, FragFuse, CAMS, Agent-Memory Protocol, and Permission-Aware RAG materially improve coverage of poisoning, extraction, MCP exfiltration, access-control bypass, purpose-bound memory, and retrieval authorization. |
| Data-lineage policy addition from PRR-07 | B | Accepted for governance framing | Honest Computing supports the connection between demonstrable lineage/provenance and process-sensitive policy. |
| SSRN/preprint-only source | C/B with venue caveat | Accepted only with caveat | Agentic GraphRAG survey remains useful but should be replaced or supplemented if a formal venue version appears. |

Citation result: no fabricated citation was detected in the reviewed set. The
bibliography is materially broader after PRR-07, but it remains focused rather
than systematic.

## Adversarial Review Memo

The strongest objections after PRR-07 are:

1. The title and thesis are intentionally normative. That is acceptable in
   manifesto mode, but the paper must not imply the properties are proven by
   user studies, benchmarks, or formal security analysis.
2. The PRR-07 security citations make the risk case stronger. They also raise
   the bar for implementation wording: GroundRecall should be described as
   implementing governance controls, not as preventing those attack classes in
   production.
3. The evaluation section still contains stale review-status language. It says
   the paper needs bibliography expansion and stable reproducible
   demonstrations, even though PRR-02/PRR-07 now provide initial versions. That
   should be revised to say the remaining gap is final review, systematic-scope
   choice, and broader evaluation.
4. The demonstration section lists only the early demonstration outputs, while
   the manifest now records fifteen outputs. That mismatch weakens the
   claim-to-evidence discipline and should be fixed before the next rendered
   revision.
5. The paper cites internal engineering timing. The caveats are currently
   adequate, but the timing should remain explicitly non-comparative and
   non-reproducible by outside readers unless a fixture is published.
6. The IF status table is useful but could be criticized as too much internal
   implementation detail for the main paper. Keeping it in the appendix is the
   defensible placement.

## Publication Gate Result

| Gate | Result | Notes |
| --- | --- | --- |
| Unresolved high-risk public claims | Pass with caveats | High-risk implementation/security claims are scoped to prototype evidence and limitations. |
| Fabricated or unverified citations | Pass | Reviewed citations have source links, DOI/arXiv/source pages, or explicit venue caveats. |
| Private material in public output | Pass with path caveat | Public evidence references use repository-relative paths; review provenance itself includes local absolute paths only to identify reviewed repositories. |
| Destructive irreversible action | Pass | Documentation-only review; git-revertable. |
| Contradicted or stale claims | Soft gate | Two stale manuscript statements need PRR-09 cleanup: prior-review/future-demo language and the incomplete demo-output list. |
| Final human publication approval | Required | ClaimWright does not substitute for author approval. |

Release status: conditionally suitable for internal/public draft review after
PRR-09 applies the must-fix wording updates. Not final-public-safe for
submission until human publication approval and final bibliography/evidence
scope decisions are complete.

## Findings Grouped For Action

### Must Fix Before Revision

1. Update Section 9 review-status language. The draft currently says the paper
   needs a broader governance/security bibliography pass and stable
   reproducible demonstrations. Initial bibliography expansion and demos now
   exist; remaining needs should be reframed as final human approval,
   systematic-review-scope choice, and future empirical/security evaluation.
2. Update Section 10 demonstration-output list from the early seven-output
   list to the current fifteen-output manifest, or point directly to the
   manifest to avoid another stale list.

### Should Fix Before Submission

1. Decide whether the final paper claims only focused related-work coverage or
   adopts a systematic-review protocol. Do not drift between the two.
2. Replace or supplement preprint-only / non-archival sources if peer-reviewed
   versions appear before submission.
3. Add a small reproducible public fixture if timing numbers remain in the
   paper; otherwise keep them explicitly internal and illustrative.
4. Consider a compact "security claims not made" paragraph near the PRR-07
   security-source discussion.

### Future Work

1. Benchmark GroundRecall against LongMemEval, LoCoMo, MemoryAgentBench, and
   GraphRAG-Bench only after benchmark adapters exist.
2. Add direct tests or demonstrations for persistent-memory attack resistance
   only if the implementation actually claims mitigation of those attacks.
3. Implement mandatory MCP server policy configuration, post-render
   institutional-view filtering, publication-gate preflight, distributed
   withdrawal propagation, and exceptional-erasure execution before claiming
   those capabilities.

## Post-Action Check

| Check | Result |
| --- | --- |
| Files changed by review step | This review record and generated rendered artifacts only. |
| Claims introduced | No new implementation claim; the review adds findings and gates. |
| Citations reviewed | 41-entry focused bibliography, with PRR-07 additions included. |
| Assumptions visible | The local ClaimWright repository supplies the policy/check stance; this is not external validation of ClaimWright. |
| Unresolved risks | Stale demo/review wording remains for PRR-09; final publication approval remains required; systematic-review scope remains undecided. |
| Branch outcome | Conservative/balanced branch: keep manifesto framing, accept focused bibliography, require wording cleanup before next rendered revision. |
| Broader review trigger | Yes. PRR-09 must apply must-fix items before the next substantive preprint revision. |
