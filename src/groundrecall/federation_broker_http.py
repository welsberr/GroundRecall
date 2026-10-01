"""Bounded HTTP dispatcher for the persistent federation broker service.

Authentication is supplied by the hosting adapter as an authenticated
participant. Request JSON can never set that identity. A deployment should
derive the participant and roles from its bearer-token middleware.
"""
from __future__ import annotations

import json
import re
from http import HTTPStatus
from typing import Any, TypeVar
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel, ValidationError

from .federation_broker import (
    BrokerConflictError,
    BrokerNotFoundError,
    FederationBrokerService,
)
from .federation_broker_contract import (
    AuthenticatedParticipant,
    BrokerAuthorizationError,
    BrokerEnrollmentRequest,
    BundleAcknowledgementRequest,
    CatalogDiscoveryRequest,
    ChangeBundlePullRequest,
    EnrollmentApprovalRequest,
    EnrollmentRevocationRequest,
    SigningKeyAddRequest,
    SigningKeyRevocationRequest,
    SubscriptionCreateRequest,
)

_M = TypeVar("_M", bound=BaseModel)
_ENROLLMENT_APPROVAL = re.compile(r"^/api/v1/admin/enrollments/([^/]+)/approval$")
_SIGNING_KEY_ADD = re.compile(r"^/api/v1/admin/enrollments/([^/]+)/signing-keys$")
_KEY_REVOCATION = re.compile(r"^/api/v1/enrollments/([^/]+)/keys/([^/]+)/revocation$")
_ENROLLMENT_REVOCATION = re.compile(r"^/api/v1/enrollments/([^/]+)/revocation$")
_ADMIN_ENROLLMENT_REVOCATION = re.compile(r"^/api/v1/admin/enrollments/([^/]+)/revocation$")


class FederationBrokerHTTPDispatcher:
    """Small framework-neutral dispatcher with body and response limits."""

    def __init__(
        self,
        service: FederationBrokerService,
        *,
        max_body_bytes: int = 4_000_000,
        max_response_bytes: int = 4_000_000,
    ):
        if max_body_bytes < 1 or max_response_bytes < 1:
            raise ValueError("HTTP body limits must be positive")
        self.service = service
        self.max_body_bytes = max_body_bytes
        self.max_response_bytes = max_response_bytes

    @staticmethod
    def _encode(payload: Any) -> bytes:
        return (json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")

    def _response(self, status: int, payload: Any) -> tuple[int, bytes]:
        body = self._encode(payload)
        if len(body) > self.max_response_bytes:
            return HTTPStatus.BAD_GATEWAY, self._encode({"error": "response_too_large"})
        return int(status), body

    def _body(self, body: bytes, model: type[_M]) -> _M:
        if len(body) > self.max_body_bytes:
            raise OverflowError
        value = json.loads(body)
        if not isinstance(value, dict):
            raise ValueError("request must be a JSON object")
        return model.model_validate(value)

    @staticmethod
    def _participant_required(participant: AuthenticatedParticipant | None) -> AuthenticatedParticipant:
        if participant is None:
            raise PermissionError
        return participant

    @staticmethod
    def _admin_required(participant: AuthenticatedParticipant | None) -> AuthenticatedParticipant:
        if participant is None:
            raise PermissionError
        if "broker_admin" not in participant.roles:
            raise BrokerAuthorizationError("admin role required")
        return participant

    def dispatch(
        self,
        method: str,
        path: str,
        body: bytes = b"",
        *,
        participant: AuthenticatedParticipant | None = None,
    ) -> tuple[int, bytes]:
        """Dispatch one request, using only caller identity from middleware."""
        route = urlsplit(path).path
        method = method.upper()
        try:
            if method == "GET" and route == "/api/v1/broker":
                if body:
                    return self._response(HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
                result = self.service.capabilities()
            elif method == "POST" and route == "/api/v1/enrollment-requests":
                principal = self._participant_required(participant)
                result = self.service.request_enrollment(principal, self._body(body, BrokerEnrollmentRequest))
            elif method == "POST" and (match := _ENROLLMENT_APPROVAL.fullmatch(route)):
                principal = self._admin_required(participant)
                result = self.service.approve_enrollment(
                    principal, unquote(match.group(1)), self._body(body, EnrollmentApprovalRequest)
                )
            elif method == "POST" and (match := _SIGNING_KEY_ADD.fullmatch(route)):
                principal = self._admin_required(participant)
                result = self.service.add_signing_key(
                    principal, unquote(match.group(1)), self._body(body, SigningKeyAddRequest)
                )
            elif method == "POST" and route == "/api/v1/catalogs":
                principal = self._participant_required(participant)
                from .federation_broker_contract import CatalogSubmissionRequest
                request = self._body(body, CatalogSubmissionRequest)
                result = self.service.publish_catalog(principal, request.catalog)
            elif method == "POST" and route == "/api/v1/catalogs/discover":
                principal = self._participant_required(participant)
                result = self.service.discover_catalogs(principal, self._body(body, CatalogDiscoveryRequest))
            elif method == "POST" and route == "/api/v1/subscriptions":
                principal = self._participant_required(participant)
                result = self.service.create_subscription(principal, self._body(body, SubscriptionCreateRequest))
            elif method == "POST" and route == "/api/v1/change-bundles":
                principal = self._participant_required(participant)
                from .federation_broker_contract import ChangeBundleSubmissionRequest
                request = self._body(body, ChangeBundleSubmissionRequest)
                result = self.service.submit_bundle(principal, request.bundle)
            elif method == "POST" and route == "/api/v1/change-bundles/pull":
                principal = self._participant_required(participant)
                result = self.service.pull_bundles(principal, self._body(body, ChangeBundlePullRequest))
            elif method == "POST" and route == "/api/v1/change-bundles/acknowledgements":
                principal = self._participant_required(participant)
                result = self.service.acknowledge_bundle(principal, self._body(body, BundleAcknowledgementRequest))
            elif method == "POST" and (match := _KEY_REVOCATION.fullmatch(route)):
                principal = self._participant_required(participant)
                result = self.service.revoke_key(
                    principal, unquote(match.group(1)), unquote(match.group(2)),
                    self._body(body, SigningKeyRevocationRequest),
                )
            elif method == "POST" and (match := _ENROLLMENT_REVOCATION.fullmatch(route)):
                principal = self._participant_required(participant)
                result = self.service.revoke_enrollment(
                    principal, unquote(match.group(1)), self._body(body, EnrollmentRevocationRequest)
                )
            elif method == "POST" and (match := _ADMIN_ENROLLMENT_REVOCATION.fullmatch(route)):
                principal = self._admin_required(participant)
                result = self.service.revoke_enrollment(
                    principal, unquote(match.group(1)), self._body(body, EnrollmentRevocationRequest),
                    administrator=True,
                )
            else:
                return self._response(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return self._response(HTTPStatus.OK, result.model_dump(mode="json"))
        except PermissionError:
            return self._response(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
        except OverflowError:
            return self._response(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "request_too_large"})
        except (json.JSONDecodeError, UnicodeDecodeError, ValidationError, TypeError):
            return self._response(HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
        except BrokerNotFoundError:
            return self._response(HTTPStatus.NOT_FOUND, {"error": "not_found"})
        except BrokerAuthorizationError:
            return self._response(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
        except BrokerConflictError:
            return self._response(HTTPStatus.CONFLICT, {"error": "conflict"})
        except ValueError:
            return self._response(HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})


__all__ = ["FederationBrokerHTTPDispatcher"]
