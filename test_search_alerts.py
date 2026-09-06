import pytest
from unittest.mock import patch
import functions


def test_safety_alerts_requires_authentication():
    with pytest.raises(functions.RecordGuardError):
        functions.get_medication_safety_alerts(
            user=None,
            patient_id="RG00001",
            medicine_name="Aspirin"
        )


@patch("functions._get_user_by_id", return_value={"user_id": 3, "username": "doctor", "role": "doctor", "active": 1})
@patch("functions.can_view_patient")
@patch("functions.search_medicine_with_alerts")
def test_safety_alerts_isolates_patient_data(mock_search, mock_can_view, mock_lookup):
    mock_can_view.return_value = True
    mock_search.return_value = {
        "records": [],
        "alerts": [
            {
                "level": "warning",
                "response_type": "Adverse reaction",
                "message": "Previous reaction recorded."
            }
        ]
    }

    doctor_user = {"user_id": 3, "username": "doctor", "role": "doctor"}
    patient_a = "RG00001"

    alerts = functions.get_medication_safety_alerts(
        user=doctor_user,
        patient_id=patient_a,
        medicine_name="Paracetamol"
    )

    assert isinstance(alerts, list)
    assert len(alerts) == 1
    assert alerts[0]["response_type"] == "Adverse reaction"

    mock_can_view.assert_called_once_with(doctor_user, patient_a)
    mock_search.assert_called_once_with(
        patient_id=patient_a,
        medicine_name="Paracetamol",
        user=doctor_user
    )


@patch("functions._get_user_by_id", side_effect=lambda uid: {"user_id": uid, "username": {1:"owner",2:"admin",3:"doctor"}[uid], "role": {1:"owner",2:"admin",3:"doctor"}[uid], "active": 1})
def test_lifecycle_permissions_match_recordguard_model(mock_lookup):
    owner = {"user_id": 1, "username": "owner", "role": "owner"}
    admin = {"user_id": 2, "username": "admin", "role": "admin"}
    doctor = {"user_id": 3, "username": "doctor", "role": "doctor"}

    assert functions.can_recover_archived_records(owner)
    assert functions.can_recover_archived_records(admin)
    assert not functions.can_recover_archived_records(doctor)

    assert functions.can_recover_admin_deleted_records(owner)
    assert not functions.can_recover_admin_deleted_records(admin)
    assert not functions.can_recover_admin_deleted_records(doctor)

    assert functions.can_permanently_delete(owner)
    assert not functions.can_permanently_delete(admin)
    assert not functions.can_permanently_delete(doctor)


def test_add_medication_record_requires_authorized_user():
    doctor = {"user_id": 3, "username": "doctor", "role": "doctor"}
    with pytest.raises(functions.RecordGuardError):
        functions.add_medication_record(
            user=None,
            patient_id="RG00001",
            medicine_name="Paracetamol",
            response_type="Effective"
        )
