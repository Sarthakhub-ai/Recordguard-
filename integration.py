"""Lightweight EHR interoperability adapter for the RecordGuard prototype.

The adapter intentionally uses a small FHIR-inspired representation so the
prototype can demonstrate integration without claiming a production FHIR
implementation or requiring a real hospital EHR.
"""

from datetime import datetime


def patient_to_bundle(patient, records, encounters=None, prescriptions=None, attachments=None):
    patient_id = patient.get("patient_id")
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "meta": {"source": "RecordGuard", "generatedAt": datetime.now().isoformat(timespec="seconds")},
        "entry": [
            {"resource": {
                "resourceType": "Patient",
                "id": patient_id,
                "name": [{"text": patient.get("name", "")}],
                "birthDate": patient.get("date_of_birth") or None,
                "telecom": [{"system": "phone", "value": patient.get("phone_number")}] if patient.get("phone_number") else [],
            }}
        ],
    }
    for record in records:
        bundle["entry"].append({"resource": {
            "resourceType": "MedicationStatement",
            "id": str(record.get("record_id")),
            "subject": {"reference": f"Patient/{patient_id}"},
            "medicationCodeableConcept": {"text": record.get("medicine_name")},
            "status": "active" if not record.get("is_archived") else "entered-in-error",
            "note": [{"text": record.get("notes")}] if record.get("notes") else [],
            "extension": [
                {"url": "recordguard-response-type", "valueString": record.get("response_type") or "Unknown"},
                {"url": "recordguard-reaction", "valueString": record.get("reaction")} if record.get("reaction") else {},
            ],
        }})
    for encounter in encounters or []:
        bundle["entry"].append({"resource": {
            "resourceType": "Encounter", "id": str(encounter.get("encounter_id")),
            "subject": {"reference": f"Patient/{patient_id}"},
            "period": {"start": encounter.get("visit_date")},
            "type": [{"text": encounter.get("visit_type")}] if encounter.get("visit_type") else [],
            "reasonCode": [{"text": encounter.get("chief_complaint")}] if encounter.get("chief_complaint") else [],
            "diagnosis": [{"condition": {"text": encounter.get("diagnoses")}}] if encounter.get("diagnoses") else [],
            "note": [{"text": encounter.get("visit_notes")}] if encounter.get("visit_notes") else [],
        }})
    for rx in prescriptions or []:
        bundle["entry"].append({"resource": {
            "resourceType": "MedicationRequest", "id": str(rx.get("prescription_id")),
            "subject": {"reference": f"Patient/{patient_id}"},
            "medicationCodeableConcept": {"text": rx.get("medicine_name")},
            "dosageInstruction": [{"text": " | ".join(x for x in [rx.get("dosage"),rx.get("frequency"),rx.get("duration"),rx.get("instructions")] if x)}],
        }})
    for att in attachments or []:
        bundle["entry"].append({"resource": {
            "resourceType": "DocumentReference", "id": str(att.get("attachment_id")),
            "subject": {"reference": f"Patient/{patient_id}"},
            "content": [{"attachment": {"title": att.get("original_name"), "contentType": att.get("mime_type")}}],
        }})
    return bundle
