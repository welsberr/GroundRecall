from __future__ import annotations

import json
from pathlib import Path
import shutil

import groundrecall.ingest as ingest_module
import groundrecall.source_adapters  # noqa: F401
from groundrecall.source_adapters.base import detect_source_adapter, list_source_adapters
from groundrecall.ingest import run_groundrecall_import


def _fixture_doclift_bundle() -> Path:
    return Path(__file__).parent / "fixtures" / "doclift_bundle_minimal"


def _copied_fixture_doclift_bundle(tmp_path: Path) -> Path:
    target = tmp_path / "doclift_bundle_minimal"
    shutil.copytree(_fixture_doclift_bundle(), target)
    return target


def test_groundrecall_source_adapter_registry_lists_expected_adapters() -> None:
    names = set(list_source_adapters())
    assert "llmwiki" in names
    assert "polypaper" in names
    assert "markdown_notes" in names
    assert "transcript" in names
    assert "didactopus_pack" in names
    assert "doclift_bundle" in names
    assert "citegeist_okf" in names
    assert "indexcc" in names
    assert "pandasthumb_mt" in names


def test_detect_llmwiki_adapter(tmp_path: Path) -> None:
    (tmp_path / "wiki").mkdir()
    adapter = detect_source_adapter(tmp_path)
    assert adapter.name == "llmwiki"
    assert adapter.import_intent() == "grounded_knowledge"


def test_detect_didactopus_pack_adapter(tmp_path: Path) -> None:
    (tmp_path / "pack.yaml").write_text("name: p\n", encoding="utf-8")
    (tmp_path / "concepts.yaml").write_text("concepts: []\n", encoding="utf-8")
    adapter = detect_source_adapter(tmp_path)
    assert adapter.name == "didactopus_pack"
    assert adapter.import_intent() == "both"


def test_detect_doclift_bundle_adapter() -> None:
    adapter = detect_source_adapter(_fixture_doclift_bundle())
    assert adapter.name == "doclift_bundle"
    assert adapter.import_intent() == "both"


def test_citegeist_okf_adapter_imports_works_topics_and_edges(tmp_path: Path) -> None:
    (tmp_path / "works").mkdir()
    (tmp_path / "topics").mkdir()
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "bundle_kind": "citegeist_okf_bundle",
                "okf_profile": "citegeist.work.topic.v1",
                "citation_keys": ["smith2024graphs", "miller2023search"],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "index.md").write_text("# CiteGeist OKF Bundle\n", encoding="utf-8")
    (tmp_path / "log.md").write_text("# Export Log\n", encoding="utf-8")
    (tmp_path / "bibliography.bib").write_text("@article{smith2024graphs,}\n", encoding="utf-8")
    (tmp_path / "topics" / "graph-methods.md").write_text(
        "\n".join(
            [
                "---",
                'okf_type: "citegeist.topic"',
                'slug: "graph-methods"',
                'name: "Graph Methods"',
                "---",
                "# Graph Methods",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "works" / "smith2024graphs.md").write_text(
        "\n".join(
            [
                "---",
                'okf_type: "citegeist.work"',
                'citation_key: "smith2024graphs"',
                'entry_type: "article"',
                'review_status: "reviewed"',
                'title: "Graph-first bibliography augmentation"',
                'year: "2024"',
                "authors:",
                '  - "Smith, Jane"',
                "topic_slugs:",
                '  - "graph-methods"',
                "---",
                "# Graph-first bibliography augmentation",
                "",
                "## Abstract",
                "",
                "We study citation graphs for literature discovery.",
                "",
                "## Citation Graph",
                "",
                "### cites",
                "- [miller2023search](miller2023search.md)",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "works" / "miller2023search.md").write_text(
        "\n".join(
            [
                "---",
                'okf_type: "citegeist.work"',
                'citation_key: "miller2023search"',
                'entry_type: "inproceedings"',
                'title: "Semantic search for research corpora"',
                "---",
                "# Semantic search for research corpora",
            ]
        ),
        encoding="utf-8",
    )

    adapter = detect_source_adapter(tmp_path)
    assert adapter.name == "citegeist_okf"
    assert adapter.import_intent() == "grounded_knowledge"

    result = run_groundrecall_import(tmp_path, mode="quick", import_id="citegeist-okf-test")

    assert result.manifest["source_adapter"] == "citegeist_okf"
    assert result.manifest["import_intent"] == "grounded_knowledge"
    concept_ids = {row["concept_id"] for row in result.concepts}
    assert "concept::citegeist-work-smith2024graphs" in concept_ids
    assert "concept::citegeist-topic-graph-methods" in concept_ids
    relations = {(row["source_id"], row["target_id"], row["relation_type"]) for row in result.relations}
    assert (
        "concept::citegeist-work-smith2024graphs",
        "concept::citegeist-work-miller2023search",
        "cites",
    ) in relations
    assert any("citation graphs" in row["claim_text"] for row in result.claims)


def test_groundrecall_import_records_adapter_and_intent(tmp_path: Path) -> None:
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "note.md").write_text("# Title\n\n- A note.\n", encoding="utf-8")
    result = run_groundrecall_import(tmp_path, mode="quick", import_id="adapter-test")
    assert result.manifest["source_adapter"] == "llmwiki"
    assert result.manifest["import_intent"] == "grounded_knowledge"


def test_markdown_notes_adapter_ingests_tex_files(tmp_path: Path) -> None:
    (tmp_path / "draft.tex").write_text(
        "\\section{Related Work}\n\n"
        "We connect behaviorism and language models.\n",
        encoding="utf-8",
    )

    adapter = detect_source_adapter(tmp_path)
    assert adapter.name == "markdown_notes"

    result = run_groundrecall_import(tmp_path, mode="quick", import_id="tex-test")
    assert result.manifest["source_adapter"] == "markdown_notes"
    assert result.manifest["artifact_count"] == 1
    assert result.artifacts[0]["path"] == "draft.tex"
    assert result.claims


def test_plain_markdown_directory_uses_markdown_notes_adapter(tmp_path: Path) -> None:
    (tmp_path / "note.md").write_text("# Operational Note\n\nA plain note.\n", encoding="utf-8")

    adapter = detect_source_adapter(tmp_path)

    assert adapter.name == "markdown_notes"


def test_plain_markdown_file_uses_markdown_notes_adapter(tmp_path: Path) -> None:
    source = tmp_path / "note.md"
    source.write_text("# Operational Note\n\nA plain note.\n", encoding="utf-8")

    adapter = detect_source_adapter(source)

    assert adapter.name == "markdown_notes"


def test_groundrecall_import_accepts_single_markdown_file(tmp_path: Path) -> None:
    source = tmp_path / "note.md"
    source.write_text("# Operational Note\n\nA plain note.\n", encoding="utf-8")

    result = run_groundrecall_import(source, out_root=tmp_path / "imports", mode="quick", import_id="single-file-test")

    assert result.manifest["source_adapter"] == "markdown_notes"
    assert result.manifest["artifact_count"] == 1
    assert result.artifacts[0]["path"] == "note.md"
    assert result.claims


def test_textbook_ocr_adapter_segments_paragraphs_and_suppresses_references(tmp_path: Path) -> None:
    (tmp_path / ".groundrecall-textbook.json").write_text(
        json.dumps(
            {
                "schema": "groundrecall.textbook_ocr.v1",
                "id": "pianka-evolutionary-ecology",
                "title": "Evolutionary Ecology",
                "authors": ["Eric R. Pianka"],
                "year": "1988",
                "promote_sections": True,
                "files": ["part-000.txt"],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "part-000.txt").write_text(
        "\n".join(
            [
                "Chapter 1. Background                                    1",
                "",
                "Natural Selection",
                "",
                "Although natural selection is not a difficult concept, it is frequently",
                "misunderstood. A common misconception is that natural selection is simply",
                "any evolutionary change, whereas the mechanism specifically depends on",
                "differential reproductive success among heritable variants.",
                "",
                "\f10                                                            Background",
                "",
                "Selection can be treated as a source candidate for a Notebook scaffold",
                "when the text connects mechanism, population context, and evidence in a",
                "way that can later be checked against the surrounding page image.",
                "",
                "Selected References",
                "",
                "Darwin, C. 1859. This bibliography row is long enough that a naive line",
                "importer would turn it into a review item, but the textbook adapter should",
                "suppress it once the selected references region begins.",
            ]
        ),
        encoding="utf-8",
    )

    adapter = detect_source_adapter(tmp_path)
    assert adapter.name == "textbook_ocr"

    result = run_groundrecall_import(tmp_path, mode="quick", import_id="textbook-test")
    claim_texts = [item["claim_text"] for item in result.claims]

    assert result.manifest["source_adapter"] == "textbook_ocr"
    assert result.manifest["import_intent"] == "both"
    assert len(result.claims) == 2
    assert all("bibliography row" not in text for text in claim_texts)
    assert result.fragments[0]["metadata"]["page_start"] == 1
    assert result.fragments[1]["metadata"]["page_start"] == 2
    concept_ids = {item["concept_id"] for item in result.concepts}
    assert "concept::pianka-evolutionary-ecology" in concept_ids
    assert "concept::natural-selection" in concept_ids


def test_indexcc_adapter_import_generates_rows(tmp_path: Path) -> None:
    indexcc_dir = tmp_path / "site2_src" / "content" / "indexcc"
    indexcc_dir.mkdir(parents=True)
    (indexcc_dir / "CA100.md").write_text(
        "\n".join(
            [
                "## Claim",
                "",
                "Argument from incredulity claim.",
                "",
                "## Response",
                "",
                "A lack of imagination is not evidence of impossibility.",
            ]
        ),
        encoding="utf-8",
    )
    (indexcc_dir / "CA100.meta.json").write_text(
        '{"title": "CA100: Argument from Incredulity", "page_kind": "claim_entry", "legacy_source": "/indexcc/CA/CA100.html"}\n',
        encoding="utf-8",
    )

    result = run_groundrecall_import(tmp_path, mode="quick", import_id="indexcc-test")

    assert result.manifest["source_adapter"] == "indexcc"
    assert result.manifest["import_intent"] == "grounded_knowledge"
    assert result.manifest["fragment_count"] == 0
    assert result.artifacts[0]["metadata"]["corpus"] == "indexcc"
    assert result.claims[0]["claim_kind"] == "claim_entry"


def test_pandasthumb_mt_adapter_import_generates_article_rows(tmp_path: Path) -> None:
    public_html = tmp_path / "public_html"
    archive_dir = public_html / "archives" / "2016" / "01"
    archive_dir.mkdir(parents=True)
    (public_html / "index.html").write_text("<html><body>PT</body></html>\n", encoding="utf-8")
    (archive_dir / "sample.html").write_text(
        "\n".join(
            [
                '<h1 class="post-title">Sample Article</h1>',
                '<p class="post-meta">Posted 2016-01-01 by <span class="post-author">Author Name</span></p>',
                '<div class="post-body"><p>Article body text.</p></div>',
            ]
        ),
        encoding="utf-8",
    )

    result = run_groundrecall_import(tmp_path, mode="quick", import_id="ptmt-test")

    assert result.manifest["source_adapter"] == "pandasthumb_mt"
    assert result.manifest["import_intent"] == "grounded_knowledge"
    assert result.manifest["fragment_count"] == 0
    assert result.artifacts[0]["metadata"]["corpus"] == "pandasthumb_mt"
    assert result.observations[0]["text"] == "Article body text."


def test_tex_import_uses_pandoc_markdown_when_available(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "draft.tex").write_text(
        "\\section{Ignored by fallback}\n"
        "\\usepackage{amsmath}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        ingest_module,
        "_convert_tex_to_markdown",
        lambda path: "# Converted Draft\n\n- Converted claim from pandoc.\n",
    )

    result = run_groundrecall_import(tmp_path, mode="quick", import_id="tex-pandoc-test")
    claim_texts = [item["claim_text"] for item in result.claims]
    concept_ids = {item["concept_id"] for item in result.concepts}

    assert "Converted claim from pandoc." in claim_texts
    assert "concept::converted-draft" in concept_ids


def test_detect_polypaper_adapter_and_exclude_support_files(tmp_path: Path) -> None:
    (tmp_path / "pieces").mkdir()
    (tmp_path / "figs").mkdir()
    (tmp_path / "setup").mkdir()
    (tmp_path / "main.tex").write_text(
        "\\include{pieces/discussion}\n"
        "\\include{pieces/table-results}\n"
        "\\input{figs/figure-system}\n",
        encoding="utf-8",
    )
    (tmp_path / "paper.org").write_text("* draft\n", encoding="utf-8")
    (tmp_path / "pieces" / "discussion.tex").write_text("\\section{Discussion}\n\nMore text.\n", encoding="utf-8")
    (tmp_path / "pieces" / "table-results.tex").write_text("\\begin{tabular}x\\end{tabular}\n", encoding="utf-8")
    (tmp_path / "pieces" / "unused.tex").write_text("\\section{Unused}\n\nIgnore me.\n", encoding="utf-8")
    (tmp_path / "figs" / "figure-system.tex").write_text("\\begin{figure}x\\end{figure}\n", encoding="utf-8")
    (tmp_path / "setup" / "venue-arxiv.tex").write_text("\\section{Setup}\n", encoding="utf-8")
    (tmp_path / ".pp-export-tmp.tex").write_text("\\section{Tmp}\n", encoding="utf-8")

    adapter = detect_source_adapter(tmp_path)
    assert adapter.name == "polypaper"

    result = run_groundrecall_import(tmp_path, mode="quick", import_id="polypaper-test")
    paths = {item["path"] for item in result.artifacts}
    assert "main.tex" not in paths
    assert "pieces/discussion.tex" in paths
    assert "pieces/table-results.tex" not in paths
    assert "figs/figure-system.tex" not in paths
    assert "pieces/unused.tex" not in paths
    assert "setup/venue-arxiv.tex" not in paths
    assert ".pp-export-tmp.tex" not in paths


def test_tex_import_skips_table_and_figure_markup_from_pandoc(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "draft.tex").write_text("\\section{Draft}\n", encoding="utf-8")

    monkeypatch.setattr(
        ingest_module,
        "_convert_tex_to_markdown",
        lambda path: "\n".join(
            [
                "# Draft",
                "",
                "![image](figure.png)",
                "| Col A | Col B |",
                "| --- | --- |",
                "| 1 | 2 |",
                "</div>",
                "\\begin{tabular}{ll}",
                "- Real manuscript claim.",
            ]
        ),
    )

    result = run_groundrecall_import(tmp_path, mode="quick", import_id="tex-cleanup-test")
    claim_texts = [item["claim_text"] for item in result.claims]

    assert claim_texts == ["Real manuscript claim."]


def test_didactopus_pack_import_generates_structured_concepts_and_relations(tmp_path: Path) -> None:
    (tmp_path / "pack.yaml").write_text(
        "\n".join(
            [
                "name: sample-pack",
                "display_name: Sample Pack",
                "version: 0.1.0",
                "schema_version: 0.1.0",
                "didactopus_min_version: 0.1.0",
                "didactopus_max_version: 9.9.9",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "concepts.yaml").write_text(
        "\n".join(
            [
                "concepts:",
                "  - id: basics",
                "    title: Basics",
                "    description: Foundational concept.",
                "    mastery_signals: [Explain the foundation.]",
                "  - id: advanced",
                "    title: Advanced",
                "    description: Builds on basics.",
                "    prerequisites: [basics]",
                "    distinctions: [Advanced differs from basics in scope.]",
                "    definition_candidates: [Advanced is a follow-on concept.]",
                "    qualification_candidates: [Advanced builds on basics but assumes more context.]",
                "    constraint_candidates: [Advanced cannot be understood without basics.]",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "roadmap.yaml").write_text(
        "\n".join(
            [
                "stages:",
                "  - id: stage1",
                "    title: Stage One",
                "    concepts: [basics, advanced]",
            ]
        ),
        encoding="utf-8",
    )

    result = run_groundrecall_import(tmp_path, mode="quick", import_id="pack-test")
    assert result.manifest["source_adapter"] == "didactopus_pack"
    assert result.manifest["import_intent"] == "both"
    concept_ids = {item["concept_id"] for item in result.concepts}
    assert "concept::basics" in concept_ids
    assert "concept::advanced" in concept_ids
    relation_targets = {(item["source_id"], item["target_id"], item["relation_type"]) for item in result.relations}
    assert ("concept::basics", "concept::advanced", "prerequisite") in relation_targets
    claim_ids = {item["claim_id"] for item in result.claims}
    assert "clm_pack_basics" in claim_ids
    assert "clm_stage_stage1_basics" in claim_ids
    assert "clm_dist_advanced_1" in claim_ids
    assert "clm_def_advanced_1" in claim_ids
    assert "clm_qual_advanced_1" in claim_ids
    assert "clm_constraint_advanced_1" in claim_ids


def test_doclift_bundle_import_generates_structured_concepts(tmp_path: Path) -> None:
    result = run_groundrecall_import(_copied_fixture_doclift_bundle(tmp_path), mode="quick", import_id="doclift-test")
    assert result.manifest["source_adapter"] == "doclift_bundle"
    assert result.manifest["import_intent"] == "both"
    assert result.manifest["source_root"] == "doclift_bundle_minimal"
    assert result.manifest["source_root_kind"] == "source_label"
    assert result.manifest["fragment_count"] == 2
    concept_ids = {item["concept_id"] for item in result.concepts}
    assert "concept::lecture-1" in concept_ids
    claim_ids = {item["claim_id"] for item in result.claims}
    assert "clm_doclift_1_1" in claim_ids
    assert "clm_doclift_1" not in claim_ids
    assert result.observations[0]["source_url"] == "legacy/lecture-1.doc"
    assert len(result.fragments) == 2
    assert result.fragments[0]["metadata"]["source_kind"] == "doclift_chunk"
    claim_by_id = {item["claim_id"]: item for item in result.claims}
    assert claim_by_id["clm_doclift_1_1"]["supporting_fragment_ids"] == ["frag_doclift_1_1"]


def test_doclift_bundle_import_derives_claims_from_prose_when_chunks_are_body_only(tmp_path: Path) -> None:
    root = tmp_path / "doclift_bundle_prose"
    document_dir = root / "documents" / "essay-1"
    document_dir.mkdir(parents=True)
    (root / "manifest.json").write_text(
        '{\n'
        '  "documents": [\n'
        '    {\n'
        '      "document_id": "essay-1",\n'
        '      "title": "Drift Essay",\n'
        '      "document_kind": "web_article",\n'
        '      "output_dir": "documents/essay-1",\n'
        '      "markdown_path": "documents/essay-1/document.md"\n'
        '    }\n'
        '  ]\n'
        '}\n',
        encoding="utf-8",
    )
    (document_dir / "document.md").write_text(
        "\n".join(
            [
                "# Drift Essay",
                "",
                "Random genetic drift can dominate allele-frequency change in small populations.",
                "This matters because many alleles are fixed or lost without any adaptive advantage.",
                "",
                "Posted by Example Author",
            ]
        ),
        encoding="utf-8",
    )
    (document_dir / "document.chunks.json").write_text(
        json.dumps(
            {
                "chunks": [
                    {
                        "chunk_id": "essay-1-body-1",
                        "role": "body",
                        "section": "Drift Essay",
                        "text": "Random genetic drift can dominate allele-frequency change in small populations.",
                        "line_start": 1,
                        "line_end": 2,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = run_groundrecall_import(root, mode="quick", import_id="doclift-prose-test")
    claim_texts = [item["claim_text"] for item in result.claims]

    assert any("Random genetic drift can dominate allele-frequency change in small populations." in text for text in claim_texts)
    assert not any(text == "Drift Essay is a web_article in the imported doclift bundle." for text in claim_texts)
    derived_observations = [item for item in result.observations if item["observation_id"].startswith("obs_doclift_1_derived_")]
    assert derived_observations
    assert derived_observations[0]["metadata"]["claim_strategy"] in {"conservative", "balanced", "broad"}


def test_doclift_bundle_import_ignores_blog_comment_trailers(tmp_path: Path) -> None:
    root = tmp_path / "doclift_bundle_blog"
    document_dir = root / "documents" / "blog-1"
    document_dir.mkdir(parents=True)
    (root / "manifest.json").write_text(
        '{\n'
        '  "documents": [\n'
        '    {\n'
        '      "document_id": "blog-1",\n'
        '      "title": "Blog Essay",\n'
        '      "document_kind": "web_article",\n'
        '      "output_dir": "documents/blog-1",\n'
        '      "markdown_path": "documents/blog-1/document.md"\n'
        '    }\n'
        '  ]\n'
        '}\n',
        encoding="utf-8",
    )
    (document_dir / "document.md").write_text(
        "\n".join(
                [
                    "# Blog Essay",
                    "",
                    "Random genetic drift is a fundamental and important part of evolution because many population-level changes are not driven by selection alone.",
                "",
                "Posted by Example Author",
                "",
                "3 comments:",
                "",
                "A mistake can do this glory is very unlikely and opposite to the first instinct that biology is complexity from a thinking being.",
            ]
        ),
        encoding="utf-8",
    )
    (document_dir / "document.chunks.json").write_text(
        json.dumps(
            {
                "chunks": [
                        {
                            "chunk_id": "blog-1-body-1",
                            "role": "body",
                            "section": "Blog Essay",
                            "text": "Random genetic drift is a fundamental and important part of evolution because many population-level changes are not driven by selection alone.",
                            "line_start": 1,
                            "line_end": 2,
                        }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = run_groundrecall_import(root, mode="quick", import_id="doclift-blog-test")
    claim_texts = [item["claim_text"] for item in result.claims]

    assert any("Random genetic drift is a fundamental and important part of evolution" in text for text in claim_texts)
    assert not any("A mistake can do this glory" in text for text in claim_texts)
