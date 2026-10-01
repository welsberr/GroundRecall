from __future__ import annotations

import hashlib
import json
import stat
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from groundrecall.change_feed import FederationChangeBundle, FederationChangeBundleManifest
from groundrecall.federation_broker_client import (
    BrokerClientError,
    BrokerHTTPClient,
    _persist_bundles,
    _load_json,
    _read_token,
    _safe_auth_revoke,
    _secure_local_url,
    main,
)
from groundrecall.federation_broker_contract import ChangeBundlePage
from groundrecall.federation_broker_contract import BrokerCapabilities
from groundrecall.federation_broker_server import BrokerTokenAuth, main as server_main, provision_token


def _bundle(bundle_id: str = "../../remote/path") -> FederationChangeBundle:
    return FederationChangeBundle(
        manifest=FederationChangeBundleManifest(
            bundle_id=bundle_id,
            created_at="2026-09-19T12:00:00Z",
            producer_instance_id="producer-a",
            subscription_id="sub-a",
            cursor_start="cursor-0",
            cursor_end="cursor-1",
            event_count=0,
            content_hash="0" * 64,
        ),
        events=[],
    )


def test_broker_url_requires_https_except_loopback() -> None:
    assert _secure_local_url("http://127.0.0.1:18765/") == "http://127.0.0.1:18765"
    assert _secure_local_url("http://[::1]:18765") == "http://[::1]:18765"
    assert _secure_local_url("http://localhost:18765") == "http://localhost:18765"
    assert _secure_local_url("https://broker.example.invalid") == "https://broker.example.invalid"
    with pytest.raises(BrokerClientError, match="loopback"):
        _secure_local_url("http://broker.example.invalid")
    with pytest.raises(BrokerClientError, match="credentials"):
        _secure_local_url("https://user:secret@broker.example.invalid")
    with pytest.raises(BrokerClientError, match="origin"):
        _secure_local_url("https://broker.example.invalid/api/v1")


def test_token_file_must_be_private_and_environment_can_supply_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("secret-token\n", encoding="utf-8")
    token_file.chmod(0o600)
    assert _read_token(str(token_file)) == "secret-token"
    token_file.chmod(0o644)
    with pytest.raises(BrokerClientError, match="private"):
        _read_token(str(token_file))
    link = tmp_path / "token-link"
    link.symlink_to(token_file)
    with pytest.raises(BrokerClientError, match="could not read"):
        _read_token(str(link))
    monkeypatch.setenv("GROUNDRECALL_BROKER_TOKEN", "env-secret")
    with pytest.raises(BrokerClientError, match="either"):
        _read_token(str(token_file))
    assert _read_token("") == "env-secret"


def test_json_input_is_bounded_and_rejects_symlinks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import groundrecall.federation_broker_client as client_module

    monkeypatch.setattr(client_module, "_MAX_HTTP_BYTES", 16)
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * 17)
    with pytest.raises(BrokerClientError, match="exceeds the 4 MB client limit"):
        _load_json(str(oversized))

    ordinary = tmp_path / "ordinary.json"
    ordinary.write_text("{}", encoding="utf-8")
    link = tmp_path / "linked.json"
    link.symlink_to(ordinary)
    with pytest.raises(BrokerClientError, match="could not read input file"):
        _load_json(str(link))


def test_pull_handoff_uses_private_hashed_names_and_never_overwrites(tmp_path: Path) -> None:
    directory = tmp_path / "local-quarantine"
    page = ChangeBundlePage(subscription_id="sub-a", bundles=[_bundle()])
    written = _persist_bundles(page, str(directory))
    path = Path(written[0])
    assert path.parent == directory
    assert "remote" not in path.name
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert FederationChangeBundle.model_validate_json(path.read_text()).manifest.bundle_id == "../../remote/path"
    assert _persist_bundles(page, str(directory)) == written

    altered = ChangeBundlePage(subscription_id="sub-a", bundles=[_bundle("../../another/path")])
    assert Path(_persist_bundles(altered, str(directory))[0]).read_bytes() != path.read_bytes()


def test_auth_revoke_removes_exact_participant_hashes_and_preserves_container_readability(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    auth_file = tmp_path / "auth.json"
    smoke_token = provision_token(auth_file, "compose-smoke")
    keep_token = provision_token(auth_file, "diane")
    smoke_hash = hashlib.sha256(smoke_token.encode()).hexdigest()

    assert main(["auth-revoke", "--auth-file", str(auth_file), "--participant-id", "compose-smoke"]) == 0
    output = capsys.readouterr().out
    raw = auth_file.read_text(encoding="utf-8")
    assert "removed 1 token" in output
    assert "recreate" in output
    assert smoke_token not in output and smoke_hash not in output and smoke_hash not in raw
    assert BrokerTokenAuth(auth_file).authenticate([f"Bearer {smoke_token}"]) is None
    assert BrokerTokenAuth(auth_file).authenticate([f"Bearer {keep_token}"]).participant_id == "diane"
    assert stat.S_IMODE(auth_file.stat().st_mode) == 0o644


def test_auth_revoke_refuses_to_remove_final_token_without_mutation(tmp_path: Path) -> None:
    auth_file = tmp_path / "auth.json"
    token = provision_token(auth_file, "only-participant")
    before = auth_file.read_bytes()
    with pytest.raises(BrokerClientError, match="final auth token"):
        _safe_auth_revoke(str(auth_file), "only-participant")
    assert auth_file.read_bytes() == before
    assert BrokerTokenAuth(auth_file).authenticate([f"Bearer {token}"]).participant_id == "only-participant"


def test_provision_token_file_is_private_and_secret_is_not_printed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    auth_file = tmp_path / "auth.json"
    token_file = tmp_path / "private" / "participant.token"
    assert server_main([
        "provision-token", "--auth-file", str(auth_file), "--participant-id", "alice",
        "--token-file", str(token_file),
    ]) == 0
    stdout = capsys.readouterr().out
    token = token_file.read_text(encoding="utf-8").strip()
    assert token not in stdout
    assert "written once to protected file" in stdout
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
    assert BrokerTokenAuth(auth_file).authenticate([f"Bearer {token}"]).participant_id == "alice"
    with pytest.raises(ValueError, match="already exists"):
        provision_token(auth_file, "bob", token_file=token_file)


def test_keygen_writes_private_pair_atomically_without_printing_key_material(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from cryptography.hazmat.primitives import serialization

    private_path = tmp_path / "private" / "producer.pem"
    public_path = tmp_path / "public" / "producer.pem"
    assert main([
        "keygen", "--key-id", "producer-2026",
        "--private-key-file", str(private_path), "--public-key-file", str(public_path),
    ]) == 0
    stdout = capsys.readouterr().out
    private_bytes = private_path.read_bytes()
    public_bytes = public_path.read_bytes()
    private_key = serialization.load_pem_private_key(private_bytes, password=None)
    public_key = serialization.load_pem_public_key(public_bytes)
    assert private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ) == public_bytes
    assert stat.S_IMODE(private_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(public_path.stat().st_mode) == 0o644
    assert stat.S_IMODE(private_path.parent.stat().st_mode) == 0o700
    assert "producer-2026" in stdout and str(private_path) in stdout and str(public_path) in stdout
    assert "PRIVATE KEY" not in stdout and private_bytes.decode() not in stdout
    assert main([
        "keygen", "--key-id", "producer-2027",
        "--private-key-file", str(private_path), "--public-key-file", str(public_path),
    ]) == 2
    assert private_path.read_bytes() == private_bytes
    assert public_path.read_bytes() == public_bytes


def test_http_client_authenticates_without_redirecting(tmp_path: Path) -> None:
    seen: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            seen.append(self.headers.get("Authorization", ""))
            payload = json.dumps({
                "schema_version": "groundrecall.federation_broker.capabilities.v1",
                "api_version": "v1",
                "service": "groundrecall-federation-broker",
                "signing_algorithms": ["ed25519"],
                "operations": [],
            }).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = BrokerHTTPClient(f"http://127.0.0.1:{server.server_port}", "do-not-log-this")
        result = client.request("GET", "/api/v1/broker", None, BrokerCapabilities)
        assert result.service == "groundrecall-federation-broker"
        assert seen == ["Bearer do-not-log-this"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_http_client_refuses_redirects_without_forwarding_bearer() -> None:
    paths_and_tokens: list[tuple[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            paths_and_tokens.append((self.path, self.headers.get("Authorization", "")))
            self.send_response(302)
            self.send_header("Location", "/redirect-target")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = BrokerHTTPClient(f"http://127.0.0.1:{server.server_port}", "sensitive-token")
        with pytest.raises(BrokerClientError, match="HTTP 302"):
            client.request("GET", "/api/v1/broker", None, BrokerCapabilities)
        assert paths_and_tokens == [("/api/v1/broker", "Bearer sensitive-token")]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_http_client_checks_response_size_before_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    import groundrecall.federation_broker_client as client_module

    monkeypatch.setattr(client_module, "_MAX_HTTP_BYTES", 16)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            payload = b"x" * 17
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = BrokerHTTPClient(f"http://127.0.0.1:{server.server_port}")
        with pytest.raises(BrokerClientError, match="response exceeds"):
            client.request("GET", "/api/v1/broker", None, BrokerCapabilities)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
