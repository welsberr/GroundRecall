from __future__ import annotations

import json

from groundrecall.application_http import ApplicationHTTPDispatcher
from groundrecall.application_service import ApplicationReadService
from groundrecall.models import ClaimRecord
from groundrecall.store import GroundRecallStore


def _dispatcher(tmp_path):
    store = GroundRecallStore(tmp_path)
    store.save_claim(ClaimRecord(claim_id="one", claim_text="A useful remembered claim"))
    return ApplicationHTTPDispatcher(ApplicationReadService(tmp_path))


def test_application_api_dispatches_bounded_search_capabilities_and_records(tmp_path) -> None:
    dispatcher = _dispatcher(tmp_path)
    status, body = dispatcher.dispatch("GET", "/api/v1/capabilities")
    assert status == 200
    assert json.loads(body)["operations"]["capture"] is False

    status, body = dispatcher.dispatch("POST", "/api/v1/search", b'{"query":"useful","limit":1}')
    payload = json.loads(body)
    assert status == 200 and payload["results"][0]["stable_id"] == "claim::one"

    status, body = dispatcher.dispatch("GET", "/api/v1/records/claim%3A%3Aone")
    assert status == 200 and json.loads(body)["record"]["stable_id"] == "claim::one"


def test_application_api_rejects_invalid_or_inaccessible_requests(tmp_path) -> None:
    dispatcher = _dispatcher(tmp_path)
    status, body = dispatcher.dispatch("POST", "/api/v1/search", b'{"query":"x","store_dir":"/private"}')
    assert status == 400 and json.loads(body) == {"error": "invalid_request"}
    status, body = dispatcher.dispatch("GET", "/api/v1/records/claim%3A%3Amissing")
    assert status == 404 and json.loads(body) == {"error": "not_found"}


def test_browser_pages_are_escaped_and_bookmarkable(tmp_path) -> None:
    dispatcher = _dispatcher(tmp_path)
    status, page = dispatcher.dispatch_html("GET", "/?q=%3Cscript%3E")
    assert status == 200
    assert b"&lt;script&gt;" in page and b"<script>" not in page
    status, page = dispatcher.dispatch_html("GET", "/search?q=useful")
    assert status == 200 and b"A useful remembered claim" in page
    status, page = dispatcher.dispatch_html("GET", "/records/claim%3A%3Aone")
    assert status == 200 and b"A useful remembered claim" in page
    status, page = dispatcher.dispatch_html("GET", "/records/claim%3A%3Amissing")
    assert status == 404 and b"Record not found" in page
