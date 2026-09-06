import pytest
from unittest.mock import patch
import functions

ROLES = {
    "owner": {"view": True, "add": True, "edit": True, "archive": True,
              "recover_archive": True, "admin_delete": True,
              "recover_admin_delete": True, "permanent_delete": True,
              "delete_patient": True, "register": True},
    "admin": {"view": True, "add": True, "edit": True, "archive": True,
              "recover_archive": True, "admin_delete": True,
              "recover_admin_delete": False, "permanent_delete": False,
              "delete_patient": False, "register": True},
    "doctor": {"view": True, "add": True, "edit": True, "archive": True,
                "recover_archive": False, "admin_delete": False,
                "recover_admin_delete": False, "permanent_delete": False,
                "delete_patient": False, "register": True},
    "staff": {"view": True, "add": True, "edit": False, "archive": False,
              "recover_archive": False, "admin_delete": False,
              "recover_admin_delete": False, "permanent_delete": False,
              "delete_patient": False, "register": True},
    "patient": {"view": False, "add": False, "edit": False, "archive": False,
                 "recover_archive": False, "admin_delete": False,
                 "recover_admin_delete": False, "permanent_delete": False,
                 "delete_patient": False, "register": False},
}


ROLE_IDS = {"owner": 1, "admin": 2, "doctor": 3, "staff": 4, "patient": 5}

def user(role):
    return {"user_id": ROLE_IDS[role], "username": role, "role": role}


def verified_user(user_dict):
    return {**user_dict, "active": 1}


@pytest.fixture(autouse=True)
def mock_verified_accounts():
    with patch("functions._get_user_by_id") as mock:
        def lookup(user_id):
            for role, role_id in ROLE_IDS.items():
                if role_id == user_id:
                    return {"user_id": role_id, "username": role, "role": role, "active": 1}
            return None
        mock.side_effect = lookup
        yield mock


def test_role_permission_matrix():
    for role, expected in ROLES.items():
        u = user(role)
        assert functions.can_view_all_records(u) is expected["view"]
        assert functions.can_add_records(u) is expected["add"]
        assert functions.can_edit_records(u) is expected["edit"]
        assert functions.can_archive_records(u) is expected["archive"]
        assert functions.can_recover_archived_records(u) is expected["recover_archive"]
        assert functions.can_admin_delete_records(u) is expected["admin_delete"]
        assert functions.can_recover_admin_deleted_records(u) is expected["recover_admin_delete"]
        assert functions.can_permanently_delete(u) is expected["permanent_delete"]
        assert functions.can_delete_patients(u) is expected["delete_patient"]
        assert functions.can_register_patients(u) is expected["register"]


def test_permission_helpers_require_authentication():
    helpers = [
        functions.can_view_all_records,
        functions.can_add_records,
        functions.can_edit_records,
        functions.can_archive_records,
        functions.can_recover_archived_records,
        functions.can_admin_delete_records,
        functions.can_recover_admin_deleted_records,
        functions.can_permanently_delete,
        functions.can_delete_patients,
        functions.is_owner,
        functions.can_register_patients,
    ]
    for helper in helpers:
        with pytest.raises(functions.RecordGuardError):
            helper(None)


def test_role_checks_are_case_insensitive_and_trimmed():
    admin = {"user_id": 2, "username": "admin", "role": "  ADMIN "}
    assert functions.can_recover_archived_records(admin)
    assert functions.can_admin_delete_records(admin)
    assert not functions.can_permanently_delete(admin)


def test_patient_can_only_view_linked_patient():
    patient = {"user_id": 5, "username": "patient", "role": "patient", "patient_id": "RG00001"}
    assert functions.can_view_patient(patient, "RG00001")
    assert functions.can_view_patient(patient, "rg00001")
    assert not functions.can_view_patient(patient, "RG00002")


def test_patient_without_linked_patient_cannot_view_any_patient():
    patient = {"user_id": 5, "username": "patient", "role": "patient"}
    assert not functions.can_view_patient(patient, "RG00001")


def test_direct_lifecycle_calls_require_authorization():
    calls = [
        (functions.edit_medication_record,
         dict(user=user("staff"), record_id=1, medicine_name="X", response_type="Effective")),
        (functions.archive_medication_record,
         dict(user=user("staff"), record_id=1)),
        (functions.recover_archived_medication_record,
         dict(user=user("doctor"), record_id=1)),
        (functions.admin_delete_medication_record,
         dict(user=user("doctor"), record_id=1, password="x")),
        (functions.recover_admin_deleted_medication_record,
         dict(user=user("admin"), record_id=1)),
        (functions.permanently_delete_medication_record,
         dict(user=user("admin"), record_id=1, password="x")),
        (functions.permanently_delete_patient,
         dict(user=user("admin"), patient_id="RG00001", password="x")),
    ]
    for fn, kwargs in calls:
        with pytest.raises(functions.RecordGuardError):
            fn(**kwargs)


def test_forged_or_stale_session_is_rejected():
    with patch("functions._get_user_by_id", return_value=None):
        with pytest.raises(functions.RecordGuardError):
            functions.can_permanently_delete({
                "user_id": 999,
                "username": "attacker",
                "role": "owner",
            })


def test_role_tampering_is_rejected():
    with patch("functions._get_user_by_id", return_value={
        "user_id": 2,
        "username": "admin",
        "role": "admin",
        "active": 1,
    }):
        with pytest.raises(functions.RecordGuardError):
            functions.can_permanently_delete({
                "user_id": 2,
                "username": "admin",
                "role": "owner",
            })
