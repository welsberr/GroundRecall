from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
import re
from typing import Any

from .base import DiscoveredImportSource, StructuredImportRows, register_source_adapter


ARTIFACT_SUFFIXES = {".html", ".htm"}
ARTICLE_TITLE_RE = re.compile(r'<h1 class="post-title">(.*?)</h1>', re.I | re.S)
BYLINE_RE = re.compile(
    r'<p class="post-meta">\s*Posted\s+(?P<date>.*?)\s+by\s+<span class="post-author">(?P<author>.*?)</span>',
    re.I | re.S,
)
COMMENT_META_RE = re.compile(
    r'<p class="comment-meta">\s*<span class="comment-author">(?P<author>.*?)</span>\s*&middot;\s*(?P<date>.*?)</p>',
    re.I | re.S,
)
COMMENTS_SECTION_RE = re.compile(r'<section class="comments-section">(.*?)</section>', re.I | re.S)


def _strip_tags(text: str) -> str:
    return re.sub(r"(?s)<[^>]+>", " ", text)


def _normalize_space(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _fragment_to_text(fragment: str) -> str:
    fragment = re.sub(r"(?is)<script\b.*?</script>", " ", fragment)
    fragment = re.sub(r"(?is)<style\b.*?</style>", " ", fragment)
    fragment = re.sub(
        r'(?is)<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        lambda match: f"{_strip_tags(match.group(2)).strip()} ({match.group(1).strip()})".strip(),
        fragment,
    )
    fragment = re.sub(r"(?i)<br\s*/?>", "\n", fragment)
    fragment = re.sub(r"(?i)</p\s*>", "\n\n", fragment)
    fragment = re.sub(r"(?i)<p\b[^>]*>", "", fragment)
    fragment = re.sub(r"(?i)</div\s*>", "\n", fragment)
    fragment = re.sub(r"(?i)<div\b[^>]*>", "", fragment)
    fragment = re.sub(r"(?i)</section\s*>", "\n", fragment)
    fragment = re.sub(r"(?i)<section\b[^>]*>", "", fragment)
    fragment = re.sub(r"(?i)</blockquote\s*>", "\n", fragment)
    fragment = re.sub(r"(?i)<blockquote\b[^>]*>", "\n> ", fragment)
    fragment = re.sub(r"(?i)</li\s*>", "\n", fragment)
    fragment = re.sub(r"(?i)<li\b[^>]*>", "\n- ", fragment)
    fragment = re.sub(r"(?i)<ul\b[^>]*>|</ul\s*>", "\n", fragment)
    fragment = re.sub(r"(?i)<ol\b[^>]*>|</ol\s*>", "\n", fragment)
    fragment = _strip_tags(fragment)
    fragment = re.sub(r"\s*\n\s*", "\n", fragment)
    return _normalize_space(fragment.replace("\xa0", " "))


def _id_from_path(relative_path: str) -> str:
    return f"pt_{sha256(relative_path.encode('utf-8')).hexdigest()[:12]}"


def _site_root(root: Path) -> Path:
    candidate = root / "public_html"
    if (candidate / "archives").is_dir():
        return candidate
    return root


def _discover_html_files(site_root: Path) -> list[Path]:
    archives = site_root / "archives"
    if not archives.is_dir():
        return []
    rows = []
    for path in sorted(archives.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in ARTIFACT_SUFFIXES:
            continue
        if path.name.lower() == "index.html":
            continue
        rows.append(path)
    return rows


def _extract_article(html_text: str, relative_path: str) -> dict[str, Any] | None:
    title_match = ARTICLE_TITLE_RE.search(html_text)
    body_match = re.search(r'<div class="post-body">(.*)', html_text, re.I | re.S)
    if title_match is None or body_match is None:
        return None

    meta_match = BYLINE_RE.search(html_text)
    comments_match = COMMENTS_SECTION_RE.search(html_text)
    body_html = body_match.group(1)
    if comments_match is not None:
        body_html = body_html[: comments_match.start() - body_match.end()]
    body_text = _fragment_to_text(body_html)
    title = _fragment_to_text(title_match.group(1))
    author = _fragment_to_text(meta_match.group("author")) if meta_match else ""
    published_at = _fragment_to_text(meta_match.group("date")) if meta_match else ""
    canonical_url = "/" + relative_path.lstrip("/")
    return {
        "document_id": _id_from_path(relative_path),
        "title": title,
        "author": author,
        "published_at": published_at,
        "canonical_url": canonical_url,
        "body_text": body_text,
    }


def _extract_comments(html_text: str, relative_path: str, parent_document_id: str) -> list[dict[str, Any]]:
    comments_match = COMMENTS_SECTION_RE.search(html_text)
    if comments_match is None:
        return []
    comments_html = comments_match.group(1)
    rows: list[dict[str, Any]] = []
    starts = list(re.finditer(r'<div class="comment" id="comment-(?P<comment_id>\d+)">', comments_html, re.I))
    for index, match in enumerate(starts):
        start = match.end()
        end = starts[index + 1].start() if index + 1 < len(starts) else len(comments_html)
        chunk = comments_html[start:end]
        meta_match = COMMENT_META_RE.search(chunk)
        body_match = re.search(r'<div class="comment-body">(.*)</div>', chunk, re.I | re.S)
        if body_match is None:
            continue
        rows.append(
            {
                "document_id": f"{parent_document_id}__comment_{match.group('comment_id')}",
                "parent_document_id": parent_document_id,
                "comment_id": match.group("comment_id"),
                "document_kind": "comment",
                "comment_author": _fragment_to_text(meta_match.group("author")) if meta_match else "",
                "comment_date": _fragment_to_text(meta_match.group("date")) if meta_match else "",
                "canonical_url": "/" + relative_path.lstrip("/"),
                "body_text": _fragment_to_text(body_match.group(1)),
            }
        )
    return rows


class PandasThumbMtSourceAdapter:
    name = "pandasthumb_mt"

    def detect(self, root: str | Path) -> bool:
        site_root = _site_root(Path(root))
        return (site_root / "archives").is_dir() and (site_root / "index.html").exists()

    def discover(self, root: str | Path) -> list[DiscoveredImportSource]:
        site_root = _site_root(Path(root))
        rows: list[DiscoveredImportSource] = []
        for path in _discover_html_files(site_root):
            rows.append(
                DiscoveredImportSource(
                    path=path,
                    relative_path=path.relative_to(site_root).as_posix(),
                    source_kind="pandasthumb_mt",
                    artifact_kind="pandasthumb_mt_page",
                    is_text=True,
                    metadata={"corpus": "pandasthumb_mt"},
                )
            )
        return rows

    def import_intent(self) -> str:
        return "grounded_knowledge"

    def build_rows(self, context, sources: list[DiscoveredImportSource]) -> StructuredImportRows | None:
        artifact_rows: list[dict[str, Any]] = []
        observation_rows: list[dict[str, Any]] = []
        claim_rows: list[dict[str, Any]] = []
        concept_rows: list[dict[str, Any]] = []
        relation_rows: list[dict[str, Any]] = []

        for source in sources:
            html_text = source.path.read_text(encoding="utf-8", errors="replace")
            article = _extract_article(html_text, source.relative_path)
            if article is None:
                continue

            artifact_id = _id_from_path(source.relative_path)
            artifact_rows.append(
                {
                    "artifact_id": artifact_id,
                    "import_id": context.import_id,
                    "artifact_kind": source.artifact_kind,
                    "path": source.relative_path,
                    "title": article["title"],
                    "sha256": sha256(source.path.read_bytes()).hexdigest(),
                    "created_at": context.imported_at,
                    "metadata": {
                        "corpus": "pandasthumb_mt",
                        "document_kind": "article",
                        "author": article["author"],
                        "published_at": article["published_at"],
                        "canonical_url": article["canonical_url"],
                    },
                    "current_status": "draft",
                }
            )
            observation_rows.append(
                {
                    "observation_id": f"obs_{artifact_id}_body",
                    "import_id": context.import_id,
                    "artifact_id": artifact_id,
                    "role": "summary",
                    "text": article["body_text"],
                    "origin_path": source.relative_path,
                    "origin_section": article["title"],
                    "line_start": 0,
                    "line_end": 0,
                    "source_url": article["canonical_url"],
                    "metadata": {
                        "corpus": "pandasthumb_mt",
                        "document_kind": "article",
                        "author": article["author"],
                        "published_at": article["published_at"],
                    },
                    "grounding_status": "grounded",
                    "support_kind": "direct_source",
                    "confidence_hint": 0.75,
                    "current_status": "draft",
                }
            )

            for comment in _extract_comments(html_text, source.relative_path, artifact_id):
                comment_artifact_id = comment["document_id"]
                artifact_rows.append(
                    {
                        "artifact_id": comment_artifact_id,
                        "import_id": context.import_id,
                        "artifact_kind": "pandasthumb_mt_comment",
                        "path": source.relative_path,
                        "title": f"{article['title']} comment {comment['comment_id']}",
                        "sha256": sha256(
                            f"{source.relative_path}#{comment['comment_id']}".encode("utf-8")
                        ).hexdigest(),
                        "created_at": context.imported_at,
                        "metadata": {
                            "corpus": "pandasthumb_mt",
                            "document_kind": "comment",
                            "parent_document_id": artifact_id,
                            "comment_id": comment["comment_id"],
                            "comment_author": comment["comment_author"],
                            "comment_date": comment["comment_date"],
                            "canonical_url": comment["canonical_url"],
                        },
                        "current_status": "draft",
                    }
                )
                observation_rows.append(
                    {
                        "observation_id": f"obs_{comment_artifact_id}_body",
                        "import_id": context.import_id,
                        "artifact_id": comment_artifact_id,
                        "role": "summary",
                        "text": comment["body_text"],
                        "origin_path": source.relative_path,
                        "origin_section": f"comment {comment['comment_id']}",
                        "line_start": 0,
                        "line_end": 0,
                        "source_url": comment["canonical_url"],
                        "metadata": {
                            "corpus": "pandasthumb_mt",
                            "document_kind": "comment",
                            "parent_document_id": artifact_id,
                            "comment_id": comment["comment_id"],
                            "comment_author": comment["comment_author"],
                            "comment_date": comment["comment_date"],
                        },
                        "grounding_status": "grounded",
                        "support_kind": "direct_source",
                        "confidence_hint": 0.7,
                        "current_status": "draft",
                    }
                )

        return StructuredImportRows(
            artifact_rows=artifact_rows,
            fragment_rows=[],
            observation_rows=observation_rows,
            claim_rows=claim_rows,
            concept_rows=concept_rows,
            relation_rows=relation_rows,
        )


register_source_adapter(PandasThumbMtSourceAdapter())
