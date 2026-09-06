'use client';

import { useEffect, useState } from 'react';

const API =
  process.env.NEXT_PUBLIC_RECORDGUARD_API || 'http://localhost:8000';

type User = {
  user_id?: string;
  full_name?: string;
  role?: string;
  organization_id?: string;
  patient_id?: string | null;
  username?: string;
  email?: string;
};

type Patient = {
  public_patient_id: string;
  name: string;
  age: number;
  sex: string;
  blood_group?: string | null;
  phone_number?: string | null;
};

type Medication = {
  record_id?: string;
  medication_id?: string;
  medicine_name: string;
  response_type?: string;
  reaction?: string;
  severity?: string;
  reason?: string;
  notes?: string;
  lifecycle_status?: string;
  created_at?: string;
};

type Encounter = {
  encounter_id?: string;
  visit_date: string;
  visit_type?: string;
  chief_complaint?: string;
  visit_notes?: string;
  diagnoses?: string;
  lifecycle_status?: string;
  created_at?: string;
};

type Prescription = {
  prescription_id?: string;
  medicine_name: string;
  dosage?: string;
  frequency?: string;
  duration?: string;
  instructions?: string;
  encounter_id?: string;
  lifecycle_status?: string;
  created_at?: string;
};

type Audit = {
  event_id?: string;
  actor_role?: string;
  action?: string;
  category?: string;
  resource_type?: string;
  result?: string;
  patient_id?: string;
  created_at?: string;
};

type GenericRow = Record<string, any>;

async function api(
  path: string,
  token: string | undefined,
  options: RequestInit = {}
) {
  const headers: any = {
    ...(options.headers || {}),
  };

  if (
    options.body &&
    !(options.body instanceof FormData) &&
    !headers['Content-Type']
  ) {
    headers['Content-Type'] = 'application/json';
  }

  if (token && token !== 'cookie') {
    headers.Authorization = `Bearer ${token}`;
  }

  const r = await fetch(`${API}${path}`, {
    ...options,
    credentials:'include',
    headers,
  });

  const d = await r.json().catch(() => ({}));

  if (!r.ok) {
    throw new Error(d.detail || 'Request failed');
  }

  return d;
}

function err(e: unknown) {
  return e instanceof Error ? e.message : 'Request failed.';
}

function destructivePayload(password: string) {
  return JSON.stringify({password,confirmation:'DELETE'});
}

function downloadText(filename: string, content: string, type = 'application/json') {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function csvEscape(value: unknown) {
  const text = String(value ?? '');
  return `"${text.replaceAll('"', '""')}"`;
}

const clinicalRoles = ['owner', 'admin', 'doctor', 'staff'];
const destructiveRoles = ['owner', 'admin'];

export default function Home() {
  const [token, setToken] = useState('');
  const [user, setUser] = useState<User | null>(null);
  const [tab, setTab] = useState('Dashboard');
  const [message, setMessage] = useState('');

  const [login, setLogin] = useState({
    username: '',
    password: '',
  });

  const [registering, setRegistering] = useState(false);
  const [ownerSetupAvailable, setOwnerSetupAvailable] = useState(false);
  const [ownerSetupMode, setOwnerSetupMode] = useState(false);

  const [registration, setRegistration] = useState({
    username: '',
    password: '',
    full_name: '',
    email: '',
  });

  useEffect(() => {
    api('/auth/owner/status', undefined)
      .then((d) => {
        setOwnerSetupAvailable(Boolean(d.available));
      })
      .catch(() => {
        setOwnerSetupAvailable(false);
      });
  }, []);
useEffect(() => {
    api('/auth/me', undefined)
      .then((d) => {
        setUser(d.user);
        setToken('cookie');
      })
      .catch(() => {});
  }, []);

  async function signIn(e: React.FormEvent) {
    e.preventDefault();
    setMessage('Signing inâ€¦');

    try {
      const d = await api('/auth/login', undefined, {
        method: 'POST',
        body: JSON.stringify({
          ...login,
          client:'web',
        }),
      });

      setToken('cookie');
      setUser(d.user);
      setMessage('Signed in successfully.');
    } catch (e) {
      setMessage(err(e));
    }
  }

  async function signOut() {
    try {
      await api('/auth/logout', undefined, {
        method: 'POST',
      });
    } finally {
      setToken('');
      setUser(null);
      setTab('Dashboard');
    }
  }

  if (!token) {
    return (
      <main className="auth">
        <a className="skip" href="#main">
          Skip to sign in
        </a>

        <section className="authCard" id="main">
          <div className="brand">RecordGuard</div>

          <p className="eyebrow">
            Healthcare trust &amp; governance
          </p>

          {ownerSetupMode ? (
            <>
              <h1>First-time Owner setup</h1>

              <p className="muted">
                Create the first Owner account for this RecordGuard
                installation. This option is available only when no active
                Owner account exists.
              </p>

              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  setMessage('Creating Owner account…');

                  try {
                    const d = await api('/auth/owner/setup', undefined, {
                      method: 'POST',
                      body: JSON.stringify({
                        username: registration.username,
                        password: registration.password,
                        full_name: registration.full_name,
                      }),
                    });

                    setToken('cookie');
                    setUser(d.user);
                    setOwnerSetupAvailable(false);
                    setOwnerSetupMode(false);
                    setMessage('Owner account created successfully.');
                  } catch (er) {
                    setMessage(err(er));

                    try {
                      const status = await api(
                        '/auth/owner/status',
                        undefined
                      );
                      setOwnerSetupAvailable(Boolean(status.available));
                    } catch {
                      setOwnerSetupAvailable(false);
                    }
                  }
                }}
                aria-label="First-time Owner setup form"
              >
                <label>
                  Full name
                  <input
                    required
                    value={registration.full_name}
                    onChange={(e) =>
                      setRegistration({
                        ...registration,
                        full_name: e.target.value,
                      })
                    }
                  />
                </label>

                <label>
                  Username
                  <input
                    required
                    minLength={3}
                    value={registration.username}
                    onChange={(e) =>
                      setRegistration({
                        ...registration,
                        username: e.target.value,
                      })
                    }
                  />
                </label>

                <label>
                  Password
                  <input
                    required
                    minLength={8}
                    type="password"
                    value={registration.password}
                    onChange={(e) =>
                      setRegistration({
                        ...registration,
                        password: e.target.value,
                      })
                    }
                  />
                </label>

                <button type="submit">Create Owner account</button>
              </form>

              <button
                type="button"
                className="secondary"
                onClick={() => {
                  setOwnerSetupMode(false);
                  setMessage('');
                }}
              >
                Back to sign in
              </button>
            </>
          ) : (
            <>
          {registering ? (
            <>
              <h1>Create account</h1>

              <p className="muted">
                Creates a limited Common User account. It does not create or
                grant access to a Patient profile.
              </p>

              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  setMessage('Creating accountâ€¦');

                  try {
                    await api('/auth/register', undefined, {
                      method: 'POST',
                      body: JSON.stringify(registration),
                    });

                    setMessage(
                      'Account created. Sign in, then request Patient linking if needed.'
                    );

                    setRegistering(false);
                  } catch (er) {
                    setMessage(err(er));
                  }
                }}
                aria-label="Create account form"
              >
                <label>
                  Full name
                  <input
                    required
                    value={registration.full_name}
                    onChange={(e) =>
                      setRegistration({
                        ...registration,
                        full_name: e.target.value,
                      })
                    }
                  />
                </label>

                <label>
                  Username
                  <input
                    required
                    minLength={3}
                    value={registration.username}
                    onChange={(e) =>
                      setRegistration({
                        ...registration,
                        username: e.target.value,
                      })
                    }
                  />
                </label>

                <label>
                  Email (optional)
                  <input
                    type="email"
                    value={registration.email}
                    onChange={(e) =>
                      setRegistration({
                        ...registration,
                        email: e.target.value,
                      })
                    }
                  />
                </label>

                <label>
                  Password
                  <input
                    required
                    minLength={8}
                    type="password"
                    value={registration.password}
                    onChange={(e) =>
                      setRegistration({
                        ...registration,
                        password: e.target.value,
                      })
                    }
                  />
                </label>

                <button type="submit">Create account</button>
              </form>

              <button
                type="button"
                className="secondary"
                onClick={() => {
                  setRegistering(false);
                  setMessage('');
                }}
              >
                Back to sign in
              </button>
            </>
          ) : (
            <>
              <h1>Sign in</h1>

              <p className="muted">
                Secure clinical-record workspace. Permissions are enforced by
                the API.
              </p>

              <form onSubmit={signIn} aria-label="Sign in form">
                <label>
                  Username
                  <input
                    autoComplete="username"
                    required
                    value={login.username}
                    onChange={(e) =>
                      setLogin({
                        ...login,
                        username: e.target.value,
                      })
                    }
                  />
                </label>

                <label>
                  Password
                  <input
                    autoComplete="current-password"
                    required
                    type="password"
                    value={login.password}
                    onChange={(e) =>
                      setLogin({
                        ...login,
                        password: e.target.value,
                      })
                    }
                  />
                </label>

                <button type="submit">Sign in</button>
              </form>

              <button
                type="button"
                className="secondary"
                onClick={() => {
                  setRegistering(true);
                  setMessage('');
                }}
              >
                Create Common User account
              </button>
              {ownerSetupAvailable && (
                <button
                  type="button"
                  className="secondary"
                  onClick={() => {
                    setOwnerSetupMode(true);
                    setMessage('');
                  }}
                >
                  First-time setup — Create Owner account
                </button>
              )}
            </>
          )}

          </>
          )}

          {message && (
            <div
              className="status"
              role="status"
              aria-live="polite"
            >
              {message}
            </div>
          )}
        </section>
      </main>
    );
  }

  const tabs = visibleTabs(user?.role);

  return (
    <>
      <a className="skip" href="#main">
        Skip to main content
      </a>

      <main className="shell">
        <aside aria-label="Primary navigation">
          <div className="brand">RecordGuard</div>

          <div className="role">
            {(user?.role || '').toUpperCase()}
          </div>

          <nav>
            {tabs.map((t) => (
              <button
                type="button"
                key={t}
                className={tab === t ? 'selected' : ''}
                onClick={() => {
                  setTab(t);
                  setMessage('');
                }}
              >
                {t}
              </button>
            ))}
          </nav>

          <button
            type="button"
            className="signout"
            onClick={signOut}
          >
            Sign out
          </button>
        </aside>

        <section className="workspace" id="main">
          <header>
            <div>
              <div className="eyebrow">
                Operational workspace
              </div>

              <strong>{tab}</strong>
            </div>

            <div className="profile">
              {user?.full_name}

              <small>{user?.organization_id}</small>
            </div>
          </header>

          <div className="content">
            <div className="breadcrumb">
              Workspace <span>/</span> {tab}
            </div>

            <View
              tab={tab}
              token={token}
              user={user}
              setTab={setTab}
              setMessage={setMessage}
            />

            {message && tab !== 'Dashboard' && (
              <div
                className="status"
                role="status"
                aria-live="polite"
              >
                {message}
              </div>
            )}
          </div>
        </section>
      </main>
    </>
  );
}

function visibleTabs(role?: string) {
  const tabs = ['Dashboard'];

  if (
    ['owner', 'admin', 'doctor', 'staff', 'patient'].includes(role || '')
  ) {
    tabs.push('Patients');
  }

  if (
    ['owner', 'admin', 'doctor', 'staff', 'patient'].includes(role || '')
  ) {
    tabs.push('Clinical');
  }

  if (
    ['owner', 'admin', 'doctor', 'staff', 'patient'].includes(role || '')
  ) {
    tabs.push('Medications');
  }

  if (
    ['owner', 'admin', 'doctor', 'staff', 'patient'].includes(role || '')
  ) {
    tabs.push('Timeline');
  }

  if (
    ['owner', 'admin', 'doctor', 'staff', 'patient'].includes(role || '')
  ) {
    tabs.push('Medicine Intelligence');
  }

  if (
    ['owner', 'admin', 'doctor', 'staff', 'patient'].includes(role || '')
  ) {
    tabs.push('Documents');
  }

  if (
    ['owner', 'admin', 'doctor', 'staff', 'patient'].includes(role || '')
  ) {
    tabs.push('Health Vault');
  }

  if (['owner', 'admin', 'doctor'].includes(role || '')) {
    tabs.push('Interoperability');
  }

  if (
    ['owner', 'admin', 'doctor', 'patient'].includes(role || '')
  ) {
    tabs.push('Governance');
  }

  if (
    ['owner', 'admin', 'doctor', 'patient'].includes(role || '')
  ) {
    tabs.push('Sharing');
  }

  if (role==='owner'||role==='admin') {
    tabs.push('Users');
  }

  if (role==='owner'||role==='admin') {
    tabs.push('Audit');
  }

  tabs.push('Settings');

  return tabs;
}

function View({
  tab,
  token,
  user,
  setTab,
  setMessage,
}: {
  tab: string;
  token: string;
  user: User | null;
  setTab: (s: string) => void;
  setMessage: (s: string) => void;
}) {
  if (tab === 'Patients') {
    return <Patients token={token} role={user?.role} setMessage={setMessage} />;
  }

  if (tab === 'Clinical') {
    return <Clinical token={token} role={user?.role} setMessage={setMessage} />;
  }

  if (tab === 'Medications') {
    return <Medications token={token} role={user?.role} setMessage={setMessage} />;
  }

  if (tab === 'Timeline') {
    return <Timeline token={token} role={user?.role} setMessage={setMessage} />;
  }

  if (tab === 'Medicine Intelligence') {
    return <MedicineIntelligence token={token} role={user?.role} setMessage={setMessage} />;
  }

  if (tab === 'Documents') {
    return <Documents token={token} role={user?.role} setMessage={setMessage} />;
  }

  if (tab === 'Health Vault') {
    return <HealthVault token={token} role={user?.role} setMessage={setMessage} />;
  }

  if (tab === 'Interoperability') {
    return <Interoperability token={token} role={user?.role} setMessage={setMessage} />;
  }

  if (tab === 'Governance') {
    return <Governance token={token} user={user} setMessage={setMessage} />;
  }

  if (tab === 'Sharing') {
    return <Sharing token={token} role={user?.role} setMessage={setMessage} />;
  }

  if (tab === 'Users') {
    return <Users token={token} role={user?.role} setMessage={setMessage} />;
  }

  if (tab === 'Audit') {
    return <Audit token={token} />;
  }

  if (tab === 'Settings') {
    return <Settings user={user} />;
  }

  return <Dashboard user={user} setTab={setTab} />;
}

function Dashboard({
  user,
  setTab,
}: {
  user: User | null;
  setTab: (s: string) => void;
}) {
  return (
    <>
      <div className="notice">
        <strong>Clinical trust workspace</strong>

        <p>
          RecordGuard separates identity, patient access, clinical
          records, sharing and governance. Authorization is enforced
          server-side and lifecycle actions remain auditable.
        </p>
      </div>

      <div className="grid">
        <article>
          <span>Identity</span>
          <strong>{user?.full_name || 'â€”'}</strong>
          <small>Authenticated account</small>
        </article>

        <article>
          <span>Organization</span>
          <strong>{user?.organization_id || 'â€”'}</strong>
          <small>Tenant boundary</small>
        </article>

        <article>
          <span>Access</span>
          <strong>{user?.role || 'â€”'}</strong>
          <small>Role-based permissions</small>
        </article>
      </div>

      <div className="actions">
        <button type="button" onClick={() => setTab('Patients')}>
          Open patient directory
        </button>

        <button type="button" onClick={() => setTab('Clinical')}>
          Open clinical records
        </button>

        <button type="button" onClick={() => setTab('Governance')}>
          Open governance
        </button>
      </div>
    </>
  );
}

function usePatients(token: string, setMessage: (s: string) => void) {
  const [patients, setPatients] = useState<Patient[]>([]);

  useEffect(() => {
    api('/patients', token)
      .then((d) => setPatients(d.items || []))
      .catch((e) => setMessage(err(e)));
  }, [token, setMessage]);

  return patients;
}

function PatientSelect({
  patients,
  pid,
  setPid,
}: {
  patients: Patient[];
  pid: string;
  setPid: (v: string) => void;
}) {
  return (
    <label>
      Patient
      <select value={pid} onChange={(e) => setPid(e.target.value)}>
        <option value="">Select patient</option>

        {patients.map((p) => (
          <option key={p.public_patient_id} value={p.public_patient_id}>
            {p.public_patient_id} â€” {p.name}
          </option>
        ))}
      </select>
    </label>
  );
}

function Patients({
  token,
  role,
  setMessage,
}: {
  token: string;
  role?: string;
  setMessage: (s: string) => void;
}) {
  const [items, setItems] = useState<Patient[]>([]);
  const [q, setQ] = useState('');
  const [selected, setSelected] = useState<Patient | null>(null);

  const [form, setForm] = useState({
    name: '',
    age: '',
    sex: '',
    blood_group: '',
    phone_number: '',
  });

  const canCreate = clinicalRoles.includes(role || '');

  async function load() {
    try {
      const path = q ? `/patients?q=${encodeURIComponent(q)}` : '/patients';
      setItems((await api(path, token)).items || []);
    } catch (e) {
      setMessage(err(e));
    }
  }

  useEffect(() => {
    const h = setTimeout(load, 180);
    return () => clearTimeout(h);
  }, [q]);

  async function create(e: React.FormEvent) {
    e.preventDefault();

    try {
      await api('/patients', token, {
        method: 'POST',
        body: JSON.stringify({
          ...form,
          age: Number(form.age),
        }),
      });

      setForm({
        name: '',
        age: '',
        sex: '',
        blood_group: '',
        phone_number: '',
      });

      setMessage('Patient registered.');
      load();
    } catch (e) {
      setMessage(err(e));
    }
  }

  return (
    <>
      <div className="toolbar">
        <input
          aria-label="Search patients"
          placeholder="Search patient ID, name or phone"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>

      <div className="split">
        <section className="panel">
          <h2>Patient directory</h2>

          {items.length === 0 ? (
            <div className="empty">No patients match this search.</div>
          ) : (
            <div className="table">
              {items.map((p) => (
                <button
                  type="button"
                  className="row"
                  key={p.public_patient_id}
                  onClick={() => setSelected(p)}
                >
                  <b>{p.public_patient_id}</b>
                  <span>{p.name}</span>
                  <small>
                    {p.sex} Â· {p.age} years Â·{' '}
                    {p.blood_group || 'Blood group not recorded'}
                  </small>
                </button>
              ))}
            </div>
          )}
        </section>

        {selected ? (
          <section className="panel">
            <h2>{selected.name}</h2>
            <p className="muted">{selected.public_patient_id}</p>

            <dl>
              <dt>Age</dt>
              <dd>{selected.age}</dd>

              <dt>Sex</dt>
              <dd>{selected.sex}</dd>

              <dt>Phone</dt>
              <dd>{selected.phone_number || 'Not recorded'}</dd>

              <dt>Blood group</dt>
              <dd>{selected.blood_group || 'Not recorded'}</dd>
            </dl>
          </section>
        ) : canCreate ? (
          <section className="panel">
            <h2>Register patient</h2>

            <form onSubmit={create}>
              <label>
                Name
                <input
                  required
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </label>

              <label>
                Age
                <input
                  required
                  type="number"
                  min="0"
                  max="150"
                  value={form.age}
                  onChange={(e) => setForm({ ...form, age: e.target.value })}
                />
              </label>

              <label>
                Sex
                <input
                  required
                  value={form.sex}
                  onChange={(e) => setForm({ ...form, sex: e.target.value })}
                />
              </label>

              <label>
                Blood group
                <input
                  value={form.blood_group}
                  onChange={(e) => setForm({ ...form, blood_group: e.target.value })}
                />
              </label>

              <label>
                Phone
                <input
                  value={form.phone_number}
                  onChange={(e) => setForm({ ...form, phone_number: e.target.value })}
                />
              </label>

              <button type="submit">Register patient</button>
            </form>
          </section>
        ) : null}
      </div>
    </>
  );
}

function Clinical({
  token,
  role,
  setMessage,
}: {
  token: string;
  role?: string;
  setMessage: (s: string) => void;
}) {
  const patients = usePatients(token, setMessage);
  const [pid, setPid] = useState('');
  const [view, setView] = useState<'encounters' | 'prescriptions'>('encounters');
  const [includeArchived, setIncludeArchived] = useState(false);
  const [encounters, setEncounters] = useState<Encounter[]>([]);
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);

  const [encForm, setEncForm] = useState({
    visit_date: '',
    visit_type: '',
    chief_complaint: '',
    visit_notes: '',
    diagnoses: '',
  });

  const [rxForm, setRxForm] = useState({
    medicine_name: '',
    dosage: '',
    frequency: '',
    duration: '',
    instructions: '',
    encounter_id: '',
  });

  const canCreate = clinicalRoles.includes(role || '');
  const canDestructive = destructiveRoles.includes(role || '');

  async function load() {
    if (!pid) return;

    try {
      const [e, r] = await Promise.all([
        api(`/patients/${encodeURIComponent(pid)}/encounters?include_archived=${includeArchived}`, token),
        api(`/patients/${encodeURIComponent(pid)}/prescriptions?include_archived=${includeArchived}`, token),
      ]);

      setEncounters(e.items || []);
      setPrescriptions(r.items || []);
    } catch (e) {
      setMessage(err(e));
    }
  }

  useEffect(() => {
    load();
  }, [pid, includeArchived]);

  async function createEncounter(e: React.FormEvent) {
    e.preventDefault();

    try {
      await api('/encounters', token, {
        method: 'POST',
        body: JSON.stringify({
          patient_id: pid,
          ...encForm,
        }),
      });

      setEncForm({
        visit_date: '',
        visit_type: '',
        chief_complaint: '',
        visit_notes: '',
        diagnoses: '',
      });

      setMessage('Encounter added.');
      load();
    } catch (e) {
      setMessage(err(e));
    }
  }

  async function createRx(e: React.FormEvent) {
    e.preventDefault();

    try {
      await api('/prescriptions', token, {
        method: 'POST',
        body: JSON.stringify({
          patient_id: pid,
          ...rxForm,
          encounter_id: rxForm.encounter_id || null,
        }),
      });

      setRxForm({
        medicine_name: '',
        dosage: '',
        frequency: '',
        duration: '',
        instructions: '',
        encounter_id: '',
      });

      setMessage('Prescription added.');
      load();
    } catch (e) {
      setMessage(err(e));
    }
  }

  const lifecycle = async (
    type: string,
    id: string,
    action: string,
    needsAuth = false
  ) => {
    try {
      let body: string | undefined;

      if (needsAuth) {
        const password = window.prompt('Enter your current password to continue:') || '';
        if (!password) {
          setMessage('Destructive action cancelled.');
          return;
        }

        const confirmation = window.prompt('Type DELETE to confirm this destructive action:') || '';
        if (confirmation !== 'DELETE') {
          setMessage('Destructive action cancelled. Exact DELETE confirmation is required.');
          return;
        }

        body = destructivePayload(password);
      }

      await api(`/ehr/${type}/${encodeURIComponent(id)}/${action}`, token, {
        method: 'POST',
        body,
      });

      setMessage(`${action.replaceAll('_', ' ')} completed.`);
      await load();
    } catch (e) {
      setMessage(err(e));
    }
  };

  return (
    <>
      <section className="panel">
        <div className="toolbar">
          <PatientSelect
            patients={patients}
            pid={pid}
            setPid={(v) => {
              setPid(v);
              setEncounters([]);
              setPrescriptions([]);
            }}
          />

          <div className="segmented">
            <button
              type="button"
              className={view === 'encounters' ? 'selected' : ''}
              onClick={() => setView('encounters')}
            >
              Encounters
            </button>

            <button
              type="button"
              className={view === 'prescriptions' ? 'selected' : ''}
              onClick={() => setView('prescriptions')}
            >
              Prescriptions
            </button>

            <label className="check">
              <input
                type="checkbox"
                checked={includeArchived}
                onChange={(e) => setIncludeArchived(e.target.checked)}
              />
              Include archived/deleted
            </label>
          </div>
        </div>

        {!pid ? (
          <div className="empty">Select a patient to review clinical records.</div>
        ) : view === 'encounters' ? (
          <div className="table">
            {encounters.length ? (
              encounters.map((x) => (
                <div className="row static" key={x.encounter_id}>
                  <b>{x.visit_date}</b>
                  <span>
                    {x.visit_type || 'Encounter'} Â· {x.chief_complaint || 'No chief complaint'}
                  </span>
                  <small>
                    <StatusBadge status={x.lifecycle_status} />
                    {x.encounter_id ? ` Â· ${x.encounter_id}` : ''}
                    <LifecycleButtons
                      type="encounter"
                      id={x.encounter_id}
                      status={x.lifecycle_status}
                      role={role}
                      onAction={lifecycle}
                      canDestructive={canDestructive}
                    />
                  </small>
                </div>
              ))
            ) : (
              <div className="empty">No encounters found.</div>
            )}
          </div>
        ) : (
          <div className="table">
            {prescriptions.length ? (
              prescriptions.map((x) => (
                <div className="row static" key={x.prescription_id}>
                  <b>{x.medicine_name}</b>
                  <span>
                    {[x.dosage, x.frequency, x.duration].filter(Boolean).join(' Â· ') || 'Dose details not recorded'}
                  </span>
                  <small>
                    <StatusBadge status={x.lifecycle_status} />
                    {x.prescription_id ? ` Â· ${x.prescription_id}` : ''}
                    <LifecycleButtons
                      type="prescription"
                      id={x.prescription_id}
                      status={x.lifecycle_status}
                      role={role}
                      onAction={lifecycle}
                      canDestructive={canDestructive}
                    />
                  </small>
                </div>
              ))
            ) : (
              <div className="empty">No prescriptions found.</div>
            )}
          </div>
        )}
      </section>

      {pid && canCreate && view === 'encounters' && (
        <section className="panel">
          <h2>Add encounter</h2>

          <form onSubmit={createEncounter}>
            <label>
              Visit date/time
              <input
                required
                value={encForm.visit_date}
                onChange={(e) => setEncForm({ ...encForm, visit_date: e.target.value })}
                placeholder="YYYY-MM-DD"
              />
            </label>

            <label>
              Visit type
              <input
                value={encForm.visit_type}
                onChange={(e) => setEncForm({ ...encForm, visit_type: e.target.value })}
              />
            </label>

            <label>
              Chief complaint
              <input
                value={encForm.chief_complaint}
                onChange={(e) => setEncForm({ ...encForm, chief_complaint: e.target.value })}
              />
            </label>

            <label>
              Visit notes
              <textarea
                value={encForm.visit_notes}
                onChange={(e) => setEncForm({ ...encForm, visit_notes: e.target.value })}
              />
            </label>

            <label>
              Documented assessment
              <textarea
                value={encForm.diagnoses}
                onChange={(e) => setEncForm({ ...encForm, diagnoses: e.target.value })}
              />
            </label>

            <button type="submit">Add encounter</button>
          </form>
        </section>
      )}

      {pid && canCreate && view === 'prescriptions' && (
        <section className="panel">
          <h2>Add prescription</h2>

          <form onSubmit={createRx}>
            <label>
              Medicine
              <input
                required
                value={rxForm.medicine_name}
                onChange={(e) => setRxForm({ ...rxForm, medicine_name: e.target.value })}
              />
            </label>

            <label>
              Dosage
              <input
                value={rxForm.dosage}
                onChange={(e) => setRxForm({ ...rxForm, dosage: e.target.value })}
              />
            </label>

            <label>
              Frequency
              <input
                value={rxForm.frequency}
                onChange={(e) => setRxForm({ ...rxForm, frequency: e.target.value })}
              />
            </label>

            <label>
              Duration
              <input
                value={rxForm.duration}
                onChange={(e) => setRxForm({ ...rxForm, duration: e.target.value })}
              />
            </label>

            <label>
              Instructions
              <textarea
                value={rxForm.instructions}
                onChange={(e) => setRxForm({ ...rxForm, instructions: e.target.value })}
              />
            </label>

            <label>
              Encounter ID (optional)
              <input
                value={rxForm.encounter_id}
                onChange={(e) => setRxForm({ ...rxForm, encounter_id: e.target.value })}
              />
            </label>

            <button type="submit">Add prescription</button>
          </form>
        </section>
      )}
    </>
  );
}

function LifecycleButtons({
  type,
  id,
  status,
  role,
  onAction,
  canDestructive,
}: {
  type: string;
  id?: string;
  status?: string;
  role?: string;
  onAction: (t: string, i: string, a: string, n?: boolean) => void;
  canDestructive: boolean;
}) {
  if (!id) return null;

  const s = status || 'ACTIVE';
  const actions: React.ReactNode[] = [];

  if (clinicalRoles.includes(role || '') && s === 'ACTIVE') {
    actions.push(
      <button type="button" key="archive" onClick={() => onAction(type, id, 'archive')}>
        Archive
      </button>
    );
  }

  if (['owner', 'admin'].includes(role || '') && s === 'ARCHIVED') {
    actions.push(
      <button type="button" key="recover" onClick={() => onAction(type, id, 'recover')}>
        Recover
      </button>
    );
  }

  if (canDestructive && s === 'ARCHIVED') {
    actions.push(
      <button type="button" key="delete" className="danger" onClick={() => onAction(type, id, 'admin-delete', true)}>
        Admin delete
      </button>
    );
  }

  if (role === 'owner' && s === 'ADMIN_DELETED') {
    actions.push(
      <button type="button" key="owner-recover" onClick={() => onAction(type, id, 'owner-recover')}>
        Owner recover
      </button>
    );
  }

  if (role === 'owner' && s === 'ADMIN_DELETED') {
    actions.push(
      <button type="button" key="destroy" className="danger" onClick={() => onAction(type, id, 'permanent-destroy', true)}>
        Destroy
      </button>
    );
  }

  return actions.length ? <span className="lifecycle">{actions}</span> : null;
}

function Medications({
  token,
  role,
  setMessage,
}: {
  token: string;
  role?: string;
  setMessage: (s: string) => void;
}) {
  const patients = usePatients(token, setMessage);
  const [pid, setPid] = useState('');
  const [items, setItems] = useState<Medication[]>([]);
  const [includeArchived, setIncludeArchived] = useState(false);

  const [form, setForm] = useState({
    medicine_name: '',
    response_type: '',
    reaction: '',
    severity: '',
    reason: '',
    notes: '',
  });

  const canCreate = clinicalRoles.includes(role || '');
  const canDestructive = destructiveRoles.includes(role || '');

  async function load() {
    if (!pid) return;

    try {
      setItems(
        (await api(`/patients/${encodeURIComponent(pid)}/medications?include_archived=${includeArchived}`, token)).items || []
      );
    } catch (e) {
      setMessage(err(e));
    }
  }

  useEffect(() => {
    load();
  }, [pid, includeArchived]);

  async function create(e: React.FormEvent) {
    e.preventDefault();

    try {
      await api('/medications', token, {
        method: 'POST',
        body: JSON.stringify({
          patient_id: pid,
          ...form,
        }),
      });

      setForm({
        medicine_name: '',
        response_type: '',
        reaction: '',
        severity: '',
        reason: '',
        notes: '',
      });

      setMessage('Medication record added.');
      load();
    } catch (e) {
      setMessage(err(e));
    }
  }

  const lifecycle = async (id: string, action: string, needsAuth = false) => {
    try {
      let body: string | undefined;

      if (needsAuth) {
        const password = window.prompt('Enter your current password to continue:') || '';
        if (!password) {
          setMessage('Destructive action cancelled.');
          return;
        }

        const confirmation = window.prompt('Type DELETE to confirm this destructive action:') || '';
        if (confirmation !== 'DELETE') {
          setMessage('Destructive action cancelled. Exact DELETE confirmation is required.');
          return;
        }

        body = destructivePayload(password);
      }

      await api(`/medications/${encodeURIComponent(id)}/${action}`, token, {
        method: 'POST',
        body,
      });

      setMessage(`${action.replaceAll('_', ' ')} completed.`);
      await load();
    } catch (e) {
      setMessage(err(e));
    }
  };

  return (
    <>
      <section className="panel">
        <PatientSelect patients={patients} pid={pid} setPid={setPid} />

        <label className="check">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(e) => setIncludeArchived(e.target.checked)}
          />
          Include archived/deleted
        </label>

        {!pid ? (
          <div className="empty">Select a patient to review medication history.</div>
        ) : (
          <div className="table">
            {items.length ? (
              items.map((m, i) => (
                <div className="row static" key={m.record_id || m.medication_id || i}>
                  <b>{m.medicine_name}</b>
                  <span>
                    {m.response_type || 'Response not recorded'}
                    {m.severity ? ` Â· ${m.severity}` : ''}
                  </span>
                  <small>
                    <StatusBadge status={m.lifecycle_status} />
                    {' Â· '}
                    {m.created_at || ''}

                    {m.record_id && (
                      <span className="lifecycle">
                        {clinicalRoles.includes(role || '') && m.lifecycle_status === 'ACTIVE' && (
                          <button type="button" onClick={() => lifecycle(m.record_id!, 'archive')}>
                            Archive
                          </button>
                        )}

                        {['owner', 'admin'].includes(role || '') && m.lifecycle_status === 'ARCHIVED' && (
                          <button type="button" onClick={() => lifecycle(m.record_id!, 'recover')}>
                            Recover
                          </button>
                        )}

                        {canDestructive && m.lifecycle_status === 'ARCHIVED' && (
                          <button type="button" className="danger" onClick={() => lifecycle(m.record_id!, 'admin-delete', true)}>
                            Admin delete
                          </button>
                        )}

                        {role === 'owner' && m.lifecycle_status === 'ADMIN_DELETED' && (
                          <button type="button" onClick={() => lifecycle(m.record_id!, 'owner-recover')}>
                            Owner recover
                          </button>
                        )}

                        {role === 'owner' && m.lifecycle_status === 'ADMIN_DELETED' && (
                          <button type="button" className="danger" onClick={() => lifecycle(m.record_id!, 'permanent-destroy', true)}>
                            Destroy
                          </button>
                        )}
                      </span>
                    )}
                  </small>
                </div>
              ))
            ) : (
              <div className="empty">No medication records found.</div>
            )}
          </div>
        )}
      </section>

      {pid && canCreate && (
        <section className="panel">
          <h2>Add medication record</h2>
          <p className="form-help">
            This is a historical clinical record, not an independent medication recommendation.
          </p>

          <form onSubmit={create}>
            <label>
              Medicine
              <input
                required
                value={form.medicine_name}
                onChange={(e) => setForm({ ...form, medicine_name: e.target.value })}
              />
            </label>

            <label>
              Response type
              <input
                required
                value={form.response_type}
                onChange={(e) => setForm({ ...form, response_type: e.target.value })}
              />
            </label>

            <label>
              Reaction
              <input
                value={form.reaction}
                onChange={(e) => setForm({ ...form, reaction: e.target.value })}
              />
            </label>

            <label>
              Severity
              <input
                value={form.severity}
                onChange={(e) => setForm({ ...form, severity: e.target.value })}
              />
            </label>

            <label>
              Reason
              <input
                value={form.reason}
                onChange={(e) => setForm({ ...form, reason: e.target.value })}
              />
            </label>

            <label>
              Notes
              <textarea
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
              />
            </label>

            <button type="submit">Add record</button>
          </form>
        </section>
      )}
    </>
  );
}

function Documents({
  token,
  role,
  setMessage,
}: {
  token: string;
  role?: string;
  setMessage: (s: string) => void;
}) {
  const patients = usePatients(token, setMessage);
  const [pid, setPid] = useState('');
  const [items, setItems] = useState<GenericRow[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    if (!pid) return;

    try {
      setItems((await api(`/patients/${encodeURIComponent(pid)}/attachments`, token)).items || []);
    } catch (e) {
      setMessage(err(e));
    }
  }

  useEffect(() => {
    load();
  }, [pid]);

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!pid || !file) return;

    setBusy(true);

    try {
      const fd = new FormData();
      fd.append('file', file);

      await api(`/patients/${encodeURIComponent(pid)}/attachments`, token, {
        method: 'POST',
        body: fd,
      });

      setFile(null);
      const input = document.getElementById('rg-file') as HTMLInputElement | null;
      if (input) {
        input.value = '';
      }

      setMessage('Document uploaded.');
      load();
    } catch (e) {
      setMessage(err(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <section className="panel">
        <h2>Documents &amp; evidence</h2>
        <p className="muted">
          Upload validated patient evidence. Internal storage paths are never exposed to the client.
        </p>

        <PatientSelect patients={patients} pid={pid} setPid={setPid} />

        {pid && (
          <form onSubmit={upload}>
            <label>
              Document
              <input
                id="rg-file"
                required
                type="file"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </label>

            <div className="form-help">Maximum 20 MB. The server validates file content and authorization.</div>

            <button type="submit" disabled={busy || !file}>
              {busy ? 'Uploadingâ€¦' : 'Upload document'}
            </button>
          </form>
        )}
      </section>

      {pid && (
        <section className="panel">
          <h2>Patient evidence</h2>

          {items.length ? (
            <div className="table">
              {items.map((x, i) => (
                <div className="row static" key={x.attachment_id || i}>
                  <b>{x.original_name || 'Document'}</b>
                  <span>{x.mime_type || 'Unknown type'}</span>
                  <small>
                    {x.created_at || ''} Â· {x.attachment_id || ''}
                    <a
                      className="inline-link"
                      href={`${API}/attachments/${encodeURIComponent(x.attachment_id)}/download`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Download
                    </a>
                  </small>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty">No documents have been uploaded for this patient.</div>
          )}
        </section>
      )}
    </>
  );
}

function Governance({
  token,
  user,
  setMessage,
}: {
  token: string;
  user: User | null;
  setMessage: (s: string) => void;
}) {
  const role = user?.role || '';
  const patients = usePatients(token, setMessage);
  const [pid, setPid] = useState(user?.patient_id || '');
  const [relationships, setRelationships] = useState<GenericRow[]>([]);
  const [access, setAccess] = useState<GenericRow[]>([]);
  const [links, setLinks] = useState<GenericRow[]>([]);
  const [corrections, setCorrections] = useState<GenericRow[]>([]);

  const [familyForm, setFamilyForm] = useState({
    related_patient_id: '',
    relationship_type: 'caregiver',
  });

  const [grantForm, setGrantForm] = useState({
    grantee_user_id: '',
    resource_type: 'documents',
    permission: 'view',
  });

  const [linkForm, setLinkForm] = useState({
    patient_id: user?.patient_id || '',
    reason: '',
  });

  const [corrForm, setCorrForm] = useState({
    resource_type: 'medication',
    resource_id: '',
    requested_change: '',
    reason: '',
  });

  const canReview = ['owner', 'admin'].includes(role);

  async function load() {
    if (pid) {
      try {
        const [r, a] = await Promise.all([
          api(`/family/relationships?patient_id=${encodeURIComponent(pid)}`, token),
          api(`/family/access?patient_id=${encodeURIComponent(pid)}`, token),
        ]);

        setRelationships(r.items || []);
        setAccess(a.items || []);
      } catch (e) {
        setMessage(err(e));
      }
    }

    if (['owner', 'admin'].includes(role)) {
      try {
        setLinks((await api('/patient-links', token)).items || []);
      } catch (e) {
        setMessage(err(e));
      }
    }

    if (canReview) {
      try {
        setCorrections(
          (await api(`/correction-requests${pid ? `?patient_id=${encodeURIComponent(pid)}` : ''}`, token)).items || []
        );
      } catch (e) {
        setMessage(err(e));
      }
    }
  }

  useEffect(() => {
    load();
  }, [pid, role]);

  async function addFamily(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api('/family/relationships', token, {
        method: 'POST',
        body: JSON.stringify({
          patient_id: pid,
          ...familyForm,
        }),
      });

      setFamilyForm({
        related_patient_id: '',
        relationship_type: 'caregiver',
      });

      setMessage('Family relationship added.');
      load();
    } catch (e) {
      setMessage(err(e));
    }
  }

  async function grant(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api('/family/access', token, {
        method: 'POST',
        body: JSON.stringify({
          patient_id: pid,
          ...grantForm,
        }),
      });

      setGrantForm({
        ...grantForm,
        grantee_user_id: '',
      });

      setMessage('Family access granted.');
      load();
    } catch (e) {
      setMessage(err(e));
    }
  }

  async function revokeGrant(id: string) {
    try {
      await api('/family/access/revoke', token, {
        method: 'POST',
        body: JSON.stringify({ grant_id: id }),
      });

      setMessage('Family access revoked.');
      load();
    } catch (e) {
      setMessage(err(e));
    }
  }

  async function requestLink(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api('/patient-links/request', token, {
        method: 'POST',
        body: JSON.stringify(linkForm),
      });

      setMessage('Patient-link request submitted for review.');
    } catch (e) {
      setMessage(err(e));
    }
  }

  async function reviewLink(id: string, decision: string) {
    try {
      await api('/patient-links/review', token, {
        method: 'POST',
        body: JSON.stringify({
          request_id: id,
          decision,
          notes: '',
        }),
      });

      setMessage(`Link request ${decision.toLowerCase()}.`);
      load();
    } catch (e) {
      setMessage(err(e));
    }
  }

  async function createCorrection(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api('/correction-requests', token, {
        method: 'POST',
        body: JSON.stringify({
          patient_id: pid,
          ...corrForm,
        }),
      });

      setCorrForm({
        ...corrForm,
        resource_id: '',
        requested_change: '',
        reason: '',
      });

      setMessage('Correction request submitted.');
      load();
    } catch (e) {
      setMessage(err(e));
    }
  }

  async function reviewCorrection(id: string, decision: string) {
    try {
      await api('/correction-requests/review', token, {
        method: 'POST',
        body: JSON.stringify({
          request_id: id,
          decision,
          notes: '',
        }),
      });

      setMessage(`Correction request ${decision.toLowerCase()}.`);
      load();
    } catch (e) {
      setMessage(err(e));
    }
  }

  return (
    <>
      <section className="panel">
        <h2>Governance center</h2>
        <p className="muted">
          Identity linking, family relationships, scoped family access and record-correction requests are explicit workflows.
        </p>

        <PatientSelect patients={patients} pid={pid} setPid={(v) => setPid(v)} />
      </section>

      {role === 'patient' && (
        <section className="panel">
          <h2>Request patient link</h2>
          <form onSubmit={requestLink}>
            <label>
              Patient ID
              <input
                required
                value={linkForm.patient_id}
                onChange={(e) => setLinkForm({ ...linkForm, patient_id: e.target.value })}
              />
            </label>

            <label>
              Reason
              <textarea
                value={linkForm.reason}
                onChange={(e) => setLinkForm({ ...linkForm, reason: e.target.value })}
              />
            </label>

            <button type="submit">Submit link request</button>
          </form>
        </section>
      )}

      {pid && (
        <>
          <section className="panel">
            <h2>Family relationships</h2>

            {relationships.length ? (
              <div className="table">
                {relationships.map((x, i) => (
                  <div className="row static" key={x.relationship_id || i}>
                    <b>{x.relationship_type || 'Relationship'}</b>
                    <span>
                      {x.public_patient_id || x.related_patient_id || 'â€”'} Â· {x.related_name || ''}
                    </span>
                    <small>{x.created_at || ''}</small>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty">No family relationships recorded.</div>
            )}

            {role !== 'patient' || user?.patient_id === pid ? (
              <form onSubmit={addFamily}>
                <label>
                  Related Patient ID
                  <input
                    required
                    value={familyForm.related_patient_id}
                    onChange={(e) => setFamilyForm({ ...familyForm, related_patient_id: e.target.value })}
                  />
                </label>

                <label>
                  Relationship
                  <select
                    value={familyForm.relationship_type}
                    onChange={(e) => setFamilyForm({ ...familyForm, relationship_type: e.target.value })}
                  >
                    <option value="caregiver">Caregiver</option>
                    <option value="parent">Parent</option>
                    <option value="child">Child</option>
                    <option value="spouse_partner">Spouse / partner</option>
                    <option value="sibling">Sibling</option>
                    <option value="guardian">Guardian</option>
                    <option value="dependent">Dependent</option>
                    <option value="other">Other</option>
                  </select>
                </label>

                <button type="submit">Add relationship</button>
              </form>
            ) : null}
          </section>

          <section className="panel">
            <h2>Scoped family access</h2>

            {access.length ? (
              <div className="table">
                {access.map((x, i) => (
                  <div className="row static" key={x.grant_id || i}>
                    <b>{x.username || x.grantee_user_id}</b>
                    <span>
                      {x.resource_type || 'resource'} Â· {x.permission || 'view'}
                    </span>
                    <small>
                      {x.status || 'ACTIVE'}
                      {x.grant_id && (
                        <button type="button" onClick={() => revokeGrant(x.grant_id)}>
                          Revoke
                        </button>
                      )}
                    </small>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty">No family access grants.</div>
            )}

            {['owner', 'admin', 'patient'].includes(role) && (
              <form onSubmit={grant}>
                <label>
                  Grantee user ID
                  <input
                    required
                    value={grantForm.grantee_user_id}
                    onChange={(e) => setGrantForm({ ...grantForm, grantee_user_id: e.target.value })}
                  />
                </label>

                <label>
                  Resource
                  <select
                    value={grantForm.resource_type}
                    onChange={(e) => setGrantForm({ ...grantForm, resource_type: e.target.value })}
                  >
                    <option value="documents">Documents</option>
                    <option value="medication">Medication</option>
                    <option value="ehr">Clinical records</option>
                    <option value="appointments">Appointments</option>
                  </select>
                </label>

                <label>
                  Permission
                  <select
                    value={grantForm.permission}
                    onChange={(e) => setGrantForm({ ...grantForm, permission: e.target.value })}
                  >
                    <option value="view">View</option>
                    <option value="restrict">Restrict</option>
                  </select>
                </label>

                <button type="submit">Grant scoped access</button>
              </form>
            )}
          </section>

          {role === 'patient' && (
            <section className="panel">
              <h2>Request a correction</h2>

              <form onSubmit={createCorrection}>
                <label>
                  Resource type
                  <select
                    value={corrForm.resource_type}
                    onChange={(e) => setCorrForm({ ...corrForm, resource_type: e.target.value })}
                  >
                    <option value="medication">Medication</option>
                    <option value="encounter">Encounter</option>
                    <option value="prescription">Prescription</option>
                    <option value="document">Document</option>
                  </select>
                </label>

                <label>
                  Resource ID
                  <input
                    required
                    value={corrForm.resource_id}
                    onChange={(e) => setCorrForm({ ...corrForm, resource_id: e.target.value })}
                  />
                </label>

                <label>
                  Requested change
                  <textarea
                    required
                    value={corrForm.requested_change}
                    onChange={(e) => setCorrForm({ ...corrForm, requested_change: e.target.value })}
                  />
                </label>

                <label>
                  Reason
                  <textarea
                    value={corrForm.reason}
                    onChange={(e) => setCorrForm({ ...corrForm, reason: e.target.value })}
                  />
                </label>

                <button type="submit">Submit correction request</button>
              </form>
            </section>
          )}

          {['owner', 'admin'].includes(role) && (
            <section className="panel">
              <h2>Patient-link review</h2>

              {links.length ? (
                <div className="table">
                  {links.map((x, i) => (
                    <div className="row static" key={x.request_id || i}>
                      <b>{x.public_patient_id || x.patient_id}</b>
                      <span>{x.username || x.user_id} Â· {x.status}</span>
                      <small>
                        {x.reason_context || 'No reason provided'}
                        {x.status === 'PENDING' && (
                          <span className="lifecycle">
                            <button type="button" onClick={() => reviewLink(x.request_id, 'APPROVED')}>
                              Approve
                            </button>
                            <button type="button" className="danger" onClick={() => reviewLink(x.request_id, 'REJECTED')}>
                              Reject
                            </button>
                          </span>
                        )}
                      </small>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty">No patient-link requests.</div>
              )}
            </section>
          )}

          {canReview && (
            <section className="panel">
              <h2>Correction review</h2>

              {corrections.length ? (
                <div className="table">
                  {corrections.map((x, i) => (
                    <div className="row static" key={x.request_id || i}>
                      <b>#{x.request_id}</b>
                      <span>{x.resource_type} Â· {x.resource_id} Â· {x.status}</span>
                      <small>
                        {x.requested_change || x.reason || ''}
                        {['Pending', 'PENDING'].includes(x.status) && (
                          <span className="lifecycle">
                            <button type="button" onClick={() => reviewCorrection(x.request_id, 'Approved')}>
                              Approve
                            </button>
                            <button type="button" className="danger" onClick={() => reviewCorrection(x.request_id, 'Rejected')}>
                              Reject
                            </button>
                          </span>
                        )}
                      </small>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty">No correction requests.</div>
              )}
            </section>
          )}
        </>
      )}
    </>
  );
}

function Timeline({
  token,
  role,
  setMessage,
}: {
  token: string;
  role?: string;
  setMessage: (s: string) => void;
}) {
  const patients = usePatients(token, setMessage);
  const [pid, setPid] = useState('');
  const [patient, setPatient] = useState<Patient | null>(null);
  const [meds, setMeds] = useState<Medication[]>([]);
  const [encounters, setEncounters] = useState<Encounter[]>([]);
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [documents, setDocuments] = useState<GenericRow[]>([]);
  const [busy, setBusy] = useState(false);

  async function load() {
    if (!pid) return;
    setBusy(true);

    try {
      const [p, m, e, r, d] = await Promise.all([
        api(`/patients/${encodeURIComponent(pid)}`, token),
        api(`/patients/${encodeURIComponent(pid)}/medications`, token),
        api(`/patients/${encodeURIComponent(pid)}/encounters`, token),
        api(`/patients/${encodeURIComponent(pid)}/prescriptions`, token),
        api(`/patients/${encodeURIComponent(pid)}/attachments`, token),
      ]);

      setPatient(p.patient || p);
      setMeds(m.items || []);
      setEncounters(e.items || []);
      setPrescriptions(r.items || []);
      setDocuments(d.items || []);
    } catch (e) {
      setMessage(err(e));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    load();
  }, [pid]);

  const events = [
    ...encounters.map((x) => ({
      date: x.visit_date || x.created_at || '',
      kind: 'Encounter',
      title: x.visit_type || 'Clinical encounter',
      detail: x.chief_complaint || x.visit_notes || '',
    })),
    ...prescriptions.map((x) => ({
      date: x.created_at || '',
      kind: 'Prescription',
      title: x.medicine_name,
      detail: [x.dosage, x.frequency, x.duration].filter(Boolean).join(' Â· '),
    })),
    ...meds.map((x) => ({
      date: x.created_at || '',
      kind: 'Medication history',
      title: x.medicine_name,
      detail: [x.response_type, x.reaction, x.severity].filter(Boolean).join(' Â· '),
    })),
    ...documents.map((x) => ({
      date: x.created_at || '',
      kind: 'Document',
      title: x.original_name || 'Evidence document',
      detail: x.mime_type || '',
    })),
  ].sort((a, b) => String(b.date).localeCompare(String(a.date)));

  const alerts = meds.filter((x) =>
    ['ALLERGY', 'ADVERSE REACTION'].includes(String(x.response_type || '').toUpperCase())
  );

  return (
    <>
      <section className="panel">
        <h2>Patient timeline</h2>
        <p className="muted">
          A chronological evidence view assembled from authorized clinical records.
        </p>

        <PatientSelect patients={patients} pid={pid} setPid={setPid} />
      </section>

      {pid && (
        <>
          {patient && (
            <section className="grid">
              <article>
                <span>Patient</span>
                <strong>{patient.name}</strong>
                <small>{patient.public_patient_id}</small>
              </article>

              <article>
                <span>Clinical activity</span>
                <strong>{encounters.length + prescriptions.length + meds.length}</strong>
                <small>Recorded clinical items</small>
              </article>

              <article>
                <span>Safety history</span>
                <strong>{alerts.length}</strong>
                <small>Historical allergy/adverse-response records</small>
              </article>
            </section>
          )}

          <section className="panel">
            <h2>Safety Passport</h2>
            {alerts.length ? (
              <div className="alert-list">
                {alerts.map((x, i) => (
                  <div className="alert" key={i}>
                    <b>{String(x.response_type || 'Historical warning')}</b>
                    <span>
                      {x.medicine_name}
                      {x.reaction ? ` Â· ${x.reaction}` : ''}
                    </span>
                    <small>Historical record only; verify source record before clinical action.</small>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty">No historical allergy or adverse-response medication records found.</div>
            )}
          </section>

          <section className="panel">
            <div className="toolbar">
              <h2>Evidence timeline</h2>
              {busy && <span className="muted">Loadingâ€¦</span>}
            </div>

            {events.length ? (
              <div className="timeline">
                {events.map((x, i) => (
                  <article className="timeline-item" key={`${x.kind}-${x.date}-${i}`}>
                    <div className="timeline-marker" />
                    <div>
                      <small>
                        {x.date || 'Date not recorded'} Â· {x.kind}
                      </small>
                      <h3>{x.title}</h3>
                      <p>{x.detail || 'No additional detail recorded.'}</p>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className="empty">No timeline events found for this patient.</div>
            )}
          </section>
        </>
      )}
    </>
  );
}

function MedicineIntelligence({
  token,
  role,
  setMessage,
}: {
  token: string;
  role?: string;
  setMessage: (s: string) => void;
}) {
  const patients = usePatients(token, setMessage);
  const [pid, setPid] = useState('');
  const [medicine, setMedicine] = useState('');
  const [items, setItems] = useState<Medication[]>([]);
  const [searched, setSearched] = useState(false);

  async function search(e: React.FormEvent) {
    e.preventDefault();
    if (!pid || !medicine) return;

    try {
      const d = await api(`/patients/${encodeURIComponent(pid)}/medications`, token);
      const all = (d.items || []) as Medication[];

      setItems(
        all.filter(
          (x) =>
            String(x.medicine_name || '')
              .trim()
              .toLowerCase() === medicine.trim().toLowerCase()
        )
      );

      setSearched(true);
    } catch (e) {
      setMessage(err(e));
    }
  }

  const counts = items.reduce((a, x) => {
    const k = String(x.response_type || 'Unknown');
    a[k] = (a[k] || 0) + 1;
    return a;
  }, {} as Record<string, number>);

  const alerts = Object.entries(counts).filter(([k]) =>
    ['Allergy', 'Adverse reaction', 'Ineffective'].includes(k)
  );

  return (
    <>
      <section className="panel">
        <h2>Medicine Intelligence</h2>
        <p className="muted">Historical review only: this feature does not diagnose, prescribe, or provide a personalized yes/no safety decision.</p>
        <form onSubmit={search}>
          <PatientSelect patients={patients} pid={pid} setPid={setPid} />

          <label>
            Medicine name
            <input
              required
              value={medicine}
              onChange={(e) => setMedicine(e.target.value)}
              placeholder="e.g. paracetamol"
            />
          </label>

          <button type="submit">Review historical pattern</button>
        </form>
      </section>

      {searched && (
        <section className="panel">
          <h2>Historical summary</h2>

          <div className="grid">
            {Object.entries(counts).map(([k, v]) => (
              <article key={k}>
                <span>{k}</span>
                <strong>{v}</strong>
                <small>Recorded response</small>
              </article>
            ))}
          </div>

          <div className="table">
            {items.map((x, i) => (
              <div className="row static" key={x.record_id || i}>
                <b>{x.medicine_name}</b>
                <span>{x.response_type || 'Unknown response'}</span>
                <small>
                  {[x.reaction, x.severity, x.reason].filter(Boolean).join(' Â· ') || 'No additional detail recorded.'}
                </small>
              </div>
            ))}
          </div>
        </section>
      )}
    </>
  );
}

function Sharing({
  token,
  role,
  setMessage,
}: {
  token: string;
  role?: string;
  setMessage: (s: string) => void;
}) {
  const patients = usePatients(token, setMessage);
  const [pid, setPid] = useState('');
  const [items, setItems] = useState<GenericRow[]>([]);
  const [form, setForm] = useState({
    record_id: '',
    resource_type: 'medication',
    shared_with: '',
    expires_at: '',
  });

  const [redeemToken, setRedeemToken] = useState('');
  const [redeemed, setRedeemed] = useState<GenericRow | null>(null);

  const canManage = ['owner', 'admin', 'doctor', 'patient'].includes(role || '');

  async function load() {
    if (!pid) return;
    try {
      setItems((await api(`/sharing?patient_id=${encodeURIComponent(pid)}`, token)).items || []);
    } catch (e) {
      setMessage(err(e));
    }
  }

  useEffect(() => {
    load();
  }, [pid]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    try {
      const d = await api('/sharing', token, {
        method: 'POST',
        body: JSON.stringify({
          patient_id: pid,
          ...form,
          expires_at: form.expires_at || null,
        }),
      });

      setForm({
        ...form,
        record_id: '',
        shared_with: '',
        expires_at: '',
      });

      setMessage(d.token ? 'Share created. Copy the token now; it is returned only at creation.' : 'Share created.');
      load();
    } catch (e) {
      setMessage(err(e));
    }
  }

  async function revoke(id: string) {
    try {
      await api('/sharing/revoke', token, {
        method: 'POST',
        body: JSON.stringify({ share_id: id }),
      });

      setMessage('Share revoked.');
      load();
    } catch (e) {
      setMessage(err(e));
    }
  }

  async function redeem(e: React.FormEvent) {
    e.preventDefault();
    try {
      const d = await api('/sharing/redeem', token, {
        method: 'POST',
        body: JSON.stringify({ token: redeemToken.trim() }),
      });

      setRedeemed(d);
      setMessage('Share opened. Access was recorded.');
    } catch (e) {
      setRedeemed(null);
      setMessage(err(e));
    }
  }

  return (
    <>
      <section className="panel">
        <h2>Sharing center</h2>
        <PatientSelect patients={patients} pid={pid} setPid={setPid} />

        {pid && canManage && (
          <form onSubmit={create}>
            <label>
              Resource type
              <select
                value={form.resource_type}
                onChange={(e) => setForm({ ...form, resource_type: e.target.value })}
              >
                <option value="medication">Medication</option>
                <option value="ehr">Clinical record</option>
                <option value="document">Document</option>
                <option value="encounter">Encounter</option>
                <option value="prescription">Prescription</option>
              </select>
            </label>

            <label>
              Record/resource ID
              <input
                required
                value={form.record_id}
                onChange={(e) => setForm({ ...form, record_id: e.target.value })}
              />
            </label>

            <label>
              Recipient identifier
              <input
                required
                value={form.shared_with}
                onChange={(e) => setForm({ ...form, shared_with: e.target.value })}
              />
            </label>

            <label>
              Expiry (optional)
              <input
                type="datetime-local"
                value={form.expires_at}
                onChange={(e) => setForm({ ...form, expires_at: e.target.value })}
              />
            </label>

            <button type="submit">Create secure share</button>
          </form>
        )}
      </section>

      <section className="panel">
        <h2>Open a secure share</h2>
        <form onSubmit={redeem}>
          <label>
            Share token
            <input
              required
              minLength={20}
              value={redeemToken}
              onChange={(e) => setRedeemToken(e.target.value)}
              placeholder="Paste secure share token"
            />
          </label>
          <button type="submit">Open shared record</button>
        </form>

        {redeemed && (
          <div className="notice">
            <strong>{redeemed.share?.resource_type || 'Shared record'}</strong>
            <pre className="bundle-preview">{JSON.stringify(redeemed.record, null, 2)}</pre>
          </div>
        )}
      </section>
    </>
  );
}

function Users({
  token,
  role,
  setMessage,
}: {
  token: string;
  role?: string;
  setMessage: (s: string) => void;
}) {
  const [items, setItems] = useState<GenericRow[]>([]);
  const [form, setForm] = useState({
    username: '',
    password: '',
    full_name: '',
    role: 'doctor',
    patient_id: '',
    email: '',
  });

  const [reset, setReset] = useState({
    target_user_id: '',
    new_password: '',
  });

  async function load() {
    try {
      setItems((await api('/users', token)).items || []);
    } catch (e) {
      setMessage(err(e));
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api('/users', token, {
        method: 'POST',
        body: JSON.stringify({
          ...form,
          patient_id: form.patient_id || null,
          email: form.email || null,
        }),
      });

      setForm({
        username: '',
        password: '',
        full_name: '',
        role: 'doctor',
        patient_id: '',
        email: '',
      });

      setMessage('User account created.');
      load();
    } catch (e) {
      setMessage(err(e));
    }
  }

  async function resetPassword(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api('/users/password-reset', token, {
        method: 'POST',
        body: JSON.stringify(reset),
      });

      setReset({ target_user_id: '', new_password: '' });
      setMessage('Password reset completed.');
    } catch (e) {
      setMessage(err(e));
    }
  }

  return (
    <>
      <section className="panel">
        <h2>User management</h2>
        {items.length ? (
          <div className="table">
            {items.map((x, i) => (
              <div className="row static" key={x.user_id || i}>
                <b>{x.username}</b>
                <span>{x.full_name} Â· {x.role}</span>
                <small>{x.email || 'No email'} Â· {x.patient_id ? 'Linked Patient' : 'Unlinked'}</small>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty">No user accounts found.</div>
        )}
      </section>

      <section className="panel">
        <h2>Create account</h2>
        <form onSubmit={create}>
          <label>
            Full name
            <input required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          </label>
          <label>
            Username
            <input required value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
          </label>
          <label>
            Email
            <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </label>
          <label>
            Role
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              {role === 'owner' && <option value="admin">Admin</option>}
              <option value="doctor">Doctor</option>
              <option value="staff">Staff</option>
              <option value="patient">Patient</option>
            </select>
          </label>
          <label>
            Temporary password
            <input required minLength={8} type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </label>
          <button type="submit">Create user</button>
        </form>
      </section>
    </>
  );
}

function Audit({ token }: { token: string }) {
  const [items, setItems] = useState<Audit[]>([]);
  const [filters, setFilters] = useState({
    actor_role: '',
    action: '',
    category: '',
    resource_type: '',
    result: '',
    patient_id: '',
  });

  async function load() {
    try {
      const qs = new URLSearchParams(Object.entries(filters).filter(([, v]) => v));
      setItems((await api(`/audit${qs.toString() ? `?${qs}` : ''}`, token)).items || []);
    } catch {
      setItems([]);
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <section className="panel">
      <h2>System audit trail</h2>
      {items.length ? (
        <div className="table">
          {items.map((x, i) => (
            <div className="row static" key={x.event_id || i}>
              <b>{x.action || 'Event'}</b>
              <span>{x.actor_role || 'â€”'} Â· {x.result || 'â€”'} Â· {x.resource_type || 'â€”'}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="empty">No audit events match selected filters.</div>
      )}
    </section>
  );
}

function HealthVault({
  token,
  role,
  setMessage,
}: {
  token: string;
  role?: string;
  setMessage: (s: string) => void;
}) {
  const patients = usePatients(token, setMessage);
  const [pid, setPid] = useState('');
  const [patient, setPatient] = useState<Patient | null>(null);
  const [medications, setMedications] = useState<Medication[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!pid) {
      setPatient(null);
      setMedications([]);
      return;
    }
    setLoading(true);
    Promise.all([
      api(`/patients/${encodeURIComponent(pid)}`, token),
      api(`/patients/${encodeURIComponent(pid)}/medications`, token),
    ])
      .then(([patientData, medicationData]) => {
        setPatient(patientData as Patient);
        setMedications((medicationData.items || []) as Medication[]);
      })
      .catch((e) => setMessage(err(e)))
      .finally(() => setLoading(false));
  }, [pid, token, setMessage]);

  function exportJson() {
    if (!patient) return;
    downloadText(
      `recordguard-${patient.public_patient_id}-vault.json`,
      JSON.stringify({
        exportedAt: new Date().toISOString(),
        source: 'RecordGuard Health Vault',
        patient,
        medications,
      }, null, 2),
    );
  }

  function exportCsv() {
    if (!patient) return;
    const rows = [
      ['Patient ID', 'Name', 'Age', 'Sex', 'Blood group', 'Phone'],
      [patient.public_patient_id, patient.name, patient.age, patient.sex, patient.blood_group || '', patient.phone_number || ''],
    ];
    downloadText(
      `recordguard-${patient.public_patient_id}-vault.csv`,
      rows.map((row) => row.map(csvEscape).join(',')).join('\n'),
      'text/csv;charset=utf-8',
    );
  }

  return (
    <>
      <section className="panel">
        <h2>Patient Health Vault</h2>
        <p className="muted">A patient-centered, authorized view of the record. Verify the source record before relying on any information.</p>
        <PatientSelect patients={patients} pid={pid} setPid={setPid} />
        {loading && <div className="status">Loading authorized recordâ€¦</div>}
        {patient && (
          <div className="grid">
            <article><span>Patient</span><strong>{patient.name}</strong><small>{patient.public_patient_id}</small></article>
            <article><span>Blood group</span><strong>{patient.blood_group || 'Not recorded'}</strong><small>Verify against the source record</small></article>
            <article><span>Phone</span><strong>{patient.phone_number || 'Not recorded'}</strong><small>Contact information</small></article>
          </div>
        )}
      </section>

      {patient && (
        <>
          <section className="panel">
            <h2>Emergency Health Card</h2>
            <p className="muted">A concise record view for authorized use. RecordGuard is not a diagnosis or prescribing tool.</p>
            <div className="table">
              <div className="row static"><b>Name</b><span>{patient.name}</span></div>
              <div className="row static"><b>Patient ID</b><span>{patient.public_patient_id}</span></div>
              <div className="row static"><b>Blood group</b><span>{patient.blood_group || 'Not recorded'}</span></div>
              <div className="row static"><b>Recorded medication responses</b><span>{medications.length}</span></div>
            </div>
            <div className="actions">
              <button type="button" onClick={exportJson}>Download JSON</button>
              <button type="button" onClick={exportCsv}>Download CSV</button>
            </div>
          </section>

          <section className="panel">
            <h2>Data portability</h2>
            <p className="muted">Exports contain only the authorized data currently loaded in this Health Vault view.</p>
          </section>
        </>
      )}
    </>
  );
}

function Interoperability({
  token,
  role,
  setMessage,
}: {
  token: string;
  role?: string;
  setMessage: (s: string) => void;
}) {
  const patients = usePatients(token, setMessage);
  const [pid, setPid] = useState('');
  const [capabilities, setCapabilities] = useState<GenericRow | null>(null);
  const [bundle, setBundle] = useState<GenericRow | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api('/interoperability/capabilities', token)
      .then(setCapabilities)
      .catch((e) => setMessage(err(e)));
  }, [token, setMessage]);

  async function loadBundle() {
    if (!pid) return;
    setLoading(true);
    try {
      const data = await api(`/interoperability/fhir/patients/${encodeURIComponent(pid)}`, token);
      setBundle(data);
    } catch (e) {
      setMessage(err(e));
    } finally {
      setLoading(false);
    }
  }

  function downloadBundle() {
    if (!bundle) return;
    downloadText(`recordguard-${pid}-interoperability.json`, JSON.stringify(bundle, null, 2));
  }

  return (
    <section className="panel">
      <h2>Interoperability</h2>
      <p className="muted">FHIR-inspired prototype. It exposes an authorized, read-only representation and preserves provenance.</p>
      <p className="form-help">This interface does not infer diagnoses or prescribe treatment.</p>
      <PatientSelect patients={patients} pid={pid} setPid={setPid} />
      <div className="actions">
        <button type="button" onClick={loadBundle} disabled={!pid || loading}>{loading ? 'Loadingâ€¦' : 'Load interoperability record'}</button>
        <button type="button" onClick={downloadBundle} disabled={!bundle}>Download interoperability JSON</button>
      </div>
      {capabilities && (
        <div className="notice">
          <strong>Supported resources</strong>
          <p>{(capabilities.resources || []).join(' Â· ')}</p>
        </div>
      )}
      {bundle && (
        <div className="notice">
          <strong>Read-only bundle ready</strong>
          <p>{bundle.type || 'Bundle'} Â· {Array.isArray(bundle.entry) ? bundle.entry.length : 0} resources Â· provenance preserved</p>
        </div>
      )}
    </section>
  );
}

function StatusBadge({ status }: { status?: string }) {
  const s = status || 'ACTIVE';
  return <span className={`badge badge-${s.toLowerCase().replaceAll('_', '-')}`}>{s.replaceAll('_', ' ')}</span>;
}

function Settings({ user }: { user: User | null }) {
  return (
    <section className="panel">
      <h2>Account &amp; organization</h2>
      <dl>
        <dt>Name</dt>
        <dd>{user?.full_name || 'â€”'}</dd>
        <dt>Role</dt>
        <dd>{user?.role || 'â€”'}</dd>
      </dl>
    </section>
  );
}










