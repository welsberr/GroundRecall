# R6 knowledge-basis manifests and downstream preflight

R6 adds a read-only boundary for the Library argument-bundle workflow. It
does not ingest, promote, write a GroundRecall database, or publish.

The manifest API is `compile_knowledge_basis_manifest(bundle, r5=...)`. It
records source IDs, source/version hashes, version and access timestamps,
claim IDs, R5 evidence-card/adjudication/dossier IDs, coverage and review
status, and unresolved gaps. Its IDs and JSON are deterministic for the same
inputs and it is always `release_level: private` and `review_state: draft`.

CLI:

```text
groundrecall argument-bundle-r6 manifest INPUT.json OUTPUT.json [--r5 R5.json]
```

The explicit preflight API is
`preflight_library_argument_bundle(bundle, r5=..., target="public"|"downstream")`.
It mechanically checks required review, provenance and hashes, citation
support/review, source spans, coverage completeness, rights metadata, private
records, and optional timestamp freshness (`max_age_days`). The report has
`passed` and `release_allowed`; a failed CLI preflight exits with status 2.

```text
groundrecall argument-bundle-r6 preflight INPUT.json REPORT.json \
  --r5 R5.json --target downstream [--max-age-days 365]
```

The report itself is private/draft, including when every gate passes. A
separate release system may inspect the explicit report; R6 never performs
that release or changes the input records.
