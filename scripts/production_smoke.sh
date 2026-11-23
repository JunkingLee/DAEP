#!/usr/bin/env bash
set -euo pipefail

: "${DAEP_COMPOSE_FILE:=compose.production.yaml}"
: "${DAEP_ENV_FILE:=.env}"
: "${DAEP_SMOKE_URL:=http://127.0.0.1:8000}"
: "${DAEP_ADMIN_TOKEN:?Set DAEP_ADMIN_TOKEN}"

compose=(docker compose -f "$DAEP_COMPOSE_FILE")
if [[ -f "$DAEP_ENV_FILE" ]]; then
  compose+=(--env-file "$DAEP_ENV_FILE")
fi

echo "[1/4] compose config"
"${compose[@]}" config --quiet

echo "[2/4] service state"
"${compose[@]}" ps

echo "[3/4] readiness"
curl --fail --silent --show-error "$DAEP_SMOKE_URL/readyz" | grep -q '"status":"ready"'

echo "[4/4] authenticated API"
curl --fail --silent --show-error \
  -H "Authorization: Bearer $DAEP_ADMIN_TOKEN" \
  "$DAEP_SMOKE_URL/api/v1/projects" >/dev/null

echo "DAEP production smoke check passed"
