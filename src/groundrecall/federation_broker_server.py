"""Runnable, bearer-authenticated HTTP host for the federation broker."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .federation_broker import FederationBrokerService
from .federation_broker_contract import AuthenticatedParticipant
from .federation_broker_http import FederationBrokerHTTPDispatcher


AUTH_SCHEMA = "groundrecall.federation_broker.auth.v1"
_TOKEN_HASH = re.compile(r"^[0-9a-f]{64}$")
_DEFAULT_BODY_LIMIT = 4_000_000
_DEFAULT_RESPONSE_LIMIT = 4_000_000
_DEFAULT_SOCKET_TIMEOUT = 15.0


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _validate_auth_document(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("schema_version") != AUTH_SCHEMA:
        raise ValueError(f"auth file must use schema_version {AUTH_SCHEMA!r}")
    rows = payload.get("tokens")
    if not isinstance(rows, list) or not rows:
        raise ValueError("auth file must contain at least one token")
    seen: set[str] = set()
    identities: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each auth token entry must be an object")
        digest = row.get("token_sha256")
        participant_id = row.get("participant_id")
        roles = row.get("roles", [])
        if not isinstance(digest, str) or not _TOKEN_HASH.fullmatch(digest):
            raise ValueError("token_sha256 must be a lowercase SHA-256 hex digest")
        if digest in seen:
            raise ValueError("auth file contains a duplicate token digest")
        if not isinstance(participant_id, str) or not participant_id.strip() or len(participant_id) > 256:
            raise ValueError("each token requires a nonempty participant_id (max 256 characters)")
        if not isinstance(roles, list) or any(not isinstance(role, str) or not role for role in roles):
            raise ValueError("token roles must be a list of nonempty strings")
        if len(roles) > 20 or len(set(roles)) != len(roles):
            raise ValueError("token roles must be unique and contain no more than 20 entries")
        unknown = set(roles) - {"broker_admin"}
        if unknown:
            raise ValueError(f"unsupported broker role(s): {', '.join(sorted(unknown))}")
        seen.add(digest)
        identities.append({"token_sha256": digest, "participant_id": participant_id, "roles": roles})
    return identities


def _write_one_time_token_file(path_text: str | Path, token: str) -> Path:
    """Create a new owner-only bearer-token file without overwriting anything."""
    target = Path(path_text)
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent_info = parent.stat()
    if not parent.is_dir() or parent_info.st_mode & 0o077:
        raise ValueError("token file parent directory must be private (mode 0700 or stricter)")
    if hasattr(os, "getuid") and parent_info.st_uid != os.getuid():
        raise ValueError("token file parent directory must be owned by the current user")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(target, flags, 0o600)
    except FileExistsError as exc:
        raise ValueError("token file already exists; refusing to overwrite it") from exc
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(token + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        directory_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        try:
            target.unlink()
        except OSError:
            pass
        raise
    return target


class BrokerTokenAuth:
    """Resolve opaque bearer tokens to server-owned identities and roles."""

    def __init__(self, auth_file: str | Path):
        self.auth_file = Path(auth_file)
        raw = self.auth_file.read_bytes()
        if len(raw) > 1_000_000:
            raise ValueError("auth file exceeds the 1 MB configuration limit")
        self.identities = _validate_auth_document(json.loads(raw))

    def authenticate(self, header_values: list[str] | None) -> AuthenticatedParticipant | None:
        if not header_values or len(header_values) != 1:
            return None
        value = header_values[0]
        scheme, separator, token = value.partition(" ")
        if not separator or scheme.lower() != "bearer" or not token or token.strip() != token:
            return None
        if any(char.isspace() for char in token):
            return None
        supplied = _token_digest(token)
        # Compare all rows instead of returning at the first matching identity.
        matched: dict[str, Any] | None = None
        for identity in self.identities:
            if hmac.compare_digest(supplied, identity["token_sha256"]):
                matched = identity
        if matched is None:
            return None
        return AuthenticatedParticipant(
            participant_id=matched["participant_id"], roles=list(matched["roles"])
        )


def provision_token(
    auth_file: str | Path,
    participant_id: str,
    *,
    administrator: bool = False,
    token_file: str | Path | None = None,
) -> str:
    """Add one random token, persisting only its SHA-256 digest; return it once."""
    target = Path(auth_file)
    if not participant_id.strip() or len(participant_id) > 256:
        raise ValueError("participant ID must be nonempty and at most 256 characters")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.exists():
        if target.is_symlink() or not target.is_file():
            raise ValueError("auth file must be a regular, non-symlink file")
        payload = json.loads(target.read_text(encoding="utf-8"))
        identities = _validate_auth_document(payload)
    else:
        identities = []
    token = secrets.token_urlsafe(32)
    one_time_file = _write_one_time_token_file(token_file, token) if token_file is not None else None
    identities.append({
        "token_sha256": _token_digest(token),
        "participant_id": participant_id,
        "roles": ["broker_admin"] if administrator else [],
    })
    document = {"schema_version": AUTH_SCHEMA, "tokens": identities}
    try:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary: str | None = None
        try:
            descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
            os.fchmod(descriptor, 0o644)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(document, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            temporary = None
            directory_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
    except Exception:
        if one_time_file is not None:
            try:
                one_time_file.unlink()
            except OSError:
                pass
        raise
    return token


def make_server(
    database_path: str | Path,
    auth_file: str | Path,
    *,
    host: str = "0.0.0.0",
    port: int = 8765,
    max_body_bytes: int = _DEFAULT_BODY_LIMIT,
    max_response_bytes: int = _DEFAULT_RESPONSE_LIMIT,
    socket_timeout_seconds: float = _DEFAULT_SOCKET_TIMEOUT,
) -> ThreadingHTTPServer:
    if not 0 <= port <= 65535:
        raise ValueError("port must be in the range 0..65535")
    if socket_timeout_seconds <= 0:
        raise ValueError("socket timeout must be positive")
    # Keep future SQLite database/WAL/SHM creations private for this process.
    previous_umask = os.umask(0o077)
    auth = BrokerTokenAuth(auth_file)
    dispatcher = FederationBrokerHTTPDispatcher(
        FederationBrokerService(database_path),
        max_body_bytes=max_body_bytes,
        max_response_bytes=max_response_bytes,
    )
    for path in (
        dispatcher.service.database_path,
        Path(str(dispatcher.service.database_path) + "-wal"),
        Path(str(dispatcher.service.database_path) + "-shm"),
    ):
        try:
            os.chmod(path, 0o600)
        except FileNotFoundError:
            pass

    class Handler(BaseHTTPRequestHandler):
        server_version = "GroundRecallFederationBroker"
        sys_version = ""

        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(socket_timeout_seconds)

        def _send(self, status: int, body: bytes, content_type: str = "application/json") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _json_error(self, status: int, error: str) -> None:
            self._send(status, json.dumps({"error": error}, separators=(",", ":")).encode() + b"\n")

        def _handle(self) -> None:
            if self.path == "/healthz" and self.command == "GET":
                try:
                    with dispatcher.service._connection() as connection:
                        connection.execute("SELECT 1").fetchone()
                except Exception:
                    self._json_error(503, "unavailable")
                    return
                self._send(200, b'{"ok":true}\n')
                return

            lengths = self.headers.get_all("Content-Length", [])
            transfer_encoding = self.headers.get_all("Transfer-Encoding", [])
            if len(lengths) > 1 or transfer_encoding:
                self._json_error(400, "invalid_request")
                return
            try:
                body_length = int(lengths[0]) if lengths else 0
            except ValueError:
                self._json_error(400, "invalid_request")
                return
            if body_length < 0:
                self._json_error(400, "invalid_request")
                return
            if body_length > dispatcher.max_body_bytes:
                self._json_error(413, "request_too_large")
                return
            body = self.rfile.read(body_length) if body_length else b""
            if len(body) != body_length:
                self._json_error(400, "invalid_request")
                return
            principals = self.headers.get_all("Authorization", [])
            principal = auth.authenticate(principals)
            try:
                status, response = dispatcher.dispatch(
                    self.command, self.path, body, participant=principal
                )
            except Exception:
                self._json_error(500, "internal_error")
                return
            self._send(status, response)

        def do_GET(self) -> None:
            self._handle()

        def do_POST(self) -> None:
            self._handle()

        def log_message(self, _format: str, *_args: object) -> None:
            # Avoid recording tokens, query parameters, and user-supplied paths.
            return

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        request_queue_size = 64

    server = Server((host, port), Handler)
    server.broker_dispatcher = dispatcher  # type: ignore[attr-defined]
    server.broker_previous_umask = previous_umask  # type: ignore[attr-defined]
    return server


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run or administer a GroundRecall federation broker")
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve = subparsers.add_parser("serve", help="run the broker HTTP service")
    serve.add_argument("--database", default=os.environ.get("BROKER_DB_PATH", "/var/lib/groundrecall-broker/broker.sqlite3"))
    serve.add_argument("--auth-file", default=os.environ.get("BROKER_AUTH_FILE", "/run/secrets/broker-auth.json"))
    serve.add_argument("--host", default=os.environ.get("BROKER_HOST", "0.0.0.0"))
    serve.add_argument("--port", type=int, default=int(os.environ.get("BROKER_PORT", "8765")))
    serve.add_argument("--max-body-bytes", type=int, default=int(os.environ.get("BROKER_MAX_BODY_BYTES", str(_DEFAULT_BODY_LIMIT))))
    serve.add_argument("--max-response-bytes", type=int, default=int(os.environ.get("BROKER_MAX_RESPONSE_BYTES", str(_DEFAULT_RESPONSE_LIMIT))))
    serve.add_argument("--socket-timeout-seconds", type=float, default=float(os.environ.get("BROKER_SOCKET_TIMEOUT_SECONDS", str(_DEFAULT_SOCKET_TIMEOUT))))
    token = subparsers.add_parser("provision-token", help="create a bearer token and persist only its hash")
    token.add_argument("--auth-file", required=True)
    token.add_argument("--participant-id", required=True)
    token.add_argument("--admin", action="store_true", help="grant broker_admin (use only for operator tokens)")
    token.add_argument("--token-file", help="write the one-time token to a new mode-0600 file instead of stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "provision-token":
        try:
            token = provision_token(
                args.auth_file,
                args.participant_id,
                administrator=args.admin,
                token_file=args.token_file,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"token provisioning failed: {exc}", file=sys.stderr)
            return 2
        if args.token_file:
            print(f"Bearer token written once to protected file: {args.token_file}")
        else:
            print("Bearer token (shown once; save it in a password manager):")
            print(token)
        return 0

    try:
        # SQLite database and WAL files should be private to the service user.
        os.umask(0o077)
        server = make_server(
            args.database,
            args.auth_file,
            host=args.host,
            port=args.port,
            max_body_bytes=args.max_body_bytes,
            max_response_bytes=args.max_response_bytes,
            socket_timeout_seconds=args.socket_timeout_seconds,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"broker startup failed: {exc}", file=sys.stderr)
        return 2
    try:
        print(f"GroundRecall federation broker listening on {args.host}:{server.server_port}", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
