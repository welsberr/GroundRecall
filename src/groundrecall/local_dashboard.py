"""Per-user, loopback-only dashboard. Canonical knowledge remains read-only."""
from __future__ import annotations

import argparse
from copy import deepcopy
from collections import deque
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import statistics
from threading import RLock
from time import monotonic, perf_counter
from urllib.parse import parse_qs, quote, urlsplit

from .application_http import ApplicationHTTPDispatcher
from .application_service import ApplicationReadService, _public_text
from .dashboard_assets import HTML, CSS, JS, LOGIN
from .epistemap_adapter import graph_bundle_from_rows
from .review_backlog import aggregate_backlog
from .store import GroundRecallStore
from .policy import RELEASE_RANK


COLLECTIONS = ('sources', 'fragments', 'artifacts', 'observations', 'claims', 'concepts',
               'relations', 'review_candidates', 'promotions', 'adjudications', 'scopes',
               'works', 'decisions', 'contradiction_cases', 'review_receipts',
               'contributions', 'contribution_review_receipts', 'federation_feedback',
               'stewardship', 'custody_events', 'snapshots')
COLLECTION_ID_FIELDS = {
    'sources': ('source', 'source_id'), 'fragments': ('fragment', 'fragment_id'),
    'artifacts': ('artifact', 'artifact_id'), 'observations': ('observation', 'observation_id'),
    'claims': ('claim', 'claim_id'), 'concepts': ('concept', 'concept_id'),
    'relations': ('relation', 'relation_id'), 'review_candidates': ('review_candidate', 'review_candidate_id'),
    'promotions': ('promotion', 'promotion_id'),
}


class DashboardService:
    """Owner-local projections, cached for 30 seconds; never used as team ACLs."""

    def __init__(self, store_dir: str | Path, workspace: str | Path | None = None,
                 maximum_release_level: str = 'private'):
        if maximum_release_level not in RELEASE_RANK:
            raise ValueError('maximum_release_level must be public, internal, confidential, privileged, or private')
        self.root = Path(store_dir).resolve()
        if not self.root.is_dir() or not (self.root / 'concepts').is_dir():
            raise ValueError('Select an existing canonical GroundRecall store')
        GroundRecallStore(self.root, create=False)
        self.workspace = Path(workspace).resolve() if workspace else None
        self.maximum_release_level = maximum_release_level
        self.layout = None
        if self.workspace and (self.workspace / 'workspace.json').exists():
            from .workspace import load_workspace_layout
            self.layout = load_workspace_layout(self.workspace)
            if self.layout.canonical_store != self.root:
                raise ValueError('Workspace manifest and selected canonical store disagree')
        self.application = ApplicationHTTPDispatcher(ApplicationReadService(
            self.root, auto_build=False, maximum_release_level=maximum_release_level,
            source_notes_dirs=[self.layout.source_notes] if self.layout else None,
        ))
        self.lock = RLock()
        self.cache = {}
        self.search_times = deque(maxlen=200)

    def cached(self, key, loader):
        with self.lock:
            entry = self.cache.get(key)
            if entry and monotonic() - entry[0] < 30:
                return entry[1]
            result = loader()
            self.cache[key] = (monotonic(), result)
            return result

    def record_visible(self, payload):
        """Fail closed for malformed release labels and legacy-private records."""
        if not isinstance(payload, dict):
            return False
        labels = [payload[key] for key in ('release_level', 'source_release_level') if key in payload]
        if not labels:
            labels = ['private']
        return all(
            isinstance(label, str) and label in RELEASE_RANK
            and RELEASE_RANK[label] <= RELEASE_RANK[self.maximum_release_level]
            for label in labels
        )

    def canonical_record_visible(self, collection, payload):
        if not self.record_visible(payload):
            return False
        descriptor = COLLECTION_ID_FIELDS.get(collection)
        if descriptor:
            kind, field = descriptor
            record_id = payload.get(field)
            if not isinstance(record_id, str) or not self.application.service._record_visible(kind, record_id):
                return False
        return True

    def payload_visible(self, payload, *, _top_level=True):
        """Recheck record-bearing API payloads immediately before serialization."""
        if _top_level:
            self.application.service.clear_visibility_cache()
        if isinstance(payload, list):
            return all(self.payload_visible(item, _top_level=False) for item in payload)
        if not isinstance(payload, dict):
            return True
        if 'release_level' in payload or 'source_release_level' in payload:
            if not self.record_visible(payload):
                return False
        stable_id = payload.get('stable_id')
        if isinstance(stable_id, str) and '::' in stable_id:
            kind, record_id = stable_id.split('::', 1)
            if not self.application.service._record_visible(kind, record_id):
                return False
        record_kind = payload.get('record_kind')
        record_id = payload.get('id')
        if isinstance(record_kind, str) and isinstance(record_id, str):
            if not self.application.service._record_visible(record_kind, record_id):
                return False
        if isinstance(payload.get('kind'), str) and isinstance(payload.get('record_id'), str):
            if not self.application.service._record_visible(payload['kind'], payload['record_id']):
                return False
        return all(self.payload_visible(value, _top_level=False) for value in payload.values())

    def overview(self):
        self.application.service.clear_visibility_cache()
        def inventory():
            counts, size, failures = {}, 0, 0
            if self.maximum_release_level == 'private':
                # The owner-local full-ceiling view can summarize file metadata
                # without parsing every record. Large workspaces may contain
                # tens of thousands of JSON files; parsing and dependency checks
                # here made the first dashboard request take tens of seconds.
                for name in COLLECTIONS:
                    counts[name] = 0
                    try:
                        entries = os.scandir(self.root / name)
                    except OSError:
                        failures += 1
                        continue
                    with entries:
                        for entry in entries:
                            if not entry.name.endswith('.json'):
                                continue
                            try:
                                if entry.is_file(follow_symlinks=False):
                                    stat = entry.stat(follow_symlinks=False)
                                    counts[name] += 1
                                    size += stat.st_size
                                else:
                                    failures += 1
                            except OSError:
                                failures += 1
                index = self.root / '.index' / 'groundrecall-search.sqlite'
                index_stat = index.stat() if index.is_file() else None
                disk = shutil.disk_usage(self.root)
                return dict(counts=counts, record_bytes=size, unreadable_files=failures,
                            inventory_validation='file_metadata_only',
                            disk_free_bytes=disk.free, disk_total_bytes=disk.total,
                            index_present=index_stat is not None,
                            index_bytes=index_stat.st_size if index_stat else None,
                            index_modified_at=datetime.fromtimestamp(index_stat.st_mtime, timezone.utc).isoformat() if index_stat else None,
                            index_age_seconds=max(0, int(datetime.now(timezone.utc).timestamp() - index_stat.st_mtime)) if index_stat else None,
                            measured_at=datetime.now(timezone.utc).isoformat())
            for name in COLLECTIONS:
                counts[name] = 0
                for path in (self.root / name).glob('*.json'):
                    if path.is_symlink():
                        if self.maximum_release_level == 'private':
                            failures += 1
                        continue
                    try:
                        row = json.loads(path.read_text(encoding='utf-8'))
                        if not self.canonical_record_visible(name, row):
                            continue
                        size += path.stat().st_size
                        counts[name] += 1
                    except (OSError, ValueError, TypeError):
                        if self.maximum_release_level == 'private':
                            failures += 1
            index = self.root / '.index' / 'groundrecall-search.sqlite'
            index_stat = index.stat() if index.is_file() and self.maximum_release_level == 'private' else None
            disk = shutil.disk_usage(self.root)
            return dict(counts=counts, record_bytes=size,
                        unreadable_files=failures if self.maximum_release_level == 'private' else None,
                        inventory_validation='release_checked_records',
                        disk_free_bytes=disk.free, disk_total_bytes=disk.total,
                        index_present=index_stat is not None if self.maximum_release_level == 'private' else None,
                        index_bytes=index_stat.st_size if index_stat else None,
                        index_modified_at=datetime.fromtimestamp(index_stat.st_mtime, timezone.utc).isoformat() if index_stat else None,
                        index_age_seconds=max(0, int(datetime.now(timezone.utc).timestamp() - index_stat.st_mtime)) if index_stat else None,
                        measured_at=datetime.now(timezone.utc).isoformat())
        # Capped views must observe reclassification immediately; a 30-second
        # inventory cache could otherwise retain a formerly public count.
        result = dict(self.cached('inventory', inventory) if self.maximum_release_level == 'private' else inventory())
        with self.lock:
            samples = list(self.search_times)
        result['retrieval'] = dict(samples=len(samples), median_ms=round(statistics.median(samples), 1) if samples else None,
                                   max_ms=round(max(samples), 1) if samples else None,
                                   coverage='Successful searches through this dashboard process; latest 200')
        result['runtime'] = dict(status='not_connected', open_sessions=None, agents=None, assistant_status=None,
                                 context_tokens=None, processed_tokens=None, cost=None)
        result['release_ceiling'] = self.maximum_release_level
        return result

    def graph(self, query='', focus='', limit=60, *, node_state='', edge_state='', relation_type='', selected=''):
        self.application.service.clear_visibility_cache()
        def load():
            rows, skipped = {}, 0
            for name in ('concepts', 'relations'):
                rows[name] = []
                for path in sorted((self.root / name).glob('*.json')):
                    if path.is_symlink():
                        skipped += 1
                        continue
                    try:
                        item = json.loads(path.read_text())
                        required = ('concept_id', 'title') if name == 'concepts' else ('relation_id', 'source_id', 'target_id', 'relation_type')
                        if not isinstance(item, dict) or any(not isinstance(item.get(k), str) for k in required):
                            raise ValueError('Malformed graph record')
                        if not self.canonical_record_visible(name, item):
                            continue
                        # Validate through canonical models before the Epistemap projection.
                        from .models import ConceptRecord, RelationRecord
                        model = ConceptRecord if name == 'concepts' else RelationRecord
                        rows[name].append(model.model_validate(item).model_dump(mode='json'))
                    except (OSError, ValueError, TypeError):
                        skipped += 1
            bundle = graph_bundle_from_rows(rows['concepts'], rows['relations'])
            relation_assessments = {}
            for relation in rows['relations']:
                values = []
                for assessment in relation.get('assessments', [])[:20]:
                    if not isinstance(assessment, dict):
                        continue
                    value = assessment.get('value')
                    if not isinstance(value, (int, float)) or not 0 <= value <= 1:
                        continue
                    method = assessment.get('method') if isinstance(assessment.get('method'), dict) else {}
                    values.append({
                        'dimension': _public_text(str(assessment.get('dimension', 'unspecified')), limit=128),
                        'value': value,
                        'band': _public_text(str(assessment.get('band', '')), limit=64),
                        'method': _public_text(str(method.get('name', '')), limit=160),
                        'method_version': _public_text(str(method.get('version', '')), limit=64),
                        'rationale': _public_text(str(assessment.get('rationale', '')), limit=1000),
                        'recorded_at': _public_text(str(assessment.get('recorded_at', '')), limit=64),
                    })
                relation_assessments[str(relation.get('relation_id', ''))] = values
            return bundle, skipped, relation_assessments
        bundle, skipped, relation_assessments = self.cached('graph', load) if self.maximum_release_level == 'private' else load()
        all_nodes = bundle.node_index()
        node_states = sorted({node.status for node in all_nodes.values()})
        all_edge_states = sorted({edge.status for edge in bundle.edges
                                  if edge.source in all_nodes and edge.target in all_nodes})
        relation_types = sorted({edge.type for edge in bundle.edges
                                 if edge.source in all_nodes and edge.target in all_nodes})
        visible_nodes = {
            node_id: node for node_id, node in all_nodes.items()
            if not node_state or node.status == node_state
        }
        eligible_edges = [edge for edge in bundle.edges
                          if edge.source in visible_nodes and edge.target in visible_nodes
                          and (not edge_state or edge.status == edge_state)
                          and (not relation_type or edge.type == relation_type)]
        edge_filtered = bool(edge_state or relation_type)
        if focus:
            ids = {focus} if focus in visible_nodes else set()
            for edge in eligible_edges:
                if edge.source == focus: ids.add(edge.target)
                if edge.target == focus: ids.add(edge.source)
        elif edge_filtered and not query:
            # A relationship-state/type view is a relationship-first view:
            # include its endpoints before applying the node bound. Otherwise
            # the first alphabetical concepts can hide every matching edge.
            ids = {endpoint for edge in eligible_edges
                   for endpoint in (edge.source, edge.target)}
        else:
            text = query.casefold()
            ids = {n.id for n in visible_nodes.values() if text in (' '.join([n.title, n.description, *n.aliases])).casefold()}
        ordered = sorted(ids, key=lambda i: (i != focus, i != selected, visible_nodes[i].title.casefold(), i))
        matching_links = [edge for edge in eligible_edges if edge.source in ids and edge.target in ids]
        selected = set(ordered[:limit])
        candidate_links = [edge for edge in eligible_edges if edge.source in selected and edge.target in selected]
        links = candidate_links[:300]
        return dict(schema_version='groundrecall.dashboard.graph.v1', total_nodes=len(visible_nodes), total_edges=len(eligible_edges),
                    matching_nodes=len(ids), matching_edges=len(matching_links),
                    neighborhood_title=visible_nodes[focus].title if focus in visible_nodes else None,
                    node_states=node_states, edge_states=all_edge_states, relation_types=relation_types,
                    effective_filters=dict(node_state=node_state, edge_state=edge_state, relation_type=relation_type),
                    truncated=len(ids) > limit or len(matching_links) > len(links),
                    truncated_nodes=len(ids) > limit, truncated_edges=len(matching_links) > len(links),
                    release_ceiling=self.maximum_release_level,
                    skipped_records=skipped if self.maximum_release_level == 'private' else None,
                    nodes=[dict(id=visible_nodes[i].id, record_kind='concept', title=visible_nodes[i].title,
                                summary=visible_nodes[i].description[:4096], status=visible_nodes[i].status,
                                url='/records/' + quote('concept::' + visible_nodes[i].id, safe=''),
                                wiki_urls=['/records/' + quote('artifact::' + str(a), safe='') for a in visible_nodes[i].metadata.get('source_artifact_ids', [])[:20]])
                           for i in ordered[:limit]],
                    edges=[dict(id=e.id, record_kind='relation', source=e.source, target=e.target, type=e.type, status=e.status,
                                assessments=relation_assessments.get(e.id, []),
                                url='/records/' + quote('relation::' + e.id, safe='')) for e in links[:300]])

    def maintenance(self, *, offset=0, page_size=100, priority_band='', source_kind='', status='', triage_lane=''):
        if self.workspace is None:
            return dict(status='not_configured', message='Start with --workspace to include imports and source notes.',
                        items=[], release_ceiling=self.maximum_release_level)
        load_backlog = lambda: aggregate_backlog(
            self.workspace, store=self.root, limit=None,
            imports_root=self.layout.imports if self.layout else None,
            source_notes_root=self.layout.source_notes if self.layout else None,
            maximum_release_level=self.maximum_release_level,
        ).model_dump(mode='json')
        result = deepcopy(self.cached('maintenance', load_backlog) if self.maximum_release_level == 'private' else load_backlog())
        result['release_ceiling'] = self.maximum_release_level
        if self.maximum_release_level != 'private':
            # A visible review candidate must not disclose a target record that
            # falls above the same ceiling. Filter references at the target too.
            self.application.service.clear_visibility_cache()
            items = []
            for item in result.get('items', []):
                if item.get('source_kind') == 'canonical_review_candidate' and item.get('source_id') and not self.application.service._record_visible('review_candidate', item['source_id']):
                    continue
                if item.get('source_kind') == 'canonical_review_candidate' and item.get('candidate_kind') in {'claim', 'concept', 'relation'} and item.get('candidate_id') and not self.application.service._record_visible(item['candidate_kind'], item['candidate_id']):
                    continue
                if item.get('source_kind') == 'import_review' and not self._import_item_visible(item):
                    continue
                items.append(item)
            result['visible_total'] = len(items)
            result['urgent_count'] = sum(item.get('priority_band') == 'urgent' for item in items)
            result['oldest_visible_age_seconds'] = max((item.get('age_seconds', 0) for item in items), default=0)
            for field, item_field in (('counts_by_source_kind', 'source_kind'), ('counts_by_candidate_kind', 'candidate_kind'),
                                      ('counts_by_triage_lane', 'triage_lane'), ('counts_by_priority_band', 'priority_band')):
                counts = {}
                for item in items:
                    key = item.get(item_field, '')
                    counts[key] = counts.get(key, 0) + 1
                result[field] = counts
            result['required_action_counts'] = {}
            for item in items:
                for action in item.get('required_actions', []):
                    result['required_action_counts'][action] = result['required_action_counts'].get(action, 0) + 1
            result['items'] = items
            result['reminder_recommendation'] = 'emit' if items else 'suppress_empty'
            result['diagnostics'] = []
        else:
            result['items'] = result.get('items', [])
        all_items = result.get('items', [])
        if priority_band:
            all_items = [item for item in all_items if item.get('priority_band') == priority_band]
        if source_kind:
            all_items = [item for item in all_items if item.get('source_kind') == source_kind]
        if status:
            all_items = [item for item in all_items if item.get('authoritative_status') == status]
        if triage_lane:
            all_items = [item for item in all_items if item.get('triage_lane') == triage_lane]
        result['matching_total'] = len(all_items)
        result['filter_options'] = {
            'priority_bands': sorted({item.get('priority_band', '') for item in result.get('items', []) if item.get('priority_band')}),
            'source_kinds': sorted({item.get('source_kind', '') for item in result.get('items', []) if item.get('source_kind')}),
            'statuses': sorted({item.get('authoritative_status', '') for item in result.get('items', []) if item.get('authoritative_status')}),
            'triage_lanes': sorted({item.get('triage_lane', '') for item in result.get('items', []) if item.get('triage_lane')}),
        }
        start = max(0, int(offset))
        count = None if page_size is None else max(1, min(100, int(page_size)))
        if count is not None and start >= len(all_items):
            start = ((len(all_items) - 1) // count) * count if all_items else 0
        result['offset'] = start
        result['items'] = all_items[start:] if count is None else all_items[start:start + count]
        result['has_previous'] = start > 0
        result['has_next'] = start + len(result['items']) < len(all_items)
        return result

    def _import_item_visible(self, item):
        if not self.layout:
            return False
        import_name, _, queue_id = str(item.get('source_id', '')).partition(':')
        root = self.layout.imports.resolve()
        directory = self.layout.imports / import_name
        try:
            resolved = directory.resolve(strict=True)
            queue_path = resolved / 'review_queue.json'
            if directory.is_symlink() or not resolved.is_relative_to(root) or queue_path.is_symlink():
                return False
            queue = json.loads(queue_path.read_text(encoding='utf-8'))
            rows = queue.get('items', []) if isinstance(queue, dict) else []
            row = next((value for value in rows if isinstance(value, dict) and
                        str(value.get('queue_id', value.get('candidate_id', import_name))) == queue_id), None)
            if row is None:
                return False
            filename = {'claim': 'claims.jsonl', 'concept': 'concepts.jsonl',
                        'relation': 'relations.jsonl'}.get(str(row.get('candidate_type', '')))
            if not filename:
                return True
            path = resolved / filename
            if path.is_symlink() or not path.resolve(strict=True).is_relative_to(resolved):
                return False
            key = {'claim': 'claim_id', 'concept': 'concept_id', 'relation': 'relation_id'}[str(row['candidate_type'])]
            for line in path.read_text(encoding='utf-8').splitlines():
                try:
                    candidate = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(candidate, dict) and str(candidate.get(key, candidate.get('candidate_id', ''))) == str(row.get('candidate_id', '')):
                    release = self.application.service._record_release(candidate)
                    return release is not None and RELEASE_RANK[release] <= RELEASE_RANK[self.maximum_release_level]
            # Queue-level metadata remains authoritative when the import has no
            # candidate payload for this type/ID.
            return True
        except (OSError, ValueError, TypeError, KeyError):
            return False

    def maintenance_item(self, backlog_id):
        # Resolve the ID against the current, release-filtered inventory. This
        # makes missing, stale and excluded IDs indistinguishable to callers.
        digest = self.maintenance(page_size=None)
        item = next((row for row in digest.get('items', []) if row.get('backlog_id') == backlog_id), None)
        if item is None:
            return None
        detail = {'state': 'unavailable', 'candidate': None, 'evidence': []}
        kind, candidate_id = item.get('candidate_kind', ''), item.get('candidate_id', '')
        if item.get('source_kind') == 'source_note':
            response = self.application.service.read_record('source_note::' + candidate_id)
            if response:
                detail = {'state': 'available', 'candidate': response.record.model_dump(mode='json'), 'evidence': []}
        elif item.get('source_kind') == 'canonical_review_candidate':
            store = GroundRecallStore(self.root, create=False)
            review = store.get_review_candidate(item.get('source_id', ''))
            if review and self.application.service._record_visible('review_candidate', item.get('source_id', '')):
                response = self.application.service.read_record(f'{kind}::{candidate_id}') if kind in {'claim', 'concept', 'relation', 'observation', 'artifact'} else None
                detail = {'state': 'available' if response else 'target_unavailable',
                          'candidate': response.record.model_dump(mode='json') if response else None,
                          'review_metadata': review.model_dump(mode='json'),
                          'evidence': response.relationships if response else []}
        elif item.get('source_kind') == 'import_review' and self.layout:
            import_name, _, queue_id = str(item.get('source_id', '')).partition(':')
            import_root = self.layout.imports.resolve()
            import_dir = self.layout.imports / import_name
            try:
                resolved = import_dir.resolve(strict=True)
                if resolved.is_relative_to(import_root) and resolved.is_dir() and not import_dir.is_symlink():
                    queue_path = resolved / 'review_queue.json'
                    if queue_path.is_symlink() or not queue_path.resolve(strict=True).is_relative_to(resolved):
                        raise ValueError('Review queue escapes its configured import root')
                    payload = json.loads(queue_path.read_text(encoding='utf-8'))
                    rows = payload.get('items', []) if isinstance(payload, dict) else []
                    row = next((row for row in rows if isinstance(row, dict)
                                if str(row.get('queue_id', row.get('candidate_id', import_name))) == queue_id), None)
                    if row:
                        allowed = ('candidate_type', 'candidate_id', 'candidate_text', 'title', 'rationale',
                                   'finding_codes', 'evidence_ids', 'source_ids', 'status')
                        candidate_kind = str(row.get('candidate_type', ''))
                        candidate_file = {'claim': 'claims.jsonl', 'concept': 'concepts.jsonl',
                                          'relation': 'relations.jsonl'}.get(candidate_kind)
                        candidate_row = None
                        if candidate_file:
                            candidate_path = resolved / candidate_file
                            if candidate_path.is_symlink() or not candidate_path.resolve(strict=True).is_relative_to(resolved):
                                raise ValueError('Candidate file escapes its configured import root')
                            for candidate in (json.loads(line) for line in candidate_path.read_text(encoding='utf-8').splitlines() if line.strip()):
                                if isinstance(candidate, dict) and str(candidate.get('candidate_id', candidate.get(f'{candidate_kind}_id', ''))) == str(row.get('candidate_id', '')):
                                    candidate_row = candidate
                                    break
                        source_candidate = candidate_row or row
                        release = self.application.service._record_release(source_candidate)
                        if release is not None and RELEASE_RANK[release] <= RELEASE_RANK[self.maximum_release_level]:
                            fields = ('candidate_id', 'title', 'description', 'claim_text', 'relation_type',
                                      'source_id', 'target_id', 'rationale', 'finding_codes', 'evidence_ids',
                                      'source_observation_ids', 'supporting_fragment_ids')
                            evidence_ids = list(source_candidate.get('evidence_ids', [])) + list(source_candidate.get('source_observation_ids', [])) + list(source_candidate.get('supporting_fragment_ids', []))
                            evidence = []
                            for filename, id_field, kind_name, text_field in (
                                ('observations.jsonl', 'observation_id', 'observation', 'text'),
                                ('fragments.jsonl', 'fragment_id', 'fragment', 'text'),
                            ):
                                evidence_path = resolved / filename
                                if not evidence_path.is_file() or evidence_path.is_symlink():
                                    continue
                                for line in evidence_path.read_text(encoding='utf-8').splitlines():
                                    try:
                                        record = json.loads(line)
                                    except json.JSONDecodeError:
                                        continue
                                    if not isinstance(record, dict) or str(record.get(id_field, '')) not in evidence_ids:
                                        continue
                                    record_release = self.application.service._record_release(record)
                                    if record_release is None or RELEASE_RANK[record_release] > RELEASE_RANK[self.maximum_release_level]:
                                        continue
                                    evidence.append({'kind': kind_name, 'id': str(record.get(id_field)),
                                                     'title': str(record.get('section', record.get('title', 'Evidence'))),
                                                     'excerpt': str(record.get(text_field, ''))[:2000]})
                                    if len(evidence) >= 12:
                                        break
                            detail = {'state': 'available', 'candidate': {key: source_candidate[key] for key in fields if key in source_candidate},
                                      'review_metadata': {key: row[key] for key in ('finding_codes', 'rationale', 'status') if key in row},
                                      'evidence': evidence}
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
        self.application.service.clear_visibility_cache()
        payload = dict(item=item, detail=detail, release_ceiling=self.maximum_release_level)
        return payload if self.payload_visible(payload) else None

    def route(self, path):
        parsed = urlsplit(path)
        query = parse_qs(parsed.query)
        for prefix in ('/records/', '/api/v1/records/'):
            if parsed.path.startswith(prefix):
                from urllib.parse import unquote
                stable_id = unquote(parsed.path[len(prefix):])
                if any(c in stable_id for c in ('/', '\\', '\x00')) or '..' in stable_id:
                    return 400, 'application/json', b'{"error":"invalid_record_id"}'
        if parsed.path in ('/', '/graph', '/maintenance') or parsed.path.startswith('/maintenance/item/'):
            return 200, 'text/html; charset=utf-8', HTML.encode()
        if parsed.path == '/assets/dashboard.css':
            return 200, 'text/css', CSS.encode()
        if parsed.path == '/assets/dashboard.js':
            return 200, 'text/javascript', JS.encode()
        if parsed.path == '/api/dashboard/overview':
            data = self.overview()
        elif parsed.path == '/api/dashboard/graph':
            q, focus = query.get('q', [''])[0], query.get('focus', [''])[0]
            selected = query.get('selected', [''])[0]
            node_state, edge_state = query.get('node_state', [''])[0], query.get('edge_state', [''])[0]
            relation_type = query.get('relation_type', [''])[0]
            if any(len(value) > 512 for value in (q, focus, selected)) or any(
                len(value) > 128 for value in (node_state, edge_state, relation_type)
            ):
                return 400, 'application/json', b'{"error":"invalid_request"}'
            data = self.graph(q, focus, node_state=node_state, edge_state=edge_state,
                              relation_type=relation_type, selected=selected)
        elif parsed.path == '/api/dashboard/maintenance':
            params = {key: query.get(key, [''])[0] for key in ('priority_band', 'source_kind', 'status', 'triage_lane')}
            try:
                offset = int(query.get('offset', ['0'])[0])
            except ValueError:
                return 400, 'application/json', b'{"error":"invalid_request"}'
            if offset < 0 or offset > 10_000_000 or any(len(value) > 128 for value in params.values()):
                return 400, 'application/json', b'{"error":"invalid_request"}'
            data = self.maintenance(offset=offset, **params)
        elif parsed.path.startswith('/api/dashboard/maintenance/'):
            from urllib.parse import unquote
            backlog_id = unquote(parsed.path[len('/api/dashboard/maintenance/'):])
            if not backlog_id or any(char in backlog_id for char in ('/', '\\', '\x00')):
                return 404, 'application/json', b'{"error":"not_found"}'
            data = self.maintenance_item(backlog_id)
            if data is None:
                return 404, 'application/json', b'{"error":"not_found"}'
        else:
            start = perf_counter()
            if parsed.path.startswith('/api/v1/'):
                status, body = self.application.dispatch('GET', path)
                try:
                    if body and not self.payload_visible(json.loads(body)):
                        return 502, 'application/json', b'{"error":"response_release_ceiling_violation"}'
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return 502, 'application/json', b'{"error":"response_unavailable"}'
                return status, 'application/json', body
            # The existing search service can create a missing index. Do not let
            # browsing a dashboard trigger that maintenance operation.
            if parsed.path == '/search' and query.get('q') and not (self.root / '.index' / 'groundrecall-search.sqlite').is_file():
                return 503, 'text/html', b'<h1>Search index unavailable</h1><p>Build the index with the GroundRecall CLI, then retry.</p>'
            try:
                status, body = self.application.dispatch_html('GET', path)
            except (FileNotFoundError, sqlite3.OperationalError):
                return 503, 'text/html', b'<h1>Search index unavailable</h1><p>Check the index with the GroundRecall CLI, then retry.</p>'
            if parsed.path == '/search' and query.get('q') and status == 200:
                with self.lock:
                    self.search_times.append((perf_counter() - start) * 1000)
            if status == 200:
                body = body.replace(b'</head>', b'<link rel="stylesheet" href="/assets/dashboard.css"></head>')
                ceiling = self.maximum_release_level.encode('ascii')
                nav = b'<nav aria-label="Workspace"><a href="/">Overview</a><a href="/graph">Knowledge graph</a><a href="/maintenance">Maintenance</a><a href="/search">Search</a></nav>'
                notice = b'<p class="view-ceiling">Showing records with release level up to <strong>' + ceiling + b'</strong>.</p>'
                body = body.replace(b'</header>', nav + notice + b'</header>')
            return status, 'text/html; charset=utf-8', body
        if not self.payload_visible(data):
            return 502, 'application/json', b'{"error":"response_release_ceiling_violation"}'
        if self.maximum_release_level != 'private' and isinstance(data, dict) and 'items' in data:
            # Backlog health and filtered-count summaries are operational detail
            # without per-field release metadata; omit them for capped views.
            data.pop('maintenance_health', None)
            data.pop('redaction_summary', None)
        return 200, 'application/json', json.dumps(data, ensure_ascii=False).encode()


def make_server(service: DashboardService, port=0, *, token=None):
    """Bind only IPv4 loopback. A per-process secret bootstraps an HttpOnly cookie."""
    token = token or secrets.token_urlsafe(32)
    session = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log queries, record IDs, or bootstrap credentials.

        def send(self, status, mime, body, cookie=None, allow=None):
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if allow: self.send_header('Allow', allow)
            if cookie: self.send_header('Set-Cookie', cookie)
            self.end_headers()
            self.wfile.write(body)

        def trusted(self):
            expected = f'127.0.0.1:{self.server.server_port}'
            return (self.headers.get('Host') == expected and
                    self.headers.get('Origin', 'http://' + expected) == 'http://' + expected and
                    self.headers.get('Sec-Fetch-Site') not in ('cross-site',))

        def authenticated(self):
            cookies = SimpleCookie()
            try: cookies.load(self.headers.get('Cookie', ''))
            except Exception: return False
            cookie = cookies.get(f'gr_dashboard_{self.server.server_port}')
            return bool(cookie and secrets.compare_digest(cookie.value, session))

        def reject_unsupported(self):
            if not self.trusted():
                self.send(403, 'text/plain', b'Forbidden')
            elif not self.authenticated():
                self.send(401, 'application/json', b'{"error":"authentication_required"}')
            else:
                self.send(405, 'text/plain', b'' if self.command == 'HEAD' else b'Read-only dashboard', allow='GET')

        def send_error(self, code, message=None, explain=None):
            # BaseHTTPRequestHandler otherwise emits an unguarded HTML 501 for
            # unknown verbs, bypassing the dashboard's Host/auth/CSP policy.
            if code == 501:
                self.reject_unsupported()
                return
            return super().send_error(code, message, explain)

        def do_GET(self):
            if not self.trusted():
                self.send(403, 'text/plain', b'Forbidden')
                return
            if not self.authenticated():
                if urlsplit(self.path).path == '/assets/login.js':
                    self.send(200, 'text/javascript', LOGIN.encode())
                elif urlsplit(self.path).path == '/':
                    self.send(200, 'text/html', b'<!doctype html><html lang="en"><meta charset="utf-8"><title>Open GroundRecall</title><h1>GroundRecall local dashboard</h1><p id="status">Open the access link printed by the dashboard command.</p><script src="/assets/login.js"></script></html>')
                else: self.send(401, 'application/json', b'{"error":"authentication_required"}')
                return
            try:
                status, mime, body = service.route(self.path)
                if len(body) > 1_000_000:
                    status, mime, body = 502, 'application/json', b'{"error":"response_too_large"}'
                self.send(status, mime, body)
            except Exception:
                self.send(503, 'application/json', b'{"error":"data_unavailable"}')

        def do_POST(self):
            if not self.trusted():
                self.send(403, 'text/plain', b'Forbidden')
                return
            if self.path != '/login':
                self.reject_unsupported()
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 256: raise ValueError()
                self.connection.settimeout(5)
                supplied = self.rfile.read(length).decode('ascii')
            except (ValueError, OSError):
                self.send(400, 'text/plain', b'Invalid request')
                return
            if not secrets.compare_digest(supplied, token):
                self.send(401, 'text/plain', b'Invalid access link')
                return
            self.send(200, 'text/plain', b'OK', cookie=f'gr_dashboard_{self.server.server_port}={session}; HttpOnly; SameSite=Strict; Path=/')

        def do_PUT(self): self.reject_unsupported()
        def do_PATCH(self): self.reject_unsupported()
        def do_DELETE(self): self.reject_unsupported()
        def do_OPTIONS(self): self.reject_unsupported()
        def do_HEAD(self): self.reject_unsupported()
        def do_TRACE(self): self.reject_unsupported()
        def do_CONNECT(self): self.reject_unsupported()

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    return server, token


def main():
    parser = argparse.ArgumentParser(description='Run the authenticated, owner-local GroundRecall dashboard')
    parser.add_argument('store_dir')
    parser.add_argument('--workspace', help='Workspace root for imports, source notes and review backlog')
    parser.add_argument('--port', type=int, default=18767)
    parser.add_argument('--maximum-release-level', choices=tuple(RELEASE_RANK), default='private',
                        help='Highest record release level visible in this local dashboard (default: private)')
    args = parser.parse_args()
    service = DashboardService(args.store_dir, args.workspace, args.maximum_release_level)
    server, token = make_server(service, args.port)
    print(f'Open http://127.0.0.1:{server.server_port}/#access={token}', flush=True)
    print('Local owner access only. Ctrl-C stops the dashboard and invalidates its access link.', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__ == '__main__':
    main()
