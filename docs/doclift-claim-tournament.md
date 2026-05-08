# Doclift Claim Tournament

This benchmark is a small evaluation harness for comparing multiple
doclift prose-claim extraction strategies before changing the default
GroundRecall import behavior.

Current tracks:

- `conservative`: prefers higher precision and sentence-level claims.
- `broad`: allows paragraph-level claims and shorter sentence candidates to
  improve recall.

Judge criteria:

- maximize F1 against the benchmark gold claims
- prefer higher recall when F1 ties
- penalize meta or identity-claim noise
- prefer predicted claim counts close to the gold-set size

Fixture location:

- `tests/fixtures/doclift_claim_eval/`

Primary entrypoint:

- `groundrecall.doclift_claim_tournament.evaluate_doclift_claim_tracks(...)`

This is intentionally small and deterministic. It is meant to support an
iterative tournament workflow, not to serve as a full evaluation platform by
itself.
