#!/bin/sh
set -eu
: "${DAEP_BACKUP_FILE:?Set DAEP_BACKUP_FILE to a verified custom-format dump}"
: "${DAEP_CONFIRM_RESTORE:?Set DAEP_CONFIRM_RESTORE=YES after preparing an EMPTY target database}"
[ "$DAEP_CONFIRM_RESTORE" = YES ] || { echo "Restore not confirmed" >&2; exit 2; }
[ -s "$DAEP_BACKUP_FILE" ] || { echo "Backup file missing or empty" >&2; exit 2; }
if [ -f "$DAEP_BACKUP_FILE.sha256" ]; then
  (cd "$(dirname "$DAEP_BACKUP_FILE")" && sha256sum -c "$(basename "$DAEP_BACKUP_FILE").sha256")
else
  echo "Checksum sidecar missing; refusing restore" >&2; exit 2
fi
compose=${DAEP_COMPOSE_FILE:-compose.production.yaml}
docker compose -f "$compose" exec -T postgres pg_restore --list < "$DAEP_BACKUP_FILE" >/dev/null
# Restore only into a separately provisioned, empty database; never drops existing objects.
docker compose -f "$compose" exec -T postgres pg_restore -U daep_bootstrap -d "${DAEP_RESTORE_DATABASE:-daep_restore}" --no-owner --no-privileges --exit-on-error < "$DAEP_BACKUP_FILE"
echo "Restore completed. Validate the restored database before switching application traffic."
