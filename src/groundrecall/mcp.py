from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

from .export import export_canonical_snapshot
from .inspect import inspect_store
from .query import query_concept
from .search_index import search_index


SERVER_INFO = {"name": "groundrecall-mcp", "version": "0.1.0a0"}


def _json_text(payload: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}]}


def _inspect_store(arguments: dict[str, Any]) -> dict[str, Any]:
    return _json_text(
        inspect_store(
            arguments["store_dir"],
            include_graph=bool(arguments.get("include_graph", False)),
            compact_graph=bool(arguments.get("compact_graph", False)),
        )
    )


def _query_concept(arguments: dict[str, Any]) -> dict[str, Any]:
    payload = query_concept(arguments["store_dir"], arguments["concept"])
    if payload is None:
        payload = {"ok": False, "error": "concept not found", "concept": arguments["concept"]}
    return _json_text(payload)


def _search_store(arguments: dict[str, Any]) -> dict[str, Any]:
    return _json_text(
        search_index(
            arguments["store_dir"],
            arguments["query"],
            limit=int(arguments.get("limit", 20)),
            kinds=list(arguments.get("kinds", []) or []),
            corpora=list(arguments.get("corpora", []) or []),
            rebuild=bool(arguments.get("rebuild", False)),
            expand=bool(arguments.get("expand", False)),
        )
    )


def _export_snapshot(arguments: dict[str, Any]) -> dict[str, Any]:
    return _json_text(
        export_canonical_snapshot(
            arguments["store_dir"],
            arguments["out_dir"],
            snapshot_id=arguments.get("snapshot_id"),
            include_graph_diagnostics=bool(arguments.get("include_graph_diagnostics", False)),
            include_graph_interchange=bool(arguments.get("include_graph_interchange", False)),
        )
    )


TOOLS: dict[str, dict[str, Any]] = {
    "inspect_store": {
        "description": "Summarize a canonical GroundRecall store.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "store_dir": {"type": "string"},
                "include_graph": {"type": "boolean", "default": False},
                "compact_graph": {"type": "boolean", "default": False},
            },
            "required": ["store_dir"],
        },
        "handler": _inspect_store,
    },
    "query_concept": {
        "description": "Fetch a concept-centered GroundRecall query bundle.",
        "inputSchema": {
            "type": "object",
            "properties": {"store_dir": {"type": "string"}, "concept": {"type": "string"}},
            "required": ["store_dir", "concept"],
        },
        "handler": _query_concept,
    },
    "search_store": {
        "description": "Search the GroundRecall FTS index, rebuilding it if absent or requested.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "store_dir": {"type": "string"},
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
                "kinds": {"type": "array", "items": {"type": "string"}},
                "corpora": {"type": "array", "items": {"type": "string"}},
                "rebuild": {"type": "boolean", "default": False},
                "expand": {"type": "boolean", "default": False},
            },
            "required": ["store_dir", "query"],
        },
        "handler": _search_store,
    },
    "export_snapshot": {
        "description": "Export a public-guardrailed canonical GroundRecall snapshot.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "store_dir": {"type": "string"},
                "out_dir": {"type": "string"},
                "snapshot_id": {"type": "string"},
                "include_graph_diagnostics": {"type": "boolean", "default": False},
                "include_graph_interchange": {"type": "boolean", "default": False},
            },
            "required": ["store_dir", "out_dir"],
        },
        "handler": _export_snapshot,
    },
}


def list_tools() -> list[dict[str, Any]]:
    return [
        {key: value for key, value in tool.items() if key != "handler"} | {"name": name}
        for name, tool in TOOLS.items()
    ]


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}
    try:
        if method == "initialize":
            result = {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            }
        elif method == "notifications/initialized":
            return None
        elif method == "tools/list":
            result = {"tools": list_tools()}
        elif method == "tools/call":
            name = params.get("name")
            tool = TOOLS.get(name)
            if tool is None:
                raise ValueError(f"Unknown tool: {name}")
            handler: Callable[[dict[str, Any]], dict[str, Any]] = tool["handler"]
            result = handler(params.get("arguments") or {})
        else:
            raise ValueError(f"Unsupported method: {method}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except Exception as exc:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32000, "message": str(exc)},
        }


def serve(input_stream=sys.stdin, output_stream=sys.stdout) -> None:
    for line in input_stream:
        if not line.strip():
            continue
        response = handle_request(json.loads(line))
        if response is not None:
            output_stream.write(json.dumps(response) + "\n")
            output_stream.flush()


def main() -> None:
    serve()


if __name__ == "__main__":
    main()
