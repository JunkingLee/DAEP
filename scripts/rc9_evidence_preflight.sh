#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST="$ROOT/docs/RC9_FINAL_EVIDENCE_PACKAGE.md"

echo "DAEP RC9 evidence preflight"
echo "Structure check only; this script never marks real-world gates as PASS."

for path in   docs/RC9_FINAL_EVIDENCE_PACKAGE.md   docs/RC9_BROWSER_ACCEPTANCE_RUNBOOK.md   docs/RC9_PRODUCTION_BACKUP_RESTORE_DRILL.md   docs/RC9_AGENT_INTEROPERABILITY_DRILL.md
do
  test -f "$ROOT/$path"
  echo "FOUND: $path"
done

grep -q "Real Browser Acceptance" "$MANIFEST"
grep -q "Production Backup/Restore" "$MANIFEST"
grep -q "Dual-Agent Interoperability" "$MANIFEST"
grep -q "不得 GA" "$MANIFEST"

echo "Evidence package structure PASS."
echo "Real execution remains NOT EXECUTED until human evidence is recorded."
