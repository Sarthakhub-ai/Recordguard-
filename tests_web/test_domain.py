from shared.domain import (
    Actor, DomainError, Lifecycle, Role, can_permanently_destroy,
    require_admin_delete, require_organization, require_permanent_destroy,
)


def test_cross_org_is_denied():
    actor = Actor("1", Role.ADMIN, "ORG-A")
    try:
        require_organization(actor, "ORG-B")
        assert False, "cross-organization access must be denied"
    except DomainError:
        pass


def test_permanent_destroy_requires_admin_deleted_and_password():
    assert can_permanently_destroy(Role.OWNER)
    for lifecycle in (Lifecycle.ACTIVE, Lifecycle.ARCHIVED):
        try:
            require_permanent_destroy(Role.OWNER, lifecycle, password_verified=True)
            assert False
        except DomainError:
            pass
    try:
        require_permanent_destroy(Role.OWNER, Lifecycle.ADMIN_DELETED, password_verified=False)
        assert False
    except DomainError:
        pass
    require_permanent_destroy(Role.OWNER, Lifecycle.ADMIN_DELETED, password_verified=True)


def test_admin_delete_requires_archived():
    for lifecycle in (Lifecycle.ACTIVE, Lifecycle.ADMIN_DELETED):
        try:
            require_admin_delete(Role.ADMIN, lifecycle)
            assert False
        except DomainError:
            pass
    require_admin_delete(Role.ADMIN, Lifecycle.ARCHIVED)
