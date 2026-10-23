"""Small HTTP dispatcher for the versioned GroundRecall application API.

The dispatcher is deliberately independent of a web framework.  The MCP HTTP
adapter and tests can use the same bounded, read-only routing behavior.
"""
from __future__ import annotations

import json
from http import HTTPStatus
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4

from pydantic import ValidationError

from .application_contract import SearchRequest
from .application_html import render_error_page, render_record_page, render_search_page
from .application_service import ApplicationReadService


APPLICATION_API_PREFIX = "/api/v1"


class ApplicationHTTPDispatcher:
    """Dispatch application API requests to an ``ApplicationReadService``."""

    def __init__(self, service: ApplicationReadService, *, max_body_bytes: int = 1_000_000,
                 max_response_bytes: int = 1_000_000):
        if max_body_bytes < 1:
            raise ValueError("max_body_bytes must be positive")
        if max_response_bytes < 1:
            raise ValueError("max_response_bytes must be positive")
        self.service = service
        self.max_body_bytes = max_body_bytes
        self.max_response_bytes = max_response_bytes

    @staticmethod
    def _json(payload: object) -> bytes:
        return (json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")

    def _response(self, status: int, payload: object) -> tuple[int, bytes]:
        body = self._json(payload)
        if len(body) > self.max_response_bytes:
            return HTTPStatus.BAD_GATEWAY, self._json({"error": "response_too_large"})
        return status, body

    def _html_response(self, status: int, page: str) -> tuple[int, bytes]:
        body = page.encode("utf-8")
        if len(body) > self.max_response_bytes:
            return HTTPStatus.BAD_GATEWAY, render_error_page(502, "Response unavailable").encode("utf-8")
        return status, body

    def dispatch(self, method: str, path: str, body: bytes = b"") -> tuple[int, bytes]:
        """Return an HTTP status and bounded JSON body for one API request."""
        parsed = urlsplit(path)
        route = parsed.path
        method = method.upper()
        request_id = "app-http-" + uuid4().hex

        if method == "GET" and route == f"{APPLICATION_API_PREFIX}/capabilities":
            return self._response(HTTPStatus.OK, self.service.capabilities(request_id=request_id).model_dump(mode="json"))

        if method == "POST" and route == f"{APPLICATION_API_PREFIX}/search":
            if len(body) > self.max_body_bytes:
                return self._response(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "request_too_large"})
            try:
                request = SearchRequest.model_validate(json.loads(body))
            except (json.JSONDecodeError, TypeError, ValidationError):
                return self._response(HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            response = self.service.search(request, request_id=request_id)
            return self._response(HTTPStatus.OK, response.model_dump(mode="json"))

        record_prefix = f"{APPLICATION_API_PREFIX}/records/"
        if method == "GET" and route.startswith(record_prefix):
            encoded_id = route[len(record_prefix):]
            if not encoded_id or "/" in encoded_id:
                return self._response(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            record = self.service.read_record(unquote(encoded_id), request_id=request_id)
            if record is None:
                return self._response(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return self._response(HTTPStatus.OK, record.model_dump(mode="json"))

        return self._response(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def dispatch_html(self, method: str, path: str) -> tuple[int, bytes]:
        """Render the bookmarkable human search and record pages."""
        if method.upper() != "GET":
            return self._html_response(HTTPStatus.NOT_FOUND, render_error_page(404, "Page not found"))
        parsed = urlsplit(path)
        if parsed.path in {"/", "/search"}:
            query = parse_qs(parsed.query, keep_blank_values=True).get("q", [""])[0]
            if not query:
                return self._html_response(HTTPStatus.OK, render_search_page())
            try:
                request = SearchRequest(query=query)
            except ValidationError:
                return self._html_response(HTTPStatus.BAD_REQUEST, render_search_page(query=query, error="Search query is invalid."))
            response = self.service.search(request, request_id="app-html-" + uuid4().hex)
            return self._html_response(HTTPStatus.OK, render_search_page(response, query=query))

        record_prefix = "/records/"
        if parsed.path.startswith(record_prefix):
            encoded_id = parsed.path[len(record_prefix):]
            if not encoded_id or "/" in encoded_id:
                return self._html_response(HTTPStatus.NOT_FOUND, render_error_page(404, "Record not found"))
            response = self.service.read_record(unquote(encoded_id), request_id="app-html-" + uuid4().hex)
            if response is None:
                return self._html_response(HTTPStatus.NOT_FOUND, render_record_page())
            return self._html_response(HTTPStatus.OK, render_record_page(response))
        return self._html_response(HTTPStatus.NOT_FOUND, render_error_page(404, "Page not found"))
