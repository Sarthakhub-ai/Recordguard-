
"""
validation.py
--------------
Input validation helpers for RecordGuard.

Every validation function returns None when the input is valid,
otherwise it returns a short human-readable error message.

Validation is kept separate from the UI and database layers so the
same rules are applied consistently throughout the application.
"""


# ======================================================================
# CONSTANTS
# ======================================================================

VALID_SEX_VALUES = {
    "M",
    "F",
    "Other",
}

VALID_RESPONSE_TYPES = {
    "Effective",
    "Ineffective",
    "Allergy",
    "Adverse reaction",
    "Unknown",
}

VALID_SEVERITY_VALUES = {
    "Mild",
    "Moderate",
    "Severe",
    "",
}


# ======================================================================
# PATIENT VALIDATION
# ======================================================================

def validate_name(name: str):
    """Validate a patient's name."""

    if name is None or not str(name).strip():

        return "Name is required."

    clean_name = str(name).strip()

    if len(clean_name) < 2:

        return "Name must be at least 2 characters long."

    if len(clean_name) > 100:

        return "Name is too long (max 100 characters)."

    return None


def validate_age(age_str: str):
    """Validate patient age."""

    if age_str is None or not str(age_str).strip():

        return "Age is required."

    try:

        age = int(str(age_str).strip())

    except (ValueError, TypeError):

        return "Age must be a whole number."

    if age < 0 or age > 130:

        return "Age must be between 0 and 130."

    return None


def validate_sex(sex: str):
    """Validate patient sex."""

    if sex is None or not str(sex).strip():

        return "Sex is required."

    clean_sex = str(sex).strip()

    if clean_sex not in VALID_SEX_VALUES:

        return (
            "Sex must be one of: "
            + ", ".join(sorted(VALID_SEX_VALUES))
            + "."
        )

    return None


def validate_patient_id_format(patient_id: str):
    """
    Validate a manually entered patient ID.

    Registration does not use this function because patient IDs
    are generated automatically.
    """

    if patient_id is None or not str(patient_id).strip():

        return "Patient ID is required."

    clean_id = str(patient_id).strip().upper()

    if not clean_id.startswith("RG"):

        return (
            "Patient ID must start with 'RG' "
            "(e.g. RG00001)."
        )

    return None

def validate_patient_registration(
    name: str,
    age_str: str,
    sex: str,
    date_of_birth: str = "",
    permanent_address: str = "",
    current_address: str = "",
    phone_number: str = "",
    blood_group: str = ""
) -> list:
    """Run all patient-registration validations using the shared validators."""
    from datetime import date, datetime
    import re

    errors = []

    for validator, value in (
        (validate_name, name),
        (validate_age, age_str),
        (validate_sex, sex),
    ):
        error = validator(value)
        if error:
            errors.append(error)

    clean_dob = str(date_of_birth or "").strip()
    if clean_dob:
        try:
            dob = datetime.strptime(clean_dob, "%Y-%m-%d").date()
            if dob > date.today():
                errors.append("Date of Birth cannot be in the future.")
        except ValueError:
            errors.append("Date of Birth must be a valid date in YYYY-MM-DD format.")

    clean_phone = str(phone_number or "").strip()
    if clean_phone:
        # Allow common international formatting, but reject letters and other symbols.
        if not re.fullmatch(r"\+?[0-9][0-9 .()-]{5,18}[0-9]", clean_phone):
            errors.append("Phone number may contain only digits, spaces, hyphens, parentheses, and an optional leading +.")
        else:
            digits = re.sub(r"\D", "", clean_phone)
            if not 7 <= len(digits) <= 15:
                errors.append("Phone number must contain between 7 and 15 digits.")

    clean_bg = str(blood_group or "").strip().upper()
    if clean_bg not in {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-", ""}:
        errors.append("Invalid blood group. Must be standard ABO format (e.g., O+, AB-).")

    for label, address in (("Permanent Address", permanent_address), ("Current Address", current_address)):
        if len(str(address or "").strip()) > 500:
            errors.append(f"{label} is too long (max 500 characters).")

    return errors

# ======================================================================
# MEDICATION VALIDATION
# ======================================================================

def validate_medicine_name(medicine_name: str):
    """Validate a medicine name."""

    if (
        medicine_name is None
        or not str(medicine_name).strip()
    ):

        return "Medicine name is required."

    clean_name = str(medicine_name).strip()

    if len(clean_name) > 150:

        return (
            "Medicine name is too long "
            "(max 150 characters)."
        )

    return None


def validate_response_type(response_type: str):
    """Validate the recorded medication response type."""

    if (
        response_type is None
        or not str(response_type).strip()
    ):

        return "Response type is required."

    clean_response = str(response_type).strip()

    if clean_response not in VALID_RESPONSE_TYPES:

        return (
            "Response type must be one of: "
            + ", ".join(sorted(VALID_RESPONSE_TYPES))
            + "."
        )

    return None


def validate_severity(
    severity: str,
    response_type: str
):
    """
    Validate medication-reaction severity.

    Severity is meaningful mainly for Allergy and Adverse reaction
    records. It may be left blank for other response types.

    If a value is supplied, it must be Mild, Moderate or Severe.
    """

    if severity is None:

        severity = ""

    clean_severity = str(severity).strip()

    if (
        clean_severity
        and clean_severity not in {
            "Mild",
            "Moderate",
            "Severe",
        }
    ):

        return (
            "Severity must be one of: "
            "Mild, Moderate, Severe "
            "(or left blank)."
        )

    return None


def validate_medication_record(
    medicine_name: str,
    response_type: str,
    severity: str
):
    """
    Run all medication-record validations.

    Returns:
        list: Empty list means the input is valid.
    """

    errors = []

    checks = (
        validate_medicine_name(medicine_name),
        validate_response_type(response_type),
        validate_severity(
            severity,
            response_type
        ),
    )

    for error in checks:

        if error:

            errors.append(error)

    return errors