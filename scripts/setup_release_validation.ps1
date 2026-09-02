$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "RecordGuard release-validation setup" -ForegroundColor Cyan

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker is required for live PostgreSQL validation. Install Docker Desktop, start it, then rerun this script."
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "Python is required." }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "Node.js/npm is required for the Web build." }

if (-not (Test-Path .env.validation)) {
  Copy-Item .env.validation.example .env.validation
  Write-Host "Created .env.validation. Edit POSTGRES_PASSWORD before continuing." -ForegroundColor Yellow
  throw "Set a real local POSTGRES_PASSWORD in .env.validation, then rerun."
}

Get-Content .env.validation | ForEach-Object {
  if ($_ -match '^\s*([^#=]+)=(.*)$') {
    $name=$matches[1].Trim(); $value=$matches[2].Trim()
    if ($value -and $name -notmatch '^#') { [Environment]::SetEnvironmentVariable($name,$value,'Process') }
  }
}

if ([string]::IsNullOrWhiteSpace($env:POSTGRES_PASSWORD) -or $env:POSTGRES_PASSWORD -like 'replace-with*') {
  throw "POSTGRES_PASSWORD is not configured in .env.validation."
}

python -m pip install -r requirements.txt -r requirements-web.txt
python -m pip install pip-audit

docker compose -f docker-compose.postgres.yml --env-file .env.validation up -d postgres

Write-Host "Waiting for PostgreSQL..."
for ($i=0; $i -lt 30; $i++) {
  $status = docker inspect --format='{{.State.Health.Status}}' recordguard-postgres 2>$null
  if ($status -eq 'healthy') { break }
  Start-Sleep -Seconds 2
}
if ((docker inspect --format='{{.State.Health.Status}}' recordguard-postgres) -ne 'healthy') {
  throw "PostgreSQL did not become healthy. Run: docker compose -f docker-compose.postgres.yml logs postgres"
}

python scripts/apply_postgres_schema.py

Set-Location (Join-Path $Root 'apps/web')
if (-not (Test-Path node_modules)) { npm install --no-audit --no-fund }
npm run build
Set-Location $Root

Write-Host "Running full validation..." -ForegroundColor Cyan
python scripts/final_validation.py
