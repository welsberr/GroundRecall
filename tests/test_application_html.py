from groundrecall.application_contract import ApplicationResult, MatchReason, RecordResponse, SearchResponse
from groundrecall.application_html import render_record_page, render_search_page


def _result() -> ApplicationResult:
    return ApplicationResult(
        stable_id="claim::one",
        kind="claim",
        title="A <claim> & more",
        excerpt='Text with "markup"',
        human_url="/records/claim%3A%3Aone",
        match_reason=MatchReason(kind="lexical", detail="matched <query>"),
    )


def test_search_renderer_escapes_content_and_keeps_stable_link() -> None:
    page = render_search_page(SearchResponse(request_id="r", index_generation="g", effective_scope="private", results=[_result()]), query='<script>')
    assert '<script>' not in page
    assert "&lt;script&gt;" in page
    assert "A &lt;claim&gt; &amp; more" in page
    assert 'href="/records/claim%3A%3Aone"' in page


def test_search_renderer_has_initial_and_empty_states() -> None:
    assert "Enter a query" in render_search_page()
    response = SearchResponse(request_id="r", index_generation="g", effective_scope="private", diagnostics=["no <matches>"], results=[])
    page = render_search_page(response, query="nothing")
    assert "No records matched" in page
    assert "no &lt;matches&gt;" in page


def test_record_renderer_escapes_record_and_relationships() -> None:
    response = RecordResponse(request_id="r", index_generation="g", effective_scope="private", record=_result(), relationships=[{"kind": "concept", "record_id": "x&y"}])
    page = render_record_page(response)
    assert "A &lt;claim&gt; &amp; more" in page
    assert "x&amp;y" in page
    assert 'href="/records/concept%3A%3Ax%26y"' in page
    assert 'href="/search">Search</a>' in page
    assert "Relationships" in page
    assert "<script>" not in page
