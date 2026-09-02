#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

command -v docker >/dev/null || { echo "Docker is required for live PostgreSQL validation."; exit 1; }
command -v python3 >/dev/null || { echo "Python 3 is required."; exit 1; }
command -v npm >/dev/null || { echo "Node.js/npm is required."; exit 1; }

if [[ ! -f .env.validation ]]; then
  cp .env.validation.example .env.validation
  echo "Created .env.validation. Set POSTGRES_PASSWORD and rerun."
  exit 1
fi
set -a; source .env.validation; set +a
[[ -n "${POSTGRES_PASSWORD:-}" && "$POSTGRES_PASSWORD" != replace-with* ]] || { echo "POSTGRES_PASSWORD is not configured."; exit 1; }

python3 -m pip install -r requirements.txt -r requirements-web.txt
python3 -m pip install pip-audit

docker compose -f docker-compose.postgres.yml --env-file .env.validation up -d postgres
for i in {1..30}; do
  status="$(docker inspect --format='{{.State.Health.Status}}' recordguard-postgres 2>/dev/null || true)"
  [[ "$status" == healthy ]] && break
  sleep 2
done
[[ "$(docker inspect --format='{{.State.Health.Status}}' recordguard-postgres)" == healthy ]] || { docker compose -f docker-compose.postgres.yml logs postgres; exit 1; }

python3 scripts/apply_postgres_schema.py
(cd apps/web && npm install --no-audit --no-fund && npm run build)
python3 scripts/final_validation.py
