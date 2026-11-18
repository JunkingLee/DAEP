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
docker compose -f "$compose" exec -T postgres psql -U daep_bootstrap -d "${DAEP_RESTORE_DATABASE:-daep_restore}" -v ON_ERROR_STOP=1 <<'SQL'
GRANT daep_privileged TO daep_privileged_login;
GRANT USAGE ON SCHEMA public TO daep_runtime, daep_privileged_login;
GRANT CREATE ON SCHEMA public TO daep_privileged_login;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO daep_runtime, daep_privileged_login;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO daep_runtime, daep_privileged_login;
DO $
DECLARE r record;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables WHERE schemaname='public' LOOP
    EXECUTE format('ALTER TABLE public.%I OWNER TO daep_privileged_login', r.tablename);
  END LOOP;
  FOR r IN SELECT sequencename FROM pg_sequences WHERE schemaname='public' LOOP
    EXECUTE format('ALTER SEQUENCE public.%I OWNER TO daep_privileged_login', r.sequencename);
  END LOOP;
END
$;
SQL
echo "Restore completed. Validate the restored database before switching application traffic."
