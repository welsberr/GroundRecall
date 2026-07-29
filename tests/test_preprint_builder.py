from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "docs" / "preprint" / "build_preprint_pdf.py"
spec = importlib.util.spec_from_file_location("build_preprint_pdf", MODULE_PATH)
assert spec is not None
preprint_builder = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(preprint_builder)


def test_linkify_bare_urls_preserves_existing_markdown_links_and_autolinks() -> None:
    text = "\n".join(
        [
            "Source: https://example.test/really/long/path",
            "Already autolinked: <https://example.test/autolinked>",
            "Already linked: [example](https://example.test/linked)",
        ]
    )

    rendered = preprint_builder.linkify_bare_urls(text)

    assert "Source: <https://example.test/really/long/path>" in rendered
    assert "Already autolinked: <https://example.test/autolinked>" in rendered
    assert "Already linked: [example](https://example.test/linked)" in rendered


def test_preprint_line_wrapping_assets_are_declared() -> None:
    assert preprint_builder.HTML_HEADER.exists()
    assert preprint_builder.LATEX_HEADER.exists()
    assert preprint_builder.LINEBREAK_FILTER.exists()
