# Preprint Revision Readiness Roadmap

Date: 2026-07-29
Status: active revision-preparation plan

This roadmap starts from the committed IF-14 state in the canonical
repositories under `/home/netuser/bin`. Its purpose is to get the manuscript
ready for a substantive revision without continuing open-ended feature work.

## Revision Gate

Revise the preprint after these artifacts exist and are current:

1. a generated revision evidence snapshot;
2. refreshed reproducible demonstrations for the institutional federation
   slices;
3. updated implemented-feature summary through IF-14;
4. updated claim-to-evidence matrix through IF-14;
5. updated limitation language matching current policy coverage;
6. a compact IF-00 through IF-14 status table for the paper or appendix;
7. focused bibliography/source review updates for governed memory,
   permission-aware retrieval, provenance, access control, and graph memory.

## Work Packages

### PRR-01: Revision Evidence Snapshot

Status: in progress.

Create a deterministic JSON artifact that records:

- GroundRecall and ClaimWright repository heads;
- institutional federation capability summary;
- policy coverage summary and open items;
- institutional conformance summary;
- preprint demonstration output inventory;
- explicit paper-claim boundaries.

Exit:

- the generator is committed and tested;
- the generated artifact is reproducible from the repository checkout;
- the artifact distinguishes engineering evidence from production
  certification.

### PRR-02: Institutional Demonstration Expansion

Status: completed on 2026-07-29.

Added or refreshed JSON demonstrations for:

- prior-work discovery, including negative/inconclusive work;
- signed catalog discovery;
- incremental subscription/change-bundle quarantine and acknowledgement;
- multi-party review/quorum and dissent preservation;
- custody handoff/retirement planning;
- release pack and withdrawal;
- policy-gated institutional writes and custody-event preflight.

Exit:

- each demo has a stable JSON output under `examples/preprint/out/`;
- each demo has a corresponding row in the claim-to-evidence matrix;
- the demo manifest names every generated output.

Follow-up: PRR-04 must add corresponding claim-to-evidence rows for the new
demonstrations before manuscript revision.

### PRR-03: Implemented Feature Summary Refresh

Status: completed on 2026-07-29.

Update `docs/implemented-features-summary.md` through IF-14.

Must include:

- institutional federation IF-06 through IF-14;
- policy coverage counts;
- durable mutation coverage counts;
- remaining partial routes;
- the single intentionally future destructive exceptional-erasure route.

Exit:

- Markdown and HTML summaries are current;
- claims are scoped to implemented/tested behavior.

### PRR-04: Claim-To-Evidence Matrix Refresh

Status: completed on 2026-07-29.

Update Appendix A for:

- conformance evidence report;
- policy-gated institutional writes;
- custody-event policy preflight;
- MCP institutional tools;
- release packs/withdrawal;
- institutional views;
- custody/retirement planning;
- multi-party review/feedback;
- subscriptions/change bundles.

Exit:

- each new implementation claim has code and test anchors;
- each limitation is stated as future work or scoped caveat.

### PRR-05: Limitation And Threat-Model Alignment

Align the manuscript and threat model with the current state:

- no production IAM claim;
- no network transport or distributed consensus claim;
- MCP policy remains caller-supplied;
- institutional views still need post-render policy filtering;
- release pack/withdrawal still need direct publication-gate preflight;
- semantic contradiction detection remains review-gated/future;
- exceptional erasure execution remains intentionally future.

Exit:

- limitation language matches `build_policy_coverage_report()`;
- no manuscript claim outruns the evidence snapshot.

### PRR-06: IF Status Table

Create a compact IF-00 through IF-14 table for the paper appendix.

Columns:

- package ID;
- implemented status;
- main code evidence;
- main test evidence;
- remaining caveat.

Exit:

- the table is derived from committed docs/reports where practical;
- it is short enough for the manuscript or appendix.

### PRR-07: Focused Bibliography Update

Perform a bounded bibliography update for:

- governed or persistent AI memory;
- permission-aware RAG/retrieval authorization;
- provenance-aware data governance;
- access control and information-flow control;
- GraphRAG and knowledge-graph memory;
- privacy leakage and memory-injection/extraction concerns.

Exit:

- bibliography additions are verified;
- the related-work section remains framed as focused coverage, not a systematic
  review unless a systematic-review protocol is actually added.

## Do Not Block Revision On

- network federation transport;
- CRDT merge;
- hosted review UI;
- production IAM;
- complete distributed revocation;
- exceptional erasure execution;
- broad benchmark comparisons against other memory-layer systems.

Those remain future-work items unless separately prioritized.
