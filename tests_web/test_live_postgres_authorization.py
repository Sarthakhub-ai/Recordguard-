"""Live PostgreSQL authorization parity tests.

These tests are intentionally skipped without RECORDGUARD_DATABASE_URL.
In CI, a PostgreSQL 16 service is supplied and the same role/scope
assertions run against the real repository.
"""

import os
import uuid

import pytest


DSN = os.getenv("RECORDGUARD_DATABASE_URL")

if DSN:
    psycopg = pytest.importorskip("psycopg")
else:
    psycopg = None


pytestmark = pytest.mark.skipif(
    not DSN,
    reason="Set RECORDGUARD_DATABASE_URL for live PostgreSQL authorization tests",
)


def _setup():
    from database import hash_password
    from shared.domain import Actor
    from backend.repositories.postgres import PostgreSQLRepository

    org = str(uuid.uuid4())

    owner_id = str(uuid.uuid4())
    doctor_id = str(uuid.uuid4())
    patient_user_id = str(uuid.uuid4())
    common_id = str(uuid.uuid4())

    patient_a = str(uuid.uuid4())
    patient_b = str(uuid.uuid4())

    with psycopg.connect(DSN) as c:
        # --------------------------------------------------------------
        # 1. Create the organization.
        # --------------------------------------------------------------
        c.execute(
            """
            INSERT INTO organizations(
                organization_id,
                organization_code,
                name
            )
            VALUES(%s, %s, %s)
            """,
            (
                org,
                "TEST-" + org[:8],
                "Live Authorization Test",
            ),
        )

        # --------------------------------------------------------------
        # 2. Create users with patient_id initially NULL.
        #
        # The database has a circular relationship:
        #
        # patients.registered_by -> users.user_id
        # users.patient_id       -> patients.patient_id
        #
        # Therefore users must initially be created without patient_id.
        # --------------------------------------------------------------
        users = [
            (owner_id, "owner-live", "owner"),
            (doctor_id, "doctor-live", "doctor"),
            (patient_user_id, "patient-live", "patient"),
            (common_id, "common-live", "user"),
        ]

        for uid, username, role in users:
            c.execute(
                """
                INSERT INTO users(
                    user_id,
                    organization_id,
                    username,
                    password_hash,
                    role,
                    patient_id,
                    full_name,
                    active
                )
                VALUES(
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    NULL,
                    %s,
                    TRUE
                )
                """,
                (
                    uid,
                    org,
                    username,
                    hash_password("LivePass123"),
                    role,
                    username,
                ),
            )

        # --------------------------------------------------------------
        # 3. Create Patient A.
        #
        # owner_id now exists in users, so registered_by is valid.
        # --------------------------------------------------------------
        c.execute(
            """
            INSERT INTO patients(
                patient_id,
                organization_id,
                public_patient_id,
                name,
                age,
                sex,
                registered_by
            )
            VALUES(
                %s,
                %s,
                %s,
                %s,
                30,
                'F',
                %s
            )
            """,
            (
                patient_a,
                org,
                "RGLIVE01",
                "Live Patient A",
                owner_id,
            ),
        )

        # --------------------------------------------------------------
        # 4. Create Patient B.
        # --------------------------------------------------------------
        c.execute(
            """
            INSERT INTO patients(
                patient_id,
                organization_id,
                public_patient_id,
                name,
                age,
                sex,
                registered_by
            )
            VALUES(
                %s,
                %s,
                %s,
                %s,
                31,
                'M',
                %s
            )
            """,
            (
                patient_b,
                org,
                "RGLIVE02",
                "Live Patient B",
                owner_id,
            ),
        )

        # --------------------------------------------------------------
        # 5. Link the patient user to Patient A.
        #
        # Patient A now exists, so the users.patient_id FK is valid.
        # --------------------------------------------------------------
        c.execute(
            """
            UPDATE users
            SET patient_id = %s
            WHERE user_id = %s
            """,
            (
                patient_a,
                patient_user_id,
            ),
        )

    return (
        org,
        owner_id,
        doctor_id,
        patient_user_id,
        common_id,
        patient_a,
        patient_b,
        PostgreSQLRepository(DSN),
        Actor,
    )


def _cleanup(org):
    with psycopg.connect(DSN) as c:
        # --------------------------------------------------------------
        # Remove patients first.
        #
        # patients.registered_by references users.user_id, so patients
        # must be removed before the users they reference.
        # --------------------------------------------------------------
        c.execute(
            """
            DELETE FROM patients
            WHERE organization_id = %s
            """,
            (org,),
        )

        # --------------------------------------------------------------
        # Remove users next.
        #
        # users.organization_id references organizations.organization_id.
        # --------------------------------------------------------------
        c.execute(
            """
            DELETE FROM users
            WHERE organization_id = %s
            """,
            (org,),
        )

        # --------------------------------------------------------------
        # Finally remove the organization.
        # --------------------------------------------------------------
        c.execute(
            """
            DELETE FROM organizations
            WHERE organization_id = %s
            """,
            (org,),
        )


def test_live_postgres_role_scope_parity():
    (
        org,
        owner_id,
        doctor_id,
        patient_user_id,
        common_id,
        patient_a,
        patient_b,
        repo,
        Actor,
    ) = _setup()

    from shared.domain import Role

    try:
        # --------------------------------------------------------------
        # Create actors.
        # --------------------------------------------------------------
        owner = Actor(
            owner_id,
            Role.OWNER,
            org,
        )

        doctor = Actor(
            doctor_id,
            Role.DOCTOR,
            org,
        )

        patient = Actor(
            patient_user_id,
            Role.PATIENT,
            org,
        )

        common = Actor(
            common_id,
            Role.COMMON_USER,
            org,
        )

        # --------------------------------------------------------------
        # Owner can see all patients in the organization.
        # --------------------------------------------------------------
        assert len(repo.list_patients(owner)) == 2

        # --------------------------------------------------------------
        # Doctor can see all patients in the organization.
        # --------------------------------------------------------------
        assert len(repo.list_patients(doctor)) == 2

        # --------------------------------------------------------------
        # Patient can only see their own patient.
        # --------------------------------------------------------------
        assert len(repo.list_patients(patient)) == 1

        # --------------------------------------------------------------
        # Common user cannot list patients.
        # --------------------------------------------------------------
        with pytest.raises(PermissionError):
            repo.list_patients(common)

        # --------------------------------------------------------------
        # Patient can access their own patient record.
        # --------------------------------------------------------------
        assert (
            repo.get_patient(
                patient,
                "RGLIVE01",
            )["public_patient_id"]
            == "RGLIVE01"
        )

        # --------------------------------------------------------------
        # Patient cannot access another patient's record.
        # --------------------------------------------------------------
        with pytest.raises(PermissionError):
            repo.get_patient(
                patient,
                "RGLIVE02",
            )

        # --------------------------------------------------------------
        # Common user cannot access patient records.
        # --------------------------------------------------------------
        with pytest.raises(PermissionError):
            repo.get_patient(
                common,
                "RGLIVE01",
            )

        # --------------------------------------------------------------
        # Common user cannot access medication records.
        # --------------------------------------------------------------
        with pytest.raises(PermissionError):
            repo.list_medications(
                common,
                "RGLIVE01",
            )

    finally:
        # Always clean up the test organization and its dependent data.
        _cleanup(org)