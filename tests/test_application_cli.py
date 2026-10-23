from __future__ import annotations

import json

from groundrecall.application_cli import run
from groundrecall.application_contract import ApplicationResult, MatchReason, SearchResponse


def _response() -> SearchResponse:
    return SearchResponse(
        request_id="req-cli",
        index_generation="search-index-v1:test",
        effective_scope="private",
        results=[
            ApplicationResult(
                stable_id="claim::migration",
                kind="claim",
                title="Migration",
                excerpt="Migration has multiple causes.",
                human_url="/records/claim%3A%3Amigration",
                match_reason=MatchReason(kind="lexical", detail="matched indexed content"),
            )
        ],
    )


def test_human_cli_prints_result_and_stable_url(monkeypatch, capsys, tmp_path) -> None:
    class FakeService:
        def __init__(self, store_dir):
            assert store_dir == str(tmp_path)

        def search(self, request, *, request_id=None):
            assert request.query == "multiple causes"
            assert request.limit == 3
            assert request_id == "req-cli"
            return _response()

    monkeypatch.setattr("groundrecall.application_cli.ApplicationReadService", FakeService)
    assert run([str(tmp_path), "multiple causes", "--limit", "3", "--request-id", "req-cli"]) == 0
    output = capsys.readouterr().out
    assert "Migration (claim)" in output
    assert "URL: /records/claim%3A%3Amigration" in output


def test_json_cli_serializes_contract_envelope(monkeypatch, capsys, tmp_path) -> None:
    class FakeService:
        def __init__(self, store_dir):
            pass

        def search(self, request, *, request_id=None):
            return _response()

    monkeypatch.setattr("groundrecall.application_cli.ApplicationReadService", FakeService)
    assert run([str(tmp_path), "migration", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "groundrecall.application.search_response.v1"
    assert payload["results"][0]["human_url"] == "/records/claim%3A%3Amigration"


def test_json_flag_is_a_shortcut_for_json_format(monkeypatch, capsys, tmp_path) -> None:
    class FakeService:
        def __init__(self, store_dir):
            pass

        def search(self, request, *, request_id=None):
            return _response()

    monkeypatch.setattr("groundrecall.application_cli.ApplicationReadService", FakeService)
    assert run([str(tmp_path), "migration", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["request_id"] == "req-cli"
