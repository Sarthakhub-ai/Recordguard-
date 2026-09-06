"""Shared RecordGuard domain rules.

Framework-agnostic rules shared by Desktop, Web and Mobile.
This module intentionally does not import Tkinter or any database implementation.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Optional


class Role(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    DOCTOR = "doctor"
    STAFF = "staff"
    PATIENT = "patient"
    COMMON_USER = "user"


class Lifecycle(str, Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    ADMIN_DELETED = "ADMIN_DELETED"


class DomainError(ValueError):
    """Expected domain-rule violation."""


class AuthorizationError(DomainError):
    """Typed authorization failure for deterministic API 403 responses."""


@dataclass(frozen=True)
class Actor:
    user_id: str
    role: Role
    organization_id: str

    @classmethod
    def from_mapping(cls, user: Mapping) -> "Actor":
        try:
            return cls(
                user_id=str(user["user_id"]),
                role=Role(str(user["role"]).strip().lower()),
                organization_id=str(
                    user.get("organization_id") or "DEFAULT"
                ).strip(),
            )
        except (KeyError, ValueError) as exc:
            raise DomainError("Invalid authenticated actor.") from exc


def same_organization(actor: Actor, organization_id: Optional[str]) -> bool:
    return actor.organization_id == str(
        organization_id or "DEFAULT"
    ).strip()


def require_organization(
    actor: Actor, resource_organization_id: Optional[str]
) -> None:
    if not same_organization(actor, resource_organization_id):
        raise DomainError("Cross-organization access is not permitted.")


def can_view_records(role: Role) -> bool:
    return role in {
        Role.OWNER,
        Role.ADMIN,
        Role.DOCTOR,
        Role.STAFF,
        Role.PATIENT,
    }


def can_add_records(role: Role) -> bool:
    return role in {
        Role.OWNER,
        Role.ADMIN,
        Role.DOCTOR,
        Role.STAFF,
    }


def can_edit_records(role: Role) -> bool:
    return role in {
        Role.OWNER,
        Role.ADMIN,
        Role.DOCTOR,
        Role.STAFF,
    }


def can_archive_records(role: Role) -> bool:
    return role in {
        Role.OWNER,
        Role.ADMIN,
        Role.DOCTOR,
        Role.STAFF,
    }


def can_recover_archived(role: Role) -> bool:
    return role in {Role.OWNER, Role.ADMIN}


def can_admin_delete(role: Role) -> bool:
    return role in {Role.OWNER, Role.ADMIN}


def can_recover_admin_deleted(role: Role) -> bool:
    return role is Role.OWNER


def can_permanently_destroy(role: Role) -> bool:
    return role is Role.OWNER


def require_lifecycle_transition(
    current: Lifecycle,
    target: Lifecycle,
    *,
    role: Role,
) -> None:
    """Validate a normal lifecycle transition.

    The staged RecordGuard lifecycle is:

        ACTIVE -> ARCHIVED -> ADMIN_DELETED

    Recovery and permanent destruction are deliberately handled by their
    dedicated functions below so that their stricter role/password rules
    cannot be bypassed through this generic transition function.
    """
    allowed = {
        Lifecycle.ACTIVE: {Lifecycle.ARCHIVED},
        Lifecycle.ARCHIVED: {Lifecycle.ADMIN_DELETED},
        Lifecycle.ADMIN_DELETED: set(),
    }

    if target not in allowed[current]:
        raise DomainError(
            f"Invalid lifecycle transition: "
            f"{current.value} -> {target.value}."
        )

    if target is Lifecycle.ARCHIVED and not can_archive_records(role):
        raise DomainError("You are not authorized to archive this record.")

    if target is Lifecycle.ADMIN_DELETED and not can_admin_delete(role):
        raise DomainError(
            "Only an Owner or Admin can admin-delete records."
        )


def require_admin_delete(role: Role, current: Lifecycle) -> None:
    if not can_admin_delete(role):
        raise DomainError(
            "Only an Owner or Admin can admin-delete records."
        )

    if current is not Lifecycle.ARCHIVED:
        raise DomainError(
            "A record must be archived before Admin deletion."
        )


def require_owner_recovery(role: Role, current: Lifecycle) -> None:
    if not can_recover_admin_deleted(role):
        raise DomainError(
            "Only the Owner can recover Admin-deleted records."
        )

    if current is not Lifecycle.ADMIN_DELETED:
        raise DomainError(
            "Only Admin-deleted records can be recovered by the Owner."
        )


def require_permanent_destroy(
    role: Role,
    current: Lifecycle,
    *,
    password_verified: bool,
) -> None:
    if not can_permanently_destroy(role):
        raise DomainError(
            "Only the Owner can permanently destroy records."
        )

    if current is not Lifecycle.ADMIN_DELETED:
        raise DomainError(
            "Permanent destruction requires an Admin-deleted record."
        )

    if not password_verified:
        raise DomainError("Current password verification is required.")


def require_explicit_share_fields(
    fields: Mapping[str, object],
    allowed_fields: set[str],
) -> dict:
    """Return only explicitly requested fields from an allowlist.

    Unknown fields are rejected rather than silently ignored, preventing
    callers from accidentally sharing data outside the approved scope.
    """
    unknown = set(fields) - allowed_fields

    if unknown:
        raise DomainError(
            "Requested shared fields are not permitted."
        )

    return {
        key: fields[key]
        for key in allowed_fields
        if key in fields
    }
