# Preprint Demonstrations

These demonstrations generate reproducible JSON evidence for the governed-memory
preprint. They are intended to support engineering claims in
`docs/preprint/preprint-draft.md` and Appendix A.

Run from the repository root:

```bash
python examples/preprint/run_preprint_demos.py
```

By default, outputs are written to:

```text
examples/preprint/out/
```

The runner creates temporary GroundRecall stores, exercises public APIs, and
writes stable summary JSON files. It does not commit transient stores, private
material, or signing keys.

To generate a current revision evidence snapshot that records repository heads,
institutional federation summaries, policy coverage, conformance evidence, and
the demo-output inventory, run:

```bash
python examples/preprint/generate_revision_evidence.py
```

Generated summaries:

- `provenance_promotion.json`
- `contradiction_adjudication.json`
- `contradiction_candidate_review.json`
- `release_filtering.json`
- `federation_quarantine.json`
- `local_authority.json`
- `policy_plugin_boundary.json`
- `search_mode_timing.json`
- `manifest.json`
- `revision_evidence_snapshot.json`

`search_mode_timing.json` reports a local synthetic-store timing comparison
between post-index FTS search and indexed search plus graph expansion. It is an
engineering indication for GroundRecall's query-mode tradeoff, not a benchmark
against external memory-layer products.

`revision_evidence_snapshot.json` is an engineering evidence snapshot for
preprint revision. It is not production certification, benchmark superiority
evidence, legal compliance evidence, or a complete security proof.
