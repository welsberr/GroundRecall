# R7 end-to-end readiness evaluation

R7 is the final read-only backfill/e2e readiness surface for the Library
argument-ingestion roadmap. It exercises the R0 contract and R1 handoff
validation, R2 anchored-bundle coverage, R3 audit, R4 candidate lineage, R5
evidence scaffolding, and R6 manifest/preflight chain on one supplied bundle.

The API is:

```python
evaluate_library_argument_bundle(bundle, r5=None, target="public")
```

When `r5` is omitted, R7 generates the deterministic R5 candidate packet in
memory. When it is supplied, the packet is copied and inspected. The report
contains phase statuses, stable artifact IDs and counts, unresolved gaps,
release blockers, and two separate coverage lists: automated checks supplied
by GroundRecall and corpus-specific work still requiring source reading,
expert review, rights/provenance completion, or release approval.

CLI:

```text
groundrecall argument-bundle-r7 INPUT.json REPORT.json [--r5 R5.json]
```

The command writes only the requested report file. It never opens a
GroundRecall database, promotes records, or publishes. Use
`--fail-on-blockers` when a CI job should exit 2 for a non-ready report;
without it, a report is emitted successfully even when blockers are found.

All generated output remains private/draft and is deterministic for the same
inputs and options. Candidate lineage, lexical matching, citation topology,
and R5 scaffolding are review aids, not truth or support judgments.
