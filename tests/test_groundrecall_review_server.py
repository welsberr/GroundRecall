from __future__ import annotations

from types import SimpleNamespace

from groundrecall.review_server import _safe_show_entry, _safe_verify_entry


class _StoreWithoutConflicts:
    def get_entry(self, citation_key: str):
        if citation_key != "baum1974generalized":
            return None
        return {"citation_key": citation_key, "title": "On two types of deviation"}

    def get_field_provenance(self, citation_key: str):
        return [{"field_name": "title", "source_label": "refs.bib"}]

    def get_entry_bibtex(self, citation_key: str):
        return "@article{baum1974generalized, title={On two types of deviation}}"


class _ApiWithPartialSupport:
    def __init__(self):
        self.store = _StoreWithoutConflicts()

    def show_entry(self, citation_key: str, **kwargs):
        raise AttributeError("get_conflicts missing in underlying store")

    def verify_bibtex(self, bibtex_text: str, *, context: str = "", limit: int = 5):
        raise RuntimeError("pybtex unavailable")

    def verify_strings(self, values: list[str], *, context: str = "", limit: int = 5):
        return {"context": context, "results": [{"values": values, "limit": limit}]}


def test_safe_show_entry_falls_back_when_citegeist_show_entry_is_incompatible() -> None:
    api = _ApiWithPartialSupport()

    payload = _safe_show_entry(api, "baum1974generalized")

    assert payload is not None
    assert payload["citation_key"] == "baum1974generalized"
    assert payload["conflicts"] == []
    assert payload["provenance"][0]["source_label"] == "refs.bib"
    assert "bibtex" in payload


def test_safe_verify_entry_falls_back_to_verify_strings() -> None:
    api = _ApiWithPartialSupport()
    entry = SimpleNamespace(
        citation_key="baum1974generalized",
        title="On two types of deviation",
        author="W. M. Baum",
        year="1974",
        raw_bibtex="@article{baum1974generalized, title={On two types of deviation}}",
    )

    payload = _safe_verify_entry(api, entry, context="pieces/intro.tex Intro", limit=5)

    assert payload["results"]
    assert payload["results"][0]["values"][0] == "baum1974generalized"
