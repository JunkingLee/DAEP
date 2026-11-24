# DAEP Enterprise 1.0.0-rc8

## Scope

RC8 hardens the PostgreSQL tenancy boundary and prepares the platform for real
PostgreSQL integration testing.

## Delivered

- PostgreSQL transaction-local tenant context using `app.tenant_id`.
- Platform-admin and internal-worker service context separation.
- Authentication lookup path that can resolve a token before tenant context is known.
- WebSocket authentication updated for PostgreSQL RLS compatibility.
- Durable inbox `messages.tenant_id` ownership.
- Alembic `0009_rc8_message_tenant` migration.
- Alembic `0010_rc8_postgres_rls` migration for PostgreSQL RLS.
- RLS uses `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` on:
  `members`, `projects`, `events`, `artifacts`, `outbox`, `messages`.
- RLS policy supports tenant isolation and the narrowly scoped platform-admin context.
- RC8 integration test matrix and migration contract tests.
- Regression suite: 26 passed.

## Important deployment rule

The API must use a dedicated PostgreSQL application role and must not run as a
PostgreSQL superuser. Apply Alembic migrations before enabling production API
traffic. Validate two-tenant isolation in a real PostgreSQL environment before
GA.

## Not claimed as complete

This release has not been validated against a live PostgreSQL server, a live
OIDC provider, Kafka/RabbitMQ, GitHub/GitLab, or a real MCP Host in this build
environment. Load, failover, backup/restore and independent penetration testing
remain GA gates.
