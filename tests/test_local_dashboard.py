from __future__ import annotations

import hashlib
import http.client
import json
from threading import Thread

import pytest

from groundrecall.local_dashboard import DashboardService, make_server
from groundrecall.application_contract import SearchRequest
from groundrecall.models import ClaimRecord, ConceptRecord, ConfidenceAssessment, RelationRecord, ReviewCandidateRecord, SourceRecord
from groundrecall.store import GroundRecallStore


def fixture_store(tmp_path):
    root = tmp_path / 'store'
    store = GroundRecallStore(root)
    for key, title in [('a', 'Alpha <script>alert(1)</script>'), ('b', 'Beta'), ('c', 'Isolated')]:
        store.save_concept(ConceptRecord(concept_id=key, title=title, description='Summary for ' + key))
    store.save_relation(RelationRecord(relation_id='ab', source_id='a', target_id='b', relation_type='supports'))
    store.save_review_candidate(ReviewCandidateRecord(review_candidate_id='review-a', candidate_type='concept', candidate_id='a'))
    return DashboardService(root, tmp_path)


def fingerprints(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


def test_read_projections_do_not_mutate_store_and_unknown_is_not_zero(tmp_path):
    service = fixture_store(tmp_path)
    before = fingerprints(tmp_path)
    overview = service.overview()
    assert overview['counts']['concepts'] == 3
    assert overview['runtime']['open_sessions'] is None
    assert overview['retrieval']['median_ms'] is None
    assert overview['index_present'] is False
    graph = service.graph(focus='a')
    assert {n['id'] for n in graph['nodes']} == {'a', 'b'}
    assert graph['edges'][0]['type'] == 'supports'
    assert graph['nodes'][0]['summary'] == 'Summary for a'
    assert service.graph('Isolated')['nodes'][0]['id'] == 'c'
    assert service.graph(focus='missing')['nodes'] == []
    backlog = service.maintenance()
    assert backlog['visible_total'] == 1
    assert backlog['items'][0]['candidate_id'] == 'a'
    assert service.route('/search?q=Alpha')[0] == 503
    assert service.route('/records/concept%3A%3Aa')[0] == 200
    assert fingerprints(tmp_path) == before


def test_private_overview_uses_fast_file_metadata_inventory(tmp_path, monkeypatch):
    service = fixture_store(tmp_path)
    malformed = service.root / 'concepts' / 'malformed.json'
    malformed.write_text('{not valid JSON')

    def should_not_parse_record_rows(*_args, **_kwargs):
        raise AssertionError('private overview should not parse or recheck every JSON record')

    monkeypatch.setattr(service, 'canonical_record_visible', should_not_parse_record_rows)
    overview = service.overview()
    assert overview['counts']['concepts'] == 4
    assert overview['inventory_validation'] == 'file_metadata_only'
    assert overview['record_bytes'] > 0


def test_maintenance_inspection_is_bounded_read_only_and_hides_missing_ids(tmp_path):
    service = fixture_store(tmp_path)
    before = fingerprints(tmp_path)
    page = service.maintenance(offset=0, page_size=1)
    assert page['matching_total'] == 1
    assert len(page['items']) == 1
    opened = service.maintenance_item(page['items'][0]['backlog_id'])
    assert opened and opened['detail']['state'] == 'available'
    assert opened['detail']['candidate']['stable_id'] == 'concept::a'
    assert service.maintenance_item('not-a-current-item') is None
    assert fingerprints(tmp_path) == before


def test_maintenance_filters_apply_before_pagination(tmp_path):
    root = tmp_path / 'store'
    store = GroundRecallStore(root)
    store.save_concept(ConceptRecord(concept_id='target', title='Target'))
    for index in range(3):
        store.save_review_candidate(ReviewCandidateRecord(
            review_candidate_id=f'review-{index}', candidate_type='concept', candidate_id='target',
            current_status='draft' if index < 2 else 'triaged', priority=90 if index == 2 else 10,
        ))
    service = DashboardService(root, tmp_path)
    result = service.maintenance(status='triaged', offset=0, page_size=1)
    assert result['matching_total'] == 1
    assert len(result['items']) == 1
    assert result['items'][0]['authoritative_status'] == 'triaged'
    assert result['filter_options']['statuses'] == ['draft', 'triaged']
    assert service.maintenance(status='triaged', offset=900)['offset'] == 0
    backlog_id = result['items'][0]['backlog_id']
    assert service.route('/maintenance/item/' + backlog_id)[0] == 200
    assert service.route('/api/dashboard/maintenance/' + backlog_id)[0] == 200
    assert service.route('/api/dashboard/maintenance/not-current')[0] == 404


def test_import_review_opens_bounded_candidate_and_evidence_preview(tmp_path):
    from groundrecall.workspace import workspace_manifest_payload
    root = tmp_path / 'store'
    store = GroundRecallStore(root)
    store.save_concept(ConceptRecord(concept_id='linked', title='Linked concept'))
    imports = tmp_path / 'imports' / 'import-one'
    imports.mkdir(parents=True)
    (tmp_path / 'workspace.json').write_text(json.dumps(workspace_manifest_payload(workspace_id='test')))
    (imports / 'manifest.json').write_text(json.dumps({'import_id': 'import-one', 'release_level': 'public'}))
    (imports / 'review_queue.json').write_text(json.dumps({'items': [
        {'queue_id': 'queue-one', 'candidate_type': 'claim', 'candidate_id': 'claim-one',
         'candidate_text': 'A candidate claim', 'evidence_ids': ['observation-one'],
         'status': 'needs_review', 'release_level': 'public', 'finding_codes': ['claim_ungrounded']},
        {'queue_id': 'queue-private', 'candidate_type': 'claim', 'candidate_id': 'claim-private',
         'status': 'needs_review', 'release_level': 'public'},
    ]}))
    (imports / 'claims.jsonl').write_text(json.dumps({
        'claim_id': 'claim-one', 'claim_text': 'Candidate claim text', 'source_observation_ids': ['observation-one'],
        'release_level': 'public',
    }) + '\n' + json.dumps({
        'candidate_id': 'claim-private', 'claim_text': 'Private claim text', 'release_level': 'private',
    }) + '\n')
    (imports / 'observations.jsonl').write_text(json.dumps({
        'observation_id': 'observation-one', 'role': 'quote', 'text': 'The source passage supports the claim.',
        'release_level': 'public',
    }) + '\n')
    service = DashboardService(root, tmp_path, maximum_release_level='public')
    item = next(row for row in service.maintenance()['items'] if row['source_kind'] == 'import_review')
    assert service.maintenance()['visible_total'] == 1

    opened = service.maintenance_item(item['backlog_id'])

    assert opened['detail']['state'] == 'available'
    assert opened['detail']['candidate']['claim_text'] == 'Candidate claim text'
    assert opened['detail']['evidence'][0]['excerpt'] == 'The source passage supports the claim.'


def test_dashboard_ask_cards_match_read_only_cli_parsers():
    from groundrecall.application_cli import build_parser as search_parser
    from groundrecall.cli import COMMANDS
    from groundrecall.confidence import build_readiness_parser
    from groundrecall.review_backlog import build_parser as queue_parser
    from groundrecall.dashboard_assets import JS

    assert {'application-search', 'review-status', 'confidence-readiness'} <= set(COMMANDS)
    assert search_parser().parse_args(['/store', 'example query']).query == 'example query'
    assert queue_parser().parse_args(['/workspace', '--format', 'text', '--limit', '20']).limit == 20
    assert build_readiness_parser().parse_args(['/store']).store == '/store'
    assert 'groundrecall application-search <store-dir>' in JS
    assert 'groundrecall review-status <workspace>' in JS
    assert 'groundrecall confidence-readiness <store-dir>' in JS
    assert 'What’s new' in JS and 'does not execute commands' in JS
    assert 'May build a missing search index' in JS and 'Effect' in JS


def test_graph_is_bounded_and_malformed_records_are_visible(tmp_path):
    service = fixture_store(tmp_path)
    (service.root / 'concepts' / 'bad.json').write_text('{bad')
    graph = service.graph(limit=1)
    assert len(graph['nodes']) == 1 and graph['truncated']
    assert graph['skipped_records'] == 1
    assert service.maintenance()['items']


def test_workspace_manifest_mismatch_fails(tmp_path):
    service = fixture_store(tmp_path)
    (tmp_path / 'workspace.json').write_text(json.dumps(dict(
        schema_version='groundrecall.workspace.v1', workspace_id='test', canonical_store='other',
        imports='imports', source_notes='notes', private_runs='runs',
        indexes=dict(notes='.index/n', canonical='.index/c', unified='.index/u'))))
    with pytest.raises(ValueError, match='disagree'):
        DashboardService(service.root, tmp_path)


def test_existing_index_search_records_latency_without_canonical_changes(tmp_path):
    from html.parser import HTMLParser
    from urllib.parse import urlencode
    from groundrecall.search_index import build_search_index
    service = fixture_store(tmp_path)
    build_search_index(service.root)
    before = fingerprints(tmp_path)
    class SearchForm(HTMLParser):
        action = None

        def handle_starttag(self, tag, attrs):
            if tag == 'form':
                self.action = dict(attrs).get('action')

    form = SearchForm()
    form.feed(service.route('/search')[2].decode())
    assert form.action == '/search'
    status, _, body = service.route(form.action + '?' + urlencode({'q': 'Alpha'}))
    assert status == 200 and b'Alpha' in body
    metrics = service.overview()['retrieval']
    assert metrics['samples'] == 1 and metrics['median_ms'] >= 0
    assert fingerprints(tmp_path) == before
    record = service.route('/records/concept%3A%3Aa')[2]
    assert b'href="/search">Search</a>' in record


def test_workspace_custom_source_roots_are_used(tmp_path):
    service = fixture_store(tmp_path)
    notes = tmp_path / 'custom-notes'
    notes.mkdir()
    (notes / 'pending.md').write_text('Pending source note')
    (tmp_path / 'workspace.json').write_text(json.dumps(dict(
        schema_version='groundrecall.workspace.v1', workspace_id='test', canonical_store='store',
        imports='custom-imports', source_notes='custom-notes', private_runs='runs',
        indexes=dict(notes='.index/n', canonical='.index/c', unified='.index/u'))))
    service = DashboardService(service.root, tmp_path)
    assert service.maintenance()['visible_total'] == 2


@pytest.mark.parametrize('phase', ['before_dispatch', 'before_sqlite_open'])
def test_index_removed_during_search_is_not_recreated(tmp_path, monkeypatch, phase):
    import sqlite3
    from groundrecall.search_index import build_search_index
    service = fixture_store(tmp_path)
    build_search_index(service.root)
    index = service.root / '.index' / 'groundrecall-search.sqlite'
    if phase == 'before_dispatch':
        original = service.application.dispatch_html

        def dispatch(*args):
            index.unlink()
            return original(*args)

        monkeypatch.setattr(service.application, 'dispatch_html', dispatch)
    else:
        original = sqlite3.connect

        def connect(*args, **kwargs):
            index.unlink()
            return original(*args, **kwargs)

        monkeypatch.setattr(sqlite3, 'connect', connect)
    assert service.route('/search?q=Alpha')[0] == 503
    assert not index.exists()


@pytest.mark.parametrize('prefix', ['/records/', '/api/v1/records/'])
@pytest.mark.parametrize('record', ['concept%3A%3A..%2Fsecret', 'concept%3A%3A%2Fetc%2Fpasswd', 'concept%3A%3A%00', 'concept%3A%3A..%5Csecret'])
def test_record_traversal_rejected(tmp_path, prefix, record):
    assert fixture_store(tmp_path).route(prefix + record)[0] == 400


def test_http_auth_origin_guards_and_no_mutations(tmp_path):
    service = fixture_store(tmp_path)
    server, token = make_server(service)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def request(method, path, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result
    try:
        assert server.server_address[0] == '127.0.0.1'
        assert request('GET', '/api/dashboard/overview')[0] == 401
        assert request('POST', '/login', token, {'Origin': 'https://evil.example'})[0] == 403
        assert request('GET', '/', headers={'Host': 'evil.example'})[0] == 403
        assert request('POST', '/login', 'wrong')[0] == 401
        status, headers, _ = request('POST', '/login', token)
        assert status == 200
        cookie = headers['Set-Cookie'].split(';')[0]
        assert cookie.startswith(f'gr_dashboard_{server.server_port}=')
        assert 'HttpOnly' in headers['Set-Cookie'] and 'SameSite=Strict' in headers['Set-Cookie']
        auth = {'Cookie': cookie}
        status, headers, body = request('GET', '/api/dashboard/overview', headers=auth)
        assert status == 200 and json.loads(body)['counts']['concepts'] == 3
        assert headers['Cache-Control'] == 'no-store'
        assert "frame-ancestors 'none'" in headers['Content-Security-Policy']
        assert request('POST', '/api/dashboard/promote', '{}', auth)[0] == 405
        assert request('GET', '/graph', headers=auth)[0] == 200
        status, _, body = request('GET', '/records/concept%3A%3Aa', headers=auth)
        assert status == 200 and b'&lt;script&gt;' in body and b'<script>' not in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize('method', ['PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD', 'TRACE', 'BREW'])
def test_unsupported_methods_use_guarded_405_responses(tmp_path, method):
    service = fixture_store(tmp_path)
    server, token = make_server(service)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def request(verb, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        conn.request(verb, '/api/dashboard/overview', headers=headers or {})
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result
    try:
        status, headers, _ = request(method)
        assert status == 401
        assert 'Content-Security-Policy' in headers
        login = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        login.request('POST', '/login', body=token, headers={'Content-Length': str(len(token))})
        login_response = login.getresponse()
        cookie = login_response.getheader('Set-Cookie').split(';', 1)[0]
        login_response.read()
        login.close()
        status, headers, _ = request(method, {'Cookie': cookie})
        assert status == 405
        assert headers['Allow'] == 'GET'
        assert "frame-ancestors 'none'" in headers['Content-Security-Policy']
        assert request(method, {'Host': 'attacker.example'})[0] == 403
        assert request(method, {'Origin': 'https://attacker.example'})[0] == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_release_ceiling_filters_reads_associations_graph_counts_and_backlog_payload(tmp_path):
    from groundrecall.search_index import build_search_index

    workspace = tmp_path
    root = workspace / 'store'
    store = GroundRecallStore(root)
    store.save_concept(ConceptRecord(
        concept_id='public-concept', title='Public concept', description='Public description',
        release_level='public',
    ))
    store.save_concept(ConceptRecord(
        concept_id='private-concept', title='Private concept', description='SECRET private node',
    ))
    store.save_claim(ClaimRecord(
        claim_id='private-claim', claim_text='SECRET private claim text', concept_ids=['public-concept'],
    ))
    store.save_relation(RelationRecord(
        relation_id='public-edge-to-private', source_id='public-concept', target_id='private-concept',
        relation_type='SECRET relation', release_level='public',
    ))
    state = root / '.maintenance'
    state.mkdir()
    (state / 'graph_maintenance_state__private.json').write_text(json.dumps({
        'profile': 'SECRET_PROFILE', 'updated_at': 'now', 'run_count': 1,
        'last_run': {'result': 'SECRET_PRIVATE_RUN'},
    }))
    (root / 'review_candidates' / 'private.json').write_text(json.dumps({
        'review_candidate_id': 'private-review', 'candidate_type': 'claim',
        'candidate_id': 'private-claim', 'current_status': 'draft', 'release_level': 'public',
    }))
    build_search_index(root)

    service = DashboardService(root, workspace, maximum_release_level='public')
    overview = service.overview()
    assert overview['counts']['concepts'] == 1
    assert overview['index_present'] is None
    assert overview['unreadable_files'] is None
    graph = service.graph()
    assert [node['id'] for node in graph['nodes']] == ['public-concept']
    assert graph['edges'] == []
    assert graph['skipped_records'] is None
    assert service.route('/search?q=SECRET')[0] == 200
    search_body = service.route('/search?q=SECRET')[2]
    assert b'No records matched in this view.' in search_body
    assert b'up to <strong>public</strong>' in search_body
    assert b'SECRET private claim text' not in search_body
    assert b'SECRET private node' not in search_body
    assert b'SECRET relation' not in search_body

    status, body = service.application.dispatch('GET', '/api/v1/records/concept%3A%3Apublic-concept')
    assert status == 200
    assert b'SECRET' not in body
    assert service.application.dispatch('GET', '/api/v1/records/concept%3A%3Aprivate-concept')[0] == 404

    status, _, body = service.route('/api/dashboard/maintenance')
    assert status == 200
    assert b'SECRET' not in body
    assert b'redaction_summary' not in body
    assert b'maintenance_health' not in body
    assert b'private-review' not in body
    assert b'private-claim' not in body


def test_capped_search_uses_current_canonical_text_when_index_is_stale(tmp_path):
    from groundrecall.search_index import build_search_index

    root = tmp_path / 'store'
    store = GroundRecallStore(root)
    store.save_concept(ConceptRecord(
        concept_id='reclassified', title='OLD_PRIVATE_SECRET', description='Previously private',
    ))
    build_search_index(root)
    store.save_concept(ConceptRecord(
        concept_id='reclassified', title='Current public title', description='Current public summary',
        release_level='public',
    ))

    service = DashboardService(root, maximum_release_level='public')
    response = service.application.service.search(SearchRequest(query='OLD_PRIVATE_SECRET'))
    assert response.results == []
    build_search_index(root)
    current = service.application.service.search(SearchRequest(query='Current public'))
    assert len(current.results) == 1
    assert current.results[0].title == 'Current public title'


def test_release_ceiling_dependency_cycles_do_not_cache_partial_visibility(tmp_path):
    from groundrecall.search_index import build_search_index

    root = tmp_path / 'store'
    store = GroundRecallStore(root)
    store.save_source(SourceRecord(
        source_id='a', title='Shared source A', source_release_level='public',
        derivative_source_ids=['b', 'c'],
    ))
    store.save_source(SourceRecord(
        source_id='b', title='Shared source B', source_release_level='public',
        derivative_source_ids=['a'],
    ))
    store.save_source(SourceRecord(source_id='c', title='Hidden private source'))
    build_search_index(root)

    service = DashboardService(root, maximum_release_level='public')
    assert service.application.service._record_visible('source', 'a') is False
    assert service.application.service._record_visible('source', 'b') is False
    assert service.overview()['counts']['sources'] == 0
    assert service.application.service.search(SearchRequest(query='Shared')).results == []


def test_release_ceiling_fails_closed_for_missing_or_malformed_metadata(tmp_path):
    from groundrecall.search_index import build_search_index

    root = tmp_path / 'store'
    store = GroundRecallStore(root)
    store.save_concept(ConceptRecord(concept_id='good', title='Explicit public record', release_level='public'))
    (root / 'concepts' / 'missing.json').write_text(json.dumps({
        'concept_id': 'missing', 'title': 'LEGACY_UNLABELLED_NEEDLE',
    }))
    service = DashboardService(root, maximum_release_level='public')
    build_search_index(root)
    (root / 'concepts' / 'malformed.json').write_text(json.dumps({
        'concept_id': 'malformed', 'title': 'Malformed release metadata', 'release_level': 'worldwide',
    }))
    assert service.overview()['counts']['concepts'] == 1
    assert service.application.dispatch('GET', '/api/v1/records/concept%3A%3Amissing')[0] == 404
    assert service.application.dispatch('GET', '/api/v1/records/concept%3A%3Amalformed')[0] == 404
    assert service.application.service.search(SearchRequest(query='LEGACY_UNLABELLED_NEEDLE')).results == []


def test_capped_overview_and_graph_recheck_reclassified_records(tmp_path):
    root = tmp_path / 'store'
    store = GroundRecallStore(root)
    store.save_concept(ConceptRecord(concept_id='visible', title='Public concept', release_level='public'))
    service = DashboardService(root, maximum_release_level='public')
    assert service.overview()['counts']['concepts'] == 1
    assert len(service.graph()['nodes']) == 1

    store.save_concept(ConceptRecord(concept_id='visible', title='Private concept', release_level='private'))
    assert service.overview()['counts']['concepts'] == 0
    assert service.graph()['nodes'] == []


def test_search_revalidates_indexed_source_notes_against_current_files(tmp_path):
    from groundrecall.search_index import build_search_index

    root = tmp_path / 'store'
    GroundRecallStore(root)
    notes = tmp_path / 'source-notes'
    notes.mkdir()
    note = notes / 'note.md'
    note.write_text('# Current note title\nUNIQUE_NOTE_NEEDLE current content\n')
    build_search_index(root)
    service = DashboardService(root)
    found = service.application.service.search(SearchRequest(query='UNIQUE_NOTE_NEEDLE'))
    assert len(found.results) == 1
    assert found.results[0].title == 'Current note title'
    assert service.application.dispatch('GET', '/api/v1/records/source_note%3A%3Anote')[0] == 200

    note.unlink()
    missing = service.application.service.search(SearchRequest(query='UNIQUE_NOTE_NEEDLE'))
    assert missing.results == []
    assert service.application.dispatch('GET', '/api/v1/records/source_note%3A%3Anote')[0] == 404


def test_graph_filters_are_release_safe_and_apply_before_bounded_expansion(tmp_path):
    root = tmp_path / 'store'
    store = GroundRecallStore(root)
    store.save_concept(ConceptRecord(
        concept_id='alpha', title='Alpha', current_status='promoted', release_level='public',
    ))
    store.save_concept(ConceptRecord(
        concept_id='beta', title='Beta', current_status='draft', release_level='public',
    ))
    store.save_concept(ConceptRecord(concept_id='hidden', title='Hidden', release_level='private'))
    store.save_relation(RelationRecord(
        relation_id='visible-edge', source_id='alpha', target_id='beta', relation_type='supports',
        current_status='rejected', release_level='public',
        assessments=[
            ConfidenceAssessment(assessment_id='confidence-a', subject_id='visible-edge', dimension='reviewer_endorsement',
                value=0.72, band='high', method={'name': 'reviewer', 'version': '1'}, recorded_at='2026-10-01T00:00:00Z'),
            ConfidenceAssessment(assessment_id='reliability-a', subject_id='visible-edge', dimension='source_reliability',
                value=0.41, band='moderate', method={'name': 'source profile', 'version': '2'}, recorded_at='2026-10-02T00:00:00Z'),
        ],
    ))
    store.save_relation(RelationRecord(
        relation_id='hidden-edge', source_id='alpha', target_id='hidden', relation_type='secret-link',
        current_status='promoted', release_level='public',
    ))
    service = DashboardService(root, maximum_release_level='public')

    complete = service.graph()
    assert {node['id'] for node in complete['nodes']} == {'alpha', 'beta'}
    assert [edge['id'] for edge in complete['edges']] == ['visible-edge']
    assert [(item['dimension'], item['value']) for item in complete['edges'][0]['assessments']] == [
        ('reviewer_endorsement', 0.72), ('source_reliability', 0.41),
    ]
    assert complete['relation_types'] == ['supports']
    assert complete['edge_states'] == ['rejected']

    node_filter = service.graph(limit=1, node_state='promoted')
    assert [node['id'] for node in node_filter['nodes']] == ['alpha']
    assert node_filter['truncated_nodes'] is False
    filtered_out = service.graph(focus='alpha', edge_state='promoted')
    assert [node['id'] for node in filtered_out['nodes']] == ['alpha']
    assert filtered_out['edges'] == []
    filtered_focus = service.graph(focus='alpha', edge_state='rejected', relation_type='supports')
    assert {node['id'] for node in filtered_focus['nodes']} == {'alpha', 'beta'}
    assert [edge['id'] for edge in filtered_focus['edges']] == ['visible-edge']

    status, _, body = service.route('/api/dashboard/graph?edge_state=rejected&relation_type=supports')
    assert status == 200
    assert b'secret-link' not in body and b'hidden' not in body
    js = service.route('/assets/dashboard.js')[2]
    assert b'popstate' in js and b'pushState' in js and b'data-focus' in js
    assert b'Confidence and reliability' in js and b'Reliability' in js


def test_relationship_filter_prioritizes_endpoints_over_alphabetical_node_bound(tmp_path):
    root = tmp_path / 'store'
    store = GroundRecallStore(root)
    for index in range(70):
        store.save_concept(ConceptRecord(concept_id=f'a{index:02}', title=f'Alpha {index:02}'))
    store.save_concept(ConceptRecord(concept_id='z-source', title='Zulu source'))
    store.save_concept(ConceptRecord(concept_id='z-target', title='Zulu target'))
    store.save_relation(RelationRecord(
        relation_id='rare-edge', source_id='z-source', target_id='z-target', relation_type='rare-type',
    ))
    service = DashboardService(root)

    graph = service.graph(limit=60, relation_type='rare-type')

    assert {node['id'] for node in graph['nodes']} == {'z-source', 'z-target'}
    assert [edge['id'] for edge in graph['edges']] == ['rare-edge']
    assert graph['matching_edges'] == 1


def test_capped_maintenance_counts_are_stable_after_page_truncation(tmp_path):
    root = tmp_path / 'store'
    store = GroundRecallStore(root)
    store.save_concept(ConceptRecord(concept_id='target', title='Public target', release_level='public'))
    for index in range(101):
        store.save_review_candidate(ReviewCandidateRecord(
            review_candidate_id=f'review-{index:03}', candidate_type='concept', candidate_id='target',
            current_status='draft', release_level='public',
        ))

    service = DashboardService(root, tmp_path, maximum_release_level='public')
    first = service.maintenance()
    second = service.maintenance()
    assert first['visible_total'] == second['visible_total'] == 101
    assert len(first['items']) == len(second['items']) == 100
