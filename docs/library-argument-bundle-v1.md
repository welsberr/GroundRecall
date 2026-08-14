# `library.argument_bundle.v1` handoff

Status: R4 deterministic handoff validation, draft extraction, read-only
auditing, and candidate-only claim-family/lineage generation. No promotion,
database write, or downstream UI is part of this phase.

GroundRecall owns this initial contract location:

- Schema: `docs/schemas/library.argument_bundle.v1.schema.json`
- Golden fixture: `docs/fixtures/library.argument_bundle.v1.golden.json`

## R1 handoff surface

`groundrecall.library_argument_bundle` provides validation, legacy review-state
adaptation, and canonical JSON serialization. Validation rejects unknown schema
versions, malformed records, duplicate IDs, invalid references, and inverted
spans. Public serialization requires every record to be public and rejects local
filesystem paths. IDs, hashes, spans, provenance, release levels, and review
states are preserved.

The equivalent CLI command is:

```text
groundrecall argument-bundle-export INPUT.json OUTPUT.json [--public]
```

## R3 audit and review queue surface

`groundrecall argument-bundle-audit INPUT.json OUTPUT.json` produces a stable,
private/draft audit envelope. It reports `claim_unreviewed`, missing or invalid
source spans, unresolved or invalid citation assertions, missing argument
links, incomplete coverage, and explicit `public_release_blocker` findings.
Each finding has a stable ID, priority, reason, subject ID/type, and
deterministic provenance. Each finding also produces a `needs_review` queue
candidate with the same private/draft boundary.

The API is `audit_library_argument_bundle(payload)` (and
`audit_library_argument_bundle_file`). It is intentionally read-only: it does
not call `GroundRecallStore`, write review-candidate files, alter the input,
or promote any bundle record. R1 validation can still be run separately; R3
auditing accepts malformed references so they become actionable review work.

R1/R2/R3 remain handoff-only: they do not ingest into, promote to, or write to
the GroundRecall database.

The bundle is an envelope around provenance-bearing records. It defines source,
document, version, and span identity before claims are interpreted. A span may
use character, line, page, or timestamp coordinates; multimedia uses
`locator_kind: "timestamp"` with seconds and may carry a speaker. Short quoted
text is optional and must remain subject to rights and release review.

The envelope includes claim instances, canonical claim references, argument
relations, citation assertions, lineage candidates, coverage audits, review
receipts, and a knowledge-basis manifest. Candidate relations, citations, and
lineage are assertions awaiting review, not conclusions produced by this
contract.

## R4 candidate alignment and lineage

`groundrecall argument-bundle-r4 INPUT.json OUTPUT.json` adds deterministic,
private/draft review candidates. Use `--canonical-references REFERENCES.json`
to compare claims with a JSON array of supplied references (each may provide
`canonical_claim_ref_id`, `namespace`, `key`, `label`, and `text`). Claims that
do not meet the threshold receive an `unresolved` canonical reference; supplied
matches remain `candidate`. `--threshold` defaults to `0.2` lexical Jaccard
similarity.

The API is `generate_r4_candidates(bundle, canonical_references=None)`. It
copies its input and returns exact `evidence_span_ids` for every generated
reference and lineage candidate. Lineage types include `shared_phrase`,
`shared_argument`, `independent_recurrence`, and `explicit_citation`.

Similarity and citation topology are observations about wording or graph
shape. They are not support, entailment, influence, or truth. Every R4 record
therefore carries `evidence_basis`, `truth_status: not_assessed`, rationale,
and deterministic provenance. Independent recurrence and shared argument are
reviewable hypotheses, not conclusions.

## Shared rules

- `schema_version` is exactly `library.argument_bundle.v1`.
- IDs are stable within a bundle and references use IDs rather than paths.
- Every durable record carries `release_level` (`private` or `public`) and a
  `review_state` (`draft`, `triaged`, `reviewed`, `promoted`, `public`,
  `private`, `verified`, or `deprecated`). These fields are independent: a reviewed record
  can still be private.
- Private is the safe default for generated or unresolved material. Public
  release requires the public-release and citation/factual checks appropriate
  to the record.
- `provenance` records whether a value came from a human, import, deterministic
  process, model, or review, plus capture time and optional tool/run/input hash.
- `source_id` identifies the work; `document_id` identifies a document or
  media representation; `version_id` identifies a captured content version;
  `span_id` is the smallest source anchor used by claims and evidence.
- `source_hash` and `content_hash` are optional because not every remote source
  exposes bytes, but adapters must preserve them whenever available. A
  `collection_label` may identify a non-public holdings collection without
  exposing a local filesystem path.
- Review receipts record a decision and checks, but do not silently promote a
  record. Consumers must apply their own release policy.

## Repository handoff

| Repository | R0 responsibility | Consumes/produces after R0 |
|---|---|---|
| `doclift` | Preserve document/version/span-compatible anchors from normalized text, layout, and timestamped transcripts. | Future adapter emits bundle candidates; `role` and `analysis_hints` remain machine cues. |
| `CiteGeist` | Resolve citation targets and preserve source identity/uncertainty. | Future adapter emits `citation_assertions`; unresolved matches remain candidates. |
| `library-ops` | Retain holdings and artifact/hash provenance at collection level. | Future importer may map holdings and cited passages into bundle sources/spans. |
| `GroundRecall` | Validate, review, retain, and govern the bundle and its release boundary. | Future importer/promoter; R0 does not add ingestion workers. |
| `evolutionnews-workbench` | Keep private multimedia/argument review and audit context. | Future adapter may map timestamped claims and receipts; raw media/transcripts stay private. |

Adapters should reject unknown schema versions, map legacy `candidate`,
`accepted`, and `rejected` states to `draft`/`triaged`, `reviewed`/`promoted`,
and `deprecated`, and preserve `verified` where the producer supplies it.
They must preserve source and content
hashes when available, avoid local filesystem paths in public bundles, and keep
unresolved candidate records visible. The golden fixture deliberately contains
one public article source and one private timestamped video version to test
that release level is record-specific.

## R0 non-goals

Extraction, claim decomposition, canonical matching, lineage inference,
coverage computation, review UI, publication, and cross-repository import code
remain future phases.
