#!/usr/bin/env bash
set -euo pipefail

# RC9 dual-Agent real interoperability preflight.
# This script only checks prerequisites; it does not start, wake, or control Agent Runtime.

: "${DAEP_API_URL:?DAEP_API_URL is required}"
: "${DAEP_MEMBER_TOKEN_A:?DAEP_MEMBER_TOKEN_A is required}"
: "${DAEP_MEMBER_TOKEN_B:?DAEP_MEMBER_TOKEN_B is required}"

if [[ "${DAEP_MEMBER_TOKEN_A}" == "${DAEP_MEMBER_TOKEN_B}" ]]; then
  echo "FAIL: Member A and Member B tokens must be different." >&2
  exit 1
fi

if [[ -z "${DAEP_PROJECT_ID:-}" ]]; then
  echo "FAIL: DAEP_PROJECT_ID is required." >&2
  exit 1
fi

command -v curl >/dev/null || { echo "FAIL: curl is required." >&2; exit 1; }
command -v python >/dev/null || { echo "FAIL: python is required." >&2; exit 1; }

echo "[1/5] DAEP readiness"
curl --fail --silent --show-error "${DAEP_API_URL%/}/readyz" >/dev/null

echo "[2/5] Member A authentication"
curl --fail --silent --show-error   -H "Authorization: Bearer ${DAEP_MEMBER_TOKEN_A}"   "${DAEP_API_URL%/}/api/v1/projects/${DAEP_PROJECT_ID}/agents" >/dev/null

echo "[3/5] Member B authentication"
curl --fail --silent --show-error   -H "Authorization: Bearer ${DAEP_MEMBER_TOKEN_B}"   "${DAEP_API_URL%/}/api/v1/projects/${DAEP_PROJECT_ID}/agents" >/dev/null

echo "[4/5] Local MCP adapter import"
python -c 'from daep_mcp.server import mcp; print("MCP adapter import: OK")'

echo "[5/5] Independent identity guard"
echo "A token != B token: PASS"
echo "Preflight PASS. Continue with docs/RC9_AGENT_INTEROPERABILITY_DRILL.md."
