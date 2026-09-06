-- RecordGuard Web Core8 PostgreSQL foundation.
-- This is intentionally a clean server schema rather than a mechanical
-- SQLite dump. Every tenant-owned entity carries organization_id.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS organizations (
    organization_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_code text NOT NULL UNIQUE,
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS clinics (
    clinic_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
    name text NOT NULL, code text NOT NULL, address text, active boolean NOT NULL DEFAULT true,
    created_by uuid, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE (organization_id, code)
);

CREATE TABLE IF NOT EXISTS users (
    user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(organization_id),
    username text NOT NULL,
    email text,
    password_hash text NOT NULL,
    role text NOT NULL CHECK (role IN ('owner','admin','doctor','staff','patient','user')),
    patient_id uuid,
    full_name text NOT NULL,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, username)
);

CREATE TABLE IF NOT EXISTS patients (
    patient_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(organization_id),
    public_patient_id text NOT NULL,
    name text NOT NULL,
    date_of_birth date,
    age integer,
    sex text NOT NULL,
    permanent_address text,
    current_address text,
    phone_number text,
    blood_group text,
    registered_by uuid REFERENCES users(user_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, public_patient_id)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'users_patient_fk'
    ) THEN
        ALTER TABLE users ADD CONSTRAINT users_patient_fk
            FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS user_clinics (
    organization_id uuid NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    clinic_id uuid NOT NULL REFERENCES clinics(clinic_id) ON DELETE CASCADE,
    role_scope text NOT NULL DEFAULT 'member', created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (organization_id,user_id,clinic_id)
);

CREATE TABLE IF NOT EXISTS patient_clinics (
    organization_id uuid NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
    patient_id uuid NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    clinic_id uuid NOT NULL REFERENCES clinics(clinic_id) ON DELETE CASCADE,
    is_primary boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (organization_id,patient_id,clinic_id)
);

CREATE TABLE IF NOT EXISTS patient_link_requests (
    request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(organization_id),
    user_id uuid NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    patient_id uuid NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    requested_by uuid NOT NULL REFERENCES users(user_id),
    status text NOT NULL DEFAULT 'PENDING',
    reason_context text,
    created_at timestamptz NOT NULL DEFAULT now(),
    reviewed_by uuid REFERENCES users(user_id),
    reviewed_at timestamptz,
    review_notes text
);

CREATE TABLE IF NOT EXISTS patient_user_links (
    link_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(organization_id),
    user_id uuid NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    patient_id uuid NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'ACTIVE',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, user_id, patient_id)
);

CREATE TABLE IF NOT EXISTS medications (
    medication_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    medicine_name text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS encounters (
    encounter_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(organization_id),
    patient_id uuid NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    visit_date timestamptz NOT NULL,
    visit_type text,
    chief_complaint text,
    visit_notes text,
    diagnoses text,
    created_by uuid NOT NULL REFERENCES users(user_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    lifecycle_status text NOT NULL DEFAULT 'ACTIVE'
);

CREATE TABLE IF NOT EXISTS prescriptions (
    prescription_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(organization_id),
    patient_id uuid NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    encounter_id uuid REFERENCES encounters(encounter_id) ON DELETE SET NULL,
    medicine_name text NOT NULL,
    dosage text,
    frequency text,
    duration text,
    instructions text,
    prescribed_by uuid NOT NULL REFERENCES users(user_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    lifecycle_status text NOT NULL DEFAULT 'ACTIVE'
);

CREATE TABLE IF NOT EXISTS medication_records (
    record_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(organization_id),
    public_medication_id text NOT NULL,
    patient_id uuid NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    medication_id uuid NOT NULL REFERENCES medications(medication_id),
    prescription_id uuid REFERENCES prescriptions(prescription_id) ON DELETE SET NULL,
    encounter_id uuid REFERENCES encounters(encounter_id) ON DELETE SET NULL,
    response_type text NOT NULL,
    reaction text,
    severity text,
    reason text,
    notes text,
    record_date timestamptz NOT NULL,
    lifecycle_status text NOT NULL DEFAULT 'ACTIVE',
    archived_at timestamptz,
    archived_by uuid REFERENCES users(user_id),
    admin_deleted_at timestamptz,
    admin_deleted_by uuid REFERENCES users(user_id),
    UNIQUE (organization_id, public_medication_id)
);

CREATE TABLE IF NOT EXISTS attachments (
    attachment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(organization_id),
    patient_id uuid NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    encounter_id uuid REFERENCES encounters(encounter_id) ON DELETE SET NULL,
    record_id uuid REFERENCES medication_records(record_id) ON DELETE SET NULL,
    original_name text NOT NULL,
    object_key text NOT NULL,
    mime_type text,
    uploaded_by uuid NOT NULL REFERENCES users(user_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    lifecycle_status text NOT NULL DEFAULT 'ACTIVE'
);

CREATE TABLE IF NOT EXISTS record_shares (
    share_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(organization_id),
    patient_id uuid NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    resource_type text NOT NULL,
    resource_id uuid NOT NULL,
    shared_by uuid NOT NULL REFERENCES users(user_id),
    shared_with text NOT NULL,
    token_hash text NOT NULL UNIQUE,
    expires_at timestamptz,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS family_relationships (
    relationship_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(organization_id),
    patient_id uuid NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    related_patient_id uuid NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    relationship_type text NOT NULL,
    status text NOT NULL DEFAULT 'ACTIVE',
    created_by uuid NOT NULL REFERENCES users(user_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, patient_id, related_patient_id, relationship_type)
);

CREATE TABLE IF NOT EXISTS family_access_grants (
    grant_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(organization_id),
    patient_id uuid NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    grantee_user_id uuid NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    resource_type text NOT NULL,
    permission text NOT NULL,
    status text NOT NULL DEFAULT 'ACTIVE',
    granted_by uuid NOT NULL REFERENCES users(user_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    UNIQUE (organization_id, patient_id, grantee_user_id, resource_type, permission)
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(organization_id),
    timestamp timestamptz NOT NULL DEFAULT now(),
    actor_id uuid REFERENCES users(user_id),
    actor_role text,
    action text NOT NULL,
    category text NOT NULL,
    resource_type text,
    resource_id uuid,
    patient_id uuid REFERENCES patients(patient_id),
    result text NOT NULL DEFAULT 'SUCCESS',
    reason_context text,
    source text NOT NULL DEFAULT 'api',
    correlation_id uuid
);

CREATE TABLE IF NOT EXISTS api_sessions (
    session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(organization_id),
    user_id uuid NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz
);

CREATE TABLE IF NOT EXISTS api_login_attempts (
    key text PRIMARY KEY,
    failures integer NOT NULL DEFAULT 0,
    locked_until timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_patients_org ON patients(organization_id);
CREATE INDEX IF NOT EXISTS idx_link_requests_org_status ON patient_link_requests(organization_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_users_org ON users(organization_id);
CREATE INDEX IF NOT EXISTS idx_encounters_org_patient ON encounters(organization_id, patient_id);
CREATE INDEX IF NOT EXISTS idx_prescriptions_org_patient ON prescriptions(organization_id, patient_id);
CREATE INDEX IF NOT EXISTS idx_med_records_org_patient ON medication_records(organization_id, patient_id);
CREATE INDEX IF NOT EXISTS idx_attachments_org_patient ON attachments(organization_id, patient_id);
CREATE INDEX IF NOT EXISTS idx_shares_org_patient ON record_shares(organization_id, patient_id);
CREATE INDEX IF NOT EXISTS idx_family_org_patient ON family_relationships(organization_id, patient_id);
CREATE INDEX IF NOT EXISTS idx_family_grants_org_patient ON family_access_grants(organization_id, patient_id);
CREATE INDEX IF NOT EXISTS idx_audit_org_time ON audit_events(organization_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_org_corr ON audit_events(organization_id, correlation_id);


-- Audit events are append-only. Application code can insert events but cannot
-- mutate or remove historical governance evidence through normal DML.
CREATE OR REPLACE FUNCTION recordguard_block_audit_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_recordguard_audit_no_update ON audit_events;
CREATE TRIGGER trg_recordguard_audit_no_update
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION recordguard_block_audit_mutation();


CREATE TABLE IF NOT EXISTS correction_requests (
    request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(organization_id),
    patient_id uuid NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    requested_by uuid NOT NULL REFERENCES users(user_id),
    resource_type text NOT NULL,
    resource_id uuid NOT NULL,
    requested_change text NOT NULL,
    reason text,
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','APPROVED','REJECTED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    reviewed_by uuid REFERENCES users(user_id),
    reviewed_at timestamptz,
    review_notes text
);

CREATE INDEX IF NOT EXISTS idx_correction_requests_org_patient ON correction_requests(organization_id, patient_id, created_at DESC);


-- Defense in depth: tenant-owned foreign keys must reference rows in the same organization.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='users_org_patient_fk') THEN
        ALTER TABLE patients ADD CONSTRAINT patients_org_patient_unique UNIQUE (organization_id, patient_id);
        ALTER TABLE users ADD CONSTRAINT users_org_patient_fk FOREIGN KEY (organization_id, patient_id) REFERENCES patients(organization_id, patient_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='encounters_org_patient_fk') THEN
        ALTER TABLE encounters ADD CONSTRAINT encounters_org_patient_fk FOREIGN KEY (organization_id, patient_id) REFERENCES patients(organization_id, patient_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='prescriptions_org_patient_fk') THEN
        ALTER TABLE prescriptions ADD CONSTRAINT prescriptions_org_patient_fk FOREIGN KEY (organization_id, patient_id) REFERENCES patients(organization_id, patient_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='med_records_org_patient_fk') THEN
        ALTER TABLE medication_records ADD CONSTRAINT med_records_org_patient_fk FOREIGN KEY (organization_id, patient_id) REFERENCES patients(organization_id, patient_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='attachments_org_patient_fk') THEN
        ALTER TABLE attachments ADD CONSTRAINT attachments_org_patient_fk FOREIGN KEY (organization_id, patient_id) REFERENCES patients(organization_id, patient_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='family_org_patient_fk') THEN
        ALTER TABLE family_relationships ADD CONSTRAINT family_org_patient_fk FOREIGN KEY (organization_id, patient_id) REFERENCES patients(organization_id, patient_id);
        ALTER TABLE family_relationships ADD CONSTRAINT family_org_related_patient_fk FOREIGN KEY (organization_id, related_patient_id) REFERENCES patients(organization_id, patient_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='family_access_org_patient_fk') THEN
        ALTER TABLE family_access_grants ADD CONSTRAINT family_access_org_patient_fk FOREIGN KEY (organization_id, patient_id) REFERENCES patients(organization_id, patient_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='shares_org_patient_fk') THEN
        ALTER TABLE record_shares ADD CONSTRAINT shares_org_patient_fk FOREIGN KEY (organization_id, patient_id) REFERENCES patients(organization_id, patient_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='correction_org_patient_fk') THEN
        ALTER TABLE correction_requests ADD CONSTRAINT correction_org_patient_fk FOREIGN KEY (organization_id, patient_id) REFERENCES patients(organization_id, patient_id);
    END IF;
END $$;
