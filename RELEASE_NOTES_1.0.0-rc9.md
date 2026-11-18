# DAEP Enterprise 1.0.0-rc9

## RC9 focus

RC9 moves the PostgreSQL RLS implementation from migration-only hardening toward a continuously tested runtime contract.

### Changes

- Establishes transaction-local PostgreSQL `app.tenant_id` and `app.platform_admin` context in the PostgreSQL connection wrapper before application queries.
- Keeps authentication lookup, bootstrap and the dedicated worker service path explicitly privileged for the RLS policy contract.
- Adds GitHub Actions CI for Python compilation, API tests, Alembic head validation and a real PostgreSQL 17 migration/RLS-policy job.
- Keeps SQLite as a local development/test backend.
- Keeps the existing durable inbox/outbox, MCP adapter, local Agent Bridge and worker architecture unchanged.

## Verification boundary

The PostgreSQL job is designed to execute against a real PostgreSQL 17 service in GitHub Actions. Local RC9 development does not claim that this external CI job has passed until GitHub reports a successful run.

RC9 remains a release candidate until live PostgreSQL tenant-isolation tests, OIDC IdP integration, external broker integration, Git provider integration, MCP Host compatibility, load testing, backup/restore and independent security testing are complete.
