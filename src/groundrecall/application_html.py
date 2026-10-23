"""Small, dependency free HTML views for the application read contract.

The views are intentionally model free and read only.  They accept validated
application response objects and escape every value before placing it in the
document, so they can be used by a browser adapter or a simple custom search
shortcut without introducing a template dependency.
"""
from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import quote

from .application_contract import RecordResponse, SearchResponse


def _e(value: Any) -> str:
    return escape(str(value), quote=True)


def _page(title: str, content: str) -> str:
    return (
        "<!doctype html><html lang=\"en\"><head>"
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_e(title)} · GroundRecall</title></head><body>"
        '<header><a href="/">GroundRecall</a></header><main>'
        f"{content}</main></body></html>"
    )


def render_error_page(status: int, message: str) -> str:
    """Render a bounded generic error page without exposing server details."""
    return _page(f"Error {status}", f"<h1>{_e(message)}</h1><p><a href=\"/search\">Search again</a></p>")


def render_search_page(response: SearchResponse | None = None, *, query: str = "", error: str = "") -> str:
    """Render the search form and results, including explicit empty states."""
    form = (
        '<form method="get" action="/search">'
        f'<label for="q">Search GroundRecall</label><input id="q" name="q" value="{_e(query)}" maxlength="512">'
        '<button type="submit">Search</button></form>'
    )
    if error:
        return _page("Search", form + f'<p role="alert">{_e(error)}</p>')
    if response is None:
        return _page("Search", form + "<p>Enter a query to search recorded knowledge.</p>")

    parts = [form, f"<p>{len(response.results)} result(s)</p>"]
    if response.diagnostics:
        parts.append("<ul aria-label=\"Diagnostics\">" + "".join(f"<li>{_e(item)}</li>" for item in response.diagnostics) + "</ul>")
    if not response.results:
        parts.append("<p>No records matched in this view.</p>")
    else:
        parts.append("<ol>" + "".join(
            f'<li><h2><a href="{_e(result.human_url)}">{_e(result.title or result.stable_id)}</a></h2>'
            f'<p>{_e(result.excerpt)}</p><small>{_e(result.kind)} · {_e(result.match_reason.detail)}</small></li>'
            for result in response.results
        ) + "</ol>")
    return _page(f"Search: {query}" if query else "Search", "".join(parts))


def render_record_page(response: RecordResponse | None = None, *, error: str = "") -> str:
    """Render one record and its bounded relationship summary."""
    if error:
        return _page("Record", f'<p role="alert">{_e(error)}</p><p><a href="/search">Search again</a></p>')
    if response is None:
        return render_error_page(404, "Record not found")
    record = response.record
    content = [
        f'<p><a href="/search">Search</a> · {_e(record.kind)}</p>',
        f"<h1>{_e(record.title or record.stable_id)}</h1>",
        f"<p>{_e(record.excerpt)}</p>",
        f"<p>Review state: {_e(record.review_state)}</p>",
        f'<p><code>{_e(record.stable_id)}</code></p>',
    ]
    if response.relationships:
        content.append("<h2>Relationships</h2><ul>" + "".join(
            _relationship(item)
            if isinstance(item, dict) else f"<li>{_e(item)}</li>"
            for item in response.relationships
        ) + "</ul>")
    else:
        content.append("<p>No relationships recorded.</p>")
    return _page(record.title or record.stable_id, "".join(content))


def _relationship(item: dict[str, Any]) -> str:
    kind = str(item.get('kind', 'related'))
    record_id = str(item.get('record_id', item.get('id', '')))
    label = f"{_e(kind)}: {_e(record_id)}"
    if kind in {'source', 'fragment', 'artifact', 'observation', 'claim', 'concept', 'relation', 'review_candidate', 'promotion'} and record_id:
        url = '/records/' + quote(kind + '::' + record_id, safe='')
        label = f'<a href="{_e(url)}">{label}</a>'
    return f'<li>{label}</li>'
