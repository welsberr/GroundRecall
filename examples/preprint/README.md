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

`search_mode_timing.json` reports a local synthetic-store timing comparison
between post-index FTS search and indexed search plus graph expansion. It is an
engineering indication for GroundRecall's query-mode tradeoff, not a benchmark
against external memory-layer products.
