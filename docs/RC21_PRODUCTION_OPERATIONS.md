# RC21 production operations and release runbook

## Production topology

Use `compose.production.yaml` rather than the legacy RC8 compose file for a new production deployment. The production topology separates:
- `daep_bootstrap`: PostgreSQL bootstrap/migration superuser, exposed only to the one-shot migration service and database administration.
- `daep_runtime`: application data-plane login, NOSUPERUSER and NOBYPASSRLS.
- `daep_privileged_login`: application privileged-operation login, NOSUPERUSER and NOBYPASSRLS, granted membership in the migration-created `daep_privileged` role only after migrations complete.

The API container receives only runtime and privileged application credentials; it never receives the bootstrap password. PostgreSQL is on an internal Compose network. The API binds to loopback by default; terminate TLS and apply authentication/rate-limits at a trusted reverse proxy before exposing it publicly. Set `DAEP_BIND_ADDRESS=0.0.0.0` only when an external firewall/proxy is deliberately configured.

## Required secrets

Set independent, randomly generated values (at least 32 characters) for:
- `DAEP_ADMIN_TOKEN`
- `DAEP_WORKER_TOKEN`
- `DAEP_POSTGRES_PASSWORD` (bootstrap only)
- `DAEP_RUNTIME_DB_PASSWORD`
- `DAEP_PRIVILEGED_DB_PASSWORD`

Do not reuse passwords. Store production values in a secret manager or protected environment file; do not commit `.env`. Rotate credentials independently. Optional OIDC and webhook secrets must also be managed as secrets.

## Deploy and upgrade

1. Verify a tested backup exists and record its checksum.
2. Pin the PostgreSQL image to an approved patch digest in the deployment environment for regulated production; this repository uses major tag `postgres:17` for compatibility testing.
3. Build the application image from the reviewed commit.
4. Run `docker compose -f compose.production.yaml config` and inspect rendered configuration without publishing its output (it contains interpolated secrets).
5. Start with `docker compose -f compose.production.yaml up --build -d postgres migrate daep-api`. The migration service bootstraps the schema, runs Alembic to head, then grants the least-privilege application logins their required roles and object privileges.
6. Verify `/readyz`, `/health`, authenticated API smoke tests, and PostgreSQL RLS smoke tests before routing traffic.
7. Start the optional broker worker only when the broker URL and its independent 32-character token are configured: `docker compose -f compose.production.yaml --profile broker up -d daep-worker`.

Migrations are forward-only operational changes. Do not assume a downgrade is a safe production rollback. For rollback, deploy the previous application image only if it is schema-compatible; otherwise restore a verified backup to a separate database and switch traffic after validation.

## Backup

Set `DAEP_BACKUP_DIR` to a directory accessible to the operator with restricted permissions, then run `scripts/backup_postgres.sh`. It creates a PostgreSQL custom-format dump and SHA-256 sidecar with restrictive file permissions. Copy backups off-host, encrypt them using the organization's KMS/backup system, and enforce retention independently. The script does not configure offsite replication or encryption at rest by itself.

## Restore drill

1. Provision a separate, empty PostgreSQL database named by `DAEP_RESTORE_DATABASE` (default `daep_restore`) and ensure the bootstrap login can connect.
2. Set `DAEP_BACKUP_FILE` to the dump and `DAEP_CONFIRM_RESTORE=YES`.
3. Run `scripts/restore_postgres.sh`. It verifies the SHA-256 sidecar and archive readability, then restores without dropping existing objects.
4. Run schema checks, API smoke tests and tenant/RLS isolation checks against the restored database before any cutover.

Never test restore against the live production database. A restore drill is not complete until application-level reads and authorization boundaries are verified.

## Health and incident response

- `/health`: process/database operational health summary.
- `/readyz`: readiness check used by container orchestration.
- Preserve logs and request/correlation IDs; never include access tokens, passwords or raw connection strings in incident tickets.
- If database readiness fails, stop traffic, inspect PostgreSQL connectivity and migration state, then restore service only after validation.
- The broker worker is optional and independently deployable; the platform's durable outbox does not guarantee that an arbitrary sleeping local MCP Host can be remotely awakened.

## Release acceptance checklist

- [ ] Secrets generated, independent, protected and not committed.
- [ ] Production compose rendered and reviewed securely.
- [ ] Bootstrap, runtime and privileged database identities verified.
- [ ] Migrations upgraded to Alembic head.
- [ ] API health/readiness and authenticated smoke tests pass.
- [ ] PostgreSQL RLS tenant-isolation tests pass.
- [ ] Backup copied off-host and checksum verified.
- [ ] Restore drill completed against a separate empty database.
- [ ] Reverse proxy TLS, firewall, CORS and rate limits reviewed.
- [ ] Monitoring, log retention, alert routing and on-call ownership configured.
- [ ] Previous image and schema-compatible rollback plan recorded.
- [ ] Product owner acceptance completed.

Passing repository CI does not constitute production deployment, disaster-recovery certification or GA approval.
