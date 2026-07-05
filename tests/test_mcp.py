from __future__ import annotations

from groundrecall.mcp import handle_request


def test_mcp_lists_tools() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {tool["name"] for tool in response["result"]["tools"]}
    assert {"inspect_store", "query_concept", "search_store", "export_snapshot"} <= names


def test_mcp_initializes() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        }
    )
    assert response["result"]["serverInfo"]["name"] == "groundrecall-mcp"
    assert "tools" in response["result"]["capabilities"]


def test_mcp_reports_unknown_tool() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "missing", "arguments": {}},
        }
    )
    assert response["error"]["code"] == -32000
    assert "Unknown tool" in response["error"]["message"]
