"""Read-only application service for GroundRecall's versioned application contract.

This module is intentionally independent of HTTP, MCP, and browser concerns.
Adapters can pass validated contract objects to the service and serialize the
returned Pydantic envelopes in whatever protocol they support.
"""
from __future__ import annotations

from pathlib import Path
import re
import json
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from .application_contract import (
    ApplicationResult,
    CapabilityResponse,
    MatchReason,
    RecordResponse,
    SearchRequest,
    SearchResponse,
    SourceReference,
)
from .search_index import expand_matches, search_index
from .store import GroundRecallStore
from .policy import RELEASE_RANK


_GETTERS: dict[str, str] = {
    "source": "get_source",
    "fragment": "get_fragment",
    "artifact": "get_artifact",
    "observation": "get_observation",
    "claim": "get_claim",
    "concept": "get_concept",
    "relation": "get_relation",
    "review_candidate": "get_review_candidate",
    "promotion": "get_promotion",
}
_RECORD_DIRECTORIES = {
    "source": "sources_dir", "fragment": "fragments_dir", "artifact": "artifacts_dir",
    "observation": "observations_dir", "claim": "claims_dir", "concept": "concepts_dir",
    "relation": "relations_dir", "review_candidate": "review_candidates_dir", "promotion": "promotions_dir",
}


def _request_id() -> str:
    return "app-" + uuid4().hex


def _generation(index_path: Path) -> str:
    """Return an opaque generation that changes when the derived index changes."""
    try:
        stat = index_path.stat()
        return f"search-index-v1:{stat.st_mtime_ns}:{stat.st_size}"
    except FileNotFoundError:
        return "search-index-v1:missing"


def _stable_id(kind: str, record_id: str) -> str:
    return f"{kind}::{record_id}"


def _human_url(stable_id: str) -> str:
    return "/records/" + quote(stable_id, safe="")


_LOCAL_PATH = re.compile(r"(?<![A-Za-z0-9])/(?:home|tmp|var|mnt|opt|srv|workspace)(?:/[^\s\"'<>\]\[(),]*)*")


def _public_text(value: Any, *, limit: int | None = None) -> str:
    """Keep local store/source paths out of the transport-facing result."""
    text = _LOCAL_PATH.sub("[local path redacted]", str(value))
    return text[:limit] if limit is not None else text


def _result_from_match(match: dict[str, Any]) -> ApplicationResult:
    kind = str(match.get("kind", "record"))
    record_id = str(match.get("record_id", ""))
    metadata = match.get("metadata") if isinstance(match.get("metadata"), dict) else {}
    source_refs = [
        SourceReference(source_id=_public_text(source_id))
        for source_id in metadata.get("source_ids", [])
        if str(source_id)
    ]
    return ApplicationResult(
        stable_id=_stable_id(kind, record_id),
        kind=kind,
        title=_public_text(match.get("title", "")),
        excerpt=_public_text(match.get("snippet", ""), limit=4096),
        human_url=_human_url(_stable_id(kind, record_id)),
        source_references=source_refs,
        review_state=_public_text(match.get("status", "unknown")) or "unknown",
        match_reason=MatchReason(kind="lexical", detail="matched indexed content"),
    )


def _record_text(record: Any) -> tuple[str, str]:
    data = record.model_dump(mode="json")
    title = str(
        data.get("title")
        or data.get("claim_text")
        or data.get("section")
        or data.get("role")
        or data.get("relation_type")
        or data.get("rationale")
        or data.get("source_id")
        or data.get("artifact_id")
        or ""
    )
    excerpt = str(
        data.get("description")
        or data.get("text")
        or data.get("summary")
        or data.get("claim_text")
        or data.get("question")
        or data.get("rationale")
        or title
    )
    return _public_text(title), _public_text(excerpt, limit=4096)


class ApplicationReadService:
    """Bounded, read-only facade for search, record lookup, and capabilities."""

    def __init__(self, store_dir: str | Path, *, scope: str = "private", auto_build: bool = True,
                 maximum_release_level: str = "private", source_notes_dirs: list[str | Path] | None = None):
        if maximum_release_level not in RELEASE_RANK:
            raise ValueError(f"unsupported maximum release level: {maximum_release_level}")
        self.store_dir = Path(store_dir)
        self.scope = scope
        self.auto_build = auto_build
        self.maximum_release_level = maximum_release_level
        if source_notes_dirs is None:
            candidates = ([self.store_dir.parent / "source-notes"] if self.store_dir.name == "store" else [])
            candidates.append(self.store_dir / "source-notes")
            self.source_notes_dirs = candidates
        else:
            self.source_notes_dirs = [Path(path) for path in source_notes_dirs]
        self._visibility_cache: dict[tuple[str, str], bool] = {}

    def clear_visibility_cache(self) -> None:
        """Start a fresh authorization projection for each dashboard request."""
        self._visibility_cache.clear()

    @staticmethod
    def _record_release(record: Any) -> str | None:
        data = record.model_dump(mode="json") if hasattr(record, "model_dump") else record
        if not isinstance(data, dict):
            return None
        values = [data[key] for key in ("release_level", "source_release_level") if key in data]
        # Legacy records without a release field are private by default. Invalid
        # explicit labels fail closed rather than being treated as public.
        if not values:
            return "private"
        if any(value not in RELEASE_RANK for value in values):
            return None
        return max(values, key=RELEASE_RANK.__getitem__)

    def _record_visible(self, kind: str, record_id: str, visiting: set[tuple[str, str]] | None = None) -> bool:
        # Resolve a complete dependency closure before committing positive cache
        # entries. A cycle may be provisionally traversable, then fail on a
        # different dependency elsewhere in the same closure.
        root_call = visiting is None
        path = set() if visiting is None else visiting
        memo: dict[tuple[str, str], bool] = {}
        result = self._resolve_record_visible(kind, record_id, path, memo)
        if root_call:
            if result:
                self._visibility_cache.update(memo)
            else:
                self._visibility_cache[(kind, record_id)] = False
        return result

    def _resolve_record_visible(self, kind: str, record_id: str,
                                visiting: set[tuple[str, str]],
                                memo: dict[tuple[str, str], bool]) -> bool:
        key = (kind, record_id)
        if key in self._visibility_cache:
            return self._visibility_cache[key]
        if key in memo:
            return memo[key]
        getter_name = _GETTERS.get(kind)
        if getter_name is None:
            if kind == "source_note":
                memo[key] = self.maximum_release_level == "private" and self._current_source_note(record_id) is not None
                return memo[key]
            memo[key] = False
            return memo[key]
        if key in visiting:
            return True
        visiting.add(key)
        store = GroundRecallStore(self.store_dir, create=False)
        directory_name = _RECORD_DIRECTORIES.get(kind)
        record_key = record_id.replace("::", "__") if kind == "concept" else record_id
        record_path = getattr(store, directory_name) / f"{record_key}.json" if directory_name else None
        try:
            if record_path is None or record_path.is_symlink():
                raw_record = None
            else:
                raw_record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            raw_record = None
        release = self._record_release(raw_record)
        visible = release is not None and RELEASE_RANK[release] <= RELEASE_RANK[self.maximum_release_level]
        try:
            record = getattr(store, getter_name)(record_id) if visible else None
        except Exception:
            record = None
        if record is None:
            visible = False
        else:
            if visible:
                data = record.model_dump(mode="json")
                dependencies: list[tuple[str, str]] = []
                if kind in {"source", "artifact"}:
                    dependencies.extend(("source", str(item)) for item in data.get("derivative_source_ids", []) if str(item))
                if kind == "fragment":
                    dependencies.append(("source", str(data.get("source_id", ""))))
                if kind == "observation" and data.get("artifact_id"):
                    dependencies.append(("artifact", str(data["artifact_id"])))
                if kind == "claim":
                    dependencies.extend(("observation", str(item)) for item in data.get("source_observation_ids", []))
                    dependencies.extend(("fragment", str(item)) for item in data.get("supporting_fragment_ids", []))
                if kind == "concept":
                    dependencies.extend(("artifact", str(item)) for item in data.get("source_artifact_ids", []))
                if kind == "relation":
                    for endpoint in (str(data.get("source_id", "")), str(data.get("target_id", ""))):
                        for endpoint_kind in ("concept", "claim"):
                            if getattr(store, _GETTERS[endpoint_kind])(endpoint) is not None:
                                dependencies.append((endpoint_kind, endpoint))
                                break
                    for evidence_id in data.get("evidence_ids", []):
                        for evidence_kind in ("claim", "observation", "fragment", "artifact", "source"):
                            if getattr(store, _GETTERS[evidence_kind])(str(evidence_id)) is not None:
                                dependencies.append((evidence_kind, str(evidence_id)))
                                break
                visible = all(
                    self._resolve_record_visible(dep_kind, dep_id, visiting, memo)
                    for dep_kind, dep_id in dependencies if dep_id
                )
        visiting.remove(key)
        memo[key] = visible
        return visible

    def _index_path(self) -> Path:
        return self.store_dir / ".index" / "groundrecall-search.sqlite"

    def _current_source_note(self, record_id: str, indexed_path: Any = None) -> tuple[str, str] | None:
        """Resolve indexed notes against current files under configured note roots."""
        if self.maximum_release_level != "private" or not record_id or Path(record_id).name != record_id or record_id in {".", ".."}:
            return None
        if indexed_path is None:
            candidates = [root / (record_id + ".md") for root in self.source_notes_dirs if root.is_dir()]
            if len(candidates) != 1:
                return None
            candidate = candidates[0]
        elif isinstance(indexed_path, str):
            candidate = Path(indexed_path)
            if candidate.name != record_id + ".md":
                return None
        else:
            return None
        if candidate.is_symlink() or not candidate.is_file():
            return None
        try:
            resolved = candidate.resolve(strict=True)
            if not any(resolved.is_relative_to(root.resolve()) for root in self.source_notes_dirs if root.is_dir()):
                return None
            content = resolved.read_text(encoding="utf-8", errors="replace")
        except (OSError, RuntimeError, ValueError):
            return None
        title = next((line.strip().lstrip("#").strip() for line in content.splitlines()
                      if line.strip().startswith("#")), record_id)
        return title, content

    def capabilities(self, *, request_id: str | None = None) -> CapabilityResponse:
        generation = _generation(self._index_path())
        return CapabilityResponse(
            request_id=request_id or _request_id(),
            index_generations=[] if generation.endswith(":missing") else [generation],
        )

    def search(self, request: SearchRequest, *, request_id: str | None = None) -> SearchResponse:
        self.clear_visibility_cache()
        candidate_limit = request.limit if self.maximum_release_level == "private" else min(1000, request.limit * 10)
        payload = search_index(
            self.store_dir,
            request.query,
            limit=candidate_limit,
            kinds=request.kinds,
            corpora=request.corpora,
            rebuild=self.auto_build and not self._index_path().exists(),
            scope=request.scope or self.scope,
            allow_build=self.auto_build,
        )
        visible_matches = []
        for item in payload.get("matches", []):
            kind, record_id = str(item.get("kind", "")), str(item.get("record_id", ""))
            if kind == "source_note":
                note = self._current_source_note(record_id, item.get("path"))
                if note is None:
                    continue
                terms = re.findall(r"[\w][\w:-]*", request.query.casefold())
                current_terms = set(re.findall(r"[\w][\w:-]*", (note[0] + " " + note[1]).casefold()))
                if terms and not any(term in current_terms for term in terms):
                    continue
                item = dict(item)
                item["title"], item["snippet"], item["status"] = note[0], note[1], "local"
                visible_matches.append(item)
                if len(visible_matches) >= request.limit:
                    break
                continue
            getter_name = _GETTERS.get(kind)
            if not self._record_visible(kind, record_id):
                continue
            if self.maximum_release_level != "private":
                record = getattr(GroundRecallStore(self.store_dir, create=False), getter_name)(record_id) if getter_name else None
                if record is None:
                    continue
                # The index is derived and may lag behind canonical updates. Never
                # return its old title/snippet under a lower release ceiling, and
                # don't let a stale private term make a newly public record match.
                terms = re.findall(r"[\w][\w:-]*", request.query.casefold())
                current_text = json.dumps(record.model_dump(mode="json"), sort_keys=True, default=str).casefold()
                current_terms = set(re.findall(r"[\w][\w:-]*", current_text))
                if terms and not any(term in current_terms for term in terms):
                    continue
                item = dict(item)
                item["title"], item["snippet"] = _record_text(record)
                item["status"] = str(getattr(record, "current_status", "unknown"))
                metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                item["metadata"] = dict(metadata)
            visible_matches.append(item)
            if len(visible_matches) >= request.limit:
                break
        matches = []
        for item in visible_matches:
            result = _result_from_match(item)
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            allowed_sources = [
                source_id for source_id in metadata.get("source_ids", [])
                if self._record_visible("source", str(source_id))
            ]
            result = result.model_copy(update={
                "source_references": [SourceReference(source_id=_public_text(source_id)) for source_id in allowed_sources]
            })
            matches.append(result)
        generation = _generation(Path(str(payload["index_path"])))
        diagnostics: list[str] = []
        if not matches:
            diagnostics.append(
                "no matching records returned in this view"
                if self.maximum_release_level != "private"
                else "no indexed records matched the query"
            )
        return SearchResponse(
            request_id=request_id or _request_id(),
            index_generation=generation,
            effective_scope=request.scope or self.scope,
            results=matches,
            diagnostics=diagnostics,
        )

    def read_record(self, stable_id: str, *, scope: str | None = None, request_id: str | None = None) -> RecordResponse | None:
        self.clear_visibility_cache()
        if "::" not in stable_id:
            return None
        kind, record_id = stable_id.split("::", 1)
        getter_name = _GETTERS.get(kind)
        if kind == "source_note":
            note = self._current_source_note(record_id)
            if note is None:
                return None
            title, content = note
            note_result = ApplicationResult(
                stable_id=stable_id, kind=kind, title=_public_text(title),
                excerpt=_public_text(content, limit=4096), human_url=_human_url(stable_id),
                review_state="local", match_reason=MatchReason(kind="exact_id", detail="current source-note filename"),
            )
            return RecordResponse(
                request_id=request_id or _request_id(), index_generation=_generation(self._index_path()),
                effective_scope=scope or self.scope, record=note_result,
            )
        if getter_name is None:
            return None
        if not self._record_visible(kind, record_id):
            return None
        record = getattr(GroundRecallStore(self.store_dir, create=False), getter_name)(record_id)
        if record is None:
            return None
        title, excerpt = _record_text(record)
        result = ApplicationResult(
            stable_id=stable_id,
            kind=kind,
            title=title,
            excerpt=excerpt,
            human_url=_human_url(stable_id),
            review_state=str(getattr(record, "current_status", "unknown")),
            match_reason=MatchReason(kind="exact_id", detail="stable record identifier"),
        )
        # Expansion is derived from canonical records and never writes to them.
        associations = expand_matches(self.store_dir, [{"doc_key": f"{kind}:{record_id}", "kind": kind, "record_id": record_id}])
        visible_associations = [
            item for item in associations.get(f"{kind}:{record_id}", [])
            if self.maximum_release_level == "private" or self._record_visible(str(item.get("kind", "")), str(item.get("record_id", "")))
        ]
        return RecordResponse(
            request_id=request_id or _request_id(),
            index_generation=_generation(self._index_path()),
            effective_scope=scope or self.scope,
            record=result,
            relationships=visible_associations,
        )
