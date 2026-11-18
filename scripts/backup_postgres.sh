#!/bin/sh
set -euf
set -o pipefail 2>/dev/null || true
: "${DAEP_BACKUP_DIR:?Set DAEP_BACKUP_DIR to a protected backup directory}"
mkdir -p "$DAEP_BACKUP_DIR"
umask 077
stamp=$(date -u +%Y%m%dT%H%M%SZ)
file="$DAEP_BACKUP_DIR/daep-$stamp.dump"
compose=${DAEP_COMPOSE_FILE:-compose.production.yaml}
docker compose -f "$compose" exec -T postgres sh -ec 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$file"
test -s "$file"
docker compose -f "$compose" exec -T postgres pg_restore --list < "$file" >/dev/null
sha256sum "$file" > "$file.sha256"
chmod 600 "$file" "$file.sha256"
printf 'Backup created: %s\n' "$file"
printf 'Checksum: %s\n' "$(cut -d ' ' -f 1 "$file.sha256")"
