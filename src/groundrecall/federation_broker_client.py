"""Safe command-line HTTP client for a GroundRecall federation broker.

The client speaks only the broker's versioned HTTP API. It never opens or
modifies the broker database. Received change bundles are copied into a
receiver-local, mode-0700 quarantine handoff directory and are not imported,
accepted, or acknowledged automatically.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import stat
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, TypeVar

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import BaseModel, ValidationError

from .catalog import FederationCatalog
from .change_feed import FederationChangeBundle
from .federation_broker_contract import (
    BROKER_ACKNOWLEDGEMENT_SCHEMA,
    BROKER_BUNDLE_PULL_REQUEST_SCHEMA,
    BROKER_BUNDLE_SUBMISSION_SCHEMA,
    BROKER_CATALOG_DISCOVERY_REQUEST_SCHEMA,
    BROKER_CATALOG_SUBMISSION_SCHEMA,
    BROKER_ENROLLMENT_APPROVAL_SCHEMA,
    BROKER_ENROLLMENT_REVOCATION_SCHEMA,
    BROKER_KEY_REVOCATION_SCHEMA,
    BROKER_SIGNING_KEY_ADD_SCHEMA,
    BrokerCapabilities,
    BrokerEnrollmentRequest,
    BundleAcknowledgementReceipt,
    CatalogDiscoveryRequest,
    CatalogDiscoveryResponse,
    CatalogSubmissionReceipt,
    ChangeBundlePage,
    ChangeBundleReceipt,
    EnrollmentApprovalRequest,
    EnrollmentReceipt,
    EnrollmentRevocationReceipt,
    RevocationReceipt,
    SigningKeyAddRequest,
    SigningKeyReceipt,
    SigningKeyRevocationRequest,
    SubscriptionCreateRequest,
    SubscriptionReceipt,
)


_MAX_HTTP_BYTES = 4_000_000
_MAX_TOKEN_FILE_BYTES = 16_384
_TIMEOUT_SECONDS = 20
_TOKEN_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_M = TypeVar("_M", bound=BaseModel)


class BrokerClientError(RuntimeError):
    """A bounded, non-secret-bearing broker client error."""


def _secure_local_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise BrokerClientError("broker URL must be an absolute HTTPS URL (HTTP is allowed only on loopback)")
    if parsed.username is not None or parsed.password is not None:
        raise BrokerClientError("broker URL must not contain credentials")
    if parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise BrokerClientError("broker URL must identify only the broker origin")
    if parsed.scheme == "http":
        hostname = parsed.hostname.rstrip(".").lower()
        loopback = hostname == "localhost"
        try:
            loopback = loopback or ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            pass
        if not loopback:
            raise BrokerClientError("unencrypted HTTP is allowed only for localhost or a loopback IP")
    return value.rstrip("/")


def _read_token(token_file: str | None) -> str:
    env_token = os.environ.get("GROUNDRECALL_BROKER_TOKEN", "")
    if token_file and env_token:
        raise BrokerClientError("use either --token-file or GROUNDRECALL_BROKER_TOKEN, not both")
    if token_file:
        path = Path(token_file)
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise BrokerClientError("could not read broker token file") from exc
        try:
            with os.fdopen(descriptor, "rb") as handle:
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode):
                    raise BrokerClientError("broker token file must be a regular, non-symlink file")
                if info.st_mode & 0o077:
                    raise BrokerClientError("broker token file must be private (mode 0600 or stricter)")
                if hasattr(os, "getuid") and info.st_uid != os.getuid():
                    raise BrokerClientError("broker token file must be owned by the current user")
                if info.st_size > _MAX_TOKEN_FILE_BYTES:
                    raise BrokerClientError("broker token file is too large")
                token_bytes = handle.read(_MAX_TOKEN_FILE_BYTES + 1)
                if len(token_bytes) > _MAX_TOKEN_FILE_BYTES:
                    raise BrokerClientError("broker token file is too large")
            token = token_bytes.decode("utf-8").strip()
        except UnicodeError as exc:
            raise BrokerClientError("could not read broker token file") from exc
    else:
        token = env_token.strip()
    if not token or any(char.isspace() for char in token):
        raise BrokerClientError("a broker token is required via --token-file or GROUNDRECALL_BROKER_TOKEN")
    return token


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):  # type: ignore[no-untyped-def]
        # Never forward a bearer credential to a redirect target.
        return None


class BrokerHTTPClient:
    def __init__(self, base_url: str, token: str | None = None, *, timeout: float = _TIMEOUT_SECONDS):
        self.base_url = _secure_local_url(base_url)
        self.token = token
        self.timeout = timeout
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _NoRedirect()
        )

    def request(self, method: str, path: str, request_model: BaseModel | None, response_type: type[_M]) -> _M:
        body = b""
        headers = {"Accept": "application/json"}
        if request_model is not None:
            body = (request_model.model_dump_json(exclude_none=True) + "\n").encode("utf-8")
            if len(body) > _MAX_HTTP_BYTES:
                raise BrokerClientError("request exceeds the 4 MB client limit")
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(
            self.base_url + path,
            data=body if method.upper() != "GET" else None,
            headers=headers,
            method=method.upper(),
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    try:
                        if int(content_length) > _MAX_HTTP_BYTES:
                            raise BrokerClientError("broker response exceeds the 4 MB client limit")
                    except ValueError as exc:
                        raise BrokerClientError("broker returned an invalid response length") from exc
                raw = response.read(_MAX_HTTP_BYTES + 1)
                if len(raw) > _MAX_HTTP_BYTES:
                    raise BrokerClientError("broker response exceeds the 4 MB client limit")
        except urllib.error.HTTPError as exc:
            raw = exc.read(_MAX_HTTP_BYTES + 1)
            error_code = ""
            if len(raw) <= _MAX_HTTP_BYTES:
                try:
                    parsed_error = json.loads(raw)
                    candidate = parsed_error.get("error", "") if isinstance(parsed_error, dict) else ""
                    if isinstance(candidate, str) and re.fullmatch(r"[a-z0-9_]{1,64}", candidate):
                        error_code = f": {candidate}"
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
            raise BrokerClientError(f"broker returned HTTP {exc.code}{error_code}") from None
        except urllib.error.URLError as exc:
            # Avoid propagating exception reprs that can contain request context.
            raise BrokerClientError(f"broker request failed ({type(exc.reason).__name__})") from None
        except (TimeoutError, OSError) as exc:
            raise BrokerClientError(f"broker request failed ({type(exc).__name__})") from None
        try:
            payload = json.loads(raw)
            return response_type.model_validate(payload)
        except (json.JSONDecodeError, UnicodeDecodeError, ValidationError, TypeError) as exc:
            raise BrokerClientError("broker returned an invalid response document") from exc


def _load_json(path: str, *, model: type[_M] | None = None) -> Any:
    try:
        raw = _read_bounded_file(path, _MAX_HTTP_BYTES, "input file", "4 MB client limit")
        value = json.loads(raw)
        return model.model_validate(value) if model is not None else value
    except BrokerClientError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise BrokerClientError(f"could not load valid input JSON from {path}") from exc


def _read_bounded_file(
    path: str | Path,
    limit: int,
    description: str,
    limit_label: str,
) -> bytes:
    """Read a regular local file without following symlinks or exceeding limit."""
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise BrokerClientError(f"could not read {description}") from exc
    try:
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise BrokerClientError(f"{description} must be a regular, non-symlink file")
            if info.st_size > limit:
                raise BrokerClientError(f"{description} exceeds the {limit_label}")
            content = handle.read(limit + 1)
            if len(content) > limit:
                raise BrokerClientError(f"{description} exceeds the {limit_label}")
            return content
    except BrokerClientError:
        raise
    except OSError as exc:
        raise BrokerClientError(f"could not read {description}") from exc


def _write_private_token_file(path_text: str, token: str) -> None:
    path = Path(path_text)
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent_info = parent.stat()
    if not stat.S_ISDIR(parent_info.st_mode) or parent_info.st_mode & 0o077:
        raise BrokerClientError("token file parent directory must be private (mode 0700 or stricter)")
    if hasattr(os, "getuid") and parent_info.st_uid != os.getuid():
        raise BrokerClientError("token file parent directory must be owned by the current user")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise BrokerClientError("token file already exists; refusing to overwrite it") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(token + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(path, 0o600)
        directory_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def _atomic_create_file(path: Path, content: bytes, mode: int, *, private_parent: bool) -> None:
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700 if private_parent else 0o755)
    parent_info = parent.stat()
    if not parent.is_dir():
        raise BrokerClientError("key output parent must be a directory")
    if private_parent and (parent_info.st_mode & 0o077 or (hasattr(os, "getuid") and parent_info.st_uid != os.getuid())):
        raise BrokerClientError("private key directory must be owner-only and owned by the current user")
    if path.exists() or path.is_symlink():
        raise BrokerClientError(f"refusing to overwrite existing key file: {path}")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        # Hard-link creation publishes the complete file atomically and fails
        # if another process created the destination after the preflight.
        os.link(temporary, path)
        os.unlink(temporary)
        temporary = ""
        directory_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except FileExistsError as exc:
        raise BrokerClientError(f"refusing to overwrite existing key file: {path}") from exc
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _safe_auth_revoke(auth_file: str, participant_id: str) -> int:
    """Remove every bearer-token digest for one exact participant ID."""
    from .federation_broker_server import AUTH_SCHEMA, _validate_auth_document

    target = Path(auth_file)
    try:
        info = target.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise BrokerClientError("auth file must be a regular, non-symlink file")
        if hasattr(os, "getuid") and info.st_uid != os.getuid():
            raise BrokerClientError("auth file must be owned by the current user")
        if info.st_size > 1_000_000:
            raise BrokerClientError("auth file exceeds the 1 MB configuration limit")
        document = json.loads(target.read_text(encoding="utf-8"))
    except BrokerClientError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BrokerClientError("could not read a valid broker auth file") from exc
    try:
        identities = _validate_auth_document(document)
    except (TypeError, ValueError) as exc:
        raise BrokerClientError("broker auth file failed validation; no changes made") from exc
    if document.get("schema_version") != AUTH_SCHEMA:
        raise BrokerClientError("broker auth file failed validation; no changes made")
    kept = [row for row in identities if row["participant_id"] != participant_id]
    removed = len(identities) - len(kept)
    if not removed:
        return 0
    if not kept:
        raise BrokerClientError("refusing to remove the final auth token; provision a replacement token first")
    updated = {"schema_version": AUTH_SCHEMA, "tokens": kept}
    parent = target.parent
    temporary: str | None = None
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=parent)
        # This hash-only map is intentionally readable by the container's
        # unprivileged UID (10001); keep it at least 0644 and remove write
        # permission for group/other before replacing the original.
        target_mode = (stat.S_IMODE(info.st_mode) & ~0o022) | 0o644
        os.fchmod(descriptor, target_mode)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(updated, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = None
        directory_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise BrokerClientError("failed to atomically update broker auth file") from exc
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
    return removed


def _remote_client(args: argparse.Namespace, *, authenticated: bool = True) -> BrokerHTTPClient:
    url = args.url or os.environ.get("GROUNDRECALL_BROKER_URL", "")
    if not url:
        raise BrokerClientError("set --url or GROUNDRECALL_BROKER_URL")
    token = _read_token(args.token_file) if authenticated else None
    return BrokerHTTPClient(url, token)


def _add_remote_options(parser: argparse.ArgumentParser, *, authenticated: bool = True) -> None:
    parser.add_argument("--url", default="", help="Broker origin; or set GROUNDRECALL_BROKER_URL")
    if authenticated:
        parser.add_argument("--token-file", default="", help="Private bearer-token file (mode 0600); or set GROUNDRECALL_BROKER_TOKEN")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Use a GroundRecall federation broker over its bounded HTTP API.")
    commands = parser.add_subparsers(dest="command", required=True)

    keygen = commands.add_parser("keygen", help="create a local Ed25519 producer keypair")
    keygen.add_argument("--key-id", required=True)
    keygen.add_argument("--private-key-file", required=True)
    keygen.add_argument("--public-key-file", required=True)

    info = commands.add_parser("info", help="show the broker's public API capabilities")
    _add_remote_options(info, authenticated=False)

    enrollment = commands.add_parser("enrollment-request", help="submit a validated enrollment request JSON document")
    _add_remote_options(enrollment)
    enrollment.add_argument("--request", required=True)

    approve = commands.add_parser("enrollment-approve", help="approve a pending enrollment from a JSON bounds document")
    _add_remote_options(approve)
    approve.add_argument("--enrollment-id", required=True)
    approve.add_argument("--approval", required=True)

    catalog_publish = commands.add_parser("catalog-publish", help="publish an existing signed catalog JSON document")
    _add_remote_options(catalog_publish)
    catalog_publish.add_argument("--file", required=True)

    discover = commands.add_parser("catalog-discover", help="discover catalogs allowed by the receiver enrollment")
    _add_remote_options(discover)
    discover.add_argument("--query", default="")
    discover.add_argument("--realm-id", default="")
    discover.add_argument("--scope-id", action="append", default=[])
    discover.add_argument("--limit", type=int, default=20)

    subscription = commands.add_parser("subscription-create", help="create a receiver-owned bounded subscription")
    _add_remote_options(subscription)
    subscription.add_argument("--request", required=True)

    submit = commands.add_parser("bundle-submit", help="submit an existing signed change-bundle JSON document")
    _add_remote_options(submit)
    submit.add_argument("--file", required=True)

    pull = commands.add_parser("bundle-pull", help="pull bundles into a protected local quarantine handoff directory")
    _add_remote_options(pull)
    pull.add_argument("--subscription-id", required=True)
    pull.add_argument("--quarantine-dir", required=True)
    pull.add_argument("--limit", type=int, default=20)
    pull.add_argument("--after-cursor", default="")
    pull.add_argument("--local-subscription", default="", help="optional local change-feed subscription used for signature/policy verification and quarantine import")
    pull.add_argument("--verification-key-file", default="", help="producer public key for optional receiver-side signature verification")
    pull.add_argument("--key-id", default="")
    pull.add_argument("--policy-plugins", default="")
    pull.add_argument("--requester-id", default="")

    ack = commands.add_parser("bundle-ack", help="acknowledge one locally verified and quarantined pulled bundle")
    _add_remote_options(ack)
    ack.add_argument("--bundle-file", required=True, help="bundle file produced by bundle-pull")
    ack.add_argument("--verified-locally", action="store_true", help="required confirmation that local signature, subscription, and quarantine checks succeeded")

    key_revoke = commands.add_parser("key-revoke", help="revoke one signing key in the caller's enrollment")
    _add_remote_options(key_revoke)
    key_revoke.add_argument("--enrollment-id", required=True)
    key_revoke.add_argument("--key-id", required=True)
    key_revoke.add_argument("--reason", required=True)

    key_add = commands.add_parser("key-add", help="admin-authorized addition of an enrolled producer's public key")
    _add_remote_options(key_add)
    key_add.add_argument("--enrollment-id", required=True)
    key_add.add_argument("--key-id", required=True)
    key_add.add_argument("--public-key-file", required=True)

    enrollment_revoke = commands.add_parser("enrollment-revoke", help="revoke the caller's producer enrollment")
    _add_remote_options(enrollment_revoke)
    enrollment_revoke.add_argument("--enrollment-id", required=True)
    enrollment_revoke.add_argument("--reason", required=True)

    local_revoke = commands.add_parser("auth-revoke", help="remove all local bearer tokens for one participant; container recreation required")
    local_revoke.add_argument("--auth-file", required=True)
    local_revoke.add_argument("--participant-id", required=True)
    return parser


def _json_output(model: BaseModel) -> None:
    print(model.model_dump_json(indent=2))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "auth-revoke":
            removed = _safe_auth_revoke(args.auth_file, args.participant_id)
            print(f"removed {removed} token(s) for participant {args.participant_id}; recreate the broker container to apply the change")
            return 0

        if args.command == "keygen":
            if not args.key_id.strip() or len(args.key_id) > 128:
                raise BrokerClientError("key ID must be nonempty and at most 128 characters")
            private_path = Path(args.private_key_file)
            public_path = Path(args.public_key_file)
            if private_path.absolute() == public_path.absolute():
                raise BrokerClientError("private and public key paths must differ")
            key = Ed25519PrivateKey.generate()
            private_bytes = key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            public_bytes = key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            _atomic_create_file(private_path, private_bytes, 0o600, private_parent=True)
            try:
                _atomic_create_file(public_path, public_bytes, 0o644, private_parent=False)
            except Exception:
                try:
                    private_path.unlink()
                except OSError:
                    pass
                raise
            print(json.dumps({"key_id": args.key_id, "private_key_file": str(private_path), "public_key_file": str(public_path)}, indent=2))
            return 0

        if args.command == "info":
            result = _remote_client(args, authenticated=False).request("GET", "/api/v1/broker", None, BrokerCapabilities)
        elif args.command == "enrollment-request":
            request_model = _load_json(args.request, model=BrokerEnrollmentRequest)
            result = _remote_client(args).request("POST", "/api/v1/enrollment-requests", request_model, EnrollmentReceipt)
        elif args.command == "enrollment-approve":
            request_model = _load_json(args.approval, model=EnrollmentApprovalRequest)
            path = "/api/v1/admin/enrollments/{}/approval".format(urllib.parse.quote(args.enrollment_id, safe=""))
            result = _remote_client(args).request("POST", path, request_model, EnrollmentReceipt)
        elif args.command == "catalog-publish":
            catalog = _load_json(args.file, model=FederationCatalog)
            from .federation_broker_contract import CatalogSubmissionRequest
            request_model = CatalogSubmissionRequest(catalog=catalog)
            result = _remote_client(args).request("POST", "/api/v1/catalogs", request_model, CatalogSubmissionReceipt)
        elif args.command == "catalog-discover":
            request_model = CatalogDiscoveryRequest(
                schema_version=BROKER_CATALOG_DISCOVERY_REQUEST_SCHEMA,
                query=args.query, realm_id=args.realm_id, scope_ids=args.scope_id, limit=args.limit,
            )
            result = _remote_client(args).request("POST", "/api/v1/catalogs/discover", request_model, CatalogDiscoveryResponse)
        elif args.command == "subscription-create":
            request_model = _load_json(args.request, model=SubscriptionCreateRequest)
            result = _remote_client(args).request("POST", "/api/v1/subscriptions", request_model, SubscriptionReceipt)
        elif args.command == "bundle-submit":
            bundle = _load_json(args.file, model=FederationChangeBundle)
            from .federation_broker_contract import ChangeBundleSubmissionRequest
            request_model = ChangeBundleSubmissionRequest(bundle=bundle)
            result = _remote_client(args).request("POST", "/api/v1/change-bundles", request_model, ChangeBundleReceipt)
        elif args.command == "bundle-pull":
            from .federation_broker_contract import ChangeBundlePullRequest
            request_model = ChangeBundlePullRequest(
                schema_version=BROKER_BUNDLE_PULL_REQUEST_SCHEMA,
                subscription_id=args.subscription_id, limit=args.limit, after_cursor=args.after_cursor,
            )
            page = _remote_client(args).request("POST", "/api/v1/change-bundles/pull", request_model, ChangeBundlePage)
            paths = _persist_bundles(page, args.quarantine_dir)
            if bool(args.local_subscription) != bool(args.verification_key_file):
                raise BrokerClientError("--local-subscription and --verification-key-file must be provided together")
            outcomes: list[dict[str, Any]] = []
            if args.local_subscription:
                from .change_feed import import_incremental_change_bundle_to_quarantine, load_subscription

                local_subscription = load_subscription(args.local_subscription)
                if local_subscription.subscription_id != page.subscription_id:
                    raise BrokerClientError("local subscription ID does not match the broker pull")
                key = Path(args.verification_key_file).read_bytes()
                verified_directory = Path(args.quarantine_dir) / "verified"
                _prepare_private_directory(verified_directory)
                for bundle, staged_path in zip(page.bundles, paths):
                    expected_target = verified_directory / f"{bundle.manifest.bundle_id.replace('/', '_')}.json"
                    if expected_target.exists() or expected_target.is_symlink():
                        if expected_target.is_symlink() or not expected_target.is_file():
                            raise BrokerClientError("existing verified quarantine target is not a regular file")
                        try:
                            existing = FederationChangeBundle.model_validate_json(expected_target.read_text(encoding="utf-8"))
                        except (OSError, ValidationError) as exc:
                            raise BrokerClientError("existing verified quarantine target is invalid") from exc
                        if existing.model_dump(mode="json") != bundle.model_dump(mode="json"):
                            raise BrokerClientError("refusing to overwrite a different bundle with the same ID")
                    result = import_incremental_change_bundle_to_quarantine(
                        staged_path,
                        verified_directory,
                        verification_key=key,
                        subscription=local_subscription,
                        key_id=args.key_id or None,
                        policy_plugins_path=args.policy_plugins or None,
                        requester_id=args.requester_id,
                    )
                    outcomes.append(result.model_dump(mode="json"))
            print(json.dumps({
                "subscription_id": page.subscription_id,
                "bundle_count": len(page.bundles),
                "quarantine_files": paths,
                "local_verification": outcomes,
                "next_cursor": page.next_cursor,
                "acknowledged": False,
                "promoted": False,
            }, indent=2))
            return 0
        elif args.command == "bundle-ack":
            if not args.verified_locally:
                raise BrokerClientError("refusing acknowledgement without --verified-locally")
            bundle = _load_json(args.bundle_file, model=FederationChangeBundle)
            from .federation_broker_contract import BundleAcknowledgementRequest
            request_model = BundleAcknowledgementRequest(
                schema_version=BROKER_ACKNOWLEDGEMENT_SCHEMA,
                bundle_id=bundle.manifest.bundle_id, cursor=bundle.manifest.cursor_end,
            )
            result = _remote_client(args).request("POST", "/api/v1/change-bundles/acknowledgements", request_model, BundleAcknowledgementReceipt)
        elif args.command == "key-revoke":
            request_model = SigningKeyRevocationRequest(schema_version=BROKER_KEY_REVOCATION_SCHEMA, reason=args.reason)
            path = "/api/v1/enrollments/{}/keys/{}/revocation".format(
                urllib.parse.quote(args.enrollment_id, safe=""), urllib.parse.quote(args.key_id, safe="")
            )
            result = _remote_client(args).request("POST", path, request_model, RevocationReceipt)
        elif args.command == "key-add":
            public_key_bytes = _read_bounded_file(args.public_key_file, 8192, "public key file", "8 KB")
            try:
                public_key = public_key_bytes.decode("utf-8")
            except UnicodeError as exc:
                raise BrokerClientError("could not read public key file") from exc
            request_model = SigningKeyAddRequest(schema_version=BROKER_SIGNING_KEY_ADD_SCHEMA, key_id=args.key_id, public_key_pem=public_key)
            path = "/api/v1/admin/enrollments/{}/signing-keys".format(urllib.parse.quote(args.enrollment_id, safe=""))
            result = _remote_client(args).request("POST", path, request_model, SigningKeyReceipt)
        elif args.command == "enrollment-revoke":
            from .federation_broker_contract import EnrollmentRevocationRequest
            request_model = EnrollmentRevocationRequest(schema_version=BROKER_ENROLLMENT_REVOCATION_SCHEMA, reason=args.reason)
            path = "/api/v1/enrollments/{}/revocation".format(urllib.parse.quote(args.enrollment_id, safe=""))
            result = _remote_client(args).request("POST", path, request_model, EnrollmentRevocationReceipt)
        else:
            raise BrokerClientError("unsupported command")
        _json_output(result)
        return 0
    except (BrokerClientError, ValidationError, ValueError, OSError) as exc:
        print(f"groundrecall-broker: {exc}", file=sys.stderr)
        return 2


def _persist_bundles(page: ChangeBundlePage, quarantine_dir: str) -> list[str]:
    """Write exact signed bundles atomically to a private local handoff area."""
    directory = Path(quarantine_dir)
    _prepare_private_directory(directory)
    written: list[str] = []
    for bundle in page.bundles:
        serialized = (bundle.model_dump_json(indent=2) + "\n").encode("utf-8")
        if len(serialized) > _MAX_HTTP_BYTES:
            raise BrokerClientError("one pulled bundle exceeds the 4 MB local limit")
        bundle_hash = hashlib.sha256(bundle.manifest.bundle_id.encode("utf-8")).hexdigest()[:16]
        content_hash = hashlib.sha256(serialized).hexdigest()[:16]
        target = directory / f"broker-bundle-{bundle_hash}-{content_hash}.json"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(target, flags, 0o600)
        except FileExistsError:
            existing_info = target.lstat()
            if stat.S_ISLNK(existing_info.st_mode) or not stat.S_ISREG(existing_info.st_mode):
                raise BrokerClientError("existing quarantine target is not a regular file")
            if existing_info.st_mode & 0o077 or (hasattr(os, "getuid") and existing_info.st_uid != os.getuid()):
                raise BrokerClientError("existing quarantine target is not privately owned")
            if target.read_bytes() != serialized:
                raise BrokerClientError("quarantine filename collision; existing file was not changed")
        else:
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(serialized)
                    handle.flush()
                    os.fsync(handle.fileno())
            except Exception:
                try:
                    target.unlink()
                except OSError:
                    pass
                raise
        written.append(str(target))
    return written


def _prepare_private_directory(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink() or not directory.is_dir():
        raise BrokerClientError("quarantine path must be a real directory, not a symlink")
    info = directory.stat()
    if info.st_mode & 0o077:
        raise BrokerClientError("quarantine directory must be private (mode 0700 or stricter)")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise BrokerClientError("quarantine directory must be owned by the current user")


if __name__ == "__main__":
    raise SystemExit(main())
