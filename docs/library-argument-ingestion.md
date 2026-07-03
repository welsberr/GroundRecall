# Library Argument Ingestion

GroundRecall is the durable review and recall layer for Library argument
ingestion. It should not treat doclift or LLM output as reviewed knowledge on
arrival.

## Import Contract

GroundRecall importers should accept doclift chunks with:

- source document identifier;
- source path or collection label;
- source hash when available;
- chunk identifier;
- chunk role;
- `analysis_hints`;
- source text span;
- line or page anchors;
- access restriction metadata.

Draft imports should preserve the difference between extracted source text,
machine-proposed interpretation, reviewer notes, and promoted claims.

## Draft Records

Argument-oriented imports should create review candidates for:

- propositions;
- premises;
- inference links;
- conclusions;
- evidence links;
- objections;
- rebuttals;
- critiques;
- fallacy cues;
- citation anchors.

Fallacy matches are cues for review, not final labels. GroundRecall should
store the triggering span and the detector or model that proposed the cue.

## Fallacy Taxonomy Records

GroundRecall should be able to store fallacy taxonomy records as ordinary
grounded knowledge with review status. Useful records include canonical labels,
aliases, definitions, distinguishing conditions, false-positive notes, source
citations, and reviewed examples from hosted site corpora or Library material.

Candidate detectors should link to taxonomy records by stable identifiers. A
match such as `fallacy_cue:straw_man` means "review this span against the
taxonomy", not "publish this as a straw-man fallacy".

## Claim Alignment Records

GroundRecall should model links to external claim taxonomies as candidate
alignment records before promotion. This is especially important for the
TalkOrigins Index to Creationist Claims, where adjacent entries can appear
similar while making different claims.

Candidate alignment records should include:

- source span and imported argument element;
- target taxonomy or corpus;
- candidate entry id and title;
- positive match evidence;
- negative evidence and likely neighboring confusions;
- relation type: exact, narrower, broader, analogous, cites, borrows,
  responds-to, contradicts, or background;
- confidence;
- reviewer status and disposition.

Importers and LLM workers should return ranked candidate sets with explanations,
not a single unqualified match. If no candidate is strong enough, the correct
output is an explicit unresolved alignment, not a forced Index entry.

## Work Lineage

Connections to earlier and later works should preserve the evidence type:

- explicit citation;
- quoted or paraphrased passage;
- shared uncommon phrase;
- shared example or argument sequence;
- silent borrowing candidate;
- independent recurrence;
- later citation or reuse.

Silent borrowing and influence claims should remain draft until reviewed. They
should not be inferred from topic similarity alone.

## Study-Aid Records

GroundRecall should store study-aid representations as structured views over
grounded records, not as replacements for those records. A study-aid view can
combine:

- source spine records;
- at-a-glance orientation;
- source summary;
- analysis notes;
- glossary/concept entries;
- worked critique or evidence examples;
- retrieval-practice prompts;
- unresolved questions and coverage gaps.

Each item should retain its provenance and review status. Summary records should
say what source span they summarize; analysis records should say who or what
produced the interpretation; practice prompts should link to the reviewed
source record or argument element they exercise.

## Promotion Policy

A record is promotable only when it has:

- a source anchor;
- review status;
- access/publication status;
- provenance for machine assistance;
- an explicit relation to supporting, opposing, or contextual evidence.

Public exports for SciSiteForge or other sites must exclude restricted Library
sources, private notes, raw model output, and unreviewed workbench records.
Study-aid exports must also preserve the distinction between source summary,
analysis, example, exercise, and reviewer verdict.

## Automation

GenieHive workers may process queued chunks into draft JSON records. Imports
must be idempotent by source hash, chunk id, prompt id, and model id so that
slow or partial runs can resume without duplicating records.
