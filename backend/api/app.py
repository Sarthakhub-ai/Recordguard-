"""RecordGuard Web Core8 API foundation.

Transition architecture: the API uses Core8's existing domain functions while
session handling, request validation, response shaping and tenant checks are
moved to explicit API boundaries. This lets the desktop app keep working while
PostgreSQL/repository extraction proceeds.
"""
import os
import uuid
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, UploadFile, File, status, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi import Cookie

import functions
from database import initialize_database
from shared.contracts import (
    LoginRequest, LoginResponse, LogoutResponse, OwnerSetupRequest,
    PatientCreateRequest, MedicationCreateRequest, AuditFilterRequest, LifecycleActionRequest,
    EncounterCreateRequest, PrescriptionCreateRequest, CorrectionRequestCreate, CorrectionReviewRequest,
    ShareRedeemRequest,
    PatientLinkRequest, PatientLinkReviewRequest, FamilyRelationshipRequest,
    FamilyGrantRequest, FamilyAccessRevokeRequest, ShareCreateRequest, ShareBatchRequest, ShareRevokeRequest,
)
from shared.domain import Actor, DomainError, AuthorizationError, require_organization
from backend.repositories.sqlite import SQLiteSessionRepository
from backend.repositories.postgres import PostgreSQLSessionRepository, PostgreSQLRepository, PostgreSQLUnavailable
from backend.security import check_login_rate, record_login_failure, clear_login_failures

if os.getenv("RECORDGUARD_SESSION_BACKEND", "sqlite").strip().lower() != "postgres":
    initialize_database()

def _session_repository():
    backend = os.getenv("RECORDGUARD_SESSION_BACKEND", "sqlite").strip().lower()
    if backend == "postgres":
        try:
            return PostgreSQLSessionRepository()
        except PostgreSQLUnavailable as exc:
            raise RuntimeError(str(exc)) from exc
    return SQLiteSessionRepository()

sessions = _session_repository()

def _data_repository():
    if os.getenv("RECORDGUARD_SESSION_BACKEND", "sqlite").strip().lower() == "postgres":
        try:
            return PostgreSQLRepository()
        except PostgreSQLUnavailable as exc:
            raise RuntimeError(str(exc)) from exc
    return None

data_repository = _data_repository()

app = FastAPI(title="RecordGuard API", version="0.8.0", docs_url="/docs", redoc_url="/redoc")

@app.middleware("http")
async def security_headers(request: Request, call_next):
    # A fresh correlation identifier is generated for every request. We do not
    # reflect arbitrary client input into the response header.
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith(("/auth", "/audit", "/patients", "/sharing", "/family", "/patient-links")) else "no-cache"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.middleware("http")
async def cookie_csrf_guard(request: Request, call_next):
    # Browser sessions authenticate with an HttpOnly cookie. For state-changing
    # requests, require a same-site/allowed Origin when the cookie is present.
    # Bearer-token API clients are unaffected. Requests without Origin are kept
    # compatible with non-browser clients and same-process automation.
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.cookies.get("rg_session"):
        origin = request.headers.get("origin")
        if origin:
            allowed = {o.rstrip("/") for o in origins}
            if origin.rstrip("/") not in allowed:
                from starlette.responses import JSONResponse
                return JSONResponse({"detail": "Cross-site request blocked."}, status_code=403)
    return await call_next(request)

environment = os.getenv("RECORDGUARD_ENV", "development").strip().lower()
origins = [x.strip() for x in os.getenv("RECORDGUARD_WEB_ORIGINS", "http://localhost:3000").split(",") if x.strip()]
if environment == "production":
    if not origins or any(o == "*" or not o.lower().startswith("https://") for o in origins):
        raise RuntimeError("Production requires explicit HTTPS RECORDGUARD_WEB_ORIGINS; wildcard/HTTP origins are not allowed.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


def _public_user(user: dict) -> dict:
    # Explicit response allowlist. Never return password_hash or arbitrary DB columns.
    return {k: user.get(k) for k in (
        "user_id", "username", "email", "role", "patient_id", "full_name",
        "active", "organization_id", "created_at"
    )}


def _token_from_header(authorization: Optional[str]) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return token


def current_user(authorization: Optional[str] = Header(default=None), rg_session: Optional[str] = Cookie(default=None)) -> dict:
    token = _token_from_header(authorization) if authorization else (rg_session or "")
    user = sessions.get_session_user(token)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is invalid or expired.")
    return user


def _actor(user: dict) -> Actor:
    try:
        return Actor.from_mapping(user)
    except DomainError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def _handle(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except functions.AuthorizationRecordGuardError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except functions.RecordGuardError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/health")
def health():
    backend = os.getenv("RECORDGUARD_SESSION_BACKEND", "sqlite").strip().lower()
    return {"status": "ok", "service": "recordguard-api", "session_storage": backend}


@app.post("/auth/owner/setup", response_model=LoginResponse)
def owner_setup(payload: OwnerSetupRequest, request: Request, response: Response):
    if data_repository is not None:
        if data_repository.has_owner():
            raise HTTPException(status_code=409, detail="An Owner account already exists. Please sign in.")
        user = _handle(data_repository.create_initial_owner, payload.username, payload.password, payload.full_name)
    else:
        if functions.has_owner_account():
            raise HTTPException(status_code=409, detail="An Owner account already exists. Please sign in.")
        user = _handle(functions.create_initial_owner, payload.username, payload.password, payload.full_name)
    token = sessions.create_session(user["user_id"], user.get("organization_id") or "DEFAULT")
    response.set_cookie("rg_session", token, httponly=True, secure=request.url.scheme == "https", samesite="lax", max_age=3600, path="/")
    return LoginResponse(access_token=(None if str(getattr(payload, "client", "api")).lower() == "web" else token), user=_public_user(user))


@app.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, response: Response):
    client_ip = request.client.host if request.client else "unknown"
    try:
        if data_repository is not None:
            data_repository.check_login_rate(payload.username, client_ip)
            user = data_repository.authenticate_user(payload.username, payload.password)
        else:
            check_login_rate(payload.username, client_ip)
            user = functions.authenticate_user(payload.username, payload.password)
    except PermissionError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except (functions.RecordGuardError, ValueError) as exc:
        if data_repository is not None:
            data_repository.record_login_failure(payload.username, client_ip)
        else:
            record_login_failure(payload.username, client_ip)
        raise HTTPException(status_code=401, detail="Invalid username or password.") from exc
    if data_repository is not None:
        data_repository.clear_login_failures(payload.username, client_ip)
    else:
        clear_login_failures(payload.username, client_ip)
    token = sessions.create_session(user["user_id"], user.get("organization_id") or "DEFAULT")
    if str(payload.client).lower() == "web":
        response.set_cookie("rg_session", token, httponly=True, secure=request.url.scheme == "https", samesite="lax", max_age=3600, path="/")
    return LoginResponse(access_token=(None if str(payload.client).lower() == "web" else token), user=_public_user(user))


@app.post("/auth/logout", response_model=LogoutResponse)
def logout(response: Response, authorization: Optional[str] = Header(default=None), rg_session: Optional[str] = Cookie(default=None)):
    token = _token_from_header(authorization) if authorization else (rg_session or "")
    if token:
        sessions.revoke_session(token)
    response.delete_cookie("rg_session", path="/")
    return LogoutResponse()


@app.get("/auth/me")
def me(user: dict = Depends(current_user)):
    return {"user": _public_user(user)}


@app.get("/patients")
def patients(q: Optional[str] = None, user: dict = Depends(current_user)):
    # Patient accounts never receive an organization-wide patient directory.
    if data_repository is not None:
        if str(user.get("role", "")).lower() == "patient":
            pid = user.get("patient_id")
            row = None if not pid else data_repository.get_patient(_actor(user), pid)
            return {"items": [] if row is None else [row]}
        return {"items": data_repository.list_patients(_actor(user), q)}
    if str(user.get("role", "")).lower() == "patient":
        pid = user.get("patient_id")
        return {"items": [] if not pid else [_handle(functions.get_patient_by_id, user, pid)]}
    return {"items": _handle(functions.list_all_patients, user)}


@app.post("/patients")
def create_patient(payload: PatientCreateRequest, user: dict = Depends(current_user)):
    if str(user.get("role", "")).lower() not in {"owner", "admin", "doctor", "staff"}:
        raise HTTPException(status_code=403, detail="You are not authorized to register patients.")
    if data_repository is not None:
        return _handle(data_repository.create_patient, _actor(user), payload.name, payload.age, payload.sex,
                       payload.date_of_birth, payload.permanent_address, payload.current_address,
                       payload.phone_number, payload.blood_group)
    return _handle(functions.register_patient, user, payload.name, str(payload.age), payload.sex,
                   payload.date_of_birth or "", payload.permanent_address or "", payload.current_address or "",
                   payload.phone_number or "", payload.blood_group or "")


@app.get("/patients/{patient_id}")
def get_patient(patient_id: str, user: dict = Depends(current_user)):
    if data_repository is not None:
        patient = data_repository.get_patient(_actor(user), patient_id)
    else:
        patient = _handle(functions.get_patient_by_id, user, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found.")
    require_organization(_actor(user), patient.get("organization_id"))
    return patient


@app.get("/patients/{patient_id}/medications")
def medications(patient_id: str, include_archived: bool = False, user: dict = Depends(current_user)):
    if data_repository is not None:
        if not data_repository.get_patient(_actor(user), patient_id):
            raise HTTPException(status_code=404, detail="Patient not found.")
        return {"items": data_repository.list_medications(_actor(user), patient_id, include_archived)}
    _handle(functions.get_patient_by_id, user, patient_id)
    return {"items": _handle(functions.get_medication_records_for_patient, patient_id, False, False, user)}


@app.post("/medications")
def create_medication(payload: MedicationCreateRequest, user: dict = Depends(current_user)):
    if data_repository is not None:
        return _handle(data_repository.create_medication, _actor(user), payload.patient_id, payload.medicine_name,
                       payload.response_type, payload.reaction, payload.severity, payload.reason,
                       payload.notes, payload.prescription_id, payload.encounter_id)
    patient = _handle(functions.get_patient_by_id, user, payload.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")
    require_organization(_actor(user), patient.get("organization_id"))
    return _handle(functions.add_medication_record, user, payload.patient_id, payload.medicine_name,
                   payload.response_type, payload.reaction or "", payload.severity or "", payload.reason or "",
                   payload.notes or "", payload.prescription_id, payload.encounter_id)


@app.get("/patients/{patient_id}/encounters")
def list_encounters(patient_id: str, include_archived: bool = False, user: dict = Depends(current_user)):
    if data_repository is not None:
        return {"items": _handle(data_repository.list_encounters, _actor(user), patient_id, include_archived)}
    return {"items": _handle(functions.list_encounters, user, patient_id)}


@app.post("/encounters")
def create_encounter(payload: EncounterCreateRequest, user: dict = Depends(current_user)):
    if data_repository is not None:
        return _handle(data_repository.create_encounter, _actor(user), payload.patient_id, payload.visit_date, payload.visit_type, payload.chief_complaint, payload.visit_notes, payload.diagnoses)
    return _handle(functions.create_encounter, user, payload.patient_id, payload.visit_date, payload.visit_type or "", payload.chief_complaint or "", payload.visit_notes or "", payload.diagnoses or "")


@app.get("/patients/{patient_id}/prescriptions")
def list_prescriptions(patient_id: str, include_archived: bool = False, user: dict = Depends(current_user)):
    if data_repository is not None:
        return {"items": _handle(data_repository.list_prescriptions, _actor(user), patient_id, include_archived)}
    return {"items": _handle(functions.list_prescriptions, user, patient_id)}


@app.post("/prescriptions")
def create_prescription(payload: PrescriptionCreateRequest, user: dict = Depends(current_user)):
    if data_repository is not None:
        return _handle(data_repository.create_prescription, _actor(user), payload.patient_id, payload.medicine_name, payload.dosage, payload.frequency, payload.duration, payload.instructions, payload.encounter_id)
    return _handle(functions.add_prescription, user, payload.patient_id, payload.medicine_name, payload.dosage or "", payload.frequency or "", payload.duration or "", payload.instructions or "", payload.encounter_id)


@app.get("/correction-requests")
def correction_requests(patient_id: Optional[str] = None, status_filter: Optional[str] = None, user: dict = Depends(current_user)):
    if data_repository is not None:
        return {"items": _handle(data_repository.list_correction_requests, _actor(user), patient_id, status_filter)}
    raise HTTPException(status_code=501, detail="Correction request review is available in PostgreSQL mode in this phase.")


@app.post("/correction-requests")
def create_correction_request(payload: CorrectionRequestCreate, user: dict = Depends(current_user)):
    if data_repository is None:
        raise HTTPException(status_code=501, detail="Correction requests require PostgreSQL mode in this phase.")
    return _handle(data_repository.create_correction_request, _actor(user), payload.patient_id, payload.resource_type, payload.resource_id, payload.requested_change, payload.reason)


@app.post("/correction-requests/review")
def review_correction_request(payload: CorrectionReviewRequest, user: dict = Depends(current_user)):
    if data_repository is None:
        raise HTTPException(status_code=501, detail="Correction requests require PostgreSQL mode in this phase.")
    return {"success": bool(_handle(data_repository.review_correction_request, _actor(user), payload.request_id, payload.decision, payload.notes))}


@app.get("/audit")
def audit(
    actor_id: Optional[str] = None, actor_role: Optional[str] = None,
    action: Optional[str] = None, category: Optional[str] = None,
    resource_type: Optional[str] = None, result: Optional[str] = None,
    patient_id: Optional[str] = None, date_from: Optional[str] = None,
    date_to: Optional[str] = None, user: dict = Depends(current_user)
):
    filters = AuditFilterRequest(
        actor_id=actor_id, actor_role=actor_role, action=action, category=category,
        resource_type=resource_type, result=result, patient_id=patient_id,
        date_from=date_from, date_to=date_to
    ).model_dump(exclude_none=True)
    if data_repository is not None:
        if str(user.get("role", "")).lower() not in {"owner", "admin"}:
            raise HTTPException(status_code=403, detail="Only Owner or Admin can view the audit log.")
        return {"items": data_repository.list_audit_events(user.get("organization_id") or "DEFAULT", filters)}
    return {"items": _handle(functions.get_audit_log, user, filters)}


@app.get("/audit/records/{record_id}")
def audit_record(record_id: str, user: dict = Depends(current_user)):
    if data_repository is not None:
        if str(user.get("role", "")).lower() not in {"owner", "admin"}: raise HTTPException(status_code=403, detail="Only Owner or Admin can view the audit log.")
        return {"items": [x for x in data_repository.list_audit_events(user.get("organization_id") or "DEFAULT", {"resource_id": record_id})]}
    return {"items": _handle(functions.get_audit_log_for_record, user, record_id)}


@app.post("/medications/{record_id}/archive")
def archive_medication(record_id: str, user: dict = Depends(current_user)):
    if data_repository is not None: return {"success": bool(_handle(data_repository.lifecycle_medication, _actor(user), record_id, "archive"))}
    return {"success": bool(_handle(functions.archive_medication_record, user, record_id))}


@app.post("/medications/{record_id}/recover")
def recover_medication(record_id: str, user: dict = Depends(current_user)):
    if data_repository is not None: return {"success": bool(_handle(data_repository.lifecycle_medication, _actor(user), record_id, "recover"))}
    return {"success": bool(_handle(functions.recover_archived_medication_record, user, record_id))}


@app.post("/medications/{record_id}/admin-delete")
def admin_delete_medication(record_id: str, payload: LifecycleActionRequest, user: dict = Depends(current_user)):
    if payload.confirmation != "DELETE":
        raise HTTPException(status_code=400, detail='Type DELETE in confirmation.')
    if not payload.password:
        raise HTTPException(status_code=400, detail="Current password is required.")
    if data_repository is not None: return {"success": bool(_handle(data_repository.lifecycle_medication, _actor(user), record_id, "admin_delete", payload.password))}
    return {"success": bool(_handle(functions.admin_delete_medication_record, user, record_id, payload.password))}


@app.post("/medications/{record_id}/owner-recover")
def owner_recover_medication(record_id: str, user: dict = Depends(current_user)):
    if data_repository is not None: return {"success": bool(_handle(data_repository.lifecycle_medication, _actor(user), record_id, "owner_recover"))}
    return {"success": bool(_handle(functions.recover_admin_deleted_medication_record, user, record_id))}


@app.post("/medications/{record_id}/permanent-destroy")
def permanently_destroy_medication(record_id: str, payload: LifecycleActionRequest, user: dict = Depends(current_user)):
    if payload.confirmation != "DELETE":
        raise HTTPException(status_code=400, detail='Type DELETE in confirmation.')
    if not payload.password:
        raise HTTPException(status_code=400, detail="Current password is required.")
    if data_repository is not None: return {"success": bool(_handle(data_repository.lifecycle_medication, _actor(user), record_id, "permanent_destroy", payload.password))}
    return {"success": bool(_handle(functions.permanently_delete_medication_record, user, record_id, payload.password))}


@app.post("/ehr/{resource_type}/{resource_id}/archive")
def archive_ehr(resource_type: str, resource_id: str, user: dict = Depends(current_user)):
    if data_repository is not None: return {"success": bool(_handle(data_repository.lifecycle_ehr, _actor(user), resource_type, resource_id, "archive"))}
    return {"success": bool(_handle(functions.archive_ehr_item, user, resource_type, resource_id))}


@app.post("/ehr/{resource_type}/{resource_id}/recover")
def recover_ehr(resource_type: str, resource_id: str, user: dict = Depends(current_user)):
    if data_repository is not None: return {"success": bool(_handle(data_repository.lifecycle_ehr, _actor(user), resource_type, resource_id, "recover"))}
    return {"success": bool(_handle(functions.recover_archived_ehr_item, user, resource_type, resource_id))}


@app.post("/ehr/{resource_type}/{resource_id}/admin-delete")
def admin_delete_ehr(resource_type: str, resource_id: str, payload: LifecycleActionRequest, user: dict = Depends(current_user)):
    if payload.confirmation != "DELETE":
        raise HTTPException(status_code=400, detail='Type DELETE in confirmation.')
    if not payload.password:
        raise HTTPException(status_code=400, detail="Current password is required.")
    if data_repository is not None: return {"success": bool(_handle(data_repository.lifecycle_ehr, _actor(user), resource_type, resource_id, "admin_delete", payload.password))}
    return {"success": bool(_handle(functions.admin_delete_ehr_item, user, resource_type, resource_id, payload.password))}


@app.post("/ehr/{resource_type}/{resource_id}/owner-recover")
def owner_recover_ehr(resource_type: str, resource_id: str, user: dict = Depends(current_user)):
    if data_repository is not None: return {"success": bool(_handle(data_repository.lifecycle_ehr, _actor(user), resource_type, resource_id, "owner_recover"))}
    return {"success": bool(_handle(functions.recover_admin_deleted_ehr_item, user, resource_type, resource_id))}


@app.post("/ehr/{resource_type}/{resource_id}/permanent-destroy")
def permanently_destroy_ehr(resource_type: str, resource_id: str, payload: LifecycleActionRequest, user: dict = Depends(current_user)):
    if payload.confirmation != "DELETE":
        raise HTTPException(status_code=400, detail='Type DELETE in confirmation.')
    if not payload.password:
        raise HTTPException(status_code=400, detail="Current password is required.")
    if data_repository is not None: return {"success": bool(_handle(data_repository.lifecycle_ehr, _actor(user), resource_type, resource_id, "permanent_destroy", payload.password))}
    return {"success": bool(_handle(functions.permanently_delete_ehr_item, user, resource_type, resource_id, payload.password))}


@app.post("/sharing/redeem")
def redeem_share(payload: ShareRedeemRequest):
    if data_repository is None:
        return _handle(functions.access_shared_record, payload.token)
    return _handle(data_repository.redeem_share, payload.token)


@app.get("/sharing")
def sharing(patient_id: str, user: dict = Depends(current_user)):
    if data_repository is not None:
        rows = _handle(data_repository.list_record_shares, _actor(user), patient_id)
    else:
        _handle(functions.get_patient_by_id, user, patient_id)
        rows = _handle(functions.list_record_shares, user, patient_id)
    # Share tokens are bearer credentials. Never expose them (or token hashes)
    # through an authenticated management/list endpoint.
    allowed = {"share_id", "patient_id", "record_id", "resource_type",
               "resource_id", "shared_by", "shared_with", "expires_at",
               "revoked", "revoked_at", "created_at", "viewed_at"}
    return {"items": [{k: row.get(k) for k in allowed if k in row} for row in rows]}


@app.post("/sharing")
def create_share(payload: ShareCreateRequest, user: dict = Depends(current_user)):
    if data_repository is not None:
        result = _handle(data_repository.create_record_shares_batch, _actor(user), payload.patient_id, [(payload.resource_type, payload.record_id)], payload.shared_with, payload.expires_at)
        return result[0]
    result = _handle(functions.create_record_share, user, payload.patient_id,
                      payload.record_id, payload.shared_with, payload.expires_at,
                      payload.resource_type)
    # Token is returned exactly once at creation because it is a bearer secret.
    return result


@app.post("/sharing/batch")
def create_share_batch(payload: ShareBatchRequest, user: dict = Depends(current_user)):
    if data_repository is not None:
        result = _handle(data_repository.create_record_shares_batch, _actor(user), payload.patient_id, [(item.resource_type, item.resource_id) for item in payload.items], payload.shared_with, payload.expires_at)
    else:
        result = _handle(functions.create_record_shares_batch, user, payload.patient_id,
                      [(item.resource_type, item.resource_id) for item in payload.items],
                      payload.shared_with, payload.expires_at)
    return {"items": result}


@app.post("/sharing/revoke")
def revoke_share(payload: ShareRevokeRequest, user: dict = Depends(current_user)):
    if data_repository is not None: _handle(data_repository.revoke_record_share, _actor(user), payload.share_id)
    else: _handle(functions.revoke_record_share, user, payload.share_id)
    return {"success": True}




@app.get("/family/relationships")
def family_relationships(patient_id: str, user: dict = Depends(current_user)):
    if data_repository is not None: return {"items": _handle(data_repository.list_family_relationships, _actor(user), patient_id)}
    return {"items": _handle(functions.list_family_relationships, user, patient_id)}


@app.post("/family/relationships")
def create_family_relationship(payload: FamilyRelationshipRequest, user: dict = Depends(current_user)):
    if data_repository is not None: relationship_id = _handle(data_repository.create_family_relationship, _actor(user), payload.patient_id, payload.related_patient_id, payload.relationship_type)
    else: relationship_id = _handle(functions.create_family_relationship, user, payload.patient_id,
                                payload.related_patient_id, payload.relationship_type)
    return {"relationship_id": relationship_id}


@app.get("/family/access")
def family_access(patient_id: str, user: dict = Depends(current_user)):
    if data_repository is not None: return {"items": _handle(data_repository.list_family_access, _actor(user), patient_id)}
    return {"items": _handle(functions.list_family_access, user, patient_id)}


@app.post("/family/access")
def grant_family_access(payload: FamilyGrantRequest, user: dict = Depends(current_user)):
    if data_repository is not None: grant_id = _handle(data_repository.grant_family_access, _actor(user), payload.patient_id, payload.grantee_user_id, payload.resource_type, payload.permission)
    else: grant_id = _handle(functions.grant_family_access, user, payload.patient_id,
                       payload.grantee_user_id, payload.resource_type, payload.permission)
    return {"grant_id": grant_id}


@app.post("/family/access/revoke")
def revoke_family_access(payload: FamilyAccessRevokeRequest, user: dict = Depends(current_user)):
    if data_repository is not None: _handle(data_repository.revoke_family_access, _actor(user), payload.grant_id)
    else: _handle(functions.revoke_family_access, user, payload.grant_id)
    return {"success": True}


@app.get("/patient-links")
def patient_link_requests(status_filter: Optional[str] = None, user: dict = Depends(current_user)):
    if data_repository is not None: return {"items": _handle(data_repository.list_patient_link_requests, _actor(user), status_filter)}
    return {"items": _handle(functions.list_patient_link_requests, user, status_filter)}


@app.post("/patient-links/request")
def request_patient_link(payload: PatientLinkRequest, user: dict = Depends(current_user)):
    if data_repository is not None: request_id = _handle(data_repository.request_patient_link, _actor(user), payload.patient_id, payload.reason or "")
    else: request_id = _handle(functions.request_patient_link, user, payload.patient_id, payload.reason or "")
    return {"request_id": request_id}


@app.post("/patient-links/review")
def review_patient_link(payload: PatientLinkReviewRequest, user: dict = Depends(current_user)):
    if data_repository is not None: _handle(data_repository.review_patient_link_request, _actor(user), payload.request_id, payload.decision, payload.notes or "")
    else: _handle(functions.review_patient_link_request, user, payload.request_id,
            payload.decision, payload.notes or "")
    return {"success": True}


@app.get("/patients/{patient_id}/attachments")
def attachments(patient_id: str, user: dict = Depends(current_user)):
    if data_repository is not None:
        rows = _handle(data_repository.list_attachments, _actor(user), patient_id)
    else:
        _handle(functions.get_patient_by_id, user, patient_id)
        rows = _handle(functions.list_attachments, user, patient_id)
    # Never expose filesystem paths or other internal storage metadata.
    allowed = {"attachment_id", "patient_id", "encounter_id", "record_id",
               "original_name", "mime_type", "uploaded_by", "created_at"}
    return {"items": [{k: row.get(k) for k in allowed if k in row} for row in rows]}


@app.get("/attachments/{attachment_id}/download")
def download_attachment(attachment_id: str, user: dict = Depends(current_user)):
    if data_repository is None:
        raise HTTPException(status_code=501, detail="Secure attachment downloads require PostgreSQL mode in this phase.")
    info = _handle(data_repository.get_attachment_path, _actor(user), attachment_id)
    return FileResponse(info["path"], media_type=info["mime_type"], filename=info["filename"], headers={"Cache-Control":"no-store"})


@app.post("/patients/{patient_id}/attachments")
def upload_attachment(patient_id: str, file: UploadFile = File(...), user: dict = Depends(current_user)):
    if data_repository is None:
        _handle(functions.get_patient_by_id, user, patient_id)
    else:
        _handle(data_repository.get_patient, _actor(user), patient_id)
    import tempfile, os as _os
    suffix = _os.path.splitext(file.filename or "")[1].lower()
    max_size = 20 * 1024 * 1024
    total = 0
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        path = tmp.name
        try:
            while chunk := file.file.read(1024 * 1024):
                total += len(chunk)
                if total > max_size:
                    raise HTTPException(status_code=413, detail="Attachment is too large. Maximum size is 20 MB.")
                tmp.write(chunk)
        finally:
            file.file.close()
    try:
        aid = _handle(data_repository.add_attachment, _actor(user), patient_id, path) if data_repository is not None else _handle(functions.add_attachment, user, patient_id, path)
        return {"attachment_id": aid}
    finally:
        try: _os.remove(path)
        except OSError: pass


@app.get("/openapi-contract")
def contract():
    """Small navigational endpoint for clients; the full OpenAPI document is /openapi.json."""
    return {"version": "0.8.0", "status": "security-production-hardening", "web_next": True, "mobile_next": False}