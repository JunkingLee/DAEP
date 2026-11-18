#!/bin/sh
set -eu
: "${DAEP_RUNTIME_DB_PASSWORD:?DAEP_RUNTIME_DB_PASSWORD is required}"
: "${DAEP_PRIVILEGED_DB_PASSWORD:?DAEP_PRIVILEGED_DB_PASSWORD is required}"
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=runtime_password="$DAEP_RUNTIME_DB_PASSWORD" \
  --set=privileged_password="$DAEP_PRIVILEGED_DB_PASSWORD" <<'SQL'
CREATE ROLE daep_runtime LOGIN PASSWORD :'runtime_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
CREATE ROLE daep_privileged_login LOGIN PASSWORD :'privileged_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
GRANT CONNECT ON DATABASE daep TO daep_runtime, daep_privileged_login;
GRANT USAGE ON SCHEMA public TO daep_runtime, daep_privileged_login;
ALTER DEFAULT PRIVILEGES FOR ROLE daep_bootstrap IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO daep_runtime, daep_privileged_login;
ALTER DEFAULT PRIVILEGES FOR ROLE daep_bootstrap IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO daep_runtime, daep_privileged_login;
SQL
