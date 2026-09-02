from typing import Optional, Union
"""Stable API contracts shared by API clients and tests."""
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=512)
    client: Optional[str] = Field(default="api", max_length=20)


class LoginResponse(BaseModel):
    # API clients receive the bearer token; browser clients use the HttpOnly cookie.
    access_token: Optional[str] = None
    token_type: str = "bearer"
    user: dict


class OwnerSetupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=8, max_length=512)
    full_name: str = Field(min_length=1, max_length=200)


class PatientCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    age: int = Field(ge=0, le=150)
    sex: str = Field(min_length=1, max_length=50)
    date_of_birth: Optional[str] = None
    permanent_address: Optional[str] = None
    current_address: Optional[str] = None
    phone_number: Optional[str] = None
    blood_group: Optional[str] = None


class MedicationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: str = Field(min_length=1, max_length=50)
    medicine_name: str = Field(min_length=1, max_length=200)
    response_type: str = Field(min_length=1, max_length=100)
    reaction: Optional[str] = None
    severity: Optional[str] = None
    reason: Optional[str] = None
    notes: Optional[str] = None
    record_date: Optional[str] = None
    prescription_id: Optional[Union[str, int]] = None
    encounter_id: Optional[Union[str, int]] = None


class LogoutResponse(BaseModel):
    success: bool = True


class PatientLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: str = Field(min_length=1, max_length=50)
    reason: Optional[str] = Field(default=None, max_length=1000)


class PatientLinkReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: Union[str, int]
    decision: str = Field(min_length=1, max_length=20)
    notes: Optional[str] = Field(default=None, max_length=1000)


class FamilyRelationshipRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: str = Field(min_length=1, max_length=50)
    related_patient_id: str = Field(min_length=1, max_length=50)
    relationship_type: str = Field(min_length=1, max_length=50)


class FamilyGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: str = Field(min_length=1, max_length=50)
    grantee_user_id: Optional[Union[str, int]] = None
    resource_type: Optional[str] = Field(default=None, max_length=50)
    permission: Optional[str] = Field(default=None, max_length=50)
    grant_id: Optional[Union[str, int]] = None


class ShareCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: str = Field(min_length=1, max_length=50)
    record_id: Union[str, int]
    shared_with: str = Field(min_length=1, max_length=320)
    expires_at: Optional[str] = Field(default=None, max_length=50)
    resource_type: str = Field(default="medication", min_length=1, max_length=50)


class ShareItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_type: str = Field(min_length=1, max_length=50)
    resource_id: Union[str, int]


class ShareBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: str = Field(min_length=1, max_length=50)
    items: list[ShareItem] = Field(min_length=1, max_length=100)
    shared_with: str = Field(min_length=1, max_length=320)
    expires_at: Optional[str] = Field(default=None, max_length=50)


class ShareRevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    share_id: Union[str, int]


class FamilyAccessRevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    grant_id: Union[str, int]


class AuditFilterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor_id: Optional[str] = Field(default=None, max_length=100)
    actor_role: Optional[str] = Field(default=None, max_length=30)
    action: Optional[str] = Field(default=None, max_length=100)
    category: Optional[str] = Field(default=None, max_length=100)
    resource_type: Optional[str] = Field(default=None, max_length=50)
    result: Optional[str] = Field(default=None, max_length=30)
    patient_id: Optional[str] = Field(default=None, max_length=50)
    date_from: Optional[str] = Field(default=None, max_length=50)
    date_to: Optional[str] = Field(default=None, max_length=50)


class EncounterCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: str = Field(min_length=1, max_length=50)
    visit_date: str = Field(min_length=1, max_length=50)
    visit_type: Optional[str] = Field(default=None, max_length=100)
    chief_complaint: Optional[str] = Field(default=None, max_length=2000)
    visit_notes: Optional[str] = Field(default=None, max_length=10000)
    diagnoses: Optional[str] = Field(default=None, max_length=5000)


class PrescriptionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: str = Field(min_length=1, max_length=50)
    medicine_name: str = Field(min_length=1, max_length=200)
    dosage: Optional[str] = Field(default=None, max_length=200)
    frequency: Optional[str] = Field(default=None, max_length=200)
    duration: Optional[str] = Field(default=None, max_length=200)
    instructions: Optional[str] = Field(default=None, max_length=2000)
    encounter_id: Optional[str] = Field(default=None, max_length=100)


class CorrectionRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: str = Field(min_length=1, max_length=50)
    resource_type: str = Field(min_length=1, max_length=50)
    resource_id: str = Field(min_length=1, max_length=100)
    requested_change: str = Field(min_length=1, max_length=5000)
    reason: Optional[str] = Field(default=None, max_length=2000)


class CorrectionReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=1, max_length=100)
    decision: str = Field(min_length=1, max_length=20)
    notes: Optional[str] = Field(default=None, max_length=5000)


class LifecycleActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: Optional[str] = Field(default=None, max_length=512)
    confirmation: Optional[str] = Field(default=None, max_length=20)


class ShareRedeemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=512)
