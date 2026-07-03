# Evidence-Docket Claims Analysis

GroundRecall’s current import/review model is good at:

- preserving provenance
- turning observations into reviewable claims
- keeping concepts, claims, relations, and citations separate

It is still weak at a different task:

- structured adversarial or forensic analysis of an argument across multiple claim lanes

That gap became clearer in the local `evolutionnews.net` evidence-docket work.
Those dockets do not just collect claims. They classify how claims function in
an argument.

## Why this matters

In the Mason design-biology work, the useful analysis was not just:

- what claim appears in the text
- what source supports it

It also depended on:

- what role the claim plays in the overall argument
- whether the burden of proof is being shifted
- whether multiple domains are being bundled rhetorically
- whether citations merely exist or actually support the claim
- what empirical gap is being asserted versus what research program already exists

GroundRecall can already hold the raw ingredients for that kind of work, but it
does not yet model them explicitly.

## Evidence-docket structure worth borrowing

The local evidence-docket workflow has a few recurring sections that map well
onto richer GroundRecall review:

1. `claim map`
   The operative argument structure, not just isolated statements.

2. `primary findings`
   Higher-order judgments such as burden asymmetry, domain bundling, or model
   overreach.

3. `evidence cards`
   Focused support packets that connect one objection or claim to a bounded
   source trail.

4. `rhetorical maneuvers flagged`
   Moves such as burden shift, equivocation, present-function fallacy, or
   overgeneralization from a narrow model.

5. `burden check`
   What the author requires from the opposing view versus what their own view
   must supply.

6. `citation and source audit`
   Whether named sources are real, relevant, overextended, or contradicted by
   the way they are being used.

7. `research program`
   What empirical work would actually reduce the leverage of the objection.

8. `claim alignment audit`
   Whether a docket claim has been mapped to the correct external claim record,
   such as a TalkOrigins Index to Creationist Claims entry, and which nearby
   entries were considered and rejected.

## Implications for GroundRecall

GroundRecall should stay centered on grounded records, but claim analysis can be
enriched in a way that matches the docket workflow.

### 1. Expand claim kinds

Current `claim_kind` values are mostly low-level:

- `statement`
- `summary`
- adapter-specific kinds such as `mastery_signal`

Useful additions:

- `argument_step`
- `burden_check`
- `rhetorical_move`
- `citation_audit`
- `research_gap`
- `research_program`
- `counterexample`

These do not replace ordinary claims. They make higher-order analytical claims
first-class instead of burying them in reviewer notes.

### 2. Add argument-lane metadata

Claims should be able to carry lightweight analytical tags such as:

- `argument_role`: premise, inference, objection, counterargument, scope note
- `analysis_lane`: empirical, rhetorical, citation, burden, research_program
- `risk_flags`: overstatement, bundling, equivocation, unsupported_generalization

This can start as claim metadata without requiring a schema break.

### 3. Model evidence cards explicitly

An evidence card is more than one claim. It is a bounded support packet that
ties together:

- one focal issue
- one or more claims
- supporting observations
- cited sources
- reviewer verdict

GroundRecall does not need a new top-level store object immediately. A first
step could be review-export grouping by:

- lane
- concept
- citation cluster

### 4. Treat Index-entry matching as reviewed alignment

The evidence-docket tooling should not collapse a source span to a single Index
to Creationist Claims entry merely because the text is topically similar. Wrong
Index alignment is worse than a missing link because it pollutes later evidence
cards, search facets, and lineage analysis.

Alignment review should preserve:

- the source span being mapped;
- the candidate Index entries;
- positive evidence for each candidate;
- negative evidence and neighboring confusions;
- relation type, such as exact, narrower, broader, analogous, cites, borrows,
  responds-to, or background;
- reviewer disposition.

If the best answer is uncertain, the docket should say so and carry candidate
links rather than presenting a single canonical claim link.

## Bibliography and abstracts

The bibliography expansion work showed that abstracts are often the fastest way
to estimate:

- whether a source is in the right domain
- whether it actually addresses the asserted mechanism or phenomenon
- whether a citation is likely to support or overstate a claim

That suggests two concrete upgrades for GroundRecall review:

1. show more than citation-key existence
   Review should expose whether resolved bibliography entries have abstracts,
   DOI coverage, and enough metadata depth for meaningful support judgment.

2. use abstracts as first-pass support context
   Abstract snippets should be available when a reviewer is deciding whether a
   cited work materially supports a claim or merely sounds adjacent.

Important boundary:

- abstracts are triage evidence, not final adjudication
- direct source reading still matters for strong or controversial claims

## Recommended implementation order

1. Enrich bibliography summary and artifact citation summaries.
   Surface abstract-bearing coverage, representative titles, DOI coverage, and
   short abstract snippets in review payloads.

2. Add analytical claim metadata.
   Start with optional metadata fields in claim rows and review exports.

3. Add claim-alignment review records.
   Store ranked Index-entry candidates, evidence for and against each mapping,
   and the reviewer disposition.

4. Add review lanes mirroring the evidence-docket workflow.
   Separate empirical support review from rhetorical and burden-check review.

5. Add evidence-card grouping in review UI/export.
   Let reviewers inspect a bounded packet instead of isolated claim rows.

6. Add a bibliography-assisted claim-support pass.
   Reuse CiteGeist support/verification capabilities so GroundRecall can move
   from “citation exists” toward “citation probably supports this claim because…”

## Practical near-term change

The smallest worthwhile next step is:

- improve GroundRecall review payloads so bibliography strength is visible
- especially abstract-bearing resolved entries and representative titles

That does not solve richer claim analysis by itself, but it gives reviewers a
better support surface and aligns GroundRecall with the successful parts of the
evidence-docket workflow.
