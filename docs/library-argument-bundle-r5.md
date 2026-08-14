# R5 candidate evidence cards and scientific-foundation dossiers

R5 adds a read-only compiler for the Library argument-bundle workflow:

```text
groundrecall argument-bundle-r5 INPUT.json OUTPUT.json [--bibliography BIB.json] [--knowledge-domains DOMAINS.json]
```

The API is `generate_r5_candidates(bundle, bibliography_entries=..., knowledge_domains=...)`.
It returns a separate `library.argument_bundle.r5.candidate-evidence.v1`
envelope containing bounded evidence cards, recurring knowledge-domain dossier
groups, and pending adjudication records. IDs and provenance are deterministic.

An evidence card connects a claim to its claim spans and any citation assertion
and target spans. It records evidence type, candidate relevance, existing
asserted support status, counterevidence and limitations slots, source-quality
flags, and a reviewer-decision slot. CiteGeist-style bibliography fields such
as DOI and abstract are surfaced only as metadata/triage flags; an abstract is
not treated as final support.

`record_r5_adjudication` is also pure: it returns a private/draft review record
and requires an explicit reviewer, decision, and rationale. It does not write
to a store or change the source bundle. `supported` and other decisions are
review labels, not assertions of scientific truth; expert review remains
required. No R5 output is public or promoted.

Knowledge domains are caller-supplied records with `domain_id`, `label`, and
optional `keywords`/`description`. Matching is deterministic lexical grouping
only, so a dossier identifies recurring foundation-review work without
asserting that a domain claim is scientifically correct.
