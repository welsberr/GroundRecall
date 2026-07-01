# CiteGeist OKF Import

GroundRecall can import CiteGeist OKF bundles emitted by:

```bash
citegeist --db library.sqlite3 export-okf --topic TOPIC --output-dir topic-okf
```

Then import the bundle as grounded knowledge:

```bash
groundrecall import topic-okf --mode quick
```

The `citegeist_okf` source adapter preserves:

- work pages as import artifacts;
- topic pages as `citegeist-topic-*` concepts;
- scholarly works as `citegeist-work-*` concepts;
- topic membership relations;
- citation graph relations such as `cites`, `cited_by`, and `crossref`;
- bibliographic summaries and abstracts as grounded observations, fragments, and claims;
- CiteGeist review status, DOI, citation key, and OKF metadata on imported claims.

CiteGeist remains the bibliography authority. GroundRecall treats the OKF bundle as a portable, reviewable source package that can be promoted into canonical knowledge when useful.
