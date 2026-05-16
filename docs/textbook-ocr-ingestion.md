# Textbook OCR Ingestion

Use the `textbook_ocr` source adapter for scanned textbook text that has already
been extracted from PDF or image sources. It is intended for Notebook and course
source-ingestion tests where raw line-level OCR would create too many review
items.

Create a manifest named `.groundrecall-textbook.json` in the text corpus
directory:

```json
{
  "schema": "groundrecall.textbook_ocr.v1",
  "id": "pianka-evolutionary-ecology-1988",
  "title": "Evolutionary Ecology",
  "authors": ["Eric R. Pianka"],
  "year": "1988",
  "description": "Fourth edition textbook OCR extracted from local Library PDFs.",
  "files": [
    "1988-pianka-evolutionary-ecology-000.txt",
    "1988-pianka-evolutionary-ecology-001.txt"
  ]
}
```

Then import with an optional concept seed store:

```bash
groundrecall import ./text \
  --out-root ~/.groundrecall/imports \
  --mode quick \
  --import-id pianka-evolutionary-ecology-1988 \
  --concept-seed-store ~/.groundrecall/store
```

The adapter:

- creates one local book concept by default;
- keeps section headings as provenance on fragments, observations, and claims;
- emits paragraph-level `source_excerpt` claims instead of one claim per OCR line;
- records page numbers inferred from form-feed page breaks;
- skips obvious page-number, running-head, selected-reference, bibliography, and
  index regions;
- leaves Notebook or project concept links to the seeded concept-alignment layer.

If a corpus has clean headings and should create local section concepts, add:

```json
{
  "promote_sections": true
}
```

Keep this opt-in for OCR scans. Figure labels, tables, graph axes, and index
entries often look like title-case headings.
