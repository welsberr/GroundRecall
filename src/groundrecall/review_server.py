from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .citation_support import materialize_citegeist_store
from .promotion import PromotionGateError, promote_import_to_store
from .review_workspace import GroundRecallReviewWorkspace


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(body)


def _serve_static(handler: BaseHTTPRequestHandler, asset_path: Path) -> None:
    if not asset_path.exists():
        _json_response(handler, 404, {"error": "asset not found"})
        return
    body = asset_path.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", mimetypes.guess_type(str(asset_path))[0] or "application/octet-stream")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _safe_show_entry(api: object, citation_key: str) -> dict | None:
    if not citation_key:
        return None
    try:
        return api.show_entry(  # type: ignore[attr-defined]
            citation_key,
            include_provenance=True,
            include_conflicts=True,
            include_bibtex=True,
        )
    except AttributeError:
        pass

    store = getattr(api, "store", None)
    if store is None:
        return None
    entry = store.get_entry(citation_key)
    if entry is None:
        return None
    payload = dict(entry)
    if hasattr(store, "get_field_provenance"):
        try:
            payload["provenance"] = store.get_field_provenance(citation_key)
        except Exception:
            payload["provenance"] = []
    if hasattr(store, "get_conflicts"):
        try:
            payload["conflicts"] = store.get_conflicts(citation_key)
        except Exception:
            payload["conflicts"] = []
    else:
        payload["conflicts"] = []
    if hasattr(store, "get_entry_bibtex"):
        try:
            payload["bibtex"] = store.get_entry_bibtex(citation_key)
        except Exception:
            payload["bibtex"] = None
    return payload


def _safe_verify_entry(api: object, entry: object, *, context: str, limit: int) -> dict:
    if getattr(entry, "raw_bibtex", ""):
        try:
            return api.verify_bibtex(entry.raw_bibtex, context=context, limit=limit)  # type: ignore[attr-defined]
        except Exception:
            pass
    values = [item for item in [getattr(entry, "citation_key", ""), getattr(entry, "title", ""), getattr(entry, "author", ""), getattr(entry, "year", "")] if item]
    try:
        return api.verify_strings(values, context=context, limit=limit)  # type: ignore[attr-defined]
    except Exception as exc:
        return {
            "context": context,
            "results": [],
            "error": str(exc),
        }


class GroundRecallReviewHandler(BaseHTTPRequestHandler):
    workspace: GroundRecallReviewWorkspace
    default_store_dir: str | None = None
    citegeist_bundle: dict | None = None

    def do_OPTIONS(self) -> None:
        _json_response(self, 200, {"ok": True})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/healthz":
            _json_response(self, 200, {"ok": True})
            return
        if parsed.path == "/api/load":
            review_data = self.workspace.load_review_data()
            review_data["citegeist"] = {
                "enabled": bool(self.citegeist_bundle and self.citegeist_bundle.get("available")),
                "db_path": self.citegeist_bundle.get("db_path") if self.citegeist_bundle else "",
                "ingested_files": self.citegeist_bundle.get("ingested_files", []) if self.citegeist_bundle else [],
                "show_entry_endpoint": "/api/citations/show-entry",
                "verify_endpoint": "/api/citations/verify",
            }
            _json_response(
                self,
                200,
                {
                    "ok": True,
                    "import_dir": str(self.workspace.import_dir),
                    "review_data": review_data,
                },
            )
            return
        if parsed.path == "/api/citations/show-entry":
            if not self.citegeist_bundle or not self.citegeist_bundle.get("available"):
                _json_response(self, 404, {"ok": False, "error": "citegeist unavailable"})
                return
            citation_key = parse_qs(parsed.query).get("citation_key", [""])[0]
            if not citation_key:
                _json_response(self, 400, {"ok": False, "error": "citation_key is required"})
                return
            payload = _safe_show_entry(self.citegeist_bundle["api"], citation_key)
            _json_response(self, 200, {"ok": payload is not None, "entry": payload})
            return

        asset_root = Path(__file__).with_name("review_app")
        if parsed.path in {"/", "/index.html"}:
            _serve_static(self, asset_root / "index.html")
            return
        if parsed.path == "/app.js":
            _serve_static(self, asset_root / "app.js")
            return
        if parsed.path == "/styles.css":
            _serve_static(self, asset_root / "styles.css")
            return
        _json_response(self, 404, {"error": "not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        payload = json.loads(raw.decode("utf-8") or "{}")

        if parsed.path == "/api/save":
            self.workspace.apply_updates(
                concept_updates=payload.get("concept_updates"),
                relation_updates=payload.get("relation_updates"),
                citation_updates=payload.get("citation_updates"),
                reviewer=payload.get("reviewer"),
            )
            _json_response(
                self,
                200,
                {
                    "ok": True,
                    "import_dir": str(self.workspace.import_dir),
                    "review_data": self.workspace.load_review_data(),
                },
            )
            return

        if parsed.path == "/api/promote":
            store_dir = payload.get("store_dir") or self.default_store_dir
            if not store_dir:
                _json_response(self, 400, {"ok": False, "error": "store_dir is required"})
                return
            try:
                result = promote_import_to_store(
                    import_dir=self.workspace.import_dir,
                    store_dir=store_dir,
                    reviewer=payload.get("reviewer"),
                    snapshot_id=payload.get("snapshot_id"),
                    allow_lint_errors=bool(payload.get("allow_lint_errors")),
                )
            except PromotionGateError as exc:
                _json_response(self, 409, {"ok": False, "error": str(exc), "gate": exc.payload})
                return
            _json_response(self, 200, {"ok": True, "promotion": result})
            return
        if parsed.path == "/api/citations/verify":
            if not self.citegeist_bundle or not self.citegeist_bundle.get("available"):
                _json_response(self, 404, {"ok": False, "error": "citegeist unavailable"})
                return
            citation_review_id = str(payload.get("citation_review_id") or "").strip()
            if not citation_review_id:
                _json_response(self, 400, {"ok": False, "error": "citation_review_id is required"})
                return
            session = self.workspace.load_session()
            entry = next((item for item in session.citation_reviews if item.citation_review_id == citation_review_id), None)
            if entry is None:
                _json_response(self, 404, {"ok": False, "error": "citation review entry not found"})
                return
            api = self.citegeist_bundle["api"]
            show_entry_payload = _safe_show_entry(api, entry.citation_key) if entry.citation_key else None
            context = f"{entry.artifact_path} {entry.artifact_title}".strip()
            verification = _safe_verify_entry(api, entry, context=context, limit=int(payload.get("limit", 5)))
            _json_response(
                self,
                200,
                {
                    "ok": True,
                    "citation_review_id": citation_review_id,
                    "entry": show_entry_payload,
                    "verification": verification,
                },
            )
            return

        _json_response(self, 404, {"error": "not found"})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GroundRecall local review server")
    parser.add_argument("import_dir")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--reviewer", default="GroundRecall Import")
    parser.add_argument("--store-dir", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    GroundRecallReviewHandler.workspace = GroundRecallReviewWorkspace(args.import_dir, reviewer=args.reviewer)
    GroundRecallReviewHandler.default_store_dir = args.store_dir
    GroundRecallReviewHandler.workspace.ensure_review_bundle()
    session = GroundRecallReviewHandler.workspace.load_session()
    GroundRecallReviewHandler.citegeist_bundle = materialize_citegeist_store(
        args.import_dir,
        session.draft_pack.pack.get("source_root", ""),
    )
    server = HTTPServer((args.host, args.port), GroundRecallReviewHandler)
    print(f"GroundRecall review server listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
