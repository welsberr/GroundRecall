from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable

from .store import GroundRecallStore


INDEX_VERSION = 1


@dataclass(frozen=True)
class SearchDocument:
    doc_key: str
    kind: str
    record_id: str
    title: str
    body: str
    path: str = ""
    status: str = ""
    metadata: dict[str, Any] | None = None
    source_path: Path | None = None


def index_path(store_dir: str | Path) -> Path:
    return Path(store_dir) / ".index" / "groundrecall-search.sqlite"


def build_search_index(store_dir: str | Path, *, include_source_notes: bool = True) -> dict[str, Any]:
    store_dir = Path(store_dir)
    db_path = index_path(store_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    docs = list(iter_search_documents(store_dir, include_source_notes=include_source_notes))
    with sqlite3.connect(db_path) as conn:
        _init_schema(conn)
        conn.execute("delete from docs")
        conn.execute("delete from docs_fts")
        for rowid, doc in enumerate(docs, start=1):
            metadata = dict(doc.metadata or {})
            if doc.source_path is not None and doc.source_path.exists():
                metadata["source_mtime"] = doc.source_path.stat().st_mtime
                metadata["source_path"] = str(doc.source_path)
            conn.execute(
                """
                insert into docs(rowid, doc_key, kind, record_id, path, title, status, metadata)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rowid,
                    doc.doc_key,
                    doc.kind,
                    doc.record_id,
                    doc.path,
                    doc.title,
                    doc.status,
                    json.dumps(metadata, sort_keys=True),
                ),
            )
            conn.execute(
                """
                insert into docs_fts(doc_key, title, body, metadata)
                values (?, ?, ?, ?)
                """,
                (doc.doc_key, doc.title, doc.body, json.dumps(metadata, sort_keys=True)),
            )
        conn.execute("delete from meta")
        conn.executemany(
            "insert into meta(key, value) values (?, ?)",
            [
                ("index_version", str(INDEX_VERSION)),
                ("document_count", str(len(docs))),
            ],
        )
    return {"index_path": str(db_path), "document_count": len(docs), "index_version": INDEX_VERSION}


def search_index(
    store_dir: str | Path,
    query: str,
    *,
    limit: int = 20,
    kinds: list[str] | None = None,
    corpora: list[str] | None = None,
    rebuild: bool = False,
    expand: bool = False,
    association_limit: int = 8,
) -> dict[str, Any]:
    store_dir = Path(store_dir)
    db_path = index_path(store_dir)
    if rebuild or not db_path.exists():
        build_search_index(store_dir)

    active_kinds = {item for item in (kinds or []) if item}
    active_corpora = {item for item in (corpora or []) if item}
    fts_query = _fts_query(query)
    matches: list[dict[str, Any]] = []

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        where_clauses = ["docs_fts match ?"]
        params: list[Any] = [fts_query]
        if active_kinds:
            placeholders = ", ".join("?" for _ in active_kinds)
            where_clauses.append(f"docs.kind in ({placeholders})")
            params.extend(sorted(active_kinds))
        fetch_limit = max(limit * 8, limit) if active_corpora else limit
        params.append(fetch_limit)
        sql = f"""
            select
              docs.doc_key,
              docs.kind,
              docs.record_id,
              docs.path,
              docs.title,
              docs.status,
              docs.metadata,
              snippet(docs_fts, 1, '[', ']', '...', 28) as snippet,
              bm25(docs_fts) as rank
            from docs_fts
            join docs on docs.doc_key = docs_fts.doc_key
            where {" and ".join(where_clauses)}
            order by rank
            limit ?
        """
        # Corpus filters remain Python-side because corpus is stored in metadata JSON.
        rows = conn.execute(sql, params).fetchall()

    for row in rows:
        metadata = json.loads(row["metadata"] or "{}")
        if active_kinds and row["kind"] not in active_kinds:
            continue
        if active_corpora and str(metadata.get("corpus", "")) not in active_corpora:
            continue
        matches.append(
            {
                "doc_key": row["doc_key"],
                "kind": row["kind"],
                "record_id": row["record_id"],
                "path": row["path"],
                "title": row["title"],
                "status": row["status"],
                "score": row["rank"],
                "snippet": row["snippet"],
                "metadata": metadata,
            }
        )
        if len(matches) >= limit:
            break

    associations = expand_matches(store_dir, matches, limit_per_match=association_limit) if expand else {}

    return {
        "query_type": "indexed_search",
        "query": query,
        "index_path": str(db_path),
        "active_kinds": sorted(active_kinds),
        "active_corpora": sorted(active_corpora),
        "matches": matches,
        "associations": associations,
    }


def expand_matches(
    store_dir: str | Path,
    matches: list[dict[str, Any]],
    *,
    limit_per_match: int = 8,
) -> dict[str, list[dict[str, Any]]]:
    graph = _GraphContext(GroundRecallStore(store_dir))
    expansions: dict[str, list[dict[str, Any]]] = {}
    for match in matches:
        doc_key = str(match.get("doc_key", ""))
        kind = str(match.get("kind", ""))
        record_id = str(match.get("record_id", ""))
        path = str(match.get("path", ""))
        items = graph.expand(kind, record_id, path=path)
        expansions[doc_key] = _dedupe_associations(items)[:limit_per_match]
    return expansions


def iter_search_documents(store_dir: str | Path, *, include_source_notes: bool = True) -> Iterable[SearchDocument]:
    store_dir = Path(store_dir)
    store = GroundRecallStore(store_dir)

    for source in store.list_sources():
        yield SearchDocument(
            doc_key=f"source:{source.source_id}",
            kind="source",
            record_id=source.source_id,
            title=source.title or source.source_id,
            body=_join(source.title, source.source_type, source.path, source.url, source.metadata),
            path=source.path or source.url,
            status=source.current_status,
            metadata=source.metadata,
            source_path=_record_path(store.sources_dir, source.source_id),
        )

    for fragment in store.list_fragments():
        yield SearchDocument(
            doc_key=f"fragment:{fragment.fragment_id}",
            kind="fragment",
            record_id=fragment.fragment_id,
            title=fragment.section or fragment.fragment_id,
            body=_join(fragment.text, fragment.section, fragment.source_id, fragment.metadata),
            status=fragment.current_status,
            metadata=fragment.metadata,
            source_path=_record_path(store.fragments_dir, fragment.fragment_id),
        )

    for artifact in store.list_artifacts():
        metadata = artifact.metadata if isinstance(artifact.metadata, dict) else {}
        yield SearchDocument(
            doc_key=f"artifact:{artifact.artifact_id}",
            kind="artifact",
            record_id=artifact.artifact_id,
            title=artifact.title or artifact.artifact_id,
            body=_join(artifact.title, artifact.artifact_kind, artifact.path, metadata),
            path=artifact.path,
            status=artifact.current_status,
            metadata=metadata,
            source_path=_record_path(store.artifacts_dir, artifact.artifact_id),
        )

    for observation in store.list_observations():
        yield SearchDocument(
            doc_key=f"observation:{observation.observation_id}",
            kind="observation",
            record_id=observation.observation_id,
            title=observation.role or observation.observation_id,
            body=_join(observation.text, observation.role, observation.provenance.model_dump()),
            path=observation.provenance.origin_path,
            status=observation.current_status,
            metadata={"artifact_id": observation.artifact_id},
            source_path=_record_path(store.observations_dir, observation.observation_id),
        )

    for claim in store.list_claims():
        yield SearchDocument(
            doc_key=f"claim:{claim.claim_id}",
            kind="claim",
            record_id=claim.claim_id,
            title=claim.claim_text[:120] or claim.claim_id,
            body=_join(
                claim.claim_text,
                claim.claim_kind,
                claim.concept_ids,
                claim.metadata,
                claim.provenance.model_dump(),
            ),
            path=claim.provenance.origin_path,
            status=claim.current_status,
            metadata={"concept_ids": claim.concept_ids},
            source_path=_record_path(store.claims_dir, claim.claim_id),
        )

    for concept in store.list_concepts():
        yield SearchDocument(
            doc_key=f"concept:{concept.concept_id}",
            kind="concept",
            record_id=concept.concept_id,
            title=concept.title,
            body=_join(concept.title, concept.aliases, concept.description, concept.source_artifact_ids),
            status=concept.current_status,
            metadata={"aliases": concept.aliases, "source_artifact_ids": concept.source_artifact_ids},
            source_path=_record_path(store.concepts_dir, concept.concept_id.replace("::", "__")),
        )

    for relation in store.list_relations():
        yield SearchDocument(
            doc_key=f"relation:{relation.relation_id}",
            kind="relation",
            record_id=relation.relation_id,
            title=relation.relation_type,
            body=_join(relation.source_id, relation.target_id, relation.relation_type, relation.evidence_ids),
            status=relation.current_status,
            metadata={"source_id": relation.source_id, "target_id": relation.target_id},
            source_path=_record_path(store.relations_dir, relation.relation_id),
        )

    for review in store.list_review_candidates():
        yield SearchDocument(
            doc_key=f"review_candidate:{review.review_candidate_id}",
            kind="review_candidate",
            record_id=review.review_candidate_id,
            title=review.rationale[:120] or review.review_candidate_id,
            body=_join(review.candidate_type, review.candidate_id, review.triage_lane, review.finding_codes, review.rationale),
            status=review.current_status,
            metadata={"candidate_type": review.candidate_type, "candidate_id": review.candidate_id},
            source_path=_record_path(store.review_candidates_dir, review.review_candidate_id),
        )

    for promotion in store.list_promotions():
        yield SearchDocument(
            doc_key=f"promotion:{promotion.promotion_id}",
            kind="promotion",
            record_id=promotion.promotion_id,
            title=promotion.notes[:120] or promotion.promotion_id,
            body=_join(promotion.candidate_type, promotion.candidate_id, promotion.verdict, promotion.reviewer, promotion.notes),
            status=promotion.verdict,
            metadata={"candidate_type": promotion.candidate_type, "candidate_id": promotion.candidate_id},
            source_path=_record_path(store.promotions_dir, promotion.promotion_id),
        )

    if include_source_notes:
        for note_path in _source_note_paths(store_dir):
            text = note_path.read_text(encoding="utf-8", errors="replace")
            title = _markdown_title(text) or note_path.stem
            yield SearchDocument(
                doc_key=f"source_note:{note_path.name}",
                kind="source_note",
                record_id=note_path.stem,
                title=title,
                body=text,
                path=str(note_path),
                status="local",
                metadata={"source_note": True},
                source_path=note_path,
            )


class _GraphContext:
    def __init__(self, store: GroundRecallStore):
        self.store = store
        self.sources = {item.source_id: item for item in store.list_sources()}
        self.fragments = {item.fragment_id: item for item in store.list_fragments()}
        self.artifacts = {item.artifact_id: item for item in store.list_artifacts()}
        self.observations = {item.observation_id: item for item in store.list_observations()}
        self.claims = {item.claim_id: item for item in store.list_claims()}
        self.concepts = {item.concept_id: item for item in store.list_concepts()}
        self.relations = {item.relation_id: item for item in store.list_relations()}
        self.review_candidates = {item.review_candidate_id: item for item in store.list_review_candidates()}

        self.claims_by_concept: dict[str, list[Any]] = {}
        self.claims_by_observation: dict[str, list[Any]] = {}
        self.claims_by_fragment: dict[str, list[Any]] = {}
        self.observations_by_artifact: dict[str, list[Any]] = {}
        self.concepts_by_artifact: dict[str, list[Any]] = {}
        self.relations_by_endpoint: dict[str, list[Any]] = {}
        self.review_candidates_by_candidate: dict[str, list[Any]] = {}
        self.claims_by_origin_path: dict[str, list[Any]] = {}
        self.observations_by_origin_path: dict[str, list[Any]] = {}

        for claim in self.claims.values():
            for concept_id in claim.concept_ids:
                self.claims_by_concept.setdefault(concept_id, []).append(claim)
            for observation_id in claim.source_observation_ids:
                self.claims_by_observation.setdefault(observation_id, []).append(claim)
            for fragment_id in claim.supporting_fragment_ids:
                self.claims_by_fragment.setdefault(fragment_id, []).append(claim)
            origin_path = claim.provenance.origin_path
            if origin_path:
                self.claims_by_origin_path.setdefault(origin_path, []).append(claim)
                self.claims_by_origin_path.setdefault(Path(origin_path).name, []).append(claim)

        for observation in self.observations.values():
            self.observations_by_artifact.setdefault(observation.artifact_id, []).append(observation)
            origin_path = observation.provenance.origin_path
            if origin_path:
                self.observations_by_origin_path.setdefault(origin_path, []).append(observation)
                self.observations_by_origin_path.setdefault(Path(origin_path).name, []).append(observation)

        for concept in self.concepts.values():
            for artifact_id in concept.source_artifact_ids:
                self.concepts_by_artifact.setdefault(artifact_id, []).append(concept)

        for relation in self.relations.values():
            self.relations_by_endpoint.setdefault(relation.source_id, []).append(relation)
            self.relations_by_endpoint.setdefault(relation.target_id, []).append(relation)

        for review in self.review_candidates.values():
            self.review_candidates_by_candidate.setdefault(review.candidate_id, []).append(review)

    def expand(self, kind: str, record_id: str, *, path: str = "") -> list[dict[str, Any]]:
        if kind == "concept":
            return self._expand_concept(record_id)
        if kind == "claim":
            return self._expand_claim(record_id)
        if kind == "observation":
            return self._expand_observation(record_id)
        if kind == "artifact":
            return self._expand_artifact(record_id)
        if kind == "relation":
            return self._expand_relation(record_id)
        if kind == "fragment":
            return self._expand_fragment(record_id)
        if kind == "review_candidate":
            return self._expand_review_candidate(record_id)
        if kind == "source_note":
            return self._expand_source_note(path)
        return []

    def _expand_concept(self, concept_id: str) -> list[dict[str, Any]]:
        concept = self.concepts.get(concept_id)
        items: list[dict[str, Any]] = []
        if concept is None:
            return items
        items.extend(_assoc("claim_for_concept", "claim", claim.claim_id, claim.claim_text, claim.current_status) for claim in self.claims_by_concept.get(concept_id, []))
        items.extend(_assoc("relation_for_concept", "relation", relation.relation_id, _relation_title(relation), relation.current_status) for relation in self.relations_by_endpoint.get(concept_id, []))
        items.extend(_assoc("source_artifact_for_concept", "artifact", artifact_id, self.artifacts[artifact_id].title, self.artifacts[artifact_id].current_status) for artifact_id in concept.source_artifact_ids if artifact_id in self.artifacts)
        items.extend(_assoc("review_candidate_for_concept", "review_candidate", review.review_candidate_id, review.rationale, review.current_status) for review in self.review_candidates_by_candidate.get(concept_id, []))
        return items

    def _expand_claim(self, claim_id: str) -> list[dict[str, Any]]:
        claim = self.claims.get(claim_id)
        items: list[dict[str, Any]] = []
        if claim is None:
            return items
        items.extend(_assoc("concept_for_claim", "concept", concept_id, self.concepts[concept_id].title, self.concepts[concept_id].current_status) for concept_id in claim.concept_ids if concept_id in self.concepts)
        items.extend(_assoc("source_observation_for_claim", "observation", observation_id, self.observations[observation_id].text, self.observations[observation_id].current_status) for observation_id in claim.source_observation_ids if observation_id in self.observations)
        items.extend(_assoc("supporting_fragment_for_claim", "fragment", fragment_id, self.fragments[fragment_id].text, self.fragments[fragment_id].current_status) for fragment_id in claim.supporting_fragment_ids if fragment_id in self.fragments)
        linked_claim_ids = claim.contradicts_claim_ids + claim.supersedes_claim_ids
        items.extend(_assoc("linked_claim", "claim", linked_id, self.claims[linked_id].claim_text, self.claims[linked_id].current_status) for linked_id in linked_claim_ids if linked_id in self.claims)
        items.extend(_assoc("review_candidate_for_claim", "review_candidate", review.review_candidate_id, review.rationale, review.current_status) for review in self.review_candidates_by_candidate.get(claim_id, []))
        return items

    def _expand_observation(self, observation_id: str) -> list[dict[str, Any]]:
        observation = self.observations.get(observation_id)
        items: list[dict[str, Any]] = []
        if observation is None:
            return items
        artifact = self.artifacts.get(observation.artifact_id)
        if artifact is not None:
            items.append(_assoc("artifact_for_observation", "artifact", artifact.artifact_id, artifact.title, artifact.current_status))
        items.extend(_assoc("claim_from_observation", "claim", claim.claim_id, claim.claim_text, claim.current_status) for claim in self.claims_by_observation.get(observation_id, []))
        return items

    def _expand_artifact(self, artifact_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        items.extend(_assoc("observation_for_artifact", "observation", observation.observation_id, observation.text, observation.current_status) for observation in self.observations_by_artifact.get(artifact_id, []))
        items.extend(_assoc("concept_from_artifact", "concept", concept.concept_id, concept.title, concept.current_status) for concept in self.concepts_by_artifact.get(artifact_id, []))
        for observation in self.observations_by_artifact.get(artifact_id, []):
            items.extend(_assoc("claim_from_artifact_observation", "claim", claim.claim_id, claim.claim_text, claim.current_status) for claim in self.claims_by_observation.get(observation.observation_id, []))
        return items

    def _expand_relation(self, relation_id: str) -> list[dict[str, Any]]:
        relation = self.relations.get(relation_id)
        items: list[dict[str, Any]] = []
        if relation is None:
            return items
        for endpoint_id, label in ((relation.source_id, "relation_source"), (relation.target_id, "relation_target")):
            if endpoint_id in self.concepts:
                concept = self.concepts[endpoint_id]
                items.append(_assoc(label, "concept", concept.concept_id, concept.title, concept.current_status))
            elif endpoint_id in self.claims:
                claim = self.claims[endpoint_id]
                items.append(_assoc(label, "claim", claim.claim_id, claim.claim_text, claim.current_status))
        return items

    def _expand_fragment(self, fragment_id: str) -> list[dict[str, Any]]:
        fragment = self.fragments.get(fragment_id)
        items: list[dict[str, Any]] = []
        if fragment is None:
            return items
        source = self.sources.get(fragment.source_id)
        if source is not None:
            items.append(_assoc("source_for_fragment", "source", source.source_id, source.title, source.current_status))
        items.extend(_assoc("claim_from_fragment", "claim", claim.claim_id, claim.claim_text, claim.current_status) for claim in self.claims_by_fragment.get(fragment_id, []))
        return items

    def _expand_review_candidate(self, review_candidate_id: str) -> list[dict[str, Any]]:
        review = self.review_candidates.get(review_candidate_id)
        if review is None:
            return []
        if review.candidate_type == "claim" and review.candidate_id in self.claims:
            claim = self.claims[review.candidate_id]
            return [_assoc("reviewed_claim", "claim", claim.claim_id, claim.claim_text, claim.current_status)]
        if review.candidate_type == "concept" and review.candidate_id in self.concepts:
            concept = self.concepts[review.candidate_id]
            return [_assoc("reviewed_concept", "concept", concept.concept_id, concept.title, concept.current_status)]
        if review.candidate_type == "relation" and review.candidate_id in self.relations:
            relation = self.relations[review.candidate_id]
            return [_assoc("reviewed_relation", "relation", relation.relation_id, _relation_title(relation), relation.current_status)]
        return []

    def _expand_source_note(self, path: str) -> list[dict[str, Any]]:
        if not path:
            return []
        candidates = {path, Path(path).name}
        items: list[dict[str, Any]] = []
        for candidate in candidates:
            items.extend(_assoc("claim_with_origin_path", "claim", claim.claim_id, claim.claim_text, claim.current_status) for claim in self.claims_by_origin_path.get(candidate, []))
            items.extend(_assoc("observation_with_origin_path", "observation", observation.observation_id, observation.text, observation.current_status) for observation in self.observations_by_origin_path.get(candidate, []))
        return items


def _assoc(association_type: str, kind: str, record_id: str, title: str, status: str = "") -> dict[str, Any]:
    return {
        "association_type": association_type,
        "kind": kind,
        "record_id": record_id,
        "title": str(title or record_id)[:240],
        "status": status,
    }


def _dedupe_associations(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        key = (str(item.get("association_type", "")), str(item.get("kind", "")), str(item.get("record_id", "")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _relation_title(relation: Any) -> str:
    return f"{relation.source_id} {relation.relation_type} {relation.target_id}"


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.execute("create table if not exists meta(key text primary key, value text not null)")
    conn.execute(
        """
        create table if not exists docs(
          doc_key text not null unique,
          kind text not null,
          record_id text not null,
          path text not null default '',
          title text not null default '',
          status text not null default '',
          metadata text not null default '{}'
        )
        """
    )
    conn.execute(
        """
        create virtual table if not exists docs_fts using fts5(
          doc_key unindexed,
          title,
          body,
          metadata
        )
        """
    )


def _record_path(directory: Path, key: str) -> Path:
    return directory / f"{key}.json"


def _source_note_paths(store_dir: Path) -> list[Path]:
    candidates = []
    if store_dir.name == "store":
        candidates.append(store_dir.parent / "source-notes")
    candidates.append(store_dir / "source-notes")
    paths: list[Path] = []
    for directory in candidates:
        if directory.is_dir():
            paths.extend(sorted(directory.glob("*.md")))
    return paths


def _markdown_title(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""


def _join(*values: Any) -> str:
    parts: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            parts.append(value)
        else:
            parts.append(json.dumps(value, sort_keys=True, default=str))
    return "\n".join(part for part in parts if part)


def _fts_query(query: str) -> str:
    tokens = re.findall(r"[\w][\w:-]*", query.lower())
    if not tokens:
        return '""'
    # Quote each token to avoid accidental FTS operators from user text.
    return " OR ".join(f'"{token}"' for token in tokens)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build or query the GroundRecall local FTS index.")
    parser.add_argument("store_dir")
    parser.add_argument("query", nargs="?", default="")
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--kind", action="append", default=[])
    parser.add_argument("--corpus", action="append", default=[])
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--expand", action="store_true", help="Include bounded graph associations for each match")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.rebuild or not args.query:
        payload = build_search_index(args.store_dir)
    else:
        payload = search_index(
            args.store_dir,
            args.query,
            limit=args.limit,
            kinds=list(args.kind or []),
            corpora=list(args.corpus or []),
            expand=args.expand,
        )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
