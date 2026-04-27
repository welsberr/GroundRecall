# GroundRecall

GroundRecall is a human-reviewable/AI usable knowledge layer with capabilities to meet or exceed 'llmwiki' with 'v2' specifications, plus an import path for existing llmwiki instances, and integration with Didactopus for review workflows and knowledge merging.

`GroundRecall` can also import normalized `doclift` bundles directly when the
source material began as legacy office documents and you want a provenance-aware
knowledge import without going through a learner pack first. See
`docs/quickstart.md` for the minimal `doclift -> GroundRecall` flow.

`GroundRecall` can now also export a pack-ready
`groundrecall_query_bundle.json` for a reviewed concept so `Didactopus` can
carry that concept context into a learner-facing pack:

```bash
python -m groundrecall.export /path/to/groundrecall-store /tmp/groundrecall-export \
  --pack-ready-concept channel-capacity
```

The matching `Didactopus` bridge flow is:

```bash
didactopus doclift-bundle-groundrecall \
  /path/to/groundrecall-store \
  channel-capacity \
  /tmp/doclift-bundle \
  /tmp/didactopus-pack \
  --course-title "Example Course"
```

See:

- `docs/quickstart.md`
- `docs/didactopus-bridge.md`
