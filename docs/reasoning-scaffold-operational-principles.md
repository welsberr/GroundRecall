# Reasoning Scaffold Operational Principles

GroundRecall is the durable memory layer for reasoning-scaffold work. It should preserve why a scaffold exists, what review decisions were made, which source slots remain unresolved, and how later tools changed the artifact.

## Principles

- Store reviewed rationale, not raw hidden chain-of-thought.
- Keep decisions recoverable: source choices, rejected citations, audience assumptions, and revision reasons belong in durable notes.
- Link concrete artifacts by path so future sessions can find the HTML, JSON, app page, source note, or bibliography record without rediscovery.
- Treat pending source slots as first-class memory items. They should remain visible until CiteGeist or another reviewed workflow resolves them.
- Prefer compact operational notes that future agents can act on over broad summaries that lack file paths or next actions.

## Current Pilot

The first applied scaffold is the evo-edu Notebook concept page:

- `/home/netuser/dev/evo-edu.org/notebook/concepts/allele-frequency-change.html`
- `/home/netuser/dev/evo-edu.org/notebook/concepts/allele-frequency-change.scaffold.json`

Related local memory notes:

- `/home/netuser/.groundrecall/source-notes/knowledgebase-lcot-sciencepedia-implications-20260513.md`
- `/home/netuser/.groundrecall/source-notes/evo-edu-notebook-allele-frequency-scaffold-20260513.md`

## Downstream Responsibilities

- Didactopus consumes prompt seeds for learner-facing prediction, evidence, and revision activities.
- doclift extracts or emits scaffold-shaped records from longer documents.
- CiteGeist resolves bibliography source slots.
- Notebook exposes the reviewed learner-facing summary.
