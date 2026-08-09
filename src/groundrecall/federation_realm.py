"""Realm and audience contracts for low-friction GroundRecall federation."""
from __future__ import annotations

from typing import Literal
from pathlib import Path

from pydantic import BaseModel, Field


RealmAudience = Literal["device_local", "principal", "project", "team", "public"]


class FederationRealm(BaseModel):
    schema_version: str = "groundrecall.federation_realm.v1"
    realm_id: str
    audience: RealmAudience
    principal_id: str = ""
    scope_ids: list[str] = Field(default_factory=list)
    trusted_instance_ids: list[str] = Field(default_factory=list)
    maximum_release_level: str = "private"
    allowed_restriction_markers: list[str] = Field(default_factory=list)
    auto_accept: bool = False


class FederationDevice(BaseModel):
    schema_version: str = "groundrecall.federation_device.v1"
    principal_id: str
    instance_id: str
    key_id: str
    enrolled_at: str = ""
    active: bool = True


def event_matches_realm(
    *,
    realm: FederationRealm,
    audience: str,
    event_realm_id: str,
    event_scope_id: str,
    event_origin_instance_id: str = "",
) -> bool:
    """Return whether an event is explicitly addressed to a realm."""
    if not audience or not event_realm_id or audience != realm.audience:
        return False
    if event_realm_id != realm.realm_id:
        return False
    if realm.scope_ids and event_scope_id not in realm.scope_ids:
        return False
    if realm.trusted_instance_ids and event_origin_instance_id not in realm.trusted_instance_ids:
        return False
    return True


def save_realm(path: str | Path, realm: FederationRealm) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(realm.model_dump_json(indent=2) + "\n", encoding="utf-8")


def load_realm(path: str | Path) -> FederationRealm:
    return FederationRealm.model_validate_json(Path(path).read_text(encoding="utf-8"))


def save_device(path: str | Path, device: FederationDevice) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(device.model_dump_json(indent=2) + "\n", encoding="utf-8")


def load_device(path: str | Path) -> FederationDevice:
    return FederationDevice.model_validate_json(Path(path).read_text(encoding="utf-8"))
