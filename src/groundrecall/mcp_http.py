"""Bounded HTTP pilot adapter for the local GroundRecall MCP core.

This adapter intentionally keeps the transport small: JSON-RPC requests are
POSTed to ``/mcp`` and health is exposed at ``/healthz``. It is suitable for a
private tunnel or local integration tests, not direct public exposure. The
server owns policy configuration and identity; callers cannot replace them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from threading import BoundedSemaphore, Event, Lock, Thread
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
    "handoff_get",
    "handoff_list",
    "handoff_events",
    }
)
HANDOFF_WRITE_TOOLS = frozenset({"handoff_propose", "handoff_update_status", "handoff_accept", "handoff_complete", "handoff_review", "handoff_promotion_request", "handoff_claim", "handoff_release", "progress_append", "result_propose"})

# Keep transport negotiation independent from the local stdio adapter.  These
# values are intentionally constants: responses must not disclose policy
# paths, store locations, or other server internals.
MCP_HTTP_PROTOCOL_VERSION = "2025-06-18"
MCP_HTTP_SERVER_INFO = {"name": "groundrecall-mcp-http", "version": "0.1.0a1"}
MCP_HTTP_RESPONSE_TOO_LARGE = b'{"error":"response_too_large"}\n'
MCP_HTTP_MIN_RESPONSE_BYTES = len(MCP_HTTP_RESPONSE_TOO_LARGE)


@dataclass(frozen=True)
class MCPHTTPConfig:
    policy_config: str
    store_dir: str = ""
    require_policy: bool = False
    subject_id: str = ""
    realm_id: str = ""
    bearer_token: str = ""
    identity_file: str = ""
    allowed_tools: frozenset[str] = field(default_factory=lambda: DEFAULT_READ_ONLY_TOOLS)
    max_body_bytes: int = 1_000_000
    max_response_bytes: int = 1_000_000
    max_concurrent_requests: int = 16
    request_timeout_seconds: float = 0.0
    audit_log_path: str = ""


@dataclass(frozen=True)
class MCPPrincipal:
    subject_id: str
    realm_id: str = ""
    maximum_release_level: str = "private"
    allowed_tools: frozenset[str] = field(default_factory=lambda: DEFAULT_READ_ONLY_TOOLS)


def _load_identities(path: str) -> dict[str, MCPPrincipal]:
    if not path:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("identity file must contain a JSON object")
    rows = payload.get("identities", [])
    if not isinstance(rows, list):
        raise ValueError("identity file identities must be a list")
    identities: dict[str, MCPPrincipal] = {}
    for row in rows:
        if not isinstance(row, dict) or not str(row.get("token", "")) or not str(row.get("subject_id", "")):
            raise ValueError("identity entries require token and subject_id")
        token = str(row["token"])
        tools = frozenset(row.get("allowed_tools") or DEFAULT_READ_ONLY_TOOLS)
        unknown = tools - TOOLS.keys()
        if unknown:
            raise ValueError(f"identity contains unknown MCP tools: {sorted(unknown)}")
        if token in identities:
            raise ValueError("identity file contains duplicate token")
        identities[token] = MCPPrincipal(
            subject_id=str(row["subject_id"]),
            realm_id=str(row.get("realm_id", "")),
            maximum_release_level=str(row.get("maximum_release_level", "private")),
            allowed_tools=tools,
        )
    return identities


def _json_response(
    request_id: Any,
    result: Any = None,
    error: dict[str, Any] | None = None,
    *,
    correlation_id: str = "",
) -> bytes:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
    if correlation_id:
        # MCP permits implementation metadata on responses.  Keep this
        # deliberately free of credentials or caller-supplied values.
        payload["_meta"] = {"groundrecall": {"correlation_id": correlation_id}}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


def _bounded_response_body(body: bytes, maximum: int) -> tuple[bytes, bool]:
    """Return a response body bounded by ``maximum`` without exposing content."""
    if len(body) <= maximum:
        return body, False
    return MCP_HTTP_RESPONSE_TOO_LARGE, True


def _response_http_status(body: bytes) -> int:
    """Map transport-level overload errors to HTTP without exposing details."""
    try:
        payload = json.loads(body)
        if payload.get("error", {}).get("code") == -32005:
            return 429
        if payload.get("error", {}).get("code") == -32006:
            return 504
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return 200


def _response_correlation_id(body: bytes) -> str:
    """Extract only the server-generated correlation ID from a response."""
    try:
        payload = json.loads(body)
        value = payload.get("_meta", {}).get("groundrecall", {}).get("correlation_id", "")
    except (TypeError, ValueError, json.JSONDecodeError):
        value = ""
    if isinstance(value, str) and len(value) == 32 and all(char in "0123456789abcdef" for char in value):
        return value
    return uuid.uuid4().hex


class _AuditLog:
    """Optional append-only JSONL access log; never records request content.

    Records form a hash chain within the active file.  Rotation intentionally
    starts a new chain (the first record has an empty ``previous_hash``), so
    archives remain independently verifiable and no mutable sidecar state is
    required.
    """

    def __init__(self, path: str):
        self.path = Path(path) if path else None
        self._lock = Lock()
        self._previous_hash = self._read_previous_hash()

    def _read_previous_hash(self) -> str:
        if self.path is None or not self.path.is_file():
            return ""
        try:
            for line in reversed(self.path.read_text(encoding="utf-8").splitlines()):
                if not line.strip():
                    continue
                row = json.loads(line)
                value = row.get("record_hash") if isinstance(row, dict) else None
                if isinstance(value, str) and value:
                    return value
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            # Do not make an optional audit sink prevent service startup.  The
            # verifier remains strict and reports malformed/tampered records.
            return ""
        return ""

    def write(self, *, correlation_id: str, principal: MCPPrincipal | None,
              method: str, tool: str = "", decision: str, result_class: str,
              http_status: int | None = None, reason: str = "") -> None:
        if self.path is None:
            return
        row: dict[str, Any] = {
            "event_kind": "groundrecall_mcp_access",
            "schema_version": "groundrecall.mcp_access.v1",
            "event_id": uuid.uuid4().hex,
            "recorded_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "correlation_id": correlation_id,
            "method": method,
            "decision": decision,
            "result_class": result_class,
        }
        if tool:
            row["tool"] = tool
        if principal is not None:
            row["subject_id"] = principal.subject_id
            if principal.realm_id:
                row["realm_id"] = principal.realm_id
            row["maximum_release_level"] = principal.maximum_release_level
        if http_status is not None:
            row["http_status"] = http_status
        if reason:
            row["reason"] = reason
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            row["hash_algorithm"] = "sha256"
            row["previous_hash"] = self._previous_hash
            row["record_hash"] = _audit_record_hash(row, self._previous_hash)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
            self._previous_hash = row["record_hash"]


def _audit_record_hash(row: dict[str, Any], previous_hash: str) -> str:
    payload = dict(row)
    payload.pop("record_hash", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((previous_hash + "\n" + canonical).encode("utf-8")).hexdigest()


def verify_audit_log(path: str) -> dict[str, Any]:
    """Verify the active JSONL audit chain and return bounded summary data.

    Legacy unchained records are accepted before the first chained record so
    existing logs remain readable.  Once chaining begins, every subsequent
    record must carry a valid hash and predecessor link.  Rotation boundaries
    are represented by a new file whose first chained record has an empty
    ``previous_hash``.
    """
    log_path = Path(path)
    if not log_path.is_file():
        raise ValueError("audit log does not exist")
    previous = ""
    chained = False
    records = 0
    chained_records = 0
    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"cannot read audit log: {exc}") from exc
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        records += 1
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid audit JSON at line {line_number}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"audit record at line {line_number} is not an object")
        record_hash = row.get("record_hash")
        if not record_hash:
            if chained:
                raise ValueError(f"missing record hash at line {line_number}")
            continue
        if row.get("hash_algorithm") != "sha256":
            raise ValueError(f"unsupported audit hash algorithm at line {line_number}")
        if row.get("previous_hash", "") != previous:
            raise ValueError(f"audit chain predecessor mismatch at line {line_number}")
        expected = _audit_record_hash(row, previous)
        if record_hash != expected:
            raise ValueError(f"audit record hash mismatch at line {line_number}")
        chained = True
        chained_records += 1
        previous = record_hash
    return {"records": records, "chained_records": chained_records, "last_hash": previous}


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
        if config.max_response_bytes < MCP_HTTP_MIN_RESPONSE_BYTES:
            raise ValueError(f"max_response_bytes must be at least {MCP_HTTP_MIN_RESPONSE_BYTES}")
        if config.max_concurrent_requests < 1 or config.max_concurrent_requests > 1024:
            raise ValueError("max_concurrent_requests must be between 1 and 1024")
        if config.request_timeout_seconds < 0 or config.request_timeout_seconds > 3600:
            raise ValueError("request_timeout_seconds must be between 0 and 3600")
        self.config = config
        self.audit = _AuditLog(config.audit_log_path)
        self._request_slots = BoundedSemaphore(config.max_concurrent_requests)
        self.identities = _load_identities(config.identity_file)
        if config.identity_file and not self.identities:
            raise ValueError("identity file must contain at least one identity")
        if self.identities and config.bearer_token:
            raise ValueError("configure either bearer_token or identity_file, not both")

    def readiness(self) -> tuple[bool, dict[str, Any]]:
        """Return bounded operational checks without revealing configured paths."""
        policy_ok = self._policy_available() if self.config.require_policy else Path(self.config.policy_config).is_file()
        store_configured = bool(self.config.store_dir)
        store_path = Path(self.config.store_dir) if store_configured else None
        store_ok = bool(store_path and store_path.is_dir() and os.access(store_path, os.R_OK | os.W_OK))
        checks = {"policy": policy_ok, "store": store_ok}
        ready = policy_ok and store_configured and store_ok
        reason = "ready" if ready else ("store_not_configured" if not store_configured else "dependency_unavailable")
        return ready, {"ok": ready, "service": "groundrecall-mcp-http", "checks": checks, "reason": reason}

    def _policy_available(self) -> bool:
        try:
            return Path(self.config.policy_config).is_file() and load_policy_plugins(self.config.policy_config) is not None
        except Exception:  # policy parsing/provider construction must fail closed
            return False

    def principal_for_token(self, token: str = "") -> MCPPrincipal:
        if self.identities:
            principal = self.identities.get(token)
            if principal is None:
                raise PermissionError("unknown bearer token")
            return principal
        if self.config.bearer_token and token != self.config.bearer_token:
            raise PermissionError("invalid bearer token")
        return MCPPrincipal(subject_id=self.config.subject_id, realm_id=self.config.realm_id, allowed_tools=self.config.allowed_tools)

    def dispatch(self, request: dict[str, Any], *, token: str = "") -> bytes | None:
        if not self._request_slots.acquire(blocking=False):
            correlation_id = uuid.uuid4().hex
            self.audit.write(correlation_id=correlation_id, principal=None,
                             method=str(request.get("method", "")), decision="denied",
                             result_class="overloaded", http_status=429,
                             reason="request_concurrency_limit")
            return _json_response(request.get("id"), error={"code": -32005, "message": "server busy"}, correlation_id=correlation_id)
        if self.config.request_timeout_seconds <= 0:
            try:
                return self._dispatch_unbounded(request, token=token)
            finally:
                self._request_slots.release()

        completed = Event()
        result: dict[str, Any] = {}

        def run() -> None:
            try:
                result["value"] = self._dispatch_unbounded(request, token=token)
            except BaseException as exc:  # propagate handler/auth errors to caller
                result["error"] = exc
            finally:
                self._request_slots.release()
                completed.set()

        Thread(target=run, name="groundrecall-mcp-request", daemon=True).start()
        if not completed.wait(self.config.request_timeout_seconds):
            correlation_id = uuid.uuid4().hex
            self.audit.write(correlation_id=correlation_id, principal=None,
                             method=str(request.get("method", "")), decision="denied",
                             result_class="timeout", http_status=504,
                             reason="request_execution_timeout")
            return _json_response(request.get("id"), error={"code": -32006, "message": "request timed out"}, correlation_id=correlation_id)
        if "error" in result:
            raise result["error"]
        return result.get("value")

    def _dispatch_unbounded(self, request: dict[str, Any], *, token: str = "") -> bytes | None:
        correlation_id = uuid.uuid4().hex
        method = str(request.get("method", ""))
        try:
            principal = self.principal_for_token(token)
        except PermissionError as exc:
            self.audit.write(correlation_id=correlation_id, principal=None, method=method,
                             decision="denied", result_class="authorization_error",
                             http_status=401, reason=str(exc))
            raise
        if self.config.require_policy and not self._policy_available():
            self.audit.write(correlation_id=correlation_id, principal=principal, method=method,
                             decision="denied", result_class="policy_unavailable",
                             http_status=503, reason="server_policy_unavailable")
            return _json_response(request.get("id"), error={"code": -32004, "message": "server policy unavailable"}, correlation_id=correlation_id)
        enabled_tools = self.config.allowed_tools & principal.allowed_tools
        method = request.get("method")
        request_id = request.get("id")
        if method == "initialize":
            self.audit.write(correlation_id=correlation_id, principal=principal, method=method,
                             decision="allowed", result_class="success", http_status=200)
            return _json_response(
                request_id,
                {
                    "protocolVersion": MCP_HTTP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": dict(MCP_HTTP_SERVER_INFO),
                },
                correlation_id=correlation_id,
            )
        if method == "ping":
            self.audit.write(correlation_id=correlation_id, principal=principal, method=method,
                             decision="allowed", result_class="success", http_status=200)
            return _json_response(request_id, {}, correlation_id=correlation_id)
        if method == "notifications/initialized":
            self.audit.write(correlation_id=correlation_id, principal=principal, method=method,
                             decision="allowed", result_class="notification", http_status=200)
            return None
        if method == "tools/list":
            tools = []
            for tool in list_tools():
                if tool["name"] not in enabled_tools:
                    continue
                exposed = dict(tool)
                exposed["annotations"] = {"readOnlyHint": tool["name"] not in HANDOFF_WRITE_TOOLS}
                tools.append(exposed)
            self.audit.write(correlation_id=correlation_id, principal=principal, method=method,
                             decision="allowed", result_class="success", http_status=200)
            return _json_response(request_id, {"tools": tools}, correlation_id=correlation_id)
        if method == "tools/call":
            params = dict(request.get("params") or {})
            name = str(params.get("name", ""))
            if name not in enabled_tools:
                self.audit.write(correlation_id=correlation_id, principal=principal, method=method,
                                 tool=name, decision="denied", result_class="policy_denied",
                                 http_status=200, reason="tool_not_enabled")
                return _json_response(request_id, error={"code": -32003, "message": "tool is not enabled by server policy"}, correlation_id=correlation_id)
            arguments = dict(params.get("arguments") or {})
            # Server-owned controls override caller-supplied policy and identity.
            arguments["policy_config"] = self.config.policy_config
            if self.config.store_dir:
                arguments["store_dir"] = self.config.store_dir
            if self.config.subject_id:
                arguments["subject_id"] = principal.subject_id
            elif principal.subject_id:
                arguments["subject_id"] = principal.subject_id
            if principal.maximum_release_level:
                arguments["maximum_release_level"] = principal.maximum_release_level
            # Realm is server-owned just like subject and release caps. An
            # empty realm is intentional for fixed-token local deployments.
            arguments["realm_id"] = principal.realm_id
            arguments.pop("policy_request", None)
            metadata = {"groundrecall.correlation_id": correlation_id}
            if principal.realm_id:
                metadata["groundrecall.realm_id"] = principal.realm_id
            # Caller policy fields are ignored, but server-generated metadata
            # is supplied so policy providers can correlate evaluations safely.
            arguments["policy_request"] = {"metadata": metadata}
            params["arguments"] = arguments
            request = dict(request)
            request["params"] = params
        response = handle_request(request)
        if response is None:
            self.audit.write(correlation_id=correlation_id, principal=principal, method=method,
                             tool=str((request.get("params") or {}).get("name", "")),
                             decision="allowed", result_class="notification", http_status=200)
            return None
        error = response.get("error")
        self.audit.write(correlation_id=correlation_id, principal=principal, method=method,
                         tool=str((request.get("params") or {}).get("name", "")),
                         decision="allowed" if error is None else "completed",
                         result_class="error" if error is not None else "success", http_status=200,
                         reason="handler_error" if error is not None else "")
        response = dict(response)
        response["_meta"] = {"groundrecall": {"correlation_id": correlation_id}}
        return (json.dumps(response, separators=(",", ":")) + "\n").encode("utf-8")


def make_server(host: str, port: int, config: MCPHTTPConfig) -> ThreadingHTTPServer:
    application = MCPHTTPApplication(config)

    class Handler(BaseHTTPRequestHandler):
        server_version = "GroundRecallMCP/0.1"

        def _authorized(self) -> bool:
            try:
                self._principal = application.principal_for_token(self._token())
                return True
            except PermissionError:
                return False

        def _token(self) -> str:
            value = self.headers.get("Authorization", "")
            return value[7:] if value.startswith("Bearer ") else ""

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
            elif self.path == "/readyz":
                ready, payload = application.readiness()
                self._write(200 if ready else 503, (json.dumps(payload, separators=(",", ":")) + "\n").encode())
            else:
                self._write(404, b'{"error":"not_found"}\n')

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/mcp":
                self._write(404, b'{"error":"not_found"}\n')
                return
            if not self._authorized():
                # Do not parse or retain an unauthorized body.  Record only a
                # transport-level denial and a server-generated correlation ID.
                application.audit.write(
                    correlation_id=uuid.uuid4().hex,
                    principal=None,
                    method="HTTP /mcp",
                    decision="denied",
                    result_class="authorization_error",
                    http_status=401,
                    reason="invalid bearer token",
                )
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
                body = application.dispatch(request, token=self._token())
                if body is not None:
                    bounded, exceeded = _bounded_response_body(body, application.config.max_response_bytes)
                    if exceeded:
                        application.audit.write(
                            correlation_id=_response_correlation_id(body),
                            principal=self._principal,
                            method=str(request.get("method", "")),
                            tool=str((request.get("params") or {}).get("name", "")),
                            decision="denied",
                            result_class="response_too_large",
                            http_status=502,
                            reason="response_too_large",
                        )
                        self._write(502, bounded)
                    else:
                        self._write(_response_http_status(bounded), bounded)
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
    parser.add_argument("--store-dir", default="", help="Server-owned store path used for readiness and MCP calls.")
    parser.add_argument("--require-policy", action="store_true", help="Fail closed if the server policy becomes unavailable or invalid.")
    parser.add_argument("--subject-id", default="", help="Server-owned principal identity for all requests.")
    parser.add_argument("--realm-id", default="", help="Server-owned realm for fixed-token deployments.")
    parser.add_argument("--bearer-token", default="", help="Optional bearer token; use a tunnel or stronger auth for deployment.")
    parser.add_argument("--identity-file", default="", help="JSON file mapping bearer tokens to server-owned principals and tool caps.")
    parser.add_argument("--max-response-bytes", type=int, default=1_000_000, help="Maximum MCP response size; oversized results return a bounded error.")
    parser.add_argument("--max-concurrent-requests", type=int, default=16, help="Maximum concurrent MCP dispatches; overload returns a bounded 429 response.")
    parser.add_argument("--request-timeout-seconds", type=float, default=0.0, help="Optional bounded MCP execution wait; timed-out workers finish in the background while retaining their concurrency slot.")
    parser.add_argument("--audit-log-path", default="", help="Optional append-only JSONL access audit path (never stores request content or tokens).")
    args = parser.parse_args()
    server = make_server(args.host, args.port, MCPHTTPConfig(policy_config=args.policy_config, store_dir=args.store_dir, require_policy=args.require_policy, subject_id=args.subject_id, realm_id=args.realm_id, bearer_token=args.bearer_token, identity_file=args.identity_file, max_response_bytes=args.max_response_bytes, max_concurrent_requests=args.max_concurrent_requests, request_timeout_seconds=args.request_timeout_seconds, audit_log_path=args.audit_log_path))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
