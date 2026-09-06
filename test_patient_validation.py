import pytest
import functions
from unittest.mock import patch
from validation import validate_patient_registration


def test_registration_validation_uses_shared_rules():
    errors = validate_patient_registration(
        name="",
        age_str="not-a-number",
        sex="Invalid",
        date_of_birth="2026-99-99",
        phone_number="abc1234567890",
        blood_group="XYZ",
    )
    assert any("Name is required" in e for e in errors)
    assert any("Age must be a whole number" in e for e in errors)
    assert any("Sex must be one of" in e for e in errors)
    assert any("valid date" in e for e in errors)
    assert any("Phone number" in e for e in errors)
    assert any("blood group" in e for e in errors)


def test_registration_rejects_future_dob():
    errors = validate_patient_registration(
        "Test Patient", "20", "M", date_of_birth="2999-01-01"
    )
    assert any("future" in e.lower() for e in errors)


def test_registration_rejects_letters_in_phone():
    errors = validate_patient_registration(
        "Test Patient", "20", "M", phone_number="abc9876543210"
    )
    assert any("Phone number" in e for e in errors)


def test_registration_requires_authenticated_authorized_user():
    with pytest.raises(functions.RecordGuardError):
        functions.register_patient(
            user=None,
            name="Test Patient",
            age_str="20",
            sex="M",
        )


@patch("functions._get_user_by_id", side_effect=lambda uid: {"user_id": uid, "username": str(uid), "role": str(uid), "active": 1})
def test_register_permission_model(mock_lookup):
    for role in ("owner", "admin", "doctor", "staff"):
        u = {"user_id": role, "username": role, "role": role}
        mock_lookup.side_effect = lambda uid: {"user_id": uid, "username": uid, "role": uid, "active": 1}
        assert functions.can_register_patients(u)
    patient = {"user_id": "patient", "username": "patient", "role": "patient"}
    assert not functions.can_register_patients(patient)


def test_password_hash_rejects_weak_password():
    with pytest.raises(ValueError):
        functions.hash_password("short")
