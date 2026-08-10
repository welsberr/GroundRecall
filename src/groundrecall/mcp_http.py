"""Bounded HTTP pilot adapter for the local GroundRecall MCP core.

This adapter intentionally keeps the transport small: JSON-RPC requests are
POSTed to ``/mcp`` and health is exposed at ``/healthz``. It is suitable for a
private tunnel or local integration tests, not direct public exposure. The
server owns policy configuration and identity; callers cannot replace them.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .mcp import TOOLS, handle_request, list_tools
from .policy import load_policy_plugins


DEFAULT_READ_ONLY_TOOLS = frozenset(
    {
        "inspect_store",
        "query_concept",
        "search_store",
        "prior_work_review",
        "catalog_discovery",
        "subscription_status",
        "impact_report",
        "stewardship_orphans",
        "review_backlog",
        "review_backlog_item",
    }
)


@dataclass(frozen=True)
class MCPHTTPConfig:
    policy_config: str
    subject_id: str = ""
    bearer_token: str = ""
    allowed_tools: frozenset[str] = field(default_factory=lambda: DEFAULT_READ_ONLY_TOOLS)
    max_body_bytes: int = 1_000_000


def _json_response(request_id: Any, result: Any = None, error: dict[str, Any] | None = None) -> bytes:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


class MCPHTTPApplication:
    def __init__(self, config: MCPHTTPConfig):
        if not config.policy_config:
            raise ValueError("server policy_config is required")
        policy_path = Path(config.policy_config)
        if not policy_path.is_file():
            raise ValueError("server policy_config must point to an existing policy file")
        load_policy_plugins(policy_path)
        unknown = config.allowed_tools - TOOLS.keys()
        if unknown:
            raise ValueError(f"unknown MCP tools: {sorted(unknown)}")
        self.config = config

    def dispatch(self, request: dict[str, Any]) -> bytes | None:
        method = request.get("method")
        request_id = request.get("id")
        if method == "tools/list":
            tools = []
            for tool in list_tools():
                if tool["name"] not in self.config.allowed_tools:
                    continue
                exposed = dict(tool)
                exposed["annotations"] = {"readOnlyHint": True}
                tools.append(exposed)
            return _json_response(request_id, {"tools": tools})
        if method == "tools/call":
            params = dict(request.get("params") or {})
            name = str(params.get("name", ""))
            if name not in self.config.allowed_tools:
                return _json_response(request_id, error={"code": -32003, "message": "tool is not enabled by server policy"})
            arguments = dict(params.get("arguments") or {})
            # Server-owned controls override caller-supplied policy and identity.
            arguments["policy_config"] = self.config.policy_config
            if self.config.subject_id:
                arguments["subject_id"] = self.config.subject_id
            arguments.pop("policy_request", None)
            params["arguments"] = arguments
            request = dict(request)
            request["params"] = params
        response = handle_request(request)
        if response is None:
            return None
        return (json.dumps(response, separators=(",", ":")) + "\n").encode("utf-8")


def make_server(host: str, port: int, config: MCPHTTPConfig) -> ThreadingHTTPServer:
    application = MCPHTTPApplication(config)

    class Handler(BaseHTTPRequestHandler):
        server_version = "GroundRecallMCP/0.1"

        def _authorized(self) -> bool:
            expected = application.config.bearer_token
            if not expected:
                return True
            return self.headers.get("Authorization", "") == f"Bearer {expected}"

        def _write(self, status: int, body: bytes, content_type: str = "application/json") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/healthz":
                self._write(200, b'{"ok":true,"service":"groundrecall-mcp-http"}\n')
            else:
                self._write(404, b'{"error":"not_found"}\n')

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/mcp":
                self._write(404, b'{"error":"not_found"}\n')
                return
            if not self._authorized():
                self._write(401, b'{"error":"unauthorized"}\n')
                return
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                length = -1
            if length < 0 or length > application.config.max_body_bytes:
                self._write(413, b'{"error":"request_too_large"}\n')
                return
            try:
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict):
                    raise ValueError("request must be a JSON object")
                body = application.dispatch(request)
                if body is not None:
                    self._write(200, body)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self._write(400, json.dumps({"error": "invalid_request", "message": str(exc)}).encode() + b"\n")

        def log_message(self, format: str, *args: Any) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the bounded GroundRecall HTTP MCP pilot.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--policy-config", required=True, help="Server-owned policy plugin configuration.")
    parser.add_argument("--subject-id", default="", help="Server-owned principal identity for all requests.")
    parser.add_argument("--bearer-token", default="", help="Optional bearer token; use a tunnel or stronger auth for deployment.")
    args = parser.parse_args()
    server = make_server(args.host, args.port, MCPHTTPConfig(policy_config=args.policy_config, subject_id=args.subject_id, bearer_token=args.bearer_token))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
