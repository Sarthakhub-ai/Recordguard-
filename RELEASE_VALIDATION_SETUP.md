# RecordGuard Release Validation Setup

This is the concrete procedure for clearing the four remaining local validation gates.

## 1. PostgreSQL live validation

Install and start Docker Desktop. From the project root:

```powershell
Copy-Item .env.validation.example .env.validation
```

Edit `.env.validation` and replace `POSTGRES_PASSWORD` with a strong local password. Keep the file uncommitted.

Then on Windows PowerShell:

```powershell
.\scripts\setup_release_validation.ps1
```

Or on Linux/macOS:

```bash
./scripts/setup_release_validation.sh
```

The setup starts PostgreSQL 16, waits for its health check, applies the RecordGuard schema, sets `RECORDGUARD_SESSION_BACKEND=postgres`, and runs the live PostgreSQL tests.

## 2. Production web-origin configuration

For local validation the example uses:

`RECORDGUARD_WEB_ORIGINS=http://localhost:3000`

For a real deployment, replace this with the exact HTTPS frontend origin, for example:

`RECORDGUARD_WEB_ORIGINS=https://app.example.com`

Do not use `*` when credentialed cookies are enabled. Keep the API and frontend origins explicit.

## 3. Next.js production build

The previous failure was not an application failure; dependencies were not installed. The setup script runs:

```powershell
cd apps/web
npm install --no-audit --no-fund
npm run build
```

If installation times out, retry from a stable network or CI runner. The build must finish successfully before release.

## 4. Dependency vulnerability scan

Install the scanner into the active Python environment:

```powershell
python -m pip install --upgrade pip pip-audit
python -m pip_audit -r requirements.txt -r requirements-web.txt
```

A real release should also scan the JavaScript dependency tree in CI (for example with `npm audit` at the chosen severity threshold).

## One-command path

After `.env.validation` is configured, run:

```powershell
.\scripts\setup_release_validation.ps1
```

The script stops on failure and does not mark blocked gates as passed.
