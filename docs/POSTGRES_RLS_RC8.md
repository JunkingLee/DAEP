# PostgreSQL / RLS — RC8

RC8 adds PostgreSQL Row-Level Security policies for tenant-owned tables:
`members`, `projects`, `events`, `artifacts`, `outbox`, and `messages`.

The API sets transaction-local `app.tenant_id` and `app.platform_admin` from
an authenticated member token before application queries. The RLS migration
also uses `FORCE ROW LEVEL SECURITY` so a normal table owner cannot silently
bypass policies.

## Deployment requirements

1. Use a dedicated PostgreSQL application role; do not run the API as a
   PostgreSQL superuser.
2. Apply Alembic migrations before starting API workers.
3. Keep `DAEP_ADMIN_TOKEN` and `DAEP_WORKER_TOKEN` separate.
4. Treat the platform-admin role as a narrowly controlled bootstrap identity.
5. Validate RLS with two tenant accounts before production rollout.

SQLite does not implement these policies; local development continues to use
application-level tenant checks.
