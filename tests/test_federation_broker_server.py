from __future__ import annotations

import hashlib
import json
import os
import stat
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from groundrecall.federation_broker_server import (
    AUTH_SCHEMA,
    BrokerTokenAuth,
    make_server,
    provision_token,
)


def _request(url: str, *, method: str = "GET", token: str = "", body: bytes = b""):
    request = urllib.request.Request(url, data=body if method != "GET" else None, method=method)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    if body:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as response:
        return response.code, response.read()


def _server(tmp_path: Path, *, max_body_bytes: int = 128):
    auth_file = tmp_path / "auth.json"
    token = provision_token(auth_file, "alice")
    admin_token = provision_token(auth_file, "operator", administrator=True)
    server = make_server(
        tmp_path / "broker.sqlite3", auth_file, host="127.0.0.1", port=0,
        max_body_bytes=max_body_bytes,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, token, admin_token


def test_provisioned_tokens_store_only_hash_and_assign_server_identity(tmp_path: Path) -> None:
    auth_file = tmp_path / "secrets" / "auth.json"
    token = provision_token(auth_file, "alice")
    admin_token = provision_token(auth_file, "operator", administrator=True)
    raw = auth_file.read_text(encoding="utf-8")
    document = json.loads(raw)

    assert document["schema_version"] == AUTH_SCHEMA
    assert stat.S_IMODE(auth_file.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(auth_file.stat().st_mode) == 0o644
    assert token not in raw
    assert admin_token not in raw
    assert hashlib.sha256(token.encode()).hexdigest() == document["tokens"][0]["token_sha256"]
    assert BrokerTokenAuth(auth_file).authenticate([f"Bearer {token}"]).participant_id == "alice"
    assert BrokerTokenAuth(auth_file).authenticate([f"Bearer {admin_token}"]).roles == ["broker_admin"]
    assert BrokerTokenAuth(auth_file).authenticate([f"Bearer {token}", f"Bearer {token}"]) is None


def test_http_host_exposes_health_and_capabilities_but_requires_auth_for_operations(tmp_path: Path) -> None:
    server, thread, token, _admin_token = _server(tmp_path)
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        assert _request(base + "/healthz") == (200, b'{"ok":true}\n')
        status, body = _request(base + "/api/v1/broker")
        assert status == 200
        assert json.loads(body)["schema_version"] == "groundrecall.federation_broker.capabilities.v1"

        # JSON cannot invent the auth participant; absent middleware auth gets 401.
        body = json.dumps({"participant_id": "operator"}).encode()
        assert _request(base + "/api/v1/enrollment-requests", method="POST", body=body)[0] == 401

        # Auth identity is server-derived, and request body fields remain strict.
        assert _request(
            base + "/api/v1/enrollment-requests", method="POST", token=token, body=body
        )[0] == 400

        service = server.broker_dispatcher.service
        assert stat.S_IMODE(service.database_path.stat().st_mode) == 0o600
        connection = service._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("INSERT OR REPLACE INTO broker_meta(name,value) VALUES('mode_probe', X'01')")
            for suffix in ("-wal", "-shm"):
                sidecar = Path(str(service.database_path) + suffix)
                assert sidecar.exists()
                assert stat.S_IMODE(sidecar.stat().st_mode) == 0o600
            connection.rollback()
        finally:
            connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        os.umask(server.broker_previous_umask)


def test_http_host_rejects_oversized_body_and_unknown_bearer(tmp_path: Path) -> None:
    server, thread, _token, _admin_token = _server(tmp_path, max_body_bytes=16)
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        status, _ = _request(
            base + "/api/v1/enrollment-requests", method="POST", token="bad-token", body=b"x" * 17
        )
        assert status == 413
        status, _ = _request(
            base + "/api/v1/enrollment-requests", method="POST", token="bad-token", body=b"{}"
        )
        assert status == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        os.umask(server.broker_previous_umask)


def test_invalid_or_empty_auth_configuration_fails_closed(tmp_path: Path) -> None:
    auth_file = tmp_path / "auth.json"
    auth_file.write_text(json.dumps({"schema_version": AUTH_SCHEMA, "tokens": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="at least one token"):
        BrokerTokenAuth(auth_file)
